"""The published benchmark package: references are independent and agree with the suite."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2] / "benchmarks"
DATA = ROOT / "data"

pytestmark = pytest.mark.skipif(not (DATA / "suite_results.json").exists(),
                                reason="benchmark package not generated")


def test_reference_script_runs_without_motionproof(tmp_path: Path) -> None:
    out = subprocess.run([sys.executable, "-I", "-c",
                          "import sys, runpy; sys.argv = ['r', sys.argv[1]]; "
                          "runpy.run_path(sys.argv[1].replace('data', 'reference_calculations.py')"
                          ", run_name='__main__')", str(DATA)],
                         capture_output=True, text=True, cwd=tmp_path)
    assert out.returncode == 0, out.stderr
    refs = json.loads((DATA / "references.json").read_text(encoding="utf-8"))
    assert "no motionproof import" in refs["generated_by"]


def test_published_cross_check_all_agree() -> None:
    from benchmarks_publish import cross_check  # type: ignore[import-not-found]

    results = json.loads((DATA / "suite_results.json").read_text(encoding="utf-8"))
    refs = json.loads((DATA / "references.json").read_text(encoding="utf-8"))
    rows = cross_check(results, refs)
    graded = [r for r in rows if r["passed"] is not None]
    assert len(graded) >= 50
    assert all(r["passed"] for r in graded), [r for r in graded if not r["passed"]]


def test_manifest_matches_files() -> None:
    import hashlib

    manifest = json.loads((DATA / "MANIFEST.json").read_text(encoding="utf-8"))
    for rel, digest in manifest.items():
        if rel in ("references.json",):
            continue  # rewritten by the first test
        assert hashlib.sha256((DATA / rel).read_bytes()).hexdigest()[:16] == digest, rel


@pytest.fixture(autouse=True)
def _publish_module(monkeypatch: pytest.MonkeyPatch) -> None:
    import importlib.util

    spec = importlib.util.spec_from_file_location("benchmarks_publish", ROOT / "publish.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    monkeypatch.setitem(sys.modules, "benchmarks_publish", mod)
