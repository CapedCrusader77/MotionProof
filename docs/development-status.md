# Development status

Updated 2026-11-15. Version 0.3.0 (advanced upgrade).

## Accounts, interface and reproducibility round (unreleased)

| Item | State | Evidence | Limits |
|---|---|---|---|
| Accounts and sessions | Done | `motionproof/api/auth.py`; tests/integration/test_auth.py (10): 401 without a session, register/sign-out/sign-in, same answer for wrong password and unknown email, throttling, no clear-text password or token in `auth.db`, forged cookie refused; E2E sign-in against the server | no password reset, email verification, admin role or account deletion; throttle counter is in memory |
| Per-account workspaces and jobs | Done | `UserStores` resolves the signed-in user's `Store`; jobs carry an owner and run in the submitting request's context; test_auth.py checks that a second account sees no projects or jobs of the first | first account keeps the existing workspace root |
| Server hardening and hosting | Done | `motionproof/api/security.py`, `--production`, `docs/hosting.md`, `deploy/`; tests/integration/test_security.py (17): headers and CSP, same-origin check, production defaults, closed registration, per-address limits, job cap, scrypt upgrade and migration, admin-only actions, account commands; all 29 screens opened in a browser against a production-mode server with 0 CSP violations | the systemd unit, Caddyfile and install steps are standard but **not run on a live server**; limits are per process and in memory; no MFA |
| Account administration | Done | password change signs out other sessions; administrator lists, resets and deletes accounts; last administrator protected; throttle persisted; test_auth.py (16 tests); E2E changes a password in Settings | no email-based reset |
| Parallel experiments | Done | `Experiment.run(workers=...)`, process pool from 100 scenarios; test_pipeline_components.py checks identical records, order, cancellation and resume with 2 workers; 400 scenarios 215 s serial, 105 s with 4 workers | worker start-up about 8 s each on Windows; speed-up limited by the laptop's mixed core types |
| UI launch tests | Done | E2E runs a process batch, an adaptive experiment and a degradation projection from their screens | Engineering Challenge launch covered by backend tests only (it runs 260+ simulations) |
| Public health check | Done | `GET /health` returns only the status; details moved to `GET /system` behind sign-in | |
| Screens that need a selection | Done | `Chooser` lists the workspace's real projects, models and experiments; E2E opens Tolerances from a pick | |
| Reproducible benchmark publication | Done | `publish.py` writes no timings or dates; two runs give byte-identical `BENCHMARK_RESULTS.md`, `MANIFEST.json` and `assembly.step` | timings are printed, not published |
| Sobol intervals | Done | BCa falls back to percentile intervals when the bootstrap is degenerate (an index of exactly zero) | |
| First load of the web app | Done | 3D screens load three.js on demand; first-load JavaScript about 0.9 MB instead of 1.9 MB | |

## External experimental validation (unreleased)

Public experimental robot datasets used to test MotionProof's model components on other
robots. Not physical validation of the reference gearbox (benchmark J remains NOT RUN).

| Item | State | Evidence |
|---|---|---|
| Adapters: Anchor-Lab, Stuttgart DaRUS-5760, NIST UR5, KUKA KR300 | Done | 171 files imported and verified (SHA-256 / MD5 where published); `tests/integration/test_external_validation.py` (13) |
| Pre-registered protocols X1–X6 | Done | committed before the first run (git history); v1 and v2 of X1 superseded with reasons, records kept |
| Results | X3 PASS; X1, X2, X4, X5 FAIL; X6 INSUFFICIENT DATA | `EXTERNAL_VALIDATION_RESULTS.md`, `validation/external/runs/` |
| CLI, API, External validation screen | Done | `motionproof external list/inspect/import/validate/report/runs/benchmark`; `/api/v1/external/*`; E2E route sweep |

Not done: Anchor-Lab G1 and H1 multi-joint groups; a speed-dependent TE term; a multibody
KUKA model; per-run TCP data (does not exist in the NIST release).

## Validation and hardening round (unreleased)

