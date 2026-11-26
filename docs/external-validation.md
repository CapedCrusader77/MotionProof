# External experimental validation

MotionProof can import public experimental robot datasets, fit compatible model components on
identification trials, predict separate holdout trials, and report the prediction accuracy.
This measures the model components on **external systems**. It is not a validation of the
MotionProof reference gearbox or of any user hardware; that is benchmark J, which stays NOT RUN
until a physical rig is tested.

## Workflow

```bash
uv sync --extra external
```

```bash
uv run motionproof external list
```

```bash
uv run motionproof external import stuttgart-te
```

```bash
uv run motionproof external inspect stuttgart-te
```

```bash
uv run motionproof external validate transmission-error-v4
```

```bash
uv run motionproof external report VALIDATION_001
```

```bash
uv run motionproof external benchmark
```

`--data DIR` (or `MOTIONPROOF_EXTERNAL_DATA`) selects where data and runs are stored; the
default is `external_data/`, which is git-ignored. Importing is the only step that uses the
network, and only when you run it. The API equivalents are under `/api/v1/external/`, and the
**External validation** screen in the web application shows datasets, signal mappings, runs,
measured-versus-predicted plots, residuals and metrics.

## Rules the framework enforces

* **Integrity.** Files are downloaded once to `raw/` and never modified. The publisher's
  checksum (SHA-256 for Anchor-Lab, MD5 for DaRUS and KUKA) is verified; a mismatch stops the
  import. NIST publishes no checksums, so SHA-256 is recorded at import and verified later.
* **Schema.** Every signal has an SI unit, its original field name and the conversion applied.
  Non-finite values are rejected; missing signals are absent, never filled with zeros.
  Unknown units stay out: SO-101 `present_load_raw` is raw servo units and is not imported.
* **Time.** Original time stamps are kept (relative to the trial start; the absolute start is
  stored). Alignment is linear interpolation inside the shared span; extrapolation raises.
* **Splits.** Identification, validation and unused trials are fixed by the protocol and split
  by whole trial. `check_disjoint` refuses any overlap. Fitting functions receive only
  identification trials; a test changes the validation files and checks that the fitted model
  stays identical.
* **Acceptance.** Criteria were committed before the first run. Changing a criterion means a new
  protocol ID; old results stay.
* **No hidden failures.** Every run is recorded with its status, including FAIL, NOT RUN,
  INCOMPATIBLE DATA and INSUFFICIENT DATA.
* **Comparable quantities only.** Each protocol names the measured quantity it predicts. When
  the dataset quantity differs from a MotionProof output (for example H1 `elbow_tau` is a
  firmware torque estimate), the protocol says so.

## Run records

`external_data/runs/VALIDATION_NNN/record.json` stores dataset source, version, licence and
citation, the checksums of every file used, adapter and MotionProof versions, the signal
transformations, the identification and validation trial IDs, the model configuration,
fitted parameters with identifiability diagnostics, all metrics and the reproduce command.
`report.md` and PNG plots sit next to it. Runs are never overwritten.

## Metrics

Residual r = observed − predicted at the same instants. Reported: RMSE, MAE, maximum absolute
error, mean error (bias), bias normalised by the observed standard deviation, NRMSE (RMSE / std
of the observed signal), R², Pearson correlation, residual percentiles and histogram, and errors
grouped by speed or operating condition where the dataset defines them.

## Evidence in the model trust system

Imported data are labelled `EXTERNAL_CALIBRATION` (identification trials) or
`EXTERNAL_VALIDATION` (holdout trials), with dataset, trial, citation, licence, role and
transformation, and the scope statement "external system; not a measurement of the MotionProof
reference gearbox or of any user hardware". They never enter a MotionProof model as measured
values of the user's parts.

## Current results (2026-11-26)

