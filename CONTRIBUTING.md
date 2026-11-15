# Contributing

```bash
uv sync
```

```bash
uv run pytest
```

```bash
uv run ruff check motionproof tests
```

Frontend: `npm install`, then `npm run build` in `frontend/`.

Rules for changes:

* Every numerical method needs a test against an analytic value or an independent calculation.
  State the expected value and the accepted tolerance in the test.
* A bug fix comes with a regression test. Do not loosen a threshold to make a test pass.
* Never add default tolerance, motor or measurement values that could be mistaken for real
  data. Placeholder values must be labelled `assumed`.
* State the modelling level (A or C) and fidelity of anything that produces a result.
* Documentation describes what is implemented. Planned work belongs in `TECHNICAL_ROADMAP.md`.
* Update `DEVELOPMENT_STATUS.md` when something is verified or found broken.
