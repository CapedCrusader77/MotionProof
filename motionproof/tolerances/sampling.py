"""Experiment variable space and sampling designs.

A ``VariableSpace`` holds named scalar variables (tolerances and operating conditions), their
distributions and an optional correlation matrix applied through a Gaussian copula. Every
design is generated from an explicit seed; nothing depends on global random state.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np
from numpy.typing import NDArray
from scipy import stats
from scipy.stats import qmc

from motionproof.core.schema import Correlation, Distribution, MechanicalModelSpec, Tolerance
from motionproof.tolerances import distributions as D

Arr = NDArray[np.float64]
SamplingMethod = Literal["monte_carlo", "latin_hypercube", "sobol", "boundary", "corners"]
MAX_CORNER_DIMS = 12


def design_value(tol: Tolerance) -> float:
    """Value used for the nominal assembly.

    The nominal size when it lies inside the limits, otherwise the middle of the tolerance
    zone (an 8 g6 shaft is never exactly 8.000).
    """
    if tol.lower_limit <= tol.nominal <= tol.upper_limit:
        return tol.nominal
    return (tol.lower_limit + tol.upper_limit) / 2.0


class SamplingError(ValueError):
    pass


@dataclass
class Variable:
    name: str
    distribution: Distribution
    nominal: float
    kind: Literal["tolerance", "operating"]
    unit: str = ""


@dataclass
class Design:
    method: str
    seed: int
    names: list[str]
    values: Arr  # (n, d) physical values
    independent: bool  # True when rows are independent random draws
    note: str = ""


class VariableSpace:
    def __init__(self, variables: list[Variable], correlations: list[Correlation] | None = None):
        names = [v.name for v in variables]
        if len(set(names)) != len(names):
            raise SamplingError("variable names must be unique")
        for v in variables:
            problems = D.validate(v.distribution)
            if problems:
                raise SamplingError(f"variable {v.name!r}: {'; '.join(problems)}")
        self.variables = variables
        self.names = names
        self.correlation = self._matrix(correlations or [])
        self._chol = None if self.correlation is None else np.linalg.cholesky(self.correlation)

    @classmethod
    def from_model(
        cls, spec: MechanicalModelSpec, operating: dict[str, Distribution] | None = None
    ) -> VariableSpace:
        variables = [
            Variable(t.id, t.distribution, design_value(t), "tolerance", t.unit)
            for t in spec.tolerances
        ]
        for name, dist in (operating or {}).items():
            variables.append(Variable(f"op.{name}", dist, D.mean_std(dist)[0], "operating"))
        return cls(variables, spec.correlations)

    def _matrix(self, correlations: list[Correlation]) -> Arr | None:
        used = [c for c in correlations if set(c.parameters) <= set(self.names)]
        if not used:
            return None
        n = len(self.names)
        m = np.eye(n)
        for c in used:
            i, j = (self.names.index(p) for p in c.parameters)
            if i == j:
                raise SamplingError("a variable cannot be correlated with itself")
            m[i, j] = m[j, i] = c.coefficient
        if np.linalg.eigvalsh(m).min() <= 1e-10:
            raise SamplingError(
                "correlation matrix is not positive definite; the specified pairwise "
                "coefficients are mutually inconsistent"
            )
        return m

    @property
    def dim(self) -> int:
        return len(self.variables)

    def nominal(self) -> Arr:
        return np.array([v.nominal for v in self.variables])

    def bounds(self) -> Arr:
        return np.array([D.bounds(v.distribution) for v in self.variables])

    def transform(self, u: Arr) -> Arr:
        """Map independent uniforms (n, d) to physical values, applying the copula."""
        u = np.atleast_2d(np.asarray(u, dtype=float))
        if self._chol is not None:
            z = stats.norm.ppf(np.clip(u, 1e-12, 1 - 1e-12)) @ self._chol.T
            u = stats.norm.cdf(z)
        return np.column_stack(
            [D.ppf(v.distribution, u[:, i]) for i, v in enumerate(self.variables)]
        )

    def design(self, method: SamplingMethod, n: int, seed: int) -> Design:
        d = self.dim
        if d == 0:
            raise SamplingError("the variable space is empty: define at least one tolerance")
        if method == "monte_carlo":
            u = np.random.default_rng(seed).random((n, d))
            return Design(method, seed, self.names, self.transform(u), True)
        if method == "latin_hypercube":
            u = qmc.LatinHypercube(d=d, seed=seed).random(n)
            return Design(method, seed, self.names, self.transform(u), False,
                          "stratified design: rows are not independent draws")
        if method == "sobol":
            u = qmc.Sobol(d=d, scramble=True, seed=seed).random(n)
            return Design(method, seed, self.names, self.transform(u), False,
                          "scrambled Sobol sequence: rows are not independent draws")
        lo, hi = self.bounds().T
        nom = self.nominal()
        if method == "boundary":
            rows = [nom.copy()]
            for i in range(d):
                for edge in (lo[i], hi[i]):
                    r = nom.copy()
                    r[i] = edge
                    rows.append(r)
            return Design(method, seed, self.names, np.array(rows), False,
                          "nominal plus each variable at its lower and upper bound")
        if method == "corners":
            if d <= MAX_CORNER_DIMS and 2**d <= max(n, 1):
                bits = (np.arange(2**d)[:, None] >> np.arange(d)) & 1
                note = f"all {2**d} bound combinations"
            else:
                bits = np.random.default_rng(seed).integers(0, 2, size=(n, d))
                note = f"{n} seeded random bound combinations out of 2^{d}"
            return Design(method, seed, self.names, np.where(bits == 1, hi, lo), False, note)
        raise SamplingError(f"unknown sampling method {method!r}")
