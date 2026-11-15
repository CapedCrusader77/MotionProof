"""Virtual as-manufactured variants.

``resolve_variant`` turns one sampled set of actual dimensions into the quantities the
assembly and the dynamics model need: fit clearances, mesh backlash, radial play, joint
misalignment and drive-train parameters. Each derived quantity records the modelling level
that produced it:

* ``A`` - regenerated parametric geometry (see ``motionproof.reference``),
* ``C`` - reduced-order relation (documented formula, geometry not regenerated).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

import numpy as np

from motionproof.core.schema import Fit, MechanicalModelSpec
from motionproof.core.units import angle_factor, length_factor
from motionproof.tolerances.sampling import design_value
from motionproof.transmissions.gears import StageResult, evaluate_stage

LENGTH_TARGETS = {"radial_play", "offset_x", "offset_y", "offset_z"}
ANGLE_TARGETS = {"backlash", "tilt_x", "tilt_y", "zero_offset"}


@dataclass
class FitResult:
    fit: str
    shaft: float
    bore: float
    clearance: float  # diametral, in the fit's unit
    unit: str
    state: str  # clearance | interference | line
    violation: str | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class JointVariant:
    """Physical parameters of one driven joint for one manufactured variant (SI)."""

    joint: str
    ratio: float
    backlash: float
    efficiency: float
    stiffness: float
    damping_ratio: float
    friction: float
    damping: float
    torque_scale: float = 1.0
    radial_play: float = 0.0  # diametral, m
    tilt_x: float = 0.0
    tilt_y: float = 0.0
    offset: tuple[float, float, float] = (0.0, 0.0, 0.0)
    zero_offset: float = 0.0
    # transmission-error harmonics: (amplitude at output rad, cycles per output rev, phase)
    te: list[tuple[float, float, float]] = field(default_factory=list)


@dataclass
class Variant:
    values: dict[str, float]
    joints: dict[str, JointVariant]
    fits: list[FitResult]
    stages: list[StageResult]
    out_of_spec: list[str]
    violations: list[dict[str, str]]
    levels: dict[str, str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "values": self.values,
            "joints": {k: asdict(v) for k, v in self.joints.items()},
            "fits": [f.to_dict() for f in self.fits],
            "stages": [s.to_dict() for s in self.stages],
            "out_of_spec": self.out_of_spec,
            "violations": self.violations,
            "levels": self.levels,
        }


def nominal_values(spec: MechanicalModelSpec) -> dict[str, float]:
    return {t.id: design_value(t) for t in spec.tolerances}


def evaluate_fit(fit: Fit, spec: MechanicalModelSpec, values: dict[str, float]) -> FitResult:
    ts, tb = spec.tolerance(fit.shaft), spec.tolerance(fit.bore)
    conv = length_factor(ts.unit) / length_factor(tb.unit)
    shaft = values[fit.shaft] * conv
    bore = values[fit.bore]
    clearance = bore - shaft
    eps = 1e-12
    state = "clearance" if clearance > eps else "interference" if clearance < -eps else "line"
    violation = None
    if fit.max_interference is not None and -clearance > fit.max_interference:
        violation = (f"interference {-clearance:.4g} {tb.unit} exceeds the allowed "
                     f"{fit.max_interference:.4g} {tb.unit}")
    if fit.min_clearance is not None and clearance < fit.min_clearance:
        violation = (f"clearance {clearance:.4g} {tb.unit} is below the required "
                     f"{fit.min_clearance:.4g} {tb.unit}")
    return FitResult(fit.id, shaft, bore, clearance, tb.unit, state, violation)


def fit_range(fit: Fit, spec: MechanicalModelSpec) -> dict[str, Any]:
    """Limit analysis of a fit from the specification limits (no sampling)."""
    ts, tb = spec.tolerance(fit.shaft), spec.tolerance(fit.bore)
    conv = length_factor(ts.unit) / length_factor(tb.unit)
    lo = tb.lower_limit - ts.upper_limit * conv
    hi = tb.upper_limit - ts.lower_limit * conv
    kind = "clearance" if lo >= 0 else "interference" if hi <= 0 else "transition"
    return {"fit": fit.id, "min_clearance": lo, "max_clearance": hi, "unit": tb.unit,
            "class": kind}


def resolve_variant(spec: MechanicalModelSpec, values: dict[str, float]) -> Variant:
    """Derive assembly and drive-train parameters from actual tolerance values."""
    missing = [t.id for t in spec.tolerances if t.id not in values]
    if missing:
        raise KeyError(f"variant is missing values for tolerances: {missing}")
    levels: dict[str, str] = {}
    violations: list[dict[str, str]] = []

    joints: dict[str, JointVariant] = {}
    for name, drive in spec.drives.items():
        g = drive.gearbox
        joints[name] = JointVariant(
            joint=name, ratio=g.ratio, backlash=g.backlash, efficiency=g.efficiency,
            stiffness=g.stiffness, damping_ratio=g.damping_ratio, friction=drive.friction,
            damping=drive.damping,
        )

    # --- specification conformance ------------------------------------------------
    out_of_spec = [
        t.id for t in spec.tolerances
        if not (t.lower_limit - 1e-12 <= values[t.id] <= t.upper_limit + 1e-12)
    ]
    groups: dict[str, list[str]] = {}
    for t in spec.tolerances:
        if t.zone_group:
            groups.setdefault(t.zone_group, []).append(t.id)
    for group, ids in groups.items():
        tols = [spec.tolerance(i) for i in ids]
        radius = float(np.sqrt(sum((values[t.id] - t.nominal) ** 2 for t in tols)))
        if radius > max(t.upper for t in tols) + 1e-12:
            out_of_spec.append(f"zone:{group}")

    # --- fits ---------------------------------------------------------------------
    fits = [evaluate_fit(f, spec, values) for f in spec.fits]
    fit_by_id = {f.fit: f for f in fits}
    for f in fits:
        levels[f"fit.{f.fit}"] = "C"
        if f.violation:
            violations.append({"category": "fit", "subject": f.fit, "message": f.violation})

    # --- gear stages: backlash and transmission error ------------------------------
    stages = [evaluate_stage(s, spec, values) for s in spec.gear_stages]
    for name, jv in joints.items():
        mine = sorted(
            (s for s in spec.gear_stages if s.joint == name), key=lambda s: s.order
        )
        res = {r.stage: r for r in stages}
        for i, st in enumerate(mine):
            downstream = float(np.prod([s.ratio for s in mine[i + 1:]])) if mine[i + 1:] else 1.0
            r = res[st.id]
            jv.backlash += r.backlash_angle / downstream
            if r.te_amplitude_input > 0:
                to_output = st.ratio * downstream
                jv.te.append((r.te_amplitude_input / to_output, to_output, r.te_phase))
            levels[f"stage.{st.id}"] = "C"
            if r.binding:
                violations.append({
                    "category": "mesh_interference", "subject": st.id,
                    "message": f"mesh backlash reaches {r.min_mesh_backlash_mm * 1000:.1f} um "
                               "(negative: teeth bind) during a revolution",
                })

    # --- direct reduced-order effects ------------------------------------------------
    for e in spec.effects:
        if e.joint not in joints:
            raise KeyError(f"effect targets joint {e.joint!r}, which has no drive defined")
        tol = spec.tolerance(e.tolerance)
        if e.target in LENGTH_TARGETS:
            k = length_factor(tol.unit)
        elif e.target in ANGLE_TARGETS:
            k = angle_factor(tol.unit)
        else:
            k = 1.0
        actual, dev = values[tol.id] * k, (values[tol.id] - tol.nominal) * k
        jv = joints[e.joint]
        levels[f"{e.joint}.{e.target}"] = "C"
        if e.target.startswith("offset_"):
            idx = "xyz".index(e.target[-1])
            off = list(jv.offset)
            off[idx] = _apply(off[idx], e.mode, e.gain, actual, dev)
            jv.offset = (off[0], off[1], off[2])
        else:
            setattr(jv, e.target, _apply(getattr(jv, e.target), e.mode, e.gain, actual, dev))

    # --- radial support: play -> seating offset and tilt -------------------------------
    for rs in spec.radial_supports:
        if rs.joint not in joints:
            raise KeyError(f"radial support refers to joint {rs.joint!r} with no drive")
        jv = joints[rs.joint]
        play = jv.radial_play
        if rs.internal_clearance:
            t = spec.tolerance(rs.internal_clearance)
            play += max(values[t.id], 0.0) * length_factor(t.unit)
        for fit_id in rs.fits:
            f = fit_by_id[fit_id]
            play += max(f.clearance, 0.0) * length_factor(f.unit)
        jv.radial_play = play
        # worst-case seating: the shaft drops by half the play and the two bearing rows sit at
        # opposite extremes, tilting the axis by play / span.
        jv.offset = (jv.offset[0], jv.offset[1], jv.offset[2] - play / 2.0)
        jv.tilt_y += play / rs.bearing_span
        levels[f"{rs.joint}.radial_play"] = "C"

    for jv in joints.values():
        if not 0 < jv.efficiency <= 1:
            violations.append({"category": "model", "subject": jv.joint,
                               "message": f"efficiency {jv.efficiency:.3f} is outside (0, 1]"})
            jv.efficiency = float(np.clip(jv.efficiency, 1e-3, 1.0))
        jv.backlash = max(jv.backlash, 0.0)
        jv.friction = max(jv.friction, 0.0)
        jv.stiffness = max(jv.stiffness, 1e-6)

    return Variant({k: float(v) for k, v in values.items()}, joints, fits, stages,
                   out_of_spec, violations, levels)


def _apply(current: float, mode: str, gain: float, actual: float, dev: float) -> float:
    if mode == "add":
        return current + gain * dev
    if mode == "set":
        return gain * actual
    return current * (1.0 + gain * dev)
