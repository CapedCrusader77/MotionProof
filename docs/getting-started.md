# Getting started

1. `uv sync`, then `uv run motionproof doctor` to check the environment.
2. `uv run motionproof serve --home workspace` and open http://127.0.0.1:8000. Create an
   account on the sign-in page; the first account keeps any projects already in the workspace,
   later accounts start with their own empty workspace.
3. Create a project. Either import a model (CAD import) or add the reference design, which is
   synthetic and labelled as such everywhere.
4. Assembly workbench: inspect components, move joints, read the readiness report.
5. Features and datums, then Tolerances: register what your drawings specify.
6. Virtual assemblies: generate variants and see fits, backlash and deviations per variant.
7. Mechanical model: enter motor and gearbox data; run a task on the nominal assembly.
8. Experiment builder: sampling, task, constraints; launch and watch the live monitor.
9. Robustness, Sensitivity, Worst case, Tolerance optimisation, Design comparison.
10. Reports: download PDF, Markdown, JSON or CSV; replay any scenario.

The same workflow is available from the command line (`docs/cli-reference.md`).
