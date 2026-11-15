# Sensitivity analysis

| Method | Cost | What it says | Limits |
|---|---|---|---|
| Spearman rank correlation, Fisher-z interval | None (uses results) | Monotonic association and its direction | Not causation; misses non-monotonic effects |
| Standardised regression coefficients | None | Approximate variance share | Only as good as R², which is shown; assumes uncorrelated inputs |
| Interaction screen | None | Pairwise product terms among the top variables | Screening only |
| One-at-a-time | 2d + 1 simulations | Effect of moving each variable alone to its bounds | No interactions |
| Sobol indices | N·(d + 2) simulations | First- and total-order variance shares with bootstrap intervals | Requires independent inputs; refused when correlations are defined |

The interface labels every result with its method and never shows Sobol indices unless that
analysis has been run. A variable that varies widely but has a correlation interval spanning
zero is reported as "not distinguishable from zero".
