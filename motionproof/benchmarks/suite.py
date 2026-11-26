"""Reproducible mechanical benchmark suite.

Every benchmark computes its expected value independently (closed form or a separate method),
runs MotionProof, and records expected, actual, error and the acceptance criterion. Nothing is
hard-coded as a result: ``BENCHMARK_RESULTS.md`` is written only from a run.

Synthetic data are labelled. Benchmark J (hardware) has no measurements and reports NOT RUN.
"""

from __future__ import annotations

import math
import platform
import tempfile
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import mujoco
import numpy as np
from scipy import stats
from scipy.optimize import least_squares

import motionproof
from motionproof.model import MechanicalModel

SINGLE_XML = """<mujoco model="single_joint">
  <compiler angle="radian"/>
  <option gravity="0 0 -9.81" timestep="0.0005" integrator="implicitfast"/>
  <worldbody>
    <body name="arm">
      <joint name="j" type="hinge" pos="0 0 0" axis="0 -1 0"/>
      <inertial pos="0.3 0 0" mass="1.0" diaginertia="1e-5 1e-5 1e-5"/>
    </body>
  </worldbody>
</mujoco>
"""
L_ARM, M_ARM, G, RATIO = 0.3, 1.0, 9.81, 20.0
_CACHE: dict[str, Any] = {}


def single_joint(backlash_range: tuple[float, float] = (0.0, 0.02), stiffness: float = 2000.0,
                 friction: float = 0.0, gravity: bool = True, backlash: float = 0.0,
                 efficiency: float = 1.0) -> MechanicalModel:
    """Point mass 1 kg on a massless 0.3 m arm, 20:1 gearbox. All values are benchmark inputs."""
    d = Path(tempfile.mkdtemp(prefix="mp_bench_"))
    (d / "single.xml").write_text(SINGLE_XML, encoding="utf-8")
    lo, hi = backlash_range
    raw = {
        "schema": "motionproof.model/1", "name": "benchmark single joint", "synthetic": True,
        "source": {"kind": "mjcf", "file": "single.xml"},
        "tolerances": [{"id": "backlash_tol", "component": "gearbox", "parameter": "backlash",
                        "characteristic": "backlash", "category": "assembly", "nominal": 0.0,
                        "lower": lo, "upper": hi, "unit": "rad",
                        "distribution": {"type": "uniform", "low": lo, "high": hi},
                        "source": "benchmark input", "confidence": "specified"}],
        "effects": [{"tolerance": "backlash_tol", "joint": "j", "target": "backlash"}],
        "drives": {"j": {"motor": {"continuous_torque": 1.0, "peak_torque": 2.0,
                                   "max_speed": 300.0, "rotor_inertia": 1e-5,
                                   "source": "benchmark input", "confidence": "specified"},
                         "gearbox": {"ratio": RATIO, "efficiency": efficiency,
                                     "backlash": backlash, "stiffness": stiffness,
                                     "damping_ratio": 0.3, "source": "benchmark input",
                                     "confidence": "specified"},
                         "controller": {"bandwidth": 40.0}, "friction": friction}},
        "end_effector": {"body": "arm", "offset": [L_ARM, 0.0, 0.0]},
        "simulation": {"timestep": 5e-4,
                       "gravity": [0, 0, -9.81] if gravity else [0.0, 0.0, 0.0]},
    }
    return MechanicalModel.from_dict(raw, d)


def reference() -> MechanicalModel:
    if "ref" not in _CACHE:
        from motionproof.reference.nema17_arm import write_reference_project

        _CACHE["ref"] = MechanicalModel.load(
            write_reference_project(Path(tempfile.mkdtemp(prefix="mp_bench_ref_"))))
    ref: MechanicalModel = _CACHE["ref"]
    return ref


def check(name: str, expected: float, actual: float, tol: float, rel: bool = False,
          unit: str = "") -> dict[str, Any]:
    err = actual - expected
    limit = tol * abs(expected) if rel else tol
    return {"quantity": name, "expected": expected, "actual": actual, "error": err,
            "criterion": f"|error| <= {tol:g}{' x expected' if rel else ' ' + unit}",
            "passed": bool(abs(err) <= limit + 1e-15), "unit": unit}


def condition(name: str, ok: bool, detail: str) -> dict[str, Any]:
    return {"quantity": name, "expected": None, "actual": detail, "error": None,
            "criterion": "condition holds", "passed": bool(ok), "unit": ""}


# ---- A geometry and fits ------------------------------------------------------------------

