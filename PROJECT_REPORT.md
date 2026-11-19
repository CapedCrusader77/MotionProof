# MotionProof: project report

Version 0.3.0 plus the unreleased validation and hardening round. Report date 2026-11-15.

## 1. Summary

MotionProof is an open-source engineering lab that answers one question: **given the
manufacturing tolerances of a mechanism, how will the parts that actually get built move?** It
takes a CAD model or a robot description, attaches a tolerance specification, generates virtual
as-manufactured assemblies, simulates each one dynamically on MuJoCo with a gearbox model that
includes backlash, stiffness and friction, and turns the results into statistics, sensitivities,
worst cases, optimised tolerances and a report.

Around that core it now has:

* as-built inspection from 3D scans;
* hierarchical models of manufacturing processes;
* adaptive (surrogate-guided) experiments;
* workspace reliability maps;
* lifetime degradation;
* multi-fidelity simulation;
* root-cause analysis;
* hardware-in-the-loop testing;
* an Engineering Challenge that minimises cost under a statistically verified reliability
  target;
* a published, independently cross-checked benchmark suite.

| Size | |
|---|---|
| Python engine | 14,875 lines in 28 subpackages |
| React application | 5,385 lines, 29 screens |
| Tests | 3,267 lines, 255 tests plus 9 browser end-to-end, all passing |
| REST API | 78 routes |
| CLI | 55 commands |
| Documentation | 48 topic documents in `docs/` plus top-level guides |

Everything has been verified in software against closed forms, separate methods or synthetic
data with known ground truth. **Nothing has yet been compared with a physical measurement.** The
tooling for that (rig firmware, serial device, measurement import) is built and tested. Running
it needs the physical gearbox and measured parts.

## 2. What was done, in order

| Phase | Outcome |
|---|---|
| 0.1.0: environment | Python 3.12 with `uv`, MuJoCo 3.14, CadQuery/OCC, FastAPI, Node 24 frontend; environment checks as tests (`motionproof doctor`). |
| 0.2.0: tolerance-to-dynamics workflow | Model schema, CAD import, tolerance distributions and sampling, virtual variants, planetary gearbox model, drive-train dynamics, experiments with replay, statistics, sensitivity, worst case, allocation, calibration, reports, API, CLI, SDK, React application, synthetic NEMA 17 reference design. |
| Real assemblies | A user CAD assembly and a designer's package were imported. Assumed FDM tolerances were added and clearly labelled as assumptions, not measurements. |
| 0.3.0: advanced upgrade | As-built scans, process models, adaptive experiments, workspace maps, degradation, multi-fidelity, root cause, hardware in the loop, Engineering Challenge, benchmark suite A to N, 11 new screens, command palette, model trust panel. |
| Validation and hardening (unreleased) | Serial rig device and ESP32 firmware sketch, model-independent encoder analysis, measured-dimension import, yield (scrap) cost model, published benchmark package with independent references, strict typing, API/CLI contract tests, Playwright end-to-end tests, CI for Windows and Linux. |

Every defect found along the way was fixed with a regression test. Examples:

* the PID overshoot, replaced by PD control with load feedforward;
* held-joint instability;
* the challenge accepting negative clearances;
* a biased ratio estimator;
* a serial timeout being mistaken for a completed test.

## 3. Architecture

A modular monolith: one Python package, one SQLite workspace, one background worker, one React
application. The engine never imports the web layer.

```
CAD / URDF / MJCF ──> cad.importers ──> inventory.json + viewer meshes
                                              │
model.yaml (features, datums, tolerances, fits, gear stages, drives)
        │ core.schema (validated)             │
        v                                     v
tolerances.sampling ──> design matrix    MechanicalModel (spec + MuJoCo model)
        │                                     │
        v                                     │
manufacturing.variants ── transmissions.gears ─┤  one variant per row
        │                                     v
        └────────────────────────────> simulation.engine (MuJoCo + drive train)
                                              │ metrics, traces
                                              v
experiments.runner (manifest, results.jsonl, replay)
        ├─ statistics / sensitivity / worst_case / allocation / calibration / reporting
        ├─ scans / process / adaptive / workspace / degradation / fidelity / rootcause
        └─ challenge / hardware / benchmarks
                │
services ──> api (FastAPI + jobs) ──> frontend (React, three.js)
         └─> cli (Typer)       SDK: motionproof.ManufacturingExperiment
```