| Item requested | State | Evidence | What is still needed |
|---|---|---|---|
| 1. Test the real NEMA 17 planetary gearbox | **Tooling ready, not run** | serial device, firmware sketch, rig test files, `hardware analyse`; tests/integration/test_hardware.py (15) incl. serial path with a fake port and model-independent analysis | build the rig (`docs/rig-build-and-test.md`), compile the firmware, run the tests; no physical measurement exists |
| 2. Validate against real manufacturing measurements | **Tooling ready, no data** | measurement CSV import, summary, apply, per-part evaluation; test_measurements.py (4); as-built scan path from 0.3.0 | measured dimensions or a real scan of the parts |
| 3. Reproducible benchmarks | **Done (synthetic)** | `benchmarks/`: inputs, raw data, references, hashes; 13 PASS, J NOT RUN; cross-check 57/57 agree; test_benchmark_package.py (3) | physical benchmark J needs item 1 |
| 4. Software hardening | **Done** | full pytest 300 passed; mypy strict clean (99 files); ruff clean (engine, tests, benchmarks); test_contracts.py (CLI help for every command, every API route); 14 Playwright E2E tests passed against the real backend with installed Chrome; CI workflow for Windows and Linux | CI first run on GitHub to be checked |
| 5. Engineering Challenge with a defensible cost model | **Method verified, defensible run waits for data** | yield cost model, closed-form test, benchmark M; template refuses placeholder values | real unit cost, inspection cost and measured process spread (item 2) |

## Advanced upgrade: verified

Test suite: 159 passed (158 in one full run, plus the challenge file re-run after the last fix). Lint clean. Benchmarks: 13 PASS, J NOT RUN.


| Capability | Evidence | Limits |
|---|---|---|
| As-built scan import, registration, inspection, approval, as-built variant | tests/integration/test_scans.py (9), test_advanced_api.py, benchmark A; UI walked through (import, align, analyse, approve) | SYNTHETIC scans only; fitted geometry, not GD&T |
| Process-aware batches | tests/unit/test_process.py (6), benchmark G; CLI run | statistical model, synthetic batches |
| Adaptive experiments | test_advanced.py, benchmark K (median rel. error 0.14 vs 1.0 for random, 10 seeds) | on the 28-input reference reversal the surrogate was not predictive (Q2 about 0.2) and the run says so |
| Workspace maps | test_advanced.py, benchmark H (within 5 % of Level 2); UI map computed | no collision geometry |
| Lifetime degradation | test_advanced.py, benchmark I | projections of user progressions; no wear physics |
| Multi-fidelity L1/L2 | test_advanced.py, benchmark L | L3/L4 not implemented |
| Root cause | test_advanced.py, benchmark N; UI investigation of EXP_001 S000003 ranked payload first (matches earlier sensitivity) | causal only within the model |
| Hardware in the loop | test_hardware.py (12): confirmation gate, preflight, e-stop, sensor loss, watchdog, lost packets, temperature, calibration from two sessions; UI run | SIMULATED DEVICE only; serial path untested; no firmware |
| Engineering Challenge | test_challenge.py (9) analytic optimum, infeasible case, sample-size refusal, impossible specs; benchmark M | see the reference result below |
| Benchmarks | BENCHMARK_RESULTS.md: 13 PASS, J NOT RUN | J has no hardware data |
| UI | 11 new screens, command palette (Ctrl+K), trust panel; type check and build clean; as-built, hardware, workspace, investigation, trust, benchmarks, palette exercised in the browser; challenge, process, adaptive, degradation, fidelity opened without console errors | not exercised by hand: challenge launch from the UI, process batch launch, adaptive and degradation launch; no automated frontend tests |

### Reference Engineering Challenge

Run `examples/advanced/challenge_reference.yaml` (SYNTHETIC design, example requirements, no
cost data, so cost is a relative index and no saving is claimed): 25 candidates, 1,440 Level 2
scenario evaluations, 6 candidates rejected unsimulated as physically impossible.

| | Original | Chosen C017 |
|---|---|---|
| Relative cost index | 3.000 | 2.698 |
| s2 sun-planet backlash (mm) | 0.025 to 0.055 | 0.0064 to 0.0650 (scale 1.95, shift -0.0043) |
| s2 planet-ring backlash (mm) | 0.025 to 0.055 | 0.0219 to 0.0448 (scale 0.76, shift -0.0067) |
| s2 planet clearance (mm) | 0.005 to 0.020 | 0.0033 to 0.0204 (scale 1.14, shift -0.0006) |
| Verified pass fraction (150 fresh scenarios) | 88.0 % | 94.7 % |
| Clopper-Pearson lower bound, 90 % | 0.839 | 0.915 (target 0.90) |
| Lost motion p95 | 7.00 mrad | 6.43 mrad |
| Smallest mesh backlash p95 | 30.2 um | 27.2 um |

Evidence kept: the payload-dominated first attempt (infeasible), a scale-only attempt
(infeasible: the lost-motion limit is below the nominal backlash and scaling does not move the
centre), and an unbounded run whose proposal had a negative clearance limit. That last result
exposed a defect: the search accepted physically impossible specifications. Fixed: clearance
and backlash limits must stay >= 0 (regression test added). Shifts carry no cost in this model.

