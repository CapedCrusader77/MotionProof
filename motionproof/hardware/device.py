"""Hardware-in-the-loop: device protocol, device abstraction, safety monitor, test sessions.

No physical hardware has been tested with this code. The simulated device exercises the whole
software path (protocol, validation, safety aborts, logging, comparison, calibration) and every
session it produces is labelled ``SIMULATED DEVICE``.

Safety: the checks here are software checks. They do not replace a wired emergency-stop circuit,
mechanical travel stops or an electrical assessment of the rig. Nothing moves without
``confirm_actuation=True`` passed explicitly by the caller for that one run.

Protocol (newline-delimited JSON, UTF-8), documented in docs/device-protocol.md:

    device -> host  {"type":"hello","device":str,"firmware":str,"sensors":{...}}
                    {"type":"telemetry","seq":int,"t_us":int,"command_rad":float,
                     "input_angle_rad":float,"output_angle_rad":float,"input_counts":int,
                     "output_counts":int,"torque_nm":float|null,"current_a":float|null,
                     "temp_c":float|null,"flags":int}
    host -> device  {"cmd":"arm"} {"cmd":"move",...} {"cmd":"stop"} {"cmd":"ping"}

Flags: bit 0 emergency stop asserted, bit 1 limit switch, bit 2 driver fault, bit 3 sensor fault.
"""

from __future__ import annotations

import csv
import dataclasses
import json
import math
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
from pydantic import BaseModel, ConfigDict, Field

from motionproof.model import MechanicalModel
from motionproof.simulation.tasks import RepeatCycles, Reversal

FLAG_ESTOP, FLAG_LIMIT, FLAG_DRIVER, FLAG_SENSOR = 1, 2, 4, 8
REQUIRED = ("seq", "t_us", "command_rad", "input_angle_rad", "output_angle_rad")
SIMULATED = "SIMULATED DEVICE"


class HardwareError(RuntimeError):
    pass


class ProtocolError(ValueError):
    pass


def with_parameters(jv: Any, values: dict[str, float]) -> Any:
    """Copy of a JointVariant with some float parameters replaced."""
    out = dataclasses.replace(jv)
    for k, v in values.items():
        if not isinstance(getattr(out, k, None), float | int):
            raise KeyError(f"{k!r} is not a numeric joint parameter")
        setattr(out, k, float(v))
    return out


def parse_line(line: str) -> dict[str, Any]:
    """Validate one device message. Raises ``ProtocolError`` with the reason."""
    try:
        msg = json.loads(line)
    except json.JSONDecodeError as exc:
        raise ProtocolError(f"not valid JSON: {exc.msg}") from None
    if not isinstance(msg, dict) or "type" not in msg:
        raise ProtocolError("message is not an object with a 'type'")
    if msg["type"] == "telemetry":
        for key in REQUIRED:
            if key not in msg:
                raise ProtocolError(f"telemetry is missing '{key}'")
            if not isinstance(msg[key], int | float) or isinstance(msg[key], bool) \
                    or not math.isfinite(msg[key]):
                raise ProtocolError(f"telemetry field '{key}' is not a finite number")
        for key in ("torque_nm", "current_a", "temp_c"):
            v = msg.get(key)
            if v is not None and (not isinstance(v, int | float) or not math.isfinite(v)):
                raise ProtocolError(f"telemetry field '{key}' is not a finite number or null")
        msg.setdefault("flags", 0)
    elif msg["type"] == "hello":
        if not msg.get("device") or not msg.get("firmware"):
            raise ProtocolError("hello needs 'device' and 'firmware'")
    elif msg["type"] != "status":
        raise ProtocolError(f"unknown message type {msg['type']!r}")
    return msg


class Device(ABC):
    """A test rig. Implementations yield raw protocol lines."""

    kind: str = "abstract"
    #: True when ``read() -> None`` means the test is over (simulated device). A physical
    #: device signals the end with a ``status`` message; ``None`` is only a read timeout.
    end_on_silence: bool = False

    @abstractmethod
    def open(self) -> dict[str, Any]: ...

    @abstractmethod
    def send(self, command: dict[str, Any]) -> None: ...

    @abstractmethod
    def read(self) -> str | None:
        """Next line, or ``None`` when the device has nothing more to send."""

    @abstractmethod
    def close(self) -> None: ...


