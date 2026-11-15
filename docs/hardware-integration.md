# Hardware integration

`motionproof/hardware/device.py`. **No physical hardware has been tested.**

* `SimulatedDevice`: a software rig driven by the engine with its own "true" parameters,
  encoder quantisation, noise and injectable faults (dropped, garbled, invalid readings,
  emergency stop, temperature). Every session it produces is labelled SIMULATED DEVICE.
* `SerialDevice`: USB serial / UART with the JSON-lines protocol in `device-protocol.md`; needs
  the optional `pyserial` package (not installed: `uv add pyserial`).

Safety (software): nothing moves without `confirm_actuation=True` for that run (the interface
resets the confirmation after each run); preflight on travel, peak speed, duration and torque
sensing; during the run, abort on emergency-stop or fault flags, travel, speed, torque,
temperature, duration, watchdog gaps, lost packets and three invalid readings. **These checks
are not a safety system**: a wired emergency-stop circuit, mechanical stops and an electrical
assessment are required before any powered test.

Sessions store device identity, firmware, test, limits, samples, lost and malformed counts and
a CSV export; `compare_with_simulation` overlays measured and predicted angles, residuals and
lost motion. Calibration uses one session for fitting and another as the independent holdout.

Recommended first physical test: small-angle, low-speed reversal without load, travel limits a
few degrees either side, emergency stop wired in series with the driver enable.
