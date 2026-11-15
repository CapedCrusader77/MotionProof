"""Measured component dimensions (caliper, micrometer, bore gauge, CMM) in the model.

CSV schema, one row per measurement:

    part_id, tolerance, value, unit, instrument, resolution, date, operator, notes

``tolerance`` is a tolerance id of the model; ``resolution`` (same unit) is the smallest
increment of the instrument. Repeated measurements of one part and tolerance are averaged.

Three uses:

* **summary**: per tolerance n, mean, standard deviation, range, out-of-specification count,
  Cp/Cpk against the specification, and a gauge-resolution check;
* **apply**: a new model file whose distributions come from the measurements (normal or
  empirical) with ``confidence: measured``; the original model is not modified;
* **parts**: one variant per physically measured part, evaluated with the real simulation,
  so the verdict is about parts that exist.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Literal

import numpy as np

from motionproof.core.schema import MechanicalModelSpec
from motionproof.core.units import length_factor
from motionproof.manufacturing.variants import nominal_values

REQUIRED = ("part_id", "tolerance", "value", "unit")
ANGLE_UNITS = {"rad": 1.0, "deg": 0.017453292519943295}


class MeasurementError(ValueError):
    pass


def _convert(value: float, unit: str, target: str) -> float:
    u, t = unit.strip().lower(), target.strip().lower()
    if u == t:
        return value
    if u in ANGLE_UNITS and t in ANGLE_UNITS:
        return value * ANGLE_UNITS[u] / ANGLE_UNITS[t]
    try:
        return value * length_factor(u) / length_factor(t)
    except ValueError:
        raise MeasurementError(f"cannot convert {unit!r} to {target!r}") from None


def load(path: str | Path, spec: MechanicalModelSpec) -> list[dict[str, Any]]:
    """Read and validate a measurement CSV; values are converted to the tolerance's unit."""
    p = Path(path)
    with p.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(line for line in f if not line.lstrip().startswith("#"))
        missing = [c for c in REQUIRED if c not in (reader.fieldnames or [])]
        if missing:
            raise MeasurementError(f"{p.name}: missing columns {missing}; required {REQUIRED}")
        known = {t.id: t for t in spec.tolerances}
        rows = []
        for n, r in enumerate(reader, start=2):
            if not (r.get("value") or "").strip():
                continue  # template rows left empty
            tid = r["tolerance"].strip()
            if tid not in known:
                raise MeasurementError(f"{p.name} line {n}: unknown tolerance {tid!r}")
            try:
                value = float(r["value"])
            except ValueError:
                raise MeasurementError(f"{p.name} line {n}: value {r['value']!r} is not a "
                                       "number") from None
            if not r["unit"].strip():
                raise MeasurementError(f"{p.name} line {n}: unit missing (never assumed)")
            tol = known[tid]
            res = (r.get("resolution") or "").strip()
            rows.append({
                "part_id": r["part_id"].strip(), "tolerance": tid,
                "value": _convert(value, r["unit"], tol.unit), "unit": tol.unit,
                "instrument": (r.get("instrument") or "").strip() or None,
                "resolution": _convert(float(res), r["unit"], tol.unit) if res else None,
                "date": (r.get("date") or "").strip() or None,
                "operator": (r.get("operator") or "").strip() or None,
                "line": n})
    if not rows:
        raise MeasurementError(f"{p.name} contains no measured values")
    return rows


def _per_part(rows: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    acc: dict[str, dict[str, list[float]]] = {}
    for r in rows:
        acc.setdefault(r["part_id"], {}).setdefault(r["tolerance"], []).append(r["value"])
    return {p: {t: float(np.mean(v)) for t, v in d.items()} for p, d in acc.items()}


def summary(rows: list[dict[str, Any]], spec: MechanicalModelSpec) -> dict[str, Any]:
    parts = _per_part(rows)
    out: dict[str, Any] = {}
    for tid in sorted({r["tolerance"] for r in rows}):
        tol = spec.tolerance(tid)
        x = np.array([d[tid] for d in parts.values() if tid in d])
        res = [r["resolution"] for r in rows if r["tolerance"] == tid and r["resolution"]]
        repeats = [r for r in rows if r["tolerance"] == tid]
        warnings: list[str] = []
        entry: dict[str, Any] = {"n_parts": int(len(x)), "n_readings": len(repeats),
                                 "unit": tol.unit, "lower_limit": tol.lower_limit,
                                 "upper_limit": tol.upper_limit, "mean": float(x.mean()),
                                 "min": float(x.min()), "max": float(x.max()),
                                 "out_of_spec": int(np.sum((x < tol.lower_limit - 1e-12)
                                                           | (x > tol.upper_limit + 1e-12)))}
        if len(x) >= 2:
            sd = float(x.std(ddof=1))
            entry["std"] = sd
            width = tol.upper_limit - tol.lower_limit
            if sd > 0:
                entry["cp"] = width / (6 * sd)
                entry["cpk"] = min(tol.upper_limit - entry["mean"],
                                   entry["mean"] - tol.lower_limit) / (3 * sd)
            if len(x) < 30:
                warnings.append(f"{len(x)} parts: standard deviation and capability are "
                                "imprecise (30 or more recommended)")
        else:
            warnings.append("one part only: no spread can be estimated")
        if res:
            r_max = max(res)
            entry["resolution"] = r_max
            width = tol.upper_limit - tol.lower_limit
            if width > 0 and r_max > width / 10:
                warnings.append(f"instrument resolution {r_max:g} {tol.unit} is coarser than a "
                                f"tenth of the tolerance width {width:g}: the measurement "
                                "cannot resolve this tolerance reliably")
        else:
            warnings.append("instrument resolution not recorded")
        entry["warnings"] = warnings
        out[tid] = entry
    return {"tolerances": out, "parts": len(parts),
            "note": "statistics of the measured parts; capability assumes a stable process"}


def apply(spec: MechanicalModelSpec, rows: list[dict[str, Any]], source: str,
          mode: Literal["normal", "empirical"] = "normal") -> MechanicalModelSpec:
    """A copy of ``spec`` whose measured tolerances use distributions from the data."""
    stats = summary(rows, spec)["tolerances"]
    parts = _per_part(rows)
    data = spec.model_dump(mode="json", by_alias=True)
    for t in data["tolerances"]:
        s = stats.get(t["id"])
        if s is None:
            continue
        if s["n_parts"] < 2:
            raise MeasurementError(f"{t['id']}: at least two measured parts are needed to "
                                   "derive a distribution")
        values = [d[t["id"]] for d in parts.values() if t["id"] in d]
        if mode == "empirical":
            t["distribution"] = {"type": "empirical", "samples": values}
        else:
            t["distribution"] = {"type": "normal", "mean": s["mean"], "std": s["std"]}
        t["source"] = (f"measured: {source}, {s['n_parts']} parts, {mode} fit"
                       + (f"; {s['warnings'][0]}" if s["warnings"] else ""))
        t["confidence"] = "measured"
        t["verification"] = "measured"
    data["description"] = (data.get("description", "") + f" Distributions of measured "
                           f"tolerances replaced from {source}.").strip()
    return MechanicalModelSpec.model_validate(data)


def part_rows(rows: list[dict[str, Any]], spec: MechanicalModelSpec
              ) -> dict[str, dict[str, Any]]:
    """Tolerance values of each measured part; unmeasured tolerances stay at design value."""
    nominal = nominal_values(spec)
    out = {}
    for pid, vals in _per_part(rows).items():
        out[pid] = {"values": nominal | vals, "measured": sorted(vals),
                    "unmeasured": sorted(set(nominal) - set(vals))}
    return out
