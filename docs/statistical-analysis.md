# Statistical analysis

Per constraint and for all constraints together: counts, pass fraction, interval, minimum and
mean normalised margin. Per metric: mean, standard deviation, 5 %, 50 %, 95 % quantiles, range.
Failure categories are counted per scenario.

* **Independent Monte Carlo:** Wilson score interval. With zero failures the result says so
  explicitly: the data bound the failure probability, they do not show it is zero.
* **Latin hypercube / Sobol:** rows are not independent, so no binomial interval is given for a
  single design. With randomised replicates a Student-t interval over the replicate estimates
  is reported.
* **Boundary / corners:** counts only; no probability estimate.

Invalid simulations are excluded from pass fractions and reported separately.

Every estimate is conditional on the distributions, the model fidelity, the task and the sample
size, and is a model prediction unless a calibration report based on real measurements is
attached. MotionProof never reports a certified reliability.
