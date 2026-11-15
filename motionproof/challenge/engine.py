"""MotionProof Engineering Challenge: the least expensive tolerance specification that meets
stated requirements with stated statistical confidence.

Problem
-------
minimise   cost(x)                              (user cost model, or a labelled relative index)
subject to L(x) >= p_req                        L = one-sided exact (Clopper-Pearson) lower bound on
                                                the fraction of scenarios meeting *all*
                                                requirements, at confidence c

Decision variables are explicit: ``scale`` multiplies a tolerance's width and spread about its
centre; ``shift`` moves its centre (for example a backlash target). Every candidate is
evaluated with common random numbers. The search may use the Level 1 quasi-static model to
screen; the chosen candidate is always re-verified with Level 2 dynamics on fresh, independently
seeded scenarios, and only a candidate that passes verification is reported as feasible.

Search: a seeded Latin-hypercube screen followed by SciPy differential evolution on a penalised
objective, seeded with the best screened candidates.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any, Literal

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, model_validator
from scipy import stats
from scipy.optimize import differential_evolution
from scipy.stats import qmc

from motionproof.core.schema import MechanicalModelSpec
from motionproof.experiments.runner import ExperimentConfig, evaluate_scenario
from motionproof.fidelity.static import L1, L2, static_pose
from motionproof.model import MechanicalModel
from motionproof.optimisation.allocation import CostTerm, scaled_spec
from motionproof.tolerances.sampling import VariableSpace


class _M(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Variable(_M):
    tolerance: str
    kind: Literal["scale", "shift"] = "scale"
    lower: float
    upper: float
    min_limit: float | None = Field(default=None, description="physical floor for the "
                                    "resulting lower specification limit")
    max_limit: float | None = None

    @model_validator(mode="after")
    def _range(self) -> Variable:
        if self.upper <= self.lower:
            raise ValueError(f"variable {self.tolerance}: upper must exceed lower")
        if self.kind == "scale" and self.lower <= 0:
            raise ValueError(f"variable {self.tolerance}: scale must stay positive")
        return self

    @property
    def key(self) -> str:
        return f"{self.kind}:{self.tolerance}"


class Reliability(_M):
    target: float = Field(gt=0, lt=1, description="required fraction meeting all requirements")
    confidence: float = Field(default=0.9, gt=0.5, lt=1)


class ChallengeConfig(_M):
    name: str
    experiment: ExperimentConfig  # task, operating variation and requirements (constraints)
    variables: list[Variable] = Field(min_length=1)
    costs: dict[str, CostTerm] = Field(default_factory=dict)
    cost_source: str | None = None
    reliability: Reliability
    samples: int = Field(default=60, ge=10, le=5000)
    verify_samples: int = Field(default=200, ge=20, le=50_000)
    screen: int = Field(default=16, ge=2, le=500)
    refine_generations: int = Field(default=4, ge=0, le=100)
    search_fidelity: Literal["L1", "L2"] = "L2"
    l1_pose: dict[str, float] | None = None
    seed: int = 0

    @model_validator(mode="after")
    def _check(self) -> ChallengeConfig:
        keys = [v.key for v in self.variables]
        if len(set(keys)) != len(keys):
            raise ValueError("each (kind, tolerance) decision variable may appear once")
        unknown = set(self.costs) - {v.tolerance for v in self.variables if v.kind == "scale"}
        if unknown:
            raise ValueError(f"cost terms for tolerances that are not scaled: {sorted(unknown)}")
        if not self.experiment.constraints:
            raise ValueError("the challenge needs at least one requirement (constraint)")
        if self.search_fidelity == "L1" and self.l1_pose is None:
            raise ValueError("Level 1 search needs l1_pose: the pose evaluated statically")
        return self


def lower_bound(passed: int, n: int, confidence: float) -> float:
    """One-sided exact (Clopper-Pearson) lower confidence bound for a binomial proportion.

    Exact rather than Wilson because a reliability demonstration must not be optimistic:
    with zero failures Wilson needs 15 scenarios for 90 % at 90 % confidence, the exact
    bound 22.
    """
    if n == 0 or passed == 0:
        return 0.0
    if passed == n:
        return float((1.0 - confidence) ** (1.0 / n))
    return float(stats.beta.ppf(1.0 - confidence, passed, n - passed + 1))


def samples_needed(target: float, confidence: float) -> int:
    """Smallest n for which zero failures in n scenarios demonstrates ``target``."""
    for n in range(1, 10_000_000):
        if lower_bound(n, n, confidence) >= target:
            return n
    raise ValueError("target cannot be demonstrated")


def shifted_spec(spec: MechanicalModelSpec, shifts: dict[str, float]) -> MechanicalModelSpec:
    data = spec.model_dump(mode="json", by_alias=True)
    for t in data["tolerances"]:
        d = shifts.get(t["id"])
        if d is None:
            continue
        t["nominal"] += d
        dist = t["distribution"]
        for key in ("mean", "low", "high"):
            if key in dist:
                dist[key] += d
        if dist["type"] in ("discrete", "empirical"):
            k = "values" if dist["type"] == "discrete" else "samples"
            dist[k] = [v + d for v in dist[k]]
        if dist["type"] == "lognormal":
            raise ValueError(f"tolerance {t['id']}: a log-normal distribution cannot be shifted")
    return MechanicalModelSpec.model_validate(data)


class Challenge:
    def __init__(self, model: MechanicalModel, config: ChallengeConfig):
        self.model, self.config = model, config
        tol_ids = {t.id for t in model.spec.tolerances}
        missing = {v.tolerance for v in config.variables} - tol_ids
        if missing:
            raise KeyError(f"decision variables refer to unknown tolerances: {sorted(missing)}")
        self.priced = bool(config.costs)
        self.evaluations = 0
        self.history: list[dict[str, Any]] = []
        self._cache: dict[tuple[float, ...], dict[str, Any]] = {}

    # ---------------------------------------------------------------- pieces

    def decode(self, x: np.ndarray) -> dict[str, float]:
        return {v.key: float(val) for v, val in zip(self.config.variables, x, strict=True)}

    def baseline(self) -> dict[str, float]:
        return {v.key: (1.0 if v.kind == "scale" else 0.0) for v in self.config.variables}

    def limits(self, tol_id: str, decision: dict[str, float]) -> tuple[float, float]:
        """Specification limits of a tolerance under a decision (scale about the centre, then
        shift)."""
        t = self.model.spec.tolerance(tol_id)
        scale = decision.get(f"scale:{tol_id}", 1.0)
        shift = decision.get(f"shift:{tol_id}", 0.0)
        mid = t.nominal + (t.upper + t.lower) / 2 + shift
        half = (t.upper - t.lower) / 2 * scale
        return mid - half, mid + half

    def process_yield(self, tol_id: str, decision: dict[str, float]) -> float:
        term = self.config.costs[tol_id]
        assert term.process is not None
        lo, hi = self.limits(tol_id, decision)
        mu = term.process.mean + decision.get(f"shift:{tol_id}", 0.0)
        sd = term.process.std
        return float(stats.norm.cdf((hi - mu) / sd) - stats.norm.cdf((lo - mu) / sd))

    def cost(self, decision: dict[str, float]) -> float:
        total = 0.0
        for v in self.config.variables:
            if v.kind != "scale":
                continue
            term = self.config.costs.get(v.tolerance, CostTerm())
            if term.model == "yield":
                assert term.unit_cost is not None
                y = self.process_yield(v.tolerance, decision)
                total += term.fixed + (term.unit_cost + term.inspection_cost) / max(y, 1e-9)
            else:
                total += term.fixed + term.coefficient / decision[v.key] ** term.exponent
        return total

    def physical_violations(self, spec: MechanicalModelSpec) -> list[str]:
        """Resulting specifications that cannot exist (for example a negative clearance).

        Clearance and backlash characteristics are floored at zero unless the variable states
        its own ``min_limit``.
        """
        out = []
        for v in self.config.variables:
            t = spec.tolerance(v.tolerance)
            floor = v.min_limit
            if floor is None and t.characteristic in PHYSICAL_NON_NEGATIVE:
                floor = 0.0
            lo = min(t.lower_limit, *_support(t))
            hi = max(t.upper_limit, *_support(t))
            if floor is not None and lo < floor - 1e-15:
                out.append(f"{t.id}: lower limit {lo:.6g} {t.unit} is below the physical "
                           f"minimum {floor:g}")
            if v.max_limit is not None and hi > v.max_limit + 1e-15:
                out.append(f"{t.id}: upper limit {hi:.6g} {t.unit} exceeds {v.max_limit:g}")
        return sorted(set(out))

    def candidate_model(self, decision: dict[str, float]) -> MechanicalModel:
        scales = {k.split(":", 1)[1]: v for k, v in decision.items() if k.startswith("scale:")}
        shifts = {k.split(":", 1)[1]: v for k, v in decision.items() if k.startswith("shift:")}
        spec = shifted_spec(scaled_spec(self.model.spec, scales), shifts)
        yields = {k: t for k, t in self.config.costs.items() if t.model == "yield"}
        if yields:
            data = spec.model_dump(mode="json", by_alias=True)
            for t in data["tolerances"]:
                term = yields.get(t["id"])
                if term is None or term.process is None:
                    continue
                lo, hi = self.limits(t["id"], decision)
                mu = term.process.mean + decision.get(f"shift:{t['id']}", 0.0)
                # 100 % inspection: accepted parts are the process truncated to the limits
                t["distribution"] = {"type": "truncated_normal", "mean": mu,
                                     "std": term.process.std, "low": lo, "high": hi}
                t["lower"], t["upper"] = lo - t["nominal"], hi - t["nominal"]
                t["source"] = (f"process {term.process.basis} ({term.process.source}), "
                               "inspected and sorted to the specification")
            spec = MechanicalModelSpec.model_validate(data)
        return MechanicalModel(spec, self.model.directory)

    def evaluate(self, decision: dict[str, float], samples: int, seed: int,
                 level: Literal["L1", "L2"], keep_rows: bool = False) -> dict[str, Any]:
        cfg = self.config
        model = self.candidate_model(decision)
        invalid = self.physical_violations(model.spec)
        if invalid:
            return {"decision": decision, "cost": self.cost(decision), "level": L2 if level ==
                    "L2" else L1, "samples": 0, "valid": 0, "passed": 0, "seed": seed,
                    "pass_fraction": 0.0, "lower_bound": 0.0, "feasible": False,
                    "physically_invalid": invalid, "constraint_pass_fraction": {},
                    "metrics": {}, "failure_categories": {}}
        space = VariableSpace.from_model(model.spec, cfg.experiment.operating)
        design = space.design("monte_carlo", samples, seed)
        passed, valid = 0, 0
        per: dict[str, int] = {c.name: 0 for c in cfg.experiment.constraints}
        metrics: dict[str, list[float]] = {c.metric: [] for c in cfg.experiment.constraints}
        failures: dict[str, int] = {}
        rows = []
        for r in design.values:
            row = dict(zip(space.names, r.tolist(), strict=True))
            if level == "L2":
                res = evaluate_scenario(model, cfg.experiment, row)
                ok_valid, m, fails = res["valid"], res["metrics"], res["failures"]
                ok = res["passed"]
            else:
                vals = {k: v for k, v in row.items() if not k.startswith("op.")}
                payload = row.get("op.payload_mass", cfg.experiment.task.payload_mass)
                variant = model.variant(vals)
                m = static_pose(model, variant, cfg.l1_pose or {}, payload)["metrics"]
                ok_valid = True
                fails = [{"category": v["category"]} for v in variant.violations]
                ok = not fails
                for c in cfg.experiment.constraints:
                    if c.metric not in m:
                        raise KeyError(f"metric {c.metric!r} has no Level 1 equivalent; "
                                       "search this challenge at Level 2")
                    if not c.check(m[c.metric])[0]:
                        ok = False
                        fails.append({"category": c.category})
            self.evaluations += 1
            if not ok_valid:
                continue
            valid += 1
            passed += ok
            for c in cfg.experiment.constraints:
                if c.metric in m:
                    metrics[c.metric].append(m[c.metric])
                    per[c.name] += bool(c.check(m[c.metric])[0])
            for cat in {f["category"] for f in fails}:
                failures[cat] = failures.get(cat, 0) + 1
            if keep_rows:
                rows.append({"values": row, "passed": ok})
        lb = lower_bound(passed, valid, cfg.reliability.confidence)
        out = {
            "decision": decision, "cost": self.cost(decision), "level": L2 if level == "L2"
            else L1, "samples": samples, "valid": valid, "passed": passed, "seed": seed,
            "pass_fraction": passed / valid if valid else 0.0, "lower_bound": lb,
            "feasible": lb >= cfg.reliability.target,
            "constraint_pass_fraction": {k: v / valid if valid else 0.0 for k, v in per.items()},
            "metrics": {k: {"mean": float(np.mean(v)), "p95": float(np.quantile(v, 0.95)),
                            "max": float(np.max(v))} for k, v in metrics.items() if v},
            "failure_categories": failures,
            "yield": {k: self.process_yield(k, decision) for k, t in cfg.costs.items()
                      if t.model == "yield"},
        }
        if keep_rows:
            out["rows"] = rows
        return out

    # ---------------------------------------------------------------- search

    def run(self, progress: Callable[[dict[str, Any]], None] | None = None,
            cancel: threading.Event | None = None) -> dict[str, Any]:
        cfg = self.config
        lo = np.array([v.lower for v in cfg.variables])
        hi = np.array([v.upper for v in cfg.variables])
        level = cfg.search_fidelity
        base = self.evaluate(self.baseline(), cfg.samples, cfg.seed, level)
        base["id"] = "baseline"
        candidates = [base]
        total = 1 + cfg.screen + cfg.refine_generations * max(cfg.screen // 2, 4) * len(lo)

        def tick() -> None:
            if progress:
                feas = [c for c in candidates if c["feasible"]]
                progress({"done": len(candidates), "total": total,
                          "best_cost": min((c["cost"] for c in feas), default=None)})

        def penalised(x: np.ndarray) -> float:
            if cancel is not None and cancel.is_set():
                raise _Stop
            key = tuple(np.round(x, 9))
            if key not in self._cache:
                ev = self.evaluate(self.decode(x), cfg.samples, cfg.seed, level)
                ev["id"] = f"C{len(candidates):03d}"
                candidates.append(ev)
                self._cache[key] = ev
                tick()
            ev = self._cache[key]
            if ev["feasible"]:
                return float(ev["cost"])
            worst = self.cost(self.decode(lo)) if self.config.variables else 0.0
            return float(worst + 1.0 + 100.0 * (cfg.reliability.target - ev["lower_bound"]))

        status = "completed"
        try:
            unit = qmc.LatinHypercube(d=len(lo), seed=cfg.seed).random(cfg.screen)
            pts = lo + unit * (hi - lo)
            scores = [penalised(p) for p in pts]
            if cfg.refine_generations:
                k = max(cfg.screen // 2, 4)
                init = pts[np.argsort(scores)[:k]]
                if len(init) < 5:
                    init = np.vstack([init, lo + qmc.LatinHypercube(
                        d=len(lo), seed=cfg.seed + 1).random(5 - len(init)) * (hi - lo)])
                differential_evolution(penalised, list(zip(lo, hi, strict=True)),
                                       init=init, maxiter=cfg.refine_generations,
                                       seed=cfg.seed, tol=0.0, polish=False,
                                       updating="immediate")
        except _Stop:
            status = "cancelled"
        tick()

        feasible = sorted((c for c in candidates if c["feasible"]), key=lambda c: c["cost"])
        verification = []
        chosen = None
        for c in feasible[:5]:
            v = self.evaluate(c["decision"], cfg.verify_samples, cfg.seed + 104_729, "L2")
            v["candidate"] = c["id"]
            verification.append(v)
            if v["feasible"]:
                chosen = c["id"]
                break
        baseline_verify = self.evaluate(self.baseline(), cfg.verify_samples,
                                        cfg.seed + 104_729, "L2")

        front = []
        for c in candidates:
            if not any(o["cost"] <= c["cost"] and o["lower_bound"] >= c["lower_bound"]
                       and (o["cost"] < c["cost"] or o["lower_bound"] > c["lower_bound"])
                       for o in candidates):
                front.append(c["id"])
        n_req = samples_needed(cfg.reliability.target, cfg.reliability.confidence)
        notes = []
        rejected = sum(1 for c in candidates if c.get("physically_invalid"))
        if rejected:
            notes.append(f"{rejected} candidates were rejected without simulation because "
                         "their specification is physically impossible (for example a "
                         "negative clearance)")
        if cfg.samples < n_req:
            notes.append(f"{cfg.samples} search scenarios per candidate cannot demonstrate "
                         f"{cfg.reliability.target:.1%} at {cfg.reliability.confidence:.0%} "
                         f"confidence even with zero failures; at least {n_req} are needed, "
                         "so no candidate can be feasible in the search")
        if cfg.verify_samples < n_req:
            notes.append(f"verification needs at least {n_req} scenarios for this target")
        if chosen is None:
            notes.append("no candidate met the requirement after independent verification "
                         "within the given variable ranges" if feasible else
                         "no candidate met the requirement in the search within the given "
                         "variable ranges")
        if level == "L1":
            agree = [v for v in verification if v["candidate"] in {c["id"] for c in feasible}]
            if any(not v["feasible"] for v in agree):
                notes.append("a candidate that was feasible at Level 1 failed Level 2 "
                             "verification: Level 1 is not sufficient near these limits")
        return {
            "name": cfg.name, "status": status, "chosen": chosen,
            "cost_label": ("estimated cost from the user cost model"
                           + (f" ({cfg.cost_source})" if cfg.cost_source else ""))
            if self.priced else "relative cost index (no cost data supplied; not a price)",
            "cost_terms": {k: t.model_dump() for k, t in cfg.costs.items()},
            "objective": "minimise cost subject to the one-sided Clopper-Pearson lower bound "
                         "of the "
                         f"all-requirements pass fraction >= {cfg.reliability.target:g} at "
                         f"{cfg.reliability.confidence:.0%} confidence",
            "search": {"fidelity": L1 if level == "L1" else L2, "screen": cfg.screen,
                       "refine_generations": cfg.refine_generations, "seed": cfg.seed,
                       "candidates": len(candidates), "scenario_evaluations": self.evaluations,
                       "method": "Latin-hypercube screen + differential evolution (SciPy) on a "
                                 "penalised objective, common random numbers"},
            "variables": [v.model_dump() for v in cfg.variables],
            "requirements": [c.model_dump() for c in cfg.experiment.constraints],
            "reliability": cfg.reliability.model_dump(), "samples_needed_zero_failures": n_req,
            "candidates": candidates, "pareto": front,
            "verification": verification, "baseline_verification": baseline_verify,
            "notes": notes,
        }


class _Stop(Exception):
    pass


PHYSICAL_NON_NEGATIVE = {"radial_clearance", "axial_clearance", "backlash"}


def _support(t: Any) -> tuple[float, float]:
    from motionproof.tolerances.distributions import bounds

    return bounds(t.distribution)


def comparison(result: dict[str, Any], model: MechanicalModel) -> dict[str, Any]:
    """Original versus chosen specification (limits, cost and verified performance)."""
    chosen = next((c for c in result["candidates"] if c["id"] == result["chosen"]), None)
    if chosen is None:
        return {"available": False, "reason": "no verified candidate"}
    verify = next(v for v in result["verification"] if v["candidate"] == chosen["id"])
    base = result["baseline_verification"]
    rows = []
    for tol_id in dict.fromkeys(v["tolerance"] for v in result["variables"]):
        tol = model.spec.tolerance(tol_id)
        scale = chosen["decision"].get(f"scale:{tol_id}", 1.0)
        shift = chosen["decision"].get(f"shift:{tol_id}", 0.0)
        mid = tol.nominal + (tol.upper + tol.lower) / 2 + shift
        half = (tol.upper - tol.lower) / 2 * scale
        rows.append({"tolerance": tol.id, "scale": scale, "shift": shift, "unit": tol.unit,
                     "original_limits": [tol.lower_limit, tol.upper_limit],
                     "proposed_limits": [mid - half, mid + half]})
    priced = result["cost_label"].startswith("estimated")
    baseline_cost = next(c for c in result["candidates"] if c["id"] == "baseline")["cost"]
    return {"available": True, "tolerances": rows,
            "cost": {"original": baseline_cost, "proposed": chosen["cost"],
                     "difference": chosen["cost"] - baseline_cost, "label": result["cost_label"],
                     "savings_claim": "supported by the user cost model" if priced else
                     "not a saving: no cost data were supplied"},
            "verified": {"original": base, "proposed": verify}}
