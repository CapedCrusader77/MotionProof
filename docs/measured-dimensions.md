# Measured component dimensions

Item 2 of the validation plan: replace assumed tolerances with dimensions measured on real
parts. Two routes exist: a 3D scan (`as-built-import.md`) or direct measurement with gauges,
described here. **No real measurements have been imported yet.**

## Sheet

```bash
uv run motionproof measurements template examples/forearm_elbow/model.yaml --parts 5 -o sheet.csv
```

Columns: `part_id, tolerance, value, unit, instrument, resolution, date, operator, notes`.
The unit is required on every row; it is converted, never assumed. Repeat readings of one part
are averaged.

## What to measure on the powered elbow (printed PETG/PLA+ parts)

| Tolerance id | Feature | Instrument | Note |
|---|---|---|---|
| `hub_journal_diameter` | GB-07 output hub journal, 25 mm | micrometer (0.001 mm) | 3 readings at 120 degrees |
| `lid_seat_diameter` | GB-02 bearing seat, 37 mm | bore gauge or inside micrometer | a caliper (0.01 mm) breaks the 10:1 rule on a 0.3 mm band only marginally; record its resolution |
| `s1_pin_radial_*`, `s2_pin_radial_*` | carrier pin circle radius per pin | caliper over pins, or a scan | radius deviation from 16.5 / 18.0 mm |
| `ring_offset_x/_y` | ring gear bore position in GB-01 | scan or CMM | hard with hand tools |
| backlash values | per mesh | rig measurement (`rig-build-and-test.md`) | not a dimension |

Print at least 5 parts per feature from the same printer, filament and settings. 30 or more
are needed for a stable standard deviation and capability index; the tool warns below that.

## Commands

```bash
uv run motionproof measurements summary examples/forearm_elbow/model.yaml sheet.csv
```

```bash
uv run motionproof measurements apply examples/forearm_elbow/model.yaml sheet.csv -o examples/forearm_elbow/model_measured.yaml
```

```bash
uv run motionproof measurements evaluate sheet.csv --experiment examples/forearm_elbow/experiment_move_to_90.yaml
```

* `summary`: per tolerance n, mean, standard deviation, range, out-of-spec count, Cp/Cpk and a
  gauge-resolution check (resolution should be at most a tenth of the tolerance width).
* `apply`: a new model file whose measured tolerances use normal or empirical distributions
  from the data, marked `confidence: measured`. The original model file is never changed.
* `evaluate`: simulates each measured part as it is; tolerances not measured stay at their
  design value and are listed.

The process standard deviation found here is also the input of the yield-based cost model of
the Engineering Challenge (`ENGINEERING_CHALLENGE.md`).