def bench_a() -> dict[str, Any]:
    from motionproof.cad.features import measure_shaft_in_bore
    from motionproof.manufacturing.variants import fit_range
    from motionproof.scans import inspection as I
    from motionproof.scans import registration as R
    from motionproof.scans import synthetic as S
    from motionproof.tolerances import distributions as D
    from motionproof.tolerances.sampling import VariableSpace

    spec = reference().spec
    fit = next(f for f in spec.fits if f.id == "shaft_in_bearing")
    fr = fit_range(fit, spec)
    shaft, bore = spec.tolerance(fit.shaft), spec.tolerance(fit.bore)
    checks = [check("min clearance (bore LSL - shaft USL)", bore.lower_limit - shaft.upper_limit,
                    fr["min_clearance"], 1e-12, unit="mm"),
              check("max clearance (bore USL - shaft LSL)", bore.upper_limit - shaft.lower_limit,
                    fr["max_clearance"], 1e-12, unit="mm")]
    space = VariableSpace.from_model(spec)
    x = space.design("monte_carlo", 200_000, 7).values
    c = x[:, space.names.index(fit.bore)] - x[:, space.names.index(fit.shaft)]
    (mb, sb), (ms, ss) = D.mean_std(bore.distribution), D.mean_std(shaft.distribution)
    checks.append(check("clearance mean (Monte Carlo vs analytic)", mb - ms, float(c.mean()),
                        2e-5, unit="mm"))
    checks.append(check("clearance std (Monte Carlo vs RSS)", math.hypot(sb, ss),
                        float(c.std()), 0.01, rel=True, unit="mm"))
    m = measure_shaft_in_bore(9.98, 10.03, 20.0, 0.01)
    checks.append(check("exact B-rep radial gap with 10 um offset", 0.015,
                        m["min_radial_gap"], 1e-7, unit="mm"))
    # as-built recovery from a SYNTHETIC scan
    import trimesh

    mesh = trimesh.creation.cylinder(radius=4.0, height=40.0, sections=720)
    mesh.apply_translation([0, 0, 20])
    nominal = R.Nominal.from_mesh(mesh, "shaft", 150_000, seed=1)
    pts = S.cylinder_scan(8.030, 40.0, 20_000, noise=0.005, seed=3)
    moved, _ = S.rigid(pts, (0.3, 1.0, 0.2), 0.02, (0.4, -0.3, 0.2))
    from motionproof.scans.pointcloud import PointCloud, noise_estimate

    cloud = PointCloud(moved, units="mm")
    reg = R.icp(moved, nominal, init=R.coarse_align(moved, nominal),
                noise=noise_estimate(cloud), lock=("rz",))
    aligned = reg.apply(moved)
    sel = I.select_near_cylinder(aligned, np.zeros(3), np.array([0, 0, 1.0]), 4.0, 0.2, 1, 38)
    f = I.fit_cylinder(aligned[sel], np.array([0, 0, 1.0]))
    checks.append(check("diameter recovered from SYNTHETIC noisy scan (unknown pose)", 8.030,
                        f.diameter, 0.002, unit="mm"))
    checks.append(condition("registration accepted for inspection", reg.valid_for_inspection,
                            f"RMS {reg.rms:.4f} mm, {reg.iterations} iterations"))
    return {"title": "Shaft and bearing fit; as-built scan recovery", "area": "geometry",
            "fidelity": "F1 geometry", "synthetic": True,
            "purpose": "Fit limits, Monte Carlo clearance statistics, exact B-rep gap and "
                       "diameter recovery from a scan, each against an independent value.",
            "formulation": "clearance = bore - shaft; var = var_bore + var_shaft (independent); "
                           "radial gap = (D - d)/2 - offset",
            "checks": checks}


# ---- B planetary gearbox ------------------------------------------------------------------

def bench_b() -> dict[str, Any]:
    from motionproof.manufacturing.variants import nominal_values, resolve_variant
    from motionproof.simulation.tasks import StaticHold
    from motionproof.transmissions.gears import evaluate_stage

    m = reference()
    spec = m.spec
    s1, s2 = spec.gear_stages
    vals = nominal_values(spec)
    checks = [check("stage 1 ratio 1 + 54/12", 5.5, s1.ratio, 1e-12),
              check("stage 2 ratio 1 + 60/12", 6.0, s2.ratio, 1e-12),
              check("overall 33:1 from tooth counts", 33.0, s1.ratio * s2.ratio, 1e-12)]
    r2 = evaluate_stage(s2, spec, vals)
    checks.append(check("stage 2 backlash ((0.04 + 0.04)/2 + 0.012) / 9 mm", 0.052 / 9.0,
                        r2.backlash_angle, 1e-12, unit="rad"))
    v = resolve_variant(spec, vals)
    r1 = evaluate_stage(s1, spec, vals)
    checks.append(check("output backlash = s2 + s1 / 6", r2.backlash_angle + r1.backlash_angle / 6,
                        v.joints["shoulder"].backlash, 1e-12, unit="rad"))
    runout = vals | {"input_shaft_runout": 0.02}
    v2 = resolve_variant(spec, runout)
    amp = v2.joints["shoulder"].te[0][0]
    checks.append(check("transmission error amplitude e / r_sun / 33", 0.01 / 3.0 / 33.0, amp,
                        1e-12, unit="rad"))
    res = m.simulate(StaticHold(pose={"shoulder": 0.0}, duration=1.0), keep_trace=True)
    jv = m.nominal_variant().joints["shoulder"]
    tau = abs(res.trace["tau_out"][-1])
    checks.append(check("motor torque = output torque / 33 (eta does not act at rest)",
                        tau / 33.0, abs(res.trace["tau_motor"][-1]), 0.01, rel=True,
                        unit="N*m"))
    defl = res.measurements[-1]["angle_error"]["shoulder"]
    checks.append(check("output deflection = b/2 + tau/k", jv.backlash / 2 + tau / jv.stiffness,
                        defl, 0.01, rel=True, unit="rad"))
    return {"title": "Two-stage planetary gearbox (NEMA 17 reference, 33:1)",
            "area": "transmission", "fidelity": "F2 reduced order", "synthetic": True,
            "purpose": "Ratios, lost-motion relation, transmission error and the static "
                       "torque path of the reference gearbox.",
            "formulation": "i = 1 + z_r/z_s; backlash = ((j_sp + j_pr)/2 + c)/a; "
                           "TE = (e/2)/r_sun/i; static: tau_m = tau_out/N, defl = b/2 + tau/k",
            "checks": checks,
            "notes": ["Efficiency acts on transmitted power; at rest it does not change the "
                      "motor torque in this model. The dynamic efficiency check is in "
                      "tests/physics (mid-stroke torque)."]}


