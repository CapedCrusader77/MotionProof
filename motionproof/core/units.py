"""Explicit unit handling. Every quantity entering the simulator is converted to SI here."""

from __future__ import annotations

LENGTH_TO_M: dict[str, float] = {
    "m": 1.0,
    "cm": 0.01,
    "mm": 0.001,
    "um": 1e-6,
    "in": 0.0254,
    "ft": 0.3048,
}
MASS_TO_KG: dict[str, float] = {"kg": 1.0, "g": 1e-3, "lb": 0.45359237, "lbmass": 0.45359237}
ANGLE_TO_RAD: dict[str, float] = {"rad": 1.0, "deg": 0.017453292519943295}


class UnitError(ValueError):
    """Raised for unknown or inconsistent units."""


def _lookup(table: dict[str, float], unit: str, kind: str) -> float:
    key = unit.strip().lower()
    if key not in table:
        raise UnitError(f"unknown {kind} unit {unit!r}; supported: {sorted(table)}")
    return table[key]


def length_factor(unit: str) -> float:
    """Multiplier converting a length in ``unit`` to metres."""
    return _lookup(LENGTH_TO_M, unit, "length")


def mass_factor(unit: str) -> float:
    """Multiplier converting a mass in ``unit`` to kilograms."""
    return _lookup(MASS_TO_KG, unit, "mass")


def angle_factor(unit: str) -> float:
    """Multiplier converting an angle in ``unit`` to radians."""
    return _lookup(ANGLE_TO_RAD, unit, "angle")


def inertia_factor(mass_unit: str, length_unit: str) -> float:
    """Multiplier converting a moment of inertia (mass * length^2) to kg*m^2."""
    return mass_factor(mass_unit) * length_factor(length_unit) ** 2


def density_factor(mass_unit: str, length_unit: str) -> float:
    """Multiplier converting a density (mass / length^3) to kg/m^3."""
    return mass_factor(mass_unit) / length_factor(length_unit) ** 3


def convert_length(value: float, from_unit: str, to_unit: str = "m") -> float:
    return value * length_factor(from_unit) / length_factor(to_unit)


def convert_angle(value: float, from_unit: str, to_unit: str = "rad") -> float:
    return value * angle_factor(from_unit) / angle_factor(to_unit)
