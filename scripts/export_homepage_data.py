"""Export real MotionProof results for the public homepage. Nothing here is invented.

Reads the reference design (examples/nema17_planetary_joint) and one finished experiment
(workspace, EXP_001), selects three real scenarios, regenerates their geometry with the
engine (CadQuery, same call as the application) and writes:

  frontend/public/assets/motionproof/data.json
  assets/blender/homepage/build/variants/<id>/meshes/*.stl   (input for the Blender pipeline)

    uv run python scripts/export_homepage_data.py
"""
from __future__ import annotations
import json, shutil, sys
from datetime import date
from pathlib import Path
import numpy as np, yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from motionproof.reference import nema17_arm as ref
from motionproof.sensitivity.analysis import analyse

EXP = ROOT / "workspace/projects/PRJ_001/experiments/EXP_001"
MODEL = ROOT / "examples/nema17_planetary_joint"
OUT = ROOT / "frontend/public/assets/motionproof"
BUILD = ROOT / "assets/blender/homepage/build"

rows = [json.loads(l) for l in (EXP / "results.jsonl").read_text().splitlines() if l.strip()]
manifest = json.loads((EXP / "manifest.json").read_text())
spec = yaml.safe_load((MODEL / "model.yaml").read_text())
inv = json.loads((MODEL / "geometry/inventory.json").read_text())
valid = [r for r in rows if r["valid"]]
names = list(valid[0]["values"])
X = np.array([[r["values"][n] for n in names] for r in valid])
M = lambda k: np.array([r["metrics"][k] for r in valid])

# three real scenarios: a passing one near the median, the worst failing, a failing one at the 90th percentile
key = M("angle_error_max")
order = np.argsort(key)
pick = {"typical": order[len(order) // 2], "p90": order[int(len(order) * 0.9)], "worst": order[-1]}
variants = []
for label, i in pick.items():
    r = valid[int(i)]
    geo = {k: r["values"][k] for k in ref.GEOMETRY_PARAMETERS if k in r["values"]}
    d = BUILD / "variants" / label
    if d.exists(): shutil.rmtree(d)
    ref.write_geometry(d, geo)
    variants.append({"id": label, "scenario": r["id"], "values": r["values"], "regenerated": geo,
                     "metrics": r["metrics"], "constraints": r["metrics_constraints"] if "metrics_constraints" in r else r["constraints"],
                     "passed": r["passed"], "failures": r["failures"], "joints": r["joints"]})

# nominal geometry is the model's own export; copy so the pipeline has one input tree
nd = BUILD / "nominal"
if nd.exists(): shutil.rmtree(nd)
shutil.copytree(MODEL / "geometry", nd, ignore=shutil.ignore_patterns("assembly.step"))

cols = ["angle_error_max", "backlash", "lost_motion", "direction_error_ee", "torque_utilisation_peak"]
pop = {c: [round(float(v), 6) for v in M(c)] for c in cols}
pop["passed"] = [bool(r["passed"]) for r in valid]
sens = analyse(names, X, {c: M(c) for c in cols}, "angle_error_max")
cons = {}
for r in valid:
    for k, v in r["constraints"].items() if "constraints" in r and isinstance(r["constraints"], dict) else []:
        pass
data = {
    "provenance": {
        "generated": date.today().isoformat(), "model": spec.get("name"), "synthetic": True,
        "statement": "Synthetic reference design created by MotionProof. Tolerances, motor and gearbox values are illustrative assumptions, not anyone's hardware.",
        "experiment": {"id": "EXP_001", "name": manifest.get("name"), "scenarios": len(rows), "valid": len(valid),
                       "passed": int(sum(r["passed"] for r in valid)), "seed": manifest.get("seed")},
        "source": "workspace results.jsonl, regenerated geometry via motionproof.reference.nema17_arm.write_geometry",
    },
    "components": [{k: c.get(k) for k in ("id", "body", "group", "note", "mass_kg")} for c in inv["components"]],
    "parameters": inv["parameters"],
    "stages": ref.STAGES if hasattr(ref, "STAGES") else None,
    "tolerances": [{k: t.get(k) for k in ("id", "component", "parameter", "characteristic", "category", "nominal", "lower", "upper", "unit", "distribution", "confidence", "datum", "feature", "source")} for t in spec["tolerances"]],
    "variants": variants,
    "population": pop,
    "sensitivity": {"metric": "angle_error_max", "rows": sens["rank_correlation"]["rows"][:10],
                    "method": sens["rank_correlation"]["method"], "caveat": sens["rank_correlation"]["caveat"]},
    "constraints": spec.get("constraints") or spec.get("requirements"),
}
OUT.mkdir(parents=True, exist_ok=True)
(OUT / "data.json").write_text(json.dumps(data, default=float), encoding="utf-8")
print("variants:", [(v["id"], v["scenario"], round(v["metrics"]["angle_error_max"], 5), v["passed"]) for v in variants])
print((OUT / "data.json").stat().st_size // 1024, "KB")
