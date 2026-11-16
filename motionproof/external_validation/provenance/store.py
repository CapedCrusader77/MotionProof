"""Download, integrity checks and provenance records for external datasets.

Original files are written once and never modified. Every file gets a manifest entry with its
source URL, published checksum (when the publisher provides one), the checksum MotionProof
computed, size and retrieval time.
"""

from __future__ import annotations

import hashlib
import json
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from motionproof.external_validation.datasets.registry import ADAPTER_VERSION, DATASETS

Evidence = Literal["EXTERNAL_MEASURED", "EXTERNAL_CALIBRATION", "EXTERNAL_VALIDATION",
                   "ASSUMED", "SYNTHETIC", "ANALYTICAL_REFERENCE"]
USER_AGENT = "MotionProof-external-validation/1.0"


class IntegrityError(ValueError):
    pass


def digest(path: Path, algo: str) -> str:
    h = hashlib.new(algo)
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def dataset_dir(root: Path, key: str) -> Path:
    return Path(root) / key


def manifest_path(root: Path, key: str) -> Path:
    return dataset_dir(root, key) / "manifest.json"


def load_manifest(root: Path, key: str) -> dict[str, Any]:
    p = manifest_path(root, key)
    if not p.exists():
        info = DATASETS[key]
        return {"dataset": key, "title": info.title, "source": info.url, "doi": info.doi,
                "version": info.version, "licence": info.licence, "citation": info.citation,
                "adapter_version": ADAPTER_VERSION, "files": {}}
    data: dict[str, Any] = json.loads(p.read_text(encoding="utf-8"))
    return data


def save_manifest(root: Path, key: str, manifest: dict[str, Any]) -> None:
    p = manifest_path(root, key)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(manifest, indent=1, sort_keys=True), encoding="utf-8")


def fetch(root: Path, key: str, rel: str, url: str, algo: str | None = None,
          expected: str | None = None) -> dict[str, Any]:
    """Download ``url`` to ``<root>/<key>/raw/<rel>`` once and verify it.

    An existing file is never overwritten; it is re-verified instead. A checksum mismatch
    deletes nothing and raises, so a corrupt download is never used silently.
    """
    dest = dataset_dir(root, key) / "raw" / rel
    manifest = load_manifest(root, key)
    if not dest.exists():
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(dest.suffix + ".part")
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=120) as r, tmp.open("wb") as f:
            while chunk := r.read(1 << 20):
                f.write(chunk)
        tmp.replace(dest)
    entry = verify(dest, algo, expected)
    entry |= {"url": url, "retrieved_utc": manifest["files"].get(rel, {}).get(
        "retrieved_utc", datetime.now(UTC).isoformat(timespec="seconds"))}
    manifest["files"][rel] = entry
    save_manifest(root, key, manifest)
    return entry


def verify(path: Path, algo: str | None, expected: str | None) -> dict[str, Any]:
    sha256 = digest(path, "sha256")
    entry: dict[str, Any] = {"bytes": path.stat().st_size, "sha256": sha256}
    if algo and expected:
        actual = sha256 if algo == "sha256" else digest(path, algo)
        if actual.lower() != expected.lower():
            raise IntegrityError(f"{path.name}: {algo} {actual} does not match the published "
                                 f"{expected}")
        entry |= {"published_checksum": {"algorithm": algo, "value": expected},
                  "integrity": "verified against published checksum"}
    else:
        entry["integrity"] = "no published checksum; SHA-256 recorded at import"
    return entry


def evidence(kind: Evidence, dataset: str, trial: str | None, role: str, detail: str,
             transformation: str | None = None) -> dict[str, Any]:
    """One model-trust evidence record for an external quantity."""
    info = DATASETS[dataset]
    return {"evidence": kind, "dataset": dataset, "system": info.system, "trial": trial,
            "role": role, "detail": detail, "citation": info.citation,
            "licence": info.licence, "transformation": transformation,
            "scope": "external system; not a measurement of the MotionProof reference "
                     "gearbox or of any user hardware"}
