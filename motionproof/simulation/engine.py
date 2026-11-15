"""Task-level dynamics of a geared mechanism (Fidelity 2, reduced order).

MuJoCo integrates the rigid multibody system. Each driven joint gets a drive train that is
integrated alongside it:

    motor rotor (output-referred angle th_r, inertia J_m * N^2)
        -- backlash dead band (half-width b/2) + torsional spring k + damper c --
    link joint (MuJoCo DOF, angle th_o)

    gap  = th_r + TE(th_r) + zero_offset - th_o
    s    = gap - clip(gap, -b/2, +b/2)            # engaged deflection, 0 inside the dead band
    tau_c = k*s + c*(w_r - w_o) while engaged (never pulling across the gap)

Gearbox losses are a load-dependent mesh friction ``(1 - eta) * |tau_c|`` opposing output
motion (solved implicitly as a MuJoCo friction-loss constraint, so it also produces stiction):
a driving gearbox delivers ``eta * tau_c``. The motor is position-controlled on
the *motor* side (PD plus load feedforward, limited by the torque-speed curve): lost motion
in the gearbox is therefore not corrected, as on a real stepper or a servo with a motor-side
encoder.

No tooth contact is resolved. See docs/backlash-modelling.md for derivation and validation.
"""

from __future__ import annotations

import copy
import math
from dataclasses import dataclass, field
from typing import Any

import mujoco
import numpy as np

from motionproof.core.schema import MechanicalModelSpec
from motionproof.core.transforms import (
    axis_angle_matrix,
    matrix_to_quat,
    normalize,
    quat_multiply,
    quat_to_matrix,
)
from motionproof.manufacturing.variants import JointVariant, Variant
from motionproof.simulation.tasks import Plan, _Task, build_plan
from motionproof.transmissions.motor import available_torque

VEL_SMOOTH = 0.01  # rad/s, sign smoothing used when reporting friction torque
ROTOR_SMOOTH = 0.05  # rad/s (output-referred), smoothing of motor friction
MAX_TRACE = 400
HELD_BAND = 1e-7  # rad, half-width of the range that locks an ideally held joint


class SimulationError(RuntimeError):
    pass


@dataclass
class SimResult:
    valid: bool
    metrics: dict[str, float]
    measurements: list[dict[str, Any]]
    trace: dict[str, list[float]] = field(default_factory=dict)
    message: str = ""

    def to_dict(self, with_trace: bool = True) -> dict[str, Any]:
        d: dict[str, Any] = {"valid": self.valid, "metrics": self.metrics,
                             "measurements": self.measurements, "message": self.message}
        if with_trace:
            d["trace"] = self.trace
        return d


def apply_joint_geometry(model: mujoco.MjModel, joint_id: int, tilt_x: float, tilt_y: float,
                         offset: tuple[float, float, float]) -> None:
    """Misalign a joint: rotate its child body about the joint anchor and shift it.

    ``tilt_x`` rotates about e1 = axis x up (horizontal for a horizontal axis) and ``tilt_y``
    about e2 = axis x e1; both are perpendicular to the joint axis. ``offset`` is expressed in
    the parent frame. This is a kinematic (Level C) representation of the misalignment.
    """
    body = int(model.jnt_bodyid[joint_id])
    r_body = quat_to_matrix(model.body_quat[body])
    anchor = model.body_pos[body] + r_body @ model.jnt_pos[joint_id]
    axis = normalize(r_body @ model.jnt_axis[joint_id])
    up = np.array([0.0, 0.0, 1.0]) if abs(axis[2]) < 0.9 else np.array([1.0, 0.0, 0.0])
    e1 = normalize(np.cross(axis, up))
    e2 = np.cross(axis, e1)
    rot = axis_angle_matrix(e2, tilt_y) @ axis_angle_matrix(e1, tilt_x)
    model.body_pos[body] = anchor + rot @ (model.body_pos[body] - anchor) + np.asarray(offset)
    model.body_quat[body] = quat_multiply(matrix_to_quat(rot), model.body_quat[body])


