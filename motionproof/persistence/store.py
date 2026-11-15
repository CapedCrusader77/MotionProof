"""Local workspace: SQLite index plus one directory per project, model and experiment.

Layout::

    <home>/motionproof.db
    <home>/projects/<PRJ_id>/models/<MDL_id>/{model.yaml, geometry/, original/}
    <home>/projects/<PRJ_id>/experiments/<EXP_id>/{manifest.json, results.jsonl, ...}
"""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY, name TEXT NOT NULL, description TEXT, demo INTEGER NOT NULL DEFAULT 0,
    created TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS models (
    id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id), name TEXT NOT NULL,
    kind TEXT NOT NULL, synthetic INTEGER NOT NULL, directory TEXT NOT NULL,
    created TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS experiments (
    id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id),
    model_id TEXT NOT NULL REFERENCES models(id), name TEXT NOT NULL, status TEXT NOT NULL,
    directory TEXT NOT NULL, summary TEXT, created TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS artifacts (
    id TEXT PRIMARY KEY, project_id TEXT NOT NULL, model_id TEXT, experiment_id TEXT,
    kind TEXT NOT NULL, name TEXT NOT NULL, status TEXT NOT NULL, directory TEXT NOT NULL,
    summary TEXT, created TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS counters (name TEXT PRIMARY KEY, value INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT NOT NULL, action TEXT NOT NULL, detail TEXT);
"""


class NotFound(KeyError):
    pass


def default_home() -> Path:
    return Path(os.environ.get("MOTIONPROOF_HOME", Path.cwd() / "workspace")).resolve()


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class Store:
    def __init__(self, home: str | Path | None = None):
        self.home = Path(home).resolve() if home else default_home()
        (self.home / "projects").mkdir(parents=True, exist_ok=True)
        self.db_path = self.home / "motionproof.db"
        self._lock = threading.Lock()
        with self._conn() as c:
            c.executescript(SCHEMA)

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _next_id(self, prefix: str) -> str:
        with self._lock, self._conn() as c:
            c.execute("INSERT INTO counters(name, value) VALUES(?, 0) "
                      "ON CONFLICT(name) DO NOTHING", (prefix,))
            c.execute("UPDATE counters SET value = value + 1 WHERE name = ?", (prefix,))
            n = c.execute("SELECT value FROM counters WHERE name = ?", (prefix,)).fetchone()[0]
        return f"{prefix}_{n:03d}"

    def audit(self, action: str, detail: Any = None) -> None:
        with self._conn() as c:
            c.execute("INSERT INTO audit(at, action, detail) VALUES(?, ?, ?)",
                      (_now(), action, json.dumps(detail, default=str)))

    # ------------------------------------------------------------------ projects

    def create_project(self, name: str, description: str = "", demo: bool = False
                       ) -> dict[str, Any]:
        pid = self._next_id("PRJ")
        (self.home / "projects" / pid).mkdir(parents=True)
        with self._conn() as c:
            c.execute("INSERT INTO projects VALUES(?, ?, ?, ?, ?)",
                      (pid, name, description, int(demo), _now()))
        self.audit("project.create", {"id": pid, "name": name})
        return self.project(pid)

    def projects(self) -> list[dict[str, Any]]:
        with self._conn() as c:
            return [dict(r) for r in c.execute("SELECT * FROM projects ORDER BY created DESC")]

    def project(self, pid: str) -> dict[str, Any]:
        with self._conn() as c:
            row = c.execute("SELECT * FROM projects WHERE id = ?", (pid,)).fetchone()
        if row is None:
            raise NotFound(f"project {pid!r} not found")
        return dict(row)

    def delete_project(self, pid: str) -> None:
        self.project(pid)
        with self._conn() as c:
            c.execute("DELETE FROM experiments WHERE project_id = ?", (pid,))
            c.execute("DELETE FROM models WHERE project_id = ?", (pid,))
            c.execute("DELETE FROM projects WHERE id = ?", (pid,))
        target = (self.home / "projects" / pid).resolve()
        if target.parent == (self.home / "projects").resolve() and target.is_dir():
            shutil.rmtree(target)
        self.audit("project.delete", {"id": pid})

    # ------------------------------------------------------------------ models

    def new_model_dir(self, pid: str) -> tuple[str, Path]:
        self.project(pid)
        mid = self._next_id("MDL")
        path = self.home / "projects" / pid / "models" / mid
        path.mkdir(parents=True)
        return mid, path

    def register_model(self, mid: str, pid: str, name: str, kind: str, synthetic: bool,
                       directory: Path) -> dict[str, Any]:
        with self._conn() as c:
            c.execute("INSERT INTO models VALUES(?, ?, ?, ?, ?, ?, ?)",
                      (mid, pid, name, kind, int(synthetic), str(directory), _now()))
        self.audit("model.register", {"id": mid, "project": pid, "kind": kind})
        return self.model(mid)

    def models(self, pid: str | None = None) -> list[dict[str, Any]]:
        q = "SELECT * FROM models" + (" WHERE project_id = ?" if pid else "") + \
            " ORDER BY created DESC"
        with self._conn() as c:
            return [dict(r) for r in c.execute(q, (pid,) if pid else ())]

    def model(self, mid: str) -> dict[str, Any]:
        with self._conn() as c:
            row = c.execute("SELECT * FROM models WHERE id = ?", (mid,)).fetchone()
        if row is None:
            raise NotFound(f"model {mid!r} not found")
        return dict(row)

    # ------------------------------------------------------------------ experiments

    def new_experiment_dir(self, pid: str) -> tuple[str, Path]:
        eid = self._next_id("EXP")
        return eid, self.home / "projects" / pid / "experiments" / eid

    def register_experiment(self, eid: str, pid: str, mid: str, name: str,
                            directory: Path) -> dict[str, Any]:
        with self._conn() as c:
            c.execute("INSERT INTO experiments VALUES(?, ?, ?, ?, ?, ?, ?, ?)",
                      (eid, pid, mid, name, "created", str(directory), None, _now()))
        self.audit("experiment.create", {"id": eid, "model": mid})
        return self.experiment(eid)

    def update_experiment(self, eid: str, status: str,
                          summary: dict[str, Any] | None = None) -> None:
        with self._conn() as c:
            if summary is None:
                c.execute("UPDATE experiments SET status = ? WHERE id = ?", (status, eid))
            else:
                c.execute("UPDATE experiments SET status = ?, summary = ? WHERE id = ?",
                          (status, json.dumps(summary), eid))

    def experiments(self, pid: str | None = None) -> list[dict[str, Any]]:
        q = "SELECT * FROM experiments" + (" WHERE project_id = ?" if pid else "") + \
            " ORDER BY created DESC"
        with self._conn() as c:
            rows = [dict(r) for r in c.execute(q, (pid,) if pid else ())]
        for r in rows:
            r["summary"] = json.loads(r["summary"]) if r["summary"] else None
        return rows

    def experiment(self, eid: str) -> dict[str, Any]:
        with self._conn() as c:
            row = c.execute("SELECT * FROM experiments WHERE id = ?", (eid,)).fetchone()
        if row is None:
            raise NotFound(f"experiment {eid!r} not found")
        out = dict(row)
        out["summary"] = json.loads(out["summary"]) if out["summary"] else None
        return out


    # ------------------------------------------------------------------ artifacts
    # scans, process batches, adaptive runs, workspace maps, degradation projections,
    # hardware sessions, challenges, root-cause investigations, benchmark runs

    PREFIX = {"scan": "SCN", "batch": "BAT", "adaptive": "ADP", "workspace": "WSM",
              "degradation": "DEG", "hardware": "HWS", "challenge": "CHL", "rootcause": "RCA",
              "benchmark": "BEN", "fidelity": "FID"}

    def new_artifact(self, kind: str, project_id: str, name: str, model_id: str | None = None,
                     experiment_id: str | None = None) -> tuple[str, Path]:
        self.project(project_id)
        aid = self._next_id(self.PREFIX[kind])
        directory = self.home / "projects" / project_id / "artifacts" / aid
        directory.mkdir(parents=True)
        with self._conn() as c:
            c.execute("INSERT INTO artifacts VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                      (aid, project_id, model_id, experiment_id, kind, name, "created",
                       str(directory), None, _now()))
        self.audit(f"{kind}.create", {"id": aid, "model": model_id})
        return aid, directory

    def update_artifact(self, aid: str, status: str, summary: dict[str, Any] | None = None
                        ) -> None:
        with self._conn() as c:
            c.execute("UPDATE artifacts SET status = ?, summary = COALESCE(?, summary) "
                      "WHERE id = ?", (status, None if summary is None else
                                       json.dumps(summary, default=str), aid))

    def artifact(self, aid: str) -> dict[str, Any]:
        with self._conn() as c:
            row = c.execute("SELECT * FROM artifacts WHERE id = ?", (aid,)).fetchone()
        if row is None:
            raise NotFound(f"{aid!r} not found")
        out = dict(row)
        out["summary"] = json.loads(out["summary"]) if out["summary"] else None
        return out

    def artifacts(self, kind: str | None = None, project_id: str | None = None,
                  model_id: str | None = None) -> list[dict[str, Any]]:
        q, args = "SELECT * FROM artifacts WHERE 1=1", []
        for col, val in (("kind", kind), ("project_id", project_id), ("model_id", model_id)):
            if val is not None:
                q += f" AND {col} = ?"
                args.append(val)
        with self._conn() as c:
            rows = [dict(r) for r in c.execute(q + " ORDER BY created DESC", args)]
        for r in rows:
            r["summary"] = json.loads(r["summary"]) if r["summary"] else None
        return rows

    def save_json(self, aid: str, name: str, data: Any) -> Path:
        path = Path(self.artifact(aid)["directory"]) / f"{name}.json"
        path.write_text(json.dumps(data, default=_json_default), encoding="utf-8")
        return path

    def load_json(self, aid: str, name: str) -> Any:
        path = Path(self.artifact(aid)["directory"]) / f"{name}.json"
        if not path.is_file():
            raise NotFound(f"{aid} has no {name} yet")
        return json.loads(path.read_text(encoding="utf-8"))


def _json_default(o: Any) -> Any:
    import numpy as np

    if isinstance(o, np.ndarray):
        return o.tolist()
    if isinstance(o, np.generic):
        return o.item()
    raise TypeError(f"not JSON serialisable: {type(o).__name__}")
