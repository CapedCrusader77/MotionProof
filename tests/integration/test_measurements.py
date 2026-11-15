"""Measured component dimensions. Every data file here is SYNTHETIC with known truth."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import yaml
from typer.testing import CliRunner

from motionproof.cli.main import app
from motionproof.manufacturing import measurements as M
from motionproof.model import MechanicalModel

runner = CliRunner()


def _write(path: Path, rows: list[list[object]]) -> Path:
    lines = ["part_id,tolerance,value,unit,instrument,resolution,date,operator,notes"]
    lines += [",".join(str(x) for x in r) for r in rows]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _synthetic(path: Path, n: int, mean: float, sd: float, seed: int = 0) -> Path:
    rng = np.random.default_rng(seed)
    rows: list[list[object]] = []
    for i, v in enumerate(rng.normal(mean, sd, n)):
        rows.append([f"P{i:02d}", "output_shaft_diameter", f"{v:.5f}", "mm", "micrometer",
                     "0.001", "", "", ""])
        rows.append([f"P{i:02d}", "bearing_bore_diameter", f"{7.996 + rng.normal(0, 0.001):.5f}",
                     "mm", "bore gauge", "0.001", "", "", ""])
    return _write(path, rows)


def test_summary_capability_and_resolution(reference_model: MechanicalModel,
                                           tmp_path: Path) -> None:
    spec = reference_model.spec
    rows = M.load(_synthetic(tmp_path / "m.csv", 40, 7.9905, 0.0015), spec)
    s = M.summary(rows, spec)["tolerances"]["output_shaft_diameter"]
    assert s["n_parts"] == 40 and s["mean"] == pytest.approx(7.9905, abs=0.0006)
    assert s["std"] == pytest.approx(0.0015, rel=0.25)
    assert s["cp"] == pytest.approx(0.009 / (6 * s["std"]))
    # a 1 um micrometer on a 9 um tolerance band breaks the 10:1 gauge rule
    assert [w for w in s["warnings"] if "cannot resolve" in w]
    coarse = _write(tmp_path / "c.csv", [["P1", "output_shaft_diameter", "7.99", "mm",
                                          "caliper", "0.01", "", "", ""],
                                         ["P2", "output_shaft_diameter", "7.99", "mm",
                                          "caliper", "0.01", "", "", ""]])
    w = M.summary(M.load(coarse, spec), spec)["tolerances"]["output_shaft_diameter"]["warnings"]
    assert any("cannot resolve" in x for x in w) and any("imprecise" in x for x in w)


def test_units_are_converted_never_assumed(reference_model: MechanicalModel,
                                           tmp_path: Path) -> None:
    spec = reference_model.spec
    p = _write(tmp_path / "u.csv", [["P1", "output_shaft_diameter", "0.31458", "in", "", "",
                                     "", "", ""]])
    assert M.load(p, spec)[0]["value"] == pytest.approx(0.31458 * 25.4)
    p = _write(tmp_path / "n.csv", [["P1", "output_shaft_diameter", "7.99", "", "", "", "", "",
                                     ""]])
    with pytest.raises(M.MeasurementError, match="unit missing"):
        M.load(p, spec)
    p = _write(tmp_path / "x.csv", [["P1", "no_such", "1", "mm", "", "", "", "", ""]])
    with pytest.raises(M.MeasurementError, match="unknown tolerance"):
        M.load(p, spec)


def test_apply_and_evaluate_parts(reference_model: MechanicalModel, tmp_path: Path) -> None:
    spec = reference_model.spec
    rows = M.load(_synthetic(tmp_path / "m.csv", 12, 7.9905, 0.0015), spec)
    new = M.apply(spec, rows, "m.csv", "empirical")
    t = new.tolerance("output_shaft_diameter")
    assert t.distribution.type == "empirical" and len(t.distribution.samples) == 12  # type: ignore[union-attr]
    assert t.confidence.value == "measured" and "12 parts" in t.source
    assert spec.tolerance("output_shaft_diameter").confidence.value == "assumed"  # original
    parts = M.part_rows(rows, spec)
    assert len(parts) == 12 and "output_shaft_diameter" in parts["P00"]["measured"]
    assert "s2_backlash_sp" in parts["P00"]["unmeasured"]


def test_cli_template_summary_apply_evaluate(tmp_path: Path) -> None:
    ref = tmp_path / "ref"
    assert runner.invoke(app, ["reference", "create", str(ref)]).exit_code == 0
    model = str(ref / "model.yaml")
    r = runner.invoke(app, ["measurements", "template", model, "--parts", "2", "-o",
                            str(tmp_path / "t.csv")])
    assert r.exit_code == 0 and (tmp_path / "t.csv").read_text().count("P02") > 3
    data = _synthetic(tmp_path / "m.csv", 6, 7.9905, 0.0015)
    r = runner.invoke(app, ["measurements", "summary", model, str(data)])
    assert r.exit_code == 0 and "6 measured parts" in r.output
    r = runner.invoke(app, ["measurements", "apply", model, str(data), "-o", model])
    assert r.exit_code == 2 and "refusing to overwrite" in " ".join(r.output.split())
    out = ref / "model_measured.yaml"
    r = runner.invoke(app, ["measurements", "apply", model, str(data), "-o", str(out)])
    assert r.exit_code == 0 and MechanicalModel.load(out).spec.tolerance(
        "output_shaft_diameter").confidence.value == "measured"
    exp = tmp_path / "exp.yaml"
    exp.write_text(yaml.safe_dump({
        "model": "ref/model.yaml", "name": "parts",
        "task": {"type": "static_hold", "pose": {"shoulder": 0.0}},
        "constraints": [{"name": "tip", "metric": "ee_error_final", "op": "<=",
                         "limit": 0.003}]}), encoding="utf-8")
    r = runner.invoke(app, ["measurements", "evaluate", str(data), "--experiment", str(exp)])
    assert r.exit_code == 0 and "held at their design value" in " ".join(r.output.split())
