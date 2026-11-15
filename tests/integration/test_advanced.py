"""Multi-fidelity, adaptive sampling, workspace maps, root cause and degradation."""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pytest
from scipy import stats

from motionproof.adaptive.sampler import GaussianProcess, run_adaptive
from motionproof.degradation.model import (
    Mechanism,
    compare_maintenance,
    fit_progression,
    lifetime_experiment,
)
from motionproof.experiments.runner import Constraint, Experiment, ExperimentConfig
from motionproof.fidelity.static import discrepancy, static_pose, sufficient
from motionproof.model import MechanicalModel
from motionproof.rootcause.analysis import investigate
from motionproof.simulation.tasks import StaticHold
from motionproof.tolerances.sampling import VariableSpace
from motionproof.workspace.maps import compare_maps, reliability_map, verify_pose
from tests.conftest import ARM_LENGTH, ARM_MASS

G = 9.81

# ---- multi-fidelity -----------------------------------------------------------------------


def test_level1_matches_closed_form_and_level2(single_joint) -> None:  # type: ignore[no-untyped-def]
    """Analytic: deflection = b/2 + m g L / k. Level 1 must match it; Level 2 within 0.5 %."""
    backlash, k = 0.010, 2000.0
    m = single_joint(backlash=backlash, stiffness=k)
    variant = m.nominal_variant()
    lo = static_pose(m, variant, {"j": 0.0})
    analytic = backlash / 2 + ARM_MASS * G * ARM_LENGTH / k
    assert lo["metrics"]["angle_error_final"] == pytest.approx(analytic, rel=1e-4)
    assert lo["metrics"]["torque_utilisation_peak"] == pytest.approx(
        ARM_MASS * G * ARM_LENGTH / 20 / 2.0, rel=1e-4)
    hi = m.engine.run(variant, StaticHold(pose={"j": 0.0}, duration=1.0))
    assert hi.metrics["angle_error_final"] == pytest.approx(
        lo["metrics"]["angle_error_final"], rel=5e-3)
    assert lo["level"] == "L1_quasi_static" and not lo["flank_ambiguous"]


def test_level1_reports_flank_ambiguity_at_zero_load(single_joint) -> None:  # type: ignore[no-untyped-def]
    m = single_joint(backlash=0.01)
    res = static_pose(m, m.nominal_variant(), {"j": math.pi / 2})  # arm vertical: no torque
    assert res["flank_ambiguous"] is True
    assert res["metrics"]["angle_error_final"] == pytest.approx(0.005, rel=1e-3)


def test_discrepancy_and_sufficiency_rule(single_joint) -> None:  # type: ignore[no-untyped-def]
    m = single_joint()
    rows = [{"backlash_tol": b} for b in (0.0, 0.005, 0.01, 0.015, 0.02)]
    d = discrepancy(m, rows, {"j": 0.0})
    band = d["metrics"]["ee_error_final"]["p95_abs_difference"]
    assert d["variants"] == 5 and band < 2e-5  # metres
    value = static_pose(m, m.variant(rows[2]), {"j": 0.0})["metrics"]["ee_error_final"]
    far = sufficient(value, "<=", value + 1e-3, band)
    assert far["sufficient"] and far["verdict"] == "pass"
    near = sufficient(value, "<=", value + band, band)
    assert not near["sufficient"] and near["verdict"] == "undecided"
    assert "L2_reduced_order_dynamics" in near["action"]


# ---- adaptive sampling --------------------------------------------------------------------


def test_gaussian_process_interpolates_a_smooth_function() -> None:
    rng = np.random.default_rng(0)
    x = rng.uniform(-2, 2, (60, 2))

    def f(a: np.ndarray) -> np.ndarray:
        return np.sin(a[:, 0]) + 0.5 * a[:, 1] ** 2

    gp = GaussianProcess().fit(x, f(x))
    xt = rng.uniform(-1.8, 1.8, (200, 2))
    mean, std = gp.predict(xt)
    assert np.sqrt(np.mean((mean - f(xt)) ** 2)) < 0.02
    assert np.mean(np.abs(mean - f(xt)) <= 3 * std + 1e-9) > 0.95  # honest uncertainty
    assert gp.leave_one_out_q2(f(x)) > 0.99