def apply_payload(model: mujoco.MjModel, body: int, mass: float, position: np.ndarray) -> None:
    """Add a point mass rigidly to ``body`` at ``position`` (body frame)."""
    if mass <= 0:
        return
    m0 = float(model.body_mass[body])
    c0 = model.body_ipos[body].copy()
    r0 = quat_to_matrix(model.body_iquat[body])
    i0 = r0 @ np.diag(model.body_inertia[body]) @ r0.T
    total = m0 + mass
    com = (m0 * c0 + mass * position) / total

    def shift(inertia: np.ndarray, m: float, d: np.ndarray) -> np.ndarray:
        return inertia + m * (float(d @ d) * np.eye(3) - np.outer(d, d))

    inertia = shift(i0, m0, c0 - com) + shift(np.zeros((3, 3)), mass, position - com)
    w, v = np.linalg.eigh(inertia)
    if np.linalg.det(v) < 0:
        v[:, 2] = -v[:, 2]
    model.body_mass[body] = total
    model.body_ipos[body] = com
    model.body_inertia[body] = np.maximum(w, 1e-12)
    model.body_iquat[body] = matrix_to_quat(v)


class _Drive:
    """Run-time state of one drive train."""

    def __init__(self, name: str, jv: JointVariant, spec: MechanicalModelSpec,
                 model: mujoco.MjModel, link_inertia: float):
        drive = spec.drives[name]
        self.name = name
        self.jv = jv
        self.motor = drive.motor
        self.jid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, name)
        if self.jid < 0:
            raise SimulationError(f"drive joint {name!r} does not exist in the dynamics model")
        self.qadr = int(model.jnt_qposadr[self.jid])
        self.dadr = int(model.jnt_dofadr[self.jid])
        n = jv.ratio
        self.n = n
        self.j_rotor = self.motor.rotor_inertia * n * n
        self.k = jv.stiffness
        self.c = 2.0 * jv.damping_ratio * math.sqrt(self.k * self.j_rotor)
        self.half = jv.backlash / 2.0
        j_total = self.j_rotor + link_inertia
        ctl = drive.controller
        w = ctl.bandwidth
        self.kp = ctl.kp if ctl.kp is not None else j_total * w * w
        self.kd = ctl.kd if ctl.kd is not None else 1.8 * j_total * w
        self.th_r = 0.0
        self.w_r = 0.0

    def te(self, th_r: float) -> float:
        return sum(a * math.sin(c * th_r + ph) for a, c, ph in self.jv.te)


