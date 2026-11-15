# Tolerance optimisation

Variables are width scales of selected tolerances (below 1 tightens limits and spread about the
zone centre). Only uniform, normal and truncated-normal tolerances can be scaled.

**Cost.** `cost = Σ fixed + coefficient / scale^exponent` with your coefficients. Without cost
data a unit coefficient is used and the axis is labelled a relative cost index, not a price.

**Method.** A seeded Latin-hypercube screen of candidates plus the current specification, each
evaluated with real Monte Carlo simulation using common random numbers; non-dominated candidates
(cost versus the 95 % quantile of the chosen metric) are marked. The cheapest candidate meeting
the required pass fraction is recommended and then **re-verified** with a larger, independently
seeded run. It is reported as meeting the target only if that verification does.

This is a screen, not a converged multi-objective optimisation; NSGA-II is not implemented.

**Design comparison** evaluates named scale sets against the current specification with the
same random numbers and reports pass fractions with Wilson intervals and metric statistics.
