# Workspace reliability

`motionproof/workspace/maps.py`. For a grid of joint angles and a set of variants (nominal,
virtual Monte Carlo, or the measured as-built variant, optionally with scaled tolerances):

* reachability against joint limits; manipulability (`sqrt(det J J^T)`) with a near-singular
  flag;
* per pose: mean, RMS, maximum and 95 % tip error from the Level 1 quasi-static model;
* probability of meeting a position tolerance, with a Wilson interval only when the variants
  are independent draws;
* the worst verifiable poses re-simulated at Level 2 (held joints must sit at their held
  angle);
* cell-by-cell comparison of two maps on the same grid.

Collision is not evaluated (the models carry no collision geometry). Evaluations are capped at
400,000 per map.

Verified (benchmark H): map RMS within 5 % of direct Level 2 simulation at three poses; a known
2 mrad axis tilt produces the expected pose-dependent error.
