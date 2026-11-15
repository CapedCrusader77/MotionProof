"""CAD and model import: STEP, STL, OBJ, URDF and MJCF.

Every importer writes viewer meshes (one STL per component) plus an ``inventory.json`` into
the model directory and returns the inventory. Original files are copied, never modified.
Units are reported as found; mesh formats carry no unit and are marked ``unknown`` until the
user states one.
"""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Any

import numpy as np
import trimesh

from motionproof.cad.geometry import GeometryError, analyse_mesh, file_sha256, load_mesh
from motionproof.core.units import length_factor

SUPPORTED = {".step": "step", ".stp": "step", ".stl": "stl", ".obj": "obj", ".urdf": "urdf",
             ".xml": "mjcf", ".mjcf": "mjcf"}
MAX_UPLOAD_BYTES = 300 * 1024 * 1024


class ImportFailure(ValueError):
    """An import problem with a message the user can act on."""


def safe_name(name: str) -> str:
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(name).name).strip("._")
    if not stem:
        raise ImportFailure("file name contains no usable characters")
    return stem[:120]


def detect_format(filename: str) -> str:
    ext = Path(filename).suffix.lower()
    if ext not in SUPPORTED:
        raise ImportFailure(f"unsupported file type {ext or '(none)'!r}; supported: "
                            f"{', '.join(sorted(SUPPORTED))}")
    return SUPPORTED[ext]


def _duplicates(components: list[dict[str, Any]]) -> list[str]:
    seen: dict[tuple[float, ...], str] = {}
    warnings = []
    for c in components:
        if c.get("volume_mm3") is None or c.get("bbox") is None:
            continue
        key = (round(c["volume_mm3"], 3), *np.round(np.ravel(c["bbox"]), 3))
        if key in seen:
            warnings.append(f"{c['id']} occupies exactly the same space as {seen[key]}: "
                            "possible duplicate geometry")
        else:
            seen[key] = c["id"]
    return warnings


def _import_step(src: Path, out: Path) -> dict[str, Any]:
    import cadquery as cq

    from motionproof.cad.features import cylindrical_features

    try:
        shape = cq.importers.importStep(str(src))
    except Exception as exc:
        raise ImportFailure(f"OpenCascade could not read {src.name}: {exc}. Check that the "
                            "file is a complete STEP AP203/AP214/AP242 export.") from exc
    from motionproof.cad.features import solids_of

    solids = solids_of(shape)
    if not solids:
        raise ImportFailure(f"{src.name} contains no solid bodies (surfaces or wireframe only). "
                            "Export solids from the CAD system.")
    names: list[str] = []
    try:  # assembly part names, when the file carries an assembly structure
        assy = cq.Assembly.importStep(str(src))
        names = [n for n, sub in assy.traverse() if sub.obj is not None]
    except Exception:
        names = []
    components, warnings, suggestions = [], [], {}
    for i, solid in enumerate(solids):
        cid = f"solid_{i + 1:03d}"
        label = names[i] if len(names) == len(solids) else cid
        valid = bool(solid.isValid())
        vol = float(solid.Volume())
        bb = solid.BoundingBox()
        com = cq.Shape.centerOfMass(solid)
        mesh_file = f"meshes/{cid}.stl"
        solid.exportStl(str(out / mesh_file), 0.02, 0.2)
        if not valid:
            warnings.append(f"{label}: OpenCascade reports an invalid solid")
        if vol <= 0:
            warnings.append(f"{label}: volume is not positive")
        components.append({
            "id": cid, "name": label, "body": "world", "group": "imported", "mesh": mesh_file,
            "mesh_units": "mm", "valid": valid, "volume_mm3": vol, "area_mm2": float(solid.Area()),
            "bbox": [[bb.xmin, bb.ymin, bb.zmin], [bb.xmax, bb.ymax, bb.zmax]],
            "com_mm": [com.x, com.y, com.z], "mass_kg": None, "density_kg_m3": None,
            "source": f"STEP solid {i + 1} of {src.name}"})
        try:
            suggestions[cid] = cylindrical_features(solid, min_radius=0.25)[:40]
        except Exception as exc:  # feature detection must never block an import
            warnings.append(f"{label}: feature detection failed ({exc})")
    if len(names) != len(solids):
        warnings.append("component names could not be matched to solids; generic names used")
    warnings.append("mass is undefined until a material density is assigned (STEP geometry "
                    "carries no reliable density)")
    warnings.append("STEP has no feature history: detected cylinders are suggestions to confirm")
    return {"format": "step", "units": {"geometry": "mm", "note": "OpenCascade converts STEP "
            "lengths to millimetres using the units declared in the file"},
            "components": components, "feature_suggestions": suggestions,
            "warnings": warnings + _duplicates(components), "dynamics": None}