| Package | Lines | Role |
|---|---|---|
| `core` | 671 | units, transforms, validated model schema |
| `cad` | 754 | STEP/STL/OBJ/URDF/MJCF import, cylinder detection, exact B-rep fit measurement |
| `tolerances` | 400 | six distributions, Gaussian copula, five sampling designs, Cp/Cpk |
| `manufacturing` | 416 | variant resolver (fits, radial play, tilt, backlash), measured dimensions |
| `transmissions` | 145 | planetary stage lost motion, transmission error, motor limits |
| `simulation` | 566 | MuJoCo engine with drive train, five task types, metrics |
| `experiments` | 421 | experiment runner, checkpoint/resume, exact replay, SDK |
| `statistics`, `sensitivity`, `optimisation` | 759 | robustness intervals, sensitivity, worst case, allocation |
| `calibration` | 301 | fit backlash, stiffness, friction to recordings, with holdout |
| `scans` | 807 | point clouds, cleaning, ICP registration, deviation, feature fits |
| `process` | 267 | hierarchical batch/setup/tool/part variation, drift, ANOVA |
| `adaptive` | 224 | Gaussian-process active learning |
| `workspace`, `degradation`, `fidelity`, `rootcause` | 643 | reliability maps, lifetime, L1/L2 models, counterfactuals |
| `hardware` | 660 | device protocol, simulated and serial devices, safety monitor, analysis |
| `challenge` | 465 | cost-minimising tolerance search with verification |
| `benchmarks` | 726 | benchmark suite A to N |
| `api`, `persistence`, `cli`, `reporting`, `reference`, `ai` | 3,169 | interfaces, storage, reports, reference design, optional local assistant |

## 4. How it works

### 4.1 Model

A model is a `model.yaml` file plus geometry. The YAML is validated by `core.schema`. It holds:

* features and datums (3-2-1 frames);
* tolerances, each with a nominal value, limits, distribution, source and **confidence**
  (`specified`, `assumed` or `measured`);
* correlations between tolerances;
* fits (shaft/bore pairs);
* gear stages (tooth counts, module, pressure angle, and which tolerances feed them);
* drives (motor, gearbox, controller, friction);
* effects that map tolerances onto joints;
* the end effector, simulation settings and a list of assumptions.

Every value carries its provenance, so a report can say which numbers are assumptions.

CAD import reads STEP through OpenCascade (CadQuery), meshes through trimesh, and URDF/MJCF
directly. It writes an inventory (bodies, joints, masses, inertias) and viewer meshes. Two
levels of geometric fidelity exist:

* **Level A**: the reference design's geometry is regenerated per variant with CadQuery and
  measured exactly with OCC (for example the radial gap of a shaft in a bore).
* **Level C**: reduced-order relations, used for imported models.

Level B (varying features of imported STEP solids) is not implemented.

### 4.2 Tolerances and sampling

Each tolerance has a distribution: uniform, normal, truncated normal, lognormal, discrete or
empirical. Samples are drawn through the inverse CDF. Correlations are imposed with a Gaussian
copula. Five designs are available: Monte Carlo, Latin hypercube, Sobol, boundary and corners.
Capability indices (Cp, Cpk) and stack-ups are computed from the same specification.

### 4.3 Virtual as-manufactured assemblies

For each sampled row, `manufacturing.variants` resolves the tolerances into joint-level effects:

* **Fits.** Clearance = bore − shaft. The minimum and maximum come from the limits; the
  statistics come from the distributions.
* **Radial play and tilt.** Bearing seat and internal clearances give the radial play; the tilt
  is play divided by the bearing span.
* **Planetary gearbox.** Per planet `k`, the lost motion is
  `d_k = (j_sp + j_pr)/2 + c`. Here `j_sp` and `j_pr` are the circumferential backlashes of the
  sun-planet and planet-ring meshes, and `c` is the planet bearing clearance. The stage backlash
  angle is `min_k d_k / a`, where `a` is the centre distance. A centre-distance error `Δa`
  changes the backlash by `2·tanα·Δa`. The stage ratio is `1 + z_ring/z_sun`, so the reference
  design is (1 + 54/12)(1 + 60/12) = 33:1. Sun runout gives a transmission error of amplitude
  `(e/2)/r_sun/i`. Output backlash adds the first stage divided by the second stage's ratio.
* **Misalignment.** Joint offsets and axis tilts are applied to the kinematics.

### 4.4 Dynamic simulation

MuJoCo integrates the rigid multibody (implicit-fast integrator, 0.5 ms step). Each driven
joint has a drive train computed alongside it in Python:

