"""MotionProof REST API (FastAPI). Thin layer over ``motionproof.services`` and the engine."""

from __future__ import annotations

import json
import logging
import shutil
import tempfile
from pathlib import Path
from typing import Any, Literal

import numpy as np
from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, ValidationError

import motionproof
from motionproof import services
from motionproof.ai.assistant import explain as ai_explain
from motionproof.ai.assistant import status as ai_status
from motionproof.api.jobs import JobManager
from motionproof.cad.importers import MAX_UPLOAD_BYTES, ImportFailure, safe_name
from motionproof.calibration.fit import (
    CalibrationConfig,
    CalibrationError,
    calibrate,
    preview_csv,
    read_csv,
)
from motionproof.core.schema import Feature, Tolerance
from motionproof.experiments.runner import (
    Experiment,
    ExperimentConfig,
    ExperimentError,
    evaluate_scenario,
    versions,
)
from motionproof.model import ModelError
from motionproof.optimisation import allocation as alloc
from motionproof.optimisation import worst_case
from motionproof.persistence.store import NotFound, Store
from motionproof.reporting import report as reporting
from motionproof.sensitivity import analysis as sens
from motionproof.simulation.engine import SimulationError
from motionproof.simulation.tasks import Task
from motionproof.statistics.robustness import histogram, summarise
from motionproof.tolerances.sampling import SamplingError, SamplingMethod, VariableSpace

log = logging.getLogger("motionproof.api")
API = "/api/v1"


