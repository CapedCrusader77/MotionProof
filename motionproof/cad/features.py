"""Geometric feature detection on B-rep solids and exact fit measurement (OpenCascade).

Detected features are *suggestions*: STEP carries no design intent, so a cylindrical face is
reported with its measured radius and axis and left for the engineer to confirm.
"""

from __future__ import annotations

from typing import Any

import cadquery as cq
import numpy as np
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.BRepExtrema import BRepExtrema_DistShapeShape
from OCP.GeomAbs import GeomAbs_Cylinder, GeomAbs_Plane


def as_shape(wp: cq.Workplane) -> cq.Shape:
    """The single shape held by a workplane (raises when it holds something else)."""
    v = wp.val()
    if not isinstance(v, cq.Shape):
        raise TypeError(f"expected a shape, got {type(v).__name__}")
    return v


def solids_of(shape: cq.Workplane) -> list[cq.Shape]:
    """All solids of every shape on a workplane."""
    return [s for v in shape.vals() if isinstance(v, cq.Shape) for s in v.Solids()]


def cylindrical_features(solid: cq.Shape, min_radius: float = 0.0) -> list[dict[str, Any]]:
    """Group cylindrical faces by axis and radius; classify as external (shaft) or internal."""
    groups: dict[tuple[float, ...], dict[str, Any]] = {}
    for idx, face in enumerate(solid.Faces()):
        surf = BRepAdaptor_Surface(face.wrapped)
        if surf.GetType() != GeomAbs_Cylinder:
            continue
        cyl = surf.Cylinder()
        r = float(cyl.Radius())
        if r < min_radius:
            continue
        loc, d = cyl.Axis().Location(), cyl.Axis().Direction()
        p0 = np.array([loc.X(), loc.Y(), loc.Z()])
        axis = np.array([d.X(), d.Y(), d.Z()])
        if axis[np.argmax(np.abs(axis))] < 0:
            axis = -axis
        foot = p0 - axis * float(p0 @ axis)  # axis point closest to the origin
        # sample a point on the surface and compare the outward normal with the radial direction
        u = (surf.FirstUParameter() + surf.LastUParameter()) / 2
        v = (surf.FirstVParameter() + surf.LastVParameter()) / 2
        pnt = surf.Value(u, v)
        c = np.array([pnt.X(), pnt.Y(), pnt.Z()])
        radial = c - (foot + axis * float((c - foot) @ axis))
        n = face.normalAt(cq.Vector(*c))
        external = bool(np.array([n.x, n.y, n.z]) @ radial > 0)
        key = (*np.round(foot, 5), *np.round(axis, 6), round(r, 6), float(external))
        bb = face.BoundingBox()
        corners = np.array([[bb.xmin, bb.ymin, bb.zmin], [bb.xmax, bb.ymax, bb.zmax]]) @ axis
        lo, hi = float(corners.min()), float(corners.max())
        g = groups.setdefault(key, {"axis_point": foot.tolist(), "axis_direction": axis.tolist(),
                                    "radius": r, "diameter": 2 * r, "external": external,
                                    "faces": [], "lo": lo, "hi": hi})
        g["faces"].append(idx)
        g["lo"], g["hi"] = min(g["lo"], lo), max(g["hi"], hi)
    out = []
    for g in groups.values():
        g["length"] = g["hi"] - g["lo"]
        g["axis_start"] = (np.array(g["axis_point"]) + np.array(g["axis_direction"]) * g.pop("lo")
                           ).tolist()
        g.pop("hi")
        g["suggested_type"] = "shaft" if g["external"] else "bore"
        g["status"] = "suggested"
        out.append(g)
    return sorted(out, key=lambda g: (-g["radius"], g["faces"][0]))


def planar_features(solid: cq.Shape, limit: int = 12) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for idx, face in enumerate(solid.Faces()):
        if BRepAdaptor_Surface(face.wrapped).GetType() != GeomAbs_Plane:
            continue
        c, n = face.Center(), face.normalAt()
        out.append({"face": idx, "point": [c.x, c.y, c.z], "normal": [n.x, n.y, n.z],
                    "area": float(face.Area()), "suggested_type": "datum_plane",
                    "status": "suggested"})
    return sorted(out, key=lambda f: -float(f["area"]))[:limit]


def min_distance(a: cq.Shape, b: cq.Shape) -> float:
    """Exact minimum distance between two shapes (0 when they touch or overlap)."""
    ext = BRepExtrema_DistShapeShape(a.wrapped, b.wrapped)
    if not ext.IsDone():
        raise RuntimeError("OpenCascade distance computation failed")
    return float(ext.Value())


def interference_volume(a: cq.Shape, b: cq.Shape) -> float:
    """Volume of the boolean intersection of two solids (0 when they do not overlap)."""
    try:
        return float(max(a.intersect(b).Volume(), 0.0))
    except Exception:
        return 0.0


def measure_shaft_in_bore(
    shaft_diameter: float, bore_diameter: float, length: float, radial_offset: float = 0.0
) -> dict[str, float]:
    """Build an as-manufactured shaft and sleeve and measure the fit on real solids.

    Returns the minimum radial gap and the interference volume. With concentric parts the gap
    equals ``(bore - shaft) / 2``; an offset shaft reduces it by the offset.
    """
    shaft = as_shape(cq.Workplane("XY").circle(shaft_diameter / 2).extrude(length))
    shaft = shaft.translate(cq.Vector(radial_offset, 0, 0))
    sleeve = as_shape(
        cq.Workplane("XY").circle(bore_diameter / 2 + 5.0).circle(bore_diameter / 2)
        .extrude(length)
    )
    return {
        "min_radial_gap": min_distance(shaft, sleeve),
        "interference_volume": interference_volume(shaft, sleeve),
    }