class SafetyLimits(BaseModel):
    model_config = ConfigDict(extra="forbid")
    travel_min: float = Field(description="rad, at the output")
    travel_max: float
    max_speed: float = Field(gt=0, description="rad/s at the output")
    max_duration: float = Field(gt=0, le=3600, description="s")
    max_torque: float | None = Field(default=None, gt=0)
    max_temperature: float | None = None
    watchdog_ms: float = Field(default=200.0, gt=0)
    max_lost_packets: int = Field(default=20, ge=0)


class HardwareTest(BaseModel):
    """A low-risk reversal or cycling test at one joint."""

    model_config = ConfigDict(extra="forbid")
    joint: str
    kind: str = Field(default="reversal", pattern="^(reversal|cycles)$")
    centre: float = Field(description="rad")
    excursion: float = Field(gt=0, description="rad either side (reversal) or A to B (cycles)")
    move_time: float = Field(gt=0)
    settle: float = Field(default=0.4, gt=0)
    cycles: int = Field(default=1, ge=1, le=100)
    load_mass: float = Field(default=0.0, ge=0)

    def task(self) -> Reversal | RepeatCycles:
        if self.kind == "reversal":
            return Reversal(target={self.joint: self.centre}, joint=self.joint,
                            excursion=self.excursion, move_time=self.move_time,
                            settle=self.settle, payload_mass=self.load_mass)
        return RepeatCycles(a={self.joint: self.centre},
                            b={self.joint: self.centre + self.excursion}, cycles=self.cycles,
                            move_time=self.move_time, settle=self.settle,
                            payload_mass=self.load_mass)

    @property
    def peak_speed(self) -> float:
        return 1.875 * self.excursion / self.move_time  # peak of a rest-to-rest quintic


class SimulatedDevice(Device):
    """A software rig driven by the MotionProof engine with its own 'true' parameters.

    ``truth`` overrides joint parameters (for example the real backlash of the rig) so that
    calibration has something to find. ``faults`` injects protocol and sensor problems.
    """

    kind = "simulated"
    end_on_silence = True

    def __init__(self, model: MechanicalModel, truth: dict[str, float] | None = None,
                 sample_hz: float = 200.0, encoder_counts: int = 4096, noise: float = 0.0,
                 seed: int = 0, faults: dict[str, Any] | None = None, name: str = "SIM-001"):
        self.model, self.truth = model, truth or {}
        self.sample_hz, self.counts, self.noise = sample_hz, encoder_counts, noise
        self.rng = np.random.default_rng(seed)
        self.faults = faults or {}
        self.name = name
        self._lines: list[str] = []
        self._armed = False
        drives = model.spec.drives
        self.ratio = float(next(iter(drives.values())).gearbox.ratio) if drives else 1.0
        self.sent: list[dict[str, Any]] = []

    def open(self) -> dict[str, Any]:
        hello = {"type": "hello", "device": self.name, "firmware": "simulated-1",
                 "nominal_ratio": self.ratio,
                 "sensors": {"input_encoder_counts": self.counts,
                             "output_encoder_counts": self.counts, "torque": False,
                             "current": False, "temperature": bool(
                                 self.faults.get("temperature_c"))},
                 "simulated": True}
        return hello

    def send(self, command: dict[str, Any]) -> None:
        self.sent.append(command)
        if command.get("cmd") == "arm":
            self._armed = True
        elif command.get("cmd") == "stop":
            self._lines = []
        elif command.get("cmd") == "move":
            if not self._armed:
                raise HardwareError("device is not armed")
            self._generate(HardwareTest.model_validate(command["test"]))

    def _generate(self, test: HardwareTest) -> None:
        variant = self.model.nominal_variant()
        jv = variant.joints[test.joint]
        variant.joints[test.joint] = with_parameters(jv, self.truth)
        res = self.model.engine.run(variant, test.task(), keep_trace=True, trace_points=100_000)
        if not res.valid:
            raise HardwareError(f"simulated rig failed: {res.message}")
        t = np.asarray(res.trace["t"])
        ts = np.arange(0.0, t[-1], 1.0 / self.sample_hz)
        q = 2 * math.pi / self.counts
        sig = {k: np.interp(ts, t, res.trace[k]) for k in ("q_cmd", "q_motor", "q_out")}
        drop = set(self.faults.get("drop", []))
        garble = set(self.faults.get("garble", []))
        sensor_loss = self.faults.get("sensor_loss_at")
        estop = self.faults.get("estop_at")
        self._lines = []
        for i, time_s in enumerate(ts):
            if i in drop:
                continue
            if i in garble:
                self._lines.append('{"type":"telemetry","seq":' + str(i) + ',"t_us":')
                continue
            out = sig["q_out"][i] + self.noise * self.rng.normal()
            msg: dict[str, Any] = {
                "type": "telemetry", "seq": i, "t_us": int(round(time_s * 1e6)),
                "command_rad": float(sig["q_cmd"][i]),
                "input_angle_rad": float(round(sig["q_motor"][i] / q) * q),
                "output_angle_rad": float(round(out / q) * q),
                "input_counts": int(round(sig["q_motor"][i] * self.ratio / q)),
                "output_counts": int(round(out / q)),
                "torque_nm": None, "current_a": None,
                "temp_c": self.faults.get("temperature_c"), "flags": 0}
            if sensor_loss is not None and i >= sensor_loss:
                msg["output_angle_rad"] = float("nan")
                self._lines.append(json.dumps(msg).replace("NaN", "null"))
                continue
            if estop is not None and i >= estop:
                msg["flags"] = FLAG_ESTOP
            self._lines.append(json.dumps(msg))
        if estop is None and sensor_loss is None:
            self._lines.append(json.dumps({"type": "status", "state": "done"}))
        self._lines.reverse()

    def read(self) -> str | None:
        return self._lines.pop() if self._lines else None

    def close(self) -> None:
        self._lines = []
        self._armed = False


