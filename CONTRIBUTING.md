# Contributing

```bash
uv sync
```

```bash
uv run pytest
```

On Windows, stop `motionproof serve` first: `uv run` reinstalls the package and cannot replace
`motionproof.exe` while the server holds it (`os error 32`). Or run the tests without the
reinstall: `.venv\Scripts\python -m pytest`.

```bash
uv run ruff check motionproof tests
```

Frontend: `npm install`, then `npm run build` in `frontend/`.

Two tools in `frontend/tools/` run against a server started on a copy of a workspace that holds
the reference design (the first account registered owns it; see the header of each file):

* `audit-contrast.mjs` checks text contrast (WCAG AA) on ten screens in both themes; run it after
  any colour change.
* `capture-screens.mjs` takes the product screenshots used by the README and the homepage; then
  run `uv run python scripts/make_tour.py` to rebuild the README tour GIF.

Rules for changes:

* Every numerical method needs a test against an analytic value or an independent calculation.
  State the expected value and the accepted tolerance in the test.
* A bug fix comes with a regression test. Do not loosen a threshold to make a test pass.
* Never add default tolerance, motor or measurement values that could be mistaken for real
  data. Placeholder values must be labelled `assumed`.
* State the modelling level (A or C) and fidelity of anything that produces a result.
* Documentation describes what is implemented. Planned work belongs in an issue, not in the docs.
* Update `docs/development-status.md` when something is verified or found broken.