# ---- C two-link arm -----------------------------------------------------------------------

def bench_c() -> dict[str, Any]:
    m = reference()
    eng = m.engine
    lay = m.inventory["joints"]
    sh = np.array(lay["shoulder"]["pos"])
    el = np.array(lay["elbow"]["pos"])
    tip = np.array(m.spec.end_effector.offset)  # type: ignore[union-attr]
    l1 = float(el[0] - sh[0])
    l2 = float(tip[0] - el[0])
    checks = []
    fk_out = []
    for q1, q2 in ((0.0, 0.0), (0.7, 0.0), (0.4, 1.1), (-0.9, -0.5)):
        ee = eng.reference_ee({"shoulder": q1, "elbow": q2})
        fk_out.append({"q": [q1, q2], "ee": [float(v) for v in ee]})
        x = sh[0] + l1 * math.cos(q1) + l2 * math.cos(q1 + q2)
        z = sh[2] + l1 * math.sin(q1) + l2 * math.sin(q1 + q2)
        checks.append(check(f"FK error at q = ({q1}, {q2})", 0.0,
                            float(np.hypot(ee[0] - x, ee[2] - z)), 1e-9, unit="m"))
    target = np.array([sh[0] + 0.25, 0.0, sh[2] + 0.12])

    def resid(q: np.ndarray) -> np.ndarray:
        e = eng.reference_ee({"shoulder": q[0], "elbow": q[1]})
        return np.array([e[0] - target[0], e[2] - target[2]])

    sol = least_squares(resid, [0.3, 0.8], bounds=([-1.5708, -2.4], [1.5708, 2.4]))
    checks.append(check("IK (damped least squares, SciPy) reaches the target", 0.0,
                        float(np.linalg.norm(sol.fun)), 1e-9, unit="m"))
    r = float(np.linalg.norm(target[[0, 2]] - sh[[0, 2]]))
    cos2 = (r * r - l1 * l1 - l2 * l2) / (2 * l1 * l2)
    checks.append(check("IK elbow angle vs law of cosines", math.acos(cos2), abs(sol.x[1]),
                        1e-6, unit="rad"))
    mj = m.mj_model
    assert mj is not None
    data = mujoco.MjData(mj)
    mujoco.mj_forward(mj, data)
    expected_tau = sum(mj.body_mass[b] * G * (data.xipos[b][0] - sh[0]) for b in (2, 3))
    checks.append(check("shoulder gravity torque = sum m g x_com", expected_tau,
                        abs(float(data.qfrc_bias[0])), 1e-9, rel=True, unit="N*m"))
    import re

    from motionproof.workspace.maps import reliability_map

    xml = m.xml_path.read_text(encoding="utf-8")  # type: ignore[union-attr]
    upper = float(re.search(r'name="shoulder"[^>]*range="[-\d.]+ ([-\d.]+)"', xml).group(1))  # type: ignore[union-attr]
    checks.append(check("shoulder upper limit compiled from the model file", upper,
                        float(mj.jnt_range[0][1]), 1e-9, unit="rad"))
    cells = reliability_map(m, {"shoulder": [upper - 0.01, upper + 0.01]}, [{}])["cells"]
    checks.append(condition("pose inside the limit reachable, pose outside not",
                            cells[0]["reachable"] and not cells[1]["reachable"],
                            f"limit {upper} rad"))
    reach = l1 + l2
    ee = eng.reference_ee({"shoulder": 0.0, "elbow": 0.0})
    checks.append(check("workspace outer radius", reach, float(np.hypot(*(ee - sh)[[0, 2]])),
                        1e-9, unit="m"))
    return {"title": "Two-link arm kinematics and gravity torque", "area": "robotics",
            "fidelity": "kinematics", "synthetic": True,
            "purpose": "Forward and inverse kinematics against closed form, gravity torque "
                       "against the mass distribution.",
            "formulation": "x = l1 cos q1 + l2 cos(q1+q2); cos q2 = (r^2 - l1^2 - l2^2)/(2 l1 l2)",
            "checks": checks, "outputs": {"fk": fk_out, "ik_target": target.tolist()},
            "notes": ["IK is a SciPy least-squares solve over the model's own kinematics, "
                      "done in this benchmark; MotionProof has no general IK module."]}


# ---- D joint reversal ---------------------------------------------------------------------

