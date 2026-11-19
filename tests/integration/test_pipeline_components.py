"""CAD import, feature detection, Level A geometry, experiments, calibration, allocation, CLI."""

from __future__ import annotations

import csv
import json
import threading
import time
from pathlib import Path

import cadquery as cq
import numpy as np
import pytest
import trimesh
import yaml
from typer.testing import CliRunner

from motionproof.cad.features import cylindrical_features, measure_shaft_in_bore
from motionproof.cad.geometry import analyse_mesh, convex_decompose, load_mesh, mass_properties_si
from motionproof.cad.importers import ImportFailure, import_file
from motionproof.calibration.fit import CalibrationConfig, calibrate, read_csv
from motionproof.cli.main import app
from motionproof.experiments.runner import Experiment, ExperimentConfig, ExperimentError
from motionproof.model import MechanicalModel
from motionproof.optimisation import allocation as alloc
from motionproof.reference import nema17_arm as ref
from motionproof.simulation.tasks import Reversal

REVERSAL = {"type": "reversal", "target": {"shoulder": 1.5708}, "joint": "shoulder",
            "payload_mass": 0.2}


# ---- geometry and import ----------------------------------------------------------------


def _bracket(tmp_path: Path) -> tuple[cq.Workplane, Path]:
    part = (cq.Workplane("XY").box(60, 40, 20).faces(">Z").workplane().hole(12.0)
            .faces(">Z").workplane().pushPoints([(20, 10)]).hole(5.0))
    path = tmp_path / "bracket.step"
    cq.exporters.export(part, str(path))
    return part, path


def test_step_import_reports_volume_units_and_features(tmp_path: Path) -> None:
    part, path = _bracket(tmp_path)
    inv = import_file(path, tmp_path / "model")
    assert inv["format"] == "step" and inv["units"]["geometry"] == "mm"
    comp = inv["components"][0]
    expected = 60 * 40 * 20 - np.pi * 6**2 * 20 - np.pi * 2.5**2 * 20
    assert comp["volume_mm3"] == pytest.approx(expected, rel=1e-9)
    assert comp["valid"] and comp["mass_kg"] is None  # no density -> no invented mass
    assert (tmp_path / "model" / "original" / "bracket.step").read_bytes() == path.read_bytes()
    feats = inv["feature_suggestions"][comp["id"]]
    assert sorted(round(f["diameter"], 6) for f in feats) == [5.0, 12.0]
    assert all(f["suggested_type"] == "bore" and f["status"] == "suggested" for f in feats)
    mesh = load_mesh(tmp_path / "model" / "geometry" / comp["mesh"])
    assert analyse_mesh(mesh).solid
    assert mesh.volume == pytest.approx(expected, rel=2e-3)  # tessellation error


def test_invalid_and_unsupported_files_fail_with_guidance(tmp_path: Path) -> None:
    bad = tmp_path / "broken.step"
    bad.write_text("ISO-10303-21; garbage", encoding="utf-8")
    with pytest.raises(ImportFailure, match="STEP"):
        import_file(bad, tmp_path / "m1")
    empty = tmp_path / "empty.stl"
    empty.write_bytes(b"")
    with pytest.raises(ImportFailure, match="empty"):
        import_file(empty, tmp_path / "m2")
    with pytest.raises(ImportFailure, match="unsupported"):
        import_file(tmp_path / "x.dwg", tmp_path / "m3") if (tmp_path / "x.dwg").write_bytes(
            b"1") else None


def test_stl_import_never_guesses_units(tmp_path: Path) -> None:
    box = trimesh.creation.box(extents=(10, 20, 30))
    box.export(tmp_path / "box.stl")
    inv = import_file(tmp_path / "box.stl", tmp_path / "a")
    assert inv["units"]["geometry"] == "unknown"
    assert inv["components"][0]["volume_mm3"] is None
    assert any("no length unit" in w for w in inv["warnings"])
    inv = import_file(tmp_path / "box.stl", tmp_path / "b", mesh_units="cm")
    assert inv["components"][0]["volume_mm3"] == pytest.approx(6000 * 1000.0)


