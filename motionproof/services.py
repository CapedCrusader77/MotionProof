"""Application services shared by the REST API and the CLI (no web or terminal code here)."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import yaml

from motionproof.cad.importers import detect_format, import_file, safe_name
from motionproof.core.schema import Confidence, MechanicalModelSpec
from motionproof.manufacturing.variants import fit_range
from motionproof.model import MechanicalModel, ModelError
from motionproof.persistence.store import Store
from motionproof.tolerances import distributions as D
from motionproof.tolerances.capability import capability, review_tolerances
from motionproof.tolerances.sampling import SamplingMethod, VariableSpace, design_value


def create_reference_model(store: Store, project_id: str) -> dict[str, Any]:
    from motionproof.reference.nema17_arm import write_reference_project

    mid, directory = store.new_model_dir(project_id)
    write_reference_project(directory)
    model = MechanicalModel.load(directory)
    return store.register_model(mid, project_id, model.spec.name, "reference_design", True,
                                directory)


def seed_demo(store: Store) -> bool:
    """Give a brand-new workspace one project holding the synthetic reference design.

    Done once: a marker file stops it coming back after the user deletes the project. Returns
    whether a project was created."""
    marker = store.home / ".demo-seeded"
    if marker.exists():
        return False
    marker.write_text("", encoding="utf-8")
    if store.projects():
        return False
    project = store.create_project(
        "Demo", "The synthetic NEMA 17 planetary joint: open Virtual assemblies or Robustness "
        "to run it.", demo=True)
    create_reference_model(store, project["id"])
    return True


def import_model(store: Store, project_id: str, files: list[Path], name: str | None = None,
                 mesh_units: str | None = None) -> dict[str, Any]:
    """Import a CAD/model file (plus companion mesh files) as a new model."""
    primary = files[0]
    fmt = detect_format(primary.name)
    mid, directory = store.new_model_dir(project_id)
    try:
        inventory = import_file(primary, directory, mesh_units)
        spec: dict[str, Any] = {
            "schema": "motionproof.model/1",
            "name": name or primary.stem,
            "description": f"Imported from {primary.name}",
            "synthetic": False,
            "source": {"kind": "geometry"},
            "fidelity": "F1_geometry_kinematics",
            "assumptions": [],
        }
        if fmt in ("mjcf", "urdf"):
            spec["source"] = {"kind": fmt, "file": f"geometry/{safe_name(primary.name)}"}
            spec["fidelity"] = "F2_reduced_order_dynamics"
        (directory / "model.yaml").write_text(yaml.safe_dump(spec, sort_keys=False),
                                              encoding="utf-8")
        MechanicalModel.load(directory)
    except Exception:
        shutil.rmtree(directory, ignore_errors=True)
        raise
    row = store.register_model(mid, project_id, spec["name"], fmt, False, directory)
    return row | {"inventory": inventory}


def load_model(store: Store, model_id: str) -> MechanicalModel:
    return MechanicalModel.load(Path(store.model(model_id)["directory"]))


def save_spec(store: Store, model_id: str, raw: dict[str, Any]) -> MechanicalModel:
    """Validate and persist an edited specification (the previous file is kept as .bak)."""
    directory = Path(store.model(model_id)["directory"])
    model = MechanicalModel.from_dict(raw, directory)  # validates, compiles dynamics
    if model.mj_model is not None and model.spec.drives:
        _ = model.engine  # checks joint and end-effector references
    path = directory / "model.yaml"
    if path.exists():
        shutil.copy2(path, directory / "model.yaml.bak")
    model.save()
    store.audit("model.update", {"id": model_id, "fingerprint": model.fingerprint})
    return model


def model_detail(store: Store, model_id: str) -> dict[str, Any]:
    row = store.model(model_id)
    model = load_model(store, model_id)
    inv = model.inventory
    return {
        **row,
        "fingerprint": model.fingerprint,
        "geometry_fingerprint": model.geometry_fingerprint(),
        "spec": model.spec.model_dump(mode="json", by_alias=True),
        "components": inv.get("components", []),
        "units": inv.get("units", {}),
        "import_warnings": inv.get("warnings", []),
        "dynamics": inv.get("dynamics"),
        "joints": model.joint_names(),
        "has_dynamics": model.mj_model is not None,
        "source_file": inv.get("source_file"),
    }


def readiness(model: MechanicalModel) -> dict[str, Any]:
    """Model-readiness report: what is in place and what blocks a trustworthy experiment."""
    spec = model.spec
    checks: list[dict[str, str]] = []

    def add(area: str, status: str, message: str) -> None:
        checks.append({"area": area, "status": status, "message": message})

    comps = model.inventory.get("components", [])
    if not comps:
        add("geometry", "error", "no components: the model has no geometry")
    else:
        bad = [c["id"] for c in comps if c.get("valid") is False]
        add("geometry", "warning" if bad else "ok",
            f"{len(comps)} components" + (f"; invalid solids: {bad}" if bad else ", all valid"))
        unknown = [c["id"] for c in comps if c.get("mesh_units") == "unknown"]
        if unknown:
            add("units", "error", f"length unit not stated for {unknown}")
    for w in model.inventory.get("warnings", []):
        add("import", "warning", w)
    if spec.synthetic:
        add("provenance", "info", "synthetic reference design, not measured hardware")
    confirmed = [f for f in spec.features if f.status == "confirmed"]
    add("features", "ok" if confirmed else "error",
        f"{len(confirmed)} confirmed features, "
        f"{len(spec.features) - len(confirmed)} unconfirmed suggestions")
    comp_ids = {c["id"] for c in comps}
    orphan = sorted({f.component for f in spec.features if comp_ids
                     and f.component not in comp_ids})
    if orphan:
        add("features", "warning", f"features refer to components not in the geometry: {orphan}")
    findings = review_tolerances(spec)
    errors = [f for f in findings if f["severity"] == "error"]
    warns = [f for f in findings if f["severity"] == "warning"]
    add("tolerances", "error" if errors else "warning" if warns else "ok",
        f"{len(spec.tolerances)} tolerances; {len(errors)} errors, {len(warns)} warnings")
    assumed = [t.id for t in spec.tolerances if t.confidence == Confidence.ASSUMED]
    if assumed:
        add("tolerances", "warning",
            f"{len(assumed)} of {len(spec.tolerances)} tolerances are assumed values")
    if model.mj_model is None:
        add("dynamics", "warning", "geometry only: no dynamics model, simulation unavailable")
    elif not spec.drives:
        add("dynamics", "error", "no drive defined: configure a motor and gearbox for a joint")
    else:
        try:
            _ = model.engine
            add("dynamics", "ok", f"drives on {sorted(spec.drives)}; model compiles")
        except Exception as exc:
            add("dynamics", "error", str(exc))
        for name, d in spec.drives.items():
            for part, conf in (("motor", d.motor.confidence), ("gearbox", d.gearbox.confidence)):
                if conf == Confidence.ASSUMED:
                    add("mechanics", "warning", f"{name} {part} data are assumed values")
    status = ("blocked" if any(c["status"] == "error" for c in checks)
              else "ready_with_warnings" if any(c["status"] == "warning" for c in checks)
              else "ready")
    return {"status": status, "checks": checks, "tolerance_findings": findings,
            "fidelity": spec.fidelity.value}


def tolerance_review(model: MechanicalModel) -> dict[str, Any]:
    spec = model.spec
    rows = []
    for t in spec.tolerances:
        mean, std = D.mean_std(t.distribution)
        cap = capability(t)
        rows.append({
            "id": t.id, "design_value": design_value(t), "lower_limit": t.lower_limit,
            "upper_limit": t.upper_limit, "mean": mean, "std": std,
            "fraction_out_of_spec": D.fraction_outside(t.distribution, t.lower_limit,
                                                       t.upper_limit),
            "curve": D.density_curve(t.distribution),
            "capability": cap.to_dict() if cap else None,
        })
    return {"review": rows, "findings": review_tolerances(spec),
            "fits": [fit_range(f, spec) for f in spec.fits]}


def generate_variants(model: MechanicalModel, method: SamplingMethod, samples: int,
                      seed: int) -> dict[str, Any]:
    if samples > 500:
        raise ModelError("at most 500 variants can be generated interactively; use an "
                         "experiment for larger sets")
    space = VariableSpace.from_model(model.spec)
    design = space.design(method, samples, seed)
    out = []
    for i, row in enumerate(design.values):
        v = model.variant(dict(zip(design.names, row.tolist(), strict=True)))
        out.append({"id": f"V{i + 1:04d}", **v.to_dict()})
    nominal = model.nominal_variant().to_dict()
    return {"method": design.method, "seed": seed, "note": design.note, "nominal": nominal,
            "variants": out}


def variant_detail(model: MechanicalModel, values: dict[str, float]) -> dict[str, Any]:
    """One manufactured variant: derived quantities plus Level A geometry where available."""
    variant = model.variant(values)
    nominal = model.nominal_variant()
    deviations = []
    for t in model.spec.tolerances:
        actual, base = variant.values[t.id], nominal.values[t.id]
        if abs(actual - base) > 0:
            span = (t.upper - t.lower) or 1.0
            deviations.append({
                "tolerance": t.id, "component": t.component, "feature": t.feature,
                "parameter": t.parameter, "unit": t.unit, "nominal": base, "actual": actual,
                "deviation": actual - base, "zone_fraction": (actual - t.lower_limit) / span,
                "in_spec": t.lower_limit - 1e-12 <= actual <= t.upper_limit + 1e-12})
    geometry = None
    if model.spec.source.kind == "reference_design":
        from motionproof.reference.nema17_arm import measure_variant_geometry

        geometry = measure_variant_geometry(variant.values)
    return {"variant": variant.to_dict(), "nominal": nominal.to_dict(),
            "deviations": sorted(deviations, key=lambda d: -abs(d["zone_fraction"] - 0.5)),
            "geometry": geometry,
            "levels_note": "A = regenerated parametric geometry measured with OpenCascade; "
                           "C = reduced-order relation (geometry not regenerated)"}


def edit_spec(store: Store, model_id: str, mutate: Any) -> MechanicalModel:
    model = load_model(store, model_id)
    raw = model.spec.model_dump(mode="json", by_alias=True, exclude_none=True)
    mutate(raw)
    MechanicalModelSpec.model_validate(raw)
    return save_spec(store, model_id, raw)
