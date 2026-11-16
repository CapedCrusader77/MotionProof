"""KUKA KR300 R2500 identification benchmark adapter (prepared data without raw runs).

The archive is RAR. It is extracted with the system ``tar`` (bsdtar/libarchive, built into
Windows 10+ and most Linux distributions); the original archive is kept unmodified.
Inverse-identification file: u = [q(6), dq(6), ddq(6)] in deg, deg/s, deg/s^2; y = motor
torques in N*m; time in s. The benchmark's own train/test split is used as is.
"""

from __future__ import annotations

import math
import os
import shutil
import subprocess
from pathlib import Path

from motionproof.external_validation.adapters.base import Adapter, RemoteFile
from motionproof.external_validation.schemas.trial import SchemaError, Signal, Trial

BASE = "https://fdm-fallback.uni-kl.de/TUK/FB/MV/WSKL/0001"
ARCHIVE = "Robot_Identification_Benchmark_Without_Raw_Data.rar"
ARCHIVE_MD5 = "6fffa993f60d65f85100bad053888df2"
D2R = math.pi / 180.0


def libarchive_tar() -> str:
    """A tar that can read RAR: libarchive's bsdtar (GNU tar cannot)."""
    candidates = [shutil.which("bsdtar"), str(Path(os.environ.get("SystemRoot", "C:/Windows"))
                                              / "System32" / "tar.exe"), shutil.which("tar")]
    for c in candidates:
        if c and Path(c).exists():
            v = subprocess.run([c, "--version"], capture_output=True, text=True).stdout
            if "libarchive" in v:
                return c
    raise SchemaError("extracting the RAR archive needs libarchive's bsdtar (built into "
                      "Windows 10+; 'apt install libarchive-tools' on Linux)")


class KukaKR300(Adapter):
    key = "kuka-kr300"

    def remote_files(self, root: Path) -> list[RemoteFile]:
        return [RemoteFile(ARCHIVE, f"{BASE}/{ARCHIVE}", "md5", ARCHIVE_MD5, "benchmark")]

    def extracted(self, root: Path) -> Path:
        out = self.raw(root).parent / "extracted"
        mat = out / "inverse_identification_without_raw_data.mat"
        if not mat.exists():
            tar = libarchive_tar()
            out.mkdir(parents=True, exist_ok=True)
            subprocess.run([tar, "-xf", str(self.raw(root) / ARCHIVE), "-C", str(out)],
                           check=True)
        return out

    def load(self, root: Path, rel: str) -> Trial:
        import scipy.io as sio

        if rel not in ("train", "test"):
            raise SchemaError("KUKA trials are 'train' and 'test' (benchmark split)")
        d = sio.loadmat(self.extracted(root) / "inverse_identification_without_raw_data.mat")
        u, y, t = d[f"u_{rel}"], d[f"y_{rel}"], d[f"time_{rel}"].ravel()
        if u.shape[0] != 18 or y.shape[0] != 6:
            raise SchemaError(f"unexpected shapes u {u.shape}, y {y.shape}")
        signals: dict[str, Signal] = {}
        for j in range(6):
            a = f"A{j + 1}"
            signals[f"{a}/q"] = Signal(f"{a}/q", u[j] * D2R, "rad", f"u_{rel}[{j}]",
                                       "deg to rad", t)
            signals[f"{a}/dq"] = Signal(f"{a}/dq", u[6 + j] * D2R, "rad/s",
                                        f"u_{rel}[{6 + j}]", "deg/s to rad/s", t)
            signals[f"{a}/ddq"] = Signal(f"{a}/ddq", u[12 + j] * D2R, "rad/s^2",
                                         f"u_{rel}[{12 + j}]", "deg/s^2 to rad/s^2", t)
            signals[f"{a}/tau"] = Signal(f"{a}/tau", y[j], "N*m", f"y_{rel}[{j}]",
                                         "none (motor torque)", t)
        return Trial(self.key, rel, ARCHIVE, signals, {"benchmark_split": rel})

    def available_files(self, root: Path) -> list[str]:
        return [ARCHIVE] if (self.raw(root) / ARCHIVE).exists() else []

    def available(self, root: Path) -> list[str]:
        return ["train", "test"] if (self.raw(root) / ARCHIVE).exists() else []