```
gap = θ_rotor + TE(θ_rotor) + zero_offset − θ_output
s   = gap − clip(gap, −b/2, +b/2)       engaged deflection (zero inside the dead band)
τ   = k·s + c·(ω_rotor − ω_output)      while engaged; a flank pushes, never pulls
```

* Mesh losses `(1 − η)·|τ|` and output friction act through MuJoCo's friction constraint, so
  stiction exists.
* The motor runs PD position control on the motor side with load feedforward, limited by the
  torque-speed curve. Lost motion is therefore not corrected, as with a stepper or a motor-side
  encoder.
* Joints that are not driven are locked with a zero-width range.

Five tasks exist: point-to-point, reversal, static hold, repeated cycles and workspace sweep.
Each uses a quintic trajectory. Metrics include:

* end-effector error and direction-dependent error;
* lost motion;
* torque utilisation and saturated fraction;
* smallest mesh backlash.

### 4.5 Experiments and analysis

An experiment combines a model, a task, a sampling design, operating conditions (payload,
speed) and constraints. Results go to `results.jsonl` with an immutable manifest. A run can
resume after interruption. Any scenario replays bit-exactly.

On top of the results:

* **Robustness**: Wilson intervals for pass fractions, t-intervals over replicates.
* **Sensitivity**: rank correlation, regression decomposition, an interaction screen,
  one-at-a-time and Sobol indices.
* **Worst case**: searches the tolerance box for the worst value of a metric.
* **Allocation**: a Latin-hypercube Pareto screen of tolerance scales against cost.
* **Calibration**: fits backlash, stiffness and friction to a recording and checks the fit on a
  separate holdout recording. It warns when parameters are not identifiable.
* **Reports**: JSON, Markdown, CSV and PDF.

### 4.6 Advanced capabilities

* **As-built scans.** PLY/PCD/XYZ/CSV/STL/OBJ clouds with explicit units are read in chunks.
  Outliers, duplicates and excess density (voxel) are cleaned. The scan is registered to the
  nominal geometry with a datum 3-2-1 frame or trimmed point-to-plane ICP with locked degrees of
  freedom. Registration quality is gated before inspection. The outputs are signed deviation
  maps with coverage and least-squares cylinder fits. Approved measurements become an as-built
  variant.
* **Process models.** Variation is split into batch, setup, tool, part and measurement levels.
  Setup errors can be shared between features (they cancel in bore − shaft). Tool wear adds
  drift. The module generates virtual batches and computes nested-ANOVA variance components and
  control charts.
* **Adaptive experiments.** A NumPy Gaussian process (length scales and nugget by marginal
  likelihood, inputs screened by Spearman correlation) runs an AK-MCS-style search near the
  failure boundary. Predictions count only when cross-validated Q² ≥ 0.5. Observed and
  predicted results are kept apart.
* **Workspace maps.** Pass probability and error over a grid of poses, using the Level 1 model.
  Selected poses are checked against Level 2 dynamics.
* **Degradation.** Progressions of parameters such as backlash over cycles; the module finds
  the cycle at which each requirement is crossed.
* **Multi-fidelity.**
  * L1: quasi-static deflection `b/2 + τ(q)/k`.
  * L2: full dynamics.
  * The L1/L2 discrepancy is measured, and an L1 verdict close to a limit is refused.
  * L3 (contact, FEA) is not implemented.
  * L4 is physical testing.
* **Root cause.** For a failed scenario, each variable is reset to nominal (a counterfactual)
  and re-simulated. Variables are ranked by how much they contribute and whether removing them
  fixes the failure.
* **Hardware in the loop.**
  * Protocol: JSON lines. The device sends `hello`, `telemetry` and `status`; the host sends
    `ping`, `arm`, `move` and `stop`. Fault flags: e-stop, limit, driver, sensor.
  * Safety: explicit confirmation, a preflight check, a software safety monitor (travel, speed,
    temperature, watchdog, silence timeout) and keep-alive pings.
  * Devices: a simulated device with fault injection and a serial device for an ESP32 rig.
  * Sessions are saved as CSV and compared with the simulation.
  * The software stop is documented as **not** a safety function: a hardware e-stop is
    required.
