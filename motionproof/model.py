"""``MechanicalModel``: a validated model file bound to its geometry and dynamics model."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import mujoco
import yaml
from pydantic import ValidationError

from motionproof.core.schema import MechanicalModelSpec
from motionproof.manufacturing.variants import Variant, nominal_values, resolve_variant
from motionproof.simulation.engine import Engine, SimResult
from motionproof.simulation.tasks import _Task


class ModelError(ValueError):
    pass


def _safe_child(root: Path, relative: str) -> Path:
    path = (root / relative).resolve()
    if root.resolve() not in path.parents and path != root.resolve():
        raise ModelError(f"path {relative!r} escapes the model directory")
    return path


class MechanicalModel:
    """A mechanical model: specification + geometry inventory + MuJoCo dynamics model."""

    def __init__(self, spec: MechanicalModelSpec, directory: Path):
        self.spec = spec
        self.directory = directory
        self.inventory: dict[str, Any] = {}
        src = spec.source
        self.xml_path: Path | None = None
        self.mj_model: mujoco.MjModel | None = None
        self.geometry_dir = directory / "geometry"
        if src.kind == "reference_design":
            from motionproof.reference import nema17_arm

            if src.generator != nema17_arm.GENERATOR:
                raise ModelError(f"unknown reference generator {src.generator!r}")
            if not (self.geometry_dir / "inventory.json").is_file():
                nema17_arm.write_geometry(self.geometry_dir, src.parameters or None)
            self.xml_path = self.geometry_dir / "model.xml"
        elif src.kind in ("mjcf", "urdf"):
            if not src.file:
                raise ModelError("source.file is required for mjcf/urdf models")
            self.xml_path = _safe_child(directory, src.file)
        inv = self.geometry_dir / "inventory.json"
        if inv.is_file():
            self.inventory = json.loads(inv.read_text(encoding="utf-8"))
        if self.xml_path is not None:
            if not self.xml_path.is_file():
                raise ModelError(f"dynamics model file not found: {self.xml_path}")
            try:
                self.mj_model = mujoco.MjModel.from_xml_path(str(self.xml_path))
            except ValueError as exc:
                raise ModelError(
                    f"MuJoCo could not compile {self.xml_path.name}: {exc}") from exc
        self._engine: Engine | None = None

    # ------------------------------------------------------------------ loading

    @classmethod
    def load(cls, path: str | Path) -> MechanicalModel:
        p = Path(path)
        if p.is_dir():
            p = p / "model.yaml"
        if not p.is_file():
            raise ModelError(f"model file not found: {p}")
        try:
            raw = yaml.safe_load(p.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            raise ModelError(f"{p.name} is not valid YAML: {exc}") from exc
        return cls.from_dict(raw, p.parent)

    @classmethod
    def from_dict(cls, raw: dict[str, Any], directory: str | Path) -> MechanicalModel:
        try:
            spec = MechanicalModelSpec.model_validate(raw)
        except ValidationError as exc:
            lines = [f"  {'.'.join(str(x) for x in e['loc'])}: {e['msg']}" for e in exc.errors()]
            raise ModelError("invalid model definition:\n" + "\n".join(lines)) from exc
        return cls(spec, Path(directory))

    def save(self) -> Path:
        path = self.directory / "model.yaml"
        data = self.spec.model_dump(mode="json", by_alias=True, exclude_none=True)
        path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
        return path

    # ------------------------------------------------------------------ identity

    @property
    def fingerprint(self) -> str:
        """Hash of the specification and the dynamics model file."""
        h = hashlib.sha256()
        h.update(json.dumps(self.spec.model_dump(mode="json", by_alias=True),
                            sort_keys=True).encode())
        if self.xml_path is not None:
            h.update(self.xml_path.read_bytes())
        return h.hexdigest()[:16]

    def geometry_fingerprint(self) -> str:
        h = hashlib.sha256()
        for f in sorted(self.geometry_dir.rglob("*")):
            if f.is_file() and f.suffix.lower() in {".stl", ".step", ".stp", ".obj", ".xml"}:
                h.update(f.name.encode())
                h.update(f.read_bytes())
        return h.hexdigest()[:16]

    # ------------------------------------------------------------------ behaviour

    @property
    def engine(self) -> Engine:
        if self.mj_model is None:
            raise ModelError("this model is geometry only: attach a dynamics model (MJCF or "
                             "URDF) before simulating")
        if self._engine is None:
            self._engine = Engine(self.spec, self.mj_model)
        return self._engine

    def nominal_variant(self) -> Variant:
        return resolve_variant(self.spec, nominal_values(self.spec))

    def variant(self, values: dict[str, float]) -> Variant:
        return resolve_variant(self.spec, {**nominal_values(self.spec), **values})

    def simulate(self, task: _Task, values: dict[str, float] | None = None,
                 keep_trace: bool = True) -> SimResult:
        return self.engine.run(self.variant(values or {}), task, keep_trace)

    def joint_names(self) -> list[str]:
        if self.mj_model is None:
            return []
        return [mujoco.mj_id2name(self.mj_model, mujoco.mjtObj.mjOBJ_JOINT, i)
                for i in range(self.mj_model.njnt)]

    def body_poses(self, pose: dict[str, float] | None = None,
                   values: dict[str, float] | None = None) -> dict[str, Any]:
        """World pose of every body for a joint configuration (viewer and comparison).

        With ``values`` the joint misalignment of that manufactured variant is applied.
        """
        if self.mj_model is None:
            return {"bodies": {}}
        if values is None or not self.spec.drives:
            model = self.mj_model
        else:
            model = self.engine.build_model(self.variant(values), 0.0)
        data = mujoco.MjData(model)
        for name, value in {**self.spec.held_joints, **(pose or {})}.items():
            jid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, name)
            if jid < 0:
                raise ModelError(f"unknown joint {name!r}")
            data.qpos[model.jnt_qposadr[jid]] = value
        mujoco.mj_kinematics(model, data)
        bodies = {}
        for b in range(model.nbody):
            name = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_BODY, b) or "world"
            bodies[name] = {"pos": data.xpos[b].tolist(), "quat": data.xquat[b].tolist()}
        joints = []
        for j in range(model.njnt):
            joints.append({
                "name": mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_JOINT, j),
                "anchor": data.xanchor[j].tolist(), "axis": data.xaxis[j].tolist(),
                "range": model.jnt_range[j].tolist() if model.jnt_limited[j] else None,
                "driven": mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_JOINT, j)
                in self.spec.drives})
        return {"bodies": bodies, "joints": joints}
