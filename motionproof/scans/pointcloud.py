"""Point-cloud import and cleaning for as-built inspection.

Formats: PLY, PCD (ASCII), XYZ/TXT, CSV, and STL/OBJ (surface sampled). Units are never
assumed: a cloud without a stated unit keeps ``units = None`` and cannot be registered against
CAD until the user states one.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray
from scipy.spatial import cKDTree

from motionproof.core.units import length_factor

Arr = NDArray[np.float64]
TEXT_CHUNK = 200_000
DEFAULT_MAX_POINTS = 2_000_000


class ScanError(ValueError):
    """A scan problem with a message the user can act on."""


@dataclass
class PointCloud:
    points: Arr  # (n, 3) in the cloud's own units
    units: str | None = None
    normals: Arr | None = None
    colors: Arr | None = None
    confidence: Arr | None = None
    meta: dict[str, Any] = field(default_factory=dict)
    history: list[str] = field(default_factory=list)

    def __len__(self) -> int:
        return int(len(self.points))

    def in_mm(self) -> Arr:
        if self.units is None:
            raise ScanError("the scan has no length unit; state it before comparing with CAD "
                            "(nothing is scaled or assumed)")
        return self.points * (length_factor(self.units) * 1000.0)

    def subset(self, mask: NDArray[np.bool_], note: str) -> PointCloud:
        def pick(a: Arr | None) -> Arr | None:
            return None if a is None else a[mask]
        return PointCloud(self.points[mask], self.units, pick(self.normals), pick(self.colors),
                          pick(self.confidence), dict(self.meta), [*self.history, note])

    def summary(self) -> dict[str, Any]:
        lo, hi = self.points.min(axis=0), self.points.max(axis=0)
        return {"points": len(self), "units": self.units, "bbox_min": lo.tolist(),
                "bbox_max": hi.tolist(), "extents": (hi - lo).tolist(),
                "has_normals": self.normals is not None, "has_colors": self.colors is not None,
                "has_confidence": self.confidence is not None, "meta": self.meta,
                "history": self.history}


def _assign(columns: list[str] | None, data: Arr) -> dict[str, Arr | None]:
    """Split a numeric table into xyz / normals / colours / confidence."""
    n = data.shape[1]
    if n < 3:
        raise ScanError("a point file needs at least three numeric columns (x, y, z)")
    out: dict[str, Arr | None] = {"points": None, "normals": None, "colors": None,
                                  "confidence": None}
    if columns:
        idx = {c.strip().lower(): i for i, c in enumerate(columns)}

        def take(names: tuple[str, ...]) -> Arr | None:
            return data[:, [idx[k] for k in names]] if all(k in idx for k in names) else None

        out["points"] = take(("x", "y", "z"))
        out["normals"] = take(("nx", "ny", "nz"))
        if out["normals"] is None:
            out["normals"] = take(("normal_x", "normal_y", "normal_z"))
        out["colors"] = take(("r", "g", "b"))
        if out["colors"] is None:
            out["colors"] = take(("red", "green", "blue"))
        for key in ("confidence", "quality", "intensity"):
            if key in idx:
                out["confidence"] = data[:, idx[key]]
                break
    if out["points"] is None:
        out["points"] = data[:, :3]
        if n >= 6 and columns is None:
            block = data[:, 3:6]
            unit_len = np.abs(np.linalg.norm(block, axis=1) - 1.0) < 1e-2
            if unit_len.mean() > 0.95:
                out["normals"] = block
            elif block.min() >= 0 and block.max() <= 255:
                out["colors"] = block
    return out


def _read_text(path: Path, delimiter: str | None, max_points: int) -> PointCloud:
    """Chunked reader: thins the stream by a stride instead of holding every row."""
    header: list[str] | None = None
    chunks: list[Arr] = []
    total = kept = 0
    stride = 1
    with path.open(newline="", encoding="utf-8-sig") as f:
        rows: list[list[float]] = []
        for raw in f:
            line = raw.strip()
            if not line or line.startswith(("#", "//")):
                continue
            parts = next(csv.reader([line])) if delimiter == "," else line.split()
            try:
                vals = [float(p) for p in parts]
            except ValueError:
                if header is None and total == 0:
                    header = parts
                    continue
                raise ScanError(f"{path.name}: non-numeric value in row {total + 1}") from None
            total += 1
            if total % stride:
                continue
            rows.append(vals)
            if len(rows) >= TEXT_CHUNK:
                chunks.append(np.asarray(rows, dtype=float))
                kept += len(rows)
                rows = []
                if kept >= max_points:  # halve the retained density and keep reading
                    chunks = [np.concatenate(chunks)[::2]]
                    kept = len(chunks[0])
                    stride *= 2
        if rows:
            widths = {len(r) for r in rows}
            if len(widths) != 1:
                raise ScanError(f"{path.name}: rows have differing numbers of columns")
            chunks.append(np.asarray(rows, dtype=float))
    if not chunks:
        raise ScanError(f"{path.name} contains no points")
    try:
        data = np.concatenate(chunks)
    except ValueError:
        raise ScanError(f"{path.name}: rows have differing numbers of columns") from None
    parts_ = _assign(header, data)
    cloud = PointCloud(parts_["points"], normals=parts_["normals"], colors=parts_["colors"],  # type: ignore[arg-type]
                       confidence=parts_["confidence"])
    cloud.meta |= {"rows_in_file": total, "read_stride": stride}
    if stride > 1:
        cloud.history.append(f"thinned on read: every {stride}th point kept "
                             f"({total} points in the file)")
    return cloud


def _read_pcd(path: Path, max_points: int) -> PointCloud:
    fields: list[str] = []
    meta: dict[str, Any] = {}
    with path.open("rb") as f:
        while True:
            line = f.readline().decode("ascii", errors="replace").strip()
            if not line:
                raise ScanError(f"{path.name}: incomplete PCD header")
            if line.startswith("#"):
                continue
            key, _, rest = line.partition(" ")
            if key == "FIELDS":
                fields = rest.split()
            elif key in ("WIDTH", "HEIGHT", "POINTS", "VIEWPOINT", "VERSION"):
                meta[key.lower()] = rest
            elif key == "DATA":
                if rest.strip().lower() != "ascii":
                    raise ScanError(f"{path.name}: only ASCII PCD files are supported "
                                    f"(this one is '{rest.strip()}'); re-export as ASCII or PLY")
                break
        body = np.loadtxt(f, dtype=float, ndmin=2, max_rows=None)
    if body.size == 0:
        raise ScanError(f"{path.name} contains no points")
    if len(body) > max_points:
        body = body[:: int(np.ceil(len(body) / max_points))]
    parts = _assign(fields or None, body)
    return PointCloud(parts["points"], normals=parts["normals"], colors=parts["colors"],  # type: ignore[arg-type]
                      confidence=parts["confidence"], meta={"pcd": meta})


def read_point_cloud(path: str | Path, units: str | None = None,
                     max_points: int = DEFAULT_MAX_POINTS, sample_seed: int = 0,
                     meta: dict[str, Any] | None = None) -> PointCloud:
    """Read a scan. ``units`` must come from the user or the scanner; it is never guessed."""
    p = Path(path)
    if not p.is_file():
        raise ScanError(f"scan file not found: {p}")
    if p.stat().st_size == 0:
        raise ScanError(f"{p.name} is empty")
    if units is not None:
        length_factor(units)  # validates the unit name
    ext = p.suffix.lower()
    if ext in (".xyz", ".txt", ".pts"):
        cloud = _read_text(p, None, max_points)
    elif ext == ".csv":
        cloud = _read_text(p, ",", max_points)
    elif ext == ".pcd":
        cloud = _read_pcd(p, max_points)
    elif ext in (".ply", ".stl", ".obj"):
        import trimesh

        try:
            obj: Any = trimesh.load(str(p), process=False)
        except Exception as exc:
            raise ScanError(f"cannot read {p.name}: {exc}") from exc
        if isinstance(obj, trimesh.Scene):
            obj = obj.to_geometry() if hasattr(obj, "to_geometry") else obj.dump(concatenate=True)
        if isinstance(obj, trimesh.Trimesh) and len(obj.faces) > 0:
            count = min(max_points, max(20_000, 4 * len(obj.vertices)))
            pts, face = trimesh.sample.sample_surface(obj, count, seed=sample_seed)
            cloud = PointCloud(np.asarray(pts, dtype=float),
                               normals=np.asarray(obj.face_normals[face], dtype=float))
            cloud.history.append(f"sampled {count} points from the mesh surface (seed "
                                 f"{sample_seed}); a mesh is not raw scan data")
        else:
            verts = np.asarray(obj.vertices, dtype=float)
            if len(verts) == 0:
                raise ScanError(f"{p.name} contains no points")
            if len(verts) > max_points:
                verts = verts[:: int(np.ceil(len(verts) / max_points))]
            cloud = PointCloud(verts)
            cols = getattr(obj, "colors", None)
            if cols is not None and len(cols) == len(obj.vertices):
                cloud.colors = np.asarray(cols, dtype=float)[: len(verts), :3]
    else:
        raise ScanError(f"unsupported scan format {ext or '(none)'!r}; supported: .ply, .pcd, "
                        ".xyz, .txt, .csv, .stl, .obj")
    if not np.isfinite(cloud.points).all():
        keep = np.isfinite(cloud.points).all(axis=1)
        cloud = cloud.subset(keep, f"removed {int((~keep).sum())} rows with non-finite values")
    if len(cloud) < 10:
        raise ScanError(f"{p.name}: fewer than 10 valid points")
    cloud.units = units
    cloud.meta |= {"file": p.name, **(meta or {})}
    return cloud


# ---- cleaning ----------------------------------------------------------------------------


def remove_duplicates(cloud: PointCloud, tolerance: float = 1e-9) -> PointCloud:
    scale = max(float(np.ptp(cloud.points, axis=0).max()), 1e-12)
    key = np.round(cloud.points / (tolerance * scale + 1e-300))
    _, first = np.unique(key, axis=0, return_index=True)
    mask = np.zeros(len(cloud), dtype=bool)
    mask[first] = True
    return cloud.subset(mask, f"duplicate removal: {int((~mask).sum())} points dropped")


def remove_outliers(cloud: PointCloud, neighbours: int = 12, sigma: float = 3.0) -> PointCloud:
    """Statistical outlier removal: drop points whose mean neighbour distance is extreme."""
    k = min(neighbours + 1, len(cloud))
    dist, _ = cKDTree(cloud.points).query(cloud.points, k=k)
    mean = dist[:, 1:].mean(axis=1)
    med = float(np.median(mean))
    mad = float(np.median(np.abs(mean - med))) * 1.4826
    mask = mean <= med + sigma * max(mad, 1e-12)
    return cloud.subset(mask, f"outlier filter (k={neighbours}, {sigma} robust sigma): "
                              f"{int((~mask).sum())} points dropped")


def voxel_downsample(cloud: PointCloud, voxel: float) -> PointCloud:
    if voxel <= 0:
        raise ScanError("voxel size must be positive")
    key = np.floor(cloud.points / voxel).astype(np.int64)
    _, first = np.unique(key, axis=0, return_index=True)
    mask = np.zeros(len(cloud), dtype=bool)
    mask[first] = True
    return cloud.subset(mask, f"voxel downsample at {voxel:g}: {int(mask.sum())} points kept")


def estimate_normals(cloud: PointCloud, neighbours: int = 16) -> tuple[Arr, Arr]:
    """Normals by local plane fit, and each point's out-of-plane residual (a noise estimate)."""
    k = min(neighbours, len(cloud))
    _, idx = cKDTree(cloud.points).query(cloud.points, k=k)
    nb = cloud.points[idx] - cloud.points[idx].mean(axis=1, keepdims=True)
    cov = np.einsum("nki,nkj->nij", nb, nb) / k
    w, v = np.linalg.eigh(cov)
    return v[:, :, 0], np.sqrt(np.clip(w[:, 0], 0.0, None))


def noise_estimate(cloud: PointCloud, neighbours: int = 16) -> float:
    """Median local out-of-plane scatter. Curvature inflates it on small radii."""
    return float(np.median(estimate_normals(cloud, neighbours)[1]))
