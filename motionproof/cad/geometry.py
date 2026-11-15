"""Mesh inspection, validation, mass properties and collision-geometry generation."""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import trimesh

from motionproof.core.transforms import Mat

MAX_MESH_BYTES = 400 * 1024 * 1024


class GeometryError(ValueError):
    pass


@dataclass
class MeshReport:
    """Geometric facts about one mesh, in the mesh's own length units."""

    file: str
    triangles: int
    vertices: int
    watertight: bool
    winding_consistent: bool
    volume: float | None
    area: float
    bbox_min: list[float]
    bbox_max: list[float]
    extents: list[float]
    center_of_mass: list[float] | None
    degenerate_faces: int
    issues: list[str] = field(default_factory=list)

    @property
    def solid(self) -> bool:
        return self.watertight and self.winding_consistent and (self.volume or 0) > 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self) | {"solid": self.solid}


def file_sha256(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_mesh(path: str | Path) -> trimesh.Trimesh:
    """Load STL/OBJ as a single triangle mesh. Vertices are merged; nothing is rescaled."""
    p = Path(path)
    if not p.is_file():
        raise GeometryError(f"mesh file not found: {p}")
    if p.stat().st_size > MAX_MESH_BYTES:
        raise GeometryError(f"mesh file {p.name} exceeds the {MAX_MESH_BYTES >> 20} MB limit")
    try:
        mesh = trimesh.load(str(p), force="mesh", process=False)
    except Exception as exc:  # trimesh raises many types
        raise GeometryError(f"cannot read mesh {p.name}: {exc}") from exc
    if not isinstance(mesh, trimesh.Trimesh) or len(mesh.faces) == 0:
        raise GeometryError(f"{p.name} contains no triangles")
    mesh.merge_vertices()
    return mesh


def _mp(mesh: trimesh.Trimesh) -> tuple[float, Mat, Mat]:
    """(volume, centre of mass, inertia about COM for unit density)."""
    mp = trimesh.triangles.mass_properties(mesh.triangles, density=1.0)
    return (
        float(mp["volume"]),
        np.asarray(mp["center_mass"], dtype=float),
        np.asarray(mp["inertia"], dtype=float),
    )


def analyse_mesh(mesh: trimesh.Trimesh, name: str = "") -> MeshReport:
    issues: list[str] = []
    watertight = bool(mesh.is_watertight)
    winding = bool(mesh.is_winding_consistent)
    areas = mesh.area_faces
    degenerate = int(np.sum(areas < 1e-14 * max(1.0, float(mesh.scale) ** 2)))
    volume: float | None = None
    com: list[float] | None = None
    if watertight and winding:
        v, c, _ = _mp(mesh)
        volume = v
        com = c.tolist()
        if v <= 0:
            issues.append("volume is not positive: face normals point inward")
    else:
        if not watertight:
            issues.append("mesh is not watertight: volume, centre of mass and inertia are undefined")
        if not winding:
            issues.append("triangle winding is inconsistent")
    if degenerate:
        issues.append(f"{degenerate} degenerate (zero-area) triangles")
    b = mesh.bounds
    return MeshReport(
        file=name,
        triangles=int(len(mesh.faces)),
        vertices=int(len(mesh.vertices)),
        watertight=watertight,
        winding_consistent=winding,
        volume=volume,
        area=float(mesh.area),
        bbox_min=b[0].tolist(),
        bbox_max=b[1].tolist(),
        extents=(b[1] - b[0]).tolist(),
        center_of_mass=com,
        degenerate_faces=degenerate,
        issues=issues,
    )


def mass_properties_si(
    mesh: trimesh.Trimesh, scale: float, density: float
) -> tuple[float, Mat, Mat]:
    """Mass (kg), COM (m) and inertia about the COM (kg*m^2) of a closed mesh.

    ``scale`` converts mesh units to metres, ``density`` is kg/m^3. Raises for meshes whose
    volume integral is not meaningful (open or inconsistently wound).
    """
    if not (mesh.is_watertight and mesh.is_winding_consistent):
        raise GeometryError("mass properties need a watertight, consistently wound mesh")
    volume, com, inertia = _mp(mesh)
    if volume <= 0:
        raise GeometryError("mesh volume is not positive (inverted normals)")
    return (
        density * volume * scale**3,
        com * scale,
        inertia * density * scale**5,
    )


# ---- collision geometry ---------------------------------------------------------


def _hull(points: np.ndarray) -> trimesh.Trimesh | None:
    if len(points) < 4:
        return None
    try:
        h = trimesh.convex.convex_hull(points)
    except Exception:
        return None
    return h if len(h.faces) >= 4 and h.volume > 0 else None


def _split(mesh: trimesh.Trimesh, normal: np.ndarray, origin: np.ndarray) -> list[trimesh.Trimesh]:
    out = []
    for sign in (1.0, -1.0):
        try:
            part = trimesh.intersections.slice_mesh_plane(  # type: ignore[no-untyped-call]
                mesh, sign * normal, origin, cap=False)
        except Exception:
            return []
        if part is None or len(part.faces) == 0:
            return []
        out.append(part)
    return out


def convex_decompose(
    mesh: trimesh.Trimesh, max_pieces: int = 8, max_error: float = 0.05
) -> tuple[list[trimesh.Trimesh], float | None]:
    """Approximate ``mesh`` by a set of convex hulls.

    Greedy planar splitting: at each step the cut (through a piece's centroid, along one of
    its principal axes) that most reduces the total hull volume is applied. Pieces on opposite
    sides of a cut cannot overlap, so ``sum(hull volumes) / mesh volume - 1`` is the relative
    volume excess of the approximation; it is returned as the recorded simplification error
    (``None`` when the mesh is not a closed solid and the error cannot be measured).
    """
    solid = mesh.is_watertight and mesh.is_winding_consistent and mesh.volume > 0
    first = _hull(np.asarray(mesh.vertices))
    if first is None:
        raise GeometryError("cannot build a convex hull (degenerate geometry)")
    if not solid:
        return [first], None
    target = float(mesh.volume)
    pieces: list[tuple[trimesh.Trimesh, trimesh.Trimesh]] = [(mesh, first)]

    def error() -> float:
        return sum(float(h.volume) for _, h in pieces) / target - 1.0

    while len(pieces) < max_pieces and error() > max_error:
        best: tuple[float, int, list[tuple[trimesh.Trimesh, trimesh.Trimesh]]] | None = None
        for idx, (part, hull) in enumerate(pieces):
            pts = np.asarray(part.vertices)
            centre = pts.mean(axis=0)
            _, _, vt = np.linalg.svd(pts - centre, full_matrices=False)
            lo, hi = pts.min(axis=0), pts.max(axis=0)
            candidates = [(vt[k], centre) for k in range(3)]
            candidates += [(np.eye(3)[k], (lo + hi) / 2) for k in range(3)]
            for normal, origin in candidates:
                halves = _split(part, normal, origin)
                if len(halves) != 2:
                    continue
                hulls = [_hull(np.asarray(h.vertices)) for h in halves]
                if any(h is None for h in hulls):
                    continue
                gain = float(hull.volume) - sum(float(h.volume) for h in hulls if h is not None)
                if best is None or gain > best[0]:
                    best = (gain, idx, list(zip(halves, hulls, strict=True)))  # type: ignore[arg-type]
        if best is None or best[0] <= 1e-9 * target:
            break
        _, idx, new = best
        pieces[idx : idx + 1] = new
    return [h for _, h in pieces], error()
