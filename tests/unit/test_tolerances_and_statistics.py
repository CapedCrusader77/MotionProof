"""Units, transforms, distributions, sampling, stacks, gear relations, statistics."""

from __future__ import annotations

import math

import numpy as np
import pytest
from scipy import stats

from motionproof.core import transforms as T
from motionproof.core import units as U
from motionproof.core.schema import (
    Correlation,
    Discrete,
    Empirical,
    LogNormal,
    MechanicalModelSpec,
    Normal,
    TruncatedNormal,
    Uniform,
)
from motionproof.manufacturing.variants import fit_range, nominal_values, resolve_variant
from motionproof.reference.nema17_arm import reference_model_dict
from motionproof.sensitivity import analysis as S
from motionproof.statistics.robustness import replicate_interval, summarise, wilson_interval
from motionproof.tolerances import distributions as D
from motionproof.tolerances.capability import capability, linear_stack, review_tolerances
from motionproof.tolerances.sampling import SamplingError, Variable, VariableSpace
from motionproof.transmissions.gears import (
    backlash_from_centre_distance,
    evaluate_stage,
    planetary_ratio,
)
from motionproof.transmissions.motor import available_torque

N = 200_000
U_GRID = (np.arange(N) + 0.5) / N


# ---- units and transforms ---------------------------------------------------------


def test_unit_factors() -> None:
    assert U.length_factor("mm") == 1e-3
    assert U.convert_length(1.0, "in", "mm") == pytest.approx(25.4)
    assert U.inertia_factor("kg", "cm") == pytest.approx(1e-4)
    assert U.density_factor("g", "cm") == pytest.approx(1000.0)
    assert U.convert_angle(180.0, "deg") == pytest.approx(math.pi)
    with pytest.raises(U.UnitError):
        U.length_factor("furlong")


def test_quaternion_matrix_round_trip() -> None:
    rng = np.random.default_rng(0)
    for _ in range(50):
        q = T.normalize(rng.normal(size=4))
        q = -q if q[0] < 0 else q
        r = T.quat_to_matrix(q)
        assert T.is_rotation(r)
        assert np.allclose(T.matrix_to_quat(r), q, atol=1e-12)


def test_axis_angle_and_quat_product() -> None:
    r = T.axis_angle_matrix([0, 0, 1], math.pi / 2)
    assert np.allclose(r @ [1, 0, 0], [0, 1, 0])
    qa = T.matrix_to_quat(T.axis_angle_matrix([1, 0, 0], 0.3))
    qb = T.matrix_to_quat(T.axis_angle_matrix([0, 1, 0], -0.7))
    assert np.allclose(T.quat_to_matrix(T.quat_multiply(qa, qb)),
                       T.quat_to_matrix(qa) @ T.quat_to_matrix(qb))


def test_transform_inverse_and_parallel_axis() -> None:
    t = T.make_transform(T.axis_angle_matrix([1, 2, 3], 0.9), [0.1, -0.2, 0.3])
    assert np.allclose(T.invert_transform(t) @ t, np.eye(4), atol=1e-12)
    # two equal point masses 2a apart: I about the midpoint = 2 m a^2 on the transverse axes
    m, a = 1.5, 0.2
    total, com, inertia = T.combine_inertias([
        (m, np.array([a, 0, 0]), np.zeros((3, 3))), (m, np.array([-a, 0, 0]), np.zeros((3, 3)))])
    assert total == 3.0 and np.allclose(com, 0)
    assert np.allclose(np.diag(inertia), [0, 2 * m * a * a, 2 * m * a * a])
    assert T.inertia_is_physical(np.diag([1.0, 1.0, 1.5]))
    assert not T.inertia_is_physical(np.diag([1.0, 1.0, 2.5]))  # violates triangle inequality


# ---- distributions -------------------------------------------------------------------


def test_normal_and_uniform_moments() -> None:
    x = D.ppf(Normal(mean=10.0, std=0.02), U_GRID)
    assert x.mean() == pytest.approx(10.0, abs=1e-6) and x.std() == pytest.approx(0.02, rel=1e-3)
    x = D.ppf(Uniform(low=1.0, high=3.0), U_GRID)
    assert x.min() >= 1.0 and x.max() <= 3.0
    assert x.std() == pytest.approx(2 / math.sqrt(12), rel=1e-4)


def test_truncated_normal_respects_limits_and_matches_scipy() -> None:
    d = TruncatedNormal(mean=0.0, std=1.0, low=-0.5, high=2.0)
    x = D.ppf(d, U_GRID)
    assert x.min() >= -0.5 and x.max() <= 2.0
    mean, std = D.mean_std(d)
    assert mean == pytest.approx(stats.truncnorm.mean(-0.5, 2.0), rel=1e-9)
    assert x.std() == pytest.approx(std, rel=2e-3)
    assert D.bounds(d) == (-0.5, 2.0)


