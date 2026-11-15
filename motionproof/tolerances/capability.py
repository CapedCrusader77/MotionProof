"""Process capability, specification checks and linear tolerance stacks."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

import numpy as np

from motionproof.core.schema import UNPROPAGATED, Confidence, MechanicalModelSpec, Tolerance
from motionproof.tolerances import distributions as D


@dataclass
class Capability:
    tolerance: str
    cp: float
    cpk: float
    basis: str
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def capability(tol: Tolerance) -> Capability | None:
    """Cp and Cpk from the supplied process data (``None`` when no process data exist)."""
    p = tol.process
    if p is None:
        return None
    width = tol.upper_limit - tol.lower_limit
    cp = width / (6 * p.std)
    cpk = min(tol.upper_limit - p.mean, p.mean - tol.lower_limit) / (3 * p.std)
    warnings: list[str] = []
    if p.basis == "assumed":
        warnings.append("process mean and standard deviation are assumed, not measured")
    if p.sample_size is not None and p.sample_size < 30:
        warnings.append(f"only {p.sample_size} measurements: indices are imprecise")
    if cpk < 1.0:
        warnings.append("Cpk < 1.0: the process is not capable of this specification")
    elif cpk < 1.33:
        warnings.append("Cpk < 1.33: marginal capability")
    warnings.append("indices assume a stable, normally distributed process")
    return Capability(tol.id, float(cp), float(cpk), p.basis, warnings)


def review_tolerances(spec: MechanicalModelSpec) -> list[dict[str, Any]]:
    """Validation findings for the tolerance set (shown in the UI validation panel)."""
    findings: list[dict[str, Any]] = []

    def add(tol_id: str | None, severity: str, message: str) -> None:
        findings.append({"tolerance": tol_id, "severity": severity, "message": message})

    bound = {e.tolerance for e in spec.effects}
    for f in spec.fits:
        bound |= {f.shaft, f.bore}
    for rs in spec.radial_supports:
        if rs.internal_clearance:
            bound.add(rs.internal_clearance)
    for g in spec.gear_stages:
        inputs = g.inputs.model_dump()
        bound |= {v for k, v in inputs.items() if k != "carrier_pin_radial" and v}
        bound |= set(g.inputs.carrier_pin_radial)

    for t in spec.tolerances:
        for problem in D.validate(t.distribution):
            add(t.id, "error", f"distribution: {problem}")
        outside = D.fraction_outside(t.distribution, t.lower_limit, t.upper_limit)
        if outside > 1e-6:
            add(t.id, "info", f"{outside * 100:.3g}% of the distribution lies outside the "
                              "specification limits (out-of-spec parts are simulated, not removed)")
        lo, hi = D.bounds(t.distribution)
        if hi < t.lower_limit or lo > t.upper_limit:
            add(t.id, "error", "distribution does not overlap the specification limits")
        if t.confidence == Confidence.ASSUMED:
            add(t.id, "warning", "values are assumed, not taken from a specification or measurement")
        if t.characteristic in UNPROPAGATED:
            add(t.id, "warning", f"{t.characteristic} is recorded but has no propagation model")
        elif t.id not in bound:
            add(t.id, "warning", "not bound to any fit, gear stage or effect: it cannot "
                                 "influence simulation results")
        if t.category == "geometric" and t.datum is None and t.characteristic not in UNPROPAGATED:
            add(t.id, "warning", "geometric tolerance without a datum reference")
    for c in spec.correlations:
        if c.basis == "assumed":
            add(None, "warning",
                f"correlation {c.parameters[0]} ~ {c.parameters[1]} is assumed, not measured")
    if not spec.tolerances:
        add(None, "error", "no tolerances defined")
    return findings


def linear_stack(contributors: list[tuple[float, float, float]]) -> dict[str, float]:
    """Linear stack ``y = sum(a_i * x_i)`` from (sensitivity, half-width, sigma) triples.

    Returns the worst-case half-width (arithmetic sum) and the root-sum-square sigma, the two
    standard analytical stack results.
    """
    a = np.array([c[0] for c in contributors], dtype=float)
    t = np.array([c[1] for c in contributors], dtype=float)
    s = np.array([c[2] for c in contributors], dtype=float)
    return {
        "worst_case": float(np.sum(np.abs(a) * t)),
        "rss_sigma": float(np.sqrt(np.sum((a * s) ** 2))),
    }
