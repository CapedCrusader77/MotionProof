"""Integrated advanced workflow through the REST API, on the synthetic reference design.

Import model -> synthetic scan of the output shaft -> register -> measure -> approve ->
as-built variant -> process batch -> adaptive experiment -> workspace map -> root cause ->
degradation -> fidelity comparison -> simulated hardware session -> challenge -> trust panel.
"""

from __future__ import annotations

import math
import time
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from fastapi.testclient import TestClient

from motionproof.api.app import create_app
from motionproof.scans import synthetic as S
from tests.conftest import signed_in

API = "/api/v1"


@pytest.fixture(scope="module")
def client(tmp_path_factory: pytest.TempPathFactory) -> TestClient:
    return signed_in(TestClient(create_app(tmp_path_factory.mktemp("ws"))))


@pytest.fixture(scope="module")
def ids(client: TestClient) -> dict[str, Any]:
    pid = client.post(f"{API}/projects", json={"name": "advanced"}).json()["id"]
    mid = client.post(f"{API}/models/reference", json={"project_id": pid}).json()["id"]
    return {"project": pid, "model": mid}


def wait(client: TestClient, job: dict[str, Any], timeout: float = 900) -> dict[str, Any]:
    assert "id" in job, job
    end = time.time() + timeout
    while time.time() < end:
        j = client.get(f"{API}/jobs/{job['id']}").json()
        if j["status"] in ("completed", "failed", "cancelled"):
            assert j["status"] == "completed", j
            return j
        time.sleep(0.2)
    raise AssertionError("timeout")


def test_scan_to_as_built(client: TestClient, ids: dict, tmp_path: Path) -> None:
    """SYNTHETIC scan of the output shaft (component frame, mm). Journal axis +Y from y = 11,
    length 41 mm. True diameter 7.982 mm (below the 7.986 lower limit)."""
    pts = S.cylinder_scan(7.982, 41.0, 15_000, noise=0.004, seed=7)
    pts = pts[:, [0, 2, 1]] + np.array([0.0, 11.0, 0.0])  # cylinder axis Z -> world Y
    pts, _ = S.rigid(pts, (1.0, 0.0, 0.3), 0.01, (0.2, 0.1, -0.15))
    path = S.write_xyz(tmp_path / "synthetic_output_shaft.xyz", pts, "mm", "shaft 7.982")
    with path.open("rb") as f:
        r = client.post(f"{API}/scans/import", data={"model_id": ids["model"], "units": "mm",
                                                     "scanner": "synthetic"},
                        files={"file": (path.name, f)})
    assert r.status_code == 201, r.text
    scan = r.json()
    assert scan["synthetic"] is True and scan["units"] == "mm"
    ids["scan"] = scan["id"]
    wait(client, client.post(f"{API}/scans/{scan['id']}/register",
                             json={"component": "output_shaft", "lock": ["ry"],
                                   "accept_rms": 0.03}).json())
    cyl = {"feature": "output_shaft_journal", "tolerance": "output_shaft_diameter",
           "axis_point": [0, 11, 0], "axis_direction": [0, 1, 0], "radius": 4.0, "band": 0.2,
           "start": 1.0, "length": 39.0}
    wait(client, client.post(f"{API}/scans/{scan['id']}/analyse",
                             json={"limit": 0.01, "cylinders": [cyl]}).json())
    got = client.get(f"{API}/scans/{scan['id']}").json()
    assert got["registration"]["registration"]["valid_for_inspection"] is True
    m = got["analysis"]["measured"][0]
    assert m["status"] == "pending" and m["value"] == pytest.approx(7.982, abs=0.002)
    assert got["analysis"]["deviation"]["coverage"]["fraction_of_nominal_surface"] > 0.9
    before = client.get(f"{API}/models/{ids['model']}/as-built").json()
    assert before["values"] == {}
    d = client.post(f"{API}/scans/{scan['id']}/measurements/{m['id']}",
                    json={"status": "approved"}).json()
    assert d["status"] == "approved"
    built = client.get(f"{API}/models/{ids['model']}/as-built").json()
    assert built["used"][0]["in_spec"] is False
    fit = next(f for f in built["variant"]["fits"] if f["fit"] == "shaft_in_bearing")
    assert fit["shaft"] == pytest.approx(m["value"])
    trust = client.get(f"{API}/models/{ids['model']}/trust").json()
    row = next(p for p in trust["parameters"] if p["parameter"] == "output_shaft_diameter")
    assert row["status"] == "extracted from scan"
    assert "no overall trust" in trust["note"]


