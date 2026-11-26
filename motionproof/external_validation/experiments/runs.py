"""Validation experiments. Each follows its pre-registered protocol in ``protocols.py``.

Every function returns a result dictionary with the status (PASS, FAIL, NOT RUN,
INCOMPATIBLE DATA, INSUFFICIENT DATA), the exact identification and validation trial IDs,
fitted parameters with identifiability information, metrics on both sets, plot series, the
transformations applied and model-trust evidence records. Validation data never enter a fit:
models are fitted by functions that receive identification trials only.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np
from scipy.optimize import least_squares
from scipy.signal import savgol_filter

from motionproof.external_validation.adapters import ADAPTERS
from motionproof.external_validation.adapters.kuka_kr300 import KukaKR300
from motionproof.external_validation.experiments.protocols import PROTOCOLS
from motionproof.external_validation.metrics.errors import (
    by_group,
    errors,
    residual_histogram,
    thin,
)
from motionproof.external_validation.provenance.store import evidence
from motionproof.external_validation.schemas.trial import SchemaError, Signal, Trial, align

EPS_COULOMB = 0.02  # rad/s, smoothing of sign(dq) in the Coulomb term (fixed by protocol)


class LeakageError(RuntimeError):
    pass


def check_disjoint(ident: list[str], valid: list[str]) -> None:
    overlap = set(ident) & set(valid)
    if overlap:
        raise LeakageError(f"trials in both identification and validation: {sorted(overlap)}")


def linear_fit(X: np.ndarray, y: np.ndarray,  # noqa: N803 (matrix notation)
               names: list[str]) -> dict[str, Any]:
    """Least squares with identifiability diagnostics.

    Standard errors assume independent residuals; time-series residuals are correlated, so
    they are optimistic and reported as such.
    """
    scale = np.where(np.std(X, axis=0) > 0, np.std(X, axis=0), 1.0)
    Xs = X / scale
    beta_s, *_ = np.linalg.lstsq(Xs, y, rcond=None)
    beta = beta_s / scale
    r = y - X @ beta
    dof = max(len(y) - len(beta), 1)
    s2 = float(r @ r / dof)
    cov = s2 * np.linalg.pinv(X.T @ X)
    se = np.sqrt(np.clip(np.diag(cov), 0, None))
    d = np.sqrt(np.clip(np.diag(cov), 1e-300, None))
    corr = cov / np.outer(d, d)
    high = [(names[i], names[j], float(corr[i, j])) for i in range(len(names))
            for j in range(i + 1, len(names)) if abs(corr[i, j]) > 0.95]
    return {"parameters": {n: float(b) for n, b in zip(names, beta, strict=True)},
            "standard_errors": {n: float(s) for n, s in zip(names, se, strict=True)},
            "condition_number_scaled": float(np.linalg.cond(Xs)),
            "highly_correlated_pairs": high,
            "note": "standard errors assume independent residuals and are optimistic for "
                    "time series", "beta": beta}


def _trials(dataset: str, root: Path, rels: list[str]) -> list[Trial]:
    a = ADAPTERS[dataset]
    return [a.load(root, r) for r in rels]


def _status(ok: bool) -> str:
    return "PASS" if ok else "FAIL"


def _base(pid: str) -> dict[str, Any]:
    p = PROTOCOLS[pid]
    return {"protocol": pid, "benchmark": p.benchmark, "dataset": p.dataset, "title": p.title,
            "system": p.system, "quantity": p.quantity, "baseline": p.baseline,
            "model": p.model, "acceptance": p.acceptance, "reproduce": p.reproduce,
            "split": {"identification": p.identification, "validation": p.validation,
                      "unused": p.unused},
            "scope": "external system; says nothing about the MotionProof reference "
                     "gearbox or user hardware"}


def _not_imported(pid: str, what: str) -> dict[str, Any]:
    out = _base(pid)
    out |= {"status": "NOT RUN", "reason": f"dataset not imported ({what}); run "
            f"'motionproof external import {PROTOCOLS[pid].dataset}'"}
    return out


# ---- X1 transmission error ----------------------------------------------------------------

def _te_orders(trials: list[Trial], n_orders: int = 30, kmax: int = 4000,
               step: float = 1e-4, min_periods: float = 0.0) -> list[int]:
    spec = np.zeros(kmax + 1)
    for tr in trials:
        q, te = tr.signals["q_set"].values, tr.signals["theta_TE"].values
        order = np.argsort(q)
        q, te = q[order], te[order]
        grid = np.arange(q[0], q[-1], step)
        if len(grid) < 64:
            continue
        g = np.interp(grid, q, te) - np.mean(te)
        span = grid[-1] - grid[0]
        f = np.abs(np.fft.rfft(g * np.hanning(len(g))))
        k = np.fft.rfftfreq(len(g), d=step) * 2 * math.pi  # cycles per joint revolution
        spec += np.interp(np.arange(kmax + 1), k, f) * (span > 0)
    spec[0] = 0
    if min_periods > 0:
        span = min(float(np.ptp(t.signals["q_set"].values)) for t in trials)
        spec[: int(math.ceil(min_periods * 2 * math.pi / span))] = 0
    return sorted(int(i) for i in np.argsort(spec)[::-1][:n_orders])


def _te_design(trials: list[Trial], orders: list[int], windup: bool = False
               ) -> tuple[np.ndarray, np.ndarray, np.ndarray, list[str]]:
    rows, ys, labels = [], [], []
    for tr in trials:
        q = tr.signals["q_set"].values
        v = float(tr.conditions["q_set_dot_rad_s"])
        cols = [np.ones_like(q), np.sign(v) * np.ones_like(q)]
        if windup:
            cols.append(np.full_like(q, v))  # twist of the gearbox under viscous friction
        for k in orders:
            cols += [np.sin(k * q), np.cos(k * q)]
        rows.append(np.column_stack(cols))
        ys.append(tr.signals["theta_TE"].values)
        labels += [tr.conditions["q_set_dot_rad_s"]] * len(q)
    names = ["c0", "b_half"] + (["w_windup"] if windup else []) + [
        f"{t}{k}" for k in orders for t in ("a", "c")]
    return np.vstack(rows), np.concatenate(ys), np.asarray(labels), names


def speed_holdout(rels: list[str]) -> tuple[list[str], list[str]]:
    """Split recordings by velocity-setpoint rank within each sign: even rank to
    identification, odd rank to validation. Whole files only."""
    ident, valid = [], []
    for sign in (-1, 1):
        mine = [r for r in rels if np.sign(float(r.split("q_set_dot=")[1].removesuffix(
            ".csv"))) == sign]
        mine.sort(key=lambda r: abs(float(r.split("q_set_dot=")[1].removesuffix(".csv"))))
        ident += mine[0::2]
        valid += mine[1::2]
    return sorted(ident), sorted(valid)


def validate_transmission_error(root: Path, pid: str = "transmission-error",
                                min_periods: float = 0.0, split: str = "published",
                                windup: bool = False,
                                axis_names: tuple[str, ...] = ("axis_2", "axis_3")
                                ) -> dict[str, Any]:
    out = _base(pid)
    a = ADAPTERS["stuttgart-te"]
    have = a.available(root)
    if not any(r.startswith(f"identification/{ax}/") for r in have for ax in axis_names):
        return _not_imported(pid, "stuttgart-te " + ", ".join(axis_names))
    axes: dict[str, Any] = {}
    ok_all = True
    ev = []
    for axis in axis_names:
        ident_rel = sorted(r for r in have if r.startswith(f"identification/{axis}/"))
        valid_rel = sorted(r for r in have if r.startswith(f"validation/{axis}/"))
        if split == "speed-holdout":
            ident_rel, valid_rel = speed_holdout(ident_rel)
        if not ident_rel or not valid_rel:
            axes[axis] = {"status": "INSUFFICIENT DATA", "reason": "files missing"}
            ok_all = False
            continue
        ident, valid = _trials("stuttgart-te", root, ident_rel), _trials("stuttgart-te", root,
                                                                         valid_rel)
        check_disjoint([t.trial_id for t in ident], [t.trial_id for t in valid])
        orders = _te_orders(ident, min_periods=min_periods)  # identification spectrum only
        Xi, yi, li, names = _te_design(ident, orders, windup)
        fit = linear_fit(Xi, yi, names)
        Xv, yv, lv, _ = _te_design(valid, orders, windup)
        beta = fit.pop("beta")
        base_i, base_v = np.full_like(yi, yi.mean()), np.full_like(yv, yi.mean())
        m_i, m_v = Xi @ beta, Xv @ beta
        e = {"identification": {"model": errors(yi, m_i), "baseline": errors(yi, base_i)},
             "validation": {"model": errors(yv, m_v), "baseline": errors(yv, base_v)}}
        rv, rb, ri = (e["validation"]["model"]["rmse"], e["validation"]["baseline"]["rmse"],
                      e["identification"]["model"]["rmse"])
        ok = rv <= 0.5 * rb and rv <= 1.5 * ri
        ok_all &= ok
        # plot: first validation trial, measured vs predicted along q
        tr = valid[len(valid) // 2]
        Xp, yp, _, _ = _te_design([tr], orders, windup)
        qx = tr.signals["q_set"].values
        axes[axis] = {
            "status": _status(ok), "orders": orders,
            "identification_trials": [t.trial_id for t in ident],
            "validation_trials": [t.trial_id for t in valid],
            "fit": {"parameters": {k: fit["parameters"][k] for k in ("c0", "b_half", "w_windup")
                                   if k in fit["parameters"]},
                    "harmonics": len(orders),
                    "condition_number_scaled": fit["condition_number_scaled"],
                    "highly_correlated_pairs": fit["highly_correlated_pairs"]},
            "metrics": e, "rmse_ratio_model_to_baseline": rv / rb,
            "rmse_ratio_validation_to_identification": rv / ri,
            "validation_by_speed": by_group(yv, m_v, list(lv)),
            "residual_histogram": residual_histogram(yv, m_v),
            "plot": dict(zip(("x", "measured", "predicted"),
                             thin(qx, yp, Xp @ beta), strict=True))
                    | {"x_label": "q_set (rad)", "y_label": "theta_TE (rad)",
                       "trial": tr.trial_id},
        }
        ev += [evidence("EXTERNAL_CALIBRATION", "stuttgart-te", t.trial_id, "identification",
                        "fitted TE harmonics and dead-band offset") for t in ident]
        ev += [evidence("EXTERNAL_VALIDATION", "stuttgart-te", t.trial_id, "validation",
                        "holdout comparison of predicted and measured theta_TE") for t in valid]
    prefixes = tuple(f"identification/{ax}" for ax in axis_names) + (
        tuple(f"validation/{ax}" for ax in axis_names) if split == "published" else ())
    out["files_used"] = sorted(r for r in have if r.startswith(prefixes))
    if windup:
        out["details"] = [
            "Blind: protocol committed before any axis 1 file was downloaded; the model form "
            "was chosen on axes 2 and 3 only." if axis_names == ("axis_1",) else
            "Not blind: written after transmission-error-v3 (axis 3 FAIL); the windup term "
            "was chosen from the v3 residuals, which fall linearly with the velocity setpoint.",
            "Fitted windup w (rad per rad/s): " + "; ".join(
                f"{k} {v['fit']['parameters']['w_windup']:.2e}" for k, v in axes.items()
                if "fit" in v) + "."]
    out |= {"status": _status(ok_all) if all("metrics" in v for v in axes.values())
            else "INSUFFICIENT DATA", "axes": axes, "evidence": ev,
            "transformations": ["none: theta_TE compared at the published samples",
                                "orders chosen from identification spectrum only (uniform q "
                                "resampling, step 1e-4 rad, Hann window)"]}
    return out


# ---- X2 H1 elbow friction -----------------------------------------------------------------

def _h1_series(tr: Trial, dt: float = 0.002) -> dict[str, np.ndarray]:
    tr.require("elbow/q", "elbow/dq", "elbow/tau")
    s = tr.signals
    lo = max(s[k].time_s[0] for k in ("elbow/q", "elbow/dq", "elbow/tau"))  # type: ignore[index]
    hi = min(s[k].time_s[-1] for k in ("elbow/q", "elbow/dq", "elbow/tau"))  # type: ignore[index]
    t = np.arange(lo, hi, dt)
    q, dq, tau = (align(t, s["elbow/q"]), align(t, s["elbow/dq"]), align(t, s["elbow/tau"]))
    ddq = savgol_filter(dq, 21, 3, deriv=1, delta=dt)
    trim = slice(25, -25)  # derivative edge effects
    return {"t": t[trim], "q": q[trim], "dq": dq[trim], "ddq": ddq[trim], "tau": tau[trim]}


def _joint_design(d: dict[str, np.ndarray], friction: bool,
                  coupled: bool = False) -> tuple[np.ndarray, list[str]]:
    cols = [d["ddq"], np.sin(d["q"]), np.cos(d["q"]), np.ones_like(d["q"])]
    names = ["J", "g1", "g2", "tau0"]
    if friction:
        cols += [d["dq"], np.tanh(d["dq"] / EPS_COULOMB)]
        names += ["c_viscous", "F_coulomb"]
    if "base" in d:  # extra baseline columns shared by every variant (e.g. payload terms)
        cols += list(d["base"].T)
        names += [f"b{i}" for i in range(d["base"].shape[1])]
    if coupled and "gravity" in d:
        cols += list(d["gravity"].T)
        names += [f"gc{i}" for i in range(d["gravity"].shape[1])]
    return np.column_stack(cols), names


def _joint_validation(ident: list[dict[str, np.ndarray]], valid: list[dict[str, np.ndarray]],
                      labels_v: list[str], coupled: bool = False) -> dict[str, Any]:
    res: dict[str, Any] = {}
    yi = np.concatenate([d["tau"] for d in ident])
    yv = np.concatenate([d["tau"] for d in valid])
    variants = [("baseline", False, False), ("model", True, coupled)]
    if coupled:  # diagnostic: the same coupled gravity without friction
        variants.append(("coupled_rigid", False, True))
    for name, fr, cp in variants:
        Xi = np.vstack([_joint_design(d, fr, cp)[0] for d in ident])
        Xv = np.vstack([_joint_design(d, fr, cp)[0] for d in valid])
        fit = linear_fit(Xi, yi, _joint_design(ident[0], fr, cp)[1])
        beta = fit.pop("beta")
        res[name] = {"fit": fit, "identification": errors(yi, Xi @ beta),
                     "validation": errors(yv, Xv @ beta), "pred_v": Xv @ beta}
    res["labels_v"] = np.repeat(labels_v, [len(d["tau"]) for d in valid])
    res["yv"] = yv
    return res


def validate_h1_friction(root: Path) -> dict[str, Any]:
    out = _base("h1-friction")
    a = ADAPTERS["anchor-lab"]
    have = [r for r in a.available(root) if r.startswith("h1_elbow_teststand/")]
    if not have:
        return _not_imported("h1-friction", "anchor-lab h1-teststand")
    trials = _trials("anchor-lab", root, sorted(have))
    ident = [t for t in trials if t.conditions.get("position") in (8, 9, 10)]
    valid = [t for t in trials if t.conditions.get("position") == 11]
    if len(ident) < 3 or not valid:
        out |= {"status": "INSUFFICIENT DATA", "reason": f"{len(ident)} identification, "
                f"{len(valid)} validation trials"}
        return out
    check_disjoint([t.trial_id for t in ident], [t.trial_id for t in valid])
    di, dv = [_h1_series(t) for t in ident], [_h1_series(t) for t in valid]
    labels = [f"{t.conditions['frequency_hz']} Hz {t.conditions['amplitude']}" for t in valid]
    r = _joint_validation(di, dv, labels)
    m, b = r["model"]["validation"], r["baseline"]["validation"]
    ok = m["rmse"] <= 0.8 * b["rmse"] and (m["nrmse"] or 9) <= 0.35
    k = len(dv[0]["t"])
    out |= {
        "status": _status(ok), "files_used": [t.source_file for t in ident + valid],
        "identification_trials": [t.trial_id for t in ident],
        "validation_trials": [t.trial_id for t in valid],
        "fit": {"model": r["model"]["fit"], "baseline": r["baseline"]["fit"]},
        "metrics": {"model": {"identification": r["model"]["identification"],
                              "validation": m},
                    "baseline": {"identification": r["baseline"]["identification"],
                                 "validation": b}},
        "rmse_ratio_model_to_baseline": m["rmse"] / b["rmse"],
        "validation_by_condition": by_group(r["yv"], r["model"]["pred_v"],
                                            list(r["labels_v"])),
        "residual_histogram": residual_histogram(r["yv"], r["model"]["pred_v"]),
        "plot": dict(zip(("x", "measured", "predicted", "baseline"),
                         thin(dv[0]["t"], r["yv"][:k], r["model"]["pred_v"][:k],
                              r["baseline"]["pred_v"][:k]), strict=True))
                | {"x_label": "time (s)", "y_label": "elbow_tau (N*m)",
                   "trial": valid[0].trial_id},
        "transformations": ["q, dq, tau linearly interpolated onto a common uniform 2 ms "
                            "grid inside the shared time span (no extrapolation)",
                            "ddq: Savitzky-Golay derivative of dq (21 samples, cubic)",
                            "25 samples trimmed at each end (derivative edge effects)"],
        "evidence": [evidence("EXTERNAL_CALIBRATION", "anchor-lab", t.trial_id,
                              "identification", "friction and inertia fit") for t in ident]
                    + [evidence("EXTERNAL_VALIDATION", "anchor-lab", t.trial_id, "validation",
                                "holdout torque prediction") for t in valid],
    }
    return out


# ---- X3 SO-101 servo tracking -------------------------------------------------------------

def _servo_sim(p: np.ndarray, t: np.ndarray, t_cmd: np.ndarray, cmd: np.ndarray,
               q0: float, dt: float = 0.001) -> np.ndarray:
    wn, zeta, vmax, b, off = p
    tt = np.arange(t[0], t[-1] + dt, dt)
    idx = np.clip(np.searchsorted(t_cmd, tt, side="right") - 1, 0, len(cmd) - 1)
    u = (cmd[idx] + off).tolist()  # zero-order hold of the recorded command
    # plain Python floats in the loop: numpy scalar calls per step dominated the run time;
    # the arithmetic and its order are unchanged, so results are identical
    kp, kd, vm, half, h = float(wn * wn), float(2 * zeta * wn), float(vmax), float(b / 2), dt
    x, v, q = float(q0), 0.0, float(q0)
    out = [0.0] * len(u)
    for i, ui in enumerate(u):
        acc = kp * (ui - x) - kd * v
        v = min(max(v + acc * h, -vm), vm)
        x += v * h
        if x - q > half:            # dead band between servo output and joint
            q = x - half
        elif x - q < -half:
            q = x + half
        out[i] = q
    return np.asarray(np.interp(t, tt, np.asarray(out)), dtype=float)


def parallel_map(fn: Callable[..., Any], items: list[tuple[Any, ...]]) -> list[Any]:
    """``[fn(*a) for a in items]`` in worker processes (``default_workers()``), or serially
    when there is one item or this already is a worker process. Order is kept."""
    import multiprocessing as mp
    from concurrent.futures import ProcessPoolExecutor

    from motionproof.experiments.runner import default_workers

    n = min(len(items), default_workers())
    if n <= 1 or mp.parent_process() is not None:
        return [fn(*a) for a in items]
    with ProcessPoolExecutor(n) as ex:
        return list(ex.map(fn, *zip(*items, strict=True)))


def _so101_series(tr: Trial, joint: str = "elbow") -> dict[str, np.ndarray]:
    tr.require(f"{joint}/q", f"{joint}/q_cmd")
    q, c = tr.signals[f"{joint}/q"], tr.signals[f"{joint}/q_cmd"]
    assert q.time_s is not None and c.time_s is not None
    sel = (q.time_s >= c.time_s[0]) & (q.time_s <= c.time_s[-1])
    return {"t": q.time_s[sel], "q": q.values[sel], "t_cmd": c.time_s, "cmd": c.values}


def validate_so101_tracking(root: Path, pid: str = "so101-tracking", joint: str = "elbow",
                            ident_trial: str = "single-joint-elbow") -> dict[str, Any]:
    out = _base(pid)
    a = ADAPTERS["anchor-lab"]
    have = [r for r in a.available(root) if r.startswith("so101_arm_50motion/")]
    ident_rel = [r for r in have if r.endswith(f"train-{ident_trial}.parquet")]
    held = [r for r in have if "-heldout-" in r]
    if not ident_rel or not held:
        return _not_imported(pid, f"anchor-lab so101 ({ident_trial})")
    ident = _trials("anchor-lab", root, ident_rel)[0]
    valid: list[tuple[Trial, float]] = []
    unused: list[tuple[Trial, float]] = []
    for tr in _trials("anchor-lab", root, sorted(held)):
        c = tr.signals.get(f"{joint}/q_cmd")
        span = 0.0 if c is None else float(np.ptp(c.values))
        (valid if span >= 0.1 else unused).append((tr, span))
    if not valid:
        out |= {"status": "INSUFFICIENT DATA",
                "reason": f"no heldout trial excites the {joint} joint"}
        return out
    check_disjoint([ident.trial_id], [t.trial_id for t, _ in valid])
    di = _so101_series(ident, joint)

    def resid(p: np.ndarray) -> np.ndarray:
        return np.asarray(_servo_sim(p, di["t"], di["t_cmd"], di["cmd"], di["q"][0]) - di["q"])

    fit = least_squares(resid, x0=[30.0, 0.8, 5.0, 0.01, 0.0],
                        bounds=([1, 0.05, 0.1, 0.0, -0.2], [300, 3, 50, 0.2, 0.2]))
    J = fit.jac
    cov = np.linalg.pinv(J.T @ J) * float(fit.fun @ fit.fun) / max(len(fit.fun) - 5, 1)
    names = ["wn", "zeta", "vmax", "deadband", "offset"]
    off_b = float(np.mean(di["q"] - np.interp(di["t"], di["t_cmd"], di["cmd"])))

    def baseline(d: dict[str, np.ndarray]) -> np.ndarray:
        idx = np.clip(np.searchsorted(d["t_cmd"], d["t"], side="right") - 1, 0,
                      len(d["cmd"]) - 1)
        return np.asarray(d["cmd"][idx] + off_b, dtype=float)

    obs, pm, pb, lab = [], [], [], []
    per: dict[str, Any] = {}
    first = None
    for tr, span in valid:
        d = _so101_series(tr, joint)
        m = _servo_sim(fit.x, d["t"], d["t_cmd"], d["cmd"], d["q"][0])
        bl = baseline(d)
        per[tr.trial_id] = {"command_span_rad": span, "model": errors(d["q"], m)["rmse"],
                            "baseline": errors(d["q"], bl)["rmse"]}
        obs.append(d["q"])
        pm.append(m)
        pb.append(bl)
        lab += [tr.trial_id] * len(m)
        first = first or (d, m, bl, tr.trial_id)
    yo, ym, yb = np.concatenate(obs), np.concatenate(pm), np.concatenate(pb)
    em, eb = errors(yo, ym), errors(yo, yb)
    ok = em["rmse"] <= 0.6 * eb["rmse"]
    assert first is not None
    d, m, bl, tid = first
    out |= {
        "status": _status(ok),
        "files_used": [ident.source_file] + [t.source_file for t, _ in valid + unused],
        "identification_trials": [ident.trial_id],
        "validation_trials": [t.trial_id for t, _ in valid],
        "unused_trials": {t.trial_id: f"{joint} command span {s:.3f} rad < 0.1 rad"
                          for t, s in unused},
        "fit": {"parameters": dict(zip(names, map(float, fit.x), strict=True)),
                "standard_errors": dict(zip(names, map(float, np.sqrt(np.clip(
                    np.diag(cov), 0, None))), strict=True)),
                "at_bound": [n for n, am in zip(names, fit.active_mask, strict=True)
                             if am != 0],
                "not_identifiable": [n for n, col in zip(names, np.abs(J).sum(axis=0),
                                                         strict=True) if col == 0],
                "identification_rmse": float(np.sqrt(np.mean(fit.fun ** 2)))},
        "metrics": {"model": {"validation": em}, "baseline": {"validation": eb}},
        "rmse_ratio_model_to_baseline": em["rmse"] / eb["rmse"],
        "validation_by_trial": per,
        "residual_histogram": residual_histogram(yo, ym),
        "plot": dict(zip(("x", "measured", "predicted", "baseline"),
                         thin(d["t"], d["q"], m, bl), strict=True))
                | {"x_label": "time (s)", "y_label": f"{joint} actual_q (rad)", "trial": tid},
        "transformations": ["command held constant between its samples (zero-order hold)",
                            "simulation at 1 ms, linearly interpolated to the actual_q "
                            "sample instants", "only samples inside the command time span"],
        "evidence": [evidence("EXTERNAL_CALIBRATION", "anchor-lab", ident.trial_id,
                              "identification", "servo response and dead band fit")]
                    + [evidence("EXTERNAL_VALIDATION", "anchor-lab", t.trial_id, "validation",
                                "simulated response to the recorded command") for t, _ in valid],
    }
    return out


SO101_BLIND_JOINTS = {"rotation": "single-joint-rotation",
                      "wrist_pitch": "single-joint-wrist-pitch",
                      "wrist_roll": "single-joint-wrist-roll"}


def validate_so101_joints(root: Path) -> dict[str, Any]:
    """X10: the X3 servo model, unchanged, on the SO-101 joints that have their own
    single-joint identification trial."""
    pid = "so101-joints"
    out = _base(pid)
    joints = dict(zip(SO101_BLIND_JOINTS, parallel_map(
        validate_so101_tracking,
        [(root, pid, j, trial) for j, trial in SO101_BLIND_JOINTS.items()]), strict=True))
    if all(r["status"] == "NOT RUN" for r in joints.values()):
        return _not_imported(pid, "anchor-lab so101 single-joint trials")
    evaluated = {j: r for j, r in joints.items() if "metrics" in r}
    ok = bool(evaluated) and all(r["status"] == "PASS" for r in evaluated.values())
    keep = ("status", "reason", "metrics", "rmse_ratio_model_to_baseline", "fit",
            "identification_trials", "validation_trials", "unused_trials",
            "validation_by_trial")
    out |= {"status": _status(ok) if evaluated else "INSUFFICIENT DATA",
            "joints": {j: {k: r[k] for k in keep if k in r} for j, r in joints.items()},
            "files_used": sorted({f for r in joints.values() for f in r.get("files_used", [])}),
            "identification_trials": [t for r in evaluated.values()
                                      for t in r["identification_trials"]],
            "validation_trials": sorted({t for r in evaluated.values()
                                         for t in r["validation_trials"]}),
            "details": ["Blind: protocol committed before the single-joint identification "
                        "trials of these joints were downloaded and before any fit to them; "
                        "the model is X3's, unchanged."],
            "evidence": [e for r in evaluated.values() for e in r.get("evidence", [])]}
    return out


# ---- X4 KUKA inverse dynamics -------------------------------------------------------------

def _kuka_gravity(s: dict[str, Signal], j: int) -> np.ndarray | None:
    """Multibody gravity columns of axis j (kuka-inverse-v2), or None for axes without."""
    q = {k: s[f"A{k}/q"].values for k in (2, 3, 4, 5)}
    q23 = q[2] + q[3]
    if j in (2, 3):
        return np.column_stack([np.sin(q23), np.cos(q23)])
    if j == 5:
        arms = (np.sin(q23) * np.cos(q[4]), np.cos(q23) * np.cos(q[4]), np.sin(q23),
                np.cos(q23))
        return np.column_stack([f(q[5]) * a for a in arms for f in (np.sin, np.cos)])
    return None


def validate_kuka_inverse(root: Path, pid: str = "kuka-inverse",
                          coupled: bool = False) -> dict[str, Any]:
    out = _base(pid)
    a = ADAPTERS["kuka-kr300"]
    assert isinstance(a, KukaKR300)
    if not a.available(root):
        return _not_imported(pid, "kuka-kr300")
    tr_train, tr_test = a.load(root, "train"), a.load(root, "test")
    axes: dict[str, Any] = {}
    ok_all = True
    for j in range(1, 7):
        ax = f"A{j}"

        def series(tr: Trial, ax: str = ax) -> dict[str, np.ndarray]:
            s = tr.signals
            d = {"q": s[f"{ax}/q"].values, "dq": s[f"{ax}/dq"].values,
                 "ddq": s[f"{ax}/ddq"].values, "tau": s[f"{ax}/tau"].values,
                 "t": s[f"{ax}/q"].time_s}
            g = _kuka_gravity(s, int(ax[1])) if coupled else None
            if g is not None:
                d["gravity"] = g
            return d  # type: ignore[return-value]

        r = _joint_validation([series(tr_train)], [series(tr_test)], ["test"], coupled)
        m, b = r["model"]["validation"], r["baseline"]["validation"]
        ok = m["rmse"] <= 0.8 * b["rmse"]
        ok_all &= ok
        axes[ax] = {"status": _status(ok), "metrics": {
            "model": {"identification": r["model"]["identification"], "validation": m},
            "baseline": {"identification": r["baseline"]["identification"], "validation": b}},
            "rmse_ratio_model_to_baseline": m["rmse"] / b["rmse"],
            **({"friction_only_ratio": m["rmse"] / r["coupled_rigid"]["validation"]["rmse"]}
               if coupled else {}),
            "fit": {"model": r["model"]["fit"]},
            "plot": dict(zip(("x", "measured", "predicted", "baseline"),
                             thin(series(tr_test)["t"], r["yv"], r["model"]["pred_v"],
                                  r["baseline"]["pred_v"]), strict=True))
                    | {"x_label": "time (s)", "y_label": f"{ax} motor torque (N*m)",
                       "trial": "test"}}
    if coupled:
        out["details"] = [
            "Not blind: written after kuka-inverse (v1) failed on A2, A3 and A5; two A5 "
            "gravity forms were tried against the test set.",
            "Friction-only contribution, test RMSE of the model / the same coupled gravity "
            "without friction: " + "; ".join(
                f"{k} {v['friction_only_ratio']:.2f}" for k, v in axes.items()) + "."]
    out |= {"status": _status(ok_all), "axes": axes, "files_used": a.available_files(root),
            "identification_trials": ["train"], "validation_trials": ["test"],
            "transformations": ["deg, deg/s, deg/s^2 converted to rad, rad/s, rad/s^2",
                                "benchmark's filtered, down-sampled data used unchanged"],
            "evidence": [evidence("EXTERNAL_CALIBRATION", "kuka-kr300", "train",
                                  "identification", "per-axis friction and inertia fit"),
                         evidence("EXTERNAL_VALIDATION", "kuka-kr300", "test", "validation",
                                  "per-axis torque prediction")]}
    return out


# ---- X5 NIST joint tracking, X6 NIST TCP --------------------------------------------------

def _nist_design(tr: Trial, j: int, accel: bool = False) -> tuple[np.ndarray, np.ndarray]:
    s = tr.signals
    e = s[f"J{j}/q_target"].values - s[f"J{j}/q"].values
    cols = [np.ones_like(e), s[f"J{j}/tau_target"].values,
            np.sign(s[f"J{j}/dq_target"].values), s[f"J{j}/dq_target"].values]
    if accel:  # second-order position loop: error also ~ target acceleration / wn^2
        cols.append(s[f"J{j}/ddq_target"].values)
    return np.column_stack(cols), e


def validate_nist_tracking(root: Path, pid: str = "nist-tracking",
                           accel: bool = False) -> dict[str, Any]:
    out = _base(pid)
    a = ADAPTERS["nist-ur5"]
    runs = [r for r in a.available(root) if r.endswith(".csv")]
    if not runs:
        return _not_imported(pid, "nist-ur5")
    trials = _trials("nist-ur5", root, sorted(runs))
    ident = [t for t in trials if t.conditions["repeat"] in (1, 2)]
    valid = [t for t in trials if t.conditions["repeat"] == 3]
    check_disjoint([t.trial_id for t in ident], [t.trial_id for t in valid])
    joints: dict[str, Any] = {}
    ok_all = True
    names = ["e0", "compliance_1_over_k", "deadband_half", "lag"] + (
        ["accel_lag"] if accel else [])
    for j in range(1, 7):
        Xi = np.vstack([_nist_design(t, j, accel)[0] for t in ident])
        yi = np.concatenate([_nist_design(t, j, accel)[1] for t in ident])
        fit = linear_fit(Xi, yi, names)
        beta = fit.pop("beta")
        Xv = [_nist_design(t, j, accel) for t in valid]
        yv = np.concatenate([e for _, e in Xv])
        pm = np.concatenate([X @ beta for X, _ in Xv])
        pb = np.full_like(yv, yi.mean())
        em, eb = errors(yv, pm), errors(yv, pb)
        ok = em["rmse"] <= 0.8 * eb["rmse"]
        ok_all &= ok
        lab_speed = np.concatenate([[t.conditions["speed"]] * len(e) for t, (_, e)
                                    in zip(valid, Xv, strict=True)])
        lab_load = np.concatenate([[f"{t.conditions['payload_lb']} lb"] * len(e) for t, (_, e)
                                   in zip(valid, Xv, strict=True)])
        temp = np.concatenate([t.signals[f"J{j}/temperature"].values for t in valid])
        from scipy.stats import spearmanr

        rho = spearmanr(np.abs(yv - pm), temp)
        joints[f"J{j}"] = {
            "status": _status(ok), "fit": fit,
            "metrics": {"model": {"validation": em}, "baseline": {"validation": eb}},
            "rmse_ratio_model_to_baseline": em["rmse"] / eb["rmse"],
            "validation_by_speed": by_group(yv, pm, list(lab_speed)),
            "validation_by_payload": by_group(yv, pm, list(lab_load)),
            "residual_vs_temperature_spearman": {"rho": float(rho.statistic),
                                                 "p_value": float(rho.pvalue),
                                                 "note": "association only, not causation"}}
    t0 = valid[0]
    X0, e0 = _nist_design(t0, 2, accel)
    if accel:
        out["details"] = [
            "Not blind: written after nist-tracking (v1) failed on J2 to J6; the "
            "acceleration term is the 1/wn^2 error of the second-order position loop used in "
            "X3, taken from the controller's recorded target acceleration."]
    b2 = np.asarray(list(joints["J2"]["fit"]["parameters"].values()))
    sig = t0.signals["J2/q"]
    assert sig.time_s is not None
    out |= {"status": _status(ok_all), "joints": joints, "files_used": sorted(runs),
            "identification_trials": [t.trial_id for t in ident],
            "validation_trials": [t.trial_id for t in valid],
            "plot": dict(zip(("x", "measured", "predicted"), thin(sig.time_s, e0, X0 @ b2),
                             strict=True))
                    | {"x_label": "time (s)", "y_label": "J2 position error (rad)",
                       "trial": t0.trial_id},
            "transformations": ["joint angles deg to rad (unit inferred from values)",
                                "error = target - actual at the same controller sample"],
            "limitations": ["controller-reported actual position, not an external "
                            "measurement of the joint output", "this is servo tracking "
                            "error during motion, not TCP accuracy"],
            "evidence": [evidence("EXTERNAL_CALIBRATION", "nist-ur5", t.trial_id,
                                  "identification", "deflection, dead band, lag fit")
                         for t in ident]
                        + [evidence("EXTERNAL_VALIDATION", "nist-ur5", t.trial_id,
                                    "validation", "holdout tracking-error prediction")
                           for t in valid]}
    return out


def _ur5_gravity(s: dict[str, Signal], j: int) -> np.ndarray | None:
    """Multibody gravity columns of UR5 joint j (nist-dynamics), before payload scaling."""
    q = {k: s[f"J{k}/q"].values for k in (2, 3, 4, 5)}
    q23, q234 = q[2] + q[3], q[2] + q[3] + q[4]
    if j in (2, 3):
        return np.column_stack([np.sin(q23), np.cos(q23), np.sin(q234), np.cos(q234)])
    if j == 4:
        base = [np.sin(q234), np.cos(q234)]
        return np.column_stack(base + [b * f(q[5]) for b in base for f in (np.cos, np.sin)])
    if j == 5:
        return np.column_stack([f(q[5]) * a for a in (np.sin(q234), np.cos(q234))
                                for f in (np.sin, np.cos)])
    return None


def validate_nist_dynamics(root: Path) -> dict[str, Any]:
    pid = "nist-dynamics"
    out = _base(pid)
    a = ADAPTERS["nist-ur5"]
    runs_ = [r for r in a.available(root) if r.endswith(".csv")]
    if not runs_:
        return _not_imported(pid, "nist-ur5")
    trials = _trials("nist-ur5", root, sorted(runs_))
    ident = [t for t in trials if t.conditions["repeat"] in (1, 2)]
    valid = [t for t in trials if t.conditions["repeat"] == 3]
    check_disjoint([t.trial_id for t in ident], [t.trial_id for t in valid])
    joints: dict[str, Any] = {}
    ok_all = True
    for j in range(1, 7):
        def series(tr: Trial, j: int = j) -> dict[str, np.ndarray]:
            s = tr.signals
            q = s[f"J{j}/q"].values
            m = float(tr.conditions["payload_kg"])
            d = {"q": q, "dq": s[f"J{j}/dq"].values, "ddq": s[f"J{j}/ddq_target"].values,
                 "tau": s[f"J{j}/current"].values, "t": s[f"J{j}/q"].time_s,
                 "base": np.column_stack([m * np.sin(q), m * np.cos(q)])}
            g = _ur5_gravity(s, j)
            if g is not None:
                d["gravity"] = np.column_stack([g, m * g])
            return d  # type: ignore[return-value]

        r = _joint_validation([series(t) for t in ident], [series(t) for t in valid],
                              [t.trial_id for t in valid], coupled=True)
        mv, bv = r["model"]["validation"], r["baseline"]["validation"]
        ok = mv["rmse"] <= 0.8 * bv["rmse"]
        ok_all &= ok
        joints[f"J{j}"] = {
            "status": _status(ok), "rmse_ratio_model_to_baseline": mv["rmse"] / bv["rmse"],
            "friction_only_ratio": mv["rmse"] / r["coupled_rigid"]["validation"]["rmse"],
            "metrics": {"model": {"identification": r["model"]["identification"],
                                  "validation": mv},
                        "baseline": {"identification": r["baseline"]["identification"],
                                     "validation": bv}},
            "fit": {"model": r["model"]["fit"]}}
    out |= {"status": _status(ok_all), "joints": joints, "files_used": sorted(runs_),
            "identification_trials": [t.trial_id for t in ident],
            "validation_trials": [t.trial_id for t in valid],
            "details": [
                "Blind: protocol committed before any model was fitted to the UR5 joint "
                "currents; the model idea comes from X4 (KUKA).",
                "Friction-only contribution, validation RMSE of the model / the same gravity "
                "without friction: " + "; ".join(
                    f"{k} {v['friction_only_ratio']:.2f}" for k, v in joints.items()) + "."],
            "transformations": ["joint angles deg to rad (unit inferred from values)",
                                "current compared in A; no torque constant applied"],
            "evidence": [evidence("EXTERNAL_CALIBRATION", "nist-ur5", t.trial_id,
                                  "identification", "current model fit") for t in ident]
                        + [evidence("EXTERNAL_VALIDATION", "nist-ur5", t.trial_id, "validation",
                                    "holdout current prediction") for t in valid]}
    return out


def validate_nist_tcp(root: Path) -> dict[str, Any]:
    out = _base("nist-tcp")
    out |= {"status": "INSUFFICIENT DATA",
            "reason": "the dataset publishes measured TCP deviation for 6 positions only, "
                      "without the run, condition or trajectory they belong to; a TCP "
                      "accuracy or degradation prediction cannot be compared with it"}
    return out


# ---- X7 COMPAct SSPG backlash (not blind) --------------------------------------------------


def _truncnorm(rng: np.random.Generator, mean: float, sd: float, lo: float, hi: float,
               n: int) -> np.ndarray:
    out = rng.normal(mean, sd, n)
    bad = (out < lo) | (out > hi)
    while bad.any():
        out[bad] = rng.normal(mean, sd, int(bad.sum()))
        bad = (out < lo) | (out > hi)
    return out


def predict_sspg_backlash(j_sp: float, j_pr: float, pin_dev: float, samples: int = 20000,
                          seed: int = 2026) -> dict[str, Any]:
    """Output backlash of the SSPG under the protocol's tolerance model (mm in, rad out)."""
    from types import SimpleNamespace

    from motionproof.core.schema import PlanetaryStage, StageInputs
    from motionproof.external_validation.adapters import compact_sspg as cs
    from motionproof.transmissions.gears import evaluate_stage

    pins = [f"pin{k}" for k in range(cs.PLANETS)]
    stage = PlanetaryStage(
        id="sspg", joint="output", order=1, sun_teeth=cs.SUN, planet_teeth=cs.PLANET,
        ring_teeth=cs.RING, planets=cs.PLANETS, module=cs.MODULE,
        pressure_angle=cs.PRESSURE_ANGLE, inputs=StageInputs(
            design_backlash_sun_planet="jsp", design_backlash_planet_ring="jpr",
            carrier_pin_radial=pins, planet_bearing_clearance="cb", sun_runout="run",
            sun_runout_phase="phase", ring_offset_x="rx", ring_offset_y="ry"))
    nominal = {"jsp": j_sp, "jpr": j_pr, "cb": 0.0, "run": 0.0, "phase": 0.0, "rx": 0.0,
               "ry": 0.0} | dict.fromkeys(pins, 0.0)
    # evaluate_stage reads each tolerance's nominal and unit; all lengths here are mm
    spec = SimpleNamespace(tolerance=lambda i: SimpleNamespace(
        nominal=nominal[i], unit="rad" if i == "phase" else "mm"))

    def backlash(values: dict[str, float]) -> float:
        return float(evaluate_stage(stage, spec, values).backlash_angle)  # type: ignore[arg-type]

    cad = backlash(nominal | dict.fromkeys(pins, pin_dev))
    rng = np.random.default_rng(seed)
    draw = {"jsp": _truncnorm(rng, j_sp, 0.04, j_sp - 0.10, j_sp + 0.10, samples),
            "jpr": _truncnorm(rng, j_pr, 0.04, j_pr - 0.10, j_pr + 0.10, samples),
            "cb": rng.uniform(0.02, 0.10, samples), "run": rng.uniform(0.0, 0.10, samples),
            "phase": rng.uniform(0.0, 2 * np.pi, samples),
            "rx": _truncnorm(rng, 0.0, 0.04, -0.10, 0.10, samples),
            "ry": _truncnorm(rng, 0.0, 0.04, -0.10, 0.10, samples)}
    for k in pins:
        draw[k] = pin_dev + _truncnorm(rng, 0.0, 0.04, -0.10, 0.10, samples)
    values = np.array([backlash({k: float(v[i]) for k, v in draw.items()})
                       for i in range(samples)])
    q05, q50, q95 = (float(x) for x in np.quantile(values, [0.05, 0.5, 0.95]))
    return {"cad_only": cad, "q05": q05, "median": q50, "q95": q95,
            "mean": float(values.mean()), "samples": samples, "seed": seed,
            "_values": values}