* **Engineering Challenge.**
  * Decision variables scale and shift tolerance bands, within bounds that stay physically
    possible.
  * Candidates are screened with L1, refined, then verified with fresh L2 Monte Carlo.
  * Acceptance needs the exact Clopper-Pearson lower bound of the pass probability to exceed
    the target at the stated confidence.
  * Two cost models:
    * reciprocal `fixed + coefficient/scale^exponent`. Without cost data it is labelled a
      relative index.
    * yield: `(unit cost + inspection cost) / yield`, where yield is the share of a measured
      process spread that falls inside the specification. Accepted parts then follow that
      normal distribution truncated to the specification.

### 4.7 Validation tooling for real hardware and parts

* **Rig.** An ESP32 drives a step/dir motor driver. An AS5600 magnetic encoder reads the gearbox
  output. The firmware sketch (`hardware/firmware/motionproof_rig`, not compiled yet) runs the
  same quintic plan as the simulator and streams telemetry at 200 Hz. The procedure, wiring,
  bill of materials and safety rules are in `docs/rig-build-and-test.md`.
* **Analysis without the model.** `motionproof hardware analyse` reports, from encoder data
  alone:
  * positioning error at each settle point;
  * lost motion;
  * repeatability;
  * encoder resolution;
  * the measured ratio, taken from pairs of settled points on the same gear flank so that
    backlash cancels.

  Which flank carries the load cannot be seen in the signals, so it must be stated. In
  simulation, the 60° one-sided-load test gives a ratio of 33.06 (true 33.0). The vertical test
  with the wrong assumption gives 29.9, and this is documented.
* **Measured dimensions.** A CSV of measurements: part, tolerance, value, unit, instrument,
  resolution, date, operator. `motionproof measurements summary` reports n, mean, std, Cp/Cpk
  and out-of-specification counts. It warns when there are fewer than 30 parts, or when the
  instrument resolution is coarser than a tenth of the tolerance width. `apply` writes a **new**
  model with measured distributions; the original is never overwritten. `evaluate` simulates
  each measured part individually.

## 5. Interfaces

* **CLI** (Typer, 55 commands in 20 top-level groups): `doctor`, `inspect`, `serve`, `model`,
  `tolerance`, `assembly`, `manufacturing`, `experiment`, `optimise`, `calibration`, `report`,
  `reference`, `scan`, `workspace`, `degradation`, `hardware`, `measurements`, `challenge`,
  `benchmark`, `external`. Invalid configuration files are reported field by
  field.
* **REST API** (FastAPI, 78 routes under `/api/v1`): long jobs run in the background with
  progress and cancellation. The OpenAPI schema is generated. Every route except the public
  health check and sign-in needs a session; each account has its own workspace and jobs
  (scrypt password hashes, HttpOnly session cookie; see `SECURITY.md`).
* **Python SDK**: `motionproof.ManufacturingExperiment`. The README example is executed as a
  test.
* **Web application** (React 19, three.js, Recharts), 29 screens grouped as Models,
  Manufacturing, Inspection and test, Experiments, Reliability, Optimisation and Evidence. It
  includes a 3D assembly workbench, a scan viewer, a live monitor, a command palette (Ctrl+K), a
  model trust panel showing which values are assumed, a chooser that lists the workspace's real projects, models and experiments when a screen needs one, a sign-in and account page, and dark (default) and light themes. It is served
  by `motionproof serve`.

## 6. Verification

| Check | Result |
|---|---|
| `pytest`: unit, analytic physics, integration, end to end, API and CLI contracts, benchmark package | 255 passed |
| `mypy --strict` (engine and benchmark scripts) | clean, 99 files |
| `ruff` | clean |
| Frontend `tsc` (application and E2E sources) and `vite build` | clean |
| Playwright E2E against the real backend and a fresh workspace | 9 passed: sign-in checked against the server, shell, project and reference design created through the UI, all 29 screens render, the chooser opens a screen from a pick, command palette, theme persistence, bad input rejected, no horizontal overflow at 390 px |
| API contract | no route answers 5xx to invalid input; collection routes succeed on an empty workspace |
| CLI contract | every one of the 55 commands answers `--help` |
| Accounts | 10 tests: sessions required, wrong password and unknown email answer alike, throttling, no clear-text passwords or tokens stored, per-account workspaces and jobs |
| Benchmark suite | 13 PASS, J (hardware) NOT RUN |
| Independent cross-check | 57/57 quantities agree |

### Benchmarks

