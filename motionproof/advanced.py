"""Services for the advanced subsystems, shared by the REST API and the CLI.

Every function reads the one ``MechanicalModel`` and writes a stored artifact recording the
model fingerprint it used, so results stay tied to the model revision that produced them.
"""

from __future__ import annotations

import json
import shutil
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal

import numpy as np
from pydantic import BaseModel, ConfigDict, Field

from motionproof import services
from motionproof.core.schema import Confidence
from motionproof.core.units import length_factor
from motionproof.experiments.runner import (
    Constraint,
    Experiment,
    ExperimentConfig,
    evaluate_scenario,
)
from motionproof.model import MechanicalModel
from motionproof.persistence.store import NotFound, Store
from motionproof.tolerances.sampling import VariableSpace

Progress = Callable[[dict[str, Any]], None] | None


class _M(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _model_ref(model: MechanicalModel) -> dict[str, Any]:
    return {"name": model.spec.name, "fingerprint": model.fingerprint,
            "synthetic": model.spec.synthetic}


# =========================================================================== scans


class CylinderRequest(_M):
    """Measure one cylindrical feature: nominal axis and radius in the nominal frame (mm)."""

    feature: str | None = None
    tolerance: str | None = None
    axis_point: tuple[float, float, float]
    axis_direction: tuple[float, float, float]
    radius: float = Field(gt=0)
    band: float = Field(default=0.3, gt=0)
    start: float | None = None
    length: float | None = None
    datum_point: tuple[float, float, float] | None = None
    datum_direction: tuple[float, float, float] | None = None


class RegisterRequest(_M):
    component: str | None = None  # nominal = this component's mesh
    method: Literal["point_to_point", "point_to_plane"] = "point_to_plane"
    lock: list[str] = Field(default_factory=list)
    accept_rms: float | None = Field(default=None, gt=0)
    initial: Literal["principal_axes", "identity"] = "principal_axes"
    outlier_sigma: float | None = Field(default=3.0, gt=0)
    voxel: float | None = Field(default=None, gt=0)


def _nominal_for(model: MechanicalModel, component: str | None) -> Any:
    from motionproof.scans.registration import Nominal

    comps = model.inventory.get("components", [])
    chosen = [c for c in comps if c.get("mesh") and (component is None or c["id"] == component)]
    if not chosen:
        raise NotFound(f"component {component!r} has no mesh" if component else
                       "the model has no meshes")
    import trimesh

    meshes = []
    for c in chosen:
        mesh = trimesh.load(str(model.geometry_dir / c["mesh"]), force="mesh", process=False)
        if c.get("mesh_units") not in ("mm", None):
            raise ValueError(f"component {c['id']} mesh is in {c['mesh_units']}, not mm")
        meshes.append(mesh)
    return Nominal.from_mesh(trimesh.util.concatenate(meshes), component or "assembly",
                             count=150_000, seed=0)


def scan_import(store: Store, model_id: str, file: Path, units: str | None,
                meta: dict[str, Any] | None = None, synthetic: bool = False) -> dict[str, Any]:
    from motionproof.scans.pointcloud import read_point_cloud

    row = store.model(model_id)
    cloud = read_point_cloud(file, units=units, meta=meta)
    aid, d = store.new_artifact("scan", row["project_id"], file.name, model_id)
    shutil.copy2(file, d / f"original{file.suffix.lower()}")
    np.savez_compressed(d / "points.npz", points=cloud.points,
                        normals=cloud.normals if cloud.normals is not None else np.zeros(0))
    summary = cloud.summary() | {"synthetic": synthetic or "synthetic" in file.name.lower()}
    store.save_json(aid, "scan", summary)
    store.update_artifact(aid, "imported", {"points": len(cloud), "units": units,
                                            "synthetic": summary["synthetic"]})
    return {"id": aid, **summary}


def _load_cloud(store: Store, scan_id: str) -> Any:
    from motionproof.scans.pointcloud import PointCloud

    art = store.artifact(scan_id)
    meta = store.load_json(scan_id, "scan")
    data = np.load(Path(art["directory"]) / "points.npz")
    normals = data["normals"] if data["normals"].size else None
    return PointCloud(data["points"], meta["units"], normals, meta=meta["meta"],
                      history=list(meta["history"]))


def scan_register(store: Store, scan_id: str, req: RegisterRequest) -> dict[str, Any]:
    from motionproof.scans import pointcloud as P
    from motionproof.scans import registration as R

    art = store.artifact(scan_id)
    model = services.load_model(store, art["model_id"])
    cloud = _load_cloud(store, scan_id)
    cloud = P.remove_duplicates(cloud)
    if req.outlier_sigma is not None:
        cloud = P.remove_outliers(cloud, sigma=req.outlier_sigma)
    if req.voxel is not None:
        cloud = P.voxel_downsample(cloud, req.voxel)
    pts = cloud.in_mm()
    nominal = _nominal_for(model, req.component)
    init = R.coarse_align(pts, nominal) if req.initial == "principal_axes" else None
    reg = R.icp(pts, nominal, req.method, init=init, lock=tuple(req.lock),
                noise=P.noise_estimate(cloud) * (length_factor(cloud.units or "mm") * 1000.0),
                accept_rms=req.accept_rms)
    out = {"scan": scan_id, "component": req.component, "request": req.model_dump(),
           "processing": cloud.history, "points_used": len(cloud),
           "registration": reg.to_dict(), "model": _model_ref(model)}
    np.savez_compressed(Path(art["directory"]) / "aligned.npz", points=reg.apply(pts))
    store.save_json(scan_id, "registration", out)
    store.update_artifact(scan_id, "registered", {
        "points": len(cloud), "rms": reg.rms, "valid_for_inspection": reg.valid_for_inspection})
    return out


def scan_analyse(store: Store, scan_id: str, limit: float | None,
                 cylinders: list[CylinderRequest]) -> dict[str, Any]:
    from motionproof.scans import inspection as I

    art = store.artifact(scan_id)
    reg = store.load_json(scan_id, "registration")
    model = services.load_model(store, art["model_id"])
    aligned = np.load(Path(art["directory"]) / "aligned.npz")["points"]
    nominal = _nominal_for(model, reg["component"])
    dev = I.deviation(aligned, nominal, limit)
    valid = reg["registration"]["valid_for_inspection"]
    measured = []
    for i, c in enumerate(cylinders, start=1):
        mask = I.select_near_cylinder(aligned, np.array(c.axis_point),
                                      np.array(c.axis_direction), c.radius, c.band, c.start,
                                      c.length)
        if mask.sum() < 12:
            measured.append({"id": f"{scan_id}-M{i}", "feature": c.feature, "status":
                             "rejected", "notes": [f"only {int(mask.sum())} points near the "
                                                   "nominal surface"]})
            continue
        fit = I.fit_cylinder(aligned[mask], np.array(c.axis_direction))
        notes = list(fit.warnings)
        if not valid:
            notes.append("registration was not accepted for inspection: value is not usable")
        m = I.MeasuredFeature(f"{scan_id}-M{i}", c.feature, "diameter", fit.diameter, "mm",
                              fit.diameter_std_error, "least-squares cylinder fit",
                              scan_id, f"{scan_id} registration", "pending" if valid
                              else "rejected", c.tolerance, notes)
        entry = m.to_dict() | {"fit": fit.to_dict(), "points": int(mask.sum())}
        if c.datum_point and c.datum_direction:
            entry["axis_offset"] = I.axis_offset(fit, np.array(c.datum_point),
                                                 np.array(c.datum_direction))
        measured.append(entry)
    out = {"scan": scan_id, "deviation": dev, "measured": measured,
           "inspection_valid": valid,
           "scope": "fitted-geometry measurement; not a standards-conformant GD&T inspection"}
    store.save_json(scan_id, "analysis", out)
    store.update_artifact(scan_id, "analysed", {
        "points": len(aligned), "rms": dev["rms"],
        "coverage": dev["coverage"]["fraction_of_nominal_surface"],
        "measured": len(measured), "valid_for_inspection": valid})
    return out


def measurement_decision(store: Store, scan_id: str, measurement_id: str,
                         status: Literal["approved", "rejected"]) -> dict[str, Any]:
    out = store.load_json(scan_id, "analysis")
    for m in out["measured"]:
        if m["id"] == measurement_id:
            if status == "approved" and not out["inspection_valid"]:
                raise ValueError("the registration was not accepted for inspection; "
                                 "measurements from it cannot be approved")
            m["status"] = status
            store.save_json(scan_id, "analysis", out)
            store.audit("scan.measurement", {"id": measurement_id, "status": status})
            entry: dict[str, Any] = m
            return entry
    raise NotFound(f"measurement {measurement_id!r} not found")


def as_built(store: Store, model_id: str) -> dict[str, Any]:
    """Approved scan measurements of this model, turned into an as-built variant."""
    from motionproof.scans.inspection import MeasuredFeature, as_built_values

    model = services.load_model(store, model_id)
    measured: list[MeasuredFeature] = []
    for a in store.artifacts("scan", model_id=model_id):
        try:
            out = store.load_json(a["id"], "analysis")
        except NotFound:
            continue
        for m in out["measured"]:
            if "quantity" in m:
                measured.append(MeasuredFeature(**{k: m[k] for k in (
                    "id", "feature", "quantity", "value", "unit", "uncertainty", "method",
                    "scan", "registration", "status", "tolerance", "notes")}))
    built = as_built_values(model.spec, measured)
    variant = model.variant(built["values"]) if built["values"] else None
    return built | {"variant": variant.to_dict() if variant else None,
                    "model": _model_ref(model)}


# =========================================================================== process


def process_batch(store: Store, model_id: str, process: dict[str, Any], plan: dict[str, Any],
                  name: str = "batch") -> dict[str, Any]:
    from motionproof.manufacturing.variants import resolve_variant
    from motionproof.process.model import (
        BatchPlan,
        ProcessModel,
        batch_summary,
        control_chart,
        generate_batch,
        variance_components,
    )

    model = services.load_model(store, model_id)
    pm, bp = ProcessModel.model_validate(process), BatchPlan.model_validate(plan)
    known = {t.id for t in model.spec.tolerances}
    unknown = {f.feature for f in pm.features} - known
    if unknown:
        raise KeyError(f"process features must be tolerance ids of the model: {sorted(unknown)}")
    batch = generate_batch(pm, bp)
    summary = batch_summary(pm, batch)
    base = services.load_model(store, model_id).spec
    from motionproof.manufacturing.variants import nominal_values

    nominal = nominal_values(base)
    n = batch["parts"]
    step = max(1, n // 2000)
    assemblies: dict[str, Any] = {"evaluated": 0, "violations": {}, "fits": {}}
    for i in range(0, n, step):
        vals = nominal | {k: float(v[i]) for k, v in batch["actual"].items()}
        v = resolve_variant(base, vals)
        assemblies["evaluated"] += 1
        for x in v.violations:
            assemblies["violations"][x["category"]] = \
                assemblies["violations"].get(x["category"], 0) + 1
        for fr in v.fits:
            assemblies["fits"].setdefault(fr.fit, []).append(fr.clearance)
    fits = {k: {"mean": float(np.mean(c)), "std": float(np.std(c)), "min": float(np.min(c)),
                "max": float(np.max(c)), "interference_fraction": float(np.mean(np.array(c) < 0))}
            for k, c in assemblies["fits"].items()}
    vc: dict[str, Any] = {}
    charts: dict[str, Any] = {}
    for f in pm.features:
        x = batch["actual"][f.feature]
        try:
            vc[f.feature] = variance_components(x, batch["batch"], batch["setup"])
        except ValueError as exc:
            vc[f.feature] = {"error": str(exc)}
        try:
            charts[f.feature] = control_chart(batch["measured"][f.feature][:5000],
                                              5 if n >= 25 else 2)
        except ValueError as exc:
            charts[f.feature] = {"error": str(exc)}
    feats = list(batch["actual"])
    corr = np.corrcoef(np.vstack([batch["actual"][k] for k in feats])).tolist() \
        if len(feats) > 1 else [[1.0]]
    rows = {k: v[::step].tolist() for k, v in batch["actual"].items()}
    row = store.model(model_id)
    aid, _ = store.new_artifact("batch", row["project_id"], name, model_id)
    out = {"id": aid, "process": pm.model_dump(), "plan": bp.model_dump(), "parts": n,
           "summary": summary, "variance_components": vc, "control_charts": charts,
           "correlation": {"features": feats, "matrix": corr},
           "assemblies": {"evaluated": assemblies["evaluated"],
                          "violations": assemblies["violations"], "fits": fits},
           "samples": rows, "model": _model_ref(model),
           "label": "virtual batch from the stated process model; not production data"}
    store.save_json(aid, "batch", out)
    store.update_artifact(aid, "generated", {"parts": n, "violations": assemblies["violations"]})
    return out


# =========================================================================== adaptive


class AdaptiveRequest(_M):
    model_id: str
    config: ExperimentConfig
    initial: int = Field(default=30, ge=4, le=2000)
    budget: int = Field(default=150, ge=4, le=20_000)
    population: int = Field(default=5000, ge=100, le=200_000)
    max_seconds: float | None = Field(default=None, gt=0)
    seed: int = 0


def adaptive_run(store: Store, req: AdaptiveRequest, progress: Progress = None,
                 cancel: threading.Event | None = None) -> dict[str, Any]:
    from motionproof.adaptive.sampler import run_adaptive

    if not req.config.constraints:
        raise ValueError("adaptive sampling needs at least one constraint (the limit state)")
    model = services.load_model(store, req.model_id)
    cfg = req.config
    space = VariableSpace.from_model(model.spec, cfg.operating)
    names = space.names
    records: list[dict[str, Any]] = []

    def limit_state(x: np.ndarray) -> float:
        row = dict(zip(names, x.tolist(), strict=True))
        res = evaluate_scenario(model, cfg, row)
        margin = min((c["margin"] for c in res["constraints"].values()), default=-1.0) \
            if res["valid"] else -1.0
        if any(f["severity"] == "assembly_violation" for f in res["failures"]):
            margin = min(margin, -1e-3)
        records.append({"values": row, "passed": res["passed"], "valid": res["valid"],
                        "margin": margin, "metrics": res["metrics"]})
        return float(margin)

    def population(n: int, seed: int) -> np.ndarray:
        return space.design("monte_carlo", n, seed).values

    out = run_adaptive(limit_state, population, space.bounds(), initial=req.initial,
                       budget=req.budget, population=req.population, seed=req.seed,
                       max_seconds=req.max_seconds, progress=progress,
                       should_stop=(lambda: cancel.is_set()) if cancel else None)
    out |= {"variables": names, "constraints": [c.model_dump() for c in cfg.constraints],
            "task": cfg.task.model_dump(), "model": _model_ref(model),
            "limit_state": "minimum normalised constraint margin (assembly violations count as "
                           "failures); negative = fail",
            "simulated": records}
    row = store.model(req.model_id)
    aid, _ = store.new_artifact("adaptive", row["project_id"], cfg.name, req.model_id)
    out["id"] = aid
    store.save_json(aid, "adaptive", out)
    store.update_artifact(aid, "completed", {"simulations": out["simulations"],
                                             "predicted_failure_fraction":
                                                 out["surrogate"]["predicted_failure_fraction"],
                                             "stopping_reason": out["stopping_reason"]})
    return out


# =========================================================================== workspace


class WorkspaceRequest(_M):
    model_id: str
    grid: dict[str, list[float]]
    samples: int = Field(default=30, ge=1, le=2000)
    seed: int = 0
    source: Literal["nominal", "virtual", "as_built"] = "virtual"
    position_tolerance: float | None = Field(default=None, gt=0)
    payload_mass: float = Field(default=0.0, ge=0)
    verify_poses: int = Field(default=0, ge=0, le=20)
    scales: dict[str, float] = Field(default_factory=dict, description="improved design")


def workspace_run(store: Store, req: WorkspaceRequest) -> dict[str, Any]:
    from motionproof.optimisation.allocation import scaled_spec
    from motionproof.workspace.maps import reliability_map, verify_pose

    model = services.load_model(store, req.model_id)
    if req.scales:
        model = MechanicalModel(scaled_spec(model.spec, req.scales), model.directory)
    space = VariableSpace.from_model(model.spec)
    nominal = dict(zip(space.names, space.nominal().tolist(), strict=True))
    independent = True
    if req.source == "nominal":
        rows, independent = [nominal], False
    elif req.source == "as_built":
        built = as_built(store, req.model_id)
        if not built["values"]:
            raise ValueError("no approved scan measurements exist for this model")
        rows, independent = [nominal | built["values"]], False
    else:
        rows = [dict(zip(space.names, r.tolist(), strict=True))
                for r in space.design("monte_carlo", req.samples, req.seed).values]
    out = reliability_map(model, req.grid, rows, req.position_tolerance, req.payload_mass,
                          independent)
    driven = set(model.spec.drives)
    held = model.spec.held_joints

    def verifiable(c: dict[str, Any]) -> bool:
        # Level 2 can only move driven joints; held joints must sit at their held angle
        return c["reachable"] and all(abs(v - held.get(k, v)) < 1e-12
                                      for k, v in c["pose"].items() if k not in driven)

    picks = sorted((c for c in out["cells"] if verifiable(c)),
                   key=lambda c: -c["error_rms"])[: req.verify_poses]
    out["verification"] = []
    for c in picks:
        pose = {k: v for k, v in c["pose"].items() if k in driven}
        v = verify_pose(model, pose, rows[: min(len(rows), 20)], req.payload_mass)
        out["verification"].append(v | {"pose": c["pose"], "map_error_rms": c["error_rms"]})
    if req.verify_poses and not picks:
        out["verification_note"] = ("no pose can be checked at Level 2: every pose moves a held "
                                    "joint away from its held angle")
    out |= {"source": req.source, "samples": len(rows), "scales": req.scales,
            "model": _model_ref(model)}
    row = store.model(req.model_id)
    aid, _ = store.new_artifact("workspace", row["project_id"], f"workspace {req.source}",
                                req.model_id)
    out["id"] = aid
    store.save_json(aid, "workspace", out)
    store.update_artifact(aid, "completed", {"cells": len(out["cells"]), "source": req.source})
    return out


# =========================================================================== degradation


class DegradationRequest(_M):
    model_id: str
    mechanisms: list[dict[str, Any]] = Field(min_length=1)
    cycles: list[float] = Field(min_length=2)
    constraints: list[Constraint] = Field(min_length=1)
    pose: dict[str, float] | None = None
    task: dict[str, Any] | None = None
    payload_mass: float = Field(default=0.0, ge=0)
    inspect_every: float | None = Field(default=None, gt=0)
    name: str = "degradation"


def degradation_run(store: Store, req: DegradationRequest) -> dict[str, Any]:
    from pydantic import TypeAdapter

    from motionproof.degradation.model import Mechanism, compare_maintenance, lifetime_experiment
    from motionproof.simulation.tasks import Task

    model = services.load_model(store, req.model_id)
    task = TypeAdapter(Task).validate_python(req.task) if req.task else None
    out = lifetime_experiment(model, [Mechanism.model_validate(m) for m in req.mechanisms],
                              req.cycles, req.constraints, task=task, pose=req.pose,
                              payload_mass=req.payload_mass)
    if req.inspect_every:
        out["maintenance"] = {c.name: compare_maintenance(out, c.name, req.inspect_every)
                              for c in req.constraints}
    out["model"] = _model_ref(model)
    row = store.model(req.model_id)
    aid, _ = store.new_artifact("degradation", row["project_id"], req.name, req.model_id)
    out["id"] = aid
    store.save_json(aid, "degradation", out)
    store.update_artifact(aid, "completed", {"crossings": out["threshold_crossings"]})
    return out


# =========================================================================== hardware


class HardwareRequest(_M):
    model_id: str
    device: str = "simulated"
    test: dict[str, Any]
    limits: dict[str, Any]
    confirm_actuation: bool = False
    simulated_truth: dict[str, float] = Field(default_factory=dict)
    simulated_noise: float = Field(default=0.0, ge=0)
    simulated_faults: dict[str, Any] = Field(default_factory=dict)
    seed: int = 0


def hardware_run(store: Store, req: HardwareRequest) -> dict[str, Any]:
    from motionproof.hardware.device import (
        HardwareTest,
        SafetyLimits,
        SerialDevice,
        SimulatedDevice,
        compare_with_simulation,
        run_test,
    )

    model = services.load_model(store, req.model_id)
    test, limits = HardwareTest.model_validate(req.test), SafetyLimits.model_validate(req.limits)
    if test.joint not in model.spec.drives:
        raise KeyError(f"joint {test.joint!r} has no drive in this model")
    if req.device == "simulated":
        dev: Any = SimulatedDevice(model, req.simulated_truth, noise=req.simulated_noise,
                                   seed=req.seed, faults=req.simulated_faults)
    else:
        dev = SerialDevice(req.device)
    session = run_test(dev, test, limits, confirm_actuation=req.confirm_actuation)
    row = store.model(req.model_id)
    aid, d = store.new_artifact("hardware", row["project_id"], f"{session.source} "
                                f"{test.kind}", req.model_id)
    session.write_csv(d / "measurements.csv")
    out: dict[str, Any] = {"id": aid, **session.summary(),
                           "truth": req.simulated_truth if req.device == "simulated" else None,
                           "model": _model_ref(model)}
    if session.status in ("completed", "aborted") and len(session.samples) >= 10:
        out["comparison"] = compare_with_simulation(session, model)
    step = max(1, len(session.samples) // 1500)
    out["series"] = {k: [s[k] for s in session.samples[::step]]
                     for k in ("t_us", "command_rad", "input_angle_rad", "output_angle_rad")}
    store.save_json(aid, "session", out)
    store.update_artifact(aid, session.status, {"source": session.source,
                                                "samples": len(session.samples),
                                                "abort_reason": session.abort_reason})
    return out


# =========================================================================== root cause / fidelity


def rootcause_run(store: Store, experiment_id: str, scenario: str) -> dict[str, Any]:
    from motionproof.rootcause.analysis import investigate

    row = store.experiment(experiment_id)
    exp = Experiment.open(row["directory"])
    out = investigate(exp, scenario)
    stored = next(r for r in exp.results() if r["id"] == scenario)
    replay = evaluate_scenario(exp.model(), exp.config, exp.row(stored["index"]),
                               keep_trace=True)
    out |= {"experiment": experiment_id, "trace": replay.get("trace"),
            "values": stored["values"], "variant": replay.get("variant"),
            "constraints": stored["constraints"], "metrics": stored["metrics"]}
    aid, _ = store.new_artifact("rootcause", row["project_id"], f"{experiment_id} {scenario}",
                                row["model_id"], experiment_id)
    out["id"] = aid
    store.save_json(aid, "rootcause", out)
    store.update_artifact(aid, "completed", {"scenario": scenario,
                                             "top": out["contributions"][0]["parameter"]
                                             if out["contributions"] else None})
    return out


def fidelity_run(store: Store, model_id: str, pose: dict[str, float], samples: int,
                 seed: int, payload_mass: float = 0.0) -> dict[str, Any]:
    from motionproof.fidelity.static import discrepancy

    model = services.load_model(store, model_id)
    space = VariableSpace.from_model(model.spec)
    rows = [dict(zip(space.names, r.tolist(), strict=True))
            for r in space.design("monte_carlo", samples, seed).values]
    out = discrepancy(model, rows, pose, payload_mass)
    out |= {"model": _model_ref(model), "levels": {
        "L1_quasi_static": "implemented", "L2_reduced_order_dynamics": "implemented",
        "L3_contact_structural": "not implemented",
        "L4_physical": "hardware sessions and calibration measurements"}}
    row = store.model(model_id)
    aid, _ = store.new_artifact("fidelity", row["project_id"], "L1 vs L2", model_id)
    out["id"] = aid
    store.save_json(aid, "fidelity", out)
    store.update_artifact(aid, "completed", {"variants": out["variants"]})
    return out


# =========================================================================== trust panel

EVIDENCE = {"specified": "entered manually (specification)", "measured": "measured physically",
            "estimated": "estimated", "assumed": "assumed"}


def trust(store: Store, model_id: str) -> dict[str, Any]:
    """Parameter-level evidence. No overall score is computed on purpose."""
    model = services.load_model(store, model_id)
    spec = model.spec
    rows: list[dict[str, Any]] = []
    for c in model.inventory.get("components", []):
        src = c.get("source", "")
        rows.append({"group": "geometry", "parameter": f"{c['id']} geometry",
                     "status": "imported from CAD" if "generated" not in src
                     else "generated (synthetic)", "source": src, "value": c.get("volume_mm3"),
                     "unit": "mm^3"})
        if c.get("mass_kg") is not None:
            rows.append({"group": "geometry", "parameter": f"{c['id']} mass",
                         "status": "estimated" if c.get("note", "").startswith("mass estimated")
                         or c.get("density_kg_m3") else "imported from CAD",
                         "source": c.get("note") or src, "value": c["mass_kg"], "unit": "kg"})
    built = as_built(store, model_id)
    measured = {u["tolerance"]: u for u in built["used"]}
    for t in spec.tolerances:
        status = EVIDENCE[t.confidence.value]
        if t.id in measured:
            status = "extracted from scan"
        rows.append({"group": "tolerance", "parameter": t.id, "status": status,
                     "source": t.source, "value": t.nominal, "unit": t.unit,
                     "verification": t.verification,
                     "as_built": measured.get(t.id)})
    for name, d in spec.drives.items():
        for part, obj in (("motor", d.motor), ("gearbox", d.gearbox)):
            status = EVIDENCE[obj.confidence.value]
            if obj.confidence == Confidence.SPECIFIED and "datasheet" in obj.source.lower():
                status = "manufacturer supplied"
            rows.append({"group": "mechanics", "parameter": f"{name} {part}", "status": status,
                         "source": obj.source, "value": None, "unit": ""})
    cal = Path(store.model(model_id)["directory"]) / "calibration.json"
    if cal.is_file():
        res = json.loads(cal.read_text(encoding="utf-8"))
        for p in res["parameters"]:
            rows.append({"group": "calibration", "parameter": f"{p['joint']}.{p['name']}",
                         "status": "independently validated"
                         if res["assessment"] == "holdout_consistent"
                         and res["holdout"]["split"] == "separate_recording" else "calibrated",
                         "source": f"calibration, holdout {res['holdout']['split']}",
                         "value": p["estimate"], "unit": ""})
    for a in store.artifacts("hardware", model_id=model_id):
        rows.append({"group": "measurement", "parameter": a["name"],
                     "status": "simulated device (not physical)"
                     if (a["summary"] or {}).get("source") == "SIMULATED DEVICE"
                     else "measured physically", "source": a["id"], "value": None, "unit": ""})
    counts: dict[str, int] = {}
    for r in rows:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    return {"model": _model_ref(model), "parameters": rows, "counts": counts,
            "note": "Evidence is shown per parameter. MotionProof computes no overall trust "
                    "score."}