class _Body(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProjectIn(_Body):
    name: str = Field(min_length=1, max_length=120)
    description: str = ""


class ModelRef(_Body):
    project_id: str


class VariantRequest(_Body):
    model_id: str
    method: SamplingMethod = "monte_carlo"
    samples: int = Field(default=20, ge=1, le=500)
    seed: int = 0


class VariantValues(_Body):
    model_id: str
    values: dict[str, float] = Field(default_factory=dict)


class PoseRequest(_Body):
    pose: dict[str, float] = Field(default_factory=dict)
    values: dict[str, float] | None = None


class MechanicsIn(_Body):
    model_id: str
    drives: dict[str, Any] | None = None
    held_joints: dict[str, float] | None = None
    end_effector: dict[str, Any] | None = None
    effects: list[dict[str, Any]] | None = None
    fits: list[dict[str, Any]] | None = None
    radial_supports: list[dict[str, Any]] | None = None
    gear_stages: list[dict[str, Any]] | None = None
    correlations: list[dict[str, Any]] | None = None
    datums: list[dict[str, Any]] | None = None


class TaskRun(_Body):
    model_id: str
    task: Task
    values: dict[str, float] = Field(default_factory=dict)


class ExperimentIn(_Body):
    model_id: str
    config: ExperimentConfig


class ReplayIn(_Body):
    scenario: str


class OptimiseIn(_Body):
    kind: Literal["worst_case", "minimise", "allocation", "sobol", "one_at_a_time", "comparison"]
    metric: str | None = None
    direction: Literal["maximise", "minimise"] = "maximise"
    algorithm: worst_case.Algorithm = "differential_evolution"
    budget: int = Field(default=300, ge=10, le=20000)
    seed: int = 0
    scenario: str | None = None
    allocation: alloc.AllocationConfig | None = None
    base_samples: int = Field(default=32, ge=8, le=1024)
    variables: list[str] | None = None
    variants: dict[str, dict[str, float]] | None = None
    samples: int = Field(default=100, ge=10, le=5000)


class CalibrationIn(_Body):
    model_id: str
    calibration_file: str
    holdout_file: str | None = None
    config: CalibrationConfig


class AiIn(_Body):
    experiment_id: str
    question: str = Field(min_length=1, max_length=2000)


def create_app(home: str | Path | None = None) -> FastAPI:
    store = Store(home)
    jobs = JobManager(workers=1)
    app = FastAPI(title="MotionProof", version=motionproof.__version__,
                  description="Tolerance-to-dynamics engineering lab API")
    app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173",
                                                      "http://127.0.0.1:5173"],
                       allow_methods=["*"], allow_headers=["*"])
    app.state.store, app.state.jobs = store, jobs

    def problem(status: int, message: str) -> JSONResponse:
        return JSONResponse(status_code=status, content={"error": message})

    for exc_type, code in ((NotFound, 404), (ModelError, 422), (ImportFailure, 422),
                           (ExperimentError, 422), (SamplingError, 422),
                           (SimulationError, 422), (CalibrationError, 422),
                           (ValidationError, 422), (KeyError, 404), (ValueError, 422)):
        def handler(_req: Any, exc: Exception, _code: int = code) -> JSONResponse:
            msg = exc.args[0] if isinstance(exc, KeyError) and exc.args else str(exc)
            return problem(_code, str(msg))
        app.add_exception_handler(exc_type, handler)

    def experiment(eid: str) -> Experiment:
        return Experiment.open(store.experiment(eid)["directory"])

    def measurement_path(project_id: str, name: str) -> Path:
        root = store.home / "projects" / project_id / "measurements"
        path = (root / safe_name(name)).resolve()
        if path.parent != root.resolve() or not path.is_file():
            raise NotFound(f"measurement file {name!r} not found")
        return path

    # ------------------------------------------------------------------ system

    @app.get(f"{API}/health")
    def health() -> dict[str, Any]:
        return {"status": "ok", "versions": versions(), "workspace": str(store.home),
                "active_jobs": len(jobs.active()), "ai": ai_status()}

    @app.get(f"{API}/jobs/{{job_id}}")
    def job(job_id: str) -> dict[str, Any]:
        return jobs.get(job_id)

    @app.post(f"{API}/jobs/{{job_id}}/cancel")
    def job_cancel(job_id: str) -> dict[str, Any]:
        return jobs.cancel(job_id)

    # ------------------------------------------------------------------ projects

    @app.post(f"{API}/projects", status_code=201)
    def project_create(body: ProjectIn) -> dict[str, Any]:
        return store.create_project(body.name, body.description)

    @app.get(f"{API}/projects")
    def project_list() -> list[dict[str, Any]]:
        out = []
        for p in store.projects():
            out.append(p | {"models": len(store.models(p["id"])),
                            "experiments": len(store.experiments(p["id"]))})
        return out

    @app.get(f"{API}/projects/{{project_id}}")
    def project_get(project_id: str) -> dict[str, Any]:
        return store.project(project_id) | {
            "models": store.models(project_id), "experiments": store.experiments(project_id)}

    @app.delete(f"{API}/projects/{{project_id}}")
    def project_delete(project_id: str, confirm: str = Query(...)) -> dict[str, Any]:
        if confirm != project_id:
            raise HTTPException(400, "confirm must equal the project id")
        store.delete_project(project_id)
        return {"deleted": project_id}

    # ------------------------------------------------------------------ models

    @app.post(f"{API}/models/import", status_code=201)
    async def model_import(project_id: str = Form(...), name: str | None = Form(None),
                           mesh_units: str | None = Form(None),
                           files: list[UploadFile] = File(...)) -> dict[str, Any]:
        store.project(project_id)
        with tempfile.TemporaryDirectory(prefix="mp_upload_") as tmp:
            saved: list[Path] = []
            for up in files:
                target = Path(tmp) / safe_name(up.filename or "upload")
                size = 0
                with target.open("wb") as f:
                    while chunk := await up.read(1 << 20):
                        size += len(chunk)
                        if size > MAX_UPLOAD_BYTES:
                            raise HTTPException(413, f"{up.filename} exceeds the "
                                                     f"{MAX_UPLOAD_BYTES >> 20} MB limit")
                        f.write(chunk)
                saved.append(target)
            return services.import_model(store, project_id, saved, name, mesh_units or None)

    @app.post(f"{API}/models/reference", status_code=201)
    def model_reference(body: ModelRef) -> dict[str, Any]:
        return services.create_reference_model(store, body.project_id)

    @app.get(f"{API}/models")
    def model_list(project_id: str | None = None) -> list[dict[str, Any]]:
        return store.models(project_id)

    @app.get(f"{API}/models/{{model_id}}")
    def model_get(model_id: str) -> dict[str, Any]:
        return services.model_detail(store, model_id)

    @app.put(f"{API}/models/{{model_id}}/spec")
    def model_put_spec(model_id: str, spec: dict[str, Any]) -> dict[str, Any]:
        services.save_spec(store, model_id, spec)
        return services.model_detail(store, model_id)

    @app.post(f"{API}/models/{{model_id}}/validate")
    def model_validate(model_id: str) -> dict[str, Any]:
        return services.readiness(services.load_model(store, model_id))

    @app.get(f"{API}/models/{{model_id}}/components")
    def model_components(model_id: str) -> list[dict[str, Any]]:
        comps: list[dict[str, Any]] = services.load_model(store, model_id).inventory.get(
            "components", [])
        return comps

    @app.get(f"{API}/models/{{model_id}}/meshes/{{component_id}}")
    def model_mesh(model_id: str, component_id: str) -> FileResponse:
        model = services.load_model(store, model_id)
        comp = next((c for c in model.inventory.get("components", [])
                     if c["id"] == component_id), None)
        if comp is None or not comp.get("mesh"):
            raise NotFound(f"component {component_id!r} has no mesh")
        path = (model.geometry_dir / comp["mesh"]).resolve()
        if model.geometry_dir.resolve() not in path.parents:
            raise HTTPException(400, "invalid mesh path")
        return FileResponse(path, media_type="model/stl")

    @app.post(f"{API}/models/{{model_id}}/pose")
    def model_pose(model_id: str, body: PoseRequest) -> dict[str, Any]:
        return services.load_model(store, model_id).body_poses(body.pose, body.values)

    @app.get(f"{API}/models/{{model_id}}/feature-suggestions")
    def model_suggestions(model_id: str) -> dict[str, Any]:
        sugg: dict[str, Any] = services.load_model(store, model_id).inventory.get(
            "feature_suggestions", {})
        return sugg

    @app.get(f"{API}/models/{{model_id}}/features")
    def feature_list(model_id: str) -> list[dict[str, Any]]:
        spec = services.load_model(store, model_id).spec
        return [f.model_dump(mode="json") for f in spec.features]

    @app.post(f"{API}/models/{{model_id}}/features", status_code=201)
    def feature_upsert(model_id: str, feature: Feature) -> list[dict[str, Any]]:
        def mutate(raw: dict[str, Any]) -> None:
            raw["features"] = [f for f in raw.get("features", []) if f["id"] != feature.id]
            raw["features"].append(feature.model_dump(mode="json", exclude_none=True))
        model = services.edit_spec(store, model_id, mutate)
        return [f.model_dump(mode="json") for f in model.spec.features]

    @app.delete(f"{API}/models/{{model_id}}/features/{{feature_id}}")
    def feature_delete(model_id: str, feature_id: str) -> dict[str, Any]:
        def mutate(raw: dict[str, Any]) -> None:
            before = len(raw.get("features", []))
            raw["features"] = [f for f in raw.get("features", []) if f["id"] != feature_id]
            if len(raw["features"]) == before:
                raise NotFound(f"feature {feature_id!r} not found")
        services.edit_spec(store, model_id, mutate)
        return {"deleted": feature_id}

    # ------------------------------------------------------------------ tolerances

    @app.get(f"{API}/tolerances")
    def tolerance_list(model_id: str) -> dict[str, Any]:
        model = services.load_model(store, model_id)
        return {"tolerances": [t.model_dump(mode="json") for t in model.spec.tolerances],
                "correlations": [c.model_dump(mode="json") for c in model.spec.correlations],
                **services.tolerance_review(model)}

    @app.post(f"{API}/tolerances", status_code=201)
    def tolerance_create(model_id: str, tol: Tolerance) -> dict[str, Any]:
        def mutate(raw: dict[str, Any]) -> None:
            if any(t["id"] == tol.id for t in raw.get("tolerances", [])):
                raise ValueError(f"tolerance {tol.id!r} already exists")
            raw.setdefault("tolerances", []).append(tol.model_dump(mode="json",
                                                                   exclude_none=True))
        services.edit_spec(store, model_id, mutate)
        return tolerance_list(model_id)

    @app.put(f"{API}/tolerances/{{tolerance_id}}")
    def tolerance_update(tolerance_id: str, model_id: str, tol: Tolerance) -> dict[str, Any]:
        if tol.id != tolerance_id:
            raise ValueError("tolerance id in the body does not match the URL")

        def mutate(raw: dict[str, Any]) -> None:
            for i, t in enumerate(raw.get("tolerances", [])):
                if t["id"] == tolerance_id:
                    raw["tolerances"][i] = tol.model_dump(mode="json", exclude_none=True)
                    return
            raise NotFound(f"tolerance {tolerance_id!r} not found")
        services.edit_spec(store, model_id, mutate)
        return tolerance_list(model_id)

    @app.delete(f"{API}/tolerances/{{tolerance_id}}")
    def tolerance_delete(tolerance_id: str, model_id: str) -> dict[str, Any]:
        def mutate(raw: dict[str, Any]) -> None:
            raw["tolerances"] = [t for t in raw.get("tolerances", []) if t["id"] != tolerance_id]
        services.edit_spec(store, model_id, mutate)
        return tolerance_list(model_id)

    # ------------------------------------------------------------------ assemblies

    @app.post(f"{API}/assemblies/generate-variants")
    def assemblies_generate(body: VariantRequest) -> dict[str, Any]:
        return services.generate_variants(services.load_model(store, body.model_id),
                                          body.method, body.samples, body.seed)

    @app.post(f"{API}/assemblies/validate")
    def assemblies_validate(body: VariantValues) -> dict[str, Any]:
        return services.variant_detail(services.load_model(store, body.model_id), body.values)

    @app.post(f"{API}/mechanics/configure")
    def mechanics_configure(body: MechanicsIn) -> dict[str, Any]:
        updates = body.model_dump(exclude={"model_id"}, exclude_none=True)

        def mutate(raw: dict[str, Any]) -> None:
            raw.update(updates)
        services.edit_spec(store, body.model_id, mutate)
        return services.model_detail(store, body.model_id)

    @app.post(f"{API}/tasks")
    def task_run(body: TaskRun) -> dict[str, Any]:
        """Run one task on one variant, synchronously (a single run takes well under 1 s)."""
        model = services.load_model(store, body.model_id)
        variant = model.variant(body.values)
        res = model.engine.run(variant, body.task, keep_trace=True)
        return res.to_dict() | {"variant": variant.to_dict(),
                                "fidelity": model.spec.fidelity.value}

    # ------------------------------------------------------------------ experiments

    @app.post(f"{API}/experiments", status_code=201)
    def experiment_create(body: ExperimentIn) -> dict[str, Any]:
        row = store.model(body.model_id)
        model = services.load_model(store, body.model_id)
        eid, directory = store.new_experiment_dir(row["project_id"])
        Experiment.create(model, body.config, directory, eid)
        return store.register_experiment(eid, row["project_id"], body.model_id,
                                         body.config.name, directory)

    @app.get(f"{API}/experiments")
    def experiment_list(project_id: str | None = None) -> list[dict[str, Any]]:
        return store.experiments(project_id)

    @app.post(f"{API}/experiments/{{experiment_id}}/run", status_code=202)
    def experiment_run(experiment_id: str) -> dict[str, Any]:
        exp = experiment(experiment_id)
        running = jobs.latest(experiment_id, "experiment")
        if running and running["status"] in ("queued", "running"):
            return running

        def work(progress: Any, cancel: Any) -> dict[str, Any]:
            store.update_experiment(experiment_id, "running")
            try:
                out = exp.run(progress=progress, cancel=cancel)
            except Exception:
                store.update_experiment(experiment_id, "failed")
                raise
            summary = summarise(exp.manifest, exp.results())
            store.update_experiment(experiment_id, out["status"],
                                    {"scenarios": summary["scenarios"],
                                     "all_constraints": summary["all_constraints"],
                                     "failure_categories": summary["failure_categories"]})
            return out
        return jobs.submit("experiment", experiment_id, work)

    @app.get(f"{API}/experiments/{{experiment_id}}")
    def experiment_get(experiment_id: str) -> dict[str, Any]:
        row = store.experiment(experiment_id)
        exp = experiment(experiment_id)
        m = exp.manifest
        return row | {
            "manifest": {k: m[k] for k in ("id", "name", "created", "config", "versions")}
            | {"model": {k: v for k, v in m["model"].items() if k != "spec"},
               "design": {k: v for k, v in m["design"].items() if k != "values"}
               | {"scenarios": exp.total}},
            "analyses": [p.stem for p in exp.directory.glob("*.json")
                         if p.stem not in ("manifest",)],
        }

    @app.get(f"{API}/experiments/{{experiment_id}}/progress")
    def experiment_progress(experiment_id: str) -> dict[str, Any]:
        row = store.experiment(experiment_id)
        exp = experiment(experiment_id)
        j = jobs.latest(experiment_id, "experiment")
        done = len(exp.results())
        return {"status": j["status"] if j else row["status"], "job": j, "done": done,
                "total": exp.total, "progress": (j or {}).get("progress") or {}}

    @app.post(f"{API}/experiments/{{experiment_id}}/cancel")
    def experiment_cancel(experiment_id: str) -> dict[str, Any]:
        j = jobs.latest(experiment_id)
        if j is None or j["status"] not in ("queued", "running"):
            raise HTTPException(409, "no running job for this experiment")
        return jobs.cancel(j["id"])

    @app.get(f"{API}/experiments/{{experiment_id}}/results")
    def experiment_results(experiment_id: str, offset: int = Query(0, ge=0),
                           limit: int = Query(200, ge=1, le=2000),
                           status: Literal["all", "failed", "passed", "invalid"] = "all",
                           category: str | None = None) -> dict[str, Any]:
        rows = experiment(experiment_id).results()
        if status == "failed":
            rows = [r for r in rows if r["valid"] and not r["passed"]]
        elif status == "passed":
            rows = [r for r in rows if r["passed"]]
        elif status == "invalid":
            rows = [r for r in rows if not r["valid"]]
        if category:
            rows = [r for r in rows if any(f["category"] == category for f in r["failures"])]
        return {"total": len(rows), "offset": offset, "results": rows[offset:offset + limit]}

    @app.get(f"{API}/experiments/{{experiment_id}}/analysis")
    def experiment_analysis(experiment_id: str, metric: str | None = None) -> dict[str, Any]:
        exp = experiment(experiment_id)
        results = exp.results()
        if not results:
            raise HTTPException(409, "the experiment has no results yet")
        summary = summarise(exp.manifest, results)
        x, metrics, valid = exp.metric_matrix()
        hists = {k: histogram(v.tolist()) for k, v in metrics.items()}
        out: dict[str, Any] = {"summary": summary, "histograms": hists,
                               "metrics": sorted(metrics), "variables": exp.names}
        if metric:
            out["sensitivity"] = sens.analyse(exp.names, x, metrics, metric)
            order = [r["parameter"] for r in out["sensitivity"]["rank_correlation"]["rows"][:6]]
            out["scatter"] = {
                p: {"x": x[:, exp.names.index(p)].tolist(), "y": metrics[metric].tolist(),
                    "passed": [bool(r["passed"]) for r in valid]} for p in order}
        return out

    @app.post(f"{API}/experiments/{{experiment_id}}/replay")
    def experiment_replay(experiment_id: str, body: ReplayIn) -> dict[str, Any]:
        return experiment(experiment_id).replay(body.scenario)

    @app.post(f"{API}/experiments/{{experiment_id}}/optimise", status_code=202)
    def experiment_optimise(experiment_id: str, body: OptimiseIn) -> dict[str, Any]:
        exp = experiment(experiment_id)
        model = exp.model()
        cfg = exp.config
        need_metric = body.kind in ("worst_case", "sobol", "one_at_a_time")
        if need_metric and not body.metric:
            raise ValueError(f"{body.kind} needs a metric")
        if body.kind == "allocation" and body.allocation is None:
            raise ValueError("allocation needs an allocation configuration")
        if body.kind == "comparison" and not body.variants:
            raise ValueError("comparison needs at least one variant")

        def scalar(metric: str) -> Any:
            def f(row: dict[str, float]) -> float:
                res = evaluate_scenario(model, cfg, row)
                return float(res["metrics"].get(metric, np.nan)) if res["valid"] else np.nan
            return f

        def work(progress: Any, cancel: Any) -> dict[str, Any]:
            space = VariableSpace.from_model(model.spec, cfg.operating)
            if body.kind == "worst_case":
                out = worst_case.search(model, cfg, body.metric or "", body.direction,
                                        body.algorithm, body.budget, body.seed, progress, cancel)
            elif body.kind == "minimise":
                if body.scenario:
                    stored = next((r for r in exp.results() if r["id"] == body.scenario), None)
                    if stored is None:
                        raise ExperimentError(f"scenario {body.scenario!r} not found")
                    failing = exp.row(stored["index"])
                else:
                    wc = json.loads((exp.directory / "worst_case.json").read_text("utf-8"))
                    failing = wc["configuration"]
                out = worst_case.minimise_failure(model, cfg, failing)
            elif body.kind == "allocation":
                assert body.allocation is not None
                out = alloc.allocate(model, cfg, body.allocation, progress, cancel)
            elif body.kind == "sobol":
                out = sens.sobol(space, scalar(body.metric or ""), body.base_samples,
                                 body.seed, body.variables) | {"metric": body.metric}
            elif body.kind == "one_at_a_time":
                out = {"metric": body.metric, "method": "one-at-a-time, nominal to each bound",
                       "rows": sens.one_at_a_time(space, scalar(body.metric or ""))}
            else:
                out = alloc.compare_specs(model, cfg, body.variants or {}, body.samples,
                                               body.seed)
            (exp.directory / f"{body.kind}.json").write_text(json.dumps(out, default=float),
                                                             encoding="utf-8")
            return {"kind": body.kind, "status": out.get("status", "completed")}
        return jobs.submit(body.kind, experiment_id, work)

    @app.get(f"{API}/experiments/{{experiment_id}}/analyses/{{name}}")
    def experiment_analysis_file(experiment_id: str, name: str) -> Any:
        if name not in ("worst_case", "minimise", "allocation", "sobol", "one_at_a_time",
                        "comparison"):
            raise NotFound(f"unknown analysis {name!r}")
        path = experiment(experiment_id).directory / f"{name}.json"
        job_state = jobs.latest(experiment_id, name)
        if not path.is_file():
            return {"available": False, "job": job_state}
        return {"available": True, "job": job_state,
                "result": json.loads(path.read_text(encoding="utf-8"))}

    # ------------------------------------------------------------------ calibration

    @app.post(f"{API}/measurements/import", status_code=201)
    async def measurement_import(project_id: str = Form(...),
                                 file: UploadFile = File(...)) -> dict[str, Any]:
        store.project(project_id)
        name = safe_name(file.filename or "measurement.csv")
        if not name.lower().endswith(".csv"):
            raise ValueError("measurements must be CSV files")
        root = store.home / "projects" / project_id / "measurements"
        root.mkdir(parents=True, exist_ok=True)
        target = root / name
        with target.open("wb") as f:
            shutil.copyfileobj(file.file, f)
        if target.stat().st_size > 50 * 1024 * 1024:
            target.unlink()
            raise HTTPException(413, "measurement files are limited to 50 MB")
        return {"file": name, **preview_csv(target)}

    @app.get(f"{API}/measurements")
    def measurement_list(project_id: str) -> list[dict[str, Any]]:
        root = store.home / "projects" / project_id / "measurements"
        return [{"file": p.name, **preview_csv(p, 3)} for p in sorted(root.glob("*.csv"))
                ] if root.is_dir() else []

    @app.post(f"{API}/calibration", status_code=202)
    def calibration_run(body: CalibrationIn) -> dict[str, Any]:
        row = store.model(body.model_id)
        model = services.load_model(store, body.model_id)
        cal = read_csv(measurement_path(row["project_id"], body.calibration_file), body.config)
        hold = (read_csv(measurement_path(row["project_id"], body.holdout_file), body.config)
                if body.holdout_file else None)
        out_path = Path(row["directory"]) / "calibration.json"

        def work(_progress: Any, _cancel: Any) -> dict[str, Any]:
            result = calibrate(model, body.config, cal, hold)
            result["model_fingerprint"] = model.fingerprint
            out_path.write_text(json.dumps(result), encoding="utf-8")
            return {"status": "completed"}
        return jobs.submit("calibration", body.model_id, work)

    @app.get(f"{API}/calibration/{{model_id}}")
    def calibration_get(model_id: str) -> dict[str, Any]:
        path = Path(store.model(model_id)["directory"]) / "calibration.json"
        j = jobs.latest(model_id, "calibration")
        if not path.is_file():
            return {"available": False, "job": j}
        return {"available": True, "job": j,
                "result": json.loads(path.read_text(encoding="utf-8"))}

    # ------------------------------------------------------------------ reports

    @app.get(f"{API}/reports/{{experiment_id}}")
    def report_get(experiment_id: str,
                   format: Literal["json", "markdown", "csv", "pdf"] = "json") -> Any:
        exp = experiment(experiment_id)
        if not exp.results():
            raise HTTPException(409, "the experiment has no results to report")
        if format == "csv":
            return PlainTextResponse(reporting.to_csv(exp), media_type="text/csv", headers={
                "Content-Disposition": f'attachment; filename="{experiment_id}_scenarios.csv"'})
        rep = reporting.build(exp)
        if format == "json":
            return rep
        if format == "markdown":
            return PlainTextResponse(reporting.to_markdown(rep), media_type="text/markdown")
        out = exp.directory / "report"
        out.mkdir(exist_ok=True)
        pdf = reporting.to_pdf(rep, exp, out / "report.pdf")
        return FileResponse(pdf, media_type="application/pdf",
                            filename=f"{experiment_id}_report.pdf")

    @app.post(f"{API}/ai/explain")
    def ai(body: AiIn) -> dict[str, Any]:
        exp = experiment(body.experiment_id)
        if not exp.results():
            raise HTTPException(409, "the experiment has no results to explain")
        return ai_explain(reporting.build(exp), body.question)

    from motionproof.api.advanced_routes import register as register_advanced

    register_advanced(app, store, jobs)

    dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
    if dist.is_dir():
        app.mount("/", StaticFiles(directory=dist, html=True), name="frontend")
    return app
