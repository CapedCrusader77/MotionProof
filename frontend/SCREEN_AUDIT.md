# Screen audit

Every screen was captured before and after the redesign at 1440 × 900 (light), after at 1440 × 900 dark and 390 × 844, with `scripts/capture_screens.mjs` against a seeded workspace. All 29 screens rendered after the change with no page errors and no horizontal overflow at any of the three sizes, and the Playwright route sweep opens each one with a model selected.

Functionality: no API call, store, handler or engineering computation was changed. Screen code changes are limited to: the shell (`App.tsx`), the loading primitive (`ui.tsx`), chart colours (`charts.tsx`, one area chart in `manufacturing.tsx`), the viewer's refit key (`Viewer.tsx`) and a layout class on Projects.

| Screen | Before | What changed | Functionality preserved | Known limitations |
|---|---|---|---|---|
| Projects | list and detail side by side; detail crushed to ~30 px at 390 px | stacks on phones; header actions wrap; tables scroll inside their panel; status badges with glyphs | create, select, delete project; add reference design; import CAD and new experiment links | per-screen redesign items in `REDESIGN_ROADMAP.md` |
| CAD import | dashed drop zone, small labels | drop zone uses surface and hover rule; system type and controls | upload, unit selection, import | per-screen redesign items in `REDESIGN_ROADMAP.md` |
| Assembly workbench | viewport framed an empty scene before meshes and pose arrived; flat grey ground | viewport refits after load; gradient ground; grouped toolbar; readiness descriptions wrap instead of clipping | tree, visibility, isolate, inspector, readiness, fit, axes, x-ray, section, explode | per-screen redesign items in `REDESIGN_ROADMAP.md` |
| Features and datums | dense table, generic styling | engineering table styling, sticky mono headers | feature registration and datum editing | per-screen redesign items in `REDESIGN_ROADMAP.md` |
| Tolerances | spinner on empty page while loading | skeleton loading; ruled table with right-aligned tabular numbers; fit classes as glyph badges | filter, add, edit, validation, fits and correlations | per-screen redesign items in `REDESIGN_ROADMAP.md` |
| Process batches | generic forms | system forms; one-column on phones (inline 5-column form overridden) | batch configuration and launch | per-screen redesign items in `REDESIGN_ROADMAP.md` |
| Virtual assemblies | viewport and lists in plain panels | viewport ground, status glyphs | sampling, generation, overlay, deviations | per-screen redesign items in `REDESIGN_ROADMAP.md` |
| Mechanical model | forms in panels | system forms and readouts; density chart in data ink | drive parameters, save, task simulation | per-screen redesign items in `REDESIGN_ROADMAP.md` |
| As-built inspection | four empty panels on first use | left-aligned empty states with guidance; system layout | scan import, alignment, analysis, approval | per-screen redesign items in `REDESIGN_ROADMAP.md` |
| Hardware testing | large empty right pane | system empty state; SIMULATED DEVICE MODE badge kept prominent; safety alert with left bar | device selection, preflight, confirmation-gated test | per-screen redesign items in `REDESIGN_ROADMAP.md` |
| Calibration | generic | system tables and charts | fit with holdout | per-screen redesign items in `REDESIGN_ROADMAP.md` |
| Experiment builder | generic wizard steps | step bar with vermilion top rule on the active step | task, sampling, constraints, create | per-screen redesign items in `REDESIGN_ROADMAP.md` |
| Live monitor | generic | system progress bar and readouts | run progress, cancel | per-screen redesign items in `REDESIGN_ROADMAP.md` |
| Adaptive experiment | generic | system charts and readouts | adaptive run | per-screen redesign items in `REDESIGN_ROADMAP.md` |
| Robustness | spinner; red-blue charts | skeleton; grouped metric readouts in one frame; histograms in neutral data ink, failing bins in the failure colour | constraint table, failure categories, scenario lists | per-screen redesign items in `REDESIGN_ROADMAP.md` |
| Sensitivity | bars in brand colour | bars and scatter in data ink; ranking table aligned | tabs: rank correlation, regression, one-at-a-time, Sobol | per-screen redesign items in `REDESIGN_ROADMAP.md` |
| Failure investigation | generic | system layout | counterfactual investigation | per-screen redesign items in `REDESIGN_ROADMAP.md` |
| Worst case | generic | system forms and tables | search and confirmation | per-screen redesign items in `REDESIGN_ROADMAP.md` |
| Workspace analysis | generic | system layout | map computation | per-screen redesign items in `REDESIGN_ROADMAP.md` |
| Degradation | generic | system charts | projection | per-screen redesign items in `REDESIGN_ROADMAP.md` |
| Model fidelity | generic | system layout | L1/L2 comparison | per-screen redesign items in `REDESIGN_ROADMAP.md` |
| Engineering Challenge | generic steps | step bar, mono readouts, system forms | challenge configuration and run | per-screen redesign items in `REDESIGN_ROADMAP.md` |
| Tolerance optimisation | generic | system charts and tables | allocation screen | per-screen redesign items in `REDESIGN_ROADMAP.md` |
| Design comparison | generic | system tables | comparison | per-screen redesign items in `REDESIGN_ROADMAP.md` |
| External validation | dataset table cells wrapping into 8 lines; superseded protocols cluttering the dataset row | superseded protocols only in the run list; status glyph badges; data-ink plots | import, validate, run detail with measured vs predicted and residuals | per-screen redesign items in `REDESIGN_ROADMAP.md` |
| Model trust | spinner | skeleton; system table | evidence per parameter | per-screen redesign items in `REDESIGN_ROADMAP.md` |
| Reports | generic | system document panels | report build, export, replay | per-screen redesign items in `REDESIGN_ROADMAP.md` |
| Benchmarks | generic table | engineering table; PASS / NOT RUN glyph badges | run all, rerun one, check detail | per-screen redesign items in `REDESIGN_ROADMAP.md` |
| Settings | generic | system forms | theme, workspace, AI configuration | per-screen redesign items in `REDESIGN_ROADMAP.md` |