def bench_d() -> dict[str, Any]:
    from motionproof.experiments.runner import Experiment, ExperimentConfig
    from motionproof.simulation.tasks import Reversal

    checks = []
    # slow moves end with the output stuck at a spring windup of about f/k on each side
    windup = 2 * 0.4 / 2000.0
    for b in (0.0, 0.005, 0.012):
        m = single_joint(gravity=False, friction=0.4, backlash=b, backlash_range=(0.0, 0.0))
        res = m.simulate(Reversal(target={"j": 0.3}, joint="j", excursion=0.2, move_time=0.8,
                                  settle=0.6))
        checks.append(check(f"lost motion = b + 2f/k for b = {b}", b + windup,
                            res.metrics["lost_motion"], 0.2 * windup, unit="rad"))
        checks.append(check(f"direction error at the tip = L (b + 2f/k) for b = {b}",
                            L_ARM * (b + windup), res.metrics["direction_error_ee"],
                            0.2 * windup * L_ARM, unit="m"))
    m = single_joint(gravity=False, friction=0.4)
    cfg = ExperimentConfig.model_validate({
        "name": "replay", "task": {"type": "reversal", "target": {"j": 0.3}, "joint": "j"},
        "sampling": {"samples": 6, "seed": 3}})
    exp = Experiment.create(m, cfg, Path(tempfile.mkdtemp()) / "e")
    exp.run(m)
    rep = [exp.replay(r["id"], m)["reproduced"] for r in exp.results()]
    checks.append(condition("replay reproduces every stored scenario exactly", all(rep),
                            f"{sum(rep)}/{len(rep)} reproduced"))
    return {"title": "Joint reversal and replay", "area": "transmission",
            "fidelity": "F2 reduced order", "synthetic": True,
            "purpose": "Dead-band lost motion on reversal and bit-exact replay.",
            "formulation": "no gravity, output friction f, stiffness k: lost motion = b + 2f/k "
                           "(friction traps spring windup f/k on each approach; the slow "
                           "move ends close to that bound); tip error = L (b + 2f/k)",
            "checks": checks}


# ---- E misalignment -----------------------------------------------------------------------

def bench_e() -> dict[str, Any]:
    from motionproof.manufacturing.variants import nominal_values, resolve_variant
    from motionproof.simulation.tasks import StaticHold

    m = single_joint(gravity=False, backlash_range=(0.0, 0.0))
    checks = []
    base = m.engine.run(m.nominal_variant(), StaticHold(pose={"j": 0.0}))
    for off in (5e-5, 2e-4):
        v = m.nominal_variant()
        v.joints["j"].offset = (0.0, 0.0, -off)
        r = m.engine.run(v, StaticHold(pose={"j": 0.0}))
        checks.append(check(f"tip error from {off * 1e3:g} mm joint offset", off,
                            r.metrics["ee_error_final"] - base.metrics["ee_error_final"],
                            1e-3, rel=True, unit="m"))
    slopes = []
    for tilt in (1e-3, 2e-3):
        v = m.nominal_variant()
        v.joints["j"].tilt_y = tilt
        r = m.engine.run(v, StaticHold(pose={"j": 0.0}))
        slopes.append(r.metrics["ee_error_final"])
    checks.append(check("sensitivity d(tip error)/d(tilt) = arm length", L_ARM,
                        (slopes[1] - slopes[0]) / 1e-3, 0.01, rel=True, unit="m/rad"))
    spec = reference().spec
    vals = nominal_values(spec)
    a = resolve_variant(spec, vals).joints["shoulder"]
    b = resolve_variant(spec, vals | {"housing_seat_diameter": vals["housing_seat_diameter"]
                                      + 0.006}).joints["shoulder"]
    checks.append(check("radial play grows with seat clearance (6 um)", 0.006e-3,
                        b.radial_play - a.radial_play, 1e-12, unit="m"))
    checks.append(check("axis tilt from extra play = play / bearing span", 0.006e-3 / 0.015,
                        b.tilt_y - a.tilt_y, 1e-12, unit="rad"))
    return {"title": "Misaligned assembly", "area": "geometry", "fidelity": "F2 reduced order",
            "synthetic": True,
            "purpose": "A known offset, tilt and clearance change propagate to the expected "
                       "tip error and joint misalignment.",
            "formulation": "tip error = offset; d(error)/d(tilt) = L; tilt = play / span",
            "checks": checks}


# ---- F loaded arm -------------------------------------------------------------------------

def bench_f() -> dict[str, Any]:
    from motionproof.simulation.tasks import StaticHold

    m = single_joint(backlash_range=(0.0, 0.0))
    checks = []
    for payload in (0.0, 0.5, 1.5):
        r = m.simulate(StaticHold(pose={"j": 0.0}, duration=1.0, payload_mass=payload))
        tau = (M_ARM + payload) * G * L_ARM
        checks.append(check(f"motor torque with {payload} kg payload = (m+mp) g L / N",
                            tau / RATIO, abs(r.trace["tau_motor"][-1]), 0.005, rel=True,
                            unit="N*m"))
        checks.append(check(f"torque utilisation with {payload} kg", tau / RATIO / 2.0,
                            r.metrics["torque_utilisation_peak"], 0.03, rel=True))
        checks.append(check(f"tip error with {payload} kg = L tau / k", L_ARM * tau / 2000.0,
                            r.metrics["ee_error_final"], 0.01, rel=True, unit="m"))
    over = 1.5 * 2.0 * RATIO / (G * L_ARM)
    r = m.simulate(StaticHold(pose={"j": 0.0}, duration=0.8, payload_mass=over))
    checks.append(condition("overload saturates the motor and loses position",
                            r.metrics["saturated_fraction"] > 0.5
                            and r.metrics["angle_error_final"] > 0.1,
                            f"saturated {r.metrics['saturated_fraction']:.2f}, angle error "
                            f"{r.metrics['angle_error_final']:.3f} rad"))
    return {"title": "Loaded arm: torque requirement and motor margin", "area": "robotics",
            "fidelity": "F2 reduced order", "synthetic": True,
            "purpose": "Payload torque, utilisation, deflection and overload behaviour.",
            "formulation": "tau = (m + mp) g L; tau_motor = tau / N; deflection = tau / k",
            "checks": checks}


