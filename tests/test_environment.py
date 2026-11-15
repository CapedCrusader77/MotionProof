"""Environment smoke tests: every core dependency imports and MuJoCo can step a model."""

import importlib

import mujoco
import pytest

MODULES = [
    "numpy", "scipy", "trimesh", "cadquery", "OCP", "shapely", "PIL",
    "mujoco", "glfw", "OpenGL", "yaml", "fastapi", "uvicorn", "pydantic",
    "pydantic_settings", "sqlalchemy", "alembic", "httpx", "multipart",
    "typer", "rich",
]


@pytest.mark.parametrize("name", MODULES)
def test_import(name: str) -> None:
    importlib.import_module(name)


def test_mujoco_version() -> None:
    assert mujoco.__version__ == "3.14.0"


def test_mujoco_steps() -> None:
    xml = (
        "<mujoco><worldbody><geom type='plane' size='1 1 .1'/>"
        "<body pos='0 0 1'><freejoint/><geom type='box' size='.1 .1 .1'/></body>"
        "</worldbody></mujoco>"
    )
    model = mujoco.MjModel.from_xml_string(xml)
    data = mujoco.MjData(model)
    for _ in range(100):
        mujoco.mj_step(model, data)
    assert data.qpos[2] < 1.0