class SerialDevice(Device):
    """USB serial / UART rig. Needs the optional ``pyserial`` package; untested on hardware."""

    kind = "serial"

    KEEPALIVE_S = 0.2

    def __init__(self, port: str, baud: int = 115200, timeout: float = 0.05,
                 serial_module: Any = None):
        if serial_module is None:
            try:
                import serial

                serial_module = serial
            except ImportError:
                raise HardwareError(
                    "serial devices need the 'pyserial' package, which is not installed. "
                    "Install it with 'uv sync --extra hardware', or use the simulated "
                    "device.") from None
        self._serial_mod = serial_module
        self.port, self.baud, self.timeout = port, baud, timeout
        self._ser: Any = None
        self._last_ping = 0.0

    def open(self) -> dict[str, Any]:
        self._ser = self._serial_mod.Serial(self.port, self.baud, timeout=self.timeout)
        self.send({"cmd": "ping"})
        for _ in range(20):
            line = self.read()
            if line:
                try:
                    msg = parse_line(line)
                except ProtocolError:
                    continue
                if msg["type"] == "hello":
                    return msg
        raise HardwareError(f"no hello message from the device on {self.port}")

    def send(self, command: dict[str, Any]) -> None:
        self._ser.write((json.dumps(command) + "\n").encode())

    def read(self) -> str | None:
        import time

        now = time.monotonic()
        if now - self._last_ping >= self.KEEPALIVE_S:  # firmware stops if pings stop
            self.send({"cmd": "ping"})
            self._last_ping = now
        raw = self._ser.readline()
        return raw.decode("utf-8", errors="replace").strip() if raw else None

    def close(self) -> None:
        if self._ser is not None:
            try:
                self.send({"cmd": "stop"})
            finally:
                self._ser.close()


def list_devices() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = [{"id": "simulated", "kind": "simulated",
                                  "description": "software rig driven by the engine "
                                                 "(no hardware)", "available": True}]
    try:
        from serial.tools import list_ports

        for p in list_ports.comports():
            out.append({"id": p.device, "kind": "serial", "description": p.description,
                        "available": True})
    except ImportError:
        out.append({"id": "serial", "kind": "serial", "available": False,
                    "description": "pyserial is not installed: serial devices unavailable"})
    return out


def preflight(test: HardwareTest, limits: SafetyLimits, hello: dict[str, Any]
              ) -> list[dict[str, Any]]:
    """Checks that must all pass before a test may start."""
    task = test.task()
    lo = test.centre - (test.excursion if test.kind == "reversal" else 0.0)
    hi = test.centre + test.excursion
    duration = test.settle * 2 + test.move_time * (3 if test.kind == "reversal"
                                                   else 2 * test.cycles) + task.pre_settle
    checks = [
        {"check": "travel within software limits",
         "ok": limits.travel_min <= lo and hi <= limits.travel_max,
         "detail": f"commanded {lo:.4f} .. {hi:.4f} rad, limits {limits.travel_min:.4f} .. "
                   f"{limits.travel_max:.4f} rad"},
        {"check": "peak speed within limit", "ok": test.peak_speed <= limits.max_speed,
         "detail": f"{test.peak_speed:.4f} rad/s, limit {limits.max_speed:.4f} rad/s"},
        {"check": "duration within limit", "ok": duration <= limits.max_duration,
         "detail": f"about {duration:.2f} s, limit {limits.max_duration:.2f} s"},
        {"check": "device identified", "ok": bool(hello.get("device")),
         "detail": f"{hello.get('device')} firmware {hello.get('firmware')}"},
        {"check": "torque limit has a sensor",
         "ok": limits.max_torque is None or bool(hello.get("sensors", {}).get("torque")),
         "detail": "a torque limit is set" if limits.max_torque is not None
         else "no torque limit configured"},
    ]
    return checks


