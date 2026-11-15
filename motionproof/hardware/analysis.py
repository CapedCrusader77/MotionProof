"""Model-independent analysis of a test-rig session.

Everything here is computed from the recorded signals and the commanded test alone, so it can
be used to validate the model rather than depending on it:

* positioning error at each settle point (command minus output, averaged over the second half
  of the settle window);
* lost motion on reversal (difference of the two approaches to the same target);
* repeatability over cycles (spread and standard deviation of the settle positions);
* measured reduction ratio, from settled points reached in the same direction (requires raw
  motor counts and the motor counts per revolution).
"""

from __future__ import annotations

import csv
import math
from pathlib import Path
from typing import Any, Literal

import numpy as np

from motionproof.hardware.device import HardwareTest
from motionproof.simulation.tasks import build_plan

COLUMNS = ("time_s", "command_rad", "motor_angle_rad", "output_angle_rad")


def load_session_csv(path: str | Path) -> dict[str, np.ndarray]:
    """Read a session CSV written by ``Session.write_csv`` (comment lines start with #)."""
    rows: list[dict[str, str]] = []
    with Path(path).open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(line for line in f if not line.startswith("#"))
        missing = [c for c in COLUMNS if c not in (reader.fieldnames or [])]
        if missing:
            raise ValueError(f"{Path(path).name}: missing columns {missing}")
        rows = list(reader)
    if len(rows) < 10:
        raise ValueError(f"{Path(path).name}: fewer than 10 samples")
    out = {c: np.array([float(r[c]) for r in rows]) for c in COLUMNS}
    for c in ("input_counts", "output_counts"):
        if rows and c in rows[0] and rows[0][c] not in ("", None):
            out[c] = np.array([float(r[c]) for r in rows])
    if np.any(np.diff(out["time_s"]) <= 0):
        raise ValueError(f"{Path(path).name}: time is not strictly increasing")
    return out


def analyse(test: HardwareTest, data: dict[str, np.ndarray],
            motor_counts_per_rev: float | None = None,
            nominal_ratio: float | None = None,
            flank: Literal["arrival", "load"] = "arrival") -> dict[str, Any]:
    """``flank`` states which gear flank carries the output at rest, which the recorded
    signals cannot tell: ``arrival`` (no net load; friction holds the output on the flank it
    arrived on) or ``load`` (a one-sided load such as gravity well away from vertical keeps
    every settled point on the same flank). The ratio estimate is only valid if this is true
    for the test that was run."""
    t, cmd, out = data["time_s"], data["command_rad"], data["output_angle_rad"]
    task = test.task()
    plan = build_plan(task, [test.joint])
    half = 0.5 * test.settle
    points: list[dict[str, Any]] = []
    for when, label in plan.measurements:
        sel = (t > when - half) & (t <= when)
        if sel.sum() < 3:
            points.append({"label": label, "time": when, "samples": int(sel.sum()),
                           "note": "too few samples in the settle window"})
            continue
        c = float(np.mean(cmd[sel]))
        o = float(np.mean(out[sel]))
        points.append({"label": label, "time": when, "samples": int(sel.sum()),
                       "command": c, "output": o, "error": c - o,
                       "output_std": float(np.std(out[sel]))})
    valid = [p for p in points if "output" in p]
    res: dict[str, Any] = {"test": test.model_dump(), "samples": int(len(t)),
                           "sample_rate_hz": float(1.0 / np.median(np.diff(t))),
                           "settle_points": points}
    if valid:
        errs = np.array([p["error"] for p in valid])
        res["positioning_error"] = {"mean": float(errs.mean()),
                                    "max_abs": float(np.abs(errs).max()),
                                    "rms": float(np.sqrt(np.mean(errs**2)))}
    by = {p["label"]: p for p in valid}
    if "approach_up" in by and "approach_down" in by:
        res["lost_motion"] = abs(by["approach_down"]["output"] - by["approach_up"]["output"])
        res["lost_motion_note"] = ("difference of the two settled approaches to one target; "
                                   "includes backlash and elastic windup under friction")
    groups: dict[str, list[float]] = {}
    for p in valid:
        groups.setdefault(p["label"], []).append(p["output"])
    rep = {k: {"n": len(v), "range": float(max(v) - min(v)),
               "std": float(np.std(v, ddof=1)) if len(v) > 1 else None}
           for k, v in groups.items() if len(v) > 1}
    if rep:
        res["repeatability"] = rep
    # encoder resolution sets the floor of what can be resolved
    steps = np.abs(np.diff(out))
    steps = steps[steps > 0]
    if len(steps):
        res["output_resolution_rad"] = float(np.min(steps))
    if "input_counts" in data and motor_counts_per_rev:
        # Settled hold points reached by moves in the same direction rest on the same gear
        # flank with the same static windup, so their differences contain no backlash.
        holds = []
        for i in range(1, len(plan.times)):
            if plan.poses[i] == plan.poses[i - 1] and i >= 2:
                arrival = float(np.sign(plan.poses[i - 1][0] - plan.poses[i - 2][0]))
                when = plan.times[i]
                sel = (t > when - half) & (t <= when)
                if sel.sum() >= 3 and arrival != 0:
                    holds.append((arrival, float(np.mean(data["input_counts"][sel])),
                                  float(np.mean(out[sel]))))
        ratios = []
        for (d0, m0, o0), (d1, m1, o1) in zip(holds, holds[1:], strict=False):
            if (flank == "load" or d0 == d1) and abs(o1 - o0) > 1e-6:
                ratios.append(((m1 - m0) / motor_counts_per_rev) / ((o1 - o0) / (2 * math.pi)))
        if ratios:
            res["measured_ratio"] = float(np.mean(ratios))
            if nominal_ratio:
                res["ratio_error"] = float(res["measured_ratio"] / nominal_ratio - 1.0)
            res["ratio_note"] = (f"from {len(ratios)} pair(s) of settled points assumed to rest "
                                 f"on the same flank (flank assumption: {flank}); wrong if the "
                                 "output crossed the dead band between them")
        else:
            res["ratio_note"] = ("not available: the test has no two settled points reached "
                                 "in the same direction (use a reversal test)")
    return res
