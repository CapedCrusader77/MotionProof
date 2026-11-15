# Building and testing the gearbox rig

This is the procedure for item 1 of the validation plan: measure the real NEMA 17 planetary
gearbox (the powered elbow in `examples/forearm_elbow`) and compare it with the model.
**Nothing here has been built or run yet.** The firmware has not been compiled.

## Safety first

* Wire a **normally closed emergency-stop switch in series with the motor supply** (or the
  driver's enable line through a relay that fails open). The firmware reads an auxiliary
  contact of the same switch, but the software stop is not the safety function.
* First tests: arm unloaded, small angles (±0.15 rad), slow moves (`move_time` >= 1 s), current
  limit on the driver set to the motor's rated current or lower.
* Keep hands out of the arm's sweep; the elbow stall torque is about 12 N*m at 33:1.
* Software limits in MotionProof (travel, speed, duration, watchdog) are an extra layer only.

## Bill of materials

| Item | Notes |
|---|---|
| ESP32 DevKit | any ESP32 with the Arduino core |
| Step/dir driver | A4988, DRV8825 or TMC2209 (step/dir mode); set the current limit |
| AS5600 magnetic encoder board + diametric magnet | on the gearbox **output** (12 bit, 1.53 mrad). An AS5048A (14 bit, 0.38 mrad) resolves backlash 4x better |
| E-stop | NC mushroom switch with an auxiliary NC contact |
| Limit switches (optional) | NC, in series |
| 12-24 V supply | sized for the motor |

## Wiring (firmware defaults, change in `motionproof_rig.ino`)

| ESP32 pin | Connects to |
|---|---|
| GPIO25 | driver STEP |
| GPIO26 | driver DIR |
| GPIO27 | driver EN (active low) |
| GPIO32 | e-stop auxiliary NC contact to GND |
| GPIO33 | limit switches NC to GND |
| GPIO21 / GPIO22 | AS5600 SDA / SCL (3.3 V supply) |

Mount the magnet on the output hub axis, centred within 0.5 mm, 1-2 mm from the sensor.
Encoder eccentricity appears as a once-per-revolution output error; record the mounting.

## Firmware

`hardware/firmware/motionproof_rig/motionproof_rig.ino`, Arduino IDE or `arduino-cli`, library
ArduinoJson 7. Check `MICROSTEPS`, `NOMINAL_RATIO`, `OUTPUT_SIGN` and the pins. The motor angle
comes from the step count (open loop): a skipped step is not detected on the input channel.

## Host

```bash
uv sync --extra hardware
```

```bash
uv run motionproof hardware devices
```

The rig appears as a serial port (for example `COM5`).

## Test sequence

Place the arm at the test's first commanded angle (`centre - excursion` for a reversal), then:

```bash
uv run motionproof hardware test rig_reversal.yaml --device COM5 --confirm --csv run1.csv
```

```bash
uv run motionproof hardware analyse run1.csv --test rig_reversal.yaml --motor-counts-per-rev 3200 --nominal-ratio 33
```

Recommended set, each repeated at least 3 times:

1. Reversal about the vertical (gravity torque near zero): lost motion is closest to the pure
   gear backlash.
2. Reversal at 60 degrees (one-sided gravity load): lost motion should almost vanish; if it
   does not, friction windup or compliance dominates.
3. Cycles between two angles (5 cycles): repeatability from one direction.
4. Two reversal recordings of the same kind on different days: one for calibration, one as the
   independent holdout (`motionproof calibration fit run1.csv --holdout run2.csv ...`).

Record for every session: date, temperature, payload, driver current, microstepping, magnet
mounting, and anything adjusted between runs.

## What the analysis reports (no model involved)

* positioning error at each settle point (command minus output);
* lost motion on reversal;
* repeatability over cycles;
* measured reduction ratio from pairs of settled points resting on the same gear flank, so the
  backlash cancels. Which flank carries the output cannot be seen in the signals, so state it:
  `--flank load` for the 60 degree test (gravity holds one flank: every settle point counts),
  `--flank arrival` only where friction, not a load, holds the output. Do **not** use the
  vertical reversal for the ratio: there gravity can pull the output across the dead band. On
  the simulated elbow the 60 degree test gives 33.06 against the true 33.0; the vertical test
  with `arrival` gives a wrong 29.9.

Then compare with the model (`compare_with_simulation`, Hardware testing screen) and calibrate
backlash, stiffness and friction on one run, validating on another.

## Resolution limits

With an AS5600 the output resolution is 1.53 mrad; the elbow model predicts about 10 mrad of
backlash, so it is resolvable but not finely. Use averaging over the settle window (the analysis
does) and an AS5048A if you need better than about 0.5 mrad.
