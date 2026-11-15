"""Sensitivity analysis. Each function states its method; results are never relabelled.

* ``rank_correlation`` - Spearman rank correlation with Fisher-z intervals (association, not
  causation; monotonic effects only).
* ``regression_decomposition`` - standardised regression coefficients; ``src^2`` is a
  variance share only to the extent the linear model fits (``r_squared`` is reported).
* ``interaction_screen`` - pairwise product terms among the leading variables.
* ``one_at_a_time`` - nominal +- bound probes, each a real simulation.
* ``sobol`` - variance-based first/total-order indices (Saltelli design via SciPy). Requires
  independent inputs and ``N * (d + 2)`` simulations.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from typing import Any

import numpy as np
from scipy import stats

from motionproof.tolerances import distributions as D
from motionproof.tolerances.sampling import VariableSpace


def _active(x: np.ndarray) -> np.ndarray:
    return np.asarray(x.std(axis=0) > 1e-15)


def rank_correlation(names: list[str], x: np.ndarray, y: np.ndarray,
                     confidence: float = 0.95) -> list[dict[str, Any]]:
    n = len(y)
    if n < 8:
        raise ValueError("rank correlation needs at least 8 valid scenarios")
    z = float(stats.norm.ppf(0.5 + confidence / 2))
    out = []
    active = _active(x)
    for i, name in enumerate(names):
        if not active[i] or y.std() < 1e-15:
            out.append({"parameter": name, "rho": 0.0, "interval": [0.0, 0.0], "p_value": 1.0,
                        "direction": "none", "note": "no variation"})
            continue
        rho, p = stats.spearmanr(x[:, i], y)
        rho = float(np.clip(rho, -0.999999, 0.999999))
        se = 1.03 / math.sqrt(max(n - 3, 1))
        lo, hi = math.tanh(math.atanh(rho) - z * se), math.tanh(math.atanh(rho) + z * se)
        significant = lo > 0 or hi < 0
        out.append({"parameter": name, "rho": rho, "interval": [lo, hi], "p_value": float(p),
                    "direction": ("increases" if rho > 0 else "decreases") if significant
                    else "not distinguishable from zero"})
    return sorted(out, key=lambda r: -abs(r["rho"]))


def regression_decomposition(names: list[str], x: np.ndarray, y: np.ndarray) -> dict[str, Any]:
    active = _active(x)
    idx = np.flatnonzero(active)
    if len(y) <= len(idx) + 2 or y.std() < 1e-15:
        return {"r_squared": None, "coefficients": [],
                "note": "not enough scenarios (or no response variation) for a regression"}
    xs = (x[:, idx] - x[:, idx].mean(axis=0)) / x[:, idx].std(axis=0)
    ys = (y - y.mean()) / y.std()
    beta, *_ = np.linalg.lstsq(xs, ys, rcond=None)
    r2 = 1.0 - float(np.sum((ys - xs @ beta) ** 2) / np.sum(ys**2))
    coefs = [{"parameter": names[j], "src": float(b), "src_squared": float(b * b)}
             for j, b in zip(idx, beta, strict=True)]
    return {"r_squared": r2, "coefficients": sorted(coefs, key=lambda c: -c["src_squared"]),
            "note": "src^2 approximates a variance share only when r_squared is close to 1 and "
                    "inputs are uncorrelated"}


def interaction_screen(names: list[str], x: np.ndarray, y: np.ndarray,
                       top: int = 5) -> dict[str, Any]:
    """Regression with pairwise products of the ``top`` variables by |Spearman rho|."""
    ranked = [r["parameter"] for r in rank_correlation(names, x, y) if "note" not in r][:top]
    idx = [names.index(p) for p in ranked]
    n_terms = len(idx) + len(idx) * (len(idx) - 1) // 2
    if len(idx) < 2 or len(y) < 3 * n_terms:
        return {"pairs": [], "note": "not enough scenarios to screen interactions"}
    xs = (x[:, idx] - x[:, idx].mean(axis=0)) / x[:, idx].std(axis=0)
    ys = (y - y.mean()) / y.std()
    cols, labels = [xs[:, i] for i in range(len(idx))], []
    for i in range(len(idx)):
        for j in range(i + 1, len(idx)):
            cols.append(xs[:, i] * xs[:, j])
            labels.append((ranked[i], ranked[j]))
    a = np.column_stack(cols)
    beta, *_ = np.linalg.lstsq(a, ys, rcond=None)
    linear = np.column_stack(cols[: len(idx)])
    b_lin, *_ = np.linalg.lstsq(linear, ys, rcond=None)
    r2_lin = 1 - float(np.sum((ys - linear @ b_lin) ** 2) / np.sum(ys**2))
    r2_full = 1 - float(np.sum((ys - a @ beta) ** 2) / np.sum(ys**2))
    pairs = [{"parameters": list(lab), "coefficient": float(b)}
             for lab, b in zip(labels, beta[len(idx):], strict=True)]
    return {"variables": ranked, "r_squared_linear": r2_lin, "r_squared_with_pairs": r2_full,
            "pairs": sorted(pairs, key=lambda p: -abs(p["coefficient"])),
            "method": "least-squares screen on standardised variables and pairwise products"}


def one_at_a_time(space: VariableSpace, evaluate: Callable[[dict[str, float]], float]
                  ) -> list[dict[str, Any]]:
    """Move each variable alone to its lower and upper bound; 2d + 1 evaluations."""
    nominal = space.nominal()
    base = evaluate(dict(zip(space.names, nominal, strict=True)))
    out = []
    for i, (name, (lo, hi)) in enumerate(zip(space.names, space.bounds(), strict=True)):
        vals = []
        for edge in (lo, hi):
            row = nominal.copy()
            row[i] = edge
            vals.append(evaluate(dict(zip(space.names, row, strict=True))))
        out.append({"parameter": name, "low": float(lo), "high": float(hi),
                    "response_low": vals[0], "response_high": vals[1], "response_nominal": base,
                    "swing": float(vals[1] - vals[0]),
                    "max_change": float(max(abs(vals[0] - base), abs(vals[1] - base))),
                    "direction": "increases" if vals[1] > vals[0] else "decreases"
                    if vals[1] < vals[0] else "none"})
    return sorted(out, key=lambda r: -r["max_change"])


def sobol(space: VariableSpace, evaluate: Callable[[dict[str, float]], float], n: int = 64,
          seed: int = 0, variables: list[str] | None = None) -> dict[str, Any]:
    """First- and total-order Sobol indices with bootstrap intervals.

    ``n`` must be a power of two. Variables not listed stay at their design value.
    """
    if space.correlation is not None:
        raise ValueError("Sobol indices assume independent inputs; this model defines "
                         "correlations - remove them or use the regression methods")
    if n < 8 or n & (n - 1):
        raise ValueError("n must be a power of two >= 8")
    chosen = variables or space.names
    idx = [space.names.index(v) for v in chosen]
    nominal = space.nominal()

    class _U:
        """Uniform(0,1) marginal; the physical distribution is applied through its ppf."""

        def ppf(self, q: np.ndarray) -> np.ndarray:
            return q

    def func(u: np.ndarray) -> np.ndarray:
        out = np.empty(u.shape[1])
        for k in range(u.shape[1]):
            row = nominal.copy()
            for j, i in enumerate(idx):
                row[i] = float(D.ppf(space.variables[i].distribution, u[j, k]))
            out[k] = evaluate(dict(zip(space.names, row, strict=True)))
        return out

    res = stats.sobol_indices(func=func, n=n, dists=[stats.uniform()] * len(idx),
                              rng=np.random.default_rng(seed))
    boot = res.bootstrap(confidence_level=0.95, n_resamples=199)
    rows = []
    for j, name in enumerate(chosen):
        rows.append({
            "parameter": name,
            "first_order": float(res.first_order[j]),
            "first_order_interval": [float(boot.first_order.confidence_interval.low[j]),
                                     float(boot.first_order.confidence_interval.high[j])],
            "total_order": float(res.total_order[j]),
            "total_order_interval": [float(boot.total_order.confidence_interval.low[j]),
                                     float(boot.total_order.confidence_interval.high[j])],
            "interaction_share": float(res.total_order[j] - res.first_order[j]),
        })
    return {"method": "Sobol indices (Saltelli design, SciPy), bootstrap 95% intervals",
            "base_samples": n, "evaluations": n * (len(idx) + 2), "seed": seed,
            "indices": sorted(rows, key=lambda r: -r["total_order"])}


def analyse(names: list[str], x: np.ndarray, metrics: dict[str, np.ndarray],
            metric: str) -> dict[str, Any]:
    """Sample-based sensitivity of one metric from experiment results."""
    if metric not in metrics:
        raise KeyError(f"metric {metric!r} not available; choose from {sorted(metrics)}")
    y = metrics[metric]
    return {
        "metric": metric, "scenarios": int(len(y)),
        "rank_correlation": {"method": "Spearman rank correlation, Fisher-z 95% interval",
                             "caveat": "association in this sample; not proof of causation",
                             "rows": rank_correlation(names, x, y)},
        "regression": {"method": "standardised regression coefficients",
                       **regression_decomposition(names, x, y)},
        "interactions": interaction_screen(names, x, y),
    }
