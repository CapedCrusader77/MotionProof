"""Scan-to-CAD registration: datum alignment and iterative closest point.

Where engineering datums are known, align by datums first and let ICP refine only the degrees
of freedom the datums leave open (``lock``). Unconstrained ICP is a best fit, not a datum
alignment, and the result records which was used. A registration that does not meet its quality
checks is marked ``valid_for_inspection = False`` and must not be used for dimensional results.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

import numpy as np
from numpy.typing import NDArray
from scipy.spatial import cKDTree

from motionproof.core.transforms import axis_angle_matrix, normalize
from motionproof.core.units import length_factor
from motionproof.scans.pointcloud import ScanError

Arr = NDArray[np.float64]
DOF = ("rx", "ry", "rz", "tx", "ty", "tz")


@dataclass
class Nominal:
    """Nominal geometry as a dense oriented surface sample (millimetres)."""

    points: Arr
    normals: Arr
    source: str
    spacing: float
    tree: cKDTree = field(repr=False, compare=False, default=None)

    def __post_init__(self) -> None:
        if self.tree is None:
            self.tree = cKDTree(self.points)

    @classmethod
    def from_mesh(cls, mesh: Any, source: str, count: int = 200_000, seed: int = 0,
                  scale_to_mm: float = 1.0) -> Nominal:
        import trimesh

        pts, face = trimesh.sample.sample_surface(mesh, count, seed=seed)
        spacing = float(np.sqrt(mesh.area * scale_to_mm**2 / count))
        return cls(np.asarray(pts, dtype=float) * scale_to_mm,
                   np.asarray(mesh.face_normals[face], dtype=float), source, spacing)

    @classmethod
    def from_file(cls, path: str | Path, units: str | None = None, count: int = 200_000,
                  seed: int = 0) -> Nominal:
        """STEP (millimetres by definition of the importer) or STL/OBJ (``units`` required)."""
        import trimesh

        p = Path(path)
        ext = p.suffix.lower()
        if ext in (".step", ".stp"):
            import cadquery as cq

            try:
                shape = cq.importers.importStep(str(p))
            except Exception as exc:
                raise ScanError(f"OpenCascade could not read {p.name}: {exc}") from exc
            parts = []
            for val in shape.vals():
                if not isinstance(val, cq.Shape):
                    continue
                verts, faces = val.tessellate(0.01, 0.1)
                parts.append(trimesh.Trimesh([v.toTuple() for v in verts], faces, process=False))
            if not parts:
                raise ScanError(f"{p.name} contains no geometry")
            return cls.from_mesh(trimesh.util.concatenate(parts), p.name, count, seed)
        if ext in (".stl", ".obj", ".ply"):
            if units is None:
                raise ScanError(f"{p.name} carries no length unit; state the unit of the "
                                "nominal mesh")
            mesh = trimesh.load(str(p), force="mesh", process=False)
            return cls.from_mesh(mesh, p.name, count, seed, length_factor(units) * 1000.0)
        raise ScanError(f"unsupported nominal geometry {ext!r}")


@dataclass
class Registration:
    transform: list[list[float]]  # 4x4 taking scan coordinates (mm) into the nominal frame
    method: str
    rms: float
    max_residual: float
    points: int
    inliers: int
    outliers: int
    iterations: int
    converged: bool
    locked: list[str]
    valid_for_inspection: bool
    diagnostics: list[str]

    def apply(self, pts: Arr) -> Arr:
        t = np.asarray(self.transform)
        return pts @ t[:3, :3].T + t[:3, 3]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def fit_plane(points: Arr) -> tuple[Arr, Arr, float]:
    """Least-squares plane: (point on plane, unit normal, RMS out-of-plane residual)."""
    c = points.mean(axis=0)
    _, s, vt = np.linalg.svd(points - c, full_matrices=False)
    return c, vt[2], float(s[2] / np.sqrt(len(points)))


def datum_frame(primary_normal: Arr, secondary_direction: Arr, origin: Arr) -> Arr:
    """Right-handed frame from a primary plane normal (Z), a secondary direction (X after
    projection into the primary plane) and an origin point: the 3-2-1 datum scheme."""
    z = normalize(primary_normal)
    x = np.asarray(secondary_direction, dtype=float)
    x = x - z * float(x @ z)
    if np.linalg.norm(x) < 1e-9:
        raise ScanError("the secondary datum direction is parallel to the primary datum normal")
    x = normalize(x)
    t = np.eye(4)
    t[:3, :3] = np.column_stack([x, np.cross(z, x), z])
    t[:3, 3] = origin
    return t


def align_by_datums(scan_frame: Arr, nominal_frame: Arr) -> Arr:
    """Transform that makes the scan's datum frame coincide with the nominal datum frame."""
    return nominal_frame @ np.linalg.inv(scan_frame)


def _solve(src: Arr, dst: Arr, nrm: Arr | None, free: NDArray[np.bool_]) -> Arr:
    """One linearised rigid update (rotation vector, translation) with locked DOF removed."""
    if nrm is None:  # point to point: p + w x p + t = q
        a = np.zeros((3 * len(src), 6))
        for i in range(3):
            e = np.zeros(3)
            e[i] = 1.0
            a[i::3, :3] = np.cross(src, e)
            a[i::3, 3 + i] = 1.0
        b = (dst - src).ravel()
    else:  # point to plane: ((p + w x p + t) - q) . n = 0
        a = np.hstack([np.cross(src, nrm), nrm])
        b = -np.einsum("ij,ij->i", src - dst, nrm)
    x = np.zeros(6)
    if free.any():
        x[free] = np.linalg.lstsq(a[:, free], b, rcond=None)[0]
    return x


