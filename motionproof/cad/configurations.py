"""Derive joints from two STEP exports of the same assembly in different poses.

STEP carries no joint definitions. When the same assembly is exported in two configurations,
every solid that moved gives a rigid transform; solids sharing one transform form the moving
group, and a pure rotation yields the joint axis and angle. This is evidence from the files,
not a guess, and each result carries its fit residual.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import cadquery as cq
import numpy as np

from motionproof.cad.importers import ImportFailure
from motionproof.core.transforms import rotation_error

MAX_POINTS = 400


def _solids(path: Path) -> tuple[list[cq.Shape], list[str]]:
    try:
        from motionproof.cad.features import solids_of

        solids = solids_of(cq.importers.importStep(str(path)))
    except Exception as exc:
        raise ImportFailure(f"OpenCascade could not read {path.name}: {exc}") from exc
    try:
        names = [n for n, sub in cq.Assembly.importStep(str(path)).traverse()
                 if sub.obj is not None]
    except Exception:
        names = []
    if len(names) != len(solids):
        names = [f"solid_{i + 1:03d}" for i in range(len(solids))]
    return solids, names


def _points(solid: cq.Shape) -> np.ndarray:
    """Vertices, face centres and the centre of mass: enough to locate round parts too."""
    pts = [[v.X, v.Y, v.Z] for v in solid.Vertices()[:MAX_POINTS]]
    pts += [list(f.Center().toTuple()) for f in solid.Faces()[:MAX_POINTS]]
    pts.append(list(cq.Shape.centerOfMass(solid).toTuple()))
    return np.array(pts)


def _well_conditioned(p: np.ndarray) -> bool:
    """True when the points span three dimensions, so a rotation fit is unique."""
    s = np.linalg.svd(p - p.mean(axis=0), compute_uv=False)
    return bool(len(s) >= 3 and s[1] > 1e-6 * max(s[0], 1e-12) and s[0] > 1e-9)


def rigid_fit(p: np.ndarray, q: np.ndarray) -> tuple[np.ndarray, np.ndarray, float]:
    """Least-squares rotation and translation taking points ``p`` to ``q`` (Kabsch)."""
    cp, cq_ = p.mean(axis=0), q.mean(axis=0)
    u, _, vt = np.linalg.svd((p - cp).T @ (q - cq_))
    d = np.sign(np.linalg.det(vt.T @ u.T))
    r = vt.T @ np.diag([1.0, 1.0, d]) @ u.T
    t = cq_ - r @ cp
    return r, t, float(np.abs(p @ r.T + t - q).max())


def compare_configurations(reference: str | Path, moved: str | Path,
                           tolerance: float = 1e-6) -> dict[str, Any]:
    """Find what moved between two exports and the joint that explains it (lengths in mm)."""
    a, names_a = _solids(Path(reference))
    b, names_b = _solids(Path(moved))
    if len(a) != len(b):
        raise ImportFailure(f"the two files contain different numbers of solids "
                            f"({len(a)} and {len(b)}); they are not the same assembly")
    if names_a != names_b:
        raise ImportFailure("the two files list their parts in a different order; solids "
                            "cannot be matched reliably")
    groups: list[dict[str, Any]] = []
    fixed: list[str] = []
    unmatched: list[str] = []
    deferred: list[tuple[str, np.ndarray, np.ndarray]] = []
    for sa, sb, name in zip(a, b, names_a, strict=True):
        p, q = _points(sa), _points(sb)
        if p.shape != q.shape:
            unmatched.append(name)
            continue
        if np.abs(p - q).max() <= tolerance:
            fixed.append(name)
            continue
        if not _well_conditioned(p):
            # axisymmetric or flat point set: its own rotation is ambiguous, so it is
            # assigned afterwards to a group whose motion explains it
            deferred.append((name, p, q))
            continue
        r, t, residual = rigid_fit(p, q)
        if residual > 1e-4 * max(1.0, float(np.ptp(p, axis=0).max())):
            unmatched.append(name)
            continue
        for g in groups:
            if np.allclose(g["_r"], r, atol=1e-7) and np.allclose(g["_t"], t, atol=1e-5):
                g["components"].append(name)
                g["max_residual_mm"] = max(g["max_residual_mm"], residual)
                break
        else:
            groups.append({"_r": r, "_t": t, "components": [name], "max_residual_mm": residual})
    for name, p, q in deferred:
        for g in groups:
            residual = float(np.abs(p @ g["_r"].T + g["_t"] - q).max())
            if residual <= 1e-5 * max(1.0, float(np.ptp(p, axis=0).max())):
                g["components"].append(name)
                g["max_residual_mm"] = max(g["max_residual_mm"], residual)
                break
        else:
            unmatched.append(name)
    joints = []
    for g in groups:
        r, t = g.pop("_r"), g.pop("_t")
        rotvec = rotation_error(np.eye(3), r)
        angle = float(np.linalg.norm(rotvec))
        entry: dict[str, Any] = {"components": g["components"],
                                 "max_residual_mm": g["max_residual_mm"]}
        if angle < 1e-9:
            entry |= {"type": "prismatic", "axis": (t / np.linalg.norm(t)).tolist(),
                      "travel_mm": float(np.linalg.norm(t))}
        else:
            axis = rotvec / angle
            slide = float(t @ axis)
            # a point on the axis: solve (I - R) c = t - slide * axis, take the foot point
            c = np.linalg.lstsq(np.eye(3) - r, t - slide * axis, rcond=None)[0]
            c = c - axis * float(c @ axis)
            entry |= {"type": "revolute" if abs(slide) < 1e-6 else "screw",
                      "axis": axis.tolist(), "point_mm": c.tolist(),
                      "angle_rad": angle, "angle_deg": float(np.degrees(angle)),
                      "axial_travel_mm": slide}
        joints.append(entry)
    return {"reference": Path(reference).name, "moved": Path(moved).name,
            "solids": len(a), "fixed": fixed, "unmatched": unmatched, "joints": joints,
            "note": "Derived from two poses. Parts that did not move between the files "
                    "(for example gears left unposed) are reported as fixed."}
