"""Motor torque availability."""

from __future__ import annotations

from motionproof.core.schema import Motor


def available_torque(motor: Motor, speed: float, scale: float = 1.0) -> float:
    """Torque (N*m) the motor can deliver at shaft ``speed`` (rad/s).

    Uses the user-supplied torque-speed curve with linear interpolation; without a curve the
    peak torque is assumed available up to ``max_speed``. Beyond the last point torque is zero.
    """
    w = abs(speed)
    curve = motor.torque_speed
    if not curve:
        return (motor.peak_torque if w <= motor.max_speed else 0.0) * scale
    if w <= curve[0][0]:
        return curve[0][1] * scale
    for (w0, t0), (w1, t1) in zip(curve, curve[1:], strict=False):
        if w <= w1:
            return (t0 + (t1 - t0) * (w - w0) / (w1 - w0)) * scale
    return 0.0
