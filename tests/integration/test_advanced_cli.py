"""Advanced CLI commands on the reference design (SYNTHETIC data only)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import yaml
from typer.testing import CliRunner

from motionproof.cli.main import app
from motionproof.scans import synthetic as S

runner = CliRunner()


def _flat(out: str) -> str:
    return " ".join(out.split())


def test_scan_inspect_and_compare(tmp_path: Path) -> None:
    ref = tmp_path / "ref"
    assert runner.invoke(app, ["reference", "create", str(ref)]).exit_code == 0
    pts = S.cylinder_scan(7.982, 41.0, 8000, noise=0.004, seed=1)[:, [0, 2, 1]] \
        + np.array([0.0, 11.0, 0.0])
    scan = S.write_xyz(tmp_path / "synthetic_shaft.xyz", pts, "mm", "test")
    r = runner.invoke(app, ["scan", "inspect", str(scan)])
    assert r.exit_code == 0 and "NOT STATED" in r.output
    r = runner.invoke(app, ["scan", "compare", str(scan),
                            str(ref / "geometry" / "meshes" / "output_shaft.stl"), "--units", "mm",
                            "--nominal-units", "mm", "--lock", "ry", "--accept-rms", "0.03",
                            "--cylinder", "0,11,0,0,1,0,4,1,39"])
    out = _flat(r.output)
    assert r.exit_code == 0, out
    assert "valid for inspection: yes" in out and "diameter 7.98" in out
    r = runner.invoke(app, ["scan", "compare", str(scan),
                            str(ref / "geometry" / "meshes" / "housing.stl"), "--units", "mm",
                            "--nominal-units", "mm", "--accept-rms", "0.03"])
    assert r.exit_code == 1 and "NO - do not use dimensions" in _flat(r.output)


def test_batch_hardware_degradation_benchmark(tmp_path: Path) -> None:
    ref = tmp_path / "ref"
    runner.invoke(app, ["reference", "create", str(ref)])
    proc = tmp_path / "proc.yaml"
    proc.write_text(yaml.safe_dump({
        "process": {"name": "p", "features": [{
            "feature": "output_shaft_diameter", "process": "turning", "target": 7.9905,
            "unit": "mm", "lower_limit": 7.986, "upper_limit": 7.995,
            "sources": [{"level": "batch", "std": 0.001, "basis": "assumed"},
                        {"level": "part", "std": 0.001, "basis": "assumed"}]}]},
        "plan": {"batches": 3, "setups_per_batch": 2, "parts_per_setup": 10}}), encoding="utf-8")
    r = runner.invoke(app, ["manufacturing", "batch", str(proc)])
    out = _flat(r.output)
    assert r.exit_code == 0 and "60 parts" in out and "imprecise" in out
    hw = tmp_path / "hw.yaml"
    hw.write_text(yaml.safe_dump({
        "model": "ref/model.yaml",
        "test": {"joint": "shoulder", "centre": 1.5708, "excursion": 0.1, "move_time": 1.0},
        "limits": {"travel_min": 1.3, "travel_max": 1.8, "max_speed": 0.5, "max_duration": 10}}),
        encoding="utf-8")
    r = runner.invoke(app, ["hardware", "test", str(hw)])
    assert r.exit_code == 2 and "not confirmed" in _flat(r.output)
    r = runner.invoke(app, ["hardware", "test", str(hw), "--confirm"])
    assert r.exit_code == 0 and "SIMULATED DEVICE: completed" in _flat(r.output)
    deg = tmp_path / "deg.yaml"
    deg.write_text(yaml.safe_dump({
        "model": "ref/model.yaml", "pose": {"shoulder": 0.0}, "cycles": [0, 1e6],
        "mechanisms": [{"joint": "shoulder", "parameter": "backlash", "kind": "linear",
                        "rate": 1e-8, "basis": "assumed"}],
        "constraints": [{"name": "tip", "metric": "ee_error_final", "op": "<=",
                         "limit": 0.003}]}), encoding="utf-8")
    r = runner.invoke(app, ["degradation", "run", str(deg)])
    assert r.exit_code == 0 and "MODEL-BASED PROJECTION" in r.output
    assert "simulated" in runner.invoke(app, ["hardware", "devices"]).output
    assert "gearbox" in runner.invoke(app, ["benchmark", "list"]).output
    out_md = tmp_path / "bench.md"
    r = runner.invoke(app, ["benchmark", "run", "B", "hardware", "--write", str(out_md)])
    assert r.exit_code == 0 and "NOT RUN" in r.output
    text = out_md.read_text(encoding="utf-8")
    assert "Two-stage planetary gearbox" in text and "No physical rig" in text