def test_open_mesh_is_reported_not_repaired(tmp_path: Path) -> None:
    box = trimesh.creation.box(extents=(1, 1, 1))
    box.update_faces(np.arange(len(box.faces)) != 0)
    rep = analyse_mesh(box)
    assert not rep.watertight and rep.volume is None
    with pytest.raises(ValueError, match="watertight"):
        mass_properties_si(box, 1.0, 1000.0)


def test_convex_decomposition_reduces_recorded_error() -> None:
    u = (cq.Workplane("XY").box(100, 60, 40)
         .cut(cq.Workplane("XY").box(60, 60, 40).translate((0, 0, 10))))
    verts, faces = u.val().tessellate(0.05)
    mesh = trimesh.Trimesh([v.toTuple() for v in verts], faces)
    _, single = convex_decompose(mesh, max_pieces=1)
    pieces, err = convex_decompose(mesh, max_pieces=8, max_error=0.02)
    assert single == pytest.approx(240000 / 132000 - 1, rel=1e-3)
    assert err is not None and err < 0.02 and 2 <= len(pieces) <= 8


def test_mjcf_import_exposes_bodies_and_joints(tmp_path: Path) -> None:
    xml = tmp_path / "arm.xml"
    xml.write_text("""<mujoco><worldbody><body name="link" pos="0 0 1">
      <joint name="hinge" type="hinge" axis="0 1 0" range="-1 1" limited="true"/>
      <geom type="box" size="0.2 0.02 0.02" pos="0.2 0 0" mass="0.5"/></body></worldbody>
      </mujoco>""", encoding="utf-8")
    inv = import_file(xml, tmp_path / "m")
    assert inv["dynamics"]["joints"][0]["name"] == "hinge"
    assert inv["dynamics"]["joints"][0]["type"] == "revolute"
    assert inv["components"][0]["mass_kg"] == pytest.approx(0.5)
    assert (tmp_path / "m" / "geometry" / inv["components"][0]["mesh"]).is_file()


@pytest.mark.parametrize(("shaft", "bore", "offset"), [(9.98, 10.03, 0.0), (9.98, 10.03, 0.01)])
def test_level_a_clearance_matches_analytic(shaft: float, bore: float, offset: float) -> None:
    m = measure_shaft_in_bore(shaft, bore, 20.0, offset)
    assert m["min_radial_gap"] == pytest.approx((bore - shaft) / 2 - offset, abs=1e-7)
    assert m["interference_volume"] == pytest.approx(0.0, abs=1e-6)


def test_level_a_interference_is_detected() -> None:
    m = measure_shaft_in_bore(10.02, 10.00, 20.0)
    assert m["min_radial_gap"] == 0.0
    assert m["interference_volume"] == pytest.approx(np.pi / 4 * (10.02**2 - 10.0**2) * 20,
                                                     rel=1e-3)


def test_reference_geometry_regenerates_with_sampled_dimensions() -> None:
    geo = ref.measure_variant_geometry({"output_shaft_diameter": 7.988,
                                        "bearing_bore_diameter": 7.997,
                                        "housing_seat_diameter": 22.015,
                                        "mount_hole_dx": 0.04, "mount_hole_dy": -0.02,
                                        "s1_pin_radial_0": 0.015})
    md = geo["measured_dimensions_mm"]
    assert md["output_shaft_diameter"] == pytest.approx(7.988, abs=1e-9)
    assert md["housing_seat_diameter"] == pytest.approx(22.015, abs=1e-9)
    assert geo["interfaces"]["shaft_to_bearing"]["min_distance_mm"] == pytest.approx(
        0.0045, abs=1e-7)
    assert geo["mount_pattern_shift_mm"]["x"] == pytest.approx(0.04, abs=1e-7)
    assert geo["mount_pattern_shift_mm"]["y"] == pytest.approx(-0.02, abs=1e-7)
    changed = {c["component"] for c in geo["changed_components"]}
    assert {"output_shaft", "housing", "stage1_carrier"} <= changed


