"""Independent reference calculations for the MotionProof benchmark suite.

This script does NOT import motionproof. It reads only the published inputs and raw data in
``benchmarks/data`` and computes, with NumPy/SciPy and its own code:

* ``expected``: the expected value of every benchmark check that has a closed form, keyed by
  the exact quantity name used in ``motionproof/benchmarks/suite.py``;
* ``estimates``: independent re-analyses of the raw (SYNTHETIC) data sets, each with the
  quantity of the suite it should agree with and an agreement tolerance.

``publish.py`` compares both with the suite's run. Run it in an isolated interpreter:

    python -I benchmarks/reference_calculations.py benchmarks/data
"""

from __future__ import annotations

import csv
import json
import math
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import numpy as np
import yaml
from scipy import stats

G = 9.81


# ---- helpers (own implementations) -----------------------------------------------------------

def tol(spec: dict[str, Any], tid: str) -> dict[str, Any]:
    return next(t for t in spec["tolerances"] if t["id"] == tid)


def limits(t: dict[str, Any]) -> tuple[float, float]:
    return t["nominal"] + t["lower"], t["nominal"] + t["upper"]


def mean_std(d: dict[str, Any]) -> tuple[float, float]:
    if d["type"] == "uniform":
        return (d["low"] + d["high"]) / 2, (d["high"] - d["low"]) / math.sqrt(12)
    if d["type"] == "normal":
        return d["mean"], d["std"]
    if d["type"] == "truncated_normal":
        a, b = (d["low"] - d["mean"]) / d["std"], (d["high"] - d["mean"]) / d["std"]
        m, v = stats.truncnorm.stats(a, b, loc=d["mean"], scale=d["std"], moments="mv")
        return float(m), math.sqrt(float(v))
    raise ValueError(d["type"])


def read_xyz(path: Path) -> np.ndarray:
    return np.loadtxt(path, comments="#")


def read_csv(path: Path) -> dict[str, np.ndarray]:
    with path.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(line for line in f if not line.startswith("#")))
    return {k: np.array([float(r[k]) for r in rows]) for k in rows[0]}


def cylinder_diameter(points: np.ndarray) -> float:
    """PCA axis, side-wall selection, algebraic (Kasa) circle fit; no registration needed."""
    c = points.mean(axis=0)
    _, _, vt = np.linalg.svd(points - c, full_matrices=False)
    axis, u, v = vt[0], vt[1], vt[2]
    t = (points - c) @ axis
    x, y = (points - c) @ u, (points - c) @ v
    rad = np.hypot(x, y)
    keep = (t > t.min() + 1.0) & (t < t.max() - 1.0) & (rad > 0.8 * np.median(rad))
    for _ in range(3):  # refine the axis direction on the side wall only
        p = points[keep]
        c = p.mean(axis=0)
        _, _, vt = np.linalg.svd(p - c, full_matrices=False)
        axis, u, v = vt[0], vt[1], vt[2]
        t = (points - c) @ axis
        x, y = (points - c) @ u, (points - c) @ v
        rad = np.hypot(x - np.mean(x[keep]), y - np.mean(y[keep]))
        keep = (t > t.min() + 1.0) & (t < t.max() - 1.0) & (rad > 0.8 * np.median(rad))
    a = np.column_stack([x[keep], y[keep], np.ones(int(keep.sum()))])
    sol, *_ = np.linalg.lstsq(a, x[keep] ** 2 + y[keep] ** 2, rcond=None)
    return 2 * math.sqrt(sol[2] + (sol[0] / 2) ** 2 + (sol[1] / 2) ** 2)


