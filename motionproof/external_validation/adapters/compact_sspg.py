"""COMPAct SSPG 7.2:1: print files of a published 3D-printed planetary gearbox.

The source publishes one measured value (no-load backlash) and the STL files the actuator was
printed from, not measurement series. This adapter downloads the four files that define the
gear meshes at a pinned commit and measures their geometry: tooth thickness on the pitch
circle of the sun, planet and ring, and the radius of the planet pins in the carrier.

STL files are faceted, so the measured thicknesses carry a small bias (a few micrometres) from
chords cutting across the involute flanks; it is reported with the result.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import numpy as np

from motionproof.external_validation.adapters.base import Adapter, RemoteFile
from motionproof.external_validation.datasets.registry import COMPACT_COMMIT
from motionproof.external_validation.schemas.trial import SchemaError, Trial

BASE = (f"https://raw.githubusercontent.com/singhaman1750/COMPAct/{COMPACT_COMMIT}/CADs/"
        "Actuator_STL_files/sspg_7.2")
PARTS = ("sun", "planet", "gearbox_casing", "carrier")

# from the paper (Table I) and the print files; checked against the meshes when measured
MODULE = 0.5
SUN, PLANET, RING, PLANETS = 25, 65, 155, 3
PRESSURE_ANGLE = 20.0  # degrees, from the repository's SSPG equation file
PUBLISHED_BACKLASH_DEG = 0.59


class CompactSSPG(Adapter):
    key = "compact-sspg"

    def remote_files(self, root: Path) -> list[RemoteFile]:
        # GitHub publishes no checksum; the commit pins the content and SHA-256 is recorded
        return [RemoteFile(f"sspg_{p}.STL", f"{BASE}/sspg_{p}.STL", None, None, "sspg")
                for p in PARTS]

    def load(self, root: Path, rel: str) -> Trial:
        raise SchemaError("this source has print files, not measurement trials")

    def mesh(self, root: Path, part: str) -> Any:
        import trimesh

        path = self.raw(root) / f"sspg_{part}.STL"
        if not path.exists():
            raise FileNotFoundError(path)
        return trimesh.load(path, force="mesh")


# ---- geometry from a planar section -------------------------------------------------------


def _segments(mesh: Any, z: float) -> np.ndarray:
    from trimesh.intersections import mesh_plane

    seg = mesh_plane(mesh, plane_normal=[0.0, 0.0, 1.0],  # type: ignore[no-untyped-call]
                     plane_origin=[0.0, 0.0, z])
    return np.asarray(seg)[:, :, :2]


def _fit_circle(points: np.ndarray) -> tuple[np.ndarray, float]:
    a = np.c_[2 * points, np.ones(len(points))]
    x = np.linalg.lstsq(a, (points**2).sum(1), rcond=None)[0]
    return x[:2], float(math.sqrt(x[2] + x[:2] @ x[:2]))


def _crossing_angles(seg: np.ndarray, centre: np.ndarray, r: float) -> np.ndarray:
    """Angles at which the section boundary crosses the circle of radius ``r``."""
    a = seg[:, 0] - centre
    d = seg[:, 1] - seg[:, 0]
    qa = (d**2).sum(1)
    qb = 2 * (a * d).sum(1)
    qc = (a**2).sum(1) - r * r
    disc = qb * qb - 4 * qa * qc
    ok = (disc >= 0) & (qa > 0)
    out = []
    for sign in (-1.0, 1.0):
        t = (-qb[ok] + sign * np.sqrt(disc[ok])) / (2 * qa[ok])
        keep = (t >= 0) & (t <= 1)
        p = a[ok][keep] + t[keep, None] * d[ok][keep]
        out.append(np.arctan2(p[:, 1], p[:, 0]))
    return np.unique(np.round(np.concatenate(out), 9))


def _inside(seg: np.ndarray, point: np.ndarray) -> bool:
    """Even-odd rule: is ``point`` inside the section (a ray along +x crosses it oddly)?"""
    y0, y1 = seg[:, 0, 1] - point[1], seg[:, 1, 1] - point[1]
    spans = (y0 > 0) != (y1 > 0)
    x0, x1 = seg[spans, 0, 0], seg[spans, 1, 0]
    t = y0[spans] / (y0[spans] - y1[spans])
    return bool(np.count_nonzero(x0 + t * (x1 - x0) > point[0]) % 2)


def tooth_thickness(mesh: Any, z: float, teeth: int, module: float, internal: bool
                    ) -> dict[str, float]:
    """Tooth thickness and space width on the pitch circle of a gear cut at height ``z``.

    The centre is fitted to the tooth tips (twice, the second time with the points selected
    around the first fit). Each arc of the pitch circle is classed as material or not by the
    even-odd rule at its midpoint."""
    seg = _segments(mesh, z)
    if len(seg) == 0:
        raise SchemaError(f"no material at z = {z} mm")
    pts = seg.reshape(-1, 2)
    rp = module * teeth / 2
    r_tip = rp - module if internal else rp + module
    centre = 0.5 * (pts.min(0) + pts.max(0))
    for band in (0.25 * module, 0.02 * module):
        near_tip = pts[np.abs(np.linalg.norm(pts - centre, axis=1) - r_tip) < band]
        if len(near_tip) < teeth:
            raise SchemaError(f"no tooth tips found near r = {r_tip} mm")
        centre, tip = _fit_circle(near_tip)
    ang = _crossing_angles(seg, centre, rp)
    if len(ang) != 2 * teeth:
        raise SchemaError(f"{len(ang) // 2} teeth on the pitch circle, expected {teeth}")
    ends = np.r_[ang[1:], ang[0] + 2 * np.pi]
    widths = (ends - ang) * rp
    mids = 0.5 * (ang + ends)
    solid = np.array([_inside(seg, centre + rp * np.array([math.cos(a), math.sin(a)]))
                      for a in mids])
    if solid.sum() != teeth:
        raise SchemaError(f"{int(solid.sum())} tooth arcs on the pitch circle, expected {teeth}")
    tooth, space = widths[solid], widths[~solid]
    return {"teeth": float(teeth), "pitch_radius": rp, "tip_radius": tip,
            "tooth_thickness": float(tooth.mean()), "tooth_thickness_sd": float(tooth.std()),
            "space_width": float(space.mean()), "centre_x": float(centre[0]),
            "centre_y": float(centre[1])}


def pin_radius(mesh: Any, z: float, count: int, near: float) -> dict[str, float]:
    """Radius from the carrier axis of ``count`` equal round holes near radius ``near``."""
    from shapely.geometry import LineString
    from shapely.ops import polygonize, unary_union

    seg = _segments(mesh, z)
    polys = list(polygonize(unary_union([LineString(s) for s in np.round(seg, 6)])))
    circles = []
    for poly in polys:
        p = np.asarray(poly.exterior.coords)
        c, r = _fit_circle(p)
        if np.abs(np.linalg.norm(p - c, axis=1) - r).max() < 0.05:
            circles.append((c, r))
    found: dict[str, float] | None = None
    for _, r in circles:
        group = [c for c, rr in circles if abs(rr - r) < 0.01]
        if len(group) != count:
            continue
        axis = np.mean(group, axis=0)          # the pin pattern is centred on the carrier axis
        radii = [float(np.linalg.norm(c - axis)) for c in group]
        if abs(float(np.mean(radii)) - near) < 1.0 and (found is None
                                                        or r > found["hole_radius"]):
            found = {"pin_radius": float(np.mean(radii)),
                     "pin_radius_spread": float(np.ptp(radii)), "hole_radius": r}
    if found is None:
        raise SchemaError(f"no group of {count} equal holes near r = {near} mm")
    return found