def test_process_batch(client: TestClient, ids: dict) -> None:
    proc = {"name": "turning", "features": [
        {"feature": "output_shaft_diameter", "process": "CNC turning", "target": 7.9905,
         "unit": "mm", "lower_limit": 7.986, "upper_limit": 7.995,
         "sources": [{"level": "setup", "std": 0.0012, "basis": "assumed",
                      "shared_group": "lathe"},
                     {"level": "part", "std": 0.0008, "basis": "assumed"}]},
        {"feature": "bearing_bore_diameter", "process": "purchased", "target": 7.996,
         "unit": "mm", "lower_limit": 7.992, "upper_limit": 8.0,
         "sources": [{"level": "part", "std": 0.0013, "basis": "assumed"}]}]}
    j = wait(client, client.post(f"{API}/manufacturing/batches", json={
        "model_id": ids["model"], "process": proc,
        "plan": {"setups_per_batch": 10, "parts_per_setup": 20, "seed": 1}}).json())
    b = client.get(f"{API}/artifacts/{j['result']}/batch").json()
    assert b["parts"] == 200 and "shaft_in_bearing" in b["assemblies"]["fits"]
    vc = b["variance_components"]["output_shaft_diameter"]
    assert vc["part_std"] == pytest.approx(0.0008, rel=0.2)
    assert "not production data" in b["label"]


def test_adaptive_workspace_rootcause_degradation_fidelity(client: TestClient, ids: dict) -> None:
    cfg = {"name": "adaptive", "task": {"type": "reversal", "target": {"shoulder": 1.5708},
                                        "joint": "shoulder", "payload_mass": 0.2},
           "constraints": [{"name": "dir", "metric": "direction_error_ee", "op": "<=",
                            "limit": 0.002}]}
    j = wait(client, client.post(f"{API}/experiments/adaptive", json={
        "model_id": ids["model"], "config": cfg, "initial": 12, "budget": 24,
        "population": 2000, "seed": 3}).json())
    a = client.get(f"{API}/artifacts/{j['result']}/adaptive").json()
    assert a["simulations"]["total"] <= 24 and len(a["simulated"]) == a["simulations"]["total"]
    assert a["surrogate"]["kind"] == "prediction, not simulation"

    j = wait(client, client.post(f"{API}/workspace/analyse", json={
        "model_id": ids["model"], "grid": {"shoulder": [-1.0, 0.0, 1.0], "elbow": [0.0, 1.0]},
        "samples": 10, "position_tolerance": 0.003, "verify_poses": 1}).json())
    w = client.get(f"{API}/artifacts/{j['result']}/workspace").json()
    assert len(w["cells"]) == 6 and w["verification"]
    j = wait(client, client.post(f"{API}/workspace/analyse", json={
        "model_id": ids["model"], "grid": {"shoulder": [0.0]}, "source": "as_built"}).json())
    assert client.get(f"{API}/artifacts/{j['result']}/workspace").json()["source"] == "as_built"

    exp = client.post(f"{API}/experiments", json={"model_id": ids["model"], "config": cfg | {
        "sampling": {"samples": 20, "seed": 5}}}).json()
    wait(client, client.post(f"{API}/experiments/{exp['id']}/run").json())
    failed = client.get(f"{API}/experiments/{exp['id']}/results",
                        params={"status": "failed"}).json()["results"]
    assert failed
    j = wait(client, client.post(f"{API}/rootcause", json={
        "experiment_id": exp["id"], "scenario": failed[0]["id"]}).json())
    rc = client.get(f"{API}/artifacts/{j['result']}/rootcause").json()
    assert rc["contributions"] and rc["explanation"] and rc["trace"]["t"]

    j = wait(client, client.post(f"{API}/degradation/experiments", json={
        "model_id": ids["model"], "pose": {"shoulder": 0.0}, "cycles": [0, 1e5, 2e5],
        "mechanisms": [{"joint": "shoulder", "parameter": "backlash", "kind": "linear",
                        "rate": 1e-8, "basis": "assumed"}],
        "constraints": [{"name": "tip", "metric": "ee_error_final", "op": "<=",
                         "limit": 0.003}], "inspect_every": 50000}).json())
    dg = client.get(f"{API}/artifacts/{j['result']}/degradation").json()
    assert dg["label"].startswith("MODEL-BASED PROJECTION") and "maintenance" in dg

    j = wait(client, client.post(f"{API}/fidelity/compare", json={
        "model_id": ids["model"], "pose": {"shoulder": 0.5}, "samples": 3}).json())
    fd = client.get(f"{API}/artifacts/{j['result']}/fidelity").json()
    assert fd["levels"]["L3_contact_structural"] == "not implemented"