### Known issues added in 0.3.0

* `mypy --strict motionproof`: 91 errors in 24 files at the 0.3.0 release; fixed since (clean).
* The three-state view draws nominal and as-built in 3D; the virtual state is a table of
  tolerance limits, because Level C variants change model values, not meshes.
* Adaptive sampling stops on its budget when the surrogate never becomes predictive; it then
  gives no saving over Monte Carlo.
* Root-cause investigation costs 2 x variables + 9 simulations (65 for the reference design).
* The as-built "deviation limit" shown is the limit stored with the analysis, not the input box.

## Verified on this machine

| Check | Result |
|---|---|
| `pytest` (0.2.0 baseline) | 102 passed (14 analytic physics, 31 unit, 33 integration and end-to-end, 23 environment) |
| `ruff check motionproof tests` | clean |
| Frontend `tsc -b` and `vite build` | clean (three.js chunk 976 kB, above Vite's warning size) |
| 1,000-scenario Monte Carlo experiment on the reference design | 49 s, 0 invalid simulations, replay reproduces stored metrics exactly |
| Web application against the real backend | Workbench (3D geometry, joint sliders), tolerances, virtual assemblies, robustness and sensitivity screens opened and exercised by hand; no console errors |

## First real assembly (2026-11-15)

The user's STEP set in `examples/New folder` (three assembly poses, 19 part files) was imported.

* `ASSEMBLY_arm_straight.step`: 37 solids, all valid, part names matched. Import took 127 s
  (32 MB with real tooth geometry); slow, not yet optimised.
* New: `motionproof assembly compare-poses` derives joints from two exports of one assembly.
  Straight versus bent-90 gives one revolute joint, axis (0, 1, 0) through (51, 0, -56) mm,
  90.0000 degrees, fit residual 1.5e-11 mm. Moving parts: GB-07, GB-08, FA-01, FA-02, FA-03.
* Read from geometry, not yet confirmed by the designer: stage 1 planets sit 16.5 mm from the
  axis and stage 2 planets 18.0 mm, consistent with module 1.0 and 12/21 and 12/24 teeth.
* Not done for this assembly: no densities, so no masses; no dynamics model; no tolerances or
  motor data entered; feature mapping not confirmed; the part files and the exploded pose were
  not examined. Fusion integration remains untested (these are STEP files).

## Powered-elbow model from the designer's package (2026-11-15)

`examples/forearm_elbow/` (built by `build_model.py`, registered as MDL_004) uses the STEP
assembly, the two poses and the design README from `out.zip`.

* From the README (specified): 12/21/54 and 12/24/60 teeth, module 1.0, pressure angle 25
  degrees, 0.15 mm backlash per mesh, 0.45 N*m stall torque, 33:1. The README's tooth counts
  and centre distances agree with what was read from the geometry, and its part volumes agree
  with the imported solids.
* Measured from geometry: elbow axis, 32.2 mm bearing span, part volumes and centroids.
* Estimated: moving mass 1.16 kg (1 kg hand and forearm per the README, printed parts as PETG).
* Nominal results: gearbox backlash 9.85 mrad (0.56 degrees) at the output; gravity torque
  3.62 N*m at 90 degrees (README says roughly 3); torque utilisation 0.24 holding and 0.35 for
  a 1 s move to 90 degrees.
* **Placeholders with no data:** gearbox efficiency, torsional stiffness, rotor inertia, motor
  speed limit and torque-speed curve. The 17 mrad positioning error at 90 degrees is 4.9 mrad
  of backlash plus 12 mrad of windup that comes from the placeholder stiffness, so that number
  is not a prediction.
* The design package contains no tolerances. At the user's request, `add_assumed_fdm.py` added 24
  entries that are **assumed** desktop-FDM figures (bearing limits are estimated normal-class
  values). Experiment EXP_002 (1,000 Monte Carlo scenarios, seed 7, move 0 to 90 degrees,
  payload 0 to 0.3 kg, 230 s, 0 invalid): 14.9 % of variants have a gear mesh that binds
  (Wilson 95 %: 12.8 to 17.2 %); no motor stall; output backlash 9.2 to 15.8 mrad (5 to 95 %).
  Positioning error is governed by the unknown gearbox stiffness (Spearman rho -0.91). These
  numbers rank what matters under the assumptions; they are not predictions of the hardware.
* Mechanical end stops are not modelled. 623ZZ bearing clearance is not included.

## Implemented

| Subsystem | Module | State |
|---|---|---|
| Units, transforms, schema | `motionproof/core` | Tested |
| CAD import (STEP, STL, OBJ, URDF, MJCF), mesh checks, cylinder detection, exact fit measurement | `motionproof/cad` | Tested |
| Distributions, copula sampling, designs, Cp/Cpk, stacks, validation findings | `motionproof/tolerances` | Tested |
| Variant resolver, fits, radial play, misalignment | `motionproof/manufacturing` | Tested |
| Planetary lost-motion model, motor torque-speed limit | `motionproof/transmissions` | Tested against the stated formulas |
| Synthetic reference design with Level A regeneration | `motionproof/reference` | Tested |
| Drive-train dynamics on MuJoCo, tasks, metrics | `motionproof/simulation` | 14 analytic tests |
| Experiments, checkpoint/resume, replay | `motionproof/experiments` | Tested |
| Statistics, sensitivity, worst-case search, minimisation, allocation screen, comparison | `statistics`, `sensitivity`, `optimisation` | Tested |
| Calibration with holdout and identifiability warnings | `motionproof/calibration` | Tested on synthetic recordings only |
| Reports (JSON, Markdown, CSV, PDF) | `motionproof/reporting` | Tested |
| REST API with background jobs, SQLite workspace | `motionproof/api`, `persistence` | End-to-end test |
| CLI and Python SDK | `motionproof/cli`, `experiments/__init__.py` | Tested, the SDK example in docs/python-sdk.md is a test |
| React application, 16 screens | `frontend/src` | Builds; partly exercised by hand (see below) |
| Optional AI assistant (Ollama, Anthropic, OpenAI-compatible) | `motionproof/ai`, `docs/ai-assistant.md` | tests/integration/test_ai.py (16): configuration, https-only keys, request and response shapes, error handling without leaking the key, daily limit; **tested against fakes only, never against a live provider or a running Ollama** |

## Not done or not verified

* **Fusion 360.** No Fusion add-in is included and no Fusion-exported assembly has been
  imported. The intended path (export with ACDC4Robot or Fusion2Mujoco, import the MJCF) is
  untested.
* **No physical measurements.** Nothing has been compared with real hardware. The reference
  gearbox is synthetic and all of its tolerances, motor and gearbox values are assumptions.
* **Level B** (feature-level variation of imported STEP geometry) is not implemented. Imported
  models use Level C relations only.
* **Frontend screens not exercised by hand:** CAD import upload, feature registration,
  mechanics editor, experiment builder launch, live monitor during a run, worst-case,
  optimisation, comparison, calibration and reports. They compile and call tested endpoints,
  but their interaction has not been walked through by hand. Automated Playwright tests open
  every screen with a model selected and check that none fails to render; they do not drive
  each screen's launch buttons.
* **Responsive layout** was looked at only at about 800 px and 1600 px widths. Three-column
  screens are cramped below roughly 1100 px.
* **NSGA-II** is not implemented; allocation is a Latin-hypercube screen with Pareto filtering.
* **Fidelity 3 and 4** (tooth contact, bearing contact, FEA, thermal) are not implemented.
* Planar, pin-slot and ball joints cannot be driven; only revolute joints.
* Only `payload_mass` and `speed_scale` can be varied as operating conditions.
* Pushed to GitHub. Licence: MIT.
* CI workflow (Windows and Linux, E2E with bundled Chromium) has never run: there is no remote.
  Locally the E2E tests ran with the installed Chrome (`MP_E2E_CHANNEL=chrome`) because the
  Playwright Chromium download did not complete on this machine.

## Known defects and modelling caveats

1. Trapped friction windup relaxes: MuJoCo's friction constraint is soft, so sub-threshold
   spring preload creeps out. Lost motion sits at the backlash value rather than up to
   `backlash + 2·friction/stiffness`.
2. With a one-sided gravity load the flanks never separate, so backlash does not appear as lost
   motion. This is physically correct but means the task must cross a load reversal (the
   reference experiment reverses about the vertical pose).
3. One pytest run of the SDK example stalled for more than five minutes and did not reproduce
   (it passes in about 10 s). Cause unknown.
4. `motionproof experiment run` prints tables with truncated column text in narrow terminals.
5. The first request after server start is slow (a few seconds) while CadQuery loads.
6. Model detail and readiness reload the model on every request; fine for the reference
   design, untested on large assemblies.

## Next tasks

1. Import a real Fusion-exported MJCF and a real STEP assembly; fix what breaks.
2. Record a reversal test on physical hardware and run calibration with a separate holdout.
3. Drive each screen's launch actions in the E2E suite.
4. Check the first CI run on GitHub.
5. Level B feature variation for cylindrical features of imported STEP solids.
