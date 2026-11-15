# CLI reference

Exit codes: 0 success; 1 negative engineering result (failures found, not reproduced, model
blocked); 2 usage or input error. `--home` selects the workspace.

| Command | Purpose |
|---|---|
| `motionproof doctor` | Check dependencies and run a reference simulation |
| `motionproof inspect FILE [--json]` | Inspect a CAD or model file without importing |
| `motionproof reference create DIR` | Write the synthetic reference model |
| `motionproof model validate MODEL.yaml` | Readiness report |
| `motionproof tolerance inspect MODEL.yaml` | Tolerances, fit classes, capability, findings |
| `motionproof assembly generate-variants MODEL.yaml [--samples N --seed S -o FILE]` | Variants and derived quantities |
| `motionproof experiment run EXPERIMENT.yaml` | Create and run an experiment |
| `motionproof experiment inspect EXP` | Configuration and summary |
| `motionproof experiment replay EXP [SCENARIO]` | Replay one or all scenarios |
| `motionproof experiment analyse EXP METRIC` | Rank-correlation sensitivity |
| `motionproof experiment compare EXP S1 S2` | Compare two scenarios |
| `motionproof experiment export EXP SCENARIO FILE` | Self-contained scenario JSON with trace |
| `motionproof optimise EXP METRIC [--algorithm --budget --seed --minimise]` | Worst-case search |
| `motionproof calibration fit DATA.csv -c CONFIG.yaml [--holdout FILE]` | Calibration |
| `motionproof report EXP [-o DIR]` | JSON, Markdown, CSV and PDF report |
| `motionproof serve [--port --home]` | API and web application |

An experiment file is the experiment configuration plus a `model:` path; see
`examples/experiment_reversal_1000.yaml`.
