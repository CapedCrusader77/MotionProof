"""Physical measurement import, parameter calibration and holdout assessment.

CSV schema
----------
One row per sample. A time column plus one or more signal columns. The mapping names the
column and its unit for every signal used:

    output_angle     joint output angle               rad | deg
    motor_angle      motor angle referred to output   rad | deg
    motor_torque     motor shaft torque               N*m
    output_velocity  joint output velocity            rad/s | deg/s

The measurement must be a recording of the *same task* that the calibration simulates.

Calibration and validation use separate data. A holdout taken from a different recording is
independent evidence; a holdout split off the end of the same recording is weaker and is
reported as such. A model is never called validated on its calibration data.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import numpy as np
from pydantic import BaseModel, ConfigDict, Field
from scipy.optimize import least_squares

from motionproof.core.units import ANGLE_TO_RAD
from motionproof.hardware.device import with_parameters
from motionproof.model import MechanicalModel
from motionproof.simulation.tasks import Task

SIGNALS: dict[str, tuple[str, dict[str, float]]] = {
    "output_angle": ("q_out", ANGLE_TO_RAD),
    "motor_angle": ("q_motor", ANGLE_TO_RAD),
    "motor_torque": ("tau_motor", {"n*m": 1.0, "nm": 1.0, "mn*m": 1e-3, "mnm": 1e-3}),
    "output_velocity": ("w_out", {"rad/s": 1.0, "deg/s": ANGLE_TO_RAD["deg"]}),
}
TIME_UNITS = {"s": 1.0, "ms": 1e-3}
PARAMETERS = {"backlash", "stiffness", "friction", "efficiency", "damping", "zero_offset",
              "damping_ratio"}
MAX_ROWS = 2_000_000


class CalibrationError(ValueError):
    pass


class ColumnMap(BaseModel):
    model_config = ConfigDict(extra="forbid")
    column: str
    unit: str


class FitParameter(BaseModel):
    model_config = ConfigDict(extra="forbid")
    joint: str
    name: str
    lower: float
    upper: float


class CalibrationConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    task: Task
    time_column: str = "time"
    time_unit: str = "s"
    signals: dict[str, ColumnMap]
    parameters: list[FitParameter] = Field(min_length=1)
    holdout_fraction: float = Field(default=0.3, gt=0, lt=0.9,
                                    description="used only when no separate holdout file")
    values: dict[str, float] = Field(default_factory=dict,
                                     description="known tolerance values of the measured unit")


@dataclass
class Dataset:
    name: str
    time: np.ndarray
    signals: dict[str, np.ndarray]

    def slice(self, mask: np.ndarray, name: str) -> Dataset:
        return Dataset(name, self.time[mask], {k: v[mask] for k, v in self.signals.items()})


def preview_csv(path: str | Path, rows: int = 8) -> dict[str, Any]:
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        header = next(reader, None)
        if not header:
            raise CalibrationError("the CSV file is empty")
        sample = [row for _, row in zip(range(rows), reader, strict=False)]
        count = len(sample) + sum(1 for _ in reader)
    return {"columns": header, "rows": sample, "row_count": count}


def read_csv(path: str | Path, config: CalibrationConfig, name: str | None = None) -> Dataset:
    p = Path(path)
    if config.time_unit not in TIME_UNITS:
        raise CalibrationError(f"time unit must be one of {sorted(TIME_UNITS)}")
    for sig, cm in config.signals.items():
        if sig not in SIGNALS:
            raise CalibrationError(f"unknown signal {sig!r}; supported: {sorted(SIGNALS)}")
        if cm.unit.lower() not in SIGNALS[sig][1]:
            raise CalibrationError(
                f"signal {sig!r}: unit {cm.unit!r} not supported "
                f"({sorted(SIGNALS[sig][1])})")
    with p.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        cols = reader.fieldnames or []
        needed = [config.time_column, *(c.column for c in config.signals.values())]
        missing = [c for c in needed if c not in cols]
        if missing:
            raise CalibrationError(f"{p.name}: missing columns {missing}; found {cols}")
        data: dict[str, list[float]] = {c: [] for c in needed}
        for line, row in enumerate(reader, start=2):
            if line > MAX_ROWS:
                raise CalibrationError(f"{p.name}: more than {MAX_ROWS} rows")
            try:
                for c in needed:
                    data[c].append(float(row[c]))
            except (TypeError, ValueError) as exc:
                raise CalibrationError(f"{p.name} line {line}: non-numeric value") from exc
    t = np.array(data[config.time_column]) * TIME_UNITS[config.time_unit]
    if len(t) < 10:
        raise CalibrationError(f"{p.name}: at least 10 samples are required")
    if np.any(np.diff(t) <= 0):
        raise CalibrationError(f"{p.name}: time must be strictly increasing")
    sigs = {s: np.array(data[cm.column]) * SIGNALS[s][1][cm.unit.lower()]
            for s, cm in config.signals.items()}
    if not all(np.isfinite(v).all() for v in [t, *sigs.values()]):
        raise CalibrationError(f"{p.name}: contains non-finite values")
    return Dataset(name or p.name, t, sigs)


def _simulate(model: MechanicalModel, config: CalibrationConfig,
              x: np.ndarray) -> dict[str, np.ndarray] | None:
    variant = model.variant(config.values)
    for p, value in zip(config.parameters, x, strict=True):
        if p.joint not in variant.joints:
            raise CalibrationError(f"parameter joint {p.joint!r} has no drive")
        if p.name not in PARAMETERS:
            raise CalibrationError(f"parameter {p.name!r} cannot be calibrated; "
                                   f"choose from {sorted(PARAMETERS)}")
        variant.joints[p.joint] = with_parameters(variant.joints[p.joint],
                                                  {p.name: float(value)})
    res = model.engine.run(variant, config.task, keep_trace=True, trace_points=4000)
    if not res.valid:
        return None
    return {k: np.asarray(v) for k, v in res.trace.items()}


def _predict(trace: dict[str, np.ndarray], ds: Dataset, signal: str) -> np.ndarray:
    return np.asarray(np.interp(ds.time, trace["t"], trace[SIGNALS[signal][0]]),
                      dtype=float)


def _errors(trace: dict[str, np.ndarray], ds: Dataset) -> dict[str, dict[str, float]]:
    out = {}
    for sig, measured in ds.signals.items():
        r = _predict(trace, ds, sig) - measured
        out[sig] = {"rmse": float(np.sqrt(np.mean(r**2))), "mae": float(np.mean(np.abs(r))),
                    "max_abs": float(np.max(np.abs(r))), "samples": int(len(r))}
    return out


def calibrate(model: MechanicalModel, config: CalibrationConfig, calibration: Dataset,
              holdout: Dataset | None = None) -> dict[str, Any]:
    """Least-squares estimate of the selected parameters, assessed on separate data."""
    split: Literal["separate_recording", "same_recording_tail"]
    if holdout is None:
        n_cal = int(round(len(calibration.time) * (1 - config.holdout_fraction)))
        mask = np.arange(len(calibration.time)) < n_cal
        holdout = calibration.slice(~mask, f"{calibration.name} [last "
                                           f"{config.holdout_fraction:.0%}]")
        calibration = calibration.slice(mask, f"{calibration.name} [first "
                                              f"{1 - config.holdout_fraction:.0%}]")
        split = "same_recording_tail"
    else:
        split = "separate_recording"
    task_end = model.engine.run(model.variant(config.values), config.task).metrics.get(
        "task_duration", 0.0)
    if calibration.time[-1] > task_end + 1e-6 or holdout.time[-1] > task_end + 1e-6:
        raise CalibrationError(
            f"measurements extend to {max(calibration.time[-1], holdout.time[-1]):.3f} s but "
            f"the simulated task lasts {task_end:.3f} s; the task must match the recording")

    lo = np.array([p.lower for p in config.parameters])
    hi = np.array([p.upper for p in config.parameters])
    if np.any(hi <= lo):
        raise CalibrationError("every parameter needs upper > lower")
    scales = {s: float(np.std(v)) or 1.0 for s, v in calibration.signals.items()}

    def residual(u: np.ndarray) -> np.ndarray:
        trace = _simulate(model, config, lo + u * (hi - lo))
        if trace is None:
            return np.full(sum(len(v) for v in calibration.signals.values()), 1e3)
        return np.concatenate([(_predict(trace, calibration, s) - m) / scales[s]
                               for s, m in calibration.signals.items()])

    # a coarse multi-start guards against the non-smooth dead band trapping the solver; the
    # starts near the bounds reach values that sit on a bound (an ideal efficiency of 1)
    starts = [np.full(len(lo), u) for u in (0.5, 0.2, 0.8, 0.02, 0.98)]
    best = None
    for u0 in starts:
        sol = least_squares(residual, u0, bounds=(0.0, 1.0), diff_step=2e-2, xtol=1e-10,
                            ftol=1e-10, max_nfev=60 * len(lo))
        if best is None or sol.cost < best.cost:
            best = sol
    assert best is not None
    x = lo + best.x * (hi - lo)
    trace = _simulate(model, config, x)
    if trace is None:
        raise CalibrationError("the calibrated model does not simulate; widen the bounds")

    # --- identifiability from the Jacobian at the optimum -------------------------------
    warnings: list[str] = []
    jac = best.jac / (hi - lo)  # d residual / d physical parameter
    n_res, n_par = jac.shape
    dof = max(n_res - n_par, 1)
    sigma2 = 2 * best.cost / dof
    jtj = jac.T @ jac
    col = np.sqrt(np.diag(jtj))
    params: list[dict[str, Any]] = []
    corr = None
    if np.any(col < 1e-12):
        cond = float("inf")
        std = np.full(n_par, np.inf)
    else:
        scaled = jtj / np.outer(col, col)
        cond = float(np.linalg.cond(scaled))
        cov = np.linalg.pinv(jtj) * sigma2
        std = np.sqrt(np.clip(np.diag(cov), 0, None))
        with np.errstate(invalid="ignore", divide="ignore"):
            corr = cov / np.outer(std, std)
    for i, p in enumerate(config.parameters):
        at_bound = bool(best.x[i] < 1e-3 or best.x[i] > 1 - 1e-3)
        entry = {"joint": p.joint, "name": p.name, "estimate": float(x[i]),
                 "std_error": None if not np.isfinite(std[i]) else float(std[i]),
                 "lower": p.lower, "upper": p.upper, "at_bound": at_bound}
        params.append(entry)
        label = f"{p.joint}.{p.name}"
        if not np.isfinite(std[i]) or col[i] < 1e-12:
            warnings.append(f"{label}: the measured signals are insensitive to this parameter; "
                            "it is not identifiable from this dataset")
        elif std[i] > 0.5 * max(abs(x[i]), 1e-12):
            warnings.append(f"{label}: standard error exceeds 50% of the estimate; poorly "
                            "identified")
        if at_bound:
            warnings.append(f"{label}: estimate sits on a bound; the true optimum may lie "
                            "outside the allowed range")
    if corr is not None:
        for i in range(n_par):
            for j in range(i + 1, n_par):
                if np.isfinite(corr[i, j]) and abs(corr[i, j]) > 0.95:
                    a, b = config.parameters[i], config.parameters[j]
                    warnings.append(
                        f"{a.joint}.{a.name} and {b.joint}.{b.name} are strongly correlated "
                        f"(r = {corr[i, j]:+.2f}): different combinations explain the data "
                        "almost equally well")
    if cond > 1e6:
        warnings.append(f"ill-conditioned estimation problem (condition number {cond:.2g})")
    if split == "same_recording_tail":
        warnings.append("holdout is the tail of the calibration recording, not an independent "
                        "recording; treat the validation result as weak evidence")

    err_cal, err_hold = _errors(trace, calibration), _errors(trace, holdout)
    ratios = {s: err_hold[s]["rmse"] / err_cal[s]["rmse"] if err_cal[s]["rmse"] > 0
              else float("inf") for s in err_cal}
    degraded = [s for s, r in ratios.items() if r > 2.0]
    if degraded:
        warnings.append(f"holdout RMSE is more than twice the calibration RMSE for {degraded}: "
                        "the model does not generalise to the holdout data")
    step = max(1, len(holdout.time) // 400)
    cstep = max(1, len(calibration.time) // 400)

    def series(ds: Dataset, st: int) -> dict[str, Any]:
        return {"name": ds.name, "samples": int(len(ds.time)),
                "time": ds.time[::st].tolist(),
                "signals": {s: {"measured": m[::st].tolist(),
                                "predicted": _predict(trace, ds, s)[::st].tolist(),
                                "residual": (_predict(trace, ds, s) - m)[::st].tolist()}
                            for s, m in ds.signals.items()}}

    return {
        "parameters": params,
        "correlation": None if corr is None else np.nan_to_num(corr).tolist(),
        "condition_number": cond,
        "solver": {"method": "bounded nonlinear least squares (SciPy trf), 5 starts",
                   "evaluations": int(best.nfev), "cost": float(best.cost),
                   "status": str(best.message)},
        "calibration": {"errors": err_cal, **series(calibration, cstep)},
        "holdout": {"errors": err_hold, "split": split, "rmse_ratio": ratios,
                    **series(holdout, step)},
        "warnings": warnings,
        "assessment": "holdout_consistent" if not degraded else "holdout_degraded",
        "statement": "Parameters were fitted on the calibration set only. The holdout errors "
                     "are the evidence of predictive quality; the calibration errors are not.",
    }
