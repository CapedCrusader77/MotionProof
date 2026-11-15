"""Probability distributions, all driven through their quantile function (``ppf``).

Sampling through the inverse CDF lets one stream of uniforms serve Monte Carlo, Latin
hypercube, Sobol sequences and Gaussian-copula correlation alike.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import ArrayLike, NDArray
from scipy import stats

from motionproof.core.schema import (
    Discrete,
    Distribution,
    Empirical,
    LogNormal,
    Normal,
    TruncatedNormal,
    Uniform,
)

Arr = NDArray[np.float64]
COVERAGE_TAIL = 0.00135  # +-3 sigma equivalent, used to bound unbounded distributions


def validate(dist: Distribution) -> list[str]:
    """Return human-readable problems with a distribution definition."""
    problems: list[str] = []
    if isinstance(dist, Uniform | TruncatedNormal) and dist.high <= dist.low:
        problems.append("upper bound must exceed lower bound")
    if isinstance(dist, Discrete):
        p = dist.probabilities
        if p is not None:
            if len(p) != len(dist.values):
                problems.append("probabilities and values differ in length")
            elif min(p) < 0 or abs(sum(p) - 1.0) > 1e-9:
                problems.append("probabilities must be non-negative and sum to 1")
    if isinstance(dist, TruncatedNormal):
        a, b = (dist.low - dist.mean) / dist.std, (dist.high - dist.mean) / dist.std
        if stats.norm.cdf(b) - stats.norm.cdf(a) < 1e-12:
            problems.append("truncation interval carries no probability mass")
    return problems


def ppf(dist: Distribution, u: ArrayLike) -> Arr:
    """Quantile function evaluated at ``u`` in (0, 1)."""
    q = np.clip(np.asarray(u, dtype=float), 1e-12, 1 - 1e-12)
    if isinstance(dist, Uniform):
        return np.asarray(dist.low + q * (dist.high - dist.low), dtype=float)
    if isinstance(dist, Normal):
        return np.asarray(stats.norm.ppf(q, dist.mean, dist.std))
    if isinstance(dist, TruncatedNormal):
        a, b = (dist.low - dist.mean) / dist.std, (dist.high - dist.mean) / dist.std
        return np.asarray(stats.truncnorm.ppf(q, a, b, dist.mean, dist.std))
    if isinstance(dist, LogNormal):
        return np.asarray(np.exp(stats.norm.ppf(q, dist.mu, dist.sigma)))
    if isinstance(dist, Discrete):
        vals = np.asarray(dist.values, dtype=float)
        p = np.full(len(vals), 1 / len(vals)) if dist.probabilities is None else np.asarray(
            dist.probabilities, dtype=float)
        order = np.argsort(vals)
        cum = np.cumsum(p[order])
        idx = np.minimum(np.searchsorted(cum, q, side="left"), len(vals) - 1)
        return np.asarray(vals[order][idx], dtype=float)
    if isinstance(dist, Empirical):
        return np.asarray(np.quantile(np.asarray(dist.samples, dtype=float), q))
    raise TypeError(f"unsupported distribution {type(dist).__name__}")


def bounds(dist: Distribution) -> tuple[float, float]:
    """Finite search bounds: exact support where bounded, else the +-3 sigma quantiles."""
    if isinstance(dist, Uniform | TruncatedNormal):
        return dist.low, dist.high
    if isinstance(dist, Discrete):
        return min(dist.values), max(dist.values)
    if isinstance(dist, Empirical):
        return min(dist.samples), max(dist.samples)
    lo, hi = ppf(dist, [COVERAGE_TAIL, 1 - COVERAGE_TAIL])
    return float(lo), float(hi)


def mean_std(dist: Distribution) -> tuple[float, float]:
    if isinstance(dist, Uniform):
        return (dist.low + dist.high) / 2, (dist.high - dist.low) / np.sqrt(12.0)
    if isinstance(dist, Normal):
        return dist.mean, dist.std
    if isinstance(dist, TruncatedNormal):
        a, b = (dist.low - dist.mean) / dist.std, (dist.high - dist.mean) / dist.std
        m, v = stats.truncnorm.stats(a, b, dist.mean, dist.std, moments="mv")
        return float(m), float(np.sqrt(v))
    if isinstance(dist, LogNormal):
        m = np.exp(dist.mu + dist.sigma**2 / 2)
        return float(m), float(m * np.sqrt(np.exp(dist.sigma**2) - 1))
    x = ppf(dist, (np.arange(20000) + 0.5) / 20000)
    return float(x.mean()), float(x.std())


def cdf(dist: Distribution, x: float) -> float:
    """Cumulative probability P(X <= x)."""
    if isinstance(dist, Uniform):
        return float(np.clip((x - dist.low) / (dist.high - dist.low), 0.0, 1.0))
    if isinstance(dist, Normal):
        return float(stats.norm.cdf(x, dist.mean, dist.std))
    if isinstance(dist, TruncatedNormal):
        a, b = (dist.low - dist.mean) / dist.std, (dist.high - dist.mean) / dist.std
        return float(stats.truncnorm.cdf(x, a, b, dist.mean, dist.std))
    if isinstance(dist, LogNormal):
        return float(stats.norm.cdf(np.log(x), dist.mu, dist.sigma)) if x > 0 else 0.0
    if isinstance(dist, Discrete):
        p = dist.probabilities or [1 / len(dist.values)] * len(dist.values)
        return float(sum(pi for v, pi in zip(dist.values, p, strict=True) if v <= x))
    samples = np.asarray(dist.samples, dtype=float)
    return float(np.mean(samples <= x))


def fraction_outside(dist: Distribution, low: float, high: float) -> float:
    """Probability mass outside [low, high]."""
    eps = 1e-12 * max(1.0, abs(low), abs(high))
    below = cdf(dist, low - eps) if not isinstance(dist, Discrete | Empirical) else (
        cdf(dist, np.nextafter(low - eps, -np.inf)))
    return float(np.clip(below + 1.0 - cdf(dist, high + eps), 0.0, 1.0))


def density_curve(dist: Distribution, points: int = 80) -> dict[str, list[float]]:
    """Density for plotting (probability mass per value for discrete distributions)."""
    if isinstance(dist, Discrete):
        vals = sorted(set(dist.values))
        p = dist.probabilities or [1 / len(dist.values)] * len(dist.values)
        mass = [sum(pi for v, pi in zip(dist.values, p, strict=True) if v == x) for x in vals]
        return {"x": vals, "density": mass}
    lo, hi = bounds(dist)
    pad = 0.05 * (hi - lo or 1.0)
    edges = np.linspace(lo - pad, hi + pad, points + 1)
    prob = np.diff([cdf(dist, float(e)) for e in edges])
    width = edges[1] - edges[0]
    return {"x": ((edges[:-1] + edges[1:]) / 2).tolist(), "density": (prob / width).tolist()}