def icp(scan_mm: Arr, nominal: Nominal,
        method: Literal["point_to_point", "point_to_plane"] = "point_to_plane",
        init: Arr | None = None, lock: tuple[str, ...] = (), max_iterations: int = 80,
        trim: float = 0.05, max_distance: float | None = None, tolerance: float = 1e-10,
        noise: float | None = None, accept_rms: float | None = None) -> Registration:
    """Trimmed ICP. ``lock`` names degrees of freedom (in the nominal frame) that stay fixed."""
    unknown = set(lock) - set(DOF)
    if unknown:
        raise ScanError(f"unknown degrees of freedom {sorted(unknown)}; use {DOF}")
    free = np.array([d not in lock for d in DOF])
    t = np.eye(4) if init is None else np.array(init, dtype=float)
    prev = np.inf
    converged = False
    keep = np.ones(len(scan_mm), dtype=bool)
    res = np.zeros(len(scan_mm))
    it = 0
    for it in range(1, max_iterations + 1):  # noqa: B007
        cur = scan_mm @ t[:3, :3].T + t[:3, 3]
        dist, idx = nominal.tree.query(cur)
        q, n = nominal.points[idx], nominal.normals[idx]
        res = np.einsum("ij,ij->i", cur - q, n) if method == "point_to_plane" else dist
        limit = np.quantile(np.abs(res), 1.0 - trim) if trim > 0 else np.inf
        if max_distance is not None:
            limit = min(limit, max_distance)
        keep = np.abs(res) <= limit
        if keep.sum() < 6:
            break
        x = _solve(cur[keep], q[keep], n[keep] if method == "point_to_plane" else None, free)
        angle = float(np.linalg.norm(x[:3]))
        step = np.eye(4)
        if angle > 1e-15:
            step[:3, :3] = axis_angle_matrix(x[:3] / angle, angle)
        step[:3, 3] = x[3:]
        t = step @ t
        rms = float(np.sqrt(np.mean(res[keep] ** 2)))
        if abs(prev - rms) < tolerance and float(np.linalg.norm(x)) < 1e-9:
            converged = True
            break
        prev = rms
    cur = scan_mm @ t[:3, :3].T + t[:3, 3]
    dist, idx = nominal.tree.query(cur)
    res = (np.einsum("ij,ij->i", cur - nominal.points[idx], nominal.normals[idx])
           if method == "point_to_plane" else dist)
    rms = float(np.sqrt(np.mean(res[keep] ** 2))) if keep.any() else float("inf")
    inliers = int(keep.sum())
    diagnostics: list[str] = []
    valid = True
    if not converged:
        valid = False
        diagnostics.append(f"did not converge in {max_iterations} iterations")
    if inliers < 0.7 * len(scan_mm):
        valid = False
        diagnostics.append(f"only {inliers} of {len(scan_mm)} points were used; the scan may "
                           "contain other geometry or be badly positioned")
    threshold = accept_rms if accept_rms is not None else (
        max(5.0 * noise, 3.0 * nominal.spacing) if noise is not None else None)
    if threshold is None:
        diagnostics.append("no acceptance threshold or noise estimate was supplied: the RMS "
                           "residual is reported but not judged")
    elif rms > threshold:
        valid = False
        diagnostics.append(f"RMS residual {rms:.4g} mm exceeds the acceptance threshold "
                           f"{threshold:.4g} mm")
    if not lock:
        diagnostics.append("unconstrained best fit: form errors are spread over the part and "
                           "datum-referenced deviations are not meaningful")
    return Registration(t.tolist(), f"trimmed ICP, {method.replace('_', ' ')}", rms,
                        float(np.abs(res[keep]).max()) if keep.any() else float("inf"),
                        len(scan_mm), inliers, len(scan_mm) - inliers, it, converged,
                        list(lock), valid, diagnostics)


def coarse_align(scan_mm: Arr, nominal: Nominal) -> Arr:
    """Initial pose from centroids and principal axes, trying the four proper orientations."""
    cs, cn = scan_mm.mean(axis=0), nominal.points.mean(axis=0)
    _, _, vs = np.linalg.svd(scan_mm - cs, full_matrices=False)
    _, _, vn = np.linalg.svd(nominal.points - cn, full_matrices=False)
    probe = scan_mm[:: max(1, len(scan_mm) // 2000)]
    best: tuple[float, Arr] | None = None
    for sx in (1, -1):
        for sy in (1, -1):
            a = vs.T @ np.diag([sx, sy, sx * sy * np.linalg.det(vs) * np.linalg.det(vn)]) @ vn
            r = a.T
            if np.linalg.det(r) < 0:
                continue
            t = np.eye(4)
            t[:3, :3] = r
            t[:3, 3] = cn - r @ cs
            d, _ = nominal.tree.query(probe @ r.T + t[:3, 3])
            score = float(np.mean(d**2))
            if best is None or score < best[0]:
                best = (score, t)
    if best is None:
        raise ScanError("could not build an initial alignment")
    return best[1]
