"""Error metrics for time-aligned predictions and observations.

Residual convention: r = observed - predicted (same physical quantity, same unit, same
instants). All functions refuse arrays of different length.
"""

from __future__ import annotations

from typing import Any

import numpy as np
from scipy import stats


def errors(observed: np.ndarray, predicted: np.ndarray) -> dict[str, Any]:
    obs, pred = np.asarray(observed, float), np.asarray(predicted, float)
    if obs.shape != pred.shape or obs.ndim != 1:
        raise ValueError(f"observed {obs.shape} and predicted {pred.shape} must be equal 1-D")
    r = obs - pred
    sd = float(np.std(obs))
    rmse = float(np.sqrt(np.mean(r ** 2)))
    out: dict[str, Any] = {
        "n": int(len(r)), "rmse": rmse, "mae": float(np.mean(np.abs(r))),
        "max_abs": float(np.max(np.abs(r))), "mean_error": float(np.mean(r)),
        "bias_normalised": float(np.mean(r) / sd) if sd > 0 else None,
        "nrmse": rmse / sd if sd > 0 else None,
        "r2": float(1 - np.sum(r ** 2) / np.sum((obs - obs.mean()) ** 2)) if sd > 0 else None,
        "residual_percentiles": {str(p): float(np.percentile(r, p))
                                 for p in (1, 5, 25, 50, 75, 95, 99)},
        "observed_std": sd,
    }
    if sd > 0 and np.ptp(pred) > 1e-12 * max(1.0, float(np.max(np.abs(pred)))):
        out["pearson_r"] = float(stats.pearsonr(obs, pred)[0])
    return out


def by_group(observed: np.ndarray, predicted: np.ndarray, labels: list[Any]
             ) -> dict[str, dict[str, Any]]:
    lab = np.asarray([str(x) for x in labels])
    return {g: {k: v for k, v in errors(observed[lab == g], predicted[lab == g]).items()
                if k in ("n", "rmse", "mae", "max_abs", "mean_error")}
            for g in sorted(set(lab))}


def residual_histogram(observed: np.ndarray, predicted: np.ndarray, bins: int = 40
                       ) -> dict[str, list[float]]:
    r = np.asarray(observed) - np.asarray(predicted)
    counts, edges = np.histogram(r, bins=bins)
    return {"counts": counts.astype(float).tolist(), "edges": edges.tolist()}


def thin(*arrays: np.ndarray, max_points: int = 2000) -> list[list[float]]:
    """Evenly thinned copies for plotting (metrics always use the full series)."""
    n = len(arrays[0])
    idx = np.linspace(0, n - 1, min(n, max_points)).astype(int)
    return [np.asarray(a)[idx].tolist() for a in arrays]
