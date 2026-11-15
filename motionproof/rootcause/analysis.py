"""Automated root-cause investigation of a failed scenario.

Three kinds of evidence are kept apart:

* **association** - how the failing and passing scenarios of the experiment differ
  (Kolmogorov-Smirnov test). Association is not causation.
* **local sensitivity** - finite-difference effect of each variable on the violated metric at
  the failing configuration (real simulations).
* **counterfactual** - the scenario re-simulated with one variable returned to its nominal
  value. This is the causal evidence: a verified change in the outcome.

The written explanation is assembled only from these numbers.
"""

from __future__ import annotations

from typing import Any

import numpy as np
from scipy import stats

from motionproof.experiments.runner import Experiment, evaluate_scenario
from motionproof.model import MechanicalModel
from motionproof.tolerances.sampling import VariableSpace


def investigate(experiment: Experiment, scenario_id: str,
                model: MechanicalModel | None = None, counterfactuals: int = 8,
                step_fraction: float = 0.05) -> dict[str, Any]:
    results = experiment.results()
    stored = next((r for r in results if r["id"] == scenario_id), None)
    if stored is None:
        raise KeyError(f"scenario {scenario_id!r} has no stored result")
    if stored["passed"]:
        raise ValueError(f"scenario {scenario_id} passed; there is no failure to investigate")
    model = model or experiment.model()
    config = experiment.config
    row = experiment.row(stored["index"])
    names = experiment.names
    space = VariableSpace.from_model(model.spec, config.operating)
    nominal = dict(zip(space.names, space.nominal().tolist(), strict=True))
    bounds = dict(zip(space.names, space.bounds().tolist(), strict=True))

    violated = [c for c in config.constraints
                if not stored["constraints"].get(c.name, {}).get("passed", True)]
    assembly = [f for f in stored["failures"] if f["severity"] == "assembly_violation"]
    if violated:
        target = violated[0]
        metric, sign = target.metric, (1.0 if target.op == "<=" else -1.0)
    elif "min_mesh_backlash_mm" in stored["metrics"] and any(
            f["category"] == "mesh_interference" for f in assembly):
        target, metric, sign = None, "min_mesh_backlash_mm", -1.0
    else:
        raise ValueError("the scenario failed without a violated metric to analyse "
                         f"({stored.get('message') or 'invalid simulation'})")

    def badness(res: dict[str, Any]) -> float | None:
        """Larger = worse, in the metric's own unit."""
        return sign * res["metrics"][metric] if res["valid"] and metric in res["metrics"] \
            else None

    base = evaluate_scenario(model, config, row)
    base_bad = badness(base)
    if base_bad is None:
        raise ValueError("the failing scenario does not simulate validly on replay")

    # --- association across the experiment ------------------------------------------
    valid = [r for r in results if r["valid"]]
    fail_idx = [r["index"] for r in valid if not r["passed"]]
    pass_idx = [r["index"] for r in valid if r["passed"]]
    design = np.asarray(experiment.manifest["design"]["values"])
    association: dict[str, dict[str, float]] = {}
    if len(fail_idx) >= 5 and len(pass_idx) >= 5:
        for i, n in enumerate(names):
            f, p = design[fail_idx, i], design[pass_idx, i]
            if np.ptp(design[:, i]) == 0:
                continue
            ks = stats.ks_2samp(f, p)
            association[n] = {"ks_statistic": float(ks.statistic), "p_value": float(ks.pvalue),
                              "median_failing": float(np.median(f)),
                              "median_passing": float(np.median(p))}

    # --- local sensitivity at the failure ---------------------------------------------
    local: dict[str, float] = {}
    for n in names:
        lo, hi = bounds[n]
        h = step_fraction * (hi - lo)
        if h <= 0:
            continue
        up = badness(evaluate_scenario(model, config, {**row, n: min(row[n] + h, hi)}))
        dn = badness(evaluate_scenario(model, config, {**row, n: max(row[n] - h, lo)}))
        if up is None or dn is None:
            continue
        span = min(row[n] + h, hi) - max(row[n] - h, lo)
        slope = (up - dn) / span if span > 0 else 0.0
        local[n] = slope * (row[n] - nominal[n])  # first-order share of the excess

    # --- counterfactual reruns ----------------------------------------------------------
    order = sorted(local, key=lambda n: -abs(local[n]))[:counterfactuals]
    contributions = []
    for n in order:
        res = evaluate_scenario(model, config, {**row, n: nominal[n]})
        bad = badness(res)
        entry: dict[str, Any] = {
            "parameter": n, "value": row[n], "reference": nominal[n],
            "local_first_order_effect": local[n],
            "association": association.get(n),
            "counterfactual": None if bad is None else {
                "metric_after": res["metrics"][metric],
                "improvement": base_bad - bad,
                "relative_improvement": (base_bad - bad) / abs(base_bad) if base_bad else 0.0,
                "fixes_failure": bool(res["passed"]),
                "method": "scenario re-simulated with this parameter at its nominal value"},
        }
        contributions.append(entry)
    contributions.sort(key=lambda c: -(c["counterfactual"] or {}).get("improvement", -np.inf))

    lines = []
    name = target.name if target else "gear mesh clearance"
    unit_val = base["metrics"][metric]
    lines.append(f"Scenario {scenario_id} violates '{name}': {metric} = {unit_val:.6g}"
                 + (f" against a limit of {target.limit:g}." if target else
                    " (negative means the teeth bind)."))
    helped = [c for c in contributions if c["counterfactual"]
              and c["counterfactual"]["improvement"] > 0]
    if helped:
        top = helped[0]
        cf = top["counterfactual"]
        lines.append(
            f"Returning {top['parameter']} from {top['value']:.6g} to its nominal "
            f"{top['reference']:.6g} in a controlled rerun changed {metric} to "
            f"{cf['metric_after']:.6g} ({100 * cf['relative_improvement']:.0f} % better)"
            + (" and removed the failure." if cf["fixes_failure"] else
               "; the failure remained."))
        fixers = [c["parameter"] for c in helped if c["counterfactual"]["fixes_failure"]]
        if len(fixers) > 1:
            lines.append("Each of these alone also removes the failure when set to nominal: "
                         + ", ".join(fixers[1:]) + ".")
        elif not fixers:
            lines.append("No single parameter removes the failure on its own: it is a "
                         "combination effect (see failure minimisation).")
        a = top["association"]
        if a and a["p_value"] < 0.01:
            lines.append(f"Across the experiment, failing scenarios have a different "
                         f"{top['parameter']} distribution from passing ones (KS p = "
                         f"{a['p_value']:.2g}); this association agrees with the rerun.")
    else:
        lines.append("No single-parameter rerun improved the result; the evidence does not "
                     "identify a cause.")
    return {
        "scenario": scenario_id, "metric": metric, "constraint": name,
        "value": unit_val, "limit": target.limit if target else 0.0,
        "failures": stored["failures"], "operating": stored["operating"],
        "simulations_run": 1 + 2 * len(local) + len(order),
        "contributions": contributions,
        "explanation": " ".join(lines),
        "evidence_note": "Counterfactual reruns are simulations and support causal statements "
                         "within the model. Association statistics do not.",
    }
