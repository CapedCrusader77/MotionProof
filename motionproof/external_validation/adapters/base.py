"""Adapter interface shared by all external datasets."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from motionproof.external_validation.datasets.registry import DATASETS, DatasetInfo
from motionproof.external_validation.provenance import store
from motionproof.external_validation.schemas.trial import Trial


@dataclass(frozen=True)
class RemoteFile:
    rel: str            # path below raw/
    url: str
    algo: str | None    # published checksum algorithm, or None if the publisher gives none
    expected: str | None
    group: str          # protocol subset the file belongs to


class Adapter:
    key: str = ""

    @property
    def info(self) -> DatasetInfo:
        return DATASETS[self.key]

    def remote_files(self, root: Path) -> list[RemoteFile]:
        raise NotImplementedError

    def import_(self, root: Path, groups: list[str] | None = None,
                progress: Any = None) -> dict[str, Any]:
        """Download (explicit user action) and verify every file of the selected groups."""
        files = [f for f in self.remote_files(root) if groups is None or f.group in groups]
        done = []
        for i, f in enumerate(files):
            entry = store.fetch(root, self.key, f.rel, f.url, f.algo, f.expected)
            done.append({"file": f.rel, "group": f.group, **entry})
            if progress:
                progress(i + 1, len(files), f.rel)
        return {"dataset": self.key, "files": done, "manifest": str(store.manifest_path(
            root, self.key))}

    def raw(self, root: Path) -> Path:
        return store.dataset_dir(root, self.key) / "raw"

    def available(self, root: Path) -> list[str]:
        manifest = store.load_manifest(root, self.key)
        return sorted(rel for rel in manifest["files"] if (self.raw(root) / rel).exists())

    def load(self, root: Path, rel: str) -> Trial:
        raise NotImplementedError

    def status(self, root: Path) -> dict[str, Any]:
        manifest = store.load_manifest(root, self.key)
        return {"dataset": self.key, "imported_files": len(self.available(root)),
                "manifest": manifest}
