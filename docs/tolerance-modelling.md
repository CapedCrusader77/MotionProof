# Tolerance modelling

Every tolerance has: id, component, feature, parameter, characteristic, category, nominal, upper
and lower deviation, unit, datum, distribution, correlation group, source, confidence
(`specified`, `measured`, `estimated`, `assumed`) and verification status.

**Distributions:** uniform, normal, truncated normal, log-normal, discrete, empirical
(resampled measurements). All are sampled through their quantile function.

**Out-of-spec parts are simulated, not discarded.** If a distribution extends beyond the limits,
those scenarios are flagged `out_of_spec` and still evaluated.

**Nominal assembly:** uses the nominal size when it lies inside the limits, otherwise the middle
of the zone (an 8 g6 shaft is never exactly 8.000 mm).

**Correlation:** pairwise coefficients applied through a Gaussian copula; the coefficient is the
correlation of the normal scores. Each pair records whether it is measured or assumed.
Inconsistent sets of coefficients are rejected. Nothing is correlated unless you say so.

**Geometric tolerances (scoped):** position as x and y deviations sharing a `zone_group`
(checked against a circular zone), runout as a total indicator reading plus a phase, and
perpendicularity/parallelism/angularity as an angle. Flatness and circularity are stored but
have no propagation model, and the validation panel says so.

**Capability:** with process mean and standard deviation, Cp and Cpk are reported with warnings
for assumed data, fewer than 30 measurements and Cpk below 1.0 or 1.33. The indices assume a
stable normal process.

A tolerance only affects results if it is bound to a fit, a gear stage or an effect; unbound
tolerances are flagged.
