# Getting started

1. `uv sync`, then `uv run motionproof doctor` to check the environment.
2. `uv run motionproof serve --home workspace` and open http://127.0.0.1:8000. There is
   no sign-in on your own computer: you work in the workspace of the first account (a fresh
   workspace gets one automatically). `--require-sign-in` asks for an account again.
3. A **Demo** project with the reference design is made on the first start (once; it does not
   come back if you delete it). It is synthetic and labelled as such everywhere. Or create your
   own project and import a model (CAD import).
4. Assembly workbench: inspect components, move joints, read the readiness report.
5. Features and datums, then Tolerances: register what your drawings specify.
6. Virtual assemblies: generate variants and see fits, backlash and deviations per variant.
7. Mechanical model: enter motor and gearbox data; run a task on the nominal assembly.
8. Experiment builder: sampling, task, constraints; launch and watch the live monitor.
9. Robustness, Sensitivity, Worst case, Tolerance optimisation, Design comparison.
10. Reports: download PDF, Markdown, JSON or CSV; replay any scenario.

The same workflow is available from the command line (`docs/cli-reference.md`).