@dataclass
class Session:
    source: str
    device: dict[str, Any]
    test: dict[str, Any]
    limits: dict[str, Any]
    status: str = "not started"
    abort_reason: str | None = None
    samples: list[dict[str, Any]] = field(default_factory=list)
    malformed: int = 0
    lost_packets: int = 0
    invalid_readings: int = 0
    errors: list[str] = field(default_factory=list)

    def arrays(self) -> dict[str, np.ndarray]:
        keys = ("t_us", "command_rad", "input_angle_rad", "output_angle_rad")
        return {k: np.array([s[k] for s in self.samples], dtype=float) for k in keys}

    def summary(self) -> dict[str, Any]:
        return {"source": self.source, "device": self.device, "status": self.status,
                "abort_reason": self.abort_reason, "samples": len(self.samples),
                "malformed_messages": self.malformed, "lost_packets": self.lost_packets,
                "invalid_readings": self.invalid_readings, "errors": self.errors[:20],
                "test": self.test, "limits": self.limits}

    def write_csv(self, path: str | Path) -> Path:
        p = Path(path)
        with p.open("w", newline="", encoding="utf-8") as f:
            f.write(f"# source: {self.source}; device {self.device.get('device')} firmware "
                    f"{self.device.get('firmware')}; status {self.status}\n")
            w = csv.writer(f)
            w.writerow(["time_s", "command_rad", "motor_angle_rad", "output_angle_rad",
                        "input_counts", "output_counts", "torque_nm", "temp_c", "flags"])
            for s in self.samples:
                w.writerow([f"{s['t_us'] / 1e6:.6f}", s["command_rad"], s["input_angle_rad"],
                            s["output_angle_rad"], s.get("input_counts", ""),
                            s.get("output_counts", ""), s.get("torque_nm") or "",
                            s.get("temp_c") or "", s["flags"]])
        return p


