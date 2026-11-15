"""Distribution constructors for the Python SDK: ``from motionproof.uncertainty import Normal``."""

from motionproof.core.schema import Discrete as _Discrete
from motionproof.core.schema import Distribution
from motionproof.core.schema import Empirical as _Empirical
from motionproof.core.schema import LogNormal as _LogNormal
from motionproof.core.schema import Normal as _Normal
from motionproof.core.schema import TruncatedNormal as _TruncatedNormal
from motionproof.core.schema import Uniform as _Uniform


def Normal(mean: float, std: float) -> Distribution:  # noqa: N802
    return _Normal(mean=mean, std=std)


def Uniform(low: float, high: float) -> Distribution:  # noqa: N802
    return _Uniform(low=low, high=high)


def TruncatedNormal(mean: float, std: float, low: float, high: float) -> Distribution:  # noqa: N802
    return _TruncatedNormal(mean=mean, std=std, low=low, high=high)


def LogNormal(mu: float, sigma: float) -> Distribution:  # noqa: N802
    return _LogNormal(mu=mu, sigma=sigma)


def Discrete(values: list[float], probabilities: list[float] | None = None) -> Distribution:  # noqa: N802
    return _Discrete(values=values, probabilities=probabilities)


def Empirical(samples: list[float]) -> Distribution:  # noqa: N802
    return _Empirical(samples=samples)


__all__ = ["Discrete", "Distribution", "Empirical", "LogNormal", "Normal", "TruncatedNormal",
           "Uniform"]
