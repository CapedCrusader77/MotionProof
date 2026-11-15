"""Shared fixtures: a minimal analytic single-joint model and the reference design."""

from __future__ import annotations

import warnings
from pathlib import Path
from typing import Any

import pytest

from motionproof.model import MechanicalModel

warnings.filterwarnings("ignore", category=FutureWarning)

ARM_LENGTH = 0.30
ARM_MASS = 1.0

SINGLE_XML = f"""<mujoco model="single_joint">
  <compiler angle="radian"/>
  <option gravity="0 0 -9.81" timestep="0.0005" integrator="implicitfast"/>
  <worldbody>
    <body name="arm">
      <joint name="j" type="hinge" pos="0 0 0" axis="0 -1 0"/>
      <inertial pos="{ARM_LENGTH} 0 0" mass="{ARM_MASS}" diaginertia="1e-5 1e-5 1e-5"/>
    </body>
  </worldbody>
</mujoco>
"""


def single_joint_dict(**gearbox: Any) -> dict[str, Any]:
    """A point mass on a massless arm driven through one gearbox. Every value is a test value."""
    gb = {"ratio": 20.0, "efficiency": 1.0, "backlash": 0.0, "stiffness": 2000.0,
          "damping_ratio": 0.3, "source": "test", "confidence": "assumed"} | gearbox
    return {
        "schema": "motionproof.model/1", "name": "single joint", "synthetic": True,
        "source": {"kind": "mjcf", "file": "single.xml"},
        "tolerances": [{
            "id": "backlash_tol", "component": "gearbox", "parameter": "backlash",
            "characteristic": "backlash", "category": "assembly", "nominal": 0.0,
            "lower": 0.0, "upper": 0.02, "unit": "rad",
            "distribution": {"type": "uniform", "low": 0.0, "high": 0.02},
            "source": "test", "confidence": "assumed"}],
        "effects": [{"tolerance": "backlash_tol", "joint": "j", "target": "backlash"}],
        "drives": {"j": {
            "motor": {"continuous_torque": 1.0, "peak_torque": 2.0, "max_speed": 300.0,
                      "rotor_inertia": 1e-5, "source": "test", "confidence": "assumed"},
            "gearbox": gb, "controller": {"bandwidth": 40.0}}},
        "end_effector": {"body": "arm", "offset": [ARM_LENGTH, 0.0, 0.0]},
        "simulation": {"timestep": 5e-4},
    }


@pytest.fixture
def single_joint(tmp_path: Path):  # type: ignore[no-untyped-def]
    def make(gravity: bool = True, friction: float = 0.0, **gearbox: Any) -> MechanicalModel:
        (tmp_path / "single.xml").write_text(SINGLE_XML, encoding="utf-8")
        raw = single_joint_dict(**gearbox)
        raw["drives"]["j"]["friction"] = friction
        if not gravity:
            raw["simulation"]["gravity"] = [0.0, 0.0, 0.0]
        return MechanicalModel.from_dict(raw, tmp_path)

    return make


@pytest.fixture(scope="session")
def reference_model(tmp_path_factory: pytest.TempPathFactory) -> MechanicalModel:
    from motionproof.reference.nema17_arm import write_reference_project

    root = tmp_path_factory.mktemp("reference")
    return MechanicalModel.load(write_reference_project(root))
