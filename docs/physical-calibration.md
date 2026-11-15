# Physical calibration

**CSV schema.** One row per sample; a time column (`s` or `ms`) and one or more signals:

| Signal | Units |
|---|---|
| `output_angle`, `motor_angle` (referred to the output) | rad, deg |
| `motor_torque` | N*m, mN*m |
| `output_velocity` | rad/s, deg/s |

Time must be strictly increasing; at least 10 samples. The recording must be the task that the
calibration simulates, with the same timing.

**Parameters:** backlash, stiffness, friction, efficiency, damping, zero offset, damping ratio,
each with bounds. Estimation is bounded nonlinear least squares from three starting points.

**Holdout.** A separate recording is independent evidence. Without one, the last 30 % of the
calibration recording is held out and the report states that this is weaker.

**Report:** estimates with standard errors, parameter correlation, condition number,
predicted-versus-measured traces and residuals for both sets, RMSE, MAE and maximum deviation,
and warnings for insensitive parameters, standard error above 50 %, estimates on a bound,
strongly correlated pairs and holdout RMSE more than twice the calibration RMSE.

Status: verified only on synthetic recordings with known parameters. No real measurement has
been used. MotionProof generates no measurement data for you.