def _limit_state(x: np.ndarray) -> float:
    """g = 3 - (x1 + x2) / sqrt(2) with standard normal inputs: P(fail) = Phi(-3)."""
    return 3.0 - (x[0] + x[1]) / math.sqrt(2.0)


def _population(n: int, seed: int) -> np.ndarray:
    return np.random.default_rng(seed).normal(size=(n, 2))


BOUNDS = np.array([[-4.0, 4.0], [-4.0, 4.0]])
TRUE_PF = float(stats.norm.cdf(-3.0))  # 1.35e-3


def test_adaptive_finds_a_rare_failure_boundary_and_is_reproducible() -> None:
    kw = dict(initial=12, budget=60, population=40_000)
    a = run_adaptive(_limit_state, _population, BOUNDS, seed=3, **kw)  # type: ignore[arg-type]
    b = run_adaptive(_limit_state, _population, BOUNDS, seed=3, **kw)  # type: ignore[arg-type]
    assert a["points"] == b["points"] and a["history"] == b["history"]
    assert a["simulations"]["total"] <= 60
    est = a["surrogate"]["predicted_failure_fraction"]
    # the surrogate classifies the fixed population; compare with that population's truth
    pool = _population(40_000, 4)
    truth = float(np.mean(3.0 - (pool[:, 0] + pool[:, 1]) / math.sqrt(2) < 0))
    assert est == pytest.approx(truth, rel=0.1)
    assert est == pytest.approx(TRUE_PF, rel=0.35)  # population sampling error included
    assert a["surrogate"]["kind"] == "prediction, not simulation"
    assert a["stopping_reason"]


def test_adaptive_versus_random_at_equal_budget() -> None:
    """Measured comparison over 8 seeds: relative error of the failure-probability estimate
    with 60 true simulations each. Random sampling with 60 draws almost never sees a
    1.35e-3 event, so its estimate is 0 (relative error 1)."""
    adaptive_err, random_err = [], []
    for seed in range(8):
        res = run_adaptive(_limit_state, _population, BOUNDS, initial=12, budget=60,
                           population=40_000, seed=seed)
        adaptive_err.append(abs(res["surrogate"]["predicted_failure_fraction"] - TRUE_PF)
                            / TRUE_PF)
        draws = _population(60, 1000 + seed)
        fails = sum(_limit_state(r) < 0 for r in draws)
        random_err.append(abs(fails / 60 - TRUE_PF) / TRUE_PF)
    assert np.median(adaptive_err) < 0.4
    assert np.median(random_err) > 0.9
    assert np.median(adaptive_err) < np.median(random_err)


def test_adaptive_stopping_rules() -> None:
    res = run_adaptive(_limit_state, _population, BOUNDS, initial=10, budget=12,
                       population=5000, seed=0)
    assert res["stopping_reason"] == "simulation budget reached"
    assert res["simulations"]["total"] == 12
    res = run_adaptive(_limit_state, _population, BOUNDS, initial=10, budget=500,
                       population=5000, seed=0, should_stop=lambda: True)
    assert res["stopping_reason"] == "cancelled" and res["simulations"]["adaptive"] == 0
    with pytest.raises(ValueError, match="initial"):
        run_adaptive(_limit_state, _population, BOUNDS, initial=2, budget=10)


def test_adaptive_warns_when_the_surrogate_is_poor() -> None:
    rng = np.random.default_rng(1)

    def noisy(x: np.ndarray) -> float:
        return float(rng.normal())  # pure noise: nothing to learn

    res = run_adaptive(noisy, _population, BOUNDS, initial=20, budget=30, population=2000)
    assert any("Q2" in w for w in res["warnings"])


# ---- workspace reliability ----------------------------------------------------------------


