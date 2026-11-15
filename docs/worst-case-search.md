# Worst-case search

Objective: maximise or minimise one metric over the bounded variable space. Algorithms:
differential evolution (SciPy, seeded), random search, random bound combinations.

Procedure: evaluate the nominal point, search within the budget, then run a **fresh confirmation
simulation** of the best configuration with traces. The result reports the proposed value, the
confirmed value and whether they match; it is labelled a failure only if the confirmation
violates a constraint. The search history is stored.

The result is the worst configuration found within the budget, not a proven global worst case.

**Failure minimisation.** Starting from a failing configuration, variables are returned to
nominal one at a time (smallest deviation first) while the same failure category persists. The
remaining "essential" parameters and a confirmation run are stored.
