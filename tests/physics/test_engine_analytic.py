"""Dynamics engine against closed-form references.

Each test states the analytic expectation and the accepted numerical tolerance.
Model: point mass m = 1 kg on a massless arm of length L = 0.30 m, gearbox ratio 20.
"""

from __future__ import annotations

import math

import mujoco
import numpy as np
import pytest

from motionproof.simulation.engine import apply_joint_geometry, apply_payload
from motionproof.simulation.tasks import PointToPoint, Reversal, StaticHold
from tests.conftest import ARM_LENGTH, ARM_MASS

G = 9.81
GRAVITY_TORQUE = ARM_MASS * G * ARM_LENGTH  # N*m with the arm horizontal


def test_gravity_torque_of_model_matches_m_g_l(single_joint) -> None:  # type: ignore[no-untyped-def]
    model = single_joint().mj_model
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)
    assert abs(data.qfrc_bias[0]) == pytest.approx(GRAVITY_TORQUE, rel=1e-9)


def test_static_hold_motor_torque_equals_load_over_ratio(single_joint) -> None:  # type: ignore[no-untyped-def]
    """Holding a horizontal arm: motor torque = m g L / N (efficiency 1)."""
    m = single_joint()
    res = m.simulate(StaticHold(pose={"j": 0.0}, duration=1.0))
    assert res.valid
    assert res.trace["tau_motor"][-1] == pytest.approx(GRAVITY_TORQUE / 20.0, rel=2e-3)


def test_static_deflection_is_half_backlash_plus_windup(single_joint) -> None:  # type: ignore[no-untyped-def]
    """Under gravity the load rests on one flank: theta_cmd - theta_out = b/2 + tau/k."""
    backlash, stiffness = 0.010, 2000.0
    m = single_joint(backlash=backlash, stiffness=stiffness)
    res = m.simulate(StaticHold(pose={"j": 0.0}, duration=1.0))
    deflection = res.measurements[-1]["angle_error"]["j"]
    # the arm sags, so the gravity arm shortens by cos(deflection); negligible here
    expected = backlash / 2 + GRAVITY_TORQUE / stiffness
    assert deflection == pytest.approx(expected, rel=5e-3)
    assert res.metrics["ee_error_final"] == pytest.approx(ARM_LENGTH * expected, rel=1e-2)


@pytest.mark.parametrize("backlash", [0.0, 0.004, 0.012])
def test_reversal_lost_motion_equals_backlash_plus_friction_windup(
        single_joint, backlash: float) -> None:  # type: ignore[no-untyped-def]
    """No gravity, Coulomb output friction f.

    The dead band contributes exactly b. Friction traps up to f/k of spring windup on each
    approach, so b <= lost motion <= b + 2 f / k. A slow move ends with the output sliding
    against friction at a spring deflection of about f/k, where it sticks: the result lies
    near the upper bound. (Before stiction was modelled, MuJoCo's soft friction let this
    windup creep out and the result sat at b.)
    """
    friction, stiffness = 0.4, 2000.0
    m = single_joint(gravity=False, friction=friction, backlash=backlash, stiffness=stiffness)
    res = m.simulate(Reversal(target={"j": 0.3}, joint="j", excursion=0.2, move_time=0.8,
                              settle=0.6))
    assert res.valid
    lost = res.metrics["lost_motion"]
    windup = 2 * friction / stiffness
    assert backlash + 0.8 * windup <= lost <= backlash + windup + 2e-5
    # the motor itself returns to the commanded angle from both directions
    assert abs(res.measurements[-1]["motor"]["j"] - 0.3) < 1e-6


def test_gravity_preload_hides_backlash(single_joint) -> None:  # type: ignore[no-untyped-def]
    """With a one-sided gravity load the flanks never separate: no direction dependence."""
    m = single_joint(backlash=0.01)
    res = m.simulate(Reversal(target={"j": 0.2}, joint="j", excursion=0.15, move_time=0.8,
                              settle=0.6))
    assert res.metrics["lost_motion"] < 2e-4


