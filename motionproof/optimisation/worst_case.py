"""Worst-case search: find manufacturing configurations that degrade a performance metric.

The optimiser only *proposes* a configuration. The reported result is always a fresh,
separately executed confirmation simulation of that configuration, and it is labelled a
failure only if that confirmation violates a stated constraint.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal

import numpy as np
from scipy.optimize import differential_evolution

from motionproof.experiments.runner import ExperimentConfig, evaluate_scenario
from motionproof.model import MechanicalModel
from motionproof.tolerances.sampling import VariableSpace

Algorithm = Literal["differential_evolution", "random", "corners"]


class _Cancelled(Exception):
    pass


def search(
    model: MechanicalModel,
    config: ExperimentConfig,
    metric: str,
    direction: Literal["maximise", "minimise"] = "maximise",
    algorithm: Algorithm = "differential_evolution",
    budget: int = 300,
    seed: int = 0,
    progress: Callable[[dict[str, Any]], None] | None = None,
    cancel: threading.Event | None = None,
) -> dict[str, Any]:
    """Search the bounded variable space for the worst value of ``metric``."""
    space = VariableSpace.from_model(model.spec, config.operating)
    fixed = [i for i, n in enumerate(space.names) if n in config.fixed]
    free = [i for i in range(space.dim) if i not in fixed]
    bounds = space.bounds()
    nominal = space.nominal()
    sign = -1.0 if direction == "maximise" else 1.0
    history: list[dict[str, Any]] = []
    best: dict[str, Any] = {"value": None, "row": None}
    PENALTY = 1e9

    def full(xfree: np.ndarray) -> dict[str, float]:
        row = nominal.copy()
        row[free] = xfree
        return dict(zip(space.names, row.tolist(), strict=True))

    def objective(xfree: np.ndarray) -> float:
        if cancel is not None and cancel.is_set():
            raise _Cancelled
        row = full(xfree)
        res = evaluate_scenario(model, config, row)
        if not res["valid"] or metric not in res["metrics"]:
            value = None
        else:
            value = float(res["metrics"][metric])
        improved = value is not None and (
            best["value"] is None or sign * value < sign * best["value"])
        if improved:
            best.update(value=value, row=row)
        history.append({"evaluation": len(history) + 1, "value": value,
                        "best": best["value"]})
        if progress is not None:
            progress({"done": len(history), "total": budget, "best": best["value"]})
        return PENALTY if value is None else sign * value

    lo, hi = bounds[free, 0], bounds[free, 1]
    rng = np.random.default_rng(seed)
    cancelled = False
    try:
        objective(nominal[free])
        if algorithm == "differential_evolution":
            d = len(free)
            popsize = max(4, min(15, budget // (4 * max(d, 1)) or 1))
            maxiter = max(1, budget // (popsize * max(d, 1)) - 1)
            span = np.where(hi > lo, hi - lo, 1.0)
            # variables with a degenerate range are held fixed by a zero-width box
            differential_evolution(
                objective, list(zip(lo, np.where(hi > lo, hi, lo + 1e-15 * span), strict=True)),
                seed=seed, popsize=popsize, maxiter=maxiter, tol=0.0, polish=False,
                init="latinhypercube", updating="immediate")
        elif algorithm == "random":
            for _ in range(budget - 1):
                objective(lo + rng.random(len(free)) * (hi - lo))
        elif algorithm == "corners":
            for _ in range(budget - 1):
                objective(np.where(rng.integers(0, 2, len(free)) == 1, hi, lo))
        else:
            raise ValueError(f"unknown algorithm {algorithm!r}")
    except _Cancelled:
        cancelled = True

    if best["row"] is None:
        return {"status": "no_valid_evaluation", "history": history}
    confirmation = evaluate_scenario(model, config, best["row"], keep_trace=True)
    nominal_run = evaluate_scenario(model, config,
                                    dict(zip(space.names, nominal.tolist(), strict=True)))
    confirmed_value = confirmation["metrics"].get(metric)
    return {
        "status": "cancelled" if cancelled else "completed",
        "metric": metric, "direction": direction, "algorithm": algorithm, "seed": seed,
        "evaluations": len(history),
        "proposed_value": best["value"],
        "confirmed_value": confirmed_value,
        "confirmation_matches": confirmed_value is not None
        and abs(confirmed_value - best["value"]) <= 1e-9 * max(1.0, abs(best["value"])),
        "nominal_value": nominal_run["metrics"].get(metric),
        "is_failure": not confirmation["passed"],
        "configuration": best["row"],
        "bounds": {n: bounds[i].tolist() for i, n in enumerate(space.names)},
        "nominal": dict(zip(space.names, nominal.tolist(), strict=True)),
        "confirmation": confirmation,
        "history": history,
        "note": "the configuration is the worst found within the search budget, not a proven "
                "global worst case",
    }


def minimise_failure(model: MechanicalModel, config: ExperimentConfig,
                     failing: dict[str, float]) -> dict[str, Any]:
    """Return variables to nominal one by one while the scenario keeps failing."""
    space = VariableSpace.from_model(model.spec, config.operating)
    nominal = dict(zip(space.names, space.nominal().tolist(), strict=True))
    bounds = dict(zip(space.names, space.bounds().tolist(), strict=True))
    first = evaluate_scenario(model, config, failing)
    if first["passed"]:
        return {"status": "not_a_failure", "initial": failing}
    categories = {f["category"] for f in first["failures"]}

    def still_fails(row: dict[str, float]) -> bool:
        res = evaluate_scenario(model, config, row)
        return (not res["passed"]) and bool(categories & {f["category"] for f in res["failures"]})

    def deviation(name: str) -> float:
        lo, hi = bounds[name]
        return float(abs(failing[name] - nominal[name]) / ((hi - lo) or 1.0))

    current = dict(failing)
    removed: list[str] = []
    for name in sorted(current, key=deviation):
        if current[name] == nominal[name]:
            continue
        trial = {**current, name: nominal[name]}
        if still_fails(trial):
            current = trial
            removed.append(name)
    confirmation = evaluate_scenario(model, config, current, keep_trace=True)
    kept = {n: {"value": current[n], "nominal": nominal[n]}
            for n in current if current[n] != nominal[n]}
    return {
        "status": "minimised", "failure_categories": sorted(categories),
        "initial": failing, "minimised": current, "returned_to_nominal": removed,
        "essential_parameters": kept,
        "confirmed": not confirmation["passed"], "confirmation": confirmation,
    }


def save(result: dict[str, Any], path: str | Path) -> None:
    Path(path).write_text(json.dumps(result, indent=1), encoding="utf-8")
