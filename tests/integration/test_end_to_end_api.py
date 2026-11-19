"""End-to-end demonstration through the REST API (section 25.7 of the product brief).

Reference design -> tolerances -> virtual variants -> simulation -> deliberate fault ->
experiment -> statistics -> worst-case search -> replay -> improved specification -> report.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from motionproof.api.app import create_app
from tests.conftest import signed_in

API = "/api/v1"
# reversal about the vertical pose: gravity changes sign there, so backlash is exposed
TASK = {"type": "reversal", "target": {"shoulder": 1.5708}, "joint": "shoulder",
        "payload_mass": 0.2}
CONSTRAINTS = [
    {"name": "bidirectional_positioning", "metric": "direction_error_ee", "op": "<=",
     "limit": 0.002},
    {"name": "torque", "metric": "torque_utilisation_peak", "op": "<=", "limit": 0.8},
    {"name": "mesh_clearance", "metric": "min_mesh_backlash_mm", "op": ">=", "limit": 0.0},
]


@pytest.fixture(scope="module")
def client(tmp_path_factory: pytest.TempPathFactory) -> TestClient:
    return signed_in(TestClient(create_app(tmp_path_factory.mktemp("workspace"))))


def wait(client: TestClient, job: dict[str, Any], timeout: float = 600.0) -> dict[str, Any]:
    end = time.time() + timeout
    while time.time() < end:
        j = client.get(f"{API}/jobs/{job['id']}").json()
        if j["status"] in ("completed", "failed", "cancelled"):
            assert j["status"] == "completed", j
            return j
        time.sleep(0.2)
    raise AssertionError("job timed out")


@pytest.fixture(scope="module")
def state(client: TestClient) -> dict[str, Any]:
    pid = client.post(f"{API}/projects", json={"name": "e2e"}).json()["id"]
    model = client.post(f"{API}/models/reference", json={"project_id": pid}).json()
    return {"project": pid, "model": model["id"]}


def test_01_reference_model_is_labelled_synthetic(client: TestClient, state: dict) -> None:
    d = client.get(f"{API}/models/{state['model']}").json()
    assert d["spec"]["synthetic"] is True
    assert len(d["components"]) >= 15
    assert {"shaft", "bore", "bearing_seat", "mounting_hole"} <= {
        f["type"] for f in d["spec"]["features"]}
    ready = client.post(f"{API}/models/{state['model']}/validate").json()
    assert ready["status"] == "ready_with_warnings"  # assumed values are flagged, not hidden
    mesh = client.get(f"{API}/models/{state['model']}/meshes/housing")
    assert mesh.status_code == 200 and len(mesh.content) > 1000


def test_02_define_and_edit_a_tolerance(client: TestClient, state: dict) -> None:
    mid = state["model"]
    tols = client.get(f"{API}/tolerances", params={"model_id": mid}).json()
    shaft = next(t for t in tols["tolerances"] if t["id"] == "output_shaft_diameter")
    shaft["note"] = "edited in test"
    r = client.put(f"{API}/tolerances/output_shaft_diameter", params={"model_id": mid},
                   json=shaft)
    assert r.status_code == 200
    bad = dict(shaft, upper=-1.0, lower=1.0)
    r = client.put(f"{API}/tolerances/output_shaft_diameter", params={"model_id": mid},
                   json=bad)
    assert r.status_code == 422
    fits = {f["fit"]: f for f in tols["fits"]}
    assert fits["bearing_in_housing"]["class"] == "clearance"
    assert fits["shaft_in_bearing"]["class"] == "transition"


def test_03_virtual_variants_change_geometry_and_fits(client: TestClient, state: dict) -> None:
    mid = state["model"]
    gen = client.post(f"{API}/assemblies/generate-variants",
                      json={"model_id": mid, "samples": 5, "seed": 3}).json()
    assert len(gen["variants"]) == 5
    v = gen["variants"][0]
    detail = client.post(f"{API}/assemblies/validate",
                         json={"model_id": mid, "values": v["values"]}).json()
    geo = detail["geometry"]
    assert geo["level"] == "A"
    # the regenerated solids carry the sampled dimensions (measured with OpenCascade)
    for key in ("output_shaft_diameter", "bearing_bore_diameter", "housing_seat_diameter"):
        assert geo["measured_dimensions_mm"][key] == pytest.approx(v["values"][key], abs=1e-6)
    fit = next(f for f in detail["variant"]["fits"] if f["fit"] == "bearing_in_housing")
    seat = geo["interfaces"]["bearing_to_housing"]
    assert seat["radial_clearance_mm"] == pytest.approx(fit["clearance"] / 2, abs=1e-6)
    assert seat["interference_mm3"] == pytest.approx(0.0, abs=1e-6)  # clearance fit
    sfit = next(f for f in detail["variant"]["fits"] if f["fit"] == "shaft_in_bearing")
    shaft = geo["interfaces"]["shaft_to_bearing"]
    if sfit["clearance"] > 0:  # exact OpenCascade distance equals the analytic radial gap
        assert shaft["min_distance_mm"] == pytest.approx(sfit["clearance"] / 2, abs=1e-6)
    else:
        assert shaft["interference_mm3"] > 0


def test_04_task_simulation_reports_backlash_position_and_torque(
        client: TestClient, state: dict) -> None:
    r = client.post(f"{API}/tasks", json={"model_id": state["model"], "task": TASK}).json()
    assert r["valid"]
    m = r["metrics"]
    assert 0.004 < m["backlash"] < 0.010
    assert 0 < m["ee_error_max"] < 0.005
    assert 0 < m["torque_utilisation_peak"] < 1
    assert len(r["trace"]["t"]) > 100


def test_05_deliberate_fault_is_detected(client: TestClient, state: dict) -> None:
    """A carrier pin 60 um too far out closes the planet-ring mesh: binding must be flagged."""
    detail = client.post(f"{API}/assemblies/validate", json={
        "model_id": state["model"], "values": {"s2_pin_radial_0": 0.06}}).json()
    cats = {v["category"] for v in detail["variant"]["violations"]}
    assert "mesh_interference" in cats
    assert "s2_pin_radial_0" in detail["variant"]["out_of_spec"]


def test_06_experiment_statistics_and_replay(client: TestClient, state: dict) -> None:
    cfg = {"name": "e2e reversal", "task": TASK,
           "sampling": {"method": "monte_carlo", "samples": 60, "seed": 11},
           "operating": {"payload_mass": {"type": "uniform", "low": 0.0, "high": 0.5}},
           "constraints": CONSTRAINTS}
    exp = client.post(f"{API}/experiments", json={"model_id": state["model"], "config": cfg})
    assert exp.status_code == 201, exp.text
    eid = exp.json()["id"]
    state["experiment"] = eid
    wait(client, client.post(f"{API}/experiments/{eid}/run").json())
    prog = client.get(f"{API}/experiments/{eid}/progress").json()
    assert prog["done"] == prog["total"] == 60

    a = client.get(f"{API}/experiments/{eid}/analysis", params={"metric": "direction_error_ee"}).json()
    s = a["summary"]
    assert s["scenarios"]["invalid"] == 0
    allc = s["all_constraints"]
    assert allc["interval_method"].startswith("Wilson")
    assert allc["interval"][0] <= allc["pass_fraction"] <= allc["interval"][1]
    assert 0 < s["scenarios"]["failed"] < 60  # the requirement discriminates
    assert a["sensitivity"]["rank_correlation"]["rows"][0]["parameter"]

    failed = client.get(f"{API}/experiments/{eid}/results", params={"status": "failed"}).json()
    sid = failed["results"][0]["id"]
    rep = client.post(f"{API}/experiments/{eid}/replay", json={"scenario": sid}).json()
    assert rep["reproduced"] is True and rep["differences"] == {}
    assert rep["replayed"]["trace"]["t"]


def test_07_worst_case_search_finds_and_confirms_a_failure(
        client: TestClient, state: dict) -> None:
    eid = state["experiment"]
    job = client.post(f"{API}/experiments/{eid}/optimise", json={
        "kind": "worst_case", "metric": "direction_error_ee", "algorithm": "corners",
        "budget": 60, "seed": 2}).json()
    wait(client, job)
    wc = client.get(f"{API}/experiments/{eid}/analyses/worst_case").json()["result"]
    assert wc["confirmation_matches"] is True
    assert wc["confirmed_value"] > wc["nominal_value"]
    assert wc["is_failure"] is True
    wait(client, client.post(f"{API}/experiments/{eid}/optimise",
                             json={"kind": "minimise"}).json())
    mini = client.get(f"{API}/experiments/{eid}/analyses/minimise").json()["result"]
    assert mini["confirmed"] is True
    assert len(mini["essential_parameters"]) < len(wc["configuration"])


def test_08_tighter_specification_compares_better(client: TestClient, state: dict) -> None:
    eid = state["experiment"]
    tight = {t: 0.4 for t in ("s2_backlash_sp", "s2_backlash_pr",
                              "s2_planet_bearing_clearance")}
    job = client.post(f"{API}/experiments/{eid}/optimise", json={
        "kind": "comparison", "samples": 40, "seed": 5,
        "variants": {"current": {}, "tight_stage2": tight}}).json()
    wait(client, job)
    cmp_ = client.get(f"{API}/experiments/{eid}/analyses/comparison").json()["result"]
    cur, new = cmp_["variants"]["current"], cmp_["variants"]["tight_stage2"]
    # tightening the spread narrows the performance distribution (same random numbers)
    spread = lambda v: v["metrics"]["backlash"]["max"] - v["metrics"]["backlash"]["mean"]  # noqa: E731
    assert spread(new) < spread(cur)
    assert new["pass_fraction"] >= cur["pass_fraction"]


def test_09_reports_in_all_formats(client: TestClient, state: dict, tmp_path: Path) -> None:
    eid = state["experiment"]
    rep = client.get(f"{API}/reports/{eid}").json()
    assert rep["synthetic_notice"]
    assert rep["limitations"] and rep["versions"]["mujoco"]
    assert rep["analyses"]["worst_case"]["is_failure"] is True
    md = client.get(f"{API}/reports/{eid}", params={"format": "markdown"}).text
    assert "SYNTHETIC REFERENCE DESIGN" in md and "Wilson" in md
    csv_text = client.get(f"{API}/reports/{eid}", params={"format": "csv"}).text
    assert len(csv_text.splitlines()) == 61
    pdf = client.get(f"{API}/reports/{eid}", params={"format": "pdf"})
    assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF"


def test_10_experiment_snapshot_is_immutable(client: TestClient, state: dict) -> None:
    """Editing the model afterwards must not change what the experiment replays."""
    mid, eid = state["model"], state["experiment"]
    tols = client.get(f"{API}/tolerances", params={"model_id": mid}).json()["tolerances"]
    t = next(t for t in tols if t["id"] == "output_friction")
    t["distribution"] = {"type": "uniform", "low": 0.02, "high": 0.3}
    t["upper"] = 0.25
    assert client.put(f"{API}/tolerances/output_friction", params={"model_id": mid},
                      json=t).status_code == 200
    rep = client.post(f"{API}/experiments/{eid}/replay", json={"scenario": "S000001"}).json()
    assert rep["reproduced"] is True
    assert rep["model_fingerprint_matches"] is True


def test_errors_are_actionable(client: TestClient, state: dict) -> None:
    r = client.post(f"{API}/models/import", data={"project_id": state["project"]},
                    files={"files": ("part.step", b"this is not a step file")})
    assert r.status_code == 422 and "STEP" in r.json()["error"]
    r = client.post(f"{API}/models/import", data={"project_id": state["project"]},
                    files={"files": ("notes.txt", b"x")})
    assert r.status_code == 422 and "unsupported file type" in r.json()["error"]
    assert client.get(f"{API}/models/MDL_999").status_code == 404
    assert client.delete(f"{API}/projects/{state['project']}",
                         params={"confirm": "wrong"}).status_code == 400
