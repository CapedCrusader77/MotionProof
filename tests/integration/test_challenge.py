"""Engineering Challenge on an analytically solvable case.

Single joint, horizontal hold. Backlash b ~ U(0.01 - 0.01 s, 0.01 + 0.01 s) for width scale s.
Requirement: angle error <= b_lim/2 + windup, i.e. b <= b_lim. Failure fraction
    F(s) = max(0, (0.01 + 0.01 s - b_lim) / (0.02 s)).
With b_lim = 0.016: zero failures for s <= 0.6; F = 0.1 at s = 0.75.
Cost = 1 / s, so the cheapest feasible specification is the largest feasible s.
"""

from __future__ import annotations

import pytest

from motionproof.challenge.engine import (
    Challenge,
    ChallengeConfig,
    comparison,
    lower_bound,
    samples_needed,
)
from tests.conftest import ARM_LENGTH, ARM_MASS

WINDUP = ARM_MASS * 9.81 * ARM_LENGTH / 2000.0


def _config(b_lim: float, fidelity: str = "L1", **kw: object) -> ChallengeConfig:
    return ChallengeConfig.model_validate({
        "name": "analytic", "search_fidelity": fidelity, "l1_pose": {"j": 0.0},
        "experiment": {"name": "hold", "task": {"type": "static_hold", "pose": {"j": 0.0},
                                                "duration": 0.6},
                       "constraints": [{"name": "angle", "metric": "angle_error_final",
                                        "op": "<=", "limit": b_lim / 2 + WINDUP}]},
        "variables": [{"tolerance": "backlash_tol", "kind": "scale", "lower": 0.2,
                       "upper": 1.0}],
        "costs": {"backlash_tol": {"coefficient": 1.0, "exponent": 1.0}},
        "cost_source": "test cost model, 1/scale",
        "reliability": {"target": 0.9, "confidence": 0.9},
        "samples": 40, "verify_samples": 60, "screen": 8, "refine_generations": 3, "seed": 1,
        **kw})


def test_statistics_helpers() -> None:
    assert samples_needed(0.9, 0.9) == 22  # ln(0.1)/ln(0.9) = 21.85 for zero failures
    assert lower_bound(22, 22, 0.9) >= 0.9 > lower_bound(21, 21, 0.9)
    assert lower_bound(0, 10, 0.9) == 0.0


def test_feasible_challenge_finds_the_analytic_optimum_and_verifies(single_joint) -> None:  # type: ignore[no-untyped-def]
    model = single_joint()
    res = Challenge(model, _config(0.016)).run()
    assert res["chosen"] is not None
    chosen = next(c for c in res["candidates"] if c["id"] == res["chosen"])
    s = chosen["decision"]["scale:backlash_tol"]
    assert 0.5 <= s <= 0.75  # analytic optimum: about 0.6 to 0.68 for this sample size
    ver = next(v for v in res["verification"] if v["candidate"] == res["chosen"])
    assert ver["level"] == "L2_reduced_order_dynamics" and ver["feasible"]
    assert ver["seed"] != res["search"]["seed"]
    assert res["baseline_verification"]["pass_fraction"] == pytest.approx(0.8, abs=0.12)
    assert "baseline" in [c["id"] for c in res["candidates"]]
    assert res["chosen"] in res["pareto"]
    cmp_ = comparison(res, model)
    row = cmp_["tolerances"][0]
    assert row["original_limits"] == [0.0, 0.02]
    assert row["proposed_limits"] == pytest.approx([0.01 - 0.01 * s, 0.01 + 0.01 * s])
    assert row["scale"] == pytest.approx(s) and row["shift"] == 0.0
    assert cmp_["cost"]["proposed"] == pytest.approx(1 / s)
    assert cmp_["cost"]["savings_claim"] == "supported by the user cost model"


def test_reproducible(single_joint) -> None:  # type: ignore[no-untyped-def]
    model = single_joint()
    a = Challenge(model, _config(0.016, refine_generations=1)).run()
    b = Challenge(model, _config(0.016, refine_generations=1)).run()
    assert [c["decision"] for c in a["candidates"]] == [c["decision"] for c in b["candidates"]]
    assert a["chosen"] == b["chosen"]


def test_infeasible_challenge_is_reported_honestly(single_joint) -> None:  # type: ignore[no-untyped-def]
    """b_lim = 0.008 is below the centre 0.01: no scale in [0.2, 1] can pass."""
    res = Challenge(single_joint(), _config(0.008, refine_generations=1)).run()
    assert res["chosen"] is None
    assert any("no candidate met the requirement" in n for n in res["notes"])


def test_too_few_samples_is_flagged(single_joint) -> None:  # type: ignore[no-untyped-def]
    res = Challenge(single_joint(), _config(0.016, samples=15, refine_generations=0)).run()
    assert res["chosen"] is None
    assert any("at least 22 are needed" in n for n in res["notes"])