def test_hardware_session_requires_confirmation(client: TestClient, ids: dict) -> None:
    body = {"model_id": ids["model"],
            "test": {"joint": "shoulder", "centre": 1.5708, "excursion": 0.2, "move_time": 1.0},
            "limits": {"travel_min": 1.0, "travel_max": 2.2, "max_speed": 1.0,
                       "max_duration": 20}, "simulated_truth": {"backlash": 0.01}}
    r = client.post(f"{API}/hardware/experiments", json=body)
    assert r.status_code == 400 and "not confirmed" in r.json()["detail"]
    j = wait(client, client.post(f"{API}/hardware/experiments",
                                 json=body | {"confirm_actuation": True}).json())
    s = client.get(f"{API}/artifacts/{j['result']}/session").json()
    assert s["source"] == "SIMULATED DEVICE" and s["status"] == "completed"
    assert s["comparison"]["measured_lost_motion"] > 0.005
    csv = client.get(f"{API}/hardware/experiments/{j['result']}/measurements").text
    assert csv.startswith("# source: SIMULATED DEVICE")
    devices = client.get(f"{API}/hardware/devices").json()
    assert devices[0]["id"] == "simulated"


def test_challenge_through_api(client: TestClient, ids: dict) -> None:
    cfg = {"name": "api challenge", "search_fidelity": "L1", "l1_pose": {"shoulder": 0.0},
           "experiment": {"name": "hold", "task": {"type": "static_hold",
                                                   "pose": {"shoulder": 0.0}},
                          "constraints": [{"name": "mesh", "metric": "min_mesh_backlash_mm",
                                           "op": ">=", "limit": 0.0}]},
           "variables": [{"tolerance": "s2_pin_radial_0", "kind": "scale", "lower": 0.3,
                          "upper": 2.0}],
           "reliability": {"target": 0.8, "confidence": 0.8},
           "samples": 30, "verify_samples": 40, "screen": 5, "refine_generations": 1}
    r = client.post(f"{API}/challenges", json={"model_id": ids["model"], "config": cfg})
    assert r.status_code == 202
    wait(client, r.json())
    ch = client.get(f"{API}/artifacts/{r.json()['challenge_id']}/challenge").json()
    assert ch["candidates"][0]["id"] == "baseline" and "not a price" in ch["cost_label"]
    assert isinstance(client.get(f"{API}/artifacts/{ch['id']}/comparison").json(), dict)
    bad = dict(cfg, variables=[{"tolerance": "nope", "kind": "scale", "lower": 0.5,
                                "upper": 1}])
    assert client.post(f"{API}/challenges", json={"model_id": ids["model"],
                                                  "config": bad}).status_code == 404


def test_benchmark_listing_and_single_run(client: TestClient) -> None:
    listing = client.get(f"{API}/benchmarks").json()
    assert [b["id"] for b in listing["benchmarks"]][:3] == ["A", "B", "C"]
    j = wait(client, client.post(f"{API}/benchmarks/run", json={"ids": ["gearbox"]}).json())
    res = client.get(f"{API}/artifacts/{j['result']}/benchmarks").json()
    assert res[0]["id"] == "B" and res[0]["status"] == "PASS"
    assert math.isfinite(res[0]["seconds"])