def test_lognormal_discrete_empirical() -> None:
    assert D.ppf(LogNormal(mu=0.0, sigma=0.5), [0.5])[0] == pytest.approx(1.0)
    x = D.ppf(Discrete(values=[1.0, 2.0, 5.0], probabilities=[0.2, 0.5, 0.3]), U_GRID)
    assert [round(float(np.mean(x == v)), 3) for v in (1.0, 2.0, 5.0)] == [0.2, 0.5, 0.3]
    samples = [9.98, 10.0, 10.01, 10.03, 10.02]
    x = D.ppf(Empirical(samples=samples), U_GRID)
    assert x.min() >= min(samples) and x.max() <= max(samples)
    assert D.validate(Discrete(values=[1.0, 2.0], probabilities=[0.5, 0.6]))
    assert D.validate(Uniform(low=2.0, high=1.0))


def test_fraction_outside_matches_normal_tail() -> None:
    frac = D.fraction_outside(Normal(mean=0.0, std=1.0), -2.0, 2.0)
    assert frac == pytest.approx(2 * stats.norm.cdf(-2.0), rel=2e-3)


# ---- sampling -----------------------------------------------------------------------


def _space(corr: float | None = None) -> VariableSpace:
    variables = [Variable("a", Normal(mean=0.0, std=1.0), 0.0, "tolerance"),
                 Variable("b", Uniform(low=0.0, high=1.0), 0.5, "tolerance"),
                 Variable("c", Normal(mean=5.0, std=2.0), 5.0, "tolerance")]
    cors = [Correlation(parameters=("a", "c"), coefficient=corr, basis="assumed")] if corr else []
    return VariableSpace(variables, cors)


def test_designs_are_reproducible_and_seed_dependent() -> None:
    sp = _space()
    for method in ("monte_carlo", "latin_hypercube", "sobol"):
        a, b = sp.design(method, 64, 7), sp.design(method, 64, 7)  # type: ignore[arg-type]
        assert np.array_equal(a.values, b.values)
        assert not np.array_equal(a.values, sp.design(method, 64, 8).values)  # type: ignore[arg-type]
    assert sp.design("monte_carlo", 8, 0).independent
    assert not sp.design("latin_hypercube", 8, 0).independent


def test_latin_hypercube_stratifies_each_margin() -> None:
    n = 50
    x = _space().design("latin_hypercube", n, 3).values
    strata = np.floor(x[:, 1] * n).astype(int)  # variable b is U(0, 1)
    assert sorted(strata) == list(range(n))


def test_gaussian_copula_reproduces_correlation_and_margins() -> None:
    x = _space(0.7).design("monte_carlo", 40_000, 1).values
    assert np.corrcoef(x[:, 0], x[:, 2])[0, 1] == pytest.approx(0.7, abs=0.01)
    assert abs(np.corrcoef(x[:, 0], x[:, 1])[0, 1]) < 0.02
    assert x[:, 2].mean() == pytest.approx(5.0, abs=0.03)
    assert x[:, 2].std() == pytest.approx(2.0, rel=0.02)


def test_inconsistent_correlations_are_rejected() -> None:
    v = [Variable(n, Normal(mean=0.0, std=1.0), 0.0, "tolerance") for n in "abc"]
    cors = [Correlation(parameters=("a", "b"), coefficient=0.95, basis="assumed"),
            Correlation(parameters=("b", "c"), coefficient=0.95, basis="assumed"),
            Correlation(parameters=("a", "c"), coefficient=-0.95, basis="assumed")]
    with pytest.raises(SamplingError, match="positive definite"):
        VariableSpace(v, cors)


def test_boundary_and_corner_designs() -> None:
    sp = _space()
    b = sp.design("boundary", 0, 0).values
    assert len(b) == 2 * sp.dim + 1 and np.array_equal(b[0], sp.nominal())
    c = sp.design("corners", 8, 0).values
    assert len(np.unique(c, axis=0)) == 8
    lo, hi = sp.bounds().T
    assert np.all((c == lo) | (c == hi))


# ---- stacks, capability, fits ---------------------------------------------------------