def test_unpriced_cost_is_a_relative_index(single_joint) -> None:  # type: ignore[no-untyped-def]
    cfg = _config(0.016, refine_generations=0).model_copy(update={"costs": {}})
    res = Challenge(single_joint(), cfg).run()
    assert "not a price" in res["cost_label"]
    cmp_ = comparison(res, single_joint())
    if cmp_["available"]:
        assert cmp_["cost"]["savings_claim"].startswith("not a saving")


def test_level2_search_on_the_same_problem(single_joint) -> None:  # type: ignore[no-untyped-def]
    res = Challenge(single_joint(), _config(0.016, "L2", screen=6, refine_generations=0,
                                            samples=30)).run()
    assert res["search"]["fidelity"] == "L2_reduced_order_dynamics"
    assert res["chosen"] is not None


def test_config_validation() -> None:
    with pytest.raises(ValueError, match="l1_pose"):
        _config(0.016).model_copy(update={"l1_pose": None}).model_validate(
            _config(0.016).model_dump() | {"l1_pose": None})
    with pytest.raises(ValueError, match="positive"):
        ChallengeConfig.model_validate(_config(0.016).model_dump() | {"variables": [
            {"tolerance": "backlash_tol", "kind": "scale", "lower": 0.0, "upper": 1.0}]})


def test_physically_impossible_specifications_are_rejected(single_joint) -> None:  # type: ignore[no-untyped-def]
    """A backlash shift that drives the lower limit below zero is rejected unsimulated."""
    raw = _config(0.016, refine_generations=0, screen=4).model_dump()
    raw["variables"].append({"tolerance": "backlash_tol", "kind": "shift", "lower": -0.02,
                             "upper": -0.015})
    cfg = ChallengeConfig.model_validate(raw)
    ch = Challenge(single_joint(), cfg)
    res = ch.run()
    bad = [c for c in res["candidates"] if c.get("physically_invalid")]
    assert bad and all(c["samples"] == 0 and not c["feasible"] for c in bad)
    assert "below the physical minimum 0" in bad[0]["physically_invalid"][0]
    assert any("physically impossible" in n for n in res["notes"])


def _yield_config(**kw: object) -> ChallengeConfig:
    raw = _config(0.016).model_dump() | {"costs": {"backlash_tol": {
        "model": "yield", "unit_cost": 1.0,
        "process": {"mean": 0.01, "std": 0.004, "basis": "specified",
                    "source": "test process"}}}, "cost_source": "test yield model"} | kw
    return ChallengeConfig.model_validate(raw)


def test_yield_cost_model_matches_closed_form(single_joint) -> None:  # type: ignore[no-untyped-def]
    """Process N(0.01, 0.004) sorted to 0.01 +- 0.01 s. Yield = 2 Phi(0.01 s / 0.004) - 1,
    cost per accepted part = 1 / yield. Accepted parts fail when b > 0.016, so every
    specification with s <= 0.6 passes; wider ones fail
    (P(0.016 < b < U) / P(L < b < U)); the original (s = 1) fails 6.1 %."""
    from scipy import stats

    ch = Challenge(single_joint(), _yield_config(samples=60, screen=8, refine_generations=2))
    for s in (0.4, 0.6, 1.0):
        y = 2 * stats.norm.cdf(0.01 * s / 0.004) - 1
        assert ch.cost({"scale:backlash_tol": s}) == pytest.approx(1 / y, rel=1e-12)
    m = ch.candidate_model({"scale:backlash_tol": 0.6}).spec.tolerance("backlash_tol")
    assert m.distribution.type == "truncated_normal"  # type: ignore[union-attr]
    assert (m.lower_limit, m.upper_limit) == pytest.approx((0.004, 0.016))
    res = ch.run()
    assert res["chosen"] is not None
    chosen = next(c for c in res["candidates"] if c["id"] == res["chosen"])
    s = chosen["decision"]["scale:backlash_tol"]
    assert 0.5 <= s <= 0.75
    assert chosen["cost"] == pytest.approx(1 / (2 * stats.norm.cdf(0.01 * s / 0.004) - 1))
    base = res["baseline_verification"]
    assert base["pass_fraction"] == pytest.approx(0.939, abs=0.06)
    assert chosen["cost"] > res["candidates"][0]["cost"]  # reliability costs scrap here
    assert res["cost_terms"]["backlash_tol"]["model"] == "yield"


def test_yield_term_needs_process_and_unit_cost() -> None:
    with pytest.raises(ValueError, match="unit_cost and process"):
        _yield_config(costs={"backlash_tol": {"model": "yield", "unit_cost": 1.0}})
