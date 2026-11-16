"""DaRUS-5760 adapter: transmission error of Staubli TX2-40 gearboxes.

Each file: tab-separated (original upload: CSV) with columns theta (input-side position, rad),
q_set (joint angle setpoint, rad) and theta_TE (transmission error, rad). The data are in the
position domain; there are no time stamps. The velocity setpoint is encoded in the file name.
"""

from __future__ import annotations

import csv
import json
import re
import urllib.request
from pathlib import Path
from typing import Any

import numpy as np

from motionproof.external_validation.adapters.base import Adapter, RemoteFile
from motionproof.external_validation.provenance.store import USER_AGENT
from motionproof.external_validation.schemas.trial import SchemaError, Signal, Trial

META = ("https://darus.uni-stuttgart.de/api/datasets/:persistentId/"
        "?persistentId=doi:10.18419/DARUS-5760")
ACCESS = "https://darus.uni-stuttgart.de/api/access/datafile/{id}?format=original"
COLUMNS = ("theta", "q_set", "theta_TE")


class StuttgartTE(Adapter):
    key = "stuttgart-te"

    def _metadata(self, root: Path) -> dict[str, Any]:
        cache = self.raw(root) / "_darus_metadata.json"
        if not cache.exists():
            req = urllib.request.Request(META, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=60) as r:
                cache.parent.mkdir(parents=True, exist_ok=True)
                cache.write_bytes(r.read())
        meta = json.loads(cache.read_text(encoding="utf-8"))
        data: dict[str, Any] = meta["data"]["latestVersion"]
        return data

    def remote_files(self, root: Path) -> list[RemoteFile]:
        out = []
        for f in self._metadata(root)["files"]:
            folder = f.get("directoryLabel")
            if not folder or not folder.startswith(("identification", "validation")):
                continue
            df = f["dataFile"]
            name = df.get("originalFileName") or df["filename"]
            out.append(RemoteFile(f"{folder}/{name}", ACCESS.format(id=df["id"]), "md5",
                                  df["md5"], folder.split("/")[1]))
        return out

    def load(self, root: Path, rel: str) -> Trial:
        path = self.raw(root) / rel
        with path.open(encoding="utf-8") as fh:
            sample = fh.readline()
            fh.seek(0)
            reader = csv.reader(fh, delimiter="\t" if "\t" in sample else ",")
            header = next(reader)
            if tuple(h.strip() for h in header) != COLUMNS:
                raise SchemaError(f"{rel}: columns {header}, expected {COLUMNS}")
            rows = np.array([[float(x) for x in r] for r in reader if r])
        m = re.search(r"q_set_dot=(-?\d+\.\d+)", rel)
        if m is None:
            raise SchemaError(f"{rel}: velocity setpoint missing from the file name")
        role, axis = rel.split("/")[0], rel.split("/")[1]
        signals = {c: Signal(c, rows[:, i], "rad", c) for i, c in enumerate(COLUMNS)}
        cond = {"axis": axis, "published_role": role, "q_set_dot_rad_s": float(m.group(1))}
        return Trial(self.key, f"{role}/{axis}/q_set_dot={m.group(1)}", rel, signals, cond)