def test_workspace_map_two_link_arm_against_direct_simulation(
        reference_model: MechanicalModel) -> None:
    """A known 2 mrad axis tilt gives a pose-dependent error; the Level 1 map is checked
    against Level 2 simulation at selected poses (accepted difference 5 % + 20 um)."""
    m = reference_model
    space = VariableSpace.from_model(m.spec)
    nominal = dict(zip(space.names, space.nominal().tolist(), strict=True))
    tilted = [nominal | {"joint_axis_misalignment": math.degrees(2e-3)}]
    grid = {"shoulder": [-1.0, 0.0, 1.0], "elbow": [0.0, 1.2]}
    base = reliability_map(m, grid, [nominal], position_tolerance=1e-3)
    tilt = reliability_map(m, grid, tilted, position_tolerance=1e-3)
    assert len(tilt["cells"]) == 6 and all(c["reachable"] for c in tilt["cells"])
    cmp_ = compare_maps(base, tilt, "error_max")
    assert cmp_["b_worse_in"] == 6
    by_pose = {(c["pose"]["shoulder"], c["pose"]["elbow"]): c for c in tilt["cells"]}
    # stretched arm: the tilt moves the tip by about reach * tilt more than the nominal case
    extra = by_pose[(0.0, 0.0)]["error_max"] - next(
        c for c in base["cells"] if c["pose"] == {"shoulder": 0.0, "elbow": 0.0})["error_max"]
    assert 0.3e-3 < extra < 0.9e-3
    # a folded arm is shorter, so the same tilt costs less
    assert by_pose[(0.0, 1.2)]["error_max"] < by_pose[(0.0, 0.0)]["error_max"]
    assert by_pose[(0.0, 0.0)]["near_singular"] is True  # stretched: singular for position
    assert by_pose[(0.0, 1.2)]["near_singular"] is False
    for q in (-1.0, 1.0):
        direct = verify_pose(m, {"shoulder": q}, tilted)
        cell = by_pose[(q, 0.0)]
        assert cell["error_max"] == pytest.approx(direct["error_max"], rel=0.05, abs=2e-5)
    out = reliability_map(m, {"shoulder": [3.5]}, [nominal])
    assert out["cells"][0]["reachable"] is False
    with pytest.raises(KeyError, match="neither driven nor held"):
        reliability_map(m, {"wrist": [0.0]}, [nominal])


def test_workspace_probability_uses_wilson_only_for_independent_rows(
        reference_model: MechanicalModel) -> None:
    space = VariableSpace.from_model(reference_model.spec)
    rows = [dict(zip(space.names, r.tolist(), strict=True))
            for r in space.design("monte_carlo", 40, 1).values]
    grid = {"shoulder": [0.0, 1.0]}
    a = reliability_map(reference_model, grid, rows, position_tolerance=2.5e-3)
    cell = a["cells"][0]
    assert cell["samples"] == 40 and cell["interval"][0] <= cell["within_tolerance"] \
        <= cell["interval"][1]
    b = reliability_map(reference_model, grid, rows, position_tolerance=2.5e-3,
                        independent_draws=False)
    assert b["cells"][0]["interval"] is None and "not independent" in b["interval_method"]


# ---- root cause ---------------------------------------------------------------------------


