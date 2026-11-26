"""NVIDIA Anchor-Lab adapter (long-form parquet: time_ns, experiment, field, value).

Protocol subsets
* ``h1-teststand``: the 36 sine trials of the H1 elbow test stand at 0.5, 1.0 and 1.5 Hz with
  small, medium and large amplitude, at stand positions 8, 9, 10 and 11.
* ``so101``: the SO-101 single-joint train trials (elbow, rotation, wrist pitch, wrist roll)
  and the eight ``heldout`` trials.

Unit assumptions: Unitree and Feetech telemetry fields in this dataset are taken to be in rad,
rad/s, N*m, A, V and degrees Celsius (converted to kelvin). The dataset card does not state
units; values were checked for plausibility at inspection (see docs/external-datasets.md).
"""

from __future__ import annotations

import json
import re
import urllib.request
from pathlib import Path
from typing import Any

import numpy as np

from motionproof.external_validation.adapters.base import Adapter, RemoteFile
from motionproof.external_validation.datasets.registry import ANCHOR_LAB_REVISION
from motionproof.external_validation.provenance.store import USER_AGENT
from motionproof.external_validation.schemas.trial import SchemaError, Signal, Trial

API = "https://huggingface.co/api/datasets/nvidia/Anchor-Lab/tree/" + ANCHOR_LAB_REVISION
FILE = "https://huggingface.co/datasets/nvidia/Anchor-Lab/resolve/" + ANCHOR_LAB_REVISION

H1_NAMES = [f"h1-elbow-teststand-sysid-{f}hz-amp-{a}-position{p}.parquet"
            for f in ("0p5", "1p0", "1p5") for a in ("small", "medium", "large")
            for p in (8, 9, 10, 11)]
SO101_IDENT = [f"so101-sysid-50motion-train-single-joint-{j}.parquet"
               for j in ("elbow", "rotation", "wrist-pitch", "wrist-roll")]

# field suffix -> (signal name, SI unit, conversion)
UNITS = {"q": ("q", "rad", "none"), "actual_q": ("q", "rad", "none"),
         "command_q": ("q_cmd", "rad", "none"), "dq": ("dq", "rad/s", "none"),
         "tau": ("tau", "N*m", "none"), "tau_abs": ("tau_abs", "N*m", "none"),
         "current": ("current", "A", "none"), "voltage": ("voltage", "V", "none"),
         "temp": ("temperature", "K", "degC + 273.15"),
         "temperature": ("temperature", "K", "degC + 273.15"),
         "is_moving": ("is_moving", "1", "none")}


def _listing(sub: str) -> list[dict[str, Any]]:
    req = urllib.request.Request(f"{API}/data/{sub}", headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=60) as r:
        data: list[dict[str, Any]] = json.loads(r.read().decode())
    return data


def read_long_parquet(path: Path) -> tuple[str, dict[str, tuple[np.ndarray, np.ndarray]]]:
    import pyarrow.parquet as pq

    t = pq.read_table(path, columns=["time_ns", "experiment", "field", "value"])
    experiments = set(t["experiment"].to_pylist())
    if len(experiments) != 1:
        raise SchemaError(f"{path.name}: expected one experiment, found {len(experiments)}")
    fields = np.array(t["field"].to_pylist())
    tn = t["time_ns"].to_numpy()
    v = t["value"].to_numpy(zero_copy_only=False)
    out = {}
    for name in np.unique(fields):
        m = fields == name
        order = np.argsort(tn[m], kind="stable")
        out[str(name)] = (tn[m][order], v[m][order])
    return experiments.pop(), out


class AnchorLab(Adapter):
    key = "anchor-lab"

    def remote_files(self, root: Path) -> list[RemoteFile]:
        cache = self.raw(root) / "_listing.json"
        if cache.exists():
            listing = json.loads(cache.read_text(encoding="utf-8"))
        else:
            listing = {"h1_elbow_teststand": _listing("h1_elbow_teststand"),
                       "so101_arm_50motion": _listing("so101_arm_50motion")}
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_text(json.dumps(listing), encoding="utf-8")
        files = []
        for sub, entries in listing.items():
            for e in entries:
                name = e["path"].split("/")[-1]
                if sub == "h1_elbow_teststand" and name in H1_NAMES:
                    group = "h1-teststand"
                elif sub == "so101_arm_50motion" and (name in SO101_IDENT or "-heldout-" in name):
                    group = "so101"
                else:
                    continue
                files.append(RemoteFile(f"{sub}/{name}", f"{FILE}/{e['path']}", "sha256",
                                        e["lfs"]["oid"], group))
        return files

    def load(self, root: Path, rel: str) -> Trial:
        path = self.raw(root) / rel
        experiment, fields = read_long_parquet(path)
        signals: dict[str, Signal] = {}
        t0 = min(int(tn[0]) for tn, _ in fields.values())
        for field, (tn, v) in fields.items():
            joint, suffix = field.split("/", 1) if "/" in field else field.split("_", 1)
            if suffix not in UNITS or suffix == "present_load_raw":
                continue  # raw servo units without a documented SI conversion: not imported
            name, unit, conv = UNITS[suffix]
            keep = np.concatenate([[True], np.diff(tn) > 0])  # duplicate stamps: first kept
            vals = v[keep] + 273.15 if conv.startswith("degC") else v[keep]
            signals[f"{joint}/{name}"] = Signal(f"{joint}/{name}", vals, unit, field, conv,
                                                (tn[keep] - t0) * 1e-9)
        cond: dict[str, object] = {"experiment": experiment}
        m = re.search(r"(\d+p\d+)hz-amp-(\w+)-position(\d+)", experiment)
        if m:
            cond |= {"frequency_hz": float(m.group(1).replace("p", ".")),
                     "amplitude": m.group(2), "position": int(m.group(3))}
        if experiment.startswith("so101"):
            cond["split"] = "heldout" if "-heldout-" in experiment else "train"
        return Trial(self.key, experiment, rel, signals, cond, t0)
