# Changelog

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
