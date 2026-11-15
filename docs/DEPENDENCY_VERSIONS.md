# Dependency Versions

Captured 2026-11-14 from `E:\Projects\MotionProof`. Exact pins are in `uv.lock` (Python) and `frontend/package-lock.json` (npm).

## Runtime
| Tool | Version |
|---|---|
| Python (uv-managed CPython) | 3.12.14 |
| uv | 0.12.5 |
| Node.js / npm | 24.19.0 / 11.17.0 |

## Python direct dependencies (24)
| Package | Version |
|---|---|
| alembic | 1.20.1 |
| cadquery | 2.8.0 |
| fastapi | 0.162.7 |
| glfw | 2.11.0 |
| httpx | 0.28.1 |
| mujoco | 3.14.0 |
| mypy | 2.4.1 |
| numpy | 2.5.4 |
| pillow | 13.0.0 |
| pydantic | 2.14.3 |
| pydantic-settings | 2.16.3 |
| pyopengl | 3.1.10 |
| pytest | 9.2.0 |
| pytest-cov | 7.1.0 |
| python-multipart | 0.0.33 |
| pyyaml | 6.0.3 |
| rich | 15.0.0 |
| ruff | 0.17.5 |
| scipy | 1.18.1 |
| shapely | 2.2.0 |
| sqlalchemy | 2.1.8 |
| trimesh | 5.2.1 |
| typer | 0.29.1 |
| uvicorn | 0.54.0 |

## Python transitive dependencies (70)
| Package | Version |
|---|---|
| absl-py | 2.5.1 |
| aiohappyeyeballs | 2.7.1 |
| aiohttp | 3.14.5 |
| aiosignal | 1.4.0 |
| annotated-doc | 0.0.6 |
| annotated-types | 0.8.0 |
| anyio | 4.16.0 |
| ast-serialize | 0.13.1 |
| attrs | 26.1.0 |
| cadquery-ocp | 7.9.3.1.1 |
| cadquery-ocp-proxy | 7.9.3.1.1 |
| casadi | 3.8.2 |
| certifi | 2026.10.23 |
| click | 8.5.1 |
| colorama | 0.4.6 |
| contourpy | 1.4.0 |
| coverage | 7.17.3 |
| cycler | 0.12.1 |
| etils | 1.15.0 |
| ezdxf | 1.4.5 |
| fonttools | 4.68.0 |
| frozenlist | 1.8.0 |
| fsspec | 2026.9.0 |
| h11 | 0.16.0 |
| httpcore | 1.0.9 |
| idna | 3.20 |
| iniconfig | 2.3.1 |
| kiwisolver | 1.5.1 |
| librt | 0.16.0 |
| llvmlite | 0.50.0 |
| mako | 1.4.3 |
| markdown-it-py | 4.3.0 |
| markupsafe | 3.0.4 |
| matplotlib | 3.11.2 |
| mdurl | 0.1.2 |
| more-itertools | 11.2.1 |
| msgpack | 1.2.4 |
| multidict | 7.2.1 |
| multimethod | 1.12 |
| mypy-extensions | 1.2.0 |
| nlopt | 2.11.0 |
| numba | 0.68.1 |
| opentelemetry-api | 1.45.2 |
| packaging | 26.3 |
| pathspec | 1.1.1 |
| pluggy | 1.7.0 |
| propcache | 0.5.4 |
| pydantic-core | 2.50.4 |
| pygments | 2.21.0 |
| pyparsing | 3.3.3 |
| python-dateutil | 4.0.0 |
| python-dotenv | 1.2.4 |
| runtype | 0.5.3 |
| shellingham | 1.5.4 |
| starlette | 1.10.0 |
| trame | 4.0.0 |
| trame-client | 4.1.4 |
| trame-common | 1.2.9 |
| trame-components | 2.5.0 |
| trame-server | 4.1.2 |
| trame-vtk | 2.11.17 |
| trame-vuetify | 3.3.0 |
| typing-extensions | 4.16.0 |
| typing-inspection | 0.4.5 |
| tzdata | 2026.6 |
| vtk | 9.6.2 |
| websockets | 17.4 |
| wslink | 2.6.0 |
| yarl | 1.25.1 |
| zipp | 4.1.2 |

## Frontend direct dependencies (`frontend/`)
```
motionproof-frontend@0.1.0 E:\Projects\MotionProof\frontend
+-- @react-three/drei@10.7.9
+-- @react-three/fiber@9.8.2
+-- @types/react-dom@19.3.0
+-- @types/react@19.3.0
+-- @types/three@0.187.0
+-- @vitejs/plugin-react@6.3.0
+-- axios@1.21.1
+-- lucide-react@1.73.0
+-- react-dom@19.3.1
+-- react@19.3.1
+-- recharts@3.10.1
+-- three@0.187.0
+-- typescript@7.0.2
+-- vite@8.3.8
`-- zustand@5.1.0
```

## Deliberately not installed
Pinocchio (`pin` 3.4.0 resolves, but would downgrade NumPy 2.5.4 to 2.3.5, so it was skipped), PyTorch, CUDA Toolkit, Docker, PostgreSQL, WSL2, FreeCAD, Ollama.
