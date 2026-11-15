# Multi-fidelity simulation

| Level | Contents | Status |
|---|---|---|
| L1 quasi-static | kinematics, gravity load, half backlash plus windup, motor static margin, fits, mesh clearance | implemented (`fidelity/static.py`) |
| L2 reduced-order dynamics | MuJoCo multibody + drive train: inertia, friction, motor torque-speed limit, backlash dynamics | implemented |
| L3 contact / structural | gear and bearing contact, flexible bodies | **not implemented** |
| L4 physical | hardware sessions, calibration measurements | software path implemented; no physical data |

`discrepancy` measures L1 against L2 (static hold) on the same variants. `sufficient` refuses an
L1 verdict when the value lies within `2 x` the measured 95 % L1/L2 difference of a limit and
asks for L2. The Engineering Challenge can search at L1 and always verifies at L2.

Measured: frictionless single joint, L1 equals the closed form to 1e-4 and L2 within 0.5 %. With
friction, L1 ignores stiction and the difference grows; benchmark L shows the sufficiency rule
flagging a near-limit case.
