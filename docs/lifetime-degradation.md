# Lifetime degradation

`motionproof/degradation/model.py`. Model-based projections, not service-life predictions.

A mechanism changes one joint parameter (backlash, friction, stiffness, radial play,
efficiency, damping) with cycles: linear, exponential or piecewise; parameters come from the
user or from `fit_progression` on measurements (with standard errors; valid inside the measured
range). A rate standard deviation gives a band (rate -/+ 1.96 sigma).

The experiment evaluates each interval with Level 1 (a pose) or Level 2 (a task), checks the
constraints and interpolates the requirement crossing. `compare_maintenance` places the
crossing relative to an inspection interval.

Not modelled: wear physics, load, speed, temperature and lubrication history, interaction
between mechanisms.

Verified (benchmark I): a SYNTHETIC linear wear law recovered within 5 %; crossing within 0.1 %
of the closed form at Level 1 and 2 % at Level 2.