# ---- G manufacturing process --------------------------------------------------------------

def bench_g() -> dict[str, Any]:
    from motionproof.process.model import (
        BatchPlan,
        ProcessModel,
        fit_linear_drift,
        generate_batch,
        variance_components,
    )

    def feat(name: str, target: float, shared: bool) -> dict[str, Any]:
        return {"feature": name, "process": "CNC turning", "target": target, "unit": "mm",
                "lower_limit": target - 0.05, "upper_limit": target + 0.05, "sources": [
                    {"level": "batch", "std": 0.010, "basis": "specified"},
                    {"level": "setup", "std": 0.006, "basis": "specified",
                     "shared_group": "f1" if shared else None},
                    {"level": "part", "std": 0.004, "basis": "specified"}]}
    checks = []
    m = ProcessModel.model_validate({"name": "g", "features": [feat("bore", 10.02, False),
                                                                 feat("shaft", 10.0, False)]})
    b = generate_batch(m, BatchPlan(batches=200, setups_per_batch=6, parts_per_setup=8, seed=1))
    vc = variance_components(b["actual"]["bore"], b["batch"], b["setup"])
    checks += [check("batch std recovered", 0.010, vc["batch_std"], 0.12, rel=True, unit="mm"),
               check("setup std recovered", 0.006, vc["setup_std"], 0.08, rel=True, unit="mm"),
               check("part std recovered", 0.004, vc["part_std"], 0.03, rel=True, unit="mm")]
    plan = BatchPlan(batches=300, setups_per_batch=5, parts_per_setup=10, seed=3)
    for shared, expected in ((False, math.sqrt(2 * (0.01**2 + 0.006**2 + 0.004**2))),
                             (True, math.sqrt(2 * (0.01**2 + 0.004**2)))):
        m = ProcessModel.model_validate({"name": "g", "features": [
            feat("bore", 10.02, shared), feat("shaft", 10.0, shared)]})
        bb = generate_batch(m, plan)
        c = bb["actual"]["bore"] - bb["actual"]["shaft"]
        checks.append(check(f"clearance std, setup error {'shared' if shared else 'independent'}",
                            expected, float(c.std()), 0.06, rel=True, unit="mm"))
    wear = ProcessModel.model_validate({"name": "w", "features": [{
        "feature": "bore", "process": "reaming", "target": 10.0, "unit": "mm",
        "lower_limit": 9.97, "upper_limit": 10.03,
        "sources": [{"level": "part", "std": 0.002, "basis": "specified"}],
        "drift": {"kind": "linear", "rate": 2e-5, "basis": "specified"}}]})
    bw = generate_batch(wear, BatchPlan(parts_per_setup=500, seed=2))
    checks.append(check("tool-wear drift rate recovered", 2e-5,
                        fit_linear_drift(bw["actual"]["bore"])["rate"], 0.1, rel=True,
                        unit="mm/part"))
    return {"title": "Hierarchical manufacturing variation", "area": "manufacturing",
            "fidelity": "statistical process model", "synthetic": True,
            "purpose": "Variance components, shared setup effects and drift are recovered "
                       "from a SYNTHETIC batch with known parameters.",
            "formulation": "x = target + drift + batch + setup + tool + part; shared setup "
                           "cancels in bore - shaft",
            "checks": checks}


# ---- H workspace --------------------------------------------------------------------------

def bench_h() -> dict[str, Any]:
    from motionproof.tolerances.sampling import VariableSpace
    from motionproof.workspace.maps import reliability_map, verify_pose

    m = reference()
    space = VariableSpace.from_model(m.spec)
    rows = [dict(zip(space.names, r.tolist(), strict=True))
            for r in space.design("monte_carlo", 8, 4).values]
    mp = reliability_map(m, {"shoulder": [-1.0, -0.5, 0.0, 0.5, 1.0]}, rows)
    checks = []
    for q in (-1.0, 0.0, 1.0):
        cell = next(c for c in mp["cells"] if c["pose"]["shoulder"] == q)
        direct = verify_pose(m, {"shoulder": q}, rows)
        checks.append(check(f"map RMS error vs direct Level 2 simulation at q = {q}",
                            direct["error_rms"], cell["error_rms"], 0.05, rel=True, unit="m"))
    return {"title": "Workspace reliability map", "area": "reliability",
            "fidelity": "L1 map checked against L2", "synthetic": True,
            "purpose": "Level 1 workspace map against direct dynamic simulation at grid poses.",
            "formulation": "per pose: static deflection b/2 + tau(q)/k propagated through FK",
            "checks": checks}


# ---- I degradation ------------------------------------------------------------------------

