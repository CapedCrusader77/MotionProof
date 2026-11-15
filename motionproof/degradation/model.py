"""Lifetime degradation: transparent, parameterised progressions of drive-train parameters.

These are projections of a stated model, not service-life predictions. A progression is an
equation the user chooses and parameterises (or fits to measurements); MotionProof has no wear
physics, lubrication, material or temperature model. Every output is labelled a model-based
projection and carries the basis of its parameters.
"""

from __future__ import annotations

from typing import Any, Literal

import numpy as np
from numpy.typing import NDArray
from pydantic import BaseModel, ConfigDict, Field
from scipy.optimize import curve_fit

from motionproof.experiments.runner import Constraint
from motionproof.fidelity.static import L1, L2, static_pose
from motionproof.hardware.device import with_parameters
from motionproof.model import MechanicalModel
from motionproof.simulation.tasks import Task

Arr = NDArray[np.float64]
PARAMETERS = ("backlash", "friction", "stiffness", "radial_play", "efficiency", "damping")


class Mechanism(BaseModel):
    """How one joint parameter changes with usage (cycles).

    * ``linear``:       value = initial + rate * cycles
    * ``exponential``:  value = initial * exp(rate * cycles)
    * ``piecewise``:    value = initial + interpolated offset through ``breakpoints``
    * ``fitted``:       like ``linear`` or ``exponential``, with parameters from ``fit``

    ``initial`` is the value of the manufactured variant; the mechanism only adds the change.
    """

    model_config = ConfigDict(extra="forbid")
    joint: str
    parameter: Literal["backlash", "friction", "stiffness", "radial_play", "efficiency",
                       "damping"]
    kind: Literal["linear", "exponential", "piecewise"]
    rate: float = 0.0
    rate_std: float | None = Field(default=None, ge=0, description="uncertainty of the rate")
    breakpoints: list[tuple[float, float]] = Field(default_factory=list)
    basis: Literal["measured", "fitted", "specified", "assumed"]
    assumptions: str = ""
    applicable: str = ""

    def change(self, initial: float, cycles: float, rate: float | None = None) -> float:
        r = self.rate if rate is None else rate
        if self.kind == "linear":
            return initial + r * cycles
        if self.kind == "exponential":
            return initial * float(np.exp(r * cycles))
        x = [b[0] for b in self.breakpoints]
        y = [b[1] for b in self.breakpoints]
        return initial + float(np.interp(cycles, x, y)) if x else initial


def fit_progression(cycles: Arr, values: Arr, kind: Literal["linear", "exponential"]
                    ) -> dict[str, Any]:
    """Fit a progression to measured (cycles, value) pairs; returns parameters and errors."""
    cycles = np.asarray(cycles, dtype=float)
    values = np.asarray(values, dtype=float)
    if len(cycles) < 4:
        raise ValueError("at least four measurements are needed to fit a progression")
    if kind == "linear":
        def f(n: Arr, initial: float, rate: float) -> Arr:
            return initial + rate * n
        p0 = [values[0], (values[-1] - values[0]) / max(cycles[-1] - cycles[0], 1e-12)]
    else:
        if np.any(values <= 0):
            raise ValueError("an exponential progression needs positive values")

        def f(n: Arr, initial: float, rate: float) -> Arr:
            return initial * np.exp(rate * n)
        p0 = [values[0], np.log(values[-1] / values[0]) / max(cycles[-1] - cycles[0], 1e-12)]
    popt, pcov = curve_fit(f, cycles, values, p0=p0)
    res = values - f(cycles, *popt)
    se = np.sqrt(np.diag(pcov))
    return {"kind": kind, "initial": float(popt[0]), "rate": float(popt[1]),
            "initial_std_error": float(se[0]), "rate_std_error": float(se[1]),
            "rms_residual": float(np.sqrt(np.mean(res**2))), "points": int(len(cycles)),
            "range_cycles": [float(cycles.min()), float(cycles.max())],
            "note": "valid inside the measured cycle range; beyond it this is extrapolation"}


def _aged(model: MechanicalModel, values: dict[str, float], mechanisms: list[Mechanism],
          cycles: float, shift: float) -> Any:
    variant = model.variant(values)
    for m in mechanisms:
        if m.joint not in variant.joints:
            raise KeyError(f"degradation mechanism targets joint {m.joint!r} with no drive")
        jv = variant.joints[m.joint]
        rate = m.rate + shift * (m.rate_std or 0.0)
        new = m.change(getattr(jv, m.parameter), cycles, rate)
        if m.parameter == "efficiency":
            new = float(np.clip(new, 1e-3, 1.0))
        elif m.parameter == "stiffness":
            new = max(new, 1e-6)
        else:
            new = max(new, 0.0)
        variant.joints[m.joint] = with_parameters(jv, {m.parameter: new})
    return variant


