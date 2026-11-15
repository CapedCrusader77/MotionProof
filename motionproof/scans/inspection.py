"""Deviation analysis and feature measurement on registered scans.

These are fitted-geometry measurements (least-squares cylinders and planes, deviation
statistics). They are not a standards-conformant GD&T inspection: no tolerance-zone
construction, no material conditions, no measurement-system analysis.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

import numpy as np
from numpy.typing import NDArray
from scipy.optimize import least_squares
from scipy.spatial import cKDTree

from motionproof.core.schema import MechanicalModelSpec
from motionproof.core.transforms import normalize
from motionproof.core.units import length_factor
from motionproof.scans.pointcloud import ScanError
from motionproof.scans.registration import Nominal, fit_plane

Arr = NDArray[np.float64]


def deviation(aligned_mm: Arr, nominal: Nominal, limit: float | None = None,
              coverage_radius: float | None = None, max_points: int = 20_000) -> dict[str, Any]:
    """Signed normal deviation of every scan point from the nominal surface (mm).

    Positive means outside the nominal material. ``limit`` is a symmetric tolerance used for
    the in/out-of-specification split. Nominal surface that no scan point reaches is reported
    as *missing coverage*; it is never counted as zero deviation.
    """
    dist, idx = nominal.tree.query(aligned_mm)
    signed = np.einsum("ij,ij->i", aligned_mm - nominal.points[idx], nominal.normals[idx])
    radius = coverage_radius if coverage_radius is not None else 3.0 * nominal.spacing
    reach, _ = cKDTree(aligned_mm).query(nominal.points, distance_upper_bound=radius)
    covered = np.isfinite(reach)
    q = np.quantile(signed, [0.01, 0.05, 0.5, 0.95, 0.99])
    out: dict[str, Any] = {
        "points": int(len(signed)), "unit": "mm",
        "min": float(signed.min()), "max": float(signed.max()), "mean": float(signed.mean()),
        "std": float(signed.std()), "rms": float(np.sqrt(np.mean(signed**2))),
        "mean_absolute": float(np.abs(signed).mean()),
        "percentiles": {"p01": float(q[0]), "p05": float(q[1]), "p50": float(q[2]),
                        "p95": float(q[3]), "p99": float(q[4])},
        "coverage": {"fraction_of_nominal_surface": float(covered.mean()),
                     "radius_mm": float(radius),
                     "note": "uncovered surface has no measurement; it is not zero deviation"},
        "resolution_mm": float(nominal.spacing),
        "sign_convention": "positive = outside nominal material",
    }
    if limit is not None:
        inside = np.abs(signed) <= limit
        out["specification"] = {"limit_mm": limit, "fraction_within": float(inside.mean()),
                                "points_outside": int((~inside).sum())}
    step = max(1, len(signed) // max_points)
    out["heatmap"] = {"points": aligned_mm[::step].round(4).tolist(),
                      "deviation": signed[::step].round(5).tolist()}
    missing = nominal.points[~covered]
    mstep = max(1, len(missing) // 4000)
    out["missing"] = missing[::mstep].round(3).tolist()
    return out


@dataclass
class CylinderFit:
    diameter: float
    axis_point: list[float]
    axis_direction: list[float]
    rms: float
    points: int
    diameter_std_error: float
    arc_coverage_deg: float
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def fit_cylinder(points: Arr, axis_guess: Arr | None = None) -> CylinderFit:
    """Least-squares cylinder. ``axis_guess`` should come from the nominal feature."""
    if len(points) < 12:
        raise ScanError("at least 12 points are needed to fit a cylinder")
    c0 = points.mean(axis=0)
    if axis_guess is None:
        _, _, vt = np.linalg.svd(points - c0, full_matrices=False)
        axis_guess = vt[0]
    a0 = normalize(axis_guess)
    ref = np.array([1.0, 0, 0]) if abs(a0[0]) < 0.9 else np.array([0, 1.0, 0])
    u = normalize(np.cross(a0, ref))
    v = np.cross(a0, u)

    def unpack(x: Arr) -> tuple[Arr, Arr, float]:
        axis = normalize(a0 + x[0] * u + x[1] * v)
        return axis, c0 + x[2] * u + x[3] * v, float(x[4])

    def residual(x: Arr) -> Arr:
        axis, centre, r = unpack(x)
        d = points - centre
        return np.linalg.norm(d - np.outer(d @ axis, axis), axis=1) - r

    d0 = points - c0
    r0 = float(np.linalg.norm(d0 - np.outer(d0 @ a0, a0), axis=1).mean())
    sol = least_squares(residual, np.array([0.0, 0.0, 0.0, 0.0, r0]), x_scale="jac")
    axis, centre, r = unpack(sol.x)
    res = sol.fun
    dof = max(len(points) - 5, 1)
    sigma2 = float(res @ res) / dof
    try:
        cov = np.linalg.inv(sol.jac.T @ sol.jac) * sigma2
        r_se = float(np.sqrt(max(cov[4, 4], 0.0)))
    except np.linalg.LinAlgError:
        r_se = float("inf")
    d = points - centre
    radial = d - np.outer(d @ axis, axis)
    ang = np.sort(np.arctan2(radial @ np.cross(axis, u), radial @ u))
    gaps = np.diff(np.concatenate([ang, [ang[0] + 2 * np.pi]]))
    arc = float(np.degrees(2 * np.pi - gaps.max()))
    warnings = []
    if arc < 120:
        warnings.append(f"only {arc:.0f} degrees of the circumference are covered: the "
                        "diameter is poorly constrained")
    if axis[np.argmax(np.abs(axis))] < 0:
        axis = -axis
    return CylinderFit(2 * r, (centre - axis * float(centre @ axis)).tolist(), axis.tolist(),
                       float(np.sqrt(np.mean(res**2))), len(points), 2 * r_se, arc, warnings)


def select_near_cylinder(aligned_mm: Arr, axis_point: Arr, axis_direction: Arr, radius: float,
                         band: float, start: float | None = None,
                         length: float | None = None) -> NDArray[np.bool_]:
    """Points within ``band`` of a nominal cylinder surface (and its axial extent)."""
    axis = normalize(axis_direction)
    d = aligned_mm - np.asarray(axis_point, dtype=float)
    along = d @ axis
    radial = np.linalg.norm(d - np.outer(along, axis), axis=1)
    mask = np.abs(radial - radius) <= band
    if start is not None and length is not None:
        mask &= (along >= start) & (along <= start + length)
    return np.asarray(mask, dtype=bool)


def flatness(points: Arr) -> dict[str, float]:
    """Range of residuals about the least-squares plane (an approximation of flatness)."""
    c, n, rms = fit_plane(points)
    r = (points - c) @ n
    return {"range": float(r.max() - r.min()), "rms": rms, "points": int(len(points))}


def axis_offset(fit: CylinderFit, datum_point: Arr, datum_direction: Arr) -> dict[str, float]:
    """Eccentricity and tilt of a fitted cylinder axis relative to a datum axis."""
    a = normalize(datum_direction)
    p = np.asarray(fit.axis_point) - np.asarray(datum_point, dtype=float)
    radial = p - a * float(p @ a)
    cos = abs(float(np.asarray(fit.axis_direction) @ a))
    return {"eccentricity": float(np.linalg.norm(radial)),
            "tilt_rad": float(np.arccos(min(cos, 1.0)))}


def centre_distance(a: CylinderFit, b: CylinderFit) -> float:
    """Distance between two (nearly parallel) fitted cylinder axes."""
    d = np.asarray(b.axis_point) - np.asarray(a.axis_point)
    axis = np.asarray(a.axis_direction)
    return float(np.linalg.norm(d - axis * float(d @ axis)))


@dataclass
class MeasuredFeature:
    """One measured value extracted from a scan, awaiting or carrying engineer approval."""

    id: str
    feature: str | None
    quantity: str  # diameter | eccentricity | centre_distance | flatness | tilt
    value: float
    unit: str
    uncertainty: float | None
    method: str
    scan: str
    registration: str
    status: str = "pending"  # pending | approved | rejected
    tolerance: str | None = None  # tolerance id this value may replace
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def as_built_values(spec: MechanicalModelSpec,
                    measured: list[MeasuredFeature]) -> dict[str, Any]:
    """Tolerance values taken from *approved* measurements (reduced-order as-built model).

    The CAD geometry is not modified: the measured dimensions replace the sampled ones in the
    variant resolver, which turns them into fits, play, misalignment and backlash.
    """
    values: dict[str, float] = {}
    used, skipped = [], []
    for m in measured:
        if m.tolerance is None:
            continue
        if m.status != "approved":
            skipped.append({"id": m.id, "reason": f"status is {m.status}"})
            continue
        tol = spec.tolerance(m.tolerance)
        values[tol.id] = m.value * length_factor(m.unit) / length_factor(tol.unit)
        used.append({"id": m.id, "tolerance": tol.id, "value": values[tol.id], "unit": tol.unit,
                     "uncertainty": m.uncertainty, "in_spec":
                         tol.lower_limit <= values[tol.id] <= tol.upper_limit})
    return {"values": values, "used": used, "skipped": skipped,
            "representation": "reduced-order: measured dimensions drive the variant relations; "
                              "the CAD geometry itself is unchanged"}
