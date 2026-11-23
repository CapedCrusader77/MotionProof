"""In-process background jobs: one worker, progress, cancellation.

Simulation work never runs inside a request handler. A single worker is the default because
the target machine has 16 GB of RAM and the engine is CPU bound.
"""

from __future__ import annotations

import contextvars
import threading
import time
import traceback
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any

JobFn = Callable[[Callable[[dict[str, Any]], None], threading.Event], Any]


class JobManager:
    def __init__(self, workers: int = 1, max_per_user: int | None = None):
        self.max_per_user = max_per_user
        self._pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="mp-job")
        self._jobs: dict[str, dict[str, Any]] = {}
        self._cancel: dict[str, threading.Event] = {}
        self._lock = threading.Lock()

    def submit(self, kind: str, subject: str, fn: JobFn) -> dict[str, Any]:
        from fastapi import HTTPException

        from motionproof.api.auth import current_user

        owner = current_user.get()
        if self.max_per_user is not None and owner is not None:
            mine = sum(1 for j in self._jobs.values()
                       if j.get("owner") == owner and j["status"] in ("queued", "running"))
            if mine >= self.max_per_user:
                raise HTTPException(429, f"you already have {mine} jobs queued or running "
                                         f"(limit {self.max_per_user}); wait for one to finish")
        jid = uuid.uuid4().hex[:12]
        cancel = threading.Event()
        job: dict[str, Any] = {"id": jid, "kind": kind, "subject": subject, "status": "queued",
               "progress": {}, "result": None, "error": None, "submitted": time.time(),
               "started": None, "finished": None, "owner": current_user.get()}
        with self._lock:
            self._jobs[jid] = job
            self._cancel[jid] = cancel

        def update(p: dict[str, Any]) -> None:
            job["progress"] = p

        def run() -> None:
            job["status"] = "running"
            job["started"] = time.time()
            try:
                job["result"] = fn(update, cancel)
                job["status"] = "cancelled" if cancel.is_set() else "completed"
            except Exception as exc:  # report, never crash the worker
                job["status"] = "failed"
                job["error"] = f"{type(exc).__name__}: {exc}"
                job["traceback"] = traceback.format_exc(limit=6)
            finally:
                job["finished"] = time.time()

        # run in the submitting request's context, so the job works in that user's workspace
        self._pool.submit(contextvars.copy_context().run, run)
        return self.get(jid)

    @staticmethod
    def _visible(job: dict[str, Any]) -> bool:
        """A signed-in user sees only their own jobs; code outside a request sees all."""
        from motionproof.api.auth import current_user

        uid = current_user.get()
        return uid is None or job.get("owner") == uid

    def get(self, jid: str) -> dict[str, Any]:
        job = self._jobs.get(jid)
        if job is None or not self._visible(job):
            raise KeyError(jid)
        out = {k: v for k, v in job.items() if k not in ("traceback", "owner")}
        if job["started"]:
            out["elapsed"] = (job["finished"] or time.time()) - job["started"]
        return out

    def cancel(self, jid: str) -> dict[str, Any]:
        if jid not in self._cancel:
            raise KeyError(jid)
        self.get(jid)  # not found for another user's job
        self._cancel[jid].set()
        return self.get(jid)

    def latest(self, subject: str, kind: str | None = None) -> dict[str, Any] | None:
        match = [j for j in self._jobs.values()
                 if j["subject"] == subject and (kind is None or j["kind"] == kind)
                 and self._visible(j)]
        return self.get(max(match, key=lambda j: j["submitted"])["id"]) if match else None

    def active(self) -> list[dict[str, Any]]:
        return [self.get(j["id"]) for j in self._jobs.values()
                if j["status"] in ("queued", "running") and self._visible(j)]
