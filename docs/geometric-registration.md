# Geometric registration

`motionproof/scans/registration.py`

* **Nominal**: the component mesh (millimetres) sampled into 150,000 oriented points.
* **Initial pose**: centroids and principal axes, testing the four proper orientations; or a
  **datum alignment**: a 3-2-1 frame from a primary plane normal, a secondary direction and an
  origin (`datum_frame`, `align_by_datums`).
* **ICP**: trimmed (5 % of the worst residuals ignored), point-to-plane by default. Degrees of
  freedom fixed by datums can be **locked** (`rx ry rz tx ty tz`, nominal frame), so ICP only
  refines what the datums leave open. Unconstrained ICP is reported as a best fit.

Reported: method, RMS and maximum residual, points used and rejected, iterations, convergence,
locked DOF and diagnostics. The registration is **valid for inspection** only if it converged,
used at least 70 % of the points and its RMS is below the acceptance threshold (given, or
5 x the measured noise / 3 x the nominal sampling spacing). Otherwise the interface says the
dimensions must not be used and refuses approval.

Tested: known pose recovery on an asymmetric bracket (within 5e-3 in the transform), locked
DOF honoured, a wrong part rejected.
