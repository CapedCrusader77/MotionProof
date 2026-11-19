# MotionProof Engineering Challenge

**Question:** what is the least expensive tolerance specification that lets the mechanism meet
its requirements, under the stated manufacturing and operating uncertainty, with stated
statistical confidence?

## Formulation

* Decision variables (explicit, bounded): `scale` multiplies a tolerance's width and spread
  about its centre (below 1 tightens); `shift` moves a design target such as a backlash or
  clearance value.
* Requirements: experiment constraints (positioning, lost motion, torque, mesh clearance, ...).
  A scenario passes only if it meets all of them.
* Reliability: feasible when the one-sided exact (Clopper-Pearson) lower bound of the pass
  fraction is at least the target at the given confidence. With zero failures, 90 % at 90 %
  needs 22 scenarios; the run reports this number and refuses to call candidates feasible if
  the search sample is too small.
* Cost, per scaled tolerance, one of two models:
  * **yield (scrap) model**, the defensible one: the feature is made by a process with mean
    `mu` and standard deviation `sigma` (from measured parts, `motionproof measurements
    summary`), every part is inspected, parts outside [L, U] are scrapped. Cost per accepted
    part = `(unit_cost + inspection_cost) / yield`, `yield = Phi((U - mu)/sigma) -
    Phi((L - mu)/sigma)`. Accepted parts then follow the process normal truncated to [L, U],
    and that is what the simulation samples. Every input is a measurement or a cost you know
    (material, machine time, inspection), not a guessed price curve.
  * **reciprocal model**: `fixed + coefficient / scale^exponent`. Without cost data it is a
    relative index and no saving is claimed.
  Shifts carry no cost unless costed.
* Search: seeded Latin-hypercube screen, then SciPy differential evolution on a penalised
  objective (infeasible candidates are ranked by how far their lower bound falls short), all
  with common random numbers, at Level 1 or Level 2.
* Verification: the cheapest feasible candidates are re-evaluated at Level 2 on fresh,
  independently seeded scenarios until one passes. Only that candidate is reported as chosen.

Code: `motionproof/challenge/engine.py`; CLI `motionproof challenge run`; API `/challenges`;
screen *Engineering Challenge* (7-step workflow: model and task, requirements, variables, cost,
reliability, review, results with Pareto view, candidate inspection and the original versus
optimised comparison).

## Analytic benchmark (benchmark M)

Single joint, backlash uniform with width scale `s`, requirement equivalent to `b <= b_lim`.
Failure fraction `F(s) = max(0, (0.01 + 0.01 s - b_lim) / (0.02 s))`. With `b_lim = 0.016` the
chosen scale lies in the analytic feasible band and passes verification; with `b_lim = 0.008`
the problem is reported infeasible.

## Reference challenge (two-link arm + NEMA 17 planetary gearbox)

`examples/advanced/challenge_reference.yaml`, SYNTHETIC design, example requirements, no cost
data. Three runs are kept as evidence:

1. `challenge_reference_first_attempt_infeasible.json`: requiring a 2 mm bidirectional tip
   error was infeasible for every stage-2 specification. That error is dominated by the payload,
   which no tolerance controls.
2. `challenge_reference_scale_only_infeasible.json`: requiring lost motion <= 6.5 mrad with
   scale variables and one shift was infeasible (best 95 % pass, 3 failures in 60, lower bound
   0.892 < 0.9). The limit is below the nominal 6.8 mrad backlash and scaling a tolerance does
   not move its centre.
3. `challenge_reference_unbounded_invalid.json`: with target shifts the search proposed a
   planet-clearance lower limit of -0.00027 mm, a physically impossible specification. This was
   a defect; clearance and backlash limits are now floored at zero.
4. `challenge_reference_result.json` and `challenge_reference_comparison.json`: chosen C017,
   relative cost index 2.698 versus 3.000, verified on 150 fresh Level 2 scenarios at 94.7 %
   pass (Clopper-Pearson lower bound 0.915 against the 0.90 target) versus 88.0 % (0.839) for
   the original. It widens the sun-planet backlash tolerance, tightens the planet-ring one and
   lowers all three design targets.

The finding from 1 and 2 is the useful engineering result: tightening tolerances cannot meet a
requirement that sits below the nominal design; the design targets must move.

## Publication status

| Part | Status |
|---|---|
| Method (search, exact binomial bound, Level 2 verification, physical-validity check) | verified on analytic cases (benchmark M, tests/integration/test_challenge.py) |
| Yield cost model | verified against its closed form `1 / (2 Phi(0.01 s / 0.004) - 1)` and the analytic feasible band (benchmark M) |
| Reference run on the synthetic design | done (above); relative cost index, so no cost claim |
| Defensible run on real hardware | **waiting for data**: `examples/forearm_elbow/challenge_yield_TEMPLATE.yaml` refuses to run until the measured process mean and spread (from printed parts) and the unit and inspection costs are filled in |

On the analytic yield case the optimum is a tighter specification than the original: it costs
more per accepted part (more scrap) but is the cheapest one that meets the reliability target.
That is the expected outcome when the process spread, not the specification, limits quality.
