# External validation roadmap

MotionProof cannot yet be tested on its own physical hardware (benchmark J is NOT RUN). This
roadmap describes how public experimental robot datasets are used instead, to measure how well
MotionProof's model components reproduce real measured behaviour **of other robots**. No
external dataset is evidence about the 33:1 NEMA 17 reference gearbox.

## 1. What already existed and is reused

| MotionProof part | Reused for |
|---|---|
| Drive model in `simulation/engine.py`: gap equation with the periodic transmission-error term `TE(θ) = Σ a sin(cθ + φ)` and the backlash dead band `b/2` | model form of X1 (transmission error) and X3 (servo dead band) |
| Drive friction (Coulomb `frictionloss`, viscous `damping`) | model form of X2 and X4 |
| Static deflection `b/2 + τ/k` (fidelity L1) | model form of X5 |
| Calibration practice in `calibration/fit.py`: fit on one recording, validate on a separate holdout, identifiability warnings | split rules and identifiability reporting in every protocol |
| Statistics conventions (residuals, intervals) | `external_validation/metrics` |
| Model trust and provenance (`advanced.py` trust panel, evidence classes) | evidence records `EXTERNAL_MEASURED`, `EXTERNAL_CALIBRATION`, `EXTERNAL_VALIDATION` |
| CLI (Typer), API (FastAPI, job manager), React application | `motionproof external ...`, `/api/v1/external/*`, External validation screen |
| Synthetic benchmark suite A–N | left unchanged; external benchmarks get IDs X1–X6 |

What is new is only what did not exist: dataset adapters, integrity checks, a trial schema, the
validation protocols, and the run records.

## 2. Datasets, after inspecting the actual files

| Dataset | What the files contain (inspected) | Usable for | Not usable for |
|---|---|---|---|
| NVIDIA Anchor-Lab (Apache-2.0) | long-form parquet `time_ns, experiment, field, value`. H1 test stand: `elbow_q, elbow_dq, elbow_tau, elbow_current, elbow_temp, elbow_voltage` at 500 Hz, 60 s per trial. SO-101: per joint `actual_q, command_q, dq, tau_abs, temperature, voltage, is_moving, present_load_raw` | joint friction and inertia (H1); simulated response to a recorded command, dead band (SO-101) | transmission error, direct backlash (not measured); `elbow_tau` is the actuator's torque estimate, not a load cell |
| Stuttgart DaRUS-5760 (CC BY 4.0) | per file `theta, q_set, theta_TE` (rad), position domain, published identification and validation folders, MD5 per file | transmission-error identification and holdout prediction | time-domain dynamics (no time stamps) |
| NIST UR5 (NIST licence) | 18 CSV runs (speed half/full, payload 16/45 lb, cold start, 3 repeats) with target and actual joint position, velocity, current, target torque and temperature at 125 Hz; TCP deviation for 6 positions only | joint tracking error versus speed, payload and temperature | TCP accuracy prediction (per-run TCP measurements not published) |
| KUKA KR300 benchmark | `.mat` with filtered axis position, velocity, acceleration (deg) and motor torque (N·m), benchmark train/test split | per-axis inverse dynamics with friction | coupled multibody dynamics (MotionProof has no such KUKA model) |

Investigated and not yet adapted: Anchor-Lab G1 single-joint and multi-joint groups, H1 single
and multi-joint groups, the KUKA raw runs and videos.

## 3. Protocols

Pre-registered in `motionproof/external_validation/experiments/protocols.py` and committed
before the first run. Each fixes the identification, validation and unused trials (split by
whole trial, never by row), the baseline, the MotionProof model and the acceptance criterion.

| ID | Protocol | Split |
|---|---|---|
| X1 | transmission error, Stäubli TX2-40 axes 2 and 3 | v3: alternate velocity setpoints of the uncompensated recordings (the published validation files contain compensated residuals; v1 and v2 kept on record) |
| X2 | H1 elbow friction and inertia | stand positions 8–10 / position 11 |
| X3 | SO-101 elbow servo response | train trial / heldout trials that move the elbow |
| X4 | KUKA per-axis inverse dynamics | benchmark train / test |
| X5 | UR5 joint tracking error | repeats 1–2 / repeat 3 of every condition |
| X6 | UR5 TCP accuracy degradation | INSUFFICIENT DATA |

## 4. Next steps

1. Adapt the G1 single-joint groups (same parquet format) as further friction cases.
2. Couple X3's servo model into the full MuJoCo drive simulation instead of the stand-alone
   loop.
3. A multibody model of the KUKA KR300 would be needed for a fair X4; until then X4 reports
   only what a single-joint model can do.
4. When the user's own rig exists, run benchmark J and keep it separate from X1–X6.
