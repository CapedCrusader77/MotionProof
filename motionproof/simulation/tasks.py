"""Reusable task definitions and the commanded motion plan they produce."""

from __future__ import annotations

import bisect
from dataclasses import dataclass, field
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

Pose = dict[str, float]


class _Task(BaseModel):
    model_config = ConfigDict(extra="forbid")
    payload_mass: float = Field(default=0.0, ge=0, description="kg at the end effector")
    pre_settle: float = Field(default=0.25, ge=0, description="s held at the start pose")


class PointToPoint(_Task):
    type: Literal["point_to_point"] = "point_to_point"
    start: Pose
    target: Pose
    duration: float = Field(gt=0)
    settle: float = Field(default=0.4, gt=0)


class Reversal(_Task):
    """Approach the same target from below and from above; the difference is lost motion."""

    type: Literal["reversal"] = "reversal"
    target: Pose
    joint: str
    excursion: float = Field(default=0.2, gt=0, description="rad either side of the target")
    move_time: float = Field(default=0.6, gt=0)
    settle: float = Field(default=0.4, gt=0)


class StaticHold(_Task):
    type: Literal["static_hold"] = "static_hold"
    pose: Pose
    duration: float = Field(default=0.6, gt=0)


class RepeatCycles(_Task):
    type: Literal["repeat_cycles"] = "repeat_cycles"
    a: Pose
    b: Pose
    cycles: int = Field(default=3, ge=1, le=50)
    move_time: float = Field(default=0.8, gt=0)
    settle: float = Field(default=0.3, gt=0)


class WorkspaceSweep(_Task):
    type: Literal["workspace_sweep"] = "workspace_sweep"
    poses: list[Pose] = Field(min_length=2)
    move_time: float = Field(default=0.8, gt=0)
    settle: float = Field(default=0.3, gt=0)


Task = Annotated[
    PointToPoint | Reversal | StaticHold | RepeatCycles | WorkspaceSweep,
    Field(discriminator="type"),
]


@dataclass
class Plan:
    """Piecewise rest-to-rest quintic motion through ``knots`` with labelled measurements."""

    joints: list[str]
    times: list[float] = field(default_factory=list)
    poses: list[list[float]] = field(default_factory=list)
    measurements: list[tuple[float, str]] = field(default_factory=list)

    def add(self, dt: float, pose: Pose, label: str | None = None) -> None:
        t = (self.times[-1] if self.times else 0.0) + (dt if self.times else 0.0)
        base = dict(zip(self.joints, self.poses[-1], strict=True)) if self.poses else {}
        full = {**dict.fromkeys(self.joints, 0.0), **base, **pose}
        unknown = set(pose) - set(self.joints)
        if unknown:
            raise KeyError(f"task refers to joints that are not driven: {sorted(unknown)}")
        self.times.append(t)
        self.poses.append([full[j] for j in self.joints])
        if label:
            self.measurements.append((t, label))

    @property
    def duration(self) -> float:
        return self.times[-1]

    def command(self, t: float) -> tuple[list[float], list[float]]:
        """Commanded positions and velocities at time ``t``."""
        times = self.times
        if t <= times[0]:
            return self.poses[0], [0.0] * len(self.joints)
        if t >= times[-1]:
            return self.poses[-1], [0.0] * len(self.joints)
        i = bisect.bisect_right(times, t) - 1
        t0, t1 = times[i], times[i + 1]
        s = (t - t0) / (t1 - t0)
        blend = s**3 * (10 - 15 * s + 6 * s**2)
        rate = 30 * s**2 * (1 - s) ** 2 / (t1 - t0)
        q0, q1 = self.poses[i], self.poses[i + 1]
        q = [a + (b - a) * blend for a, b in zip(q0, q1, strict=True)]
        qd = [(b - a) * rate for a, b in zip(q0, q1, strict=True)]
        return q, qd


def build_plan(task: _Task, joints: list[str]) -> Plan:
    plan = Plan(joints)
    if isinstance(task, PointToPoint):
        plan.add(0, task.start)
        plan.add(task.pre_settle, task.start)
        plan.add(task.duration, task.target)
        plan.add(task.settle, task.target, "target")
    elif isinstance(task, Reversal):
        if task.joint not in joints:
            raise KeyError(f"reversal joint {task.joint!r} is not a driven joint")
        centre = task.target.get(task.joint, 0.0)
        below = {**task.target, task.joint: centre - task.excursion}
        above = {**task.target, task.joint: centre + task.excursion}
        plan.add(0, below)
        plan.add(task.pre_settle, below)
        plan.add(task.move_time, task.target)
        plan.add(task.settle, task.target, "approach_up")
        plan.add(task.move_time, above)
        plan.add(task.settle, above)
        plan.add(task.move_time, task.target)
        plan.add(task.settle, task.target, "approach_down")
    elif isinstance(task, StaticHold):
        plan.add(0, task.pose)
        plan.add(task.pre_settle + task.duration, task.pose, "hold")
    elif isinstance(task, RepeatCycles):
        plan.add(0, task.a)
        plan.add(task.pre_settle, task.a)
        for _ in range(task.cycles):
            plan.add(task.move_time, task.b)
            plan.add(task.settle, task.b, "b")
            plan.add(task.move_time, task.a)
            plan.add(task.settle, task.a, "a")
    elif isinstance(task, WorkspaceSweep):
        plan.add(0, task.poses[0])
        plan.add(task.pre_settle, task.poses[0])
        for i, pose in enumerate(task.poses[1:], start=1):
            plan.add(task.move_time, pose)
            plan.add(task.settle, pose, f"pose_{i}")
    else:
        raise TypeError(f"unsupported task {type(task).__name__}")
    return plan