def test_mid_stroke_torque_reflects_efficiency(single_joint) -> None:  # type: ignore[no-untyped-def]
    """No gravity, friction f, efficiency eta. At mid-stroke of a quintic move acceleration
    is zero, so the spring carries tau_c = f / eta and the motor supplies tau_c / N."""
    friction, eta = 0.5, 0.8
    m = single_joint(gravity=False, friction=friction, efficiency=eta)
    task = PointToPoint(start={"j": 0.0}, target={"j": 1.0}, duration=2.0, pre_settle=0.2)
    res = m.simulate(task)
    t = np.array(res.trace["t"])
    i = int(np.argmin(np.abs(t - 1.2)))  # 0.2 s pre-settle + half of the 2 s move
    assert res.trace["tau_motor"][i] == pytest.approx(friction / eta / 20.0, rel=0.03)


def test_torque_limit_saturates_and_fails_to_lift(single_joint) -> None:  # type: ignore[no-untyped-def]
    """A payload whose gravity torque exceeds peak torque * ratio cannot be held."""
    m = single_joint()
    available = 2.0 * 20.0  # peak torque * ratio
    payload = 1.5 * available / (G * ARM_LENGTH)
    res = m.simulate(StaticHold(pose={"j": 0.0}, duration=0.8, payload_mass=payload))
    assert res.metrics["torque_utilisation_peak"] == pytest.approx(1.0, abs=1e-6)
    assert res.metrics["saturated_fraction"] > 0.5
    assert res.metrics["angle_error_final"] > 0.1


def test_point_to_point_reaches_target(single_joint) -> None:  # type: ignore[no-untyped-def]
    m = single_joint()
    res = m.simulate(PointToPoint(start={"j": -0.5}, target={"j": 0.5}, duration=1.0))
    # only the elastic windup m g L cos(q) / k remains
    expected = GRAVITY_TORQUE * math.cos(0.5) / 2000.0
    assert res.measurements[-1]["angle_error"]["j"] == pytest.approx(expected, rel=0.02)


def test_simulation_is_bit_reproducible(single_joint) -> None:  # type: ignore[no-untyped-def]
    m = single_joint(backlash=0.006)
    task = Reversal(target={"j": 0.3}, joint="j")
    a, b = m.simulate(task), m.simulate(task)
    assert a.metrics == b.metrics
    assert a.trace["q_out"] == b.trace["q_out"]


def test_payload_adds_point_mass(single_joint) -> None:  # type: ignore[no-untyped-def]
    model = single_joint().mj_model
    import copy

    m2 = copy.copy(model)
    apply_payload(m2, 1, 0.5, np.array([ARM_LENGTH, 0.0, 0.0]))
    data = mujoco.MjData(m2)
    mujoco.mj_forward(m2, data)
    assert m2.body_mass[1] == pytest.approx(1.5)
    assert abs(data.qfrc_bias[0]) == pytest.approx(1.5 * G * ARM_LENGTH, rel=1e-9)


def test_axis_tilt_moves_end_effector_by_length_times_angle(single_joint) -> None:  # type: ignore[no-untyped-def]
    model = single_joint().mj_model
    import copy

    m2 = copy.copy(model)
    tilt = 2e-3
    apply_joint_geometry(m2, 0, 0.0, tilt, (0.0, 0.0, 0.0))
    d1, d2 = mujoco.MjData(model), mujoco.MjData(m2)
    mujoco.mj_kinematics(model, d1)
    mujoco.mj_kinematics(m2, d2)
    tip = np.array([ARM_LENGTH, 0, 0])
    p1 = d1.xpos[1] + d1.xmat[1].reshape(3, 3) @ tip
    p2 = d2.xpos[1] + d2.xmat[1].reshape(3, 3) @ tip
    assert np.linalg.norm(p2 - p1) == pytest.approx(ARM_LENGTH * tilt, rel=1e-5)


def test_joint_offset_translates_end_effector(single_joint) -> None:  # type: ignore[no-untyped-def]
    m = single_joint(gravity=False)
    res = m.engine.run(_offset_variant(m, (0.0, 0.0, -1e-4)), StaticHold(pose={"j": 0.0}))
    assert res.metrics["ee_error_final"] == pytest.approx(1e-4, rel=1e-3)


def _offset_variant(m, offset):  # type: ignore[no-untyped-def]
    v = m.nominal_variant()
    v.joints["j"].offset = offset
    return v
