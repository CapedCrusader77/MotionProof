"""NIST UR5 accuracy-degradation adapter.

Each CSV row is a tuple of bracketed vectors in the column order of UR5TestResult_header.xlsx:
time, target q, actual q, target dq, actual dq, target current, actual current, target ddq,
target torque, control current, tool pose, TCP force, joint temperature.

Units are not stated in the header. Joint angles reach about 160, so they are degrees and are
converted to rad (inferred). Differentiating the positions gives 57.3 x the reported
velocities (``check_units``), i.e. the velocities are already in rad/s; accelerations are taken
to be rad/s^2 like the velocities (inferred, not checkable from the data).
"""

from __future__ import annotations

import math
import re
from pathlib import Path

import numpy as np

from motionproof.external_validation.adapters.base import Adapter, RemoteFile
from motionproof.external_validation.schemas.trial import SchemaError, Signal, Trial

DOC = "https://www.nist.gov/document/{}"
RUNS = [(cold, speed, lb, rep) for cold in (False, True) for speed in ("half", "full")
        for lb in (16, 45) for rep in (1, 2, 3) if not (cold and lb == 16)]
GROUPS = ["t", "q_target", "q", "dq_target", "dq", "current_target", "current",
          "ddq_target", "tau_target", "current_control", "tool_pose", "tcp_force",
          "temperature"]
D2R = math.pi / 180.0


def run_doc(cold: bool, speed: str, lb: int, rep: int) -> str:
    slug = f"ur5testresult{'coldstart' if cold else ''}{speed}speedpayload{lb}lb{rep}csv"
    return slug + ("-0" if (not cold and speed == "full" and lb == 16 and rep == 1) else "")


class NistUR5(Adapter):
    key = "nist-ur5"

    def remote_files(self, root: Path) -> list[RemoteFile]:
        out = [RemoteFile("UR5TestResult_header.xlsx", DOC.format("ur5testresultheaderxlsx"),
                          None, None, "metadata"),
               RemoteFile("calculated_deviation.xlsx",
                          DOC.format("calculateddeviationofactualpositiontonominalpositionxlsx"),
                          None, None, "metadata")]
        for cold, speed, lb, rep in RUNS:
            name = (f"{'coldstart_' if cold else ''}{speed}speed_payload{lb}lb_{rep}.csv")
            out.append(RemoteFile(name, DOC.format(run_doc(cold, speed, lb, rep)), None, None,
                                  "runs"))
        return out

    def load(self, root: Path, rel: str) -> Trial:
        path = self.raw(root) / rel
        rows = []
        with path.open(encoding="utf-8") as fh:
            for n, line in enumerate(fh, 1):
                groups = re.findall(r"\[([^\]]*)\]", line)
                if not groups:
                    continue
                if len(groups) != len(GROUPS):
                    raise SchemaError(f"{rel} line {n}: {len(groups)} groups, expected "
                                      f"{len(GROUPS)}")
                rows.append([[float(x) for x in g.split(",")] for g in groups])
        if not rows:
            raise SchemaError(f"{rel}: no data rows")
        t = np.array([r[0][0] for r in rows])
        keep = np.concatenate([[True], np.diff(t) > 0])
        t = t[keep] - t[keep][0]
        signals: dict[str, Signal] = {}
        spec = {"q_target": ("rad", D2R, "deg to rad (inferred)"),
                "q": ("rad", D2R, "deg to rad (inferred)"),
                "dq_target": ("rad/s", 1.0, "none (rad/s; verified by check_units)"),
                "dq": ("rad/s", 1.0, "none (rad/s; verified by check_units)"),
                "ddq_target": ("rad/s^2", 1.0, "none (rad/s^2, inferred from velocities)"),
                "current_target": ("A", 1.0, "none"), "current": ("A", 1.0, "none"),
                "current_control": ("A", 1.0, "none"),
                "tau_target": ("N*m", 1.0, "none (controller target torque)"),
                "temperature": ("K", 1.0, "degC + 273.15")}
        for gi, g in enumerate(GROUPS):
            if g not in spec:
                continue
            unit, k, conv = spec[g]
            arr = np.array([r[gi] for r in rows])[keep]
            for j in range(arr.shape[1]):
                vals = arr[:, j] + 273.15 if g == "temperature" else arr[:, j] * k
                signals[f"J{j + 1}/{g}"] = Signal(f"J{j + 1}/{g}", vals, unit,
                                                   f"ROBOT_{g.upper()} (J{j + 1})", conv, t)
        m = re.match(r"(coldstart_)?(half|full)speed_payload(\d+)lb_(\d)", rel)
        if m is None:
            raise SchemaError(f"{rel}: condition not encoded in the file name")
        cond = {"cold_start": bool(m.group(1)), "speed": m.group(2),
                "payload_kg": round(int(m.group(3)) * 0.45359237, 3),
                "payload_lb": int(m.group(3)), "repeat": int(m.group(4))}
        return Trial(self.key, rel.removesuffix(".csv"), rel, signals, cond)


def check_units(trial: Trial, joint: str = "J1") -> float:
    """Ratio of numerically differentiated actual position (as converted) to reported
    velocity. About 1 when units are consistent (57.3 meant degrees vs rad/s)."""
    q, dq = trial.signals[f"{joint}/q"], trial.signals[f"{joint}/dq"]
    assert q.time_s is not None
    num = np.gradient(q.values, q.time_s)
    sel = np.abs(dq.values) > 0.2 * np.max(np.abs(dq.values))
    return float(np.median(num[sel] / dq.values[sel]))