def run_test(device: Device, test: HardwareTest, limits: SafetyLimits,
             confirm_actuation: bool = False) -> Session:
    """Run one test. Refuses to move anything unless ``confirm_actuation`` is True."""
    if not confirm_actuation:
        raise HardwareError("actuation was not confirmed: pass confirm_actuation=True for this "
                            "run after checking the rig. Nothing was sent to the device.")
    hello = device.open()
    simulated = bool(hello.get("simulated")) or device.kind == "simulated"
    session = Session(SIMULATED if simulated else "hardware", hello, test.model_dump(),
                      limits.model_dump())
    failed = [c for c in preflight(test, limits, hello) if not c["ok"]]
    if failed:
        session.status = "refused"
        session.abort_reason = "preflight failed: " + "; ".join(
            f"{c['check']} ({c['detail']})" for c in failed)
        device.close()
        return session

    def abort(reason: str) -> None:
        device.send({"cmd": "stop"})
        session.status, session.abort_reason = "aborted", reason

    started_wall = __import__("time").monotonic()
    device.send({"cmd": "arm"})
    device.send({"cmd": "move", "test": test.model_dump()})
    session.status = "running"
    import time as _time

    last_seq = last_t = None
    prev: tuple[float, float] | None = None
    last_rx = _time.monotonic()
    try:
        while session.status == "running":
            line = device.read()
            if line is None:
                if device.end_on_silence:
                    break
                if (_time.monotonic() - last_rx) * 1000.0 > limits.watchdog_ms:
                    abort(f"watchdog: no data for more than {limits.watchdog_ms:.0f} ms")
                    break
                if _time.monotonic() - started_wall > limits.max_duration + 5.0:
                    abort("duration limit reached without an end-of-test message")
                    break
                continue
            last_rx = _time.monotonic()
            try:
                msg = parse_line(line)
            except ProtocolError as exc:
                session.malformed += 1
                session.errors.append(str(exc))
                if "finite number" in str(exc):
                    session.invalid_readings += 1
                    if session.invalid_readings >= 3:
                        abort("sensor loss: three invalid readings")
                continue
            if msg["type"] == "status":
                state = msg.get("state")
                if state == "done":
                    break
                if state in ("stopped", "fault"):
                    abort(f"device reported {state}: {msg.get('reason', 'no reason given')}")
                    break
                continue
            if msg["type"] != "telemetry":
                continue
            t = msg["t_us"] / 1e6
            if last_t is not None and (t - last_t) * 1000.0 > limits.watchdog_ms:
                abort(f"watchdog: {1000 * (t - last_t):.0f} ms without telemetry")
                break
            if last_seq is not None and msg["seq"] != last_seq + 1:
                session.lost_packets += max(msg["seq"] - last_seq - 1, 0)
                if session.lost_packets > limits.max_lost_packets:
                    abort(f"communication: {session.lost_packets} packets lost")
                    break
            last_seq, last_t = msg["seq"], t
            session.samples.append(msg)
            out = msg["output_angle_rad"]
            if msg["flags"] & FLAG_ESTOP:
                abort("emergency stop asserted by the device")
            elif msg["flags"] & (FLAG_LIMIT | FLAG_DRIVER | FLAG_SENSOR):
                abort(f"device fault flags {msg['flags']}")
            elif not limits.travel_min <= out <= limits.travel_max:
                abort(f"travel limit: output at {out:.4f} rad")
            elif prev is not None and t > prev[0] and \
                    abs(out - prev[1]) / (t - prev[0]) > 3.0 * limits.max_speed:
                abort("speed limit: output moved faster than three times the limit")
            elif limits.max_torque is not None and msg.get("torque_nm") is not None \
                    and abs(msg["torque_nm"]) > limits.max_torque:
                abort(f"torque limit: {msg['torque_nm']:.3f} N*m")
            elif limits.max_temperature is not None and msg.get("temp_c") is not None \
                    and msg["temp_c"] > limits.max_temperature:
                abort(f"temperature limit: {msg['temp_c']:.1f} C")
            elif t > limits.max_duration:
                abort("duration limit reached")
            prev = (t, out)
    finally:
        device.close()
    if session.status == "running":
        session.status = "completed"
    return session


def compare_with_simulation(session: Session, model: MechanicalModel,
                            values: dict[str, float] | None = None) -> dict[str, Any]:
    """Overlay the session on a simulation of the same test with the model's parameters."""
    test = HardwareTest.model_validate(session.test)
    res = model.engine.run(model.variant(values or {}), test.task(), keep_trace=True,
                           trace_points=20_000)
    if not res.valid:
        raise HardwareError(f"the comparison simulation is invalid: {res.message}")
    a = session.arrays()
    if len(a["t_us"]) < 10:
        raise HardwareError("the session holds fewer than 10 samples")
    t = a["t_us"] / 1e6
    out: dict[str, Any] = {"source": session.source, "samples": int(len(t)), "signals": {}}
    for name, key, trace in (("output_angle", "output_angle_rad", "q_out"),
                             ("input_angle", "input_angle_rad", "q_motor")):
        pred = np.interp(t, res.trace["t"], res.trace[trace])
        r = a[key] - pred
        out["signals"][name] = {"rmse": float(np.sqrt(np.mean(r**2))),
                                "mae": float(np.mean(np.abs(r))),
                                "max_abs": float(np.abs(r).max()),
                                "mean": float(r.mean())}
        step = max(1, len(t) // 400)
        out["signals"][name]["series"] = {"t": t[::step].tolist(),
                                          "measured": a[key][::step].tolist(),
                                          "predicted": pred[::step].tolist(),
                                          "residual": r[::step].tolist()}
    out["predicted_lost_motion"] = res.metrics.get("lost_motion")
    if test.kind == "reversal":
        task = test.task()
        t_up = task.pre_settle + test.move_time + test.settle
        t_down = t_up + 2 * test.move_time + 2 * test.settle
        w = 0.5 * test.settle
        up = a["output_angle_rad"][(t > t_up - w) & (t <= t_up)]
        down = a["output_angle_rad"][(t > t_down - w) & (t <= t_down)]
        if len(up) and len(down):
            out["measured_lost_motion"] = float(abs(down.mean() - up.mean()))
    out["statement"] = ("Comparison of a SIMULATED DEVICE with the model: this checks the "
                        "software path, not the physics." if session.source == SIMULATED else
                        "Comparison of hardware measurements with the model prediction.")
    return out
