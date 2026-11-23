"""REST routes for external experimental validation (``/api/v1/external``)."""

from __future__ import annotations

import os
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request

from motionproof.api.jobs import JobManager

API = "/api/v1/external"


def data_root() -> Path:
    return Path(os.environ.get("MOTIONPROOF_EXTERNAL_DATA", "external_data"))


def register(app: FastAPI, jobs: JobManager) -> None:
    from motionproof.external_validation.adapters import ADAPTERS
    from motionproof.external_validation.experiments.protocols import PROTOCOLS, SUPERSEDED
    from motionproof.external_validation.experiments.runs import VALIDATIONS, run
    from motionproof.external_validation.reports import record

    @app.get(f"{API}/datasets")
    def datasets() -> list[dict[str, Any]]:
        root = data_root()
        out = []
        for key, a in ADAPTERS.items():
            i = a.info
            out.append({"key": key, "title": i.title, "system": i.system,
                        "publisher": i.publisher, "url": i.url, "doi": i.doi,
                        "version": i.version, "licence": i.licence,
                        "licence_url": i.licence_url, "citation": i.citation,
                        "measured": list(i.measured), "not_measured": list(i.not_measured),
                        "notes": list(i.notes), "imported_files": len(a.available(root)),
                        "protocols": [pid for pid, p in PROTOCOLS.items()
                                      if p.dataset == key and pid not in SUPERSEDED],
                        "superseded_protocols": {pid: why for pid, why in SUPERSEDED.items()
                                                 if PROTOCOLS[pid].dataset == key}})
        return out

    @app.get(f"{API}/protocols")
    def protocols() -> list[dict[str, Any]]:
        return [vars(p) | {"motionproof_components": list(p.motionproof_components)}
                for p in PROTOCOLS.values()]

    @app.get(f"{API}/datasets/{{key}}/signals")
    def signals(key: str, limit: int = 2) -> list[dict[str, Any]]:
        if key not in ADAPTERS:
            raise HTTPException(404, f"unknown dataset {key!r}")
        a = ADAPTERS[key]
        files = [f for f in a.available(data_root()) if not f.endswith(".xlsx")]
        return [a.load(data_root(), f).summary() for f in files[:max(1, min(limit, 5))]]

    @app.post(f"{API}/datasets/{{key}}/import", status_code=202)
    def import_dataset(key: str, request: Request) -> dict[str, Any]:
        if not request.state.user["admin"]:        # downloads use the server's disk and bandwidth
            raise HTTPException(403, "only the administrator can download datasets")
        if key not in ADAPTERS:
            raise HTTPException(404, f"unknown dataset {key!r}")

        def job(update: Callable[[dict[str, Any]], None], cancel: threading.Event
                ) -> dict[str, Any]:
            return ADAPTERS[key].import_(
                data_root(), None, lambda i, n, f: update({"done": i, "total": n, "file": f}))
        return jobs.submit("external-import", key, job)

    @app.post(f"{API}/validate/{{pid}}", status_code=202)
    def validate(pid: str) -> dict[str, Any]:
        if pid not in VALIDATIONS:
            raise HTTPException(404, f"unknown protocol {pid!r}")

        def job(update: Callable[[dict[str, Any]], None], cancel: threading.Event
                ) -> dict[str, Any]:
            rec = record.save(data_root(), run(pid, data_root()))
            return {"id": rec["id"], "status": rec["result"]["status"]}
        return jobs.submit("external-validation", pid, job)

    @app.get(f"{API}/runs")
    def runs() -> list[dict[str, Any]]:
        return record.list_runs(data_root())

    @app.get(f"{API}/runs/{{rid}}")
    def run_detail(rid: str) -> dict[str, Any]:
        try:
            return record.load(data_root(), rid)
        except FileNotFoundError as exc:
            raise HTTPException(404, str(exc)) from None