def test_linear_stack_against_monte_carlo() -> None:
    """Gap = housing - a - b: worst case is the sum of half-widths, RSS the root sum."""
    terms = [(1.0, 0.05, 0.05 / 3), (-1.0, 0.03, 0.01), (-1.0, 0.04, 0.04 / 3)]
    res = linear_stack(terms)
    assert res["worst_case"] == pytest.approx(0.12)
    rng = np.random.default_rng(0)
    y = sum(a * rng.normal(0.0, s, 400_000) for a, _, s in terms)
    assert res["rss_sigma"] == pytest.approx(float(np.std(y)), rel=5e-3)


def _ref_spec() -> MechanicalModelSpec:
    return MechanicalModelSpec.model_validate(reference_model_dict())


def test_capability_indices() -> None:
    raw = reference_model_dict()
    t = next(t for t in raw["tolerances"] if t["id"] == "housing_seat_diameter")
    t["process"] = {"mean": 22.0105, "std": 0.0035, "sample_size": 12, "basis": "measured"}
    spec = MechanicalModelSpec.model_validate(raw)
    cap = capability(spec.tolerance("housing_seat_diameter"))
    assert cap is not None
    assert cap.cp == pytest.approx(0.021 / (6 * 0.0035))
    assert cap.cpk == pytest.approx(0.0105 / (3 * 0.0035))
    assert any("12 measurements" in w for w in cap.warnings)
    assert capability(spec.tolerance("output_shaft_diameter")) is None


def test_fit_classes_and_nominal_design_value() -> None:
    spec = _ref_spec()
    ranges = {f.id: fit_range(f, spec) for f in spec.fits}
    # shaft 8 (-0.005/-0.014) in bore 8 (0/-0.008): -0.003 .. +0.014 -> transition fit
    assert ranges["shaft_in_bearing"]["min_clearance"] == pytest.approx(-0.003)
    assert ranges["shaft_in_bearing"]["max_clearance"] == pytest.approx(0.014)
    assert ranges["shaft_in_bearing"]["class"] == "transition"
    assert ranges["bearing_in_housing"]["class"] == "clearance"
    # regression: a nominal size outside its own limits must not make the nominal assembly
    # out of specification
    nominal = resolve_variant(spec, nominal_values(spec))
    assert nominal.out_of_spec == [] and nominal.violations == []


def test_review_flags_assumed_and_unbound_tolerances() -> None:
    raw = reference_model_dict()
    raw["tolerances"].append({
        "id": "orphan", "component": "housing", "parameter": "flatness",
        "characteristic": "flatness", "category": "geometric", "nominal": 0.0, "lower": 0.0,
        "upper": 0.02, "unit": "mm", "distribution": {"type": "uniform", "low": 0, "high": 0.02},
        "source": "test", "confidence": "specified"})
    findings = review_tolerances(MechanicalModelSpec.model_validate(raw))
    assert any(f["tolerance"] == "orphan" and "no propagation model" in f["message"]
               for f in findings)
    assert any("assumed" in f["message"] for f in findings)


def test_schema_rejects_dangling_references() -> None:
    raw = reference_model_dict()
    raw["fits"][0]["shaft"] = "does_not_exist"
    with pytest.raises(ValueError, match="unknown tolerance"):
        MechanicalModelSpec.model_validate(raw)


# ---- gears and motor ------------------------------------------------------------------


def test_reference_gearbox_ratio_is_33() -> None:
    spec = _ref_spec()
    ratios = [s.ratio for s in spec.gear_stages]
    assert ratios == [5.5, 6.0]
    assert math.prod(ratios) == pytest.approx(spec.drives["shoulder"].gearbox.ratio)
    assert planetary_ratio(12, 60) == 6.0


def test_backlash_from_centre_distance() -> None:
    assert backlash_from_centre_distance(0.01, 20.0) == pytest.approx(
        2 * math.tan(math.radians(20)) * 0.01)
    assert backlash_from_centre_distance(0.01, 20.0, internal=True) < 0


def test_stage_backlash_formula_and_radial_cancellation() -> None:
    spec = _ref_spec()
    vals = nominal_values(spec)
    st = next(s for s in spec.gear_stages if s.id == "stage2")
    base = evaluate_stage(st, spec, vals)
    # (0.04 + 0.04) / 2 + 0.012 mm of free travel on a 9 mm pin circle
    assert base.backlash_angle == pytest.approx(0.052 / 9.0)
    # moving every pin outward loosens the sun mesh and tightens the ring mesh equally:
    # the lost motion is unchanged, but the ring mesh loses backlash
    moved = evaluate_stage(st, spec, vals | {f"s2_pin_radial_{k}": 0.02 for k in range(3)})
    assert moved.backlash_angle == pytest.approx(base.backlash_angle)
    assert moved.min_mesh_backlash_mm == pytest.approx(
        0.04 - 2 * math.tan(math.radians(20)) * 0.02)
    assert not moved.binding
    assert evaluate_stage(st, spec, vals | {"s2_pin_radial_1": 0.06}).binding