def nested_anova(values: np.ndarray, batch: np.ndarray, setup: np.ndarray) -> dict[str, float]:
    """Balanced two-level nested ANOVA (batch > setup > part), method of moments."""
    a = len(np.unique(batch))
    b = len(np.unique(setup)) // a
    n = len(values) // (a * b)
    y = values[np.lexsort((setup, batch))].reshape(a, b, n)
    yij, yi, yb = y.mean(2), y.mean((1, 2)), y.mean()
    msw = float(((y - yij[..., None]) ** 2).sum() / (a * b * (n - 1)))
    mss = float(n * ((yij - yi[:, None]) ** 2).sum() / (a * (b - 1)))
    msb = float(b * n * ((yi - yb) ** 2).sum() / (a - 1))
    return {"batch_std": math.sqrt(max((msb - mss) / (b * n), 0.0)),
            "setup_std": math.sqrt(max((mss - msw) / n, 0.0)), "part_std": math.sqrt(msw)}


# ---- references ------------------------------------------------------------------------------

def main(data: Path) -> dict[str, Any]:
    inp = json.loads((data / "inputs.json").read_text(encoding="utf-8"))
    spec = yaml.safe_load((data / "reference_design" / "model.yaml").read_text(encoding="utf-8"))
    sj = inp["single_joint"]
    L, M, N, K = sj["arm_length"], sj["arm_mass"], sj["ratio"], sj["stiffness"]
    exp: dict[str, dict[str, float]] = {}
    est: dict[str, list[dict[str, Any]]] = {}

    # A fits and scan
    shaft, bore = tol(spec, "output_shaft_diameter"), tol(spec, "bearing_bore_diameter")
    (s_lo, s_hi), (b_lo, b_hi) = limits(shaft), limits(bore)
    (ms, ss), (mb, sb) = mean_std(shaft["distribution"]), mean_std(bore["distribution"])
    gap = inp["A"]["brep_gap"]
    exp["A"] = {"min clearance (bore LSL - shaft USL)": b_lo - s_hi,
                "max clearance (bore USL - shaft LSL)": b_hi - s_lo,
                "clearance mean (Monte Carlo vs analytic)": mb - ms,
                "clearance std (Monte Carlo vs RSS)": math.hypot(sb, ss),
                "exact B-rep radial gap with 10 um offset":
                    (gap["bore"] - gap["shaft"]) / 2 - gap["offset"],
                "diameter recovered from SYNTHETIC noisy scan (unknown pose)":
                    inp["A"]["scan"]["true_diameter"]}
    d_ref = cylinder_diameter(read_xyz(data / "A_synthetic_shaft_scan_posed.xyz"))
    est["A"] = [{"estimate": "Kasa circle fit of the raw posed scan (no registration)",
                 "value": d_ref, "compare_with": "true diameter", "target":
                 inp["A"]["scan"]["true_diameter"], "tolerance": 0.002, "unit": "mm"}]

    # B gearbox
    s1, s2 = spec["gear_stages"]

    def stage(s: dict[str, Any]) -> tuple[float, float, float]:
        ratio = 1 + s["ring_teeth"] / s["sun_teeth"]
        a = s["module"] * (s["sun_teeth"] + s["planet_teeth"]) / 2
        p = s["inputs"]
        j = (tol(spec, p["design_backlash_sun_planet"])["nominal"]
             + tol(spec, p["design_backlash_planet_ring"])["nominal"]) / 2 \
            + tol(spec, p["planet_bearing_clearance"])["nominal"]
        return ratio, j / a, s["module"] * s["sun_teeth"] / 2

    r1, b1, rs1 = stage(s1)
    r2, b2, _ = stage(s2)
    exp["B"] = {"stage 1 ratio 1 + 54/12": r1, "stage 2 ratio 1 + 60/12": r2,
                "overall 33:1 from tooth counts": r1 * r2,
                "stage 2 backlash ((0.04 + 0.04)/2 + 0.012) / 9 mm": b2,
                "output backlash = s2 + s1 / 6": b2 + b1 / r2,
                "transmission error amplitude e / r_sun / 33":
                    inp["B"]["runout"] / 2 / rs1 / (r1 * r2)}

    # C two-link arm
    root = ET.parse(data / "reference_design" / "geometry" / "model.xml").getroot()
    jpos = {j.get("name"): np.array([float(v) for v in str(j.get("pos")).split()])
            for j in root.iter("joint")}
    sh, el = jpos["shoulder"], jpos["elbow"]
    tip = np.array(spec["end_effector"]["offset"])
    l1, l2 = float(el[0] - sh[0]), float(tip[0] - el[0])
    mp_out = json.loads((data / "motionproof_outputs.json").read_text(encoding="utf-8"))
    dev = []
    for row in mp_out["C"]["fk"]:
        q1, q2 = row["q"]
        x = sh[0] + l1 * math.cos(q1) + l2 * math.cos(q1 + q2)
        z = sh[2] + l1 * math.sin(q1) + l2 * math.sin(q1 + q2)
        dev.append(math.hypot(row["ee"][0] - x, row["ee"][2] - z))
    tgt = np.array(inp["C"]["ik_target"])
    r = float(np.hypot(tgt[0] - sh[0], tgt[2] - sh[2]))
    tau = 0.0
    for body in root.iter("body"):
        inertial = body.find("inertial")
        if inertial is None:
            continue
        pos = np.array([float(v) for v in str(inertial.get("pos")).split()])
        tau += float(str(inertial.get("mass"))) * G * (pos[0] - sh[0])  # bodies at zero pose
    shoulder = next(j for j in root.iter("joint") if j.get("name") == "shoulder")
    exp["C"] = {"IK elbow angle vs law of cosines":
                    math.acos((r * r - l1 * l1 - l2 * l2) / (2 * l1 * l2)),
                "shoulder gravity torque = sum m g x_com": tau,
                "shoulder upper limit compiled from the model file":
                    float(str(shoulder.get("range")).split()[1]),
                "workspace outer radius": l1 + l2}
    est["C"] = [{"estimate": "max deviation of MotionProof FK from the closed form",
                 "value": max(dev), "compare_with": "zero", "target": 0.0, "tolerance": 1e-9,
                 "unit": "m"}]

    # D, E, F, I, L single joint closed forms
    exp["D"] = {}
    for b in inp["D"]["backlash"]:
        exp["D"][f"lost motion = b for b = {b}"] = b
        exp["D"][f"direction error at the tip = L b for b = {b}"] = L * b
    sup = spec["radial_supports"][0]
    seat = inp["E"]["seat_change_mm"]
    exp["E"] = {f"tip error from {o * 1e3:g} mm joint offset": o for o in inp["E"]["offsets_m"]}
    exp["E"] |= {"sensitivity d(tip error)/d(tilt) = arm length": L,
                 f"radial play grows with seat clearance ({seat * 1e3:g} um)": seat * 1e-3,
                 "axis tilt from extra play = play / bearing span":
                     seat * 1e-3 / sup["bearing_span"]}
    exp["F"] = {}
    for p in inp["F"]["payloads"]:
        t = (M + p) * G * L
        exp["F"][f"motor torque with {p} kg payload = (m+mp) g L / N"] = t / N
        exp["F"][f"torque utilisation with {p} kg"] = t / N / sj["peak_torque"]
        exp["F"][f"tip error with {p} kg = L tau / k"] = L * t / K
    windup = M * G * L / K
    i = inp["I"]
    exp["I"] = {"wear rate recovered from SYNTHETIC data": i["true_rate"],
                "threshold crossing (cycles)":
                    (2 * (i["limit"] - windup) - i["initial_backlash"]) / i["true_rate"]}
    w = read_csv(data / "I_synthetic_wear.csv")
    est["I"] = [{"estimate": "wear rate, numpy.polyfit on the raw data",
                 "value": float(np.polyfit(w["cycles"], w["backlash_rad"], 1)[0]),
                 "compare_with": "suite: wear rate recovered from SYNTHETIC data",
                 "tolerance_rel": 1e-9, "unit": "rad/cycle"}]
    exp["L"] = {"L1 deflection vs closed form": inp["L"]["backlash"] / 2 + windup,
                "L1 - L2 tip error difference (frictionless)": 0.0}

    # G process
    gp = inp["G"]
    exp["G"] = {"batch std recovered": gp["batch_std"], "setup std recovered": gp["setup_std"],
                "part std recovered": gp["part_std"],
                "clearance std, setup error independent":
                    math.sqrt(2 * (gp["batch_std"] ** 2 + gp["setup_std"] ** 2
                                   + gp["part_std"] ** 2)),
                "clearance std, setup error shared":
                    math.sqrt(2 * (gp["batch_std"] ** 2 + gp["part_std"] ** 2)),
                "tool-wear drift rate recovered": gp["drift_rate"]}
    bt = read_csv(data / "G_synthetic_batch.csv")
    an = nested_anova(bt["bore_mm"], bt["batch"], bt["setup"])
    est["G"] = [{"estimate": f"{k.replace('_', ' ')}, own nested ANOVA", "value": v,
                 "compare_with": f"suite: {k.split('_')[0]} std recovered",
                 "tolerance_rel": 1e-9, "unit": "mm"} for k, v in an.items()]
    for kind in ("independent", "shared"):
        c = read_csv(data / f"G_synthetic_clearance_{kind}.csv")
        est["G"].append({"estimate": f"clearance std ({kind} setup), numpy std of bore - shaft",
                         "value": float(np.std(c["bore_mm"] - c["shaft_mm"])),
                         "compare_with": f"suite: clearance std, setup error {kind}",
                         "tolerance_rel": 1e-9, "unit": "mm"})
    tw = read_csv(data / "G_synthetic_tool_wear.csv")
    est["G"].append({"estimate": "drift rate, numpy.polyfit", "value":
                     float(np.polyfit(tw["part"], tw["bore_mm"], 1)[0]),
                     "compare_with": "suite: tool-wear drift rate recovered",
                     "tolerance_rel": 1e-6, "unit": "mm/part"})

    # K adaptive, M challenge
    exp["K"] = {"true failure probability Phi(-3) (reference only)": float(stats.norm.cdf(-3))}
    mc = inp["M"]
    hw, centre = mc["half_width"], mc["centre"]
    s = np.linspace(mc["scale_lower"], mc["scale_upper"], 80_001)
    fail = np.maximum(0.0, (centre + hw * s - mc["backlash_limit"]) / (2 * hw * s))
    exp["M"] = {"largest scale with zero failures":
                    float(s[fail == 0].max()),
                "largest scale meeting the reliability target (point estimate; cost optimum "
                "1/s without confidence margin)":
                    float(s[fail <= 1 - mc["reliability_target"]].max())}
    est["M"] = []
    y = mp_out["M"]["yield_chosen"]
    if y is not None:
        p = mc["yield_process"]
        yld = (stats.norm.cdf((centre + hw * y["scale"] - p["mean"]) / p["std"])
               - stats.norm.cdf((centre - hw * y["scale"] - p["mean"]) / p["std"]))
        est["M"].append({"estimate": f"yield cost (unit cost {mc['unit_cost']}) / yield at the "
                                     f"chosen scale {y['scale']:.6f}",
                         "value": mc["unit_cost"] / float(yld), "target": y["cost"],
                         "compare_with": "MotionProof cost of the chosen candidate",
                         "tolerance_rel": 1e-12})
    r = mp_out["M"]["reciprocal_chosen"]
    if r is not None:
        est["M"].append({"estimate": "chosen scale (reciprocal cost) within [0.5, point-"
                                     "estimate optimum]; 0.5 is the suite's lower bound "
                                     "allowing for the confidence margin",
                         "value": r["scale"], "band": [0.5, exp["M"][
                             "largest scale meeting the reliability target (point estimate; "
                             "cost optimum 1/s without confidence margin)"]]})
    return {"generated_by": "benchmarks/reference_calculations.py (NumPy "
                            f"{np.__version__}, no motionproof import)",
            "expected": exp, "estimates": est}


if __name__ == "__main__":
    folder = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent / "data"
    if "motionproof" in sys.modules:
        raise SystemExit("reference calculations must not import motionproof")
    out = main(folder)
    if any(name.startswith("motionproof") for name in sys.modules):
        raise SystemExit("motionproof was imported indirectly; reference not independent")
    (folder / "references.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(json.dumps(out, indent=1))
