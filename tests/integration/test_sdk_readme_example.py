"""The SDK example printed in README.md must run against the real implementation."""

from __future__ import annotations

from motionproof.experiments import ManufacturingExperiment
from motionproof.model import MechanicalModel
from motionproof.uncertainty import Uniform


def test_readme_sdk_example(reference_model: MechanicalModel) -> None:
    experiment = ManufacturingExperiment(
        model=reference_model,
        task={"type": "reversal", "joint": "shoulder", "target": {"shoulder": 1.5708}},
        samples=16,
        seed=42,
    )
    experiment.add_operating_variation("payload_mass", Uniform(0.0, 0.5))
    experiment.add_constraint("lost_motion", "<=", 0.0065)
    results = experiment.run()
    assert results.performance["lost_motion"]["max"] > 0
    assert results.failure_estimate["n"] == 16
    assert results.failure_estimate["interval_method"].startswith("Wilson")
    assert len(results.sensitivity("lost_motion")) == len(experiment.model.spec.tolerances) + 1