def test_pin_clearance_and_sun_coupling_play_add_lost_motion() -> None:
    """Pin clearance in the carrier adds to the planets' free travel like bearing clearance;
    torsional play at the sun appears at the carrier divided by the stage ratio."""
    from motionproof.core.schema import MechanicalModelSpec, Tolerance

    spec = _ref_spec()
    vals = nominal_values(spec)
    st = next(s for s in spec.gear_stages if s.id == "stage2")
    base = evaluate_stage(st, spec, vals).backlash_angle

    def tol(tid: str, value: float, unit: str) -> Tolerance:
        return Tolerance.model_validate({
            "id": tid, "component": "stage2", "parameter": tid, "characteristic": "radial_clearance" if unit == "mm" else "backlash",
            "category": "assembly", "nominal": value, "lower": 0.0, "upper": 2 * value,
            "unit": unit, "distribution": {"type": "uniform", "low": 0.0, "high": 2 * value},
            "source": "test", "confidence": "assumed"})

    data = spec.model_dump(mode="json", by_alias=True)
    data["tolerances"] += [tol("pin_fit", 0.03, "mm").model_dump(mode="json", by_alias=True),
                           tol("sun_key", 0.6, "deg").model_dump(mode="json", by_alias=True)]
    for g in data["gear_stages"]:
        if g["id"] == "stage2":
            g["inputs"] |= {"carrier_pin_clearance": "pin_fit", "sun_coupling_play": "sun_key"}
    spec2 = MechanicalModelSpec.model_validate(data)
    st2 = next(s for s in spec2.gear_stages if s.id == "stage2")
    vals2 = nominal_values(spec2)
    got = evaluate_stage(st2, spec2, vals2).backlash_angle
    assert got == pytest.approx(base + 0.03 / st2.centre_distance + math.radians(0.6) / st2.ratio)
    zero = evaluate_stage(st2, spec2, vals2 | {"pin_fit": 0.0, "sun_key": 0.0}).backlash_angle
    assert zero == pytest.approx(base)

def test_total_backlash_reflects_stage_one_through_stage_two() -> None:
    spec = _ref_spec()
    v = resolve_variant(spec, nominal_values(spec))
    s1, s2 = (next(s for s in v.stages if s.stage == n) for n in ("stage1", "stage2"))
    assert v.joints["shoulder"].backlash == pytest.approx(
        s2.backlash_angle + s1.backlash_angle / 6.0)


def test_radial_play_adds_clearances_and_tilts_axis() -> None:
    spec = _ref_spec()
    vals = nominal_values(spec) | {"output_shaft_diameter": 7.990, "bearing_bore_diameter": 7.998,
                                   "bearing_outer_diameter": 21.995,
                                   "housing_seat_diameter": 22.010,
                                   "bearing_internal_clearance": 0.010,
                                   "joint_axis_misalignment": 0.0}
    j = resolve_variant(spec, vals).joints["shoulder"]
    play = (0.008 + 0.015 + 0.010) * 1e-3
    assert j.radial_play == pytest.approx(play)
    assert j.tilt_y == pytest.approx(play / 0.015)
    assert j.offset[2] == pytest.approx(-play / 2)


def test_motor_torque_speed_curve() -> None:
    motor = _ref_spec().drives["shoulder"].motor
    assert available_torque(motor, 0.0) == pytest.approx(0.45)
    assert available_torque(motor, -47.1) == pytest.approx(0.34)  # midway 31.4 .. 62.8
    assert available_torque(motor, 200.0) == 0.0
    assert available_torque(motor, 0.0, scale=0.9) == pytest.approx(0.405)


# ---- statistics -----------------------------------------------------------------------


def test_wilson_interval_reference_values() -> None:
    lo, hi = wilson_interval(8, 10)
    assert (lo, hi) == pytest.approx((0.4902, 0.9433), abs=5e-4)  # textbook value
    lo, hi = wilson_interval(100, 100)
    assert hi == 1.0 and lo == pytest.approx(0.9630, abs=5e-4)
    assert wilson_interval(0, 50)[0] == 0.0


def test_replicate_interval() -> None:
    lo, hi = replicate_interval([0.90, 0.92, 0.94, 0.92])
    half = stats.t.ppf(0.975, 3) * np.std([0.90, 0.92, 0.94, 0.92], ddof=1) / 2
    assert (lo, hi) == pytest.approx((0.92 - half, 0.92 + half))


