"""Multi-fidelity: the Level 1 quasi-static model and its comparison with Level 2.

Levels
------
* **L1 quasi-static** (this module): variant geometry, kinematics, gravity torque, and the
  static drive-train deflection ``half backlash + load / stiffness``. No time integration, so
  no inertia, friction, speed limit or transient. Milliseconds per evaluation.
* **L2 reduced-order dynamics**: ``motionproof.simulation.engine``.
* **L3 contact / structural**: not implemented.
* **L4 physical experiment**: measurements imported through ``motionproof.hardware`` or CSV.

A Level 1 number is never reported as a simulation result: every value carries its level, and
``sufficient`` says whether Level 1 may be used to judge a constraint or Level 2 is required.
"""

from __future__ import annotations

import math
from typing import Any

import mujoco
import numpy as np

from motionproof.manufacturing.variants import Variant
from motionproof.model import MechanicalModel
from motionproof.simulation.tasks import StaticHold
from motionproof.transmissions.motor import available_torque

L1 = "L1_quasi_static"
L2 = "L2_reduced_order_dynamics"
FLANK_TOLERANCE = 0.02  # N*m: below this load the resting flank is not determined


def static_pose(model: MechanicalModel, variant: Variant, pose: dict[str, float],
                payload_mass: float = 0.0) -> dict[str, Any]:
    """Level 1 evaluation of one variant holding one commanded pose."""
    engine = model.engine
    mj = engine.build_model(variant, payload_mass)
    data = mujoco.MjData(mj)
    for name, value in model.spec.held_joints.items():
        jid = mujoco.mj_name2id(mj, mujoco.mjtObj.mjOBJ_JOINT, name)
        data.qpos[mj.jnt_qposadr[jid]] = pose.get(name, value)  # a pose may re-position it
    metrics: dict[str, float] = {}
    ambiguous = False
    util = 0.0
    angle_err = 0.0
    lower: dict[int, float] = {}
    for name in engine.driven:
        jv = variant.joints[name]
        jid = mujoco.mj_name2id(mj, mujoco.mjtObj.mjOBJ_JOINT, name)
        qadr, dadr = int(mj.jnt_qposadr[jid]), int(mj.jnt_dofadr[jid])
        cmd = pose.get(name, 0.0)
        half = jv.backlash / 2
        te = sum(a * math.sin(c * cmd + ph) for a, c, ph in jv.te)
        out = cmd
        load = 0.0
        for _ in range(8):
            data.qpos[qadr] = out
            mujoco.mj_forward(mj, data)
            load = -float(data.qfrc_bias[dadr])
            s = -load / jv.stiffness
            gap = s + math.copysign(half, s) if abs(load) > FLANK_TOLERANCE else s
            out = cmd + te + jv.zero_offset - gap
        if abs(load) <= FLANK_TOLERANCE and half > 0:
            ambiguous = True
            lower[qadr] = half
        data.qpos[qadr] = out
        angle_err = max(angle_err, abs(cmd - out) + lower.get(qadr, 0.0))
        motor = model.spec.drives[name].motor
        avail = available_torque(motor, 0.0, jv.torque_scale)
        util = max(util, abs(load) / jv.ratio / avail if avail > 0 else math.inf)
    mujoco.mj_kinematics(mj, data)
    ref = engine.reference_ee(pose)
    err = float(np.linalg.norm(engine._ee(data) - ref))
    if ambiguous:  # the joint may rest on either flank: report the larger error
        worst = err
        for qadr, half in lower.items():
            for sign in (-1.0, 1.0):
                base = float(data.qpos[qadr])
                data.qpos[qadr] = base + sign * half
                mujoco.mj_kinematics(mj, data)
                worst = max(worst, float(np.linalg.norm(engine._ee(data) - ref)))
                data.qpos[qadr] = base
        err = worst
    metrics |= {"ee_error_final": err, "ee_error_max": err, "angle_error_final": angle_err,
                "angle_error_max": angle_err, "torque_utilisation_peak": util,
                "backlash": float(sum(j.backlash for j in variant.joints.values())),
                "radial_play": float(max((j.radial_play for j in variant.joints.values()),
                                         default=0.0))}
    if variant.stages:
        metrics["min_mesh_backlash_mm"] = min(s.min_mesh_backlash_mm for s in variant.stages)
    if variant.fits:
        metrics["min_fit_clearance"] = min(f.clearance for f in variant.fits)
    return {"level": L1, "metrics": metrics, "flank_ambiguous": ambiguous,
            "assumptions": ["static equilibrium", "no friction, inertia or speed limits",
                            "load rests on one gear flank unless the load is near zero"]}


def discrepancy(model: MechanicalModel, rows: list[dict[str, float]], pose: dict[str, float],
                payload_mass: float = 0.0,
                metrics: tuple[str, ...] = ("ee_error_final", "angle_error_final",
                                            "torque_utilisation_peak")) -> dict[str, Any]:
    """Measure Level 1 against Level 2 (a simulated static hold) on the same variants."""
    diffs: dict[str, list[float]] = {m: [] for m in metrics}
    rel: dict[str, list[float]] = {m: [] for m in metrics}
    task = StaticHold(pose=pose, duration=1.0, payload_mass=payload_mass)
    used = 0
    for row in rows:
        variant = model.variant(row)
        hi = model.engine.run(variant, task)
        if not hi.valid:
            continue
        lo = static_pose(model, variant, pose, payload_mass)
        used += 1
        for m in metrics:
            d = lo["metrics"][m] - hi.metrics[m]
            diffs[m].append(d)
            rel[m].append(d / hi.metrics[m] if hi.metrics[m] else 0.0)
    out: dict[str, Any] = {"low": L1, "high": L2, "variants": used, "pose": pose,
                           "payload_mass": payload_mass, "metrics": {}}
    for m in metrics:
        d = np.abs(np.asarray(diffs[m]))
        out["metrics"][m] = {
            "mean_difference": float(np.mean(diffs[m])) if used else None,
            "p95_abs_difference": float(np.quantile(d, 0.95)) if used else None,
            "max_abs_difference": float(d.max()) if used else None,
            "p95_abs_relative": float(np.quantile(np.abs(rel[m]), 0.95)) if used else None}
    out["note"] = ("differences are between a static calculation and a dynamic simulation "
                   "settled for 1 s; they grow with friction and near load reversal")
    return out


def sufficient(value: float, op: str, limit: float, p95_abs_difference: float,
               factor: float = 2.0) -> dict[str, Any]:
    """May a Level 1 value decide this constraint, or is a Level 2 run required?

    Level 1 decides only when the value is further from the limit than ``factor`` times the
    measured 95 % Level 1 / Level 2 difference.
    """
    margin = (limit - value) if op == "<=" else (value - limit)
    band = factor * p95_abs_difference
    decided = abs(margin) > band
    return {"level": L1, "margin": margin, "uncertainty_band": band, "sufficient": decided,
            "verdict": ("pass" if margin >= 0 else "fail") if decided else "undecided",
            "action": None if decided else f"run {L2}: the value is within the "
                                           "fidelity-discrepancy band of the limit"}
