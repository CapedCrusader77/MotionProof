# Experiment design

An experiment = model snapshot + task + sampling + operating variations + constraints.

| Method | Use | Interval |
|---|---|---|
| Monte Carlo | Estimating pass fractions | Wilson |
| Latin hypercube, Sobol | Better coverage for sensitivity | Only with ≥ 2 randomised replicates |
| Boundary | Each variable at its bounds, others nominal | None (deterministic probe) |
| Corners | Combinations of bounds | None (deterministic probe) |

Bounds are the exact support for bounded distributions and the ±3σ-equivalent quantiles
otherwise. Operating variables: `payload_mass`, `speed_scale`.

**Manifest.** `manifest.json` stores the full model specification, fingerprints, configuration,
the complete design matrix, correlation matrix and software versions. It is written once. A
run with a model that differs from the snapshot is refused.

**Checkpointing.** One JSON line per finished scenario. An interrupted run resumes after the
last complete line; the resumed result is identical to an uninterrupted run (tested).

**Replay.** Any scenario can be re-simulated from the manifest and compared metric by metric.

Constraints compare one metric with a limit. A constraint on a metric the task does not produce
is rejected before anything runs.