def validate_compact_backlash(root: Path) -> dict[str, Any]:
    from motionproof.external_validation.adapters import compact_sspg as cs

    pid = "compact-sspg-backlash"
    a = ADAPTERS["compact-sspg"]
    assert isinstance(a, cs.CompactSSPG)
    if len(a.available(root)) < len(cs.PARTS):
        return _not_imported(pid, "print files")
    out = _base(pid)
    m = cs.MODULE
    sun = cs.tooth_thickness(a.mesh(root, "sun"), 20.0, cs.SUN, m, internal=False)
    planet = cs.tooth_thickness(a.mesh(root, "planet"), 11.0, cs.PLANET, m, internal=False)
    ring = cs.tooth_thickness(a.mesh(root, "gearbox_casing"), 27.5, cs.RING, m, internal=True)
    pins = cs.pin_radius(a.mesh(root, "carrier"), 20.0, cs.PLANETS, m * (cs.SUN + cs.PLANET) / 2)
    pitch = math.pi * m
    j_sp = pitch - sun["tooth_thickness"] - planet["tooth_thickness"]
    j_pr = ring["space_width"] - planet["tooth_thickness"]
    pin_dev = pins["pin_radius"] - m * (cs.SUN + cs.PLANET) / 2
    pred = predict_sspg_backlash(j_sp, j_pr, pin_dev)
    measured = math.radians(cs.PUBLISHED_BACKLASH_DEG)
    inside = pred["q05"] <= measured <= pred["q95"]
    percentile = float((pred.pop("_values") < measured).mean() * 100)
    out |= {"status": _status(inside), "files_used": a.available(root),
            "headline": f"published {measured * 1e3:.1f} mrad; predicted 5 to 95 % "
                        f"{pred['q05'] * 1e3:.1f} to {pred['q95'] * 1e3:.1f} mrad "
                        f"(median {pred['median'] * 1e3:.1f}); print files alone "
                        f"{pred['cad_only'] * 1e3:.2f} mrad",
            "measured_backlash_rad": measured, "prediction": pred,
            "percentile_of_measured": percentile,
            "geometry": {"sun": sun, "planet": planet, "ring": ring, "carrier": pins,
                         "j_sun_planet_mm": j_sp, "j_planet_ring_mm": j_pr,
                         "pin_radius_deviation_mm": pin_dev},
            "details": [
                f"Measured from the print files: tooth thickness on the pitch circle sun "
                f"{sun['tooth_thickness']:.4f}, planet {planet['tooth_thickness']:.4f}, ring "
                f"{ring['tooth_thickness']:.4f} mm (standard {pitch / 2:.4f}); planet pins at "
                f"{pins['pin_radius']:.3f} mm (nominal {m * (cs.SUN + cs.PLANET) / 2:.3f}).",
                f"Designed mesh backlash: sun-planet {j_sp:.4f} mm, planet-ring {j_pr:.4f} mm. "
                "Faceting of the STL files biases these by a few micrometres.",
                f"The published value lies at the {percentile:.1f} percentile of the "
                f"{pred['samples']} predicted copies.",
                "Not blind: the published value was known when the protocol was written; "
                "only the tolerance model was fixed beforehand (2026-11-15).",
                "Not the same quantity: the paper's backlash is the peak-to-peak gap between "
                "motor angle / 7.2 and output angle over a slow sinusoidal motion, which also "
                "contains friction windup, eccentricity and encoder error. One value, no "
                "repeats or spread published."]}
    return out


