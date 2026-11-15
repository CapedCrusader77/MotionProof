# Engineering Challenge

See `ENGINEERING_CHALLENGE.md` at the repository root for the full description and the
reference result. Summary:

* minimise cost (user coefficients x 1/scale, or a labelled relative index);
* subject to the exact one-sided Clopper-Pearson lower bound of the all-requirements pass
  fraction >= target at the stated confidence;
* decision variables: `scale` (tolerance width and spread) and `shift` (design target);
* search: Latin-hypercube screen + SciPy differential evolution, common random numbers, Level 1
  or Level 2;
* chosen candidate re-verified at Level 2 on fresh scenarios with an independent seed;
* infeasibility and insufficient sample size are reported, never hidden.
