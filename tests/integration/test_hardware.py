"""Hardware-in-the-loop software path. Every session here is a SIMULATED DEVICE."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from motionproof.calibration.fit import CalibrationConfig, calibrate, read_csv
from motionproof.hardware.device import (
    SIMULATED,
    HardwareError,
    HardwareTest,
    ProtocolError,
    SafetyLimits,
    SerialDevice,
    SimulatedDevice,
    compare_with_simulation,
    list_devices,
    parse_line,
    run_test,
)

TEST = HardwareTest(joint="j", kind="reversal", centre=0.3, excursion=0.2, move_time=0.8,
                    settle=0.5)
LIMITS = SafetyLimits(travel_min=-0.5, travel_max=1.0, max_speed=2.0, max_duration=30.0)


def _model(single_joint):  # type: ignore[no-untyped-def]
    return single_joint(gravity=False, friction=0.4)


def test_actuation_requires_explicit_confirmation(single_joint) -> None:  # type: ignore[no-untyped-def]
    dev = SimulatedDevice(_model(single_joint))
    with pytest.raises(HardwareError, match="not confirmed"):
        run_test(dev, TEST, LIMITS)
    assert dev.sent == []  # nothing was sent


def test_simulated_session_is_labelled_and_measures_lost_motion(
        single_joint, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    """Rig truth: backlash 8 mrad. Encoder 4096 counts (1.53 mrad). Lost motion recovered
    within one count."""
    model = _model(single_joint)
    dev = SimulatedDevice(model, truth={"backlash": 0.008}, sample_hz=200.0)
    s = run_test(dev, TEST, LIMITS, confirm_actuation=True)
    assert s.status == "completed" and s.source == SIMULATED
    assert s.lost_packets == 0 and s.malformed == 0 and len(s.samples) > 500
    cmp_ = compare_with_simulation(s, model, {"backlash_tol": 0.008})
    assert cmp_["measured_lost_motion"] == pytest.approx(0.008, abs=2 * np.pi / 4096)
    assert cmp_["signals"]["output_angle"]["rmse"] < 2 * np.pi / 4096
    assert "SIMULATED DEVICE" in cmp_["statement"]
    path = s.write_csv(tmp_path / "session.csv")
    assert path.read_text(encoding="utf-8").startswith("# source: SIMULATED DEVICE")


def test_session_data_calibrate_on_one_run_validate_on_another(
        single_joint, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    model = _model(single_joint)
    files = []
    for seed in (1, 2):
        dev = SimulatedDevice(model, truth={"backlash": 0.006}, sample_hz=250.0,
                              encoder_counts=65536, noise=2e-5, seed=seed)
        s = run_test(dev, TEST, LIMITS, confirm_actuation=True)
        files.append(s.write_csv(tmp_path / f"run{seed}.csv"))
    cfg = CalibrationConfig.model_validate({
        "task": TEST.task().model_dump(), "time_column": "time_s", "time_unit": "s",
        "signals": {"output_angle": {"column": "output_angle_rad", "unit": "rad"}},
        "parameters": [{"joint": "j", "name": "backlash", "lower": 0.0, "upper": 0.02}]})
    lines = files[0].read_text(encoding="utf-8").splitlines()
    for f in files:
        f.write_text("\n".join(x for x in f.read_text(encoding="utf-8").splitlines()
                               if not x.startswith("#")), encoding="utf-8")
    assert lines[0].startswith("# source")
    res = calibrate(model, cfg, read_csv(files[0], cfg), read_csv(files[1], cfg))
    assert res["parameters"][0]["estimate"] == pytest.approx(0.006, abs=2e-4)
    assert res["holdout"]["split"] == "separate_recording"


@pytest.mark.parametrize(("faults", "status", "reason"), [
    ({"estop_at": 50}, "aborted", "emergency stop"),
    ({"sensor_loss_at": 40}, "aborted", "sensor loss"),
    ({"drop": list(range(30, 90))}, "aborted", "watchdog"),  # 300 ms gap at 200 Hz
    ({"drop": list(range(30, 90, 2))}, "aborted", "packets lost"),
])
def test_faults_abort_the_test(single_joint, faults, status, reason) -> None:  # type: ignore[no-untyped-def]
    dev = SimulatedDevice(_model(single_joint), faults=faults)
    s = run_test(dev, TEST, LIMITS, confirm_actuation=True)
    assert s.status == status and reason in s.abort_reason
    assert dev.sent[-1] == {"cmd": "stop"}


def test_lost_and_malformed_packets_are_counted(single_joint) -> None:  # type: ignore[no-untyped-def]
    dev = SimulatedDevice(_model(single_joint), faults={"drop": [10, 20, 30],
                                                        "garble": [40, 41]})
    s = run_test(dev, TEST, LIMITS, confirm_actuation=True)
    assert s.status == "completed"
    assert s.lost_packets == 5 and s.malformed == 2  # garbled lines also leave seq gaps
    tight = LIMITS.model_copy(update={"max_lost_packets": 2})
    dev = SimulatedDevice(_model(single_joint), faults={"drop": [10, 20, 30]})
    s = run_test(dev, TEST, tight, confirm_actuation=True)
    assert s.status == "aborted" and "packets lost" in s.abort_reason


def test_preflight_refuses_unsafe_tests(single_joint) -> None:  # type: ignore[no-untyped-def]
    dev = SimulatedDevice(_model(single_joint))
    fast = TEST.model_copy(update={"move_time": 0.1})
    s = run_test(dev, fast, LIMITS, confirm_actuation=True)
    assert s.status == "refused" and "peak speed" in s.abort_reason
    far = TEST.model_copy(update={"centre": 0.95})
    s = run_test(SimulatedDevice(_model(single_joint)), far, LIMITS, confirm_actuation=True)
    assert s.status == "refused" and "travel" in s.abort_reason
    torque = LIMITS.model_copy(update={"max_torque": 1.0})
    s = run_test(SimulatedDevice(_model(single_joint)), TEST, torque, confirm_actuation=True)
    assert s.status == "refused" and "torque limit has a sensor" in s.abort_reason


def test_temperature_limit(single_joint) -> None:  # type: ignore[no-untyped-def]
    hot = SimulatedDevice(_model(single_joint), faults={"temperature_c": 85.0})
    s = run_test(hot, TEST, LIMITS.model_copy(update={"max_temperature": 70.0}),
                 confirm_actuation=True)
    assert s.status == "aborted" and "temperature" in s.abort_reason


def test_protocol_validation() -> None:
    ok = parse_line(json.dumps({"type": "telemetry", "seq": 1, "t_us": 5000,
                                "command_rad": 0.1, "input_angle_rad": 3.3,
                                "output_angle_rad": 0.1}))
    assert ok["flags"] == 0
    for bad, why in [("{nope", "not valid JSON"), ("[1,2]", "not an object"),
                     (json.dumps({"type": "telemetry", "seq": 1}), "missing"),
                     (json.dumps({"type": "telemetry", "seq": 1, "t_us": 1,
                                  "command_rad": 0, "input_angle_rad": 0,
                                  "output_angle_rad": None}), "finite"),
                     (json.dumps({"type": "telemetry", "seq": True, "t_us": 1,
                                  "command_rad": 0, "input_angle_rad": 0,
                                  "output_angle_rad": 0}), "finite"),
                     (json.dumps({"type": "hello"}), "device"),
                     (json.dumps({"type": "launch"}), "unknown message type")]:
        with pytest.raises(ProtocolError, match=why):
            parse_line(bad)


def test_device_listing_and_serial_without_pyserial() -> None:
    devices = list_devices()
    assert devices[0]["id"] == "simulated"
    try:
        import serial  # type: ignore[import-not-found]  # noqa: F401
    except ImportError:
        assert any(d["kind"] == "serial" and not d["available"] for d in devices)
        with pytest.raises(HardwareError, match="pyserial"):
            SerialDevice("COM3")


# ---- serial path with a fake port that behaves like the firmware ---------------------------

class _FakePort:
    """Emulates motionproof_rig.ino on the wire: hello on ping, telemetry after move, a final
    status message, and silence (empty reads) in between."""

    def __init__(self, sim: SimulatedDevice, stop_after: int | None = None,
                 status: dict | None = None):
        self.sim, self.stop_after, self.final = sim, stop_after, status
        self.out: list[bytes] = []
        self.written: list[dict] = []
        self.sent = 0

    def write(self, data: bytes) -> None:
        msg = json.loads(data.decode())
        self.written.append(msg)
        if msg["cmd"] == "ping" and not self.sim._lines:
            self.out.append((json.dumps(self.sim.open() | {"simulated": False}) + "\n").encode())
        elif msg["cmd"] == "arm":
            self.sim.send(msg)
        elif msg["cmd"] == "move":
            self.sim.send(msg)
            lines = []
            while (line := self.sim.read()) is not None:
                lines.append(line)
            if self.final is not None:
                lines = [x for x in lines if '"status"' not in x] + [json.dumps(self.final)]
            for i, line in enumerate(lines):
                if self.stop_after is not None and i >= self.stop_after:
                    break
                self.out.append((line + "\n").encode())
                if i % 50 == 0:
                    self.out.append(b"")  # a read timeout now and then

    def readline(self) -> bytes:
        return self.out.pop(0) if self.out else b""

    def close(self) -> None:
        pass


class _FakeSerialModule:
    def __init__(self, port: _FakePort):
        self.port = port

    def Serial(self, *_a, **_k):  # noqa: N802
        return self.port


def test_serial_device_completes_on_status_done(single_joint) -> None:  # type: ignore[no-untyped-def]
    model = _model(single_joint)
    port = _FakePort(SimulatedDevice(model, truth={"backlash": 0.008}))
    dev = SerialDevice("COM9", serial_module=_FakeSerialModule(port))
    s = run_test(dev, TEST, LIMITS, confirm_actuation=True)
    assert s.status == "completed" and s.source == "hardware" and len(s.samples) > 500
    assert any(w["cmd"] == "ping" for w in port.written)  # keepalive / hello request
    assert port.written[-1] == {"cmd": "stop"}


def test_serial_silence_and_device_stop_abort(single_joint) -> None:  # type: ignore[no-untyped-def]
    model = _model(single_joint)
    port = _FakePort(SimulatedDevice(model), stop_after=100)
    s = run_test(SerialDevice("COM9", serial_module=_FakeSerialModule(port)), TEST,
                 LIMITS.model_copy(update={"watchdog_ms": 50}), confirm_actuation=True)
    assert s.status == "aborted" and "watchdog: no data" in s.abort_reason
    port = _FakePort(SimulatedDevice(model), status={"type": "status", "state": "stopped",
                                                     "reason": "limit switch"})
    s = run_test(SerialDevice("COM9", serial_module=_FakeSerialModule(port)), TEST, LIMITS,
                 confirm_actuation=True)
    assert s.status == "aborted" and "limit switch" in s.abort_reason


def test_model_independent_session_analysis(single_joint, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    """Rig truth: backlash 8 mrad, no gravity, friction 0.4 N*m. 65536-count encoders."""
    from motionproof.hardware.analysis import analyse, load_session_csv

    model = _model(single_joint)
    dev = SimulatedDevice(model, truth={"backlash": 0.008}, encoder_counts=65536,
                          sample_hz=500.0)
    s = run_test(dev, TEST, LIMITS, confirm_actuation=True)
    data = load_session_csv(s.write_csv(tmp_path / "s.csv"))
    res = analyse(TEST, data, motor_counts_per_rev=65536, nominal_ratio=20.0)
    assert res["lost_motion"] == pytest.approx(0.008, abs=2e-4)
    assert res["measured_ratio"] == pytest.approx(20.0, rel=1e-3)
    assert abs(res["ratio_error"]) < 1e-3
    assert res["output_resolution_rad"] == pytest.approx(2 * np.pi / 65536, rel=0.01)
    cyc = HardwareTest(joint="j", kind="cycles", centre=0.0, excursion=0.4, move_time=0.6,
                       settle=0.4, cycles=4)
    s2 = run_test(SimulatedDevice(model, truth={"backlash": 0.008}, encoder_counts=65536),
                  cyc, LIMITS, confirm_actuation=True)
    rep = analyse(cyc, load_session_csv(s2.write_csv(tmp_path / "c.csv")))["repeatability"]
    # approached from one side every time: the spread stays well below the 8 mrad backlash
    assert set(rep) == {"a", "b"} and rep["b"]["n"] == 4 and rep["b"]["range"] < 0.004
