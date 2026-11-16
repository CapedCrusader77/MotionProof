"""Common in-memory form of an external measurement trial.

A trial holds named signals, each with values, an SI unit, the original field name and the
conversion applied. Missing samples are never filled: a signal with non-finite values is
rejected, and a signal the dataset does not contain is simply absent.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

SI_UNITS = {"rad", "rad/s", "rad/s^2", "N*m", "A", "V", "K", "s", "m", "1"}


class SchemaError(ValueError):
    pass


@dataclass
class Signal:
    name: str
    values: np.ndarray
    unit: str
    source_field: str
    conversion: str = "none"
    time_s: np.ndarray | None = None  # None: position-domain data without time stamps

    def __post_init__(self) -> None:
        self.values = np.asarray(self.values, dtype=float)
        if self.unit not in SI_UNITS:
            raise SchemaError(f"signal {self.name!r}: unit {self.unit!r} is not an SI unit")
        if self.values.ndim != 1 or len(self.values) == 0:
            raise SchemaError(f"signal {self.name!r}: expected a non-empty 1-D series")
        bad = int(np.sum(~np.isfinite(self.values)))
        if bad:
            raise SchemaError(f"signal {self.name!r} ({self.source_field}): {bad} non-finite "
                              "values; missing samples are never filled")
        if self.time_s is not None:
            self.time_s = np.asarray(self.time_s, dtype=float)
            if len(self.time_s) != len(self.values):
                raise SchemaError(f"signal {self.name!r}: time and values differ in length")
            if np.any(np.diff(self.time_s) <= 0):
                raise SchemaError(f"signal {self.name!r}: time stamps are not strictly "
                                  "increasing")


@dataclass
class Trial:
    dataset: str
    trial_id: str
    source_file: str
    signals: dict[str, Signal]
    conditions: dict[str, Any] = field(default_factory=dict)
    t0_ns: int | None = None  # original absolute start time, when the dataset has one

    def require(self, *names: str) -> None:
        missing = [n for n in names if n not in self.signals]
        if missing:
            raise SchemaError(f"trial {self.trial_id}: required signals missing: {missing} "
                              f"(available: {sorted(self.signals)})")

    def summary(self) -> dict[str, Any]:
        out: dict[str, Any] = {"trial": self.trial_id, "file": self.source_file,
                               "conditions": self.conditions, "signals": {}}
        for k, s in self.signals.items():
            entry: dict[str, Any] = {"unit": s.unit, "source_field": s.source_field,
                                     "conversion": s.conversion, "samples": len(s.values),
                                     "min": float(s.values.min()), "max": float(s.values.max())}
            if s.time_s is not None and len(s.time_s) > 1:
                entry["sample_period_s"] = float(np.median(np.diff(s.time_s)))
                entry["duration_s"] = float(s.time_s[-1] - s.time_s[0])
            out["signals"][k] = entry
        return out


def align(target_t: np.ndarray, source: Signal) -> np.ndarray:
    """Linear interpolation of ``source`` onto ``target_t`` within its own time span.

    Points outside the source span raise instead of being extrapolated.
    """
    if source.time_s is None:
        raise SchemaError(f"signal {source.name!r} has no time stamps")
    if target_t.min() < source.time_s[0] - 1e-12 or target_t.max() > source.time_s[-1] + 1e-12:
        raise SchemaError(f"alignment of {source.name!r} would extrapolate")
    return np.asarray(np.interp(target_t, source.time_s, source.values), dtype=float)