def test_reference_inertials_match_independent_mesh_integration(
        reference_model: MechanicalModel) -> None:
    """CAD-kernel mass properties vs. Trimesh integration of the exported STL."""
    comps = {c["id"]: c for c in reference_model.inventory["components"]}
    c = comps["upper_arm_link"]
    mesh = load_mesh(reference_model.geometry_dir / c["mesh"])
    mass, com, inertia = mass_properties_si(mesh, 1e-3, c["density_kg_m3"])
    assert mass == pytest.approx(c["mass_kg"], rel=2e-3)
    assert np.allclose(com, c["com_m"], atol=2e-5)
    assert np.allclose(inertia, c["inertia_com_kgm2"], rtol=5e-3, atol=1e-9)
    # the dynamics model carries exactly the combined body mass
    body = reference_model.inventory["bodies"]["upper_arm"]
    assert reference_model.mj_model.body_mass[2] == pytest.approx(body["mass"], rel=1e-8)
    journals = [f for f in cylindrical_features(
        ref.build_parts(None, {"output_shaft"})[0].solid) if f["external"]]
    assert journals[0]["diameter"] == pytest.approx(8.0)


# ---- experiments ----------------------------------------------------------------------


def _config(samples: int = 12, **kw: object) -> ExperimentConfig:
    return ExperimentConfig.model_validate({
        "name": "t", "task": REVERSAL,
        "sampling": {"method": "monte_carlo", "samples": samples, "seed": 4} | dict(kw),
        "constraints": [{"name": "lost", "metric": "lost_motion", "op": "<=", "limit": 0.005}]})


def test_experiment_resume_and_determinism(reference_model: MechanicalModel,
                                           tmp_path: Path) -> None:
    full = Experiment.create(reference_model, _config(), tmp_path / "full")
    full.run(reference_model)
    part = Experiment.create(reference_model, _config(), tmp_path / "part")
    cancel = threading.Event()
    part.run(reference_model, progress=lambda p: cancel.set() if p["done"] >= 5 else None,
             cancel=cancel)
    assert len(part.results()) == 5
    with part.results_path.open("a", encoding="utf-8") as f:
        f.write('{"id": "S000006", "truncat')  # simulate a crash in the middle of a write
    out = Experiment.open(tmp_path / "part").run(reference_model)
    assert out["status"] == "completed" and out["done"] == 12
    a = [r["metrics"] for r in full.results()]
    b = [r["metrics"] for r in part.results()]
    assert a == b  # resumed run is identical to the uninterrupted one


def test_parallel_run_matches_serial_and_cancels(reference_model: MechanicalModel,
                                                tmp_path: Path,
                                                monkeypatch: pytest.MonkeyPatch) -> None:
    """Scenarios evaluated in worker processes give the same records, in the same order."""
    import motionproof.experiments.runner as runner_mod
    monkeypatch.setattr(runner_mod, "MIN_PARALLEL", 2)  # exercise the pool on a small run
    serial = Experiment.create(reference_model, _config(20), tmp_path / "serial")
    serial.run(reference_model, workers=1)
    par = Experiment.create(reference_model, _config(20), tmp_path / "par")
    t0 = time.perf_counter()
    out = par.run(reference_model, workers=2)
    assert out["status"] == "completed" and out["done"] == 20
    assert time.perf_counter() - t0 < 600
    assert [r["id"] for r in par.results()] == [f"S{i:06d}" for i in range(1, 21)]
    assert [(r["metrics"], r["passed"]) for r in par.results()] ==         [(r["metrics"], r["passed"]) for r in serial.results()]
    # cancelling stops between batches and leaves a complete, resumable prefix
    cut = Experiment.create(reference_model, _config(20), tmp_path / "cut")
    stop = threading.Event()
    res = cut.run(reference_model, workers=2, cancel=stop,
                  progress=lambda p: stop.set() if p["done"] >= 3 else None)
    assert res["status"] == "cancelled" and 3 <= res["done"] < 20
    assert Experiment.open(tmp_path / "cut").run(reference_model, workers=2)["done"] == 20
    assert [r["metrics"] for r in cut.results()] == [r["metrics"] for r in serial.results()]