def test_root_cause_identifies_the_deliberately_dominant_variable(
        single_joint, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    """Backlash is the only variable that drives the positioning error; payload varies too
    but contributes little. The investigation must rank backlash first by rerun."""
    m = single_joint()
    cfg = ExperimentConfig.model_validate({
        "name": "rc", "task": {"type": "static_hold", "pose": {"j": 0.0}, "duration": 0.8},
        "sampling": {"method": "monte_carlo", "samples": 40, "seed": 2},
        "operating": {"payload_mass": {"type": "uniform", "low": 0.0, "high": 0.02}},
        "constraints": [{"name": "tip_error", "metric": "ee_error_final", "op": "<=",
                         "limit": 0.00265}]})
    exp = Experiment.create(m, cfg, tmp_path / "exp")
    exp.run(m)
    failed = [r for r in exp.results() if not r["passed"]]
    assert 5 < len(failed) < 35
    rc = investigate(exp, failed[0]["id"], m)
    top = rc["contributions"][0]
    assert top["parameter"] == "backlash_tol"
    assert top["counterfactual"]["fixes_failure"] is True
    assert top["counterfactual"]["improvement"] > 0
    assert top["association"]["p_value"] < 0.01
    assert "backlash_tol" in rc["explanation"] and "controlled rerun" in rc["explanation"]
    assert rc["simulations_run"] == 1 + 2 * 2 + 2
    passed = next(r for r in exp.results() if r["passed"])
    with pytest.raises(ValueError, match="passed"):
        investigate(exp, passed["id"], m)


# ---- degradation --------------------------------------------------------------------------


def test_degradation_fit_recovers_known_parameters() -> None:
    """SYNTHETIC wear data: backlash = 0.004 + 2e-9 * cycles, 20 urad noise."""
    rng = np.random.default_rng(0)
    cycles = np.linspace(0, 1e6, 25)
    lin = fit_progression(cycles, 0.004 + 2e-9 * cycles + rng.normal(0, 2e-5, 25), "linear")
    assert lin["rate"] == pytest.approx(2e-9, abs=3 * lin["rate_std_error"])
    assert lin["rate"] == pytest.approx(2e-9, rel=0.05)
    assert lin["initial"] == pytest.approx(0.004, abs=5e-5)
    expo = fit_progression(cycles, 0.05 * np.exp(1.5e-6 * cycles), "exponential")
    assert expo["rate"] == pytest.approx(1.5e-6, rel=1e-6)
    with pytest.raises(ValueError, match="four"):
        fit_progression(cycles[:3], cycles[:3], "linear")


def test_lifetime_projection_crosses_the_requirement_where_expected(single_joint) -> None:  # type: ignore[no-untyped-def]
    """Deflection = (b0 + rate n)/2 + tau/k. With b0 = 4 mrad, rate 2e-9 rad/cycle and a
    limit of 5 mrad on the angle error the crossing is at n = (2 (5e-3 - tau/k) - b0)/rate."""
    b0, rate, k = 0.004, 2e-9, 2000.0
    m = single_joint(backlash=b0, stiffness=k)
    windup = ARM_MASS * G * ARM_LENGTH / k
    limit = 0.005
    expected = (2 * (limit - windup) - b0) / rate
    mech = Mechanism(joint="j", parameter="backlash", kind="linear", rate=rate,
                     rate_std=2e-10, basis="assumed", assumptions="synthetic test progression")
    cons = [Constraint(name="angle", metric="angle_error_final", op="<=", limit=limit)]
    cycles = [0, 250_000, 500_000, 750_000, 1_000_000, 1_500_000, 2_000_000]
    res = lifetime_experiment(m, [mech], cycles, cons, pose={"j": 0.0})
    assert res["label"].startswith("MODEL-BASED PROJECTION")
    assert res["series"][0]["state"]["backlash"] == pytest.approx(b0)
    assert res["series"][-1]["state"]["backlash"] == pytest.approx(b0 + rate * 2e6)
    cross = res["threshold_crossings"]["angle"]["cycles"]
    assert cross == pytest.approx(expected, rel=1e-3)
    band = res["series"][3]["band"]["angle_error_final"]
    assert band[0] < res["series"][3]["metrics"]["angle_error_final"] < band[1]
    plan = compare_maintenance(res, "angle", 200_000)
    assert plan["last_inspection_before_crossing"] == math.floor(expected / 2e5) * 2e5
    # the same projection through Level 2 dynamics agrees
    dyn = lifetime_experiment(m, [mech], [0, 1_000_000, 2_000_000], cons,
                              task=StaticHold(pose={"j": 0.0}, duration=0.8))
    assert dyn["level"] == "L2_reduced_order_dynamics"
    assert dyn["threshold_crossings"]["angle"]["cycles"] == pytest.approx(expected, rel=0.02)
    with pytest.raises(ValueError, match="exactly one"):
        lifetime_experiment(m, [mech], cycles, cons)
