# Robot dynamics and friction validation (X2, X3, X4)

Each external system is a separate model and validation case. None is treated as equivalent
to the MotionProof reference gearbox.

## X2. Unitree H1 elbow on the Anchor-Lab test stand

* Quantity: `elbow_tau`, the actuator's torque estimate (N·m). It is not a load-cell
  measurement, so the comparison tests the model against the actuator's own torque estimate.
* Signals: `elbow_q`, `elbow_dq`, `elbow_tau`, interpolated onto a common uniform 2 ms grid
  inside their shared time span. `ddq` is the Savitzky–Golay derivative of `dq` (21 samples,
  cubic); 25 samples are trimmed at each end.
* Baseline B0: `τ = J q̈ + g1 sin q + g2 cos q + τ0` (rigid joint, no friction).
* Model: B0 + `c q̇ + F_c tanh(q̇ / 0.02 rad/s)`, MotionProof's viscous damping and Coulomb
  friction (MuJoCo `frictionloss`).
* Split: stand positions 8, 9, 10 for identification; position 11 for validation. Whole trials.
* Acceptance: validation RMSE(model) ≤ 0.8 × RMSE(B0) and NRMSE(model) ≤ 0.35.
* Identifiability: scaled condition number, standard errors and parameter pairs with
  |correlation| > 0.95 are reported. Standard errors are optimistic for correlated residuals.

## X3. SO-101 elbow, simulated response to the recorded command

* Quantity: `elbow/actual_q` (rad) at its own sample instants.
* Excitation: the recorded `elbow/command_q`, held between its samples (zero-order hold, about
  29 ms).
* Model, simulated at 1 ms: a second-order position loop (natural frequency ωn, damping ζ)
  with a velocity limit `vmax`, driving the joint through a dead band of width `b` (the
  MotionProof backlash model), plus a constant offset. Parameters are fitted by nonlinear least
  squares on the identification trial only.
* Baseline B0: actual = held command + constant offset.
* Split: train trial `single-joint-elbow` for identification. Validation: every heldout trial
  whose elbow command spans at least 0.1 rad; the others are listed as unused.
* Acceptance: pooled validation RMSE(model) ≤ 0.6 × RMSE(B0).

## X4. KUKA KR300 R2500 ultra SE, per-axis inverse dynamics

* Quantity: motor torque of each axis (N·m), on the benchmark's test set.
* Model per axis: the X2 model applied to that axis alone. Coupling between axes,
  pose-dependent inertia, Coriolis terms and the axis-2 hydraulic counterbalance are **not**
  modelled. MotionProof has no multibody model of this robot, so X4 measures only what a
  single-joint drive model can explain.
* Baseline B0 per axis: without the friction terms.
* Split: benchmark training and test sets, unchanged.
* Acceptance: every axis, test RMSE(model) ≤ 0.8 × RMSE(B0).
* The benchmark publishes its own baseline and figures of merit. They are not reproduced here,
  and the RMSE values here are not claimed to be comparable with them.

## Reproduce

```bash
uv run motionproof external import anchor-lab
```

```bash
uv run motionproof external validate h1-friction
```

```bash
uv run motionproof external validate so101-tracking
```

```bash
uv run motionproof external import kuka-kr300
```

```bash
uv run motionproof external validate kuka-inverse
```

Results: `EXTERNAL_VALIDATION_RESULTS.md`.
