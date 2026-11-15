"""Robustness statistics with estimation methods matched to the sampling design.

* Independent Monte Carlo draws: Wilson score interval for each pass proportion.
* Latin hypercube / Sobol designs: rows are not independent, so no binomial interval is
  reported for a single design. With ``replicates >= 2`` (independently randomised repeats)
  a Student-t interval over the replicate estimates is given instead.
* Boundary / corner designs are deterministic probes, not samples of the population: counts
  only, no probability estimate.

All estimates are conditional on the supplied distributions, the model fidelity and the task.
They are not a certified reliability.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
from scipy import stats


def wilson_interval(successes: int, n: int, confidence: float = 0.95) -> tuple[float, float]:
    """Wilson score interval for a binomial proportion."""
    if n <= 0:
        return 0.0, 1.0
    z = float(stats.norm.ppf(0.5 + confidence / 2))
    p = successes / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    lo = 0.0 if successes == 0 else max(0.0, centre - half)
    hi = 1.0 if successes == n else min(1.0, centre + half)
    return lo, hi


def replicate_interval(estimates: list[float], confidence: float = 0.95) -> tuple[float, float]:
    """Student-t interval over independent replicate estimates."""
    r = len(estimates)
    if r < 2:
        raise ValueError("at least two replicates are needed")
    mean = float(np.mean(estimates))
    half = float(stats.t.ppf(0.5 + confidence / 2, r - 1)) * float(np.std(estimates, ddof=1)
                                                                  ) / math.sqrt(r)
    return max(0.0, mean - half), min(1.0, mean + half)


def _proportion(flags: list[bool], replicates: list[int], method: str, independent: bool,
                confidence: float) -> dict[str, Any]:
    n = len(flags)
    k = int(sum(flags))
    out: dict[str, Any] = {"n": n, "passed": k, "failed": n - k,
                           "pass_fraction": k / n if n else None}
    if method in ("boundary", "corners"):
        out |= {"interval": None, "interval_method": "none",
                "note": "deterministic probe design: counts are not probability estimates"}
        out["pass_fraction"] = None
        return out
    if independent:
        lo, hi = wilson_interval(k, n, confidence)
        out |= {"interval": [lo, hi], "interval_method": f"Wilson score, {confidence:.0%}"}
        if k == n and n:
            out["note"] = (f"no failures in {n} scenarios does not mean zero failure "
                           f"probability: the data only bound it below {1 - lo:.2%}")
        return out
    reps = sorted(set(replicates))
    if len(reps) >= 2:
        per = [float(np.mean([f for f, r in zip(flags, replicates, strict=True) if r == rep]))
               for rep in reps]
        lo, hi = replicate_interval(per, confidence)
        out |= {"interval": [lo, hi], "replicate_estimates": per,
                "interval_method": f"Student-t over {len(reps)} randomised replicates, "
                                   f"{confidence:.0%}"}
    else:
        out |= {"interval": None, "interval_method": "none",
                "note": f"{method} rows are not independent draws; run >= 2 randomised "
                        "replicates to obtain a confidence interval"}
    return out


def summarise(manifest: dict[str, Any], results: list[dict[str, Any]],
              confidence: float = 0.95) -> dict[str, Any]:
    """Experiment-level robustness summary from stored scenario results."""
    method = manifest["config"]["sampling"]["method"]
    independent = bool(manifest["design"]["independent"])
    valid = [r for r in results if r["valid"]]
    reps = [r["replicate"] for r in valid]
    constraints: dict[str, Any] = {}
    for c in manifest["config"]["constraints"]:
        name = c["name"]
        flags = [bool(r["constraints"][name]["passed"]) for r in valid]
        margins = np.array([r["constraints"][name]["margin"] for r in valid])
        entry = _proportion(flags, reps, method, independent, confidence)
        entry |= {"metric": c["metric"], "op": c["op"], "limit": c["limit"],
                  "min_margin": float(margins.min()) if len(margins) else None,
                  "mean_margin": float(margins.mean()) if len(margins) else None}
        constraints[name] = entry
    overall = _proportion([bool(r["passed"]) for r in valid], reps, method, independent,
                          confidence)
    categories: dict[str, int] = {}
    for r in results:
        for cat in {f["category"] for f in r["failures"]}:
            categories[cat] = categories.get(cat, 0) + 1
    metrics: dict[str, Any] = {}
    if valid:
        for key in sorted(set.intersection(*(set(r["metrics"]) for r in valid))):
            v = np.array([r["metrics"][key] for r in valid])
            metrics[key] = {"mean": float(v.mean()), "std": float(v.std(ddof=1)) if len(v) > 1
                            else 0.0, "min": float(v.min()), "p05": float(np.quantile(v, 0.05)),
                            "p50": float(np.quantile(v, 0.5)), "p95": float(np.quantile(v, 0.95)),
                            "max": float(v.max())}
    return {
        "scenarios": {"total": len(manifest["design"]["values"]), "completed": len(results),
                      "valid": len(valid), "invalid": len(results) - len(valid),
                      "passed": int(sum(r["passed"] for r in results)),
                      "failed": int(sum(r["valid"] and not r["passed"] for r in results)),
                      "out_of_spec": int(sum(bool(r["out_of_spec"]) for r in results))},
        "all_constraints": overall,
        "constraints": constraints,
        "failure_categories": categories,
        "metrics": metrics,
        "method": {"sampling": method, "independent_draws": independent,
                   "replicates": manifest["config"]["sampling"]["replicates"],
                   "notes": manifest["design"]["notes"]},
        "conditions": [
            f"model fidelity: {manifest['model']['fidelity']}",
            "manufacturing and operating distributions as recorded in the manifest",
            "model-predicted outcomes; no physical validation unless a calibration report "
            "is attached",
        ],
    }


def histogram(values: list[float], bins: int = 30) -> dict[str, list[float]]:
    v = np.asarray(values, dtype=float)
    if len(v) == 0:
        return {"x": [], "count": []}
    counts, edges = np.histogram(v, bins=bins)
    return {"x": ((edges[:-1] + edges[1:]) / 2).tolist(), "count": counts.tolist(),
            "width": float(edges[1] - edges[0])}
