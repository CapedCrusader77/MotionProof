# Published benchmark package

Everything needed to check the benchmark results without trusting MotionProof:

| Path | Content |
|---|---|
| `data/reference_design/` | the reference NEMA 17 planetary arm project: `model.yaml` (tolerances, gear stages, drives, assumptions), `geometry/model.xml` (MJCF with inertials), `inventory.json`, STEP and meshes |
| `data/single_joint/` | the single-joint test model (`single.xml`, `model.json`): 1 kg point mass on a 0.3 m arm, 20:1 gearbox, stiffness 2000 N*m/rad |
| `data/inputs.json` | every benchmark input constant, seeds and the known scan pose |
| `data/A_synthetic_shaft_scan_posed.xyz` | SYNTHETIC scan of an 8.030 mm shaft (5 um noise, moved by a known pose) |
| `data/G_synthetic_*.csv` | SYNTHETIC production batches (nested batch/setup/part variation, shared vs independent setup error, linear tool wear) |
| `data/I_synthetic_wear.csv` | SYNTHETIC backlash-versus-cycles wear data |
| `data/suite_results.json` | the full output of the suite run (expected, actual, error, criterion per check) |
| `data/motionproof_outputs.json` | MotionProof outputs the references recheck (FK tip positions, chosen challenge candidates) |
| `data/references.json` | output of `reference_calculations.py` |
| `data/cross_check.json` | reference versus suite, per quantity |
| `data/MANIFEST.json` | SHA-256 (first 16 hex digits) of every file |
| `reference_calculations.py` | independent references: NumPy, SciPy, PyYAML only; refuses to run if motionproof is imported |
| `publish.py` | regenerates the data with the suite's seeds, runs the suite and the references, writes `BENCHMARK_RESULTS.md` |

## Reproduce

```bash
uv run python benchmarks/publish.py
```

```bash
python -I benchmarks/reference_calculations.py benchmarks/data
```

The second command needs only `numpy`, `scipy` and `pyyaml`; it can run in a clean environment
without MotionProof installed.

## What the cross-check establishes

* **Expected values**: every closed-form expected value in the suite (fit limits, RSS clearance,
  gear ratios and lost motion, transmission error, law-of-cosines IK, gravity torque from the
  MJCF inertials, payload torques, deflections, variance-component sums, wear-crossing cycles)
  is recomputed from the published inputs by separate code and must agree to 1e-9 relative.
* **Estimates from raw data**: the published raw data are re-analysed with different code (own
  nested ANOVA, `numpy.polyfit`, a Kasa circle fit of the raw scan without registration) and
  must agree with MotionProof's estimates; MotionProof's FK and the yield cost of the chosen
  challenge candidate are recomputed from closed forms.
* Checks without a closed form (dynamic simulation versus static theory, adaptive sampling,
  root cause) are reported in the suite tables with their stated acceptance criteria only.

## Assumptions and limits

* All data here are **SYNTHETIC** with known ground truth. Nothing is a physical measurement;
  benchmark J (hardware) is NOT RUN until a rig exists (see `docs/rig-build-and-test.md`).
* Reference design values are illustrative and labelled `assumed` in `model.yaml`; they are not
  supplier specifications.
* The cross-check verifies that MotionProof computes what the formulations say. It does not
  validate the formulations against physical reality.
* Floating-point results can differ in the last digits across platforms and library versions;
  the agreement tolerances allow for that.
