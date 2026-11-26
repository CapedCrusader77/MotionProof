"""External validation framework: adapters, integrity, schema, alignment, leakage, metrics,
holdout evaluation, reproducibility and provenance.

All fixtures are tiny files written here; nothing is downloaded. Fixture data are generated
for the tests and are never registered as experimental data.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import numpy as np
import pytest

from motionproof.external_validation.adapters import ADAPTERS
from motionproof.external_validation.experiments import runs
from motionproof.external_validation.metrics.errors import by_group, errors
from motionproof.external_validation.provenance import store
from motionproof.external_validation.reports import record
from motionproof.external_validation.schemas.trial import SchemaError, Signal, align


def _register(root: Path, key: str, rel: str) -> None:
    """Enter an already written raw file in the manifest, as an import would."""
    m = store.load_manifest(root, key)
    m["files"][rel] = store.verify(store.dataset_dir(root, key) / "raw" / rel, None, None)
    store.save_manifest(root, key, m)


# ---- schema and units -----------------------------------------------------------------------

def test_signal_rejects_missing_samples_and_non_si_units() -> None:
    with pytest.raises(SchemaError, match="non-finite"):
        Signal("q", np.array([0.0, np.nan, 1.0]), "rad", "q")
    with pytest.raises(SchemaError, match="not an SI unit"):
        Signal("q", np.array([0.0, 1.0]), "deg", "q")
    with pytest.raises(SchemaError, match="strictly increasing"):
        Signal("q", np.array([0.0, 1.0, 2.0]), "rad", "q", time_s=np.array([0.0, 0.1, 0.1]))


def test_alignment_interpolates_and_never_extrapolates() -> None:
    s = Signal("q", np.array([0.0, 2.0, 4.0]), "rad", "q", time_s=np.array([0.0, 1.0, 2.0]))
    assert np.allclose(align(np.array([0.5, 1.5]), s), [1.0, 3.0])
    with pytest.raises(SchemaError, match="extrapolate"):
        align(np.array([2.5]), s)


def test_nist_adapter_converts_units_and_reads_conditions(tmp_path: Path) -> None:
    raw = tmp_path / "nist-ur5" / "raw"
    raw.mkdir(parents=True)
    rows = []
    for i in range(5):
        groups = [[0.008 * i]] + [[10.0 * i + j for j in range(6)] for _ in range(11)] \
            + [[25.0 + i] * 6]
        rows.append("(" + ", ".join("[" + ", ".join(map(str, g)) + "]" for g in groups) + ")")
    (raw / "coldstart_halfspeed_payload45lb_2.csv").write_text("\n".join(rows) + "\n")
    _register(tmp_path, "nist-ur5", "coldstart_halfspeed_payload45lb_2.csv")
    tr = ADAPTERS["nist-ur5"].load(tmp_path, "coldstart_halfspeed_payload45lb_2.csv")
    assert tr.conditions == {"cold_start": True, "speed": "half", "payload_kg": 20.412,
                             "payload_lb": 45, "repeat": 2}
    assert tr.signals["J2/q"].values[1] == pytest.approx(11.0 * math.pi / 180)
    assert tr.signals["J1/temperature"].values[0] == pytest.approx(298.15)
    assert tr.signals["J1/temperature"].unit == "K"


def test_malformed_rows_are_rejected(tmp_path: Path) -> None:
    raw = tmp_path / "nist-ur5" / "raw"
    raw.mkdir(parents=True)
    (raw / "halfspeed_payload16lb_1.csv").write_text("([1.0], [1, 2, 3])\n")
    with pytest.raises(SchemaError, match="groups"):
        ADAPTERS["nist-ur5"].load(tmp_path, "halfspeed_payload16lb_1.csv")


def test_anchor_parquet_long_format(tmp_path: Path) -> None:
    pa = pytest.importorskip("pyarrow")
    import pyarrow.parquet as pq

    raw = tmp_path / "anchor-lab" / "raw" / "h1_elbow_teststand"
    raw.mkdir(parents=True)
    name = "h1-elbow-teststand-sysid-1p0hz-amp-small-position9"
    tn, fields, vals = [], [], []
    for i in range(10):
        for f, v in (("elbow_q", 0.1 * i), ("elbow_temp", 30.0), ("elbow_tau", 1.0)):
            tn.append(1_000_000_000 + 2_000_000 * i)
            fields.append(f)
            vals.append(v)
    pq.write_table(pa.table({"time_ns": tn, "experiment": [name] * len(tn), "field": fields,
                             "value": vals}), raw / f"{name}.parquet")
    tr = ADAPTERS["anchor-lab"].load(tmp_path, f"h1_elbow_teststand/{name}.parquet")
    assert tr.conditions["position"] == 9 and tr.conditions["frequency_hz"] == 1.0
    assert tr.signals["elbow/temperature"].values[0] == pytest.approx(303.15)
    assert tr.signals["elbow/q"].time_s[1] == pytest.approx(0.002)  # type: ignore[index]
    assert tr.t0_ns == 1_000_000_000
    with pytest.raises(SchemaError, match="required signals missing"):
        tr.require("elbow/dq")


# ---- integrity ---------------------------------------------------------------------------

def test_download_is_verified_and_original_never_overwritten(tmp_path: Path) -> None:
    src = tmp_path / "source.bin"
    src.write_bytes(b"measured data")
    md5 = hashlib.md5(b"measured data").hexdigest()
    root = tmp_path / "data"
    e = store.fetch(root, "kuka-kr300", "a.bin", src.as_uri(), "md5", md5)
    assert e["integrity"] == "verified against published checksum"
    src.write_bytes(b"changed upstream")
    store.fetch(root, "kuka-kr300", "a.bin", src.as_uri(), "md5", md5)  # not re-downloaded
    assert (root / "kuka-kr300" / "raw" / "a.bin").read_bytes() == b"measured data"
    with pytest.raises(store.IntegrityError):
        store.fetch(root, "kuka-kr300", "b.bin", src.as_uri(), "md5", md5)
    manifest = json.loads((root / "kuka-kr300" / "manifest.json").read_text())
    assert manifest["licence"] and manifest["citation"] and manifest["files"]["a.bin"]["url"]


# ---- metrics ------------------------------------------------------------------------------

def test_error_metrics() -> None:
    obs, pred = np.array([1.0, 2.0, 3.0, 4.0]), np.array([1.0, 2.0, 2.0, 6.0])
    e = errors(obs, pred)
    assert e["rmse"] == pytest.approx(math.sqrt(5 / 4))
    assert e["mae"] == pytest.approx(0.75)
    assert e["max_abs"] == pytest.approx(2.0)
    assert e["mean_error"] == pytest.approx(-0.25)
    g = by_group(obs, pred, ["a", "a", "b", "b"])
    assert g["a"]["rmse"] == 0.0 and g["b"]["n"] == 2
    with pytest.raises(ValueError):
        errors(obs, pred[:3])


def test_leakage_guard() -> None:
    with pytest.raises(runs.LeakageError):
        runs.check_disjoint(["t1", "t2"], ["t2", "t3"])


# ---- transmission-error protocol on a fixture -------------------------------------------

def _te_fixture(root: Path, validation_scale: float = 1.0) -> None:
    rng = np.random.default_rng(0)
    for role in ("identification", "validation"):
        for axis in ("axis_2", "axis_3"):
            d = store.dataset_dir(root, "stuttgart-te") / "raw" / role / axis
            d.mkdir(parents=True, exist_ok=True)
            for v in (-0.1, 0.1):
                q = np.arange(-1.0, 1.0, 2e-4) * np.sign(v)
                te = (1e-3 + 2e-4 * np.sign(v) + 5e-4 * np.sin(37 * q) + 2e-4 * np.cos(120 * q))
                if role == "validation":
                    te = te * validation_scale
                te = te + rng.normal(0, 1e-5, len(q))
                rel = f"{role}/{axis}/q_set_dot={v:.4f}.csv"
                rows = "\n".join(f"{a},{b},{c}" for a, b, c in zip(q + te, q, te, strict=True))
                (d / f"q_set_dot={v:.4f}.csv").write_text("theta,q_set,theta_TE\n" + rows)
                _register(root, "stuttgart-te", rel)


def test_te_fit_uses_identification_only_and_predicts_holdout(tmp_path: Path) -> None:
    _te_fixture(tmp_path)
    r = runs.run("transmission-error", tmp_path)
    assert r["status"] == "PASS"
    ax = r["axes"]["axis_2"]
    assert 37 in ax["orders"] and 120 in ax["orders"]
    assert ax["fit"]["parameters"]["b_half"] == pytest.approx(2e-4, abs=2e-5)
    assert all(t.startswith("identification/") for t in ax["identification_trials"])
    assert all(t.startswith("validation/") for t in ax["validation_trials"])
    # changing only the validation files must not change the fitted model
    other = tmp_path / "other"
    _te_fixture(other, validation_scale=3.0)
    r2 = runs.run("transmission-error", other)
    assert r2["axes"]["axis_2"]["fit"] == ax["fit"]
    assert r2["axes"]["axis_2"]["orders"] == ax["orders"]
    assert r2["status"] == "FAIL"  # and the holdout honestly reports the mismatch


def test_runs_are_recorded_reproducibly_with_provenance(tmp_path: Path) -> None:
    _te_fixture(tmp_path)
    a = record.save(tmp_path, runs.run("transmission-error", tmp_path))
    b = record.save(tmp_path, runs.run("transmission-error", tmp_path))
    assert (a["id"], b["id"]) == ("VALIDATION_001", "VALIDATION_002")
    ra, rb = a["result"], b["result"]
    assert ra["axes"]["axis_3"]["metrics"] == rb["axes"]["axis_3"]["metrics"]
    assert len(a["files"]) == 8 and all("sha256" in f for f in a["files"].values())
    assert (tmp_path / "runs" / "VALIDATION_001" / "report.md").exists()
    assert ra["reproduce"] == "motionproof external validate transmission-error"
    ev = ra["evidence"]
    assert {e["evidence"] for e in ev} == {"EXTERNAL_CALIBRATION", "EXTERNAL_VALIDATION"}
    assert all("not a measurement of the MotionProof reference gearbox" in e["scope"]
               for e in ev)
    assert all("doi:10.18419/DARUS-5760" in e["citation"] for e in ev)
    assert [r["id"] for r in record.list_runs(tmp_path)] == ["VALIDATION_001", "VALIDATION_002"]


def test_missing_data_is_not_run_and_tcp_is_insufficient(tmp_path: Path) -> None:
    for pid in ("h1-friction", "so101-tracking", "kuka-inverse", "nist-tracking"):
        assert runs.run(pid, tmp_path)["status"] == "NOT RUN"
    assert runs.run("nist-tcp", tmp_path)["status"] == "INSUFFICIENT DATA"


def test_joint_friction_fit_recovers_known_parameters() -> None:
    t = np.arange(0, 20, 0.002)
    q = 0.6 * np.sin(2 * np.pi * 0.5 * t)
    dq = np.gradient(q, t)
    ddq = np.gradient(dq, t)
    tau = 0.05 * ddq + 0.3 * dq + 0.8 * np.tanh(dq / 0.02) + 2.0 * np.sin(q) + 0.1
    d = {"t": t, "q": q, "dq": dq, "ddq": ddq, "tau": tau}
    r = runs._joint_validation([d], [d], ["x"])
    p = r["model"]["fit"]["parameters"]
    assert p["c_viscous"] == pytest.approx(0.3, rel=1e-6)
    assert p["F_coulomb"] == pytest.approx(0.8, rel=1e-6)
    assert r["model"]["validation"]["rmse"] < 1e-9 < r["baseline"]["validation"]["rmse"]


def _toothed(teeth: int, r_root: float, r_tip: float, tooth_angle: float, internal: bool,
             height: float = 4.0):  # type: ignore[no-untyped-def]
    """A gear with straight-sided sector teeth: the tooth thickness on any circle r is exactly
    r * tooth_angle, which makes the measurement checkable."""
    import trimesh
    from shapely.geometry import Point, Polygon

    sectors = []
    for k in range(teeth):
        a = 2 * math.pi * k / teeth
        arc = np.linspace(a - tooth_angle / 2, a + tooth_angle / 2, 40)
        lo, hi = (r_tip, r_root) if internal else (r_root, r_tip)
        pts = [(lo * math.cos(t), lo * math.sin(t)) for t in arc] + \
              [(hi * math.cos(t), hi * math.sin(t)) for t in arc[::-1]]
        sectors.append(Polygon(pts))
    if internal:
        shape = Point(0, 0).buffer(r_root + 3.0, 2048).difference(Point(0, 0).buffer(r_root, 2048))
    else:
        shape = Point(0, 0).buffer(r_root, 2048)
    for s in sectors:
        shape = shape.union(s.buffer(1e-6))
    # side walls only: a horizontal cut through them is exactly the outline of the shape
    vertices, faces = [], []
    for ring in [shape.exterior, *shape.interiors]:
        xy = np.asarray(ring.coords)[:-1]
        n, base = len(xy), len(vertices)
        vertices += [(x, y, 0.0) for x, y in xy] + [(x, y, height) for x, y in xy]
        for i in range(n):
            j = (i + 1) % n
            faces += [(base + i, base + j, base + n + j), (base + i, base + n + j, base + n + i)]
    return trimesh.Trimesh(np.array(vertices), np.array(faces), process=False)


@pytest.mark.parametrize("internal", [False, True])
def test_print_file_tooth_thickness_is_measured_on_the_pitch_circle(internal: bool) -> None:
    from motionproof.external_validation.adapters import compact_sspg as cs

    teeth, module = 40, 1.0
    rp = module * teeth / 2
    angle = 0.9 * math.pi / teeth                      # teeth 10 % thinner than the space
    mesh = _toothed(teeth, rp + (1.25 if internal else -1.25), rp + (-1.0 if internal else 1.0),
                    angle, internal)
    r = cs.tooth_thickness(mesh, 2.0, teeth, module, internal)
    assert r["teeth"] == teeth and abs(r["centre_x"]) < 1e-3 and abs(r["centre_y"]) < 1e-3
    assert r["tooth_thickness"] == pytest.approx(rp * angle, rel=2e-3)
    assert r["space_width"] == pytest.approx(rp * (2 * math.pi / teeth - angle), rel=2e-3)


def test_sspg_prediction_follows_the_stage_model() -> None:
    """With no variation the result is the stage relation (j_sp + j_pr) / 2 / a; the tolerance
    model only adds play, and the run is fixed by its seed."""
    pred = runs.predict_sspg_backlash(0.0238, 0.0024, 0.0, samples=400)
    assert pred["cad_only"] == pytest.approx((0.0238 + 0.0024) / 2 / 22.5, rel=1e-9)
    assert pred["cad_only"] < pred["q05"] < pred["median"] < pred["q95"]
    again = runs.predict_sspg_backlash(0.0238, 0.0024, 0.0, samples=400)
    assert again["q95"] == pred["q95"]


def test_compact_check_is_not_run_without_its_print_files(tmp_path: Path) -> None:
    r = runs.run("compact-sspg-backlash", tmp_path)
    assert r["status"] == "NOT RUN" and r["benchmark"] == "X7"
    assert "motionproof external import compact-sspg" in r["reason"]