def _import_mesh(src: Path, out: Path, fmt: str, units: str | None) -> dict[str, Any]:
    try:
        mesh = load_mesh(src)
    except GeometryError as exc:
        raise ImportFailure(str(exc)) from exc
    rep = analyse_mesh(mesh, src.name)
    mesh_file = f"meshes/{safe_name(src.stem)}.stl"
    mesh.export(str(out / mesh_file))
    warnings = list(rep.issues)
    scale_mm = None
    if units is None:
        warnings.append(f"{fmt.upper()} files carry no length unit. State the unit before "
                        "using dimensions; nothing has been scaled or assumed.")
    else:
        scale_mm = length_factor(units) * 1000.0
    comp = {"id": "mesh_001", "name": src.stem, "body": "world", "group": "imported",
            "mesh": mesh_file, "mesh_units": units or "unknown", "valid": rep.solid,
            "volume_mm3": None if rep.volume is None or scale_mm is None
            else rep.volume * scale_mm**3,
            "volume_native": rep.volume, "area_native": rep.area,
            "bbox": [rep.bbox_min, rep.bbox_max], "triangles": rep.triangles,
            "watertight": rep.watertight, "winding_consistent": rep.winding_consistent,
            "mass_kg": None, "density_kg_m3": None, "source": f"{fmt.upper()} mesh {src.name}"}
    warnings.append("a mesh file is geometry only: no assembly structure, joints or features")
    return {"format": fmt, "units": {"geometry": units or "unknown"}, "components": [comp],
            "feature_suggestions": {}, "warnings": warnings, "dynamics": None}


def _geom_mesh(model: Any, gid: int) -> trimesh.Trimesh | None:
    import mujoco

    gtype, size = int(model.geom_type[gid]), model.geom_size[gid]
    if gtype == mujoco.mjtGeom.mjGEOM_MESH:
        mid = int(model.geom_dataid[gid])
        v0, nv = int(model.mesh_vertadr[mid]), int(model.mesh_vertnum[mid])
        f0, nf = int(model.mesh_faceadr[mid]), int(model.mesh_facenum[mid])
        return trimesh.Trimesh(model.mesh_vert[v0:v0 + nv].copy(),
                               model.mesh_face[f0:f0 + nf].copy(), process=False)
    if gtype == mujoco.mjtGeom.mjGEOM_BOX:
        box: trimesh.Trimesh = trimesh.creation.box(extents=2 * size)
        return box
    if gtype == mujoco.mjtGeom.mjGEOM_SPHERE:
        sphere: trimesh.Trimesh = trimesh.creation.icosphere(radius=float(size[0]),
                                                             subdivisions=2)
        return sphere
    if gtype == mujoco.mjtGeom.mjGEOM_CYLINDER:
        cyl: trimesh.Trimesh = trimesh.creation.cylinder(radius=float(size[0]),
                                                         height=2 * float(size[1]))
        return cyl
    if gtype == mujoco.mjtGeom.mjGEOM_CAPSULE:
        cap: trimesh.Trimesh = trimesh.creation.capsule(radius=float(size[0]),
                                                        height=2 * float(size[1]))
        return cap
    if gtype == mujoco.mjtGeom.mjGEOM_ELLIPSOID:
        m: Any = trimesh.creation.icosphere(radius=1.0, subdivisions=2)
        m.apply_scale(size)
        ell: trimesh.Trimesh = m
        return ell
    return None  # planes and height fields are not exported


