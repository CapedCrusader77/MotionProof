# Adaptive experiments

`motionproof/adaptive/sampler.py`. Active-learning reliability (AK-MCS, Echard et al. 2011).

1. Space-filling initial design of true simulations.
2. Limit state `g` = minimum normalised constraint margin (assembly violations count as
   failures); `g < 0` fails.
3. A Gaussian process (squared-exponential kernel; length scale and nugget by marginal
   likelihood) is fitted to the inputs most associated with `g` in the initial design
   (default up to 8); the others still vary and enter the nugget.
4. Over a population drawn from the real input distributions, the next true simulation is the
   point whose predicted sign is least certain (`U = |mean| / std` smallest).
5. Stop on budget, wall clock, cancellation, all points classified (`U >= 2`) or a stable
   estimate. Convergence stops require at least 10 adaptive simulations and a leave-one-out
   Q2 >= 0.5; a surrogate that does not predict the response cannot declare convergence.

Reported separately: true simulations and simulated failures (observations), and the surrogate's
predicted failure fraction (a prediction).

Measured (benchmark K, 10 seeds): for `P(fail) = 1.35e-3` the adaptive run stopped after 22
true evaluations on average (budget 60) with a median relative error of 0.14; random sampling
with the same number of evaluations saw no failure, so its estimate was 0 (relative error 1.0). On the
reference reversal experiment (28 inputs, response dominated by payload through gear-flank
switching) the surrogate never became predictive (Q2 about 0.2) and the run says so; adaptive
sampling gives no benefit there.
