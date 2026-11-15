# Installation Report

Date: 2026-11-14. Machine: Windows 11 Home SL 10.0.26300, Intel Core 7 240H, 15.7 GB RAM, RTX 5050 Laptop (8 GB), NVIDIA driver 596.08.

## Pre-flight
- `E:\Projects\MotionProof` existed and was empty. E: had 50.5 GB free.
- Free RAM was 0.9–2.1 GB over several checks. Installation started at 2.1 GB after the user confirmed. No installation or test step failed from memory pressure.

## Protection rules — honoured
No changes to SCRAPP, its venvs, system Python, Fusion, drivers, PATH or global Python packages. Everything lives in `E:\Projects\MotionProof` (`.venv`, `frontend/node_modules`) plus uv's package cache. Test artefacts were created in temp directories and not kept in any existing project.

## What was installed
| Area | Result |
|---|---|
| Python env | uv project, `.venv` on CPython 3.12.14. `.python-version`, `pyproject.toml`, `uv.lock` created |
| CAD / geometry | NumPy, SciPy, Trimesh, CadQuery 2.8.0 (OCP 7.9.3.1.1), Shapely, Pillow. Installed from pip wheels, so the conda fallback was not needed |
| Simulation | mujoco 3.14.0, glfw, PyOpenGL, PyYAML |
| Backend | FastAPI, Uvicorn, Pydantic, Pydantic Settings, SQLAlchemy, Alembic, HTTPX, python-multipart, Typer, Rich |
| QA | pytest, pytest-cov, ruff, mypy (configured in `pyproject.toml`) |
| Frontend | `frontend/`: Vite, React, TypeScript, three, @react-three/fiber, @react-three/drei, Zustand, Axios, Recharts, Lucide React |

Full package list with exact versions: `DEPENDENCY_VERSIONS.md`.

Side effect: CadQuery pulled in VTK, matplotlib, numba, casadi, nlopt, ezdxf and trame as its own dependencies (about 70 transitive packages). These were not requested but are required by CadQuery 2.8.0.

## Verification results
| Test | Result |
|---|---|
| CAD → STEP/STL → Trimesh → MJCF → MuJoCo | 23/23 passed (`CAD_TO_MUJOCO_TEST.md`) |
| `pytest` (23 import and MuJoCo-step tests) | 23 passed, 1 warning (`multipart` import name deprecation) |
| `ruff check` | passed (`scripts/` and `frontend/` excluded) |
| `mypy --strict` on `tests/` | passed (`scripts/` excluded) |
| Backend smoke (temp app, not saved in project) | imports OK; real uvicorn launched; `GET /health` 200; valid POST 200; invalid POST 422; SQLite create/read OK |
| Frontend production build (`npm run build`) | succeeded; 1.16 MB JS (317 kB gzip), 0 npm vulnerabilities |
| Vite dev server and 3D scene | served HTTP 200; React rendered; WebGL canvas rendered a lit cube on a grid; orbit/zoom changed the camera view |

## GPU checks
- `nvidia-smi`: NVIDIA GeForce RTX 5050 Laptop GPU, driver 596.08, 8151 MiB, detected and working.
- MuJoCo offscreen render works, but OpenGL reports **Intel(R) Graphics (4.6)**, not the RTX 5050. Windows Optimus routes the process to the integrated GPU. Not changed, as instructed. CUDA Toolkit and PyTorch were not installed.
- A trivial one-sphere render returned an all-black frame in my probe. The earlier audit scene with a light and several geoms rendered 66,354 non-black pixels, so I attribute this to the unlit default camera framing. I did not investigate further.

## Remaining issues and limitations
1. **Fusion integration is unverified.** No Fusion-exported assembly has been tested.
2. **Pinocchio not installed.** The `pin` wheel resolves but would downgrade NumPy 2.5.4 to 2.3.5, so it was skipped. Basic kinematics can use NumPy/SciPy.
3. **MuJoCo default mesh inertia is wrong for non-convex parts** (+7.6 % in the test); always supply explicit inertia or `inertia="exact"`.
4. **MuJoCo renders on the Intel GPU** until a Windows graphics preference is set (needs your approval).
5. **Frontend bundle** exceeds 500 kB (Vite warning); code-splitting needed later.
6. **Browser camera test** used synthetic drag/scroll, which showed the view change but is not a full interaction test.
7. **Python dependency versions are lower-bound pins** (`>=`) in `pyproject.toml`; `uv.lock` pins exact versions. `mujoco` is pinned `==3.14.0`.
8. `uv` warned about hardlinking across drives, so it used full copies (`UV_LINK_MODE=copy`). This is harmless but uses more disk.
9. The `frontend/` project was written by hand (not `npm create vite`); it is minimal and has no lint config.
