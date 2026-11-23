"""REST routes for the advanced subsystems (mounted by ``api.app.create_app``)."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel, ConfigDict, Field

from motionproof import advanced, services
from motionproof.api.jobs import JobManager
from motionproof.cad.importers import safe_name
from motionproof.persistence.store import Store

API = "/api/v1"
MAX_SCAN_BYTES = 500 * 1024 * 1024


class _B(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AnalyseIn(_B):
    limit: float | None = Field(default=None, gt=0)
    cylinders: list[advanced.CylinderRequest] = Field(default_factory=list)


class DecisionIn(_B):
    status: Literal["approved", "rejected"]


class BatchIn(_B):
    model_id: str
    name: str = "batch"
    process: dict[str, Any]
    plan: dict[str, Any]


class FidelityIn(_B):
    model_id: str
    pose: dict[str, float]
    samples: int = Field(default=10, ge=1, le=500)
    seed: int = 0
    payload_mass: float = Field(default=0.0, ge=0)


class RootCauseIn(_B):
    experiment_id: str
    scenario: str


class ChallengeIn(_B):
    model_id: str
    config: dict[str, Any]


class BenchmarkIn(_B):
    ids: list[str] | None = None


def register(app: FastAPI, store: Store, jobs: JobManager) -> None:

    def submit(kind: str, subject: str, fn: Any) -> dict[str, Any]:
        return jobs.submit(kind, subject, fn)

    # ------------------------------------------------------------------ generic artifacts

    @app.get(f"{API}/artifacts")
    def artifact_list(kind: str | None = None, project_id: str | None = None,
                      model_id: str | None = None) -> list[dict[str, Any]]:
        return store.artifacts(kind, project_id, model_id)

    @app.get(f"{API}/artifacts/{{artifact_id}}/{{name}}")
    def artifact_data(artifact_id: str, name: str) -> Any:
        if name not in ("scan", "registration", "analysis", "batch", "adaptive", "workspace",
                        "degradation", "session", "rootcause", "fidelity", "challenge",
                        "comparison", "benchmarks"):
            raise HTTPException(404, f"unknown artifact part {name!r}")
        return store.load_json(artifact_id, name)

    # ------------------------------------------------------------------ scans

    @app.post(f"{API}/scans/import", status_code=201)
    async def scan_import(model_id: str = Form(...), units: str | None = Form(None),
                          scanner: str | None = Form(None),
                          capture_date: str | None = Form(None),
                          file: UploadFile = File(...)) -> dict[str, Any]:
        with tempfile.TemporaryDirectory(prefix="mp_scan_") as tmp:
            target = Path(tmp) / safe_name(file.filename or "scan.xyz")
            size = 0
            with target.open("wb") as f:
                while chunk := await file.read(1 << 20):
                    size += len(chunk)
                    if size > MAX_SCAN_BYTES:
                        raise HTTPException(413, "scan exceeds the 500 MB limit")
                    f.write(chunk)
            meta = {k: v for k, v in (("scanner", scanner), ("capture_date", capture_date)) if v}
            return advanced.scan_import(store, model_id, target, units or None, meta)

    @app.post(f"{API}/scans/{{scan_id}}/register", status_code=202)
    def scan_register(scan_id: str, req: advanced.RegisterRequest) -> dict[str, Any]:
        store.artifact(scan_id)
        return submit("scan_register", scan_id,
                      lambda p, c: advanced.scan_register(store, scan_id, req)["registration"]
                      ["rms"])

    @app.post(f"{API}/scans/{{scan_id}}/analyse", status_code=202)
    def scan_analyse(scan_id: str, req: AnalyseIn) -> dict[str, Any]:
        store.load_json(scan_id, "registration")
        return submit("scan_analyse", scan_id, lambda p, c: advanced.scan_analyse(
            store, scan_id, req.limit, req.cylinders)["deviation"]["rms"])

    @app.get(f"{API}/scans/{{scan_id}}")
    def scan_get(scan_id: str) -> dict[str, Any]:
        out: dict[str, Any] = {"artifact": store.artifact(scan_id)}
        for part in ("scan", "registration", "analysis"):
            try:
                out[part] = store.load_json(scan_id, part)
            except Exception:
                out[part] = None
        return out

    @app.post(f"{API}/scans/{{scan_id}}/measurements/{{measurement_id}}")
    def scan_decide(scan_id: str, measurement_id: str, body: DecisionIn) -> dict[str, Any]:
        return advanced.measurement_decision(store, scan_id, measurement_id, body.status)

    @app.get(f"{API}/models/{{model_id}}/as-built")
    def model_as_built(model_id: str) -> dict[str, Any]:
        return advanced.as_built(store, model_id)

    @app.get(f"{API}/models/{{model_id}}/trust")
    def model_trust(model_id: str) -> dict[str, Any]:
        return advanced.trust(store, model_id)

    # ------------------------------------------------------------------ manufacturing

    @app.post(f"{API}/manufacturing/batches", status_code=202)
    def batch_create(body: BatchIn) -> dict[str, Any]:
        services.load_model(store, body.model_id)
        return submit("batch", body.model_id, lambda p, c: advanced.process_batch(
            store, body.model_id, body.process, body.plan, body.name)["id"])

    # ------------------------------------------------------------------ adaptive

    @app.post(f"{API}/experiments/adaptive", status_code=202)
    def adaptive_create(req: advanced.AdaptiveRequest) -> dict[str, Any]:
        services.load_model(store, req.model_id)
        return submit("adaptive", req.model_id,
                      lambda p, c: advanced.adaptive_run(store, req, p, c)["id"])

    # ------------------------------------------------------------------ workspace

    @app.post(f"{API}/workspace/analyse", status_code=202)
    def workspace_create(req: advanced.WorkspaceRequest) -> dict[str, Any]:
        services.load_model(store, req.model_id)
        return submit("workspace", req.model_id,
                      lambda p, c: advanced.workspace_run(store, req)["id"])

    # ------------------------------------------------------------------ degradation

    @app.post(f"{API}/degradation/experiments", status_code=202)
    def degradation_create(req: advanced.DegradationRequest) -> dict[str, Any]:
        services.load_model(store, req.model_id)
        return submit("degradation", req.model_id,
                      lambda p, c: advanced.degradation_run(store, req)["id"])

    # ------------------------------------------------------------------ fidelity / root cause

    @app.post(f"{API}/fidelity/compare", status_code=202)
    def fidelity_create(req: FidelityIn) -> dict[str, Any]:
        return submit("fidelity", req.model_id, lambda p, c: advanced.fidelity_run(
            store, req.model_id, req.pose, req.samples, req.seed, req.payload_mass)["id"])

    @app.post(f"{API}/rootcause", status_code=202)
    def rootcause_create(req: RootCauseIn) -> dict[str, Any]:
        store.experiment(req.experiment_id)
        return submit("rootcause", req.experiment_id, lambda p, c: advanced.rootcause_run(
            store, req.experiment_id, req.scenario)["id"])

    # ------------------------------------------------------------------ hardware

    @app.get(f"{API}/hardware/devices")
    def hardware_devices() -> list[dict[str, Any]]:
        from motionproof.hardware.device import list_devices

        return list_devices()

    @app.post(f"{API}/hardware/experiments", status_code=202)
    def hardware_create(req: advanced.HardwareRequest, request: Request) -> dict[str, Any]:
        if not req.confirm_actuation:
            raise HTTPException(400, "actuation was not confirmed; nothing was sent")
        if req.device != "simulated":
            # only the serial ports the server itself lists, and only if the server allows them
            from motionproof.hardware.device import list_devices

            if not request.app.state.security.serial:
                raise HTTPException(403, "serial devices are disabled on this server "
                                         "(MOTIONPROOF_SERIAL=1 enables them)")
            if req.device not in {d["id"] for d in list_devices() if d["kind"] == "serial"}:
                raise HTTPException(422, f"unknown serial device {req.device!r}")
        services.load_model(store, req.model_id)
        return submit("hardware", req.model_id,
                      lambda p, c: advanced.hardware_run(store, req)["id"])

    @app.get(f"{API}/hardware/experiments/{{session_id}}/measurements")
    def hardware_measurements(session_id: str) -> Any:
        from fastapi.responses import FileResponse

        path = Path(store.artifact(session_id)["directory"]) / "measurements.csv"
        return FileResponse(path, media_type="text/csv", filename=f"{session_id}.csv")

    # ------------------------------------------------------------------ challenge

    @app.post(f"{API}/challenges", status_code=202)
    def challenge_create(body: ChallengeIn) -> dict[str, Any]:
        from motionproof.challenge.engine import Challenge, ChallengeConfig, comparison

        cfg = ChallengeConfig.model_validate(body.config)
        model = services.load_model(store, body.model_id)
        Challenge(model, cfg)  # validates variables against the model before queuing
        row = store.model(body.model_id)
        aid, _ = store.new_artifact("challenge", row["project_id"], cfg.name, body.model_id)

        def work(progress: Any, cancel: Any) -> str:
            store.update_artifact(aid, "running")
            res = Challenge(model, cfg).run(progress, cancel)
            res |= {"id": aid, "model": advanced._model_ref(model),
                    "config": cfg.model_dump(mode="json")}
            store.save_json(aid, "challenge", res)
            store.save_json(aid, "comparison", comparison(res, model))
            store.update_artifact(aid, res["status"], {"chosen": res["chosen"],
                                                       "candidates": len(res["candidates"])})
            return aid
        job = submit("challenge", aid, work)
        return job | {"challenge_id": aid}

    # ------------------------------------------------------------------ benchmarks

    @app.get(f"{API}/benchmarks")
    def benchmark_list() -> dict[str, Any]:
        from motionproof.benchmarks.suite import BENCHMARKS

        latest = store.artifacts("benchmark")
        last = None
        if latest:
            try:
                last = store.load_json(latest[0]["id"], "benchmarks")
            except Exception:
                last = None
        return {"benchmarks": [{"id": k, "name": n, "title": fn.__doc__ or n}
                               for k, (n, fn) in BENCHMARKS.items()],
                "latest": last, "latest_id": latest[0]["id"] if latest else None}

    @app.post(f"{API}/benchmarks/run", status_code=202)
    def benchmark_run(body: BenchmarkIn) -> dict[str, Any]:
        from motionproof.benchmarks.suite import resolve, run

        ids = [resolve(i) for i in body.ids] if body.ids else None
        projects = store.projects()
        pid = projects[-1]["id"] if projects else store.create_project("default")["id"]

        def work(progress: Any, cancel: Any) -> str:
            aid, _ = store.new_artifact("benchmark", pid, "benchmark run")
            results = run(ids)
            store.save_json(aid, "benchmarks", results)
            store.update_artifact(aid, "completed", {r["id"]: r["status"] for r in results})
            return aid
        return submit("benchmark", "benchmarks", work)

