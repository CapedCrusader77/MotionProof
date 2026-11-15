# Advanced upgrade audit

Written 2026-11-15 against version 0.2.0, before any upgrade code. It records what exists, what
each requested capability needs, and how it will be accepted. Outcomes are tracked in
`DEVELOPMENT_STATUS.md` and `BENCHMARK_RESULTS.md`.

## State of the existing application

**Functional and tested (102 tests):** units and transforms; STEP/STL/OBJ/URDF/MJCF import;
cylinder detection and exact fit measurement on B-rep solids; joint derivation from two STEP
poses; tolerance model, six distributions, Gaussian-copula sampling, five designs, Cp/Cpk;
variant resolver (fits, planetary lost motion, radial play, misalignment); drive-train dynamics
on MuJoCo (14 analytic tests); experiments with immutable manifests, resume and replay;
Wilson / replicate statistics; Spearman, regression, one-at-a-time and Sobol sensitivity;
worst-case search with confirmation and failure minimisation; tolerance allocation screen;
calibration with holdout; reports; REST API; CLI; Python SDK.

**Partially implemented:** Level A geometry regeneration (reference design only); calibration
(synthetic recordings only); tolerance allocation (Latin-hypercube screen, no evolutionary
optimiser); provenance (per-tolerance source and confidence, model fingerprints, but no single
view across all parameters).

**Mocked:** nothing. No screen shows fabricated data. The reference design is synthetic and is
labelled so.

**Real integrations:** MuJoCo, OpenCascade/CadQuery, Trimesh, SciPy. **Not real:** Fusion 360
(untested), Ollama (untested with a running server), any physical hardware, any 3D scanner.

**Frontend:** 16 screens build and call tested endpoints. Five were exercised by hand
(workbench, tolerances, virtual assemblies, robustness, sensitivity). There are no automated
frontend tests.

**Not connected end to end:** measurements of real parts cannot yet replace sampled tolerance
values; nothing spatial (per-pose) is computed; nothing time-dependent beyond one task.

**Available without new dependencies:** NumPy, SciPy (KD-tree, optimisers, statistics),
Trimesh (PLY/STL/OBJ I/O, surface sampling). **Not installed:** scikit-learn, Open3D, pyserial,
rtree. The upgrade avoids adding them: a small Gaussian-process regressor and ICP are written on
NumPy/SciPy (each under 100 lines and tested against known answers); a serial transport is
written against the optional `pyserial` import and reported unavailable when it is missing.

## Feature map

| # | Capability | Existing | To modify | New | Tests / acceptance |
|---|---|---|---|---|---|
| 1 | As-built import | Mesh import, cylinder detection on B-rep, fit evaluation | Variant resolver accepts measured values with provenance | `motionproof/scans`: point-cloud readers (PLY, PCD, XYZ, CSV, STL/OBJ vertices), cleaning, datum and ICP registration, deviation statistics, cylinder fitting, measured-feature records | Synthetic shaft scan with known diameter error and known pose: recover both within stated tolerance; noisy, outlier, incomplete and wrong-unit cases; measured diameter changes a fit result |
| 2 | Adaptive experiments | Monte Carlo, LHS, Sobol, boundary, corners | Experiment evaluation reused as the true simulator | `motionproof/adaptive`: Gaussian-process surrogate, boundary-seeking acquisition, stopping rules, observed/predicted separation | Analytic limit state with known failure probability: adaptive versus random at equal true-simulation budget, several seeds; no superiority claim unless measured |
| 3 | Hardware in the loop | Calibration from CSV, engine traces | Calibration reads device logs | `motionproof/hardware`: message schema, device abstraction, simulated device, optional serial transport, safety monitor, session logging, comparison | Simulated device, malformed lines, lost packets, sensor loss, limit violation aborts, watchdog, CSV round trip. Real hardware: **not available**, not tested |
| 4 | Process-aware manufacturing | Independent or copula-correlated distributions, Cp/Cpk | Variants can be drawn from a process batch | `motionproof/process`: hierarchical variance components, shared setup effects, drift, virtual batch, variance-component estimation, control limits | Synthetic batch from known components: recover them within tolerance; clearance variance with and without shared setup against the analytic formula |
| 5 | Workspace reliability maps | Body kinematics, variants | — | `motionproof/workspace`: pose grid, per-pose error distribution, tolerance probability with interval, comparison | Two-link arm with a known joint tilt: map against direct simulation at selected poses |
| 6 | Lifetime degradation | Variant parameters | — | `motionproof/degradation`: linear, exponential, piecewise and fitted progressions, interval experiment, threshold crossing, fitting | Synthetic degradation with known parameters: recover the trend and the crossing |
| 7 | Multi-fidelity | Fidelity labels F1, F2 | Metrics carry the level that produced them | `motionproof/fidelity`: Level 1 quasi-static model (kinematics, gravity torque, half backlash plus windup), discrepancy measurement, sufficiency rule | Level 1 against Level 2 on the single-joint benchmark; a case near a limit is flagged as needing Level 2. Level 3 (contact, FEA): **not implemented** |
| 8 | Root-cause analysis | Sensitivity, worst case, minimisation, replay | — | `motionproof/rootcause`: local sensitivity at the failure, pass/fail distribution comparison, single-variable counterfactual reruns, evidence-based explanation text | Mechanism with one deliberately dominant variable: it is ranked first by counterfactual rerun |
| 9 | Interface | 16 screens, design system | Navigation, top bar | As-built inspection, process batches, adaptive monitor, workspace map, degradation, hardware, failure workspace, challenge, trust panel, command palette | Type check and build; manual walk-through recorded honestly |
| 10 | Benchmark suite | 14 physics tests, examples | — | `benchmarks/` A to J runner writing `BENCHMARK_RESULTS.md` from actual runs | Each benchmark states purpose, formulation, expected, actual, error, criterion. J (hardware): no data, reported as not run |
| 11 | Engineering Challenge | Allocation screen, comparison, cost model | Constraint-based feasibility with confidence bounds | `motionproof/challenge`: requirements, decision variables, cost model, search, independent verification, infeasibility report | Benchmark with a known feasible and a known infeasible requirement set; reproducible; verification uses fresh seeds |

## Shared architecture decisions

1. **One mechanical model.** Every new subsystem consumes `MechanicalModel` and produces either
   tolerance values (scan measurements, process batches), joint-parameter changes (degradation)
   or evaluations of `evaluate_scenario` (adaptive, root cause, workspace, challenge). No
   feature gets its own simulator.
2. **Evidence status per value.** A single vocabulary (`cad`, `scan`, `measured`, `manual`,
   `manufacturer`, `assumed`, `estimated`, `calibrated`, `validated`) is attached to tolerances,
   drive data and measured features and listed in one trust view. No overall score.
3. **Observed versus predicted.** Surrogate predictions and Level 1 results are stored with their
   kind and are never counted as simulation results.
4. **Storage.** New artefacts are JSON files in the model or experiment directory, indexed by
   the existing SQLite store. No new database.
5. **Synthetic data are labelled** in file names, records and the interface.

## What cannot be delivered here

* Real scanner data, real hardware measurements and Benchmark J: no equipment or data exist.
* Level 3 and 4 fidelity: no validated contact or structural solver is integrated.
* Full GD&T inspection: scan inspection gives fitted dimensions and deviation statistics, not
  standard-conformant geometric tolerance verification.
* Exact as-built geometry for arbitrary parts: measured features feed reduced-order parameters.