def test_manifest_is_immutable_and_model_changes_are_refused(
        reference_model: MechanicalModel, tmp_path: Path) -> None:
    exp = Experiment.create(reference_model, _config(4), tmp_path / "e")
    with pytest.raises(ExperimentError, match="immutable"):
        Experiment.create(reference_model, _config(4), tmp_path / "e")
    raw = reference_model.spec.model_dump(mode="json", by_alias=True)
    raw["drives"]["shoulder"]["gearbox"]["stiffness"] = 900.0
    changed = MechanicalModel.from_dict(raw, reference_model.directory)
    with pytest.raises(ExperimentError, match="differs"):
        exp.run(changed)
    exp.run()  # the snapshot inside the manifest still runs
    assert exp.replay("S000002")["reproduced"]


def test_unknown_constraint_metric_fails_before_running(
        reference_model: MechanicalModel, tmp_path: Path) -> None:
    cfg = ExperimentConfig.model_validate({
        "name": "t", "task": {"type": "static_hold", "pose": {"shoulder": 0.0}},
        "constraints": [{"name": "x", "metric": "lost_motion", "op": "<=", "limit": 1}]})
    with pytest.raises(ExperimentError, match="not produced by task"):
        Experiment.create(reference_model, cfg, tmp_path / "e")
    assert not (tmp_path / "e" / "manifest.json").exists()


def test_regression_heavy_payload_stays_numerically_valid(
        reference_model: MechanicalModel) -> None:
    """A stiff explicit servo on the held elbow went unstable above ~0.5 kg payload."""
    for payload in (0.5, 0.6, 1.0):
        res = reference_model.simulate(
            Reversal(target={"shoulder": 0.3}, joint="shoulder", payload_mass=payload),
            keep_trace=False)
        assert res.valid, res.message


# ---- allocation -----------------------------------------------------------------------


def test_scaled_spec_and_cost_model(reference_model: MechanicalModel) -> None:
    spec = alloc.scaled_spec(reference_model.spec, {"s2_backlash_sp": 0.5})
    t0, t1 = reference_model.spec.tolerance("s2_backlash_sp"), spec.tolerance("s2_backlash_sp")
    assert t1.upper - t1.lower == pytest.approx(0.5 * (t0.upper - t0.lower))
    assert t1.distribution.std == pytest.approx(0.5 * t0.distribution.std)  # type: ignore[union-attr]
    cfg = alloc.AllocationConfig(tolerances=["a", "b"], objective_metric="m",
                                 costs={"a": alloc.CostTerm(fixed=1.0, coefficient=2.0,
                                                            exponent=2.0)})
    assert alloc.cost(cfg, {"a": 0.5, "b": 2.0}) == pytest.approx(1 + 2 / 0.25 + 1 / 2.0)
    assert alloc.pareto_front([(1, 5), (2, 3), (3, 4), (4, 1)]) == [0, 1, 3]


def test_allocation_screen_recommends_and_verifies(reference_model: MechanicalModel) -> None:
    tols = ["s2_backlash_sp", "s2_backlash_pr", "s2_planet_bearing_clearance"]
    res = alloc.allocate(reference_model, _config(), alloc.AllocationConfig(
        tolerances=tols, candidates=4, samples=12, verify_samples=20, seed=1,
        objective_metric="lost_motion", target_pass_fraction=0.5))
    assert res["status"] == "completed" and len(res["candidates"]) == 4
    assert res["candidates"][0]["id"] == "current"
    assert res["candidates"][0]["cost"] == pytest.approx(3.0)
    assert "relative cost index" in res["cost_label"]
    assert any(c["pareto"] for c in res["candidates"])
    if res["recommended"]:
        assert res["verification"]["seed"] != 1 and "meets_target" in res["verification"]


# ---- calibration ----------------------------------------------------------------------

CAL_TASK = {"type": "reversal", "target": {"j": 0.3}, "joint": "j", "excursion": 0.2,
            "move_time": 0.8, "settle": 0.5}


