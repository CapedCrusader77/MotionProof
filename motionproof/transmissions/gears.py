"""Planetary gear stage relations (reduced order, Fidelity 2).

This is a lost-motion model built from involute gear geometry, not a tooth-contact analysis.

Model
-----
For an involute mesh a change ``da`` of operating centre distance changes the circumferential
backlash at the pitch circle by ``2 * tan(alpha) * da`` (external mesh: more distance, more
backlash; internal mesh: the opposite sign).

With the sun and ring held, a planet centre can travel tangentially by ``d`` until both meshes
close. The planet rolls, so its pitch point moves ``d + r*phi`` at the sun and ``d - r*phi`` at
the ring; both gaps are used up when ``2*d = j_sun_planet + j_planet_ring``. Diametral
clearance ``c`` in the planet bearing adds directly. The carrier free play of planet k is

    d_k = (j_sp_k + j_pr_k) / 2 + c
    stage backlash angle = min_k(d_k) / a        (the first planet to engage carries load)

Assumptions: rigid teeth, equal load sharing ignored, tooth-thickness errors lumped into the
design backlash, errors small against the tooth depth.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

import numpy as np

from motionproof.core.schema import MechanicalModelSpec, PlanetaryStage
from motionproof.core.units import length_factor


def planetary_ratio(sun_teeth: int, ring_teeth: int) -> float:
    """Reduction with sun input, carrier output and the ring gear fixed."""
    return 1.0 + ring_teeth / sun_teeth


def backlash_from_centre_distance(delta_a: float, pressure_angle_deg: float,
                                  internal: bool = False) -> float:
    """Circumferential backlash change for a centre-distance change (same length unit)."""
    j = 2.0 * np.tan(np.radians(pressure_angle_deg)) * delta_a
    return float(-j if internal else j)


@dataclass
class StageResult:
    stage: str
    ratio: float
    centre_distance_mm: float
    backlash_angle: float  # rad at the stage output (carrier), reference position
    min_mesh_backlash_mm: float  # smallest mesh backlash over a revolution
    binding: bool  # a mesh runs out of backlash somewhere in the revolution
    te_amplitude_input: float  # rad at the sun, once-per-sun-revolution, from sun runout
    te_phase: float
    per_planet: list[dict[str, float]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def evaluate_stage(
    stage: PlanetaryStage, spec: MechanicalModelSpec, values: dict[str, float]
) -> StageResult:
    """Evaluate one stage for a set of actual tolerance values (keyed by tolerance id)."""
    notes: list[str] = []

    def mm(tol_id: str | None, what: str, deviation: bool = False) -> float:
        if tol_id is None:
            notes.append(f"{what}: no tolerance mapped, nominal (zero) used")
            return 0.0
        tol = spec.tolerance(tol_id)
        v = values[tol_id] - (tol.nominal if deviation else 0.0)
        return v * length_factor(tol.unit) * 1000.0

    inp = stage.inputs
    a = stage.centre_distance
    tan_a = float(np.tan(np.radians(stage.pressure_angle)))
    j0_sp = mm(inp.design_backlash_sun_planet, "sun-planet design backlash")
    j0_pr = mm(inp.design_backlash_planet_ring, "planet-ring design backlash")
    c_bearing = mm(inp.planet_bearing_clearance, "planet bearing clearance")
    ecc = mm(inp.sun_runout, "sun runout") / 2.0  # runout is a total indicator reading
    phase = values[inp.sun_runout_phase] if inp.sun_runout_phase else 0.0
    off = np.array([mm(inp.ring_offset_x, "ring offset x", True),
                    mm(inp.ring_offset_y, "ring offset y", True)])
    off_mag = float(np.linalg.norm(off))

    per_planet: list[dict[str, float]] = []
    travel: list[float] = []
    mesh_min = np.inf
    for k in range(stage.planets):
        ang = 2 * np.pi * k / stage.planets
        dr = mm(inp.carrier_pin_radial[k], "", True) if inp.carrier_pin_radial else 0.0
        u = np.array([np.cos(ang), np.sin(ang)])
        da_sp = dr - ecc * np.cos(ang - phase)
        da_pr = dr - float(off @ u)
        j_sp = j0_sp + 2 * tan_a * da_sp
        j_pr = j0_pr - 2 * tan_a * da_pr
        # extremes over a revolution: the sun eccentricity and ring offset sweep past each planet
        j_sp_min = j0_sp + 2 * tan_a * (dr - abs(ecc))
        j_pr_min = j0_pr - 2 * tan_a * (dr + off_mag)
        mesh_min = min(mesh_min, j_sp_min, j_pr_min)
        d = (max(j_sp, 0.0) + max(j_pr, 0.0)) / 2 + max(c_bearing, 0.0)
        travel.append(d)
        per_planet.append({"planet": k, "pin_radial_dev_mm": dr, "j_sun_planet_mm": j_sp,
                           "j_planet_ring_mm": j_pr, "free_travel_mm": d})
    if not inp.carrier_pin_radial:
        notes.append("carrier pin positions: no tolerance mapped, nominal used")
    r_sun = stage.module * stage.sun_teeth / 2.0
    return StageResult(
        stage=stage.id,
        ratio=stage.ratio,
        centre_distance_mm=a,
        backlash_angle=float(min(travel) / a),
        min_mesh_backlash_mm=float(mesh_min),
        binding=bool(mesh_min < 0.0),
        te_amplitude_input=float(abs(ecc) / r_sun),
        te_phase=float(phase),
        per_planet=per_planet,
        notes=notes,
    )
