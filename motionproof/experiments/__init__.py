"""Experiment SDK: ``ManufacturingExperiment`` is the programmatic front door."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any, Literal

from motionproof.core.schema import Distribution
from motionproof.experiments.runner import (
    Constraint,
    Experiment,
    ExperimentConfig,
    ExperimentError,
    Sampling,
)
from motionproof.model import MechanicalModel
from motionproof.sensitivity.analysis import rank_correlation
from motionproof.statistics.robustness import summarise
from motionproof.tolerances.sampling import SamplingMethod


class ExperimentResults:
    """Results of a finished experiment."""

    def __init__(self, experiment: Experiment):
        self.experiment = experiment
        self.scenarios = experiment.results()
        self.summary = summarise(experiment.manifest, self.scenarios)

    @property
    def performance(self) -> dict[str, dict[str, float]]:
        """Distribution statistics of every metric over the valid scenarios."""
        out: dict[str, dict[str, float]] = self.summary["metrics"]
        return out

    @property
    def failure_estimate(self) -> dict[str, Any]:
        """Pass/fail counts and the interval appropriate to the sampling design."""
        out: dict[str, Any] = self.summary["all_constraints"]
        return out

    def sensitivity(self, metric: str) -> list[dict[str, Any]]:
        """Spearman rank correlation of ``metric`` with every variable (association only)."""
        x, metrics, _ = self.experiment.metric_matrix()
        return rank_correlation(self.experiment.names, x, metrics[metric])


class ManufacturingExperiment:
    """Build and run a virtual manufacturing experiment from Python."""

    def __init__(self, model: MechanicalModel, task: dict[str, Any], samples: int = 100,
                 seed: int = 0, method: SamplingMethod = "monte_carlo", replicates: int = 1,
                 name: str = "experiment"):
        self.model = model
        self._task = task
        self._sampling = Sampling(method=method, samples=samples, seed=seed,
                                  replicates=replicates)
        self._name = name
        self._operating: dict[str, Distribution] = {}
        self._constraints: list[Constraint] = []
        self._fixed: dict[str, float] = {}

    def add_operating_variation(self, parameter: str, distribution: Distribution) -> None:
        """Vary an operating condition (``payload_mass`` or ``speed_scale``)."""
        self._operating[parameter] = distribution

    def fix(self, tolerance: str, value: float) -> None:
        """Pin one tolerance to a value for every scenario."""
        self._fixed[tolerance] = value

    def add_constraint(self, metric: str, op: Literal["<=", ">="], limit: float,
                       name: str | None = None) -> None:
        self._constraints.append(Constraint(name=name or metric, metric=metric, op=op,
                                            limit=limit))

    def run(self, directory: str | Path | None = None) -> ExperimentResults:
        """Run every scenario. Results are stored in ``directory`` (a new temporary folder
        when omitted) and can be reopened with ``Experiment.open``."""
        config = ExperimentConfig.model_validate({
            "name": self._name, "task": self._task,
            "sampling": self._sampling.model_dump(),
            "operating": {k: v.model_dump() for k, v in self._operating.items()},
            "constraints": [c.model_dump() for c in self._constraints],
            "fixed": self._fixed})
        out = Path(directory) if directory else Path(tempfile.mkdtemp(prefix="motionproof_exp_"))
        experiment = Experiment.create(self.model, config, out)
        experiment.run(self.model)
        return ExperimentResults(experiment)


__all__ = ["Constraint", "Experiment", "ExperimentConfig", "ExperimentError",
           "ExperimentResults", "ManufacturingExperiment", "Sampling"]