def _record(model: MechanicalModel, path: Path, backlash: float, friction: float,
            noise: float, seed: int, task: dict) -> None:
    import dataclasses

    from motionproof.calibration.fit import CalibrationConfig as _C

    cfg = _C.model_validate({"task": task, "signals": {}, "parameters": [
        {"joint": "j", "name": "backlash", "lower": 0, "upper": 1}]})
    variant = model.variant({})
    variant.joints["j"] = dataclasses.replace(variant.joints["j"], backlash=backlash,
                                              friction=friction)
    res = model.engine.run(variant, cfg.task, keep_trace=True, trace_points=1500)
    rng = np.random.default_rng(seed)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["time_ms", "angle_deg"])
        for t, q in zip(res.trace["t"], res.trace["q_out"], strict=True):
            w.writerow([f"{1000 * t:.3f}", f"{np.degrees(q + rng.normal(0, noise)):.7f}"])


def _cal_config(params: list[dict]) -> CalibrationConfig:
    return CalibrationConfig.model_validate({
        "task": CAL_TASK, "time_column": "time_ms", "time_unit": "ms",
        "signals": {"output_angle": {"column": "angle_deg", "unit": "deg"}},
        "parameters": params})


def test_calibration_recovers_known_backlash_on_separate_holdout(
        single_joint, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    model = single_joint(gravity=False, friction=0.4)
    true = 0.0080
    _record(model, tmp_path / "cal.csv", true, 0.4, 2e-5, 1, CAL_TASK)
    _record(model, tmp_path / "hold.csv", true, 0.4, 2e-5, 2, CAL_TASK)
    cfg = _cal_config([{"joint": "j", "name": "backlash", "lower": 0.0, "upper": 0.02}])
    res = calibrate(model, cfg, read_csv(tmp_path / "cal.csv", cfg),
                    read_csv(tmp_path / "hold.csv", cfg))
    est = res["parameters"][0]
    assert est["estimate"] == pytest.approx(true, abs=2e-4)
    assert res["holdout"]["split"] == "separate_recording"
    assert res["assessment"] == "holdout_consistent"
    assert res["holdout"]["errors"]["output_angle"]["rmse"] < 1e-4
    assert not any("independent recording" in w for w in res["warnings"])


def test_calibration_flags_unidentifiable_parameter_and_weak_holdout(
        single_joint, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    """Gearbox efficiency cannot be seen in an output-angle trace without load."""
    model = single_joint(gravity=False, friction=0.0)
    _record(model, tmp_path / "cal.csv", 0.006, 0.0, 2e-5, 3, CAL_TASK)
    cfg = _cal_config([{"joint": "j", "name": "backlash", "lower": 0.0, "upper": 0.02},
                       {"joint": "j", "name": "efficiency", "lower": 0.5, "upper": 1.0}])
    res = calibrate(model, cfg, read_csv(tmp_path / "cal.csv", cfg))
    text = " ".join(res["warnings"])
    assert "efficiency" in text and any(k in text for k in (
        "not identifiable", "poorly identified", "strongly correlated"))
    assert res["holdout"]["split"] == "same_recording_tail"
    assert "not an independent recording" in text


def test_calibration_csv_validation(tmp_path: Path) -> None:
    from motionproof.calibration.fit import CalibrationError

    p = tmp_path / "bad.csv"
    p.write_text("time_ms,angle_deg\n0,1\n0,2\n" + "\n".join(f"{i},1" for i in range(1, 12)),
                 encoding="utf-8")
    cfg = _cal_config([{"joint": "j", "name": "backlash", "lower": 0.0, "upper": 0.02}])
    with pytest.raises(CalibrationError, match="strictly increasing"):
        read_csv(p, cfg)
    p.write_text("t,angle\n0,1\n", encoding="utf-8")
    with pytest.raises(CalibrationError, match="missing columns"):
        read_csv(p, cfg)


# ---- CLI ------------------------------------------------------------------------------


def test_cli_workflow(tmp_path: Path) -> None:
    runner = CliRunner()
    assert "tolerance-to-dynamics" in runner.invoke(app, ["--help"]).output
    model_dir = tmp_path / "ref"
    assert runner.invoke(app, ["reference", "create", str(model_dir)]).exit_code == 0
    model_file = str(model_dir / "model.yaml")
    r = runner.invoke(app, ["model", "validate", model_file])
    assert r.exit_code == 0 and "ready_with_warnings" in r.output
    r = runner.invoke(app, ["tolerance", "inspect", model_file])
    assert r.exit_code == 0 and "transition fit" in r.output
    out = tmp_path / "variants.json"
    r = runner.invoke(app, ["assembly", "generate-variants", model_file, "--samples", "3",
                            "-o", str(out)])
    assert r.exit_code == 0 and len(json.loads(out.read_text())["variants"]) == 3
    r = runner.invoke(app, ["inspect", str(model_dir / "geometry" / "assembly.step"), "--json"])
    assert r.exit_code == 0 and '"format": "step"' in r.output

    exp_file = tmp_path / "experiment.yaml"
    exp_file.write_text(yaml.safe_dump({
        "model": "ref/model.yaml", "name": "cli", "task": REVERSAL,
        "sampling": {"method": "monte_carlo", "samples": 10, "seed": 2},
        "constraints": [{"name": "lost", "metric": "lost_motion", "op": "<=",
                         "limit": 0.004}]}), encoding="utf-8")
    home = ["--home", str(tmp_path / "ws")]
    r = runner.invoke(app, ["experiment", "run", str(exp_file), *home])
    assert r.exit_code in (0, 1) and "EXP_001" in r.output, r.output
    assert runner.invoke(app, ["experiment", "inspect", "EXP_001", *home]).exit_code == 0
    r = runner.invoke(app, ["experiment", "replay", "EXP_001", *home])
    assert r.exit_code == 0 and "reproduced" in r.output
    r = runner.invoke(app, ["experiment", "analyse", "EXP_001", "lost_motion", *home])
    assert r.exit_code == 0 and "Spearman" in r.output
    r = runner.invoke(app, ["experiment", "compare", "EXP_001", "S000001", "S000002", *home])
    assert r.exit_code == 0
    r = runner.invoke(app, ["optimise", "EXP_001", "lost_motion", "--algorithm", "corners",
                            "--budget", "12", *home])
    assert r.exit_code in (0, 1)
    assert "confirmed by fresh simulation: True" in " ".join(r.output.split())
    r = runner.invoke(app, ["report", "EXP_001", "-o", str(tmp_path / "rep"), *home])
    assert r.exit_code == 0
    assert (tmp_path / "rep" / "report.pdf").read_bytes()[:4] == b"%PDF"
    assert "Limitations" in (tmp_path / "rep" / "report.md").read_text(encoding="utf-8")

    r = runner.invoke(app, ["experiment", "inspect", "EXP_404", *home])
    assert r.exit_code == 2 and "not found" in r.output
    r = runner.invoke(app, ["model", "validate", str(tmp_path / "missing.yaml")])
    assert r.exit_code == 2


def test_joint_is_derived_from_two_exported_poses(tmp_path: Path) -> None:
    """Two STEP exports of one assembly: the moved solids define the hinge exactly."""
    from motionproof.cad.configurations import compare_configurations

    def export(angle: float, name: str) -> Path:
        assy = cq.Assembly(name="arm")
        assy.add(cq.Workplane("XY").box(40, 40, 20), name="base")
        link = cq.Workplane("XY").box(100, 10, 10).translate((50, 0, 30))
        pin = cq.Workplane("XY").circle(3).extrude(12).translate((0, 0, 24))
        rot = cq.Location((0, 0, 0), (0, 0, 1), angle)
        assy.add(link, name="link", loc=rot)
        assy.add(pin, name="pin", loc=rot)
        path = tmp_path / name
        assy.save(str(path))
        return path

    res = compare_configurations(export(0.0, "a.step"), export(35.0, "b.step"))
    assert res["fixed"] == ["base"] and res["unmatched"] == []
    (joint,) = res["joints"]
    assert joint["type"] == "revolute" and sorted(joint["components"]) == ["link", "pin"]
    assert joint["angle_deg"] == pytest.approx(35.0, abs=1e-6)
    assert np.allclose(joint["axis"], [0, 0, 1], atol=1e-9)
    assert np.allclose(joint["point_mm"][:2], [0, 0], atol=1e-6)
