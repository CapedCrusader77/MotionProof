"""Adaptive experiment generation: spend true simulations near the pass/fail boundary.

Method: active-learning reliability with a Gaussian-process surrogate (the AK-MCS scheme of
Echard, Gayton and Lemaire, Structural Safety 2011). A population is drawn from the real input
distributions; the surrogate predicts the limit state ``g`` (positive = pass) with an
uncertainty; the next *true* simulation is the population point whose sign is least certain,
``U = |mean| / std`` smallest.

The surrogate only chooses where to simulate. Every count of failures is split into
``simulated`` (true evaluations) and ``predicted`` (surrogate), and the reported failure
fraction is labelled a surrogate-based estimate.

The Gaussian process is a small NumPy implementation (squared-exponential kernel, one length
scale per run chosen by marginal likelihood) because no machine-learning library is installed;
it is tested against known functions.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

import numpy as np
from numpy.typing import NDArray
from scipy.linalg import cho_factor, cho_solve
from scipy.stats import qmc

Arr = NDArray[np.float64]
LENGTH_SCALES = (0.1, 0.2, 0.35, 0.6, 1.0, 1.7, 3.0)


NUGGETS = (1e-8, 1e-4, 1e-2, 0.05, 0.2)
MIN_Q2 = 0.5


class GaussianProcess:
    """Zero-mean GP on standardised data, squared-exponential kernel.

    Length scale and nugget are chosen together by marginal likelihood. The nugget absorbs
    variation from inputs left out of the surrogate and solver noise; predictions are of the
    latent function (the nugget is not added to the predictive variance).
    """

    def _k(self, a: Arr, b: Arr, length: float) -> Arr:
        d2 = (np.sum(a * a, axis=1)[:, None] + np.sum(b * b, axis=1)[None, :]
              - 2.0 * a @ b.T)
        return np.exp(-0.5 * np.clip(d2, 0.0, None) / (length * length))

    def fit(self, x: Arr, y: Arr) -> GaussianProcess:
        self.x_mean, self.x_std = x.mean(axis=0), x.std(axis=0)
        self.x_std[self.x_std < 1e-15] = 1.0
        self.y_mean, self.y_std = float(y.mean()), float(y.std()) or 1.0
        self.x = (x - self.x_mean) / self.x_std
        ys = (y - self.y_mean) / self.y_std
        n, d = self.x.shape
        best = None
        for scale in LENGTH_SCALES:
            length = scale * np.sqrt(d)
            base = self._k(self.x, self.x, length)
            for nugget in NUGGETS:
                try:
                    c = cho_factor(base + nugget * np.eye(n), lower=True)
                except np.linalg.LinAlgError:
                    continue
                alpha = cho_solve(c, ys)
                logml = -0.5 * float(ys @ alpha) - float(np.log(np.diag(c[0])).sum())
                if best is None or logml > best[0]:
                    best = (logml, length, nugget, c, alpha)
        if best is None:
            raise ValueError("Gaussian-process fit failed (singular kernel matrix)")
        _, self.length, self.nugget, self.chol, self.alpha = best
        return self

    def predict(self, x: Arr) -> tuple[Arr, Arr]:
        xs = (x - self.x_mean) / self.x_std
        ks = self._k(xs, self.x, self.length)
        mean = ks @ self.alpha
        v = cho_solve(self.chol, ks.T)
        var = np.clip(1.0 - np.einsum("ij,ji->i", ks, v), 1e-12, None)
        return mean * self.y_std + self.y_mean, np.sqrt(var) * self.y_std

    def leave_one_out_q2(self, y: Arr) -> float:
        """Predictive coefficient of determination from closed-form leave-one-out residuals."""
        kinv = cho_solve(self.chol, np.eye(len(self.x)))
        ys = (y - self.y_mean) / self.y_std
        res = (kinv @ ys) / np.diag(kinv)
        return float(1.0 - np.sum(res**2) / np.sum((ys - ys.mean()) ** 2))


def screen_inputs(x: Arr, y: Arr, keep: int) -> list[int]:
    """Indices of the ``keep`` inputs most associated with the response (|Spearman rho|)."""
    from scipy.stats import spearmanr

    scores = []
    for i in range(x.shape[1]):
        if np.ptp(x[:, i]) == 0 or np.ptp(y) == 0:
            scores.append(0.0)
            continue
        rho = spearmanr(x[:, i], y)[0]
        scores.append(0.0 if not np.isfinite(rho) else abs(float(rho)))
    order = np.argsort(scores)[::-1]
    return sorted(int(i) for i in order[:keep] if np.ptp(x[:, i]) > 0)


def run_adaptive(
    limit_state: Callable[[Arr], float],
    sample_population: Callable[[int, int], Arr],
    bounds: Arr,
    initial: int = 30,
    budget: int = 150,
    population: int = 5000,
    seed: int = 0,
    u_target: float = 2.0,
    stability_window: int = 10,
    stability_tolerance: float = 0.02,
    min_adaptive: int = 10,
    active: int | None = None,
    max_seconds: float | None = None,
    progress: Callable[[dict[str, Any]], None] | None = None,
    should_stop: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    """Run the adaptive loop. ``limit_state(x) >= 0`` means the scenario passes.

    ``sample_population(n, seed)`` draws from the real input distributions (physical values);
    ``bounds`` (d, 2) are used for the space-filling initial design.
    Convergence stops are only accepted after ``min_adaptive`` adaptive simulations: a
    surrogate trained on a few initial points that happened to see no failure is
    over-confident. They also require a leave-one-out Q2 of at least 0.5: a surrogate that
    does not predict the response cannot declare convergence.

    In many dimensions the surrogate uses only the ``active`` inputs most associated with the
    response in the initial design (default ``min(d, 8)``); the others still vary in every
    simulation and their effect enters the fitted nugget.
    """
    if initial < 4 or budget < initial:
        raise ValueError("need initial >= 4 and budget >= initial")
    started = time.perf_counter()
    pool = sample_population(population, seed + 1)
    d = pool.shape[1]
    unit = qmc.LatinHypercube(d=d, seed=seed).random(initial)
    x = bounds[:, 0] + unit * (bounds[:, 1] - bounds[:, 0])
    y = np.array([limit_state(row) for row in x])
    keep = min(d, 8) if active is None else max(1, min(active, d))
    cols = screen_inputs(x, y, keep) if keep < d else \
        [i for i in range(d) if bounds[i, 1] > bounds[i, 0]]
    if not cols:
        cols = [i for i in range(d) if bounds[i, 1] > bounds[i, 0]] or [0]
    kind = ["initial"] * initial
    history: list[dict[str, Any]] = []
    estimates: list[float] = []
    reason = "simulation budget reached"
    gp = GaussianProcess()
    mean = std = np.zeros(len(pool))
    while True:
        gp.fit(x[:, cols], y)
        mean, std = gp.predict(pool[:, cols])
        q2 = gp.leave_one_out_q2(y)
        u = np.abs(mean) / std
        pf = float(np.mean(mean < 0))
        estimates.append(pf)
        uncertain = int(np.sum(u < u_target))
        history.append({"simulations": len(y), "predicted_failure_fraction": pf,
                        "uncertain_population_points": uncertain, "min_u": float(u.min()),
                        "leave_one_out_q2": q2,
                        "simulated_failures": int(np.sum(y < 0))})
        if progress is not None:
            progress({"done": len(y), "total": budget, **history[-1]})
        if should_stop is not None and should_stop():
            reason = "cancelled"
            break
        settled = len(y) - initial >= min_adaptive and q2 >= MIN_Q2
        if uncertain == 0 and settled:
            reason = (f"every population point is classified with U >= {u_target:g} "
                      "(surrogate sign uncertainty below about 2.3 %)")
            break
        if settled and len(estimates) > stability_window:
            recent = estimates[-stability_window:]
            spread = max(recent) - min(recent)
            if spread <= stability_tolerance * max(max(recent), 1.0 / population):
                reason = (f"failure-fraction estimate stable within "
                          f"{stability_tolerance:.0%} over {stability_window} iterations")
                break
        if len(y) >= budget:
            if q2 < MIN_Q2:
                reason = (f"simulation budget reached; the surrogate never became predictive "
                          f"(Q2 {q2:.2f} < {MIN_Q2})")
            break
        if max_seconds is not None and time.perf_counter() - started > max_seconds:
            reason = "wall-clock budget reached"
            break
        pick = int(np.argmin(u))
        x = np.vstack([x, pool[pick]])
        y = np.append(y, limit_state(pool[pick]))
        kind.append("adaptive")
        pool = np.delete(pool, pick, axis=0)
    warnings = []
    if q2 < 0.5:
        warnings.append(f"surrogate leave-one-out Q2 = {q2:.2f}: the surrogate predicts the "
                        "response poorly; its failure estimate should not be relied on")
    if len(cols) < d:
        warnings.append(f"the surrogate uses {len(cols)} of {d} inputs, chosen by rank "
                        "correlation in the initial design; effects of the others are "
                        "treated as noise")
    return {
        "method": "Gaussian-process active learning (AK-MCS), U-function selection",
        "seed": seed, "dimensions": d, "surrogate_inputs": cols,
        "simulations": {"total": int(len(y)), "initial": initial,
                        "adaptive": int(len(y) - initial),
                        "failures_simulated": int(np.sum(y < 0))},
        "surrogate": {"kind": "prediction, not simulation", "population": int(len(pool)),
                      "predicted_failure_fraction": float(np.mean(mean < 0)),
                      "predicted_failures": int(np.sum(mean < 0)),
                      "uncertain_points": int(np.sum(np.abs(mean) / std < u_target)),
                      "length_scale": float(gp.length), "nugget": float(gp.nugget),
                      "leave_one_out_q2": q2},
        "stopping_reason": reason,
        "elapsed_seconds": time.perf_counter() - started,
        "history": history,
        "points": {"x": x.tolist(), "limit_state": y.tolist(), "kind": kind},
        "warnings": warnings,
        "statement": "Simulated failures are confirmed by the simulation engine. The failure "
                     "fraction is a surrogate-based estimate over the sampled population.",
    }
