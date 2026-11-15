"""Tolerance allocation: trade manufacturing cost against simulated performance.

Each candidate scales the spread of selected tolerances (``scale < 1`` tightens). Every
candidate is evaluated with the real experiment pipeline using common random numbers, the
non-dominated set is extracted, and the recommended candidate is re-verified with a larger,
independently seeded Monte Carlo run before it is reported as meeting the requirement.

The candidate set is a seeded Latin-hypercube screen followed by non-dominated filtering.
It is a Pareto *screen*, not a converged evolutionary optimisation.

Cost
----
``cost_i = fixed_i + coefficient_i / (scale_i ** exponent_i)`` per tolerance (the reciprocal
power form common in tolerance-cost literature). Coefficients are user data. Without them a
unit coefficient is used and the result is labelled a *relative cost index*, not a price.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any, Literal

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, model_validator
from scipy.stats import qmc

from motionproof.core.schema import (
    MechanicalModelSpec,
    Normal,
    TruncatedNormal,
    Uniform,
)
from motionproof.experiments.runner import (
    Constraint,
    ExperimentConfig,
    Sampling,
    evaluate_scenario,
)
from motionproof.model import MechanicalModel
from motionproof.statistics.robustness import wilson_interval
from motionproof.tolerances.sampling import VariableSpace


class ProcessSpread(BaseModel):
    """Spread of the process that makes a feature, ideally from measured parts."""

    model_config = ConfigDict(extra="forbid")
    mean: float
    std: float = Field(gt=0)
    basis: Literal["measured", "specified", "assumed"]
    source: str


class CostTerm(BaseModel):
    """Cost of one toleranced feature.

    * ``reciprocal``: ``fixed + coefficient / scale**exponent`` (a relative index unless the
      coefficients come from cost data).
    * ``yield``: parts are made by a process with the given spread and 100 % inspected; parts
      outside the specification are scrapped. Cost per accepted part =
      ``(unit_cost + inspection_cost) / yield`` with ``yield = P(L <= x <= U)`` for the process
      normal distribution. Accepted parts follow that normal truncated to [L, U].
    """

    model_config = ConfigDict(extra="forbid")
    model: Literal["reciprocal", "yield"] = "reciprocal"
    fixed: float = Field(default=0.0, ge=0)
    coefficient: float = Field(default=1.0, gt=0)
    exponent: float = Field(default=1.0, gt=0)
    unit_cost: float | None = Field(default=None, gt=0)
    inspection_cost: float = Field(default=0.0, ge=0)
    process: ProcessSpread | None = None
    currency: str | None = None

    @model_validator(mode="after")
    def _yield(self) -> CostTerm:
        if self.model == "yield" and (self.unit_cost is None or self.process is None):
            raise ValueError("a yield cost term needs unit_cost and process (mean, std, basis)")
        return self


class AllocationConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tolerances: list[str] = Field(min_length=1)
    scale_range: tuple[float, float] = (0.4, 1.5)
    candidates: int = Field(default=16, ge=2, le=200)
    samples: int = Field(default=60, ge=10, le=5000)
    verify_samples: int = Field(default=200, ge=20, le=20000)
    seed: int = 0
    objective_metric: str
    objective_quantile: float = Field(default=0.95, gt=0, lt=1)
    costs: dict[str, CostTerm] = Field(default_factory=dict)
    target_pass_fraction: float = Field(default=0.95, gt=0, le=1)


def scalable(spec: MechanicalModelSpec, tol_id: str) -> bool:
    return isinstance(spec.tolerance(tol_id).distribution, Normal | TruncatedNormal | Uniform)


def scaled_spec(spec: MechanicalModelSpec, scales: dict[str, float]) -> MechanicalModelSpec:
    """Copy of ``spec`` with tolerance widths (limits and spread) scaled about their centre."""
    data = spec.model_dump(mode="json", by_alias=True)
    for t in data["tolerances"]:
        k = scales.get(t["id"])
        if k is None:
            continue
        d = t["distribution"]
        mid = (t["lower"] + t["upper"]) / 2
        half = (t["upper"] - t["lower"]) / 2 * k
        t["lower"], t["upper"] = mid - half, mid + half
        if d["type"] == "uniform":
            c, h = (d["low"] + d["high"]) / 2, (d["high"] - d["low"]) / 2 * k
            d["low"], d["high"] = c - h, c + h
        elif d["type"] == "normal":
            d["std"] *= k
        elif d["type"] == "truncated_normal":
            d["std"] *= k
            d["low"] = d["mean"] - (d["mean"] - d["low"]) * k
            d["high"] = d["mean"] + (d["high"] - d["mean"]) * k
        else:
            raise ValueError(f"tolerance {t['id']!r}: {d['type']} distributions cannot be scaled")
    return MechanicalModelSpec.model_validate(data)


def cost(config: AllocationConfig, scales: dict[str, float]) -> float:
    total = 0.0
    for tol_id in config.tolerances:
        term = config.costs.get(tol_id, CostTerm())
        total += term.fixed + term.coefficient / scales[tol_id] ** term.exponent
    return total


def _evaluate(model: MechanicalModel, experiment: ExperimentConfig, scales: dict[str, float],
              metric: str, quantile: float, samples: int, seed: int,
              cancel: threading.Event | None) -> dict[str, Any] | None:
    variant_model = MechanicalModel(scaled_spec(model.spec, scales), model.directory)
    space = VariableSpace.from_model(variant_model.spec, experiment.operating)
    design = space.design("monte_carlo", samples, seed)
    values, passed, per_constraint = [], 0, {c.name: 0 for c in experiment.constraints}
    for row in design.values:
        if cancel is not None and cancel.is_set():
            return None
        res = evaluate_scenario(variant_model, experiment,
                                dict(zip(space.names, row.tolist(), strict=True)))
        if not res["valid"]:
            continue
        values.append(res["metrics"][metric])
        passed += res["passed"]
        for name, chk in res["constraints"].items():
            per_constraint[name] += chk["passed"]
    n = len(values)
    if n == 0:
        return {"valid": 0}
    lo, hi = wilson_interval(passed, n)
    return {"valid": n, "objective": float(np.quantile(values, quantile)),
            "mean": float(np.mean(values)), "pass_fraction": passed / n,
            "pass_interval": [lo, hi],
            "constraint_pass_fraction": {k: v / n for k, v in per_constraint.items()}}


def pareto_front(points: list[tuple[float, float]]) -> list[int]:
    """Indices of non-dominated points when both coordinates are minimised."""
    front = []
    for i, (a, b) in enumerate(points):
        if not any((c <= a and d <= b) and (c < a or d < b) for j, (c, d) in enumerate(points)
                   if j != i):
            front.append(i)
    return front


def allocate(model: MechanicalModel, experiment: ExperimentConfig, config: AllocationConfig,
             progress: Callable[[dict[str, Any]], None] | None = None,
             cancel: threading.Event | None = None) -> dict[str, Any]:
    spec = model.spec
    for tol_id in config.tolerances:
        if not scalable(spec, tol_id):
            raise ValueError(f"tolerance {tol_id!r} has a distribution that cannot be scaled")
    unknown = set(config.costs) - set(config.tolerances)
    if unknown:
        raise ValueError(f"cost terms for tolerances that are not optimised: {sorted(unknown)}")
    lo, hi = config.scale_range
    d = len(config.tolerances)
    unit = qmc.LatinHypercube(d=d, seed=config.seed).random(config.candidates - 1)
    scale_rows = [np.ones(d), *(lo + unit * (hi - lo))]
    candidates: list[dict[str, Any]] = []
    total = len(scale_rows) + 1
    for i, row in enumerate(scale_rows):
        scales = dict(zip(config.tolerances, [float(v) for v in row], strict=True))
        res = _evaluate(model, experiment, scales, config.objective_metric,
                        config.objective_quantile, config.samples, config.seed, cancel)
        if res is None:
            return {"status": "cancelled", "candidates": candidates}
        candidates.append({"id": "current" if i == 0 else f"C{i:03d}", "scales": scales,
                           "cost": cost(config, scales), **res})
        if progress is not None:
            progress({"done": i + 1, "total": total})
    usable = [c for c in candidates if c.get("valid")]
    front = pareto_front([(c["cost"], c["objective"]) for c in usable])
    for k, c in enumerate(usable):
        c["pareto"] = k in front
    meeting = [c for c in usable if c["pass_fraction"] >= config.target_pass_fraction]
    recommended = min(meeting, key=lambda c: c["cost"]) if meeting else None
    verification = None
    if recommended is not None:
        verification = _evaluate(model, experiment, recommended["scales"],
                                 config.objective_metric, config.objective_quantile,
                                 config.verify_samples, config.seed + 7919, cancel)
        if verification is not None and verification.get("valid"):
            verification["meets_target"] = (
                verification["pass_fraction"] >= config.target_pass_fraction)
            verification["seed"] = config.seed + 7919
    if progress is not None:
        progress({"done": total, "total": total})
    priced = bool(config.costs)
    return {
        "status": "completed",
        "method": "Latin-hypercube candidate screen + non-dominated filtering; common random "
                  "numbers across candidates; recommended candidate re-verified with an "
                  "independent seed",
        "cost_label": "estimated cost (user-supplied cost model)" if priced
        else "relative cost index (no cost data supplied; not a price)",
        "objective": f"{config.objective_quantile:.0%} quantile of {config.objective_metric}",
        "target_pass_fraction": config.target_pass_fraction,
        "tolerances": config.tolerances,
        "candidates": candidates,
        "recommended": None if recommended is None else recommended["id"],
        "verification": verification,
        "note": None if recommended is not None else
        "no screened candidate reached the target pass fraction",
    }


def compare_specs(model: MechanicalModel, experiment: ExperimentConfig,
                  variants: dict[str, dict[str, float]], samples: int = 100,
                  seed: int = 0) -> dict[str, Any]:
    """Evaluate several tolerance-scale variants with common random numbers."""
    rows = {}
    metrics: set[str] = set()
    for name, scales in variants.items():
        vm = MechanicalModel(scaled_spec(model.spec, scales), model.directory)
        space = VariableSpace.from_model(vm.spec, experiment.operating)
        design = space.design("monte_carlo", samples, seed)
        res = [evaluate_scenario(vm, experiment, dict(zip(space.names, r.tolist(), strict=True)))
               for r in design.values]
        valid = [r for r in res if r["valid"]]
        passed = sum(r["passed"] for r in valid)
        keys = sorted(set.intersection(*(set(r["metrics"]) for r in valid))) if valid else []
        metrics |= set(keys)
        rows[name] = {
            "scales": scales, "valid": len(valid), "passed": passed,
            "pass_fraction": passed / len(valid) if valid else None,
            "pass_interval": list(wilson_interval(passed, len(valid))) if valid else None,
            "metrics": {k: {"mean": float(np.mean([r["metrics"][k] for r in valid])),
                            "p95": float(np.quantile([r["metrics"][k] for r in valid], 0.95)),
                            "max": float(np.max([r["metrics"][k] for r in valid]))}
                        for k in keys},
            "constraint_pass_fraction": {
                c.name: float(np.mean([r["constraints"][c.name]["passed"] for r in valid]))
                for c in experiment.constraints} if valid else {},
        }
    return {"samples": samples, "seed": seed, "variants": rows, "metrics": sorted(metrics),
            "method": "Monte Carlo with common random numbers; Wilson 95% intervals"}


__all__ = ["AllocationConfig", "Constraint", "CostTerm", "Sampling", "allocate",
           "compare_specs", "cost", "pareto_front", "scaled_spec"]
