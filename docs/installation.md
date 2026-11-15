# Installation

Requirements: Windows 10/11 or Linux, Python 3.12, `uv`, Node.js 24 for the web application.
No GPU, CUDA, Docker or database server is needed.

```bash
uv sync
```

```bash
uv run motionproof doctor
```

`doctor` imports every dependency and runs one reference simulation. Build the web application
once with `npm install` and `npm run build` in `frontend/`; `motionproof serve` then serves it.

The workspace location is `./workspace`, `--home <dir>`, or the `MOTIONPROOF_HOME` variable.
Exact dependency versions are in `uv.lock` and `docs/DEPENDENCY_VERSIONS.md`.
