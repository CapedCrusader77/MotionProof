"""Virtual manufacturing experiments: immutable manifests, checkpointed runs and replay.

An experiment directory contains

* ``manifest.json`` - frozen snapshot: model specification, fingerprints, configuration,
  the complete design matrix, software versions. Written once and never modified.
* ``results.jsonl`` - one line per finished scenario, appended as the run progresses. An
  interrupted run resumes after the last complete line.
"""

from __future__ import annotations

import json
import os
import platform
import threading
import time
from collections.abc import Callable, Iterator
from concurrent.futures import ProcessPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import mujoco
import numpy as np
import scipy
from pydantic import BaseModel, ConfigDict, Field

import motionproof
from motionproof.core.schema import Distribution, MechanicalModelSpec
from motionproof.model import MechanicalModel
from motionproof.simulation.tasks import Task, _Task
from motionproof.tolerances.sampling import SamplingMethod, VariableSpace

RESULT_TOLERANCE = 1e-9

FAILURE_CATEGORY = {
    "ee_error": "positioning", "angle_error": "positioning", "repeatability": "positioning",
    "direction_error": "positioning", "tracking_error": "trajectory",
    "lost_motion": "backlash", "backlash": "backlash", "transmission": "transmission",
    "torque": "torque_overload", "saturated": "torque_overload", "motor_speed": "velocity",
    "output_velocity": "velocity", "output_acceleration": "acceleration",
    "min_mesh": "mesh_interference", "min_fit": "clearance", "max_fit": "fit",
    "radial_play": "clearance", "settling": "trajectory", "task_duration": "trajectory",
}


class ExperimentError(RuntimeError):
    pass