def bench_i() -> dict[str, Any]:
    from motionproof.degradation.model import Mechanism, fit_progression, lifetime_experiment
    from motionproof.experiments.runner import Constraint

    rng = np.random.default_rng(0)
    n = np.linspace(0, 1e6, 25)
    fit = fit_progression(n, 0.004 + 2e-9 * n + rng.normal(0, 2e-5, 25), "linear")
    checks = [check("wear rate recovered from SYNTHETIC data", 2e-9, fit["rate"], 0.05, rel=True,
                    unit="rad/cycle")]
    m = single_joint(backlash=0.004, backlash_range=(0.0, 0.0))
    windup = M_ARM * G * L_ARM / 2000.0
    expected = (2 * (0.005 - windup) - 0.004) / 2e-9
    res = lifetime_experiment(m, [Mechanism(joint="j", parameter="backlash", kind="linear",
                                            rate=2e-9, basis="assumed")],
                              [0, 5e5, 1e6, 1.5e6, 2e6],
                              [Constraint(name="a", metric="angle_error_final", op="<=",
                                          limit=0.005)], pose={"j": 0.0})
    checks.append(check("threshold crossing (cycles)", expected,
                        res["threshold_crossings"]["a"]["cycles"], 1e-3, rel=True))
    return {"title": "Lifetime degradation", "area": "reliability", "fidelity": "L1",
            "synthetic": True,
            "purpose": "Recovery of a SYNTHETIC linear wear law and its requirement crossing.",
            "formulation": "b(n) = b0 + r n; crossing where b/2 + tau/k = limit",
            "checks": checks}


# ---- J hardware ---------------------------------------------------------------------------

def bench_j() -> dict[str, Any]:
    return {"title": "Hardware measurements", "area": "hardware", "fidelity": "L4 physical",
            "synthetic": False, "status": "NOT RUN",
            "purpose": "Predicted versus measured behaviour of a physical rig.",
            "formulation": "-", "checks": [],
            "notes": ["No physical rig or measurements exist. The software path is verified "
                      "with a SIMULATED DEVICE in tests/integration/test_hardware.py; that is "
                      "not physical validation."]}


# ---- K adaptive sampling ------------------------------------------------------------------

def bench_k() -> dict[str, Any]:
    from motionproof.adaptive.sampler import run_adaptive

    def g(x: np.ndarray) -> float:
        return float(3.0 - (x[0] + x[1]) / math.sqrt(2.0))

    def pop(n: int, seed: int) -> np.ndarray:
        return np.random.default_rng(seed).normal(size=(n, 2))

    truth = float(stats.norm.cdf(-3.0))
    a_err, r_err, sims = [], [], []
    for seed in range(10):
        res = run_adaptive(g, pop, np.array([[-4.0, 4.0], [-4.0, 4.0]]), initial=12, budget=60,
                           population=40_000, seed=seed)
        a_err.append(abs(res["surrogate"]["predicted_failure_fraction"] - truth) / truth)
        sims.append(res["simulations"]["total"])
        draws = pop(res["simulations"]["total"], 1000 + seed)
        r_err.append(abs(np.mean([g(r) < 0 for r in draws]) - truth) / truth)
    checks = [check("median relative error, adaptive (<= 60 true evaluations)", 0.0,
                    float(np.median(a_err)), 0.4),
              condition("adaptive beats random at the same number of true evaluations",
                        float(np.median(a_err)) < float(np.median(r_err)),
                        f"median relative error adaptive {np.median(a_err):.3f}, random "
                        f"{np.median(r_err):.3f}; mean true evaluations {np.mean(sims):.1f}")]
    return {"title": "Adaptive versus random sampling", "area": "reliability",
            "fidelity": "analytic limit state", "synthetic": True,
            "purpose": "Failure-probability accuracy at equal true-evaluation budgets, 10 seeds.",
            "formulation": "g = 3 - (x1 + x2)/sqrt(2), x ~ N(0, I); P(fail) = Phi(-3) = 1.35e-3",
            "checks": checks,
            "notes": ["Rare-event case chosen on purpose; for failure fractions of tens of "
                      "percent random sampling is competitive and no advantage is claimed."]}


# ---- L multi-fidelity ---------------------------------------------------------------------

def bench_l() -> dict[str, Any]:
    from motionproof.fidelity.static import discrepancy, static_pose, sufficient

    checks = []
    m = single_joint(backlash=0.01, backlash_range=(0.0, 0.0))
    lo = static_pose(m, m.nominal_variant(), {"j": 0.0})
    analytic = 0.005 + M_ARM * G * L_ARM / 2000.0
    checks.append(check("L1 deflection vs closed form", analytic,
                        lo["metrics"]["angle_error_final"], 1e-4, rel=True, unit="rad"))
    d = discrepancy(m, [{}], {"j": 0.0})
    checks.append(check("L1 - L2 tip error difference (frictionless)", 0.0,
                        d["metrics"]["ee_error_final"]["max_abs_difference"], 2e-5, unit="m"))
    mf = single_joint(backlash=0.01, backlash_range=(0.0, 0.0), friction=0.5)
    df = discrepancy(mf, [{}], {"j": 0.5})
    band = df["metrics"]["ee_error_final"]["p95_abs_difference"]
    v = static_pose(mf, mf.nominal_variant(), {"j": 0.5})["metrics"]["ee_error_final"]
    flag = sufficient(v, "<=", v + 0.5 * band, band)
    checks.append(condition("near-limit L1 result flagged as insufficient",
                            not flag["sufficient"],
                            f"L1/L2 difference with friction {band * 1e6:.1f} um; verdict "
                            f"{flag['verdict']}"))
    return {"title": "Multi-fidelity agreement and sufficiency", "area": "reliability",
            "fidelity": "L1 vs L2", "synthetic": True,
            "purpose": "Analytic vs L1 vs L2, and the rule that refuses an L1 verdict near a "
                       "limit.", "formulation": "deflection = b/2 + m g L cos q / k",
            "checks": checks,
            "notes": ["Level 3 (contact, flexible bodies) is not implemented; no comparison."]}