VALIDATIONS: dict[str, Callable[[Path], dict[str, Any]]] = {
    "transmission-error": validate_transmission_error,
    "transmission-error-v2": lambda root: validate_transmission_error(
        root, "transmission-error-v2", min_periods=2.0),
    "transmission-error-v3": lambda root: validate_transmission_error(
        root, "transmission-error-v3", min_periods=2.0, split="speed-holdout"),
    "transmission-error-v4": lambda root: validate_transmission_error(
        root, "transmission-error-v4", min_periods=2.0, split="speed-holdout", windup=True),
    "transmission-error-axis1": lambda root: validate_transmission_error(
        root, "transmission-error-axis1", min_periods=2.0, split="speed-holdout", windup=True,
        axis_names=("axis_1",)),
    "h1-friction": validate_h1_friction,
    "so101-tracking": validate_so101_tracking,
    "so101-joints": validate_so101_joints,
    "kuka-inverse": validate_kuka_inverse,
    "kuka-inverse-v2": lambda root: validate_kuka_inverse(root, "kuka-inverse-v2",
                                                          coupled=True),
    "nist-tracking": validate_nist_tracking,
    "nist-tracking-v2": lambda root: validate_nist_tracking(root, "nist-tracking-v2",
                                                            accel=True),
    "nist-dynamics": validate_nist_dynamics,
    "nist-tcp": validate_nist_tcp,
    "compact-sspg-backlash": validate_compact_backlash,
}


def run(pid: str, root: Path) -> dict[str, Any]:
    if pid not in VALIDATIONS:
        raise KeyError(f"unknown validation {pid!r}; choose from {sorted(VALIDATIONS)}")
    try:
        return VALIDATIONS[pid](root)
    except SchemaError as exc:
        out = _base(pid)
        out |= {"status": "INCOMPATIBLE DATA", "reason": str(exc)}
        return out