class Constraint(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    metric: str
    op: Literal["<=", ">="]
    limit: float

    def check(self, value: float) -> tuple[bool, float]:
        """(passed, normalised margin). Positive margin means the requirement is met."""
        scale = abs(self.limit) if self.limit != 0 else 1.0
        margin = (self.limit - value) / scale if self.op == "<=" else (value - self.limit) / scale
        return margin >= 0, margin

    @property
    def category(self) -> str:
        for prefix, cat in FAILURE_CATEGORY.items():
            if self.metric.startswith(prefix):
                return cat
        return "performance"


class Sampling(BaseModel):
    model_config = ConfigDict(extra="forbid")
    method: SamplingMethod = "monte_carlo"
    samples: int = Field(default=100, ge=1, le=100_000)
    seed: int = 0
    replicates: int = Field(default=1, ge=1, le=64,
                            description="independent randomised repeats of the design")


class ExperimentConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    task: Task
    sampling: Sampling = Sampling()
    operating: dict[str, Distribution] = Field(default_factory=dict)
    constraints: list[Constraint] = Field(default_factory=list)
    fixed: dict[str, float] = Field(default_factory=dict,
                                    description="tolerance values pinned for every scenario")


OPERATING_VARIABLES = {"payload_mass", "speed_scale"}


def apply_operating(task: _Task, operating: dict[str, float]) -> _Task:
    unknown = set(operating) - OPERATING_VARIABLES
    if unknown:
        raise ExperimentError(f"unsupported operating variables: {sorted(unknown)}; "
                              f"supported: {sorted(OPERATING_VARIABLES)}")
    update: dict[str, Any] = {}
    if "payload_mass" in operating:
        update["payload_mass"] = max(float(operating["payload_mass"]), 0.0)
    scale = float(operating.get("speed_scale", 1.0))
    if scale != 1.0:
        if scale <= 0:
            raise ExperimentError("speed_scale must be positive")
        for name in ("duration", "move_time"):
            if hasattr(task, name) and type(task).__name__ != "StaticHold":
                update[name] = getattr(task, name) / scale
    return task.model_copy(update=update)


def evaluate_scenario(model: MechanicalModel, config: ExperimentConfig,
                      row: dict[str, float], keep_trace: bool = False) -> dict[str, Any]:
    """Build the variant for one design row, simulate the task and judge the constraints."""
    values = {k: v for k, v in row.items() if not k.startswith("op.")}
    values.update(config.fixed)
    operating = {k[3:]: v for k, v in row.items() if k.startswith("op.")}
    variant = model.variant(values)
    result = model.engine.run(variant, apply_operating(config.task, operating), keep_trace)
    checks: dict[str, dict[str, Any]] = {}
    failures: list[dict[str, Any]] = []
    if result.valid:
        for c in config.constraints:
            if c.metric not in result.metrics:
                raise ExperimentError(
                    f"constraint {c.name!r}: metric {c.metric!r} is not produced by task "
                    f"{config.task.type!r}; available: {sorted(result.metrics)}")
            value = result.metrics[c.metric]
            ok, margin = c.check(value)
            checks[c.name] = {"value": value, "passed": ok, "margin": margin}
            if not ok:
                failures.append({
                    "category": c.category, "severity": "requirement_violation",
                    "constraint": f"{c.metric} {c.op} {c.limit:g}", "name": c.name,
                    "value": value, "limit": c.limit, "evidence": "model_predicted"})
    for v in variant.violations:
        failures.append({"category": v["category"], "severity": "assembly_violation",
                         "constraint": v["message"], "name": v["subject"],
                         "evidence": "model_predicted"})
    out: dict[str, Any] = {
        "values": variant.values, "operating": operating, "valid": result.valid,
        "message": result.message, "metrics": result.metrics, "constraints": checks,
        "failures": failures, "out_of_spec": variant.out_of_spec,
        "passed": bool(result.valid and not failures),
        "joints": {k: {"backlash": j.backlash, "radial_play": j.radial_play,
                       "efficiency": j.efficiency, "friction": j.friction,
                       "tilt_x": j.tilt_x, "tilt_y": j.tilt_y, "offset": list(j.offset)}
                   for k, j in variant.joints.items()},
    }
    if keep_trace:
        out["trace"] = result.trace
        out["measurements"] = result.measurements
        out["variant"] = variant.to_dict()
    return out


def default_workers() -> int:
    """Worker processes for an experiment: ``MOTIONPROOF_WORKERS`` if set, otherwise half the
    CPU cores, at most 4 (each worker holds its own MuJoCo model, a few hundred MB)."""
    env = os.environ.get("MOTIONPROOF_WORKERS", "").strip()
    if env:
        return max(1, int(env))
    return max(1, min(4, (os.cpu_count() or 2) // 2))


MIN_PARALLEL = 100  # scenarios left before a run uses worker processes

# --- process-pool workers: each process rebuilds the snapshotted model once
_WORKER: dict[str, Any] = {}


def _worker_init(spec: dict[str, Any], directory: str, config: dict[str, Any]) -> None:
    _WORKER["model"] = MechanicalModel(MechanicalModelSpec.model_validate(spec), Path(directory))
    _WORKER["config"] = ExperimentConfig.model_validate(config)


def _worker_eval(row: dict[str, float]) -> dict[str, Any]:
    return evaluate_scenario(_WORKER["model"], _WORKER["config"], row)


def versions() -> dict[str, str]:
    return {"motionproof": motionproof.__version__, "mujoco": mujoco.__version__,
            "numpy": np.__version__, "scipy": scipy.__version__,
            "python": platform.python_version(), "platform": platform.platform()}


class Experiment:
    """An experiment bound to a directory. Create with ``Experiment.create`` or ``open``."""

    def __init__(self, directory: Path, manifest: dict[str, Any]):
        self.directory = directory
        self.manifest = manifest
        self.config = ExperimentConfig.model_validate(manifest["config"])
        self.names: list[str] = manifest["design"]["names"]

    # ------------------------------------------------------------------ creation

    @classmethod
    def create(cls, model: MechanicalModel, config: ExperimentConfig, directory: str | Path,
               experiment_id: str | None = None) -> Experiment:
        out = Path(directory)
        if (out / "manifest.json").exists():
            raise ExperimentError(f"{out} already holds an experiment; manifests are immutable")
        space = VariableSpace.from_model(model.spec, config.operating)
        unknown = set(config.fixed) - {t.id for t in model.spec.tolerances}
        if unknown:
            raise ExperimentError(f"fixed values refer to unknown tolerances: {sorted(unknown)}")
        rows: list[list[float]] = []
        replicate: list[int] = []
        notes: list[str] = []
        independent = True
        for r in range(config.sampling.replicates):
            design = space.design(config.sampling.method, config.sampling.samples,
                                  config.sampling.seed + r)
            rows.extend(design.values.tolist())
            replicate.extend([r] * len(design.values))
            independent = design.independent
            if design.note and design.note not in notes:
                notes.append(design.note)
        # fail early on a constraint that the chosen task cannot evaluate
        evaluate_scenario(model, config, dict(zip(space.names, space.nominal(), strict=True)))
        manifest = {
            "schema": "motionproof.experiment/1",
            "id": experiment_id or out.name,
            "name": config.name,
            "created": datetime.now(UTC).isoformat(timespec="seconds"),
            "model": {
                "name": model.spec.name, "synthetic": model.spec.synthetic,
                "fingerprint": model.fingerprint,
                "geometry_fingerprint": model.geometry_fingerprint(),
                "fidelity": model.spec.fidelity.value,
                "spec": model.spec.model_dump(mode="json", by_alias=True),
                "directory": str(model.directory),
            },
            "config": config.model_dump(mode="json"),
            "design": {
                "names": space.names, "values": rows, "replicate": replicate,
                "independent": independent, "notes": notes,
                "correlation": None if space.correlation is None else space.correlation.tolist(),
            },
            "versions": versions(),
        }
        out.mkdir(parents=True, exist_ok=True)
        (out / "manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
        return cls(out, manifest)

    @classmethod
    def open(cls, directory: str | Path) -> Experiment:
        path = Path(directory) / "manifest.json"
        if not path.is_file():
            raise ExperimentError(f"no experiment manifest in {directory}")
        return cls(Path(directory), json.loads(path.read_text(encoding="utf-8")))

    # ------------------------------------------------------------------ data

    @property
    def total(self) -> int:
        return len(self.manifest["design"]["values"])

    @property
    def results_path(self) -> Path:
        return self.directory / "results.jsonl"

    def row(self, index: int) -> dict[str, float]:
        return dict(zip(self.names, self.manifest["design"]["values"][index], strict=True))

    def results(self) -> list[dict[str, Any]]:
        if not self.results_path.exists():
            return []
        out = []
        with self.results_path.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        out.append(json.loads(line))
                    except json.JSONDecodeError:
                        break  # truncated final line from an interrupted run
        return out

    def model(self) -> MechanicalModel:
        """Rebuild the model exactly as snapshotted (not as the model file is today)."""
        snap = self.manifest["model"]
        spec = MechanicalModelSpec.model_validate(snap["spec"])
        return MechanicalModel(spec, Path(snap["directory"]))

    # ------------------------------------------------------------------ execution

    def run(self, model: MechanicalModel | None = None,
            progress: Callable[[dict[str, Any]], None] | None = None,
            cancel: threading.Event | None = None,
            workers: int | None = None) -> dict[str, Any]:
        """Run the remaining scenarios. ``workers`` > 1 evaluates them in that many processes;
        results are written in scenario order and are identical to a one-process run, because
        every scenario is fully determined by its design row."""
        model = model or self.model()
        workers = default_workers() if workers is None else max(1, workers)
        if model.fingerprint != self.manifest["model"]["fingerprint"]:
            raise ExperimentError(
                "the model differs from the one this experiment was created with; results of "
                "different model revisions must not be mixed - create a new experiment")
        done = self.results()
        # drop a possibly truncated tail so the file only holds complete records
        if self.results_path.exists():
            with self.results_path.open("w", encoding="utf-8") as f:
                for r in done:
                    f.write(json.dumps(r) + "\n")
        counts = {"passed": sum(r["passed"] for r in done),
                  "failed": sum((not r["passed"]) and r["valid"] for r in done),
                  "invalid": sum(not r["valid"] for r in done)}
        started = time.perf_counter()
        status = "completed"
        todo = list(range(len(done), self.total))
        with self.results_path.open("a", encoding="utf-8") as f:
            for index, res in self._evaluate(model, todo, workers, cancel):
                if res is None:
                    status = "cancelled"
                    break
                res["id"] = f"S{index + 1:06d}"
                res["index"] = index
                res["replicate"] = self.manifest["design"]["replicate"][index]
                f.write(json.dumps(res) + "\n")
                f.flush()
                key = "invalid" if not res["valid"] else "passed" if res["passed"] else "failed"
                counts[key] += 1
                if progress is not None:
                    progress({"done": index + 1, "total": self.total, **counts,
                              "current": res["id"],
                              "elapsed": time.perf_counter() - started})
        return {"status": status, "done": sum(counts.values()), "total": self.total, **counts,
                "elapsed": time.perf_counter() - started}

    def _evaluate(self, model: MechanicalModel, todo: list[int], workers: int,
                  cancel: threading.Event | None
                  ) -> Iterator[tuple[int, dict[str, Any] | None]]:
        """Yield ``(index, result)`` in scenario order; ``(index, None)`` once cancelled."""
        # each worker process needs about 8 s to start on Windows; below ~100 scenarios a single
        # process finishes first (measured: 64 scenarios 24 s serial, 67 s with 4 workers;
        # 400 scenarios 215 s serial, 105 s with 4 workers)
        if workers <= 1 or len(todo) < MIN_PARALLEL:
            for index in todo:
                if cancel is not None and cancel.is_set():
                    yield index, None
                    return
                yield index, evaluate_scenario(model, self.config, self.row(index))
            return
        snap = self.manifest["model"]
        batch = workers * 4  # check for cancellation between batches
        with ProcessPoolExecutor(max_workers=workers, initializer=_worker_init,
                                 initargs=(snap["spec"], snap["directory"],
                                           self.manifest["config"])) as pool:
            for start in range(0, len(todo), batch):
                if cancel is not None and cancel.is_set():
                    yield todo[start], None
                    return
                chunk = todo[start:start + batch]
                for index, res in zip(chunk, pool.map(_worker_eval, [self.row(i) for i in chunk]),
                                      strict=True):
                    yield index, res

    def replay(self, scenario_id: str, model: MechanicalModel | None = None) -> dict[str, Any]:
        """Re-run one stored scenario with traces and compare against the stored metrics."""
        stored = next((r for r in self.results() if r["id"] == scenario_id), None)
        if stored is None:
            raise ExperimentError(f"scenario {scenario_id!r} has no stored result")
        model = model or self.model()
        fresh = evaluate_scenario(model, self.config, self.row(stored["index"]), keep_trace=True)
        diffs = {}
        for k, v in stored["metrics"].items():
            new = fresh["metrics"].get(k)
            if new is None or abs(new - v) > RESULT_TOLERANCE * max(1.0, abs(v)):
                diffs[k] = {"stored": v, "replayed": new}
        reproduced = (not diffs and fresh["passed"] == stored["passed"]
                      and fresh["valid"] == stored["valid"])
        return {"scenario": scenario_id, "reproduced": reproduced, "differences": diffs,
                "model_fingerprint_matches":
                    model.fingerprint == self.manifest["model"]["fingerprint"],
                "stored": stored, "replayed": fresh}

    def metric_matrix(self) -> tuple[np.ndarray, dict[str, np.ndarray], list[dict[str, Any]]]:
        """(design matrix of valid scenarios, metric arrays, the valid results)."""
        valid = [r for r in self.results() if r["valid"]]
        x = np.array([self.manifest["design"]["values"][r["index"]] for r in valid])
        keys = sorted(set.intersection(*(set(r["metrics"]) for r in valid))) if valid else []
        return x, {k: np.array([r["metrics"][k] for r in valid]) for k in keys}, valid
