"""Workspace reliability maps: how positioning error varies over the reachable poses.

Each grid pose is evaluated for every manufactured variant with the Level 1 quasi-static model
(kinematics, gravity load, backlash and windup), which costs milliseconds; selected poses can
be checked against Level 2 dynamics with ``verify_pose``. Collision is not evaluated (the
models carry no collision geometry) and is reported as such.
"""

from __future__ import annotations

import itertools
from typing import Any

import mujoco
import numpy as np

from motionproof.fidelity.static import L1, L2, static_pose
from motionproof.model import MechanicalModel
from motionproof.simulation.tasks import StaticHold
from motionproof.statistics.robustness import wilson_interval

MAX_EVALUATIONS = 400_000


def _manipulability(model: MechanicalModel, pose: dict[str, float], joints: list[str]) -> float:
    """sqrt(det(J J^T)) of the end-effector position Jacobian for the gridded joints."""
    mj = model.mj_model
    if mj is None:
        raise ValueError("the model has no dynamics description")
    engine = model.engine
    data = mujoco.MjData(mj)
    for name, value in {**model.spec.held_joints, **pose}.items():
        jid = mujoco.mj_name2id(mj, mujoco.mjtObj.mjOBJ_JOINT, name)
        data.qpos[mj.jnt_qposadr[jid]] = value
    mujoco.mj_forward(mj, data)
    jacp = np.zeros((3, mj.nv))
    mujoco.mj_jac(mj, data, jacp, None, engine._ee(data), engine.ee_body)
    cols = [int(mj.jnt_dofadr[mujoco.mj_name2id(mj, mujoco.mjtObj.mjOBJ_JOINT, j)])
            for j in joints]
    j = jacp[:, cols]
    s = np.linalg.svd(j, compute_uv=False)
    return float(np.prod(s[: min(j.shape)]))


def reliability_map(model: MechanicalModel, grid: dict[str, list[float]],
                    rows: list[dict[str, float]], position_tolerance: float | None = None,
                    payload_mass: float = 0.0, independent_draws: bool = True
                    ) -> dict[str, Any]:
    """Evaluate every grid pose for every variant row (Level 1)."""
    mj = model.mj_model
    if mj is None:
        raise ValueError("the model has no dynamics description")
    joints = list(grid)
    known = set(model.spec.drives) | set(model.spec.held_joints)
    unknown = set(joints) - known
    if unknown:
        raise KeyError(f"grid joints are neither driven nor held: {sorted(unknown)}")
    poses = [dict(zip(joints, combo, strict=True))
             for combo in itertools.product(*(grid[j] for j in joints))]
    if len(poses) * max(len(rows), 1) > MAX_EVALUATIONS:
        raise ValueError(f"{len(poses)} poses x {len(rows)} variants exceeds "
                         f"{MAX_EVALUATIONS} evaluations; reduce the grid or the sample")
    variants = [model.variant(r) for r in rows]
    limits: dict[str, Any] = {}
    for j in joints:
        jid = mujoco.mj_name2id(mj, mujoco.mjtObj.mjOBJ_JOINT, j)
        limits[j] = mj.jnt_range[jid] if mj.jnt_limited[jid] else None
    cells = []
    scale = None
    for pose in poses:
        reachable = all(limits[j] is None or limits[j][0] - 1e-9 <= q <= limits[j][1] + 1e-9
                        for j, q in pose.items())
        cell: dict[str, Any] = {"pose": pose, "reachable": reachable,
                                "position": model.engine.reference_ee(pose).tolist()}
        if not reachable:
            cell["note"] = "outside the joint range"
            cells.append(cell)
            continue
        man = _manipulability(model, pose, joints)
        scale = man if scale is None else max(scale, man)
        errs = np.array([static_pose(model, v, pose, payload_mass)["metrics"]["ee_error_final"]
                         for v in variants])
        cell |= {"manipulability": man, "samples": int(len(errs)),
                 "error_mean": float(errs.mean()), "error_rms": float(np.sqrt(np.mean(errs**2))),
                 "error_max": float(errs.max()), "error_p95": float(np.quantile(errs, 0.95))}
        if position_tolerance is not None:
            ok = int(np.sum(errs <= position_tolerance))
            cell["within_tolerance"] = ok / len(errs)
            cell["interval"] = list(wilson_interval(ok, len(errs))) if independent_draws else None
        cells.append(cell)
    for c in cells:
        if c["reachable"] and scale:
            c["near_singular"] = c["manipulability"] < 1e-3 * scale
    return {"level": L1, "joints": joints, "grid": grid, "variants": len(rows),
            "position_tolerance": position_tolerance, "payload_mass": payload_mass,
            "interval_method": "Wilson score, 95 %" if independent_draws else
            "none: the variant rows are not independent draws",
            "collision": "not evaluated: the model has no collision geometry",
            "cells": cells,
            "note": "Level 1 quasi-static errors; use verify_pose for a Level 2 check"}


def verify_pose(model: MechanicalModel, pose: dict[str, float], rows: list[dict[str, float]],
                payload_mass: float = 0.0) -> dict[str, Any]:
    """Direct Level 2 simulation of one map pose, for comparison with the map value."""
    driven = {k: v for k, v in pose.items() if k in model.spec.drives}
    if len(driven) != len(pose):
        raise ValueError("Level 2 verification can only vary driven joints; held joints keep "
                         "their configured angle")
    errs = []
    for row in rows:
        res = model.engine.run(model.variant(row),
                               StaticHold(pose=driven, duration=1.0, payload_mass=payload_mass))
        if res.valid:
            errs.append(res.metrics["ee_error_final"])
    e = np.asarray(errs)
    return {"level": L2, "pose": pose, "samples": int(len(e)), "error_mean": float(e.mean()),
            "error_rms": float(np.sqrt(np.mean(e**2))), "error_max": float(e.max())}


def compare_maps(a: dict[str, Any], b: dict[str, Any], metric: str = "error_rms"
                 ) -> dict[str, Any]:
    """Cell-by-cell difference ``b - a`` of two maps computed on the same grid."""
    if a["grid"] != b["grid"]:
        raise ValueError("the two maps use different grids and cannot be compared cell by cell")
    cells = []
    for ca, cb in zip(a["cells"], b["cells"], strict=True):
        if ca["reachable"] and cb["reachable"]:
            cells.append({"pose": ca["pose"], "position": ca["position"], "a": ca[metric],
                          "b": cb[metric], "difference": cb[metric] - ca[metric]})
    worse = sum(c["difference"] > 0 for c in cells)
    return {"metric": metric, "cells": cells, "b_worse_in": worse,
            "b_better_in": sum(c["difference"] < 0 for c in cells)}