| ID | Case | Status | In one line |
|---|---|---|---|
| X1 | Stäubli TX2-40 transmission error (v4, not blind) | PASS | v3 failed on axis 3 (0.82×, needs ≤ 0.5×): the error grew linearly with speed. v4 adds the gearbox windup under viscous friction (one coefficient per axis): axis 2 0.04×, axis 3 0.28×. |
| X2 | H1 elbow friction | FAIL | Rigid model and friction model both explain about 22 % of the torque-estimate variance; friction adds 1 %. Most of the rest is a ~200 Hz oscillation fixed in time (controller or sensor), which no joint model predicts; even with it filtered out, friction on this stand is about 0.1 N·m and adds about 4 %. No revision made. |
| X3 | SO-101 elbow response | PASS | Simulated servo with dead band: 0.32× baseline RMSE on 6 heldout trials; fitted dead band 0.056 rad. |
| X4 | KUKA per-axis torque (v2, not blind) | PASS | v1 failed on A2, A3, A5: each axis saw gravity through its own angle only. v2 adds multibody gravity (q2 + q3, and the wrist on A5): all axes 0.66–0.80×. Friction alone, against the same coupled gravity without friction: 0.69–0.88×. |
| X5 | UR5 joint tracking error (v2, not blind) | FAIL | v1: J1 passed (0.73×), J2–J6 0.89–1.00×. v2 adds the position loop's acceleration lag (1/ωn² × target acceleration): J1, J3 (0.799×) and J4 pass; J2 0.86×, J5 0.97×, J6 1.00× do not. J5 and J6 errors are near the controller's resolution. No temperature association (abs(rho) ≤ 0.12). |
| X6 | UR5 TCP accuracy | INSUFFICIENT DATA | No per-run TCP measurements are published. |
| X7 | COMPAct 3D-printed planetary, no-load backlash (added 2026-11-26, not blind) | FAIL | Print files alone give 0.6 mrad; with the project's FDM tolerance assumptions 1.4–5.5 mrad (5–95 %); published 10.3 mrad. |
| X8 | Stäubli TX2-40 axis 1, transmission error (**blind** test of the X1 v4 model) | PASS | Protocol committed (40d911f) before any axis 1 file was downloaded; model form chosen on axes 2 and 3, applied unchanged. 0.223× baseline (needs ≤ 0.5×); validation 1.23× identification RMSE. Without the windup term the same fit gives 0.863×, so the term found on axes 2 and 3 carries over: fitted windup −7.9e-3 rad per rad/s, against −8.3e-3 and −5.6e-3 on axes 2 and 3. |

X7 differs from X1–X6. It compares with one published value, not measurement series, and its
protocol was written after that value was known; only the tolerance model (the FDM assumptions
written on 2026-11-15 for the project's own printed elbow) was fixed beforehand. The geometry is
measured from the authors' print files (`motionproof external import compact-sspg`, pinned to a
commit). The published quantity is also wider than the model's backlash: it is the peak-to-peak
gap between motor and output angle over a slow sine motion, which includes friction windup and
once-per-revolution errors. Still, the gap is large: the model would need about 0.23 mm of free
travel at each planet, against 0.08 mm at its median. Either the FDM assumptions are too
optimistic for printed gears, or real printed gearboxes have lost motion the model leaves out.

Checked afterwards against the print files (2026-11-26): pin and bearing play cannot supply the
missing travel. The carrier has printed 8 mm planet shafts (measured 7.90–7.94 mm on the facets)
around 5 mm bolt holes, and each planet has 12 mm bearing seats (11.96 mm) for 8 × 12 mm
bearings; these fits are drawn without clearance, so the free play left there is the bearings'
internal clearance, a few micrometres. That rules out the planet pin as the explanation and is
why X7 was not revised with `carrier_pin_clearance`. The remaining candidates have no published
numbers: the thickness error of printed 0.5-module teeth (about 0.79 mm thick, two nozzle
widths) and friction windup inside the measured quantity (2 × no-load drag / 242.7 N·m/rad
published stiffness; the drag is not published).

What this shows: the dead-band (backlash) and servo model reproduces a real joint's response
to unseen commands (X3), and the periodic TE term captures the position-dependent transmission
error of a real gearbox when speed is low (X1 axis 2). It also shows where the reduced-order
components fall short: speed-dependent transmission error, coupled multibody torque, and the
H1 torque estimate. These are model limitations found on external hardware, not statements
about the reference gearbox.

## Limitations

* Each external system is modelled on its own. A good fit on a Stäubli gearbox says nothing
  about a 3D-printed planetary stage.
* The model forms are MotionProof's reduced-order components (periodic TE plus dead band,
  Coulomb plus viscous friction, static deflection plus lag). Effects outside them (coupled
  multibody dynamics, thermal friction drift, hysteresis) appear as residual.
* Standard errors assume independent residuals and are optimistic for time series.
* Results depend on dataset units that are not always documented; each inferred unit is listed
  in `docs/external-datasets.md` and in the run's transformations.

See also: `docs/external-datasets.md`, `docs/transmission-error-validation.md`,
`docs/robot-dynamics-validation.md`, `docs/position-accuracy-validation.md` and the generated
`EXTERNAL_VALIDATION_RESULTS.md`.