class Engine:
    """Simulates tasks for one mechanical model. Reusable across variants."""

    def __init__(self, spec: MechanicalModelSpec, model: mujoco.MjModel):
        self.spec = spec
        self.nominal = model
        self.driven = list(spec.drives)
        if not self.driven:
            raise SimulationError("the model defines no drives: nothing can be actuated")
        for name in [*self.driven, *spec.held_joints]:
            jid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, name)
            if jid < 0:
                raise SimulationError(f"joint {name!r} does not exist in the dynamics model")
            if model.jnt_type[jid] not in (mujoco.mjtJoint.mjJNT_HINGE,):
                raise SimulationError(f"joint {name!r}: only revolute joints can be driven")
        ee = spec.end_effector
        if ee is None:
            raise SimulationError("the model has no end effector defined")
        self.ee_body = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, ee.body)
        if self.ee_body < 0:
            raise SimulationError(f"end-effector body {ee.body!r} does not exist")
        self.ee_offset = np.asarray(ee.offset, dtype=float)
        self._ref_data = mujoco.MjData(model)

    # ------------------------------------------------------------------ helpers

    def _ee(self, data: mujoco.MjData) -> np.ndarray:
        return np.asarray(data.xpos[self.ee_body]
                          + data.xmat[self.ee_body].reshape(3, 3) @ self.ee_offset,
                          dtype=float)

    def reference_ee(self, pose: dict[str, float]) -> np.ndarray:
        """End-effector position of the nominal design at a commanded pose."""
        d = self._ref_data
        mujoco.mj_resetData(self.nominal, d)
        for name, value in {**self.spec.held_joints, **pose}.items():
            jid = mujoco.mj_name2id(self.nominal, mujoco.mjtObj.mjOBJ_JOINT, name)
            d.qpos[self.nominal.jnt_qposadr[jid]] = value
        mujoco.mj_kinematics(self.nominal, d)
        return self._ee(d).copy()

    def build_model(self, variant: Variant, payload_mass: float) -> mujoco.MjModel:
        model = copy.copy(self.nominal)
        model.opt.timestep = self.spec.simulation.timestep
        model.opt.gravity[:] = self.spec.simulation.gravity
        for name, jv in variant.joints.items():
            jid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, name)
            apply_joint_geometry(model, jid, jv.tilt_x, jv.tilt_y, jv.offset)
            dof = model.jnt_dofadr[jid]
            model.dof_frictionloss[dof] = jv.friction  # updated every step by the drive
            model.dof_damping[dof] = jv.damping
        # Held joints (ideal servo): a zero-width joint range enforced by the constraint
        # solver. This is unconditionally stable, unlike a stiff explicit PD loop.
        for name, value in self.spec.held_joints.items():
            jid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, name)
            model.jnt_limited[jid] = 1
            model.jnt_range[jid] = (value - HELD_BAND, value + HELD_BAND)
            model.jnt_solref[jid] = (2.0 * model.opt.timestep, 1.0)
            model.jnt_solimp[jid, :3] = (0.999, 0.9999, 1e-6)
        apply_payload(model, self.ee_body, payload_mass, self.ee_offset)
        return model

    # ------------------------------------------------------------------ simulation

    def run(self, variant: Variant, task: _Task, keep_trace: bool = False,
            trace_points: int = MAX_TRACE) -> SimResult:
        plan = build_plan(task, self.driven)
        try:
            return self._run(variant, plan, task.payload_mass, keep_trace, trace_points)
        except (FloatingPointError, mujoco.FatalError) as exc:
            return SimResult(False, {}, [], message=f"simulation aborted: {exc}")

    def _run(self, variant: Variant, plan: Plan, payload: float, keep_trace: bool,
             trace_points: int = MAX_TRACE) -> SimResult:
        spec = self.spec
        model = self.build_model(variant, payload)
        data = mujoco.MjData(model)
        dt = float(model.opt.timestep)
        q0, _ = plan.command(0.0)

        for name, value in spec.held_joints.items():
            jid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, name)
            data.qpos[model.jnt_qposadr[jid]] = value
        for name, q in zip(self.driven, q0, strict=True):
            jid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, name)
            data.qpos[model.jnt_qposadr[jid]] = q
        mujoco.mj_forward(model, data)

        def dof_inertia(dof: int) -> float:
            unit, res = np.zeros(model.nv), np.zeros(model.nv)
            unit[dof] = 1.0
            mujoco.mj_mulM(model, data, res, unit)
            return float(res[dof])

        drives = [
            _Drive(n, variant.joints[n], spec, model, dof_inertia(int(model.jnt_dofadr[
                mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, n)])))
            for n in self.driven
        ]
        # start in static equilibrium: the load rests on one flank of the dead band
        for d, q in zip(drives, q0, strict=True):
            d.th_r = q
            for _ in range(4):
                mujoco.mj_forward(model, data)
                load = -float(data.qfrc_bias[d.dadr])  # torque the load exerts on the joint
                s = -load / d.k
                gap = s + math.copysign(d.half, s) if s != 0.0 else 0.0
                data.qpos[d.qadr] = d.th_r + d.te(d.th_r) + d.jv.zero_offset - gap

        n_steps = int(math.ceil(plan.duration / dt))
        stride = max(1, n_steps // max(trace_points, 1))
        marks = sorted(plan.measurements)
        mark_idx = 0
        measurements: list[dict[str, Any]] = []
        trace: dict[str, list[float]] = {k: [] for k in (
            "t", "q_cmd", "q_motor", "q_out", "w_out", "acc_out", "tau_motor", "tau_out",
            "tau_available", "tracking_error", "ee_error")} if keep_trace else {}
        primary = drives[0]

        peak_util = peak_speed = 0.0
        sum_tau2 = sum_err2 = max_err = max_te = 0.0
        saturated = moving = 0
        max_vel = max_acc = 0.0
        qfrc = data.qfrc_applied

        for step in range(n_steps + 1):
            t = step * dt
            q_cmd, qd_cmd = plan.command(t)
            for i, d in enumerate(drives):
                th_o = float(data.qpos[d.qadr])
                w_o = float(data.qvel[d.dadr])
                jv = d.jv
                gap = d.th_r + d.te(d.th_r) + jv.zero_offset - th_o
                s = gap - min(max(gap, -d.half), d.half)
                tau_c = 0.0
                if s != 0.0:
                    tau_c = d.k * s + d.c * (d.w_r - w_o)
                    if tau_c * s < 0.0:  # a flank can push, never pull
                        tau_c = 0.0
                # Friction is solved implicitly by MuJoCo (stable, with true stiction): constant
                # output friction plus the load-dependent mesh loss (1 - eta) * |tau_c|.
                loss = jv.friction + (1.0 - jv.efficiency) * abs(tau_c)
                model.dof_frictionloss[d.dadr] = loss
                qfrc[d.dadr] = tau_c
                tau_out = tau_c - loss * math.tanh(w_o / VEL_SMOOTH)

                # Motor-side position control with load feedforward: the drive cancels the
                # coupling torque and its own friction, so within its torque limit the rotor
                # follows the command like a stepper or a stiff servo.
                fric_m = d.motor.friction_torque * d.n * math.tanh(d.w_r / ROTOR_SMOOTH)
                err = q_cmd[i] - d.th_r
                want = d.kp * err + d.kd * (qd_cmd[i] - d.w_r) + tau_c + fric_m
                avail = available_torque(d.motor, d.w_r * d.n, jv.torque_scale) * d.n
                tau_m = min(max(want, -avail), avail)
                if tau_m != want:
                    saturated += 1
                d.w_r += dt * (tau_m - tau_c - fric_m) / d.j_rotor
                d.th_r += dt * d.w_r

                shaft_tau = abs(tau_m) / d.n
                rated = d.motor.peak_torque * jv.torque_scale
                peak_util = max(peak_util, shaft_tau / rated if rated > 0 else math.inf)
                peak_speed = max(peak_speed, abs(d.w_r) * d.n / d.motor.max_speed)
                sum_tau2 += shaft_tau * shaft_tau
                e_out = q_cmd[i] - th_o
                max_te = max(max_te, abs(gap))
                if qd_cmd[i] != 0.0:
                    moving += 1
                    sum_err2 += e_out * e_out
                    max_err = max(max_err, abs(e_out))
                max_vel = max(max_vel, abs(w_o))
                if i == 0 and keep_trace and step % stride == 0:
                    ref = self.reference_ee(dict(zip(self.driven, q_cmd, strict=True)))
                    trace["t"].append(t)
                    trace["q_cmd"].append(q_cmd[0])
                    trace["q_motor"].append(d.th_r)
                    trace["q_out"].append(th_o)
                    trace["w_out"].append(w_o)
                    trace["acc_out"].append(float(data.qacc[d.dadr]))
                    trace["tau_motor"].append(tau_m / d.n)
                    trace["tau_out"].append(tau_out)
                    trace["tau_available"].append(avail / d.n)
                    trace["tracking_error"].append(e_out)
                    trace["ee_error"].append(float(np.linalg.norm(self._ee(data) - ref)))

            while mark_idx < len(marks) and t >= marks[mark_idx][0] - 0.5 * dt:
                label = marks[mark_idx][1]
                pose = dict(zip(self.driven, q_cmd, strict=True))
                ee = self._ee(data)
                ref = self.reference_ee(pose)
                measurements.append({
                    "label": label, "time": t,
                    "commanded": pose,
                    "output": {d.name: float(data.qpos[d.qadr]) for d in drives},
                    "motor": {d.name: d.th_r for d in drives},
                    "angle_error": {d.name: float(pose[d.name] - data.qpos[d.qadr])
                                    for d in drives},
                    "residual_speed": max(abs(float(data.qvel[d.dadr])) for d in drives),
                    "ee": ee.tolist(), "ee_reference": ref.tolist(),
                    "ee_error": float(np.linalg.norm(ee - ref)),
                })
                mark_idx += 1

            mujoco.mj_step(model, data)
            max_acc = max(max_acc, abs(float(data.qacc[primary.dadr])))
            if not (math.isfinite(float(data.qpos[primary.qadr]))
                    and math.isfinite(primary.th_r)):
                return SimResult(False, {}, measurements, trace,
                                 f"non-finite state at t = {t:.4f} s")
        if data.warning[mujoco.mjtWarning.mjWARN_BADQACC].number:
            return SimResult(False, {}, measurements, trace, "MuJoCo reported unstable qacc")

        total = (n_steps + 1) * len(drives)
        metrics = self._metrics(variant, measurements, primary)
        cont = primary.motor.continuous_torque * primary.jv.torque_scale
        metrics.update({
            "torque_utilisation_peak": peak_util,
            "torque_rms_ratio": math.sqrt(sum_tau2 / total) / cont,
            "motor_speed_ratio_peak": peak_speed,
            "saturated_fraction": saturated / total,
            "tracking_error_max": max_err,
            "tracking_error_rms": math.sqrt(sum_err2 / moving) if moving else 0.0,
            "transmission_deflection_max": max_te,
            "output_velocity_max": max_vel,
            "output_acceleration_max": max_acc,
            "task_duration": plan.duration,
        })
        return SimResult(True, metrics, measurements, trace)

    def _metrics(self, variant: Variant, meas: list[dict[str, Any]],
                 primary: _Drive) -> dict[str, float]:
        ee_err = np.array([m["ee_error"] for m in meas]) if meas else np.zeros(1)
        ang = np.array([max(abs(v) for v in m["angle_error"].values()) for m in meas]
                       ) if meas else np.zeros(1)
        out: dict[str, float] = {
            "ee_error_final": float(ee_err[-1]),
            "ee_error_max": float(ee_err.max()),
            "ee_error_mean": float(ee_err.mean()),
            "ee_error_rms": float(np.sqrt(np.mean(ee_err**2))),
            "angle_error_final": float(ang[-1]),
            "angle_error_max": float(ang.max()),
            "settling_speed_final": float(meas[-1]["residual_speed"]) if meas else 0.0,
            "backlash": float(sum(j.backlash for j in variant.joints.values())),
            "radial_play": float(max((j.radial_play for j in variant.joints.values()),
                                     default=0.0)),
        }
        by_label: dict[str, list[dict[str, Any]]] = {}
        for m in meas:
            by_label.setdefault(m["label"], []).append(m)
        if "approach_up" in by_label and "approach_down" in by_label:
            up = by_label["approach_up"][-1]["output"][primary.name]
            down = by_label["approach_down"][-1]["output"][primary.name]
            out["lost_motion"] = abs(down - up)
            out["direction_error_ee"] = float(np.linalg.norm(
                np.array(by_label["approach_down"][-1]["ee"])
                - np.array(by_label["approach_up"][-1]["ee"])))
        spreads = []
        for group in by_label.values():
            if len(group) > 1:
                pts = np.array([g["ee"] for g in group])
                spreads.append(float(np.linalg.norm(pts.max(axis=0) - pts.min(axis=0))))
        if spreads:
            out["repeatability"] = max(spreads)
        if variant.stages:
            out["min_mesh_backlash_mm"] = min(s.min_mesh_backlash_mm for s in variant.stages)
        if variant.fits:
            out["min_fit_clearance"] = min(f.clearance for f in variant.fits)
            out["max_fit_interference"] = max(-f.clearance for f in variant.fits)
        return out