def _manifest(method: str, independent: bool, replicates: int = 1) -> dict:
    return {"config": {"sampling": {"method": method, "replicates": replicates},
                       "constraints": [{"name": "c", "metric": "m", "op": "<=", "limit": 1.0}]},
            "design": {"independent": independent, "values": [[0]] * 40, "notes": []},
            "model": {"fidelity": "F2"}}


def _results(n: int, fail_every: int, replicates: int = 1) -> list[dict]:
    out = []
    for i in range(n):
        ok = (i % fail_every) != fail_every - 1
        out.append({"valid": True, "passed": ok, "replicate": i % replicates, "out_of_spec": [],
                    "metrics": {"m": 0.5 if ok else 1.5},
                    "constraints": {"c": {"passed": ok, "margin": 0.5 if ok else -0.5}},
                    "failures": [] if ok else [{"category": "positioning"}]})
    return out


def test_summary_uses_method_appropriate_intervals() -> None:
    mc = summarise(_manifest("monte_carlo", True), _results(40, 4))
    assert mc["all_constraints"]["interval_method"].startswith("Wilson")
    assert mc["failure_categories"] == {"positioning": 10}
    lhs = summarise(_manifest("latin_hypercube", False), _results(40, 4))
    assert lhs["all_constraints"]["interval"] is None
    assert "not independent" in lhs["all_constraints"]["note"]
    rep = summarise(_manifest("latin_hypercube", False, 4), _results(40, 5, 4))
    assert rep["all_constraints"]["interval_method"].startswith("Student-t over 4")
    probe = summarise(_manifest("corners", False), _results(40, 4))
    assert probe["all_constraints"]["pass_fraction"] is None


def test_zero_failures_is_not_reported_as_certainty() -> None:
    s = summarise(_manifest("monte_carlo", True), _results(40, 10**9))
    a = s["all_constraints"]
    assert a["failed"] == 0 and a["interval"][0] < 1.0
    assert "does not mean zero failure probability" in a["note"]


# ---- sensitivity ----------------------------------------------------------------------


def test_sensitivity_recovers_known_linear_model() -> None:
    rng = np.random.default_rng(0)
    x = rng.normal(size=(600, 4))
    y = 3.0 * x[:, 0] - 1.0 * x[:, 1] + 0.05 * rng.normal(size=600)
    names = ["big", "small", "none", "constant"]
    x[:, 3] = 1.0
    rows = S.rank_correlation(names, x, y)
    assert [r["parameter"] for r in rows[:2]] == ["big", "small"]
    assert rows[0]["direction"] == "increases" and rows[1]["direction"] == "decreases"
    by = {r["parameter"]: r for r in rows}
    assert by["none"]["direction"] == "not distinguishable from zero"
    assert by["constant"]["note"] == "no variation"
    reg = S.regression_decomposition(names, x, y)
    assert reg["r_squared"] > 0.99
    src = {c["parameter"]: c["src_squared"] for c in reg["coefficients"]}
    assert src["big"] == pytest.approx(0.9, abs=0.02) and src["small"] == pytest.approx(
        0.1, abs=0.02)


def test_interaction_screen_finds_product_term() -> None:
    rng = np.random.default_rng(1)
    x = rng.normal(size=(800, 3))
    y = x[:, 0] + x[:, 1] + 2.0 * x[:, 0] * x[:, 1]
    res = S.interaction_screen(["a", "b", "c"], x, y)
    assert set(res["pairs"][0]["parameters"]) == {"a", "b"}
    assert res["r_squared_with_pairs"] > res["r_squared_linear"] + 0.3


def test_one_at_a_time_and_sobol_on_analytic_function() -> None:
    sp = VariableSpace([Variable(n, Uniform(low=-1.0, high=1.0), 0.0, "tolerance")
                        for n in ("x1", "x2", "x3")])

    def f(row: dict[str, float]) -> float:
        return 4.0 * row["x1"] + 1.0 * row["x2"]

    oat = S.one_at_a_time(sp, f)
    assert [r["parameter"] for r in oat] == ["x1", "x2", "x3"]
    assert oat[0]["swing"] == pytest.approx(8.0) and oat[2]["swing"] == 0.0
    sob = S.sobol(sp, f, n=256, seed=0)
    idx = {r["parameter"]: r for r in sob["indices"]}
    # additive model: S1 = a_i^2 / sum(a^2) = 16/17 and 1/17, no interactions
    assert idx["x1"]["first_order"] == pytest.approx(16 / 17, abs=0.05)
    assert idx["x2"]["first_order"] == pytest.approx(1 / 17, abs=0.05)
    assert abs(idx["x3"]["total_order"]) < 0.02
    assert sob["evaluations"] == 256 * 5