# ---- M challenge --------------------------------------------------------------------------

def bench_m() -> dict[str, Any]:
    from motionproof.challenge.engine import Challenge, ChallengeConfig

    windup = M_ARM * G * L_ARM / 2000.0
    cfg = ChallengeConfig.model_validate({
        "name": "analytic", "search_fidelity": "L1", "l1_pose": {"j": 0.0},
        "experiment": {"name": "hold", "task": {"type": "static_hold", "pose": {"j": 0.0},
                                                "duration": 0.6},
                       "constraints": [{"name": "angle", "metric": "angle_error_final",
                                        "op": "<=", "limit": 0.008 + windup}]},
        "variables": [{"tolerance": "backlash_tol", "kind": "scale", "lower": 0.2,
                       "upper": 1.0}],
        "costs": {"backlash_tol": {"coefficient": 1.0}}, "cost_source": "benchmark 1/scale",
        "reliability": {"target": 0.9, "confidence": 0.9}, "samples": 40,
        "verify_samples": 60, "screen": 8, "refine_generations": 3, "seed": 1})
    m = single_joint()
    res = Challenge(m, cfg).run()
    chosen = next((c for c in res["candidates"] if c["id"] == res["chosen"]), None)
    checks = [condition("a verified candidate exists", chosen is not None, str(res["chosen"]))]
    if chosen:
        s = chosen["decision"]["scale:backlash_tol"]
        checks.append(condition("chosen scale inside the analytic feasible band 0.5 to 0.75",
                                0.5 <= s <= 0.75, f"scale {s:.4f}"))
    infeasible = Challenge(m, cfg.model_copy(update={"experiment": cfg.experiment.model_copy(
        update={"constraints": [cfg.experiment.constraints[0].model_copy(
            update={"limit": 0.004 + windup})]}), "refine_generations": 1})).run()
    checks.append(condition("infeasible requirement reported as infeasible",
                            infeasible["chosen"] is None, "; ".join(infeasible["notes"])))
    ycfg = ChallengeConfig.model_validate(cfg.model_dump() | {
        "costs": {"backlash_tol": {"model": "yield", "unit_cost": 1.0, "process": {
            "mean": 0.01, "std": 0.004, "basis": "specified", "source": "benchmark input"}}},
        "samples": 60, "refine_generations": 2})
    yres = Challenge(m, ycfg).run()
    ych = next((c for c in yres["candidates"] if c["id"] == yres["chosen"]), None)
    outputs = {"reciprocal_chosen": None if chosen is None else {
        "scale": chosen["decision"]["scale:backlash_tol"], "cost": chosen["cost"]},
        "yield_chosen": None if ych is None else {
        "scale": ych["decision"]["scale:backlash_tol"], "cost": ych["cost"]}}
    checks.append(condition("yield model: a verified candidate exists", ych is not None,
                            str(yres["chosen"])))
    if ych:
        s = ych["decision"]["scale:backlash_tol"]
        y = 2 * stats.norm.cdf(0.01 * s / 0.004) - 1
        checks.append(check("yield model: cost per accepted part = 1 / yield", 1 / y,
                            ych["cost"], 1e-12, rel=True))
        checks.append(condition("yield model: chosen scale inside the analytic band 0.5 to 0.75",
                                0.5 <= s <= 0.75, f"scale {s:.4f}"))
    return {"title": "Engineering Challenge on an analytic case", "area": "optimisation",
            "fidelity": "L1 search, L2 verification", "synthetic": True,
            "purpose": "Known feasible and infeasible requirements; optimum against the "
                       "analytic band.",
            "formulation": "uniform: F(s) = max(0, (0.01 + 0.01 s - b_lim) / (0.02 s)), "
                           "cost = 1/s; yield: process N(0.01, 0.004) sorted to 0.01 +- 0.01 s, "
                           "cost = 1 / (2 Phi(0.01 s / 0.004) - 1)",
            "checks": checks, "outputs": outputs}


# ---- N root cause -------------------------------------------------------------------------

