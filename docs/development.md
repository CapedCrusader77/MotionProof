# Development

```bash
uv run ruff check motionproof tests benchmarks
```

```bash
uv run mypy motionproof
```

```bash
uv run pytest
```

```bash
cd frontend && npm run typecheck && npm run build && npm run e2e
```

`npm run e2e` starts its own backend on port 8765 with a fresh workspace. Set
`MP_E2E_CHANNEL=chrome` to use an installed Chrome instead of Playwright's Chromium. On
Windows, stop `motionproof serve` before `uv run pytest` (see
[`CONTRIBUTING.md`](../CONTRIBUTING.md)).