def lifetime_experiment(
    model: MechanicalModel, mechanisms: list[Mechanism], cycles: list[float],
    constraints: list[Constraint], task: Task | None = None,
    pose: dict[str, float] | None = None, payload_mass: float = 0.0,
    values: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Evaluate performance at each usage interval.

    Give ``task`` for Level 2 dynamics at every interval, or ``pose`` for the Level 1
    quasi-static model. Where a mechanism has ``rate_std``, the experiment is repeated at
    rate -/+ 1.96 standard deviations to give a band.
    """
    if (task is None) == (pose is None):
        raise ValueError("give exactly one of task (Level 2) or pose (Level 1)")
    if sorted(cycles) != list(cycles) or len(cycles) < 2:
        raise ValueError("cycles must be an increasing list of at least two values")
    values = values or {}
    banded = any(m.rate_std for m in mechanisms)

    def evaluate(n: float, shift: float) -> dict[str, Any] | None:
        variant = _aged(model, values, mechanisms, n, shift)
        if task is not None:
            res = model.engine.run(variant, task)
            if not res.valid:
                return None
            metrics = res.metrics
        else:
            metrics = static_pose(model, variant, pose or {}, payload_mass)["metrics"]
        state = {m.parameter if len({x.joint for x in mechanisms}) == 1
                 else f"{m.joint}.{m.parameter}": getattr(variant.joints[m.joint], m.parameter)
                 for m in mechanisms}
        return {"metrics": metrics, "state": state}

    series: list[dict[str, Any]] = []
    for n in cycles:
        centre = evaluate(n, 0.0)
        if centre is None:
            series.append({"cycles": n, "valid": False})
            continue
        entry: dict[str, Any] = {"cycles": n, "valid": True, **centre, "constraints": {}}
        if banded:
            lo, hi = evaluate(n, -1.96), evaluate(n, 1.96)
            if lo and hi:
                entry["band"] = {k: sorted([lo["metrics"][k], hi["metrics"][k]])
                                 for k in centre["metrics"]}
        for c in constraints:
            if c.metric not in centre["metrics"]:
                raise KeyError(f"constraint {c.name!r}: metric {c.metric!r} is not produced")
            ok, margin = c.check(centre["metrics"][c.metric])
            entry["constraints"][c.name] = {"value": centre["metrics"][c.metric],
                                            "passed": ok, "margin": margin}
        series.append(entry)

    crossings = {}
    for c in constraints:
        pts = [(s["cycles"], s["constraints"][c.name]["margin"]) for s in series if s["valid"]]
        cross = None
        if pts and pts[0][1] < 0:
            cross = {"cycles": pts[0][0], "note": "already violated at the first interval"}
        for (n0, m0), (n1, m1) in zip(pts, pts[1:], strict=False):
            if m0 >= 0 > m1:
                cross = {"cycles": float(n0 + (n1 - n0) * m0 / (m0 - m1)),
                         "between": [n0, n1],
                         "note": "linear interpolation between evaluated intervals"}
                break
        crossings[c.name] = cross or {"cycles": None,
                                      "note": f"not crossed within {cycles[-1]:g} cycles"}
    return {
        "label": "MODEL-BASED PROJECTION, not a service-life prediction",
        "level": L2 if task is not None else L1,
        "mechanisms": [m.model_dump() for m in mechanisms],
        "series": series, "threshold_crossings": crossings,
        "constraints": [c.model_dump() for c in constraints],
        "band": "rate -/+ 1.96 standard deviations" if banded else None,
        "assumptions": [
            "each parameter follows the stated progression independently of the others",
            "usage is counted in cycles only; load, speed, temperature and lubrication "
            "history are not modelled",
            *[f"{m.joint}.{m.parameter}: {m.kind}, basis {m.basis}"
              + (f" - {m.assumptions}" if m.assumptions else "") for m in mechanisms]],
    }


def compare_maintenance(result: dict[str, Any], constraint: str, inspect_every: float
                        ) -> dict[str, Any]:
    """When the projected crossing falls relative to an inspection interval."""
    cross = result["threshold_crossings"][constraint]["cycles"]
    if cross is None:
        return {"constraint": constraint, "crossing": None,
                "statement": "the requirement is not projected to be crossed in the range"}
    last_before = float(np.floor(cross / inspect_every) * inspect_every)
    return {"constraint": constraint, "crossing": cross, "inspect_every": inspect_every,
            "last_inspection_before_crossing": last_before,
            "cycles_between": cross - last_before,
            "statement": f"projected crossing at {cross:.0f} cycles; with inspection every "
                         f"{inspect_every:.0f} cycles the last inspection before it is at "
                         f"{last_before:.0f}"}
