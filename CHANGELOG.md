# Changelog

## Unreleased - accounts, interface and reproducibility

* Accounts: `POST /api/v1/auth/register|login|logout`, `GET /auth/me`; scrypt password hashes,
  random session tokens stored only as SHA-256, HttpOnly SameSite=Strict cookie (Secure over
  HTTPS), 14-day sessions, sign-in throttling. Every other route needs a session.
* Per-account workspaces (the first account keeps the workspace root, later accounts use
  `users/<id>/`) and private background jobs.
* `GET /health` answers only `{"status": "ok"}`; versions, workspace path, job count and AI
  status moved to `GET /system`, behind sign-in.
* Web app: sign-in and account creation against the server, a chooser instead of disabled
  navigation (lists the workspace's projects, models and experiments), dark theme by default,
  3D screens loaded on demand, and a live long-exposure of the reference gearbox's planet
  motion on the sign-in page.
* Benchmarks: `publish.py --help`; published results contain no timings or run date, so two
  runs give byte-identical files; the reference STEP file has a fixed header timestamp.
* Sobol sensitivity: percentile bootstrap intervals when BCa is undefined.
* Accounts: change password (other sessions signed out), delete own account, administrator
  (first account) lists accounts, sets passwords and deletes accounts; sign-in throttle kept in
  `auth.db` across restarts. Account panels in Settings.
* Experiments of 100 scenarios or more run in worker processes (`--workers`,
  `MOTIONPROOF_WORKERS`, default half the cores, at most 4) with records identical to a
  one-process run; 400 reference scenarios took 105 s instead of 215 s on the development laptop.
* E2E: process batch, adaptive experiment and degradation projection launched from the UI, and
  the account panel (13 tests).
* README rebuilt around a real 1000-assembly run (`scripts/make_title_anim.py`,
  `scripts/make_result_figures.py`).

## Unreleased - external experimental validation

* `motionproof/external_validation`: adapters for NVIDIA Anchor-Lab (Apache-2.0), Stuttgart
  DaRUS-5760 transmission error (CC BY 4.0), NIST UR5 accuracy degradation and the KUKA KR300
  identification benchmark; download only on explicit import, checksum verification,
  immutable originals, SI signal schema that rejects missing samples, time alignment without
  extrapolation.
* Pre-registered protocols X1–X6 with fixed splits by whole trial, leakage guard, baselines and
  acceptance criteria; run records with checksums, trial IDs, parameters, identifiability,
  metrics, plots and reproduce commands (`validation/external/`).
* Results: X3 PASS; X1, X2, X4, X5 FAIL; X6 INSUFFICIENT DATA (`EXTERNAL_VALIDATION_RESULTS.md`).
* CLI `motionproof external ...`, API `/api/v1/external/*`, External validation screen,
  optional extra `external` (pyarrow).

## Unreleased - validation and hardening

Tooling for physical validation (no physical measurement has been made yet), a published
benchmark package and software hardening.

* Physical rig: `SerialDevice` (pyserial, optional `hardware` extra) with keep-alive, silence
  watchdog and explicit `done`/`stopped`/`fault` status; ESP32 firmware sketch
  (`hardware/firmware/motionproof_rig`, not compiled); build and test procedure
  (`docs/rig-build-and-test.md`); rig test files for the forearm elbow.
* Model-independent session analysis (`motionproof hardware analyse`): positioning error at each
  settle point, lost motion, repeatability, encoder resolution, measured ratio from same-flank
  settle pairs with an explicit flank assumption.
* Measured dimensions: CSV schema with instrument and resolution, `motionproof measurements
  template|summary|apply|evaluate` (Cp/Cpk, resolution check, measured distributions written to
  a new model file, per-part evaluation); the original model is never overwritten.
* Engineering Challenge yield cost model: cost per accepted part = (unit + inspection cost) /
  yield from a measured or specified process spread; accepted parts follow the process normal
  truncated to the specification. Closed-form test and benchmark M checks; fill-in template
  `examples/forearm_elbow/challenge_yield_TEMPLATE.yaml` refuses to run until real values are
  entered.
* Benchmark package `benchmarks/`: input models, raw SYNTHETIC data, suite output, file hashes and
  `reference_calculations.py`, an independent NumPy/SciPy implementation that does not import
  MotionProof; `publish.py` cross-checks 57 quantities and rewrites `BENCHMARK_RESULTS.md`.
* Hardening: `mypy --strict` clean; CLI `--help` contract over every command; API contract (no
  route answers 5xx to bad input, collection routes succeed on an empty workspace); Playwright
  end-to-end tests against the real backend (`npm run e2e`); frontend `npm run typecheck`
  covers the E2E sources; CI on Windows and Linux with lint, types, tests, benchmark
  regeneration and E2E. CLI configuration errors list each invalid field.

## 0.3.0 - 2026-11-15

Advanced upgrade (see ADVANCED_UPGRADE_AUDIT.md).

* As-built inspection: PLY/PCD/XYZ/CSV/STL/OBJ point clouds with explicit units, cleaning,
  datum and trimmed point-to-plane ICP registration with locked DOF and quality gating,
  deviation heatmaps with coverage, cylinder fits, approval workflow, as-built variants.
* Process-aware manufacturing: hierarchical variance sources, shared setup errors, drift and
  tool life, virtual batches, variance components, control charts, assembly impact.
* Adaptive experiments: Gaussian-process active learning with input screening and Q2-gated
  stopping; observed and predicted results kept apart.
* Workspace reliability maps with Level 2 checks; lifetime degradation projections;
  multi-fidelity Level 1 model with discrepancy and sufficiency rule; root-cause analysis with
  counterfactual reruns.
* Hardware in the loop: JSON-lines protocol, simulated device with fault injection, optional
  serial device, software safety monitor, session CSV and comparison.
* Engineering Challenge: cost minimisation under a Clopper-Pearson reliability constraint
  with Level 2 verification.
* Benchmark suite A-N writing BENCHMARK_RESULTS.md; model trust panel; command palette;
  11 new screens.

## 0.2.0 - 2026-11-15

First functional version of the tolerance-to-dynamics workflow.

* Model schema with features, datums, tolerances, correlations, fits, gear stages and drives.
* CAD import for STEP, STL, OBJ, URDF and MJCF; cylinder detection; exact fit measurement.
* Distributions, Gaussian-copula sampling, five sampling designs, Cp/Cpk.
* Virtual as-manufactured variants (Level A for the reference design, Level C elsewhere).
* Planetary lost-motion model and drive-train dynamics on MuJoCo with five task types.
* Experiments with immutable manifests, resume and exact replay.
* Robustness statistics, sensitivity, worst-case search, failure minimisation, allocation
  screen, design comparison, calibration with holdout.
* REST API, CLI, Python SDK, React application, reports in four formats.
* Synthetic NEMA 17 planetary-joint reference design and a 1,000-scenario example.

## 0.1.0 - 2026-11-14

Environment set-up and the CAD-to-MuJoCo verification script (23 checks).
