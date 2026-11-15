# Backlash and drive-train dynamics

Each driven joint has a rotor (output-referred angle `θr`, inertia `Jm·N²`) coupled to the link
joint (`θo`, integrated by MuJoCo):

```
gap = θr + TE(θr) + zero_offset − θo
s   = gap − clip(gap, −b/2, +b/2)        engaged deflection, zero inside the dead band
τc  = k·s + c·(ωr − ωo)   while engaged; a flank can push, never pull
```

* `b` backlash, `k` torsional stiffness, `c` from the damping ratio of the rotor-on-spring mode.
* Losses: mesh friction `(1 − η)·|τc|` plus constant output friction, applied as a MuJoCo
  friction constraint, so a driving gearbox delivers `η·τc` and stiction exists.
* Motor: PD position control on the **motor** side with load feedforward, limited by the
  torque-speed curve. Lost motion in the gearbox is therefore not corrected, as with a stepper
  or a motor-side encoder.

Validation (tests in `tests/physics`, point mass on a massless arm):

| Case | Expectation | Accepted error |
|---|---|---|
| Static hold | motor torque = m·g·L / N | 0.2 % |
| Static deflection under gravity | b/2 + τ/k | 0.5 % |
| Reversal without gravity | lost motion = b (bounded above by b + 2f/k) | 20 µrad |
| Reversal with one-sided gravity load | no lost motion (flanks never separate) | < 0.2 mrad |
| Mid-stroke torque with friction f, efficiency η | f / (η·N) | 3 % |
| Overload | torque saturates, position is lost | — |

Known caveat: sub-threshold spring preload creeps out through the soft friction constraint, so
trapped windup is under-estimated.
