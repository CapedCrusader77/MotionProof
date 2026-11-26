# Transmission-error validation (X1)

Data: Stuttgart DaRUS-5760, Stäubli TX2-40 gearboxes, axes 2 and 3 (CC BY 4.0, cite
doi:10.18419/DARUS-5760).

## Model

MotionProof's drive model contains a periodic transmission-error term and a backlash dead band:

```
gap = θ_rotor + TE(θ_rotor) + zero_offset − θ_output,   TE(θ) = Σ a sin(c θ + φ)
```

On the published data this becomes, per axis,

```
θ_TE(q) = c0 + (b/2)·sign(q̇_set) + Σ_k [a_k sin(k q_set) + c_k cos(k q_set)]
```

* `c0`: constant offset; `b/2`: direction-dependent offset (the dead band's contribution when
  the drive moves in one direction); `k`: integer orders in cycles per joint revolution.
* Orders: the 30 largest in the amplitude spectrum of the **identification** recordings, from
  1 to 4000 (each file resampled to a uniform `q_set` grid of 1e-4 rad, Hann window). The
  validation recordings play no part in choosing them.
* Coefficients: one linear least-squares fit over all identification files of the axis.

Baseline B0: a constant equal to the mean identification transmission error.

## Protocol (current: `transmission-error-v4`, as v3 plus one windup term)

* Identification: recordings in `identification/axis_2` and `identification/axis_3` whose
  velocity setpoint has an even rank when the setpoints of each sign are sorted by magnitude.
* Validation: the recordings with odd rank. Whole recordings, all without compensation.
* Unused: the published `validation/` folder (residual TE with the authors' compensation
  active, a different quantity) and axis 1.
* Orders: as above, restricted to orders with at least 2 full periods over the shortest
  identification recording (k ≥ ceil(4π / span)).
* Quantity: `theta_TE` at each published sample; no resampling for the metrics.
* Acceptance (pre-registered, unchanged since v1): per axis, validation RMSE(model) ≤ 0.5 ×
  validation RMSE(B0) and validation RMSE(model) ≤ 1.5 × identification RMSE(model). X1 passes
  only if both axes pass.

Also reported: metrics by velocity setpoint, residual histogram, a measured-versus-predicted
plot along `q_set`, and the fit's conditioning.

## Protocol history (all runs kept)

| Protocol | Run | Status | What happened |
|---|---|---|---|
| `transmission-error` (v1) | VALIDATION_001 | FAIL | Orders 1–17 complete less than one period over the 3.4 rad joint range, are nearly collinear with the offset (scaled condition number about 4e11) and extrapolate badly. |
| `transmission-error-v2` | VALIDATION_003 | FAIL | Orders limited to at least 2 periods. Same validation error, which led to the real cause: the dataset's own `plot_figures.m` shows the published validation recordings were made **with the authors' Fourier compensation active**. Their θ_TE is the residual after compensation, about 6.5× smaller than in the identification recordings. Comparing a predicted uncompensated TE with it compares different quantities, so v1 and v2 are invalid comparisons. |
| `transmission-error-v3` | VALIDATION_004, VALIDATION_008, VALIDATION_016 | FAIL | Holdout of whole uncompensated recordings at alternate velocity setpoints. Axis 2 PASS (validation RMSE 0.175× baseline); axis 3 FAIL (0.822×, criterion 0.5×). |
| `transmission-error-v4` | VALIDATION_023 | PASS | v3 plus `w · q_set_dot`, the twist of the gearbox under viscous friction torque. Axis 2 0.037×, axis 3 0.281×; validation RMSE 1.2× identification on both. Not blind: written after the v3 residuals were seen. |

v1–v3 were each committed before they ran, with unchanged acceptance thresholds. v4 was written
after v3 ran; split, orders and thresholds are unchanged and the windup term is fitted on the
identification recordings only.

## Finding

The periodic TE term and direction offset reproduce the position-dependent shape well (axis 2
error 1.8e-3 rad against 1.0e-2 rad for the baseline). The remaining error grows steadily with
speed on both axes (axis 3: 0.2 mrad at 0.20 rad/s, 3.8 mrad at 0.67 rad/s). The mean residual
of each recording falls almost linearly with the velocity setpoint: the gearbox twists under
viscous friction torque, which is the drive model's damping acting through its stiffness. v4
adds that one term (fitted windup: axis 2 −8.3e-3, axis 3 −5.6e-3 rad per rad/s) and passes on
both axes. Because v4 was chosen after seeing the v3 residuals, it is not blind; a blind test of
it needs recordings at speeds outside the identification range, or another gearbox.

## Reproduce

```bash
uv run motionproof external import stuttgart-te --group axis_2 --group axis_3
```

```bash
uv run motionproof external validate transmission-error-v4
```

## Limitations

* The model uses `q_set` as the angle argument. Orders that are not integers per joint
  revolution (input-shaft harmonics of a non-integer ratio) are approximated by the nearest
  integers.
* Load and temperature are not part of the data, so their effect on the transmission error
  cannot be checked.
* This is a Stäubli industrial gearbox, not the MotionProof reference planetary stage.

Results: `EXTERNAL_VALIDATION_RESULTS.md`; run records in `validation/external/runs/`.
