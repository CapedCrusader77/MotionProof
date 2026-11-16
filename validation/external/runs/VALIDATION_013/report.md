# VALIDATION_013: TCP accuracy degradation, UR5

**Status: INSUFFICIENT DATA** (benchmark X6, protocol `nist-tcp`)

- System: Universal Robots UR5
- Quantity compared: TCP deviation from the 7-D measurement system
- Baseline: -
- MotionProof model: -
- Acceptance (pre-registered): requires measured TCP deviation per run and condition
- Identification: -
- Validation: -
- Unused: -
- Scope: external system; says nothing about the MotionProof reference gearbox or user hardware

Reason: the dataset publishes measured TCP deviation for 6 positions only, without the run, condition or trajectory they belong to; a TCP accuracy or degradation prediction cannot be compared with it

## Transformations


## Data

- Dataset: Degradation Measurement of Robot Arm Position Accuracy
- Source: https://www.nist.gov/el/intelligent-systems-division-73500/degradation-measurement-robot-arm-position-accuracy
- Version: dataset last updated 2018-09-07
- Licence: NIST licence statement (linked from the data.gov record): https://www.nist.gov/open/license
- Citation: G. Qiao, NIST, "Degradation Measurement of Robot Arm Position Accuracy", 2018, doi:10.18434/M31962. Related: G. Qiao, B. A. Weiss, J. Manuf. Syst. 48 (2018), doi:10.1016/j.jmsy.2018.04.004.
- Files used: 0 (checksums in record.json)

## Reproduce

```bash
motionproof external validate nist-tcp
```

Recorded 2026-11-16T11:07:43+00:00 with MotionProof 0.3.0, adapter 1.0.0, Windows-11-10.0.26300-SP0.
