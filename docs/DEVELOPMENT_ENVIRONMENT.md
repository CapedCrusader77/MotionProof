# MotionProof Development Environment

## Locations
| Item | Path |
|---|---|
| Project | `E:\Projects\MotionProof` |
| Python venv | `E:\Projects\MotionProof\.venv` (CPython 3.12.14, uv-managed) |
| Frontend | `E:\Projects\MotionProof\frontend` (`node_modules` local) |
| Verification script | `scripts/verify_cad_to_mujoco.py` |
| Tests | `tests/` |

Nothing is installed globally. System PATH, system Python and other projects (SCRAPP) were not modified.

## Daily commands
Run from `E:\Projects\MotionProof` in PowerShell.
```powershell
uv sync                                  # recreate env from uv.lock
uv run pytest                            # tests (with coverage: uv run pytest --cov=.)
uv run ruff check .                      # lint
uv run mypy tests                        # types (strict)
uv run python scripts/verify_cad_to_mujoco.py   # CAD -> MuJoCo pipeline check
cd frontend; npm install; npm run dev    # Vite dev server on :5173
cd frontend; npm run build               # production build
```
To add a package: `uv add <pkg>` (dev tools: `uv add --dev <pkg>`).

## Stack
- **Geometry:** CadQuery/OCP (STEP read/write, B-rep), Trimesh (STL, mesh validation, mass properties), Shapely, NumPy/SciPy (transforms, rotations, quaternions via `scipy.spatial.transform`).
- **Simulation:** MuJoCo 3.14.0, with glfw and PyOpenGL for rendering.
- **Backend:** FastAPI, Uvicorn, Pydantic, SQLAlchemy and Alembic on SQLite, HTTPX, Typer, Rich.
- **Frontend:** React, TypeScript, Vite, three.js with react-three-fiber and drei, Zustand, Axios, Recharts, Lucide.
- **Quality:** pytest, pytest-cov, ruff, mypy (configured in `pyproject.toml`; `scripts/` and `frontend/` excluded from ruff/mypy).

## Rules learned during setup
- Write an explicit `<inertial>` or use `inertia="exact"` for mesh bodies; MuJoCo's default `legacy` mode is wrong for non-convex parts.
- CAD units are mm and MuJoCo is SI; apply mesh `scale="0.001"` and convert mass properties.
- Use separate visual (`contype=0 conaffinity=0`) and convex collision geoms.
- Joint axes, limits, actuators and densities must be specified manually; STEP/STL do not carry them.
- Pinocchio is deliberately absent (it conflicts with NumPy 2.5).

## Not installed
CUDA Toolkit, PyTorch, Ollama, Docker Desktop, PostgreSQL, WSL2, FreeCAD, Pinocchio.

## Status
See `INSTALLATION_REPORT.md` for test results and known issues, `CAD_TO_MUJOCO_TEST.md` for the pipeline test and `DEPENDENCY_VERSIONS.md` for exact versions. Autodesk Fusion integration is not yet verified.
