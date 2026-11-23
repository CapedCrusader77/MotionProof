# Architecture

MotionProof is a modular monolith: one Python package, one SQLite file, one background worker,
one React application. The engineering engine does not import the web layer or the optional AI.

```
CAD / URDF / MJCF ──> cad.importers ──> inventory.json + viewer meshes
                                              │
model.yaml (features, datums, tolerances, fits, gear stages, drives)
        │ core.schema (validated)             │
        v                                     v
tolerances.sampling ──> design matrix    model.MechanicalModel (spec + MuJoCo model)
        │                                     │
        v                                     │
manufacturing.variants ── transmissions.gears ─┤   one Variant per row:
   (fits, backlash, radial play, tilt)        │   fits, backlash, play, misalignment
        │                                     v
        └────────────────────────────> simulation.engine (MuJoCo + drive train)
                                              │ metrics, traces
                                              v
experiments.runner (manifest, results.jsonl, replay)
        │
        ├─ statistics.robustness      ├─ optimisation.worst_case / allocation
        ├─ sensitivity.analysis       ├─ calibration.fit
        └─ reporting.report
                │
services.py ──> api.app (FastAPI, api.auth, api.jobs) ──> frontend (React, three.js)
            └─> cli.main (Typer)
```

## Package map

| Package | Responsibility |
|---|---|
| `core` | Units, rigid transforms, the validated model schema |
| `cad` | Import, mesh validation, cylinder detection, exact distance and interference |
| `tolerances` | Distributions, copula sampling, designs, capability, validation findings |
| `manufacturing` | Turns actual dimensions into fits, backlash, play and misalignment |
| `transmissions` | Planetary relations, motor torque availability |
| `reference` | The synthetic NEMA 17 planetary-joint design (parametric CadQuery) |
| `simulation` | Tasks, motion plans, the drive-train dynamics loop around MuJoCo |
| `experiments` | Immutable manifests, checkpointed execution, replay, SDK |
| `statistics`, `sensitivity`, `optimisation`, `calibration`, `reporting` | Analyses on stored results |
| `persistence` | Workspace folders and the SQLite index |
| `api`, `cli`, `services` | Interfaces; `services` holds logic shared by both |
| `api.auth` | Accounts, sessions and the middleware that requires one; hands each request the signed-in account's own `Store` and tags background jobs with their owner |
| `ai` | Optional assistant (Ollama, Anthropic or an OpenAI-compatible API) that only sees a digest of stored results |

## Decisions

1. **Keep the `motionproof/` package** instead of the `backend/app/domain` tree suggested in the
   brief. The subpackages map one-to-one onto the requested domains, and a single importable
   package is what the CLI and SDK need.
2. **MuJoCo integrates the links; the drive train is integrated beside it in Python.** This
   keeps the backlash model explicit and testable and works for imported MJCF models. Friction
   is delegated to MuJoCo's implicit friction constraint because an explicit friction term was
   unstable at the chosen time step.
3. **Held joints are locked with a zero-width joint range**, not a stiff servo. A stiff explicit
   servo went unstable above about 0.5 kg payload (regression test exists).
4. **Motor control is PD with load feedforward**, not PID. An integral term overshot after moves
   and pushed the output through the dead band, contaminating the lost-motion measurement.
5. **No Fusion exporter.** Maintained exporters exist; MotionProof imports their output.
6. **No new Python dependencies.** PDF output uses Matplotlib, which CadQuery already brings in.
   Hatchling was added as the build backend so the `motionproof` command installs.
7. **Experiments snapshot the whole model specification** so later edits cannot change what an
   experiment means; a changed model is refused rather than silently mixed.
8. **Polling instead of WebSockets** for progress: one local user, one worker.

## Data layout

```
workspace/motionproof.db
workspace/projects/PRJ_001/models/MDL_001/{model.yaml, geometry/, original/, calibration.json}
workspace/projects/PRJ_001/experiments/EXP_001/{manifest.json, results.jsonl, worst_case.json, report/}
workspace/projects/PRJ_001/measurements/*.csv
```

## Advanced subsystems (0.3.0)

All of them read the one `MechanicalModel` and the existing experiment machinery; none has its
own simulator.

```
point cloud --scans.pointcloud--> clean --scans.registration (datum / ICP)--> aligned
   aligned --scans.inspection--> deviation, fitted features --approve--> tolerance values
                                                                            |
process model --process.model--> virtual batch -------------------------> tolerance values
                                                                            v
                                        manufacturing.variants (fits, backlash, play, tilt)
                                                   |                 |
                            fidelity.static (L1) <-+-> simulation.engine (L2)
                                                   |
  adaptive.sampler (GP active learning) -----------+  uses evaluate_scenario as the truth
  workspace.maps (per-pose L1, L2 check) ----------+
  degradation.model (parameter progressions) ------+
  rootcause.analysis (association, local, counterfactual reruns)
  hardware.device (protocol, simulated / serial device, safety) -> calibration.fit
  challenge.engine (screen + differential evolution, Clopper-Pearson, L2 verification)
  benchmarks.suite (A-N, expected vs actual)
                                                   |
advanced.py (services) -> api.advanced_routes (/scans, /manufacturing, /experiments/adaptive,
                          /workspace, /degradation, /fidelity, /rootcause, /hardware,
                          /challenges, /benchmarks, /models/{id}/trust|as-built, /artifacts)
                       -> cli.main (scan, manufacturing, experiment adaptive, workspace,
                          degradation, hardware, challenge, benchmark)
```

**Artifacts.** Every advanced result is an artifact (`SCN_`, `BAT_`, `ADP_`, `WSM_`, `DEG_`,
`HWS_`, `CHL_`, `RCA_`, `FID_`, `BEN_`) indexed in the SQLite `artifacts` table and stored as
JSON in `workspace/projects/<PRJ>/artifacts/<id>/`, with the fingerprint of the model it used.

**Decisions.**

9. A small Gaussian process and ICP are written on NumPy/SciPy instead of adding
   scikit-learn or Open3D; each is tested against known answers.
10. Reliability demonstration in the Challenge uses the exact Clopper-Pearson bound (Wilson
    is kept for reporting Monte Carlo experiments), because a demonstration must not be
    optimistic.
11. Surrogates and Level 1 results are never stored as simulation results; every value
    carries the level or kind that produced it.
12. Serial hardware support is optional (`pyserial` not installed); the simulated device makes
    the whole software path testable without equipment.