| ID | Benchmark | Checks |
|---|---|---|
| A | Shaft/bearing fit; diameter recovered from a synthetic noisy scan in an unknown pose | 7/7 |
| B | Two-stage planetary gearbox: ratios, lost motion, transmission error, static torque path | 8/8 |
| C | Two-link arm: forward/inverse kinematics, gravity torque, joint limits | 10/10 |
| D | Reversal lost motion equals backlash; bit-exact replay | 7/7 |
| E | Offset, tilt and clearance propagate to tip error | 5/5 |
| F | Payload torque, utilisation, deflection, overload | 10/10 |
| G | Variance components, shared setup error, tool-wear drift recovered | 6/6 |
| H | Workspace map within 5 % of direct dynamics | 3/3 |
| I | Wear rate and requirement crossing | 2/2 |
| J | Physical hardware | NOT RUN |
| K | Adaptive versus random sampling, 10 seeds: median relative error 0.14 versus 1.0 | 2/2 |
| L | L1 versus closed form and L2; near-limit L1 verdict refused | 3/3 |
| M | Challenge finds the analytic optimum band, reports infeasible cases, yield cost exact | 6/6 |
| N | Root cause ranks the deliberate cause first; counterfactual removes the failure | 2/2 |

The benchmark package in `benchmarks/` publishes:

* the input models;
* every raw synthetic data set;
* the suite's full output;
* SHA-256 hashes of every file.

`reference_calculations.py` recomputes every closed-form expected value and re-analyses the raw
data with separate code: its own nested ANOVA, `numpy.polyfit`, and a circle fit of the raw scan
without registration. It uses only NumPy, SciPy and PyYAML, and it refuses to run if MotionProof
is imported. `uv run python benchmarks/publish.py` reproduces everything.

### Reference Engineering Challenge (synthetic)

This run uses the synthetic reference design with example requirements and no cost data, so the
cost is a relative index and no saving in money is claimed. It evaluated 25 candidates with
1,440 Level 2 scenario evaluations. Six candidates were rejected without simulation as
physically impossible.

| | Original | Chosen |
|---|---|---|
| Relative cost index | 3.000 | 2.698 |
| Verified pass fraction (150 fresh scenarios) | 88.0 % | 94.7 % |
| Clopper-Pearson lower bound, 90 % | 0.839 | 0.915 (target 0.90) |
| Lost motion p95 | 7.00 mrad | 6.43 mrad |

## 7. Engineering rules followed

* No mechanical property, tolerance, measurement, cost or result is invented. Values without a
  source are labelled `assumed`, and synthetic data is labelled SYNTHETIC in file names and
  content.
* Results are reproducible: seeds, manifests and exact replay.
* Hardware never moves without an explicit `--confirm`, and the software stop is not presented
  as a safety function.
* No claim of physical certification is made. The cross-check proves that the code computes what
  the formulations say; it does not prove that the formulations match a real gearbox.

## 8. Limitations and open items

| Item | State |
|---|---|
| Physical gearbox test (benchmark J) | Tooling ready; the rig must be built and the firmware compiled |
| Validation with real part measurements or scans | Tooling ready; no measured data yet |
| Defensible Engineering Challenge in currency | Yield cost model verified; needs real unit cost, inspection cost and measured process spread |
| Level B geometry for imported STEP | Not implemented |
| Fidelity L3 (tooth or bearing contact, FEA, thermal) | Not implemented |
| Friction windup | Relaxes through MuJoCo's soft friction constraint; lost motion sits at the backlash value |
| Adaptive sampling on the 28-input reference | Surrogate not predictive (Q² about 0.2); the run says so and gives no saving |
| Joint types | Only revolute joints can be driven |
| E2E coverage | Screens render; launch buttons of each screen are not driven automatically |
| CI | Workflow pushed; first run not yet checked |
| Git | Pushed to GitHub |
| Licence | MIT |

## 9. Next steps

1. Build the rig and record reversal, 60° and cycle tests, plus a holdout from another day.
   Calibrate on one recording and validate on the other, which fills benchmark J.
2. Measure the gearbox parts (or scan them), apply the measurements, and evaluate each part.
3. Run the yield-cost Engineering Challenge with real cost and process data.
4. Let CI run and fix what it finds.
5. Drive each screen's launch actions in the E2E suite.

## 10. How to run

```bash
uv sync
```

```bash
uv run motionproof doctor
```

```bash
uv run motionproof serve
```

```bash
uv run pytest
```

```bash
uv run python benchmarks/publish.py
```

```bash
cd frontend && npm ci && npm run build && npm run e2e
```

Hardware support: `uv sync --extra hardware`, then follow `docs/rig-build-and-test.md`.
