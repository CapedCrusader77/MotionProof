# Position accuracy and degradation validation (X5, X6)

Data: NIST "Degradation Measurement of Robot Arm Position Accuracy", Universal Robots UR5
(doi:10.18434/M31962).

## X5. Joint position error under speed, payload and temperature

* Quantity: per joint, `e = target q − actual q` (rad) at each controller sample. Both values
  come from the UR5 controller. The actual position is the controller's encoder reading, not an
  external measurement of the joint output.
* Model per joint: MotionProof's static drive deflection plus a position-loop lag,
  `e = e0 + τ_target / k + (b/2) sign(q̇_target) + lag × q̇_target`, fitted by linear least
  squares (parameters `e0`, `1/k`, `b/2`, `lag`).
* Baseline B0: a constant equal to the identification mean error.
* Split: repeats 1 and 2 of every condition for identification; repeat 3 for validation.
  Conditions: half and full speed, 16 and 45 lb payload, and cold start at 45 lb.
* Acceptance: every joint J1–J6, validation RMSE(model) ≤ 0.8 × RMSE(B0).
* Also reported per joint: validation errors grouped by speed and by payload, and the Spearman
  correlation between the absolute residual and joint temperature. That correlation is an
  association, not evidence of a cause.

## X6. TCP accuracy degradation

INSUFFICIENT DATA. The dataset publishes the measured TCP deviation (7-D measurement system)
for 6 positions only, without the run, condition or trajectory they belong to. A predicted TCP
error or a degradation trend therefore cannot be compared with any measurement. Benchmark X6
stays INSUFFICIENT DATA until per-run TCP measurements are available.

## What this does not show

* No wear-life prediction: the runs span a few hours of operation, not a service life.
  MotionProof's degradation module stays a reduced-order projection of user-supplied
  progression laws.
* No TCP accuracy validation (X6).
* No statement about the MotionProof reference arm or any user hardware.

## Reproduce

```bash
uv run motionproof external import nist-ur5
```

```bash
uv run motionproof external validate nist-tracking
```

Results: `EXTERNAL_VALIDATION_RESULTS.md`.
