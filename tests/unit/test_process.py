"""Process-aware manufacturing: synthetic batches from known hierarchical models."""

from __future__ import annotations

import numpy as np
import pytest

from motionproof.process.model import (
    BatchPlan,
    ProcessModel,
    batch_summary,
    control_chart,
    fit_linear_drift,
    generate_batch,
    variance_components,
)

BATCH, SETUP, PART = 0.010, 0.006, 0.004


def _model(shared: bool, drift: dict | None = None) -> ProcessModel:
    def feature(name: str, target: float) -> dict:
        return {"feature": name, "process": "CNC turning", "target": target, "unit": "mm",
                "lower_limit": target - 0.05, "upper_limit": target + 0.05,
                "sources": [
                    {"level": "batch", "std": BATCH, "basis": "specified"},
                    {"level": "setup", "std": SETUP, "basis": "specified",
                     "shared_group": "fixture_1" if shared else None},
                    {"level": "part", "std": PART, "basis": "specified"}],
                "drift": drift or {"kind": "none"}}
    return ProcessModel.model_validate({"name": "test", "features": [
        feature("bore", 10.02), feature("shaft", 10.00)]})


def test_variance_components_are_recovered() -> None:
    """Known components 10 / 6 / 4 um. 200 batches x 6 setups x 8 parts.
    Accepted error: 12 % on batch (200 samples of it), 8 % on setup, 3 % on part."""
    b = generate_batch(_model(False), BatchPlan(batches=200, setups_per_batch=6,
                                                parts_per_setup=8, seed=1))
    vc = variance_components(b["actual"]["bore"], b["batch"], b["setup"])
    assert vc["batch_std"] == pytest.approx(BATCH, rel=0.12)
    assert vc["setup_std"] == pytest.approx(SETUP, rel=0.08)
    assert vc["part_std"] == pytest.approx(PART, rel=0.03)
    assert vc["mean"] == pytest.approx(10.02, abs=0.002)
    s = batch_summary(_model(False), b)["bore"]
    total = np.sqrt(BATCH**2 + SETUP**2 + PART**2)
    assert s["std"] == pytest.approx(total, rel=0.08)
    assert s["cp"] == pytest.approx(0.1 / (6 * total), rel=0.08)


def test_shared_setup_error_cancels_in_the_clearance() -> None:
    """Clearance = bore - shaft. Independent setups: var = 2 (b^2 + s^2 + p^2).
    A shared setup error is common to both features and cancels: var = 2 (b^2 + p^2)."""
    plan = BatchPlan(batches=300, setups_per_batch=5, parts_per_setup=10, seed=3)
    out = {}
    for shared in (False, True):
        b = generate_batch(_model(shared), plan)
        out[shared] = b["actual"]["bore"] - b["actual"]["shaft"]
        corr = np.corrcoef(b["actual"]["bore"], b["actual"]["shaft"])[0, 1]
        expected = SETUP**2 / (BATCH**2 + SETUP**2 + PART**2) if shared else 0.0
        assert corr == pytest.approx(expected, abs=0.05)
    assert out[False].std() == pytest.approx(np.sqrt(2 * (BATCH**2 + SETUP**2 + PART**2)),
                                             rel=0.06)
    assert out[True].std() == pytest.approx(np.sqrt(2 * (BATCH**2 + PART**2)), rel=0.06)
    assert out[True].mean() == pytest.approx(0.02, abs=0.002)


def test_disabled_source_contributes_nothing() -> None:
    m = _model(False)
    for f in m.features:
        for s in f.sources:
            s.enabled = s.level == "part"
    b = generate_batch(m, BatchPlan(batches=20, setups_per_batch=5, parts_per_setup=50, seed=0))
    assert b["actual"]["bore"].std() == pytest.approx(PART, rel=0.05)


def test_tool_wear_drift_is_recovered_and_flagged() -> None:
    rate = 2e-5  # mm per part
    m = ProcessModel.model_validate({"name": "wear", "features": [{
        "feature": "bore", "process": "reaming", "target": 10.0, "unit": "mm",
        "lower_limit": 9.97, "upper_limit": 10.03,
        "sources": [{"level": "part", "std": 0.002, "basis": "specified"},
                    {"level": "measurement", "std": 0.001, "basis": "specified"}],
        "drift": {"kind": "linear", "rate": rate, "basis": "specified"}}]})
    b = generate_batch(m, BatchPlan(parts_per_setup=1000, tool_life_parts=500, seed=2))
    first_tool = b["measured"]["bore"][:500]
    fit = fit_linear_drift(first_tool)
    assert fit["rate"] == pytest.approx(rate, abs=3 * fit["rate_std_error"])
    assert fit["rate"] == pytest.approx(rate, rel=0.1)
    # the tool change resets the drift
    assert b["actual"]["bore"][500:520].mean() == pytest.approx(10.0, abs=0.002)
    chart = control_chart(first_tool, 5)
    assert any("trend" in s for s in chart["signals"])
    assert "not in statistical control" in chart["statement"]
    # measurement noise is in the measured values only
    assert np.std(b["measured"]["bore"] - b["actual"]["bore"]) == pytest.approx(0.001, rel=0.1)


def test_stable_process_gives_no_signal_but_no_stability_claim() -> None:
    x = np.random.default_rng(5).normal(10.0, 0.003, 250)
    chart = control_chart(x, 5)
    assert chart["signals"] == []
    assert "does not establish" in chart["statement"]
    assert chart["sigma_within"] == pytest.approx(0.003, rel=0.1)


def test_piecewise_drift_and_validation() -> None:
    m = ProcessModel.model_validate({"name": "pw", "features": [{
        "feature": "d", "process": "grinding", "target": 5.0, "unit": "mm", "lower_limit": 4.9,
        "upper_limit": 5.1, "sources": [{"level": "part", "std": 0.0, "basis": "assumed"}],
        "drift": {"kind": "piecewise", "breakpoints": [[0, 0.0], [100, 0.01], [200, 0.01]]}}]})
    b = generate_batch(m, BatchPlan(parts_per_setup=200))
    assert b["actual"]["d"][50] == pytest.approx(5.005)
    assert b["actual"]["d"][150] == pytest.approx(5.01)
    with pytest.raises(ValueError, match="balanced"):
        groups = np.array([0, 0, 0, 1, 1, 1, 1])  # unequal group sizes
        variance_components(np.arange(7.0), groups, groups)
    with pytest.raises(ValueError, match="once"):
        ProcessModel.model_validate({"name": "dup", "features": [
            m.features[0].model_dump(), m.features[0].model_dump()]})