def bench_n() -> dict[str, Any]:
    from motionproof.experiments.runner import Experiment, ExperimentConfig
    from motionproof.rootcause.analysis import investigate

    m = single_joint()
    cfg = ExperimentConfig.model_validate({
        "name": "rc", "task": {"type": "static_hold", "pose": {"j": 0.0}, "duration": 0.8},
        "sampling": {"samples": 40, "seed": 2},
        "operating": {"payload_mass": {"type": "uniform", "low": 0.0, "high": 0.02}},
        "constraints": [{"name": "tip", "metric": "ee_error_final", "op": "<=",
                         "limit": 0.00265}]})
    exp = Experiment.create(m, cfg, Path(tempfile.mkdtemp()) / "e")
    exp.run(m)
    failed = [r for r in exp.results() if not r["passed"]]
    rc = investigate(exp, failed[0]["id"], m)
    top = rc["contributions"][0]
    return {"title": "Root cause of a deliberate failure", "area": "reliability",
            "fidelity": "F2 reduced order", "synthetic": True,
            "purpose": "The variable that causes the failure is ranked first by counterfactual "
                       "rerun.", "formulation": "tip error = L (b/2 + tau/k); payload minor",
            "checks": [condition("dominant variable identified", top["parameter"] ==
                                 "backlash_tol", top["parameter"]),
                       condition("counterfactual rerun removes the failure",
                                 bool(top["counterfactual"]["fixes_failure"]),
                                 "metric after rerun "
                                 f"{top['counterfactual']['metric_after']:.6g}")]}


BENCHMARKS: dict[str, tuple[str, Callable[[], dict[str, Any]]]] = {
    "A": ("fit", bench_a), "B": ("gearbox", bench_b), "C": ("two_link", bench_c),
    "D": ("reversal", bench_d), "E": ("misalignment", bench_e), "F": ("loaded_arm", bench_f),
    "G": ("process", bench_g), "H": ("workspace", bench_h), "I": ("degradation", bench_i),
    "J": ("hardware", bench_j), "K": ("adaptive", bench_k), "L": ("fidelity", bench_l),
    "M": ("challenge", bench_m), "N": ("root_cause", bench_n),
}


def resolve(key: str) -> str:
    k = key.upper()
    if k in BENCHMARKS:
        return k
    for bid, (name, _) in BENCHMARKS.items():
        if name == key.lower():
            return bid
    raise KeyError(f"unknown benchmark {key!r}; choose from "
                   + ", ".join(f"{b} ({n})" for b, (n, _) in BENCHMARKS.items()))


def run(keys: list[str] | None = None) -> list[dict[str, Any]]:
    out = []
    for bid in [resolve(k) for k in keys] if keys else list(BENCHMARKS):
        name, fn = BENCHMARKS[bid]
        t = time.perf_counter()
        try:
            r = fn()
        except Exception as exc:  # a crashing benchmark is a failed benchmark, not a skip
            r = {"title": name, "checks": [], "error": f"{type(exc).__name__}: {exc}"}
        r |= {"id": bid, "name": name, "seconds": round(time.perf_counter() - t, 2)}
        r.setdefault("status", "ERROR" if "error" in r else
                     "PASS" if r["checks"] and all(c["passed"] for c in r["checks"])
                     else "FAIL")
        out.append(r)
    return out


def _fmt(v: Any) -> str:
    if v is None:
        return "-"
    if isinstance(v, float):
        return f"{v:.6g}"
    return str(v)


def write_markdown(results: list[dict[str, Any]], path: str | Path, *,
                   reproducible: bool = False) -> Path:
    """Write the results table. ``reproducible`` leaves out the run date and the timings, so
    publishing the same results twice produces the same file."""
    when = "" if reproducible else f" {datetime.now(UTC).isoformat(timespec='seconds')}"
    lines = ["# Benchmark results", "",
             f"Generated{when} by "
             "`uv run motionproof benchmark run` on " f"{platform.platform()}, MotionProof "
             f"{motionproof.__version__}, MuJoCo {mujoco.__version__}, NumPy {np.__version__}.",
             "", "Every number below comes from this run. Benchmarks marked synthetic use "
             "generated data with known ground truth; none of them is physical validation.", "",
             "| ID | Benchmark | Status | Checks | Synthetic |"
             + ("" if reproducible else " Time (s) |"),
             "|---|---|---|---|---|" + ("" if reproducible else "---|")]
    for r in results:
        n = len(r["checks"])
        ok = sum(c["passed"] for c in r["checks"])
        lines.append(f"| {r['id']} | {r['title']} | **{r['status']}** | {ok}/{n} | "
                     f"{'yes' if r.get('synthetic') else 'no'} |"
                     + ("" if reproducible else f" {r.get('seconds', '-')} |"))
    for r in results:
        lines += ["", f"## {r['id']}. {r['title']}", "",
                  f"- Status: **{r['status']}**",
                  f"- Purpose: {r.get('purpose', '-')}",
                  f"- Formulation: {r.get('formulation', '-')}",
                  f"- Fidelity: {r.get('fidelity', '-')}", ""]
        if r.get("error"):
            lines.append(f"Error: `{r['error']}`")
        if r["checks"]:
            lines += ["| Quantity | Expected | Actual | Error | Criterion | Result |",
                      "|---|---|---|---|---|---|"]
            for c in r["checks"]:
                lines.append(f"| {c['quantity']} | {_fmt(c['expected'])} | {_fmt(c['actual'])}"
                             f" | {_fmt(c['error'])} | {c['criterion']} | "
                             f"{'pass' if c['passed'] else 'FAIL'} |")
        for note in r.get("notes", []):
            lines.append(f"- Note: {note}")
        lines.append(f"- Reproduce: `uv run motionproof benchmark run {r['name']}`")
    p = Path(path)
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return p