def _import_mujoco(src: Path, out: Path, fmt: str) -> dict[str, Any]:
    import mujoco

    from motionproof.core.transforms import make_transform, quat_to_matrix

    try:
        model = mujoco.MjModel.from_xml_path(str(src))
    except ValueError as exc:
        raise ImportFailure(
            f"MuJoCo could not compile {src.name}: {exc}. Mesh files referenced by the model "
            "must be uploaded next to it.") from exc
    components, warnings = [], []
    for body in range(1, model.nbody):
        name = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_BODY, body) or f"body_{body}"
        parts = []
        for gid in range(model.ngeom):
            if int(model.geom_bodyid[gid]) != body:
                continue
            mesh = _geom_mesh(model, gid)
            if mesh is None:
                continue
            mesh.apply_transform(make_transform(quat_to_matrix(model.geom_quat[gid]),
                                                model.geom_pos[gid]))
            parts.append(mesh)
        mesh_file = None
        if parts:
            mesh_file = f"meshes/{safe_name(name)}.stl"
            merged: Any = trimesh.util.concatenate(parts)
            merged.apply_scale(1000.0)  # viewer meshes are stored in millimetres
            merged.export(str(out / mesh_file))
        else:
            warnings.append(f"body {name!r} has no exportable geometry (it will not be drawn)")
        components.append({"id": name, "name": name, "body": name, "group": "body",
                           "mesh": mesh_file, "mesh_units": "mm", "valid": True,
                           "mass_kg": float(model.body_mass[body]),
                           "com_m": model.body_ipos[body].tolist(),
                           "inertia_principal_kgm2": model.body_inertia[body].tolist(),
                           "body_frame": True, "source": f"{fmt.upper()} body in {src.name}"})
    joints = []
    kinds = {0: "free", 1: "ball", 2: "prismatic", 3: "revolute"}
    for j in range(model.njnt):
        joints.append({
            "name": mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_JOINT, j) or f"joint_{j}",
            "type": kinds[int(model.jnt_type[j])],
            "body": mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_BODY,
                                      int(model.jnt_bodyid[j])),
            "axis": model.jnt_axis[j].tolist(), "pos": model.jnt_pos[j].tolist(),
            "limited": bool(model.jnt_limited[j]), "range": model.jnt_range[j].tolist()})
    if not joints:
        warnings.append("the model has no joints: nothing can be actuated")
    return {"format": fmt, "units": {"geometry": "mm (converted from SI for display)",
                                     "dynamics": "SI"},
            "components": components, "feature_suggestions": {}, "warnings": warnings,
            "dynamics": {"file": src.name, "bodies": model.nbody - 1, "joints": joints,
                         "total_mass_kg": float(model.body_mass.sum())}}


def import_file(source: str | Path, model_dir: str | Path,
                mesh_units: str | None = None) -> dict[str, Any]:
    """Import ``source`` into ``model_dir``; returns the written inventory."""
    src = Path(source)
    out = Path(model_dir)
    if not src.is_file():
        raise ImportFailure(f"file not found: {src}")
    if src.stat().st_size == 0:
        raise ImportFailure(f"{src.name} is empty")
    if src.stat().st_size > MAX_UPLOAD_BYTES:
        raise ImportFailure(f"{src.name} exceeds the {MAX_UPLOAD_BYTES >> 20} MB limit")
    fmt = detect_format(src.name)
    geo = out / "geometry"
    (geo / "meshes").mkdir(parents=True, exist_ok=True)
    (out / "original").mkdir(parents=True, exist_ok=True)
    original = out / "original" / safe_name(src.name)
    if original.resolve() != src.resolve():
        shutil.copy2(src, original)
    if fmt == "step":
        inv = _import_step(original, geo)
    elif fmt in ("stl", "obj"):
        inv = _import_mesh(original, geo, fmt, mesh_units)
    else:
        work = geo / safe_name(src.name)
        shutil.copy2(src, work)
        for extra in src.parent.iterdir():  # meshes referenced by the model
            if extra.suffix.lower() in {".stl", ".obj", ".msh"} and extra.is_file():
                shutil.copy2(extra, geo / extra.name)
        inv = _import_mujoco(work, geo, fmt)
    inv |= {"source_file": src.name, "source_sha256": file_sha256(original), "synthetic": False,
            "geometry_processing": "motionproof.cad.importers/1"}
    (geo / "inventory.json").write_text(json.dumps(inv, indent=1), encoding="utf-8")
    return inv


def inspect_file(source: str | Path, workdir: str | Path) -> dict[str, Any]:
    """Import into a scratch directory and return a compact summary (CLI ``inspect``)."""
    inv = import_file(source, workdir)
    return {"file": inv["source_file"], "format": inv["format"], "units": inv["units"],
            "sha256": inv["source_sha256"], "component_count": len(inv["components"]),
            "components": [{k: c.get(k) for k in ("id", "name", "valid", "volume_mm3",
                                                   "mass_kg", "bbox")}
                           for c in inv["components"]],
            "suggested_features": {k: len(v) for k, v in inv["feature_suggestions"].items()},
            "dynamics": inv["dynamics"], "warnings": inv["warnings"]}
