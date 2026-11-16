# External datasets

All four datasets were inspected file by file before the adapters were written. Citations and
licences are reproduced in every run record and report. Keep them when you publish results.

## NVIDIA Anchor-Lab

* Source: https://huggingface.co/datasets/nvidia/Anchor-Lab, release v1.0 (June 2026), pinned
  to Hugging Face revision `647edd5787cd764cdc041103ad282dc59214d919`.
* Licence: Apache License 2.0 (dataset card).
* Citation: NVIDIA Robotics, "Anchor-Lab Dataset", v1.0, Hugging Face, June 2026.
* Format: long-form parquet with `time_ns` (int64), `time_utc`, `experiment`, `field`, `value`.
  Each field has its own time stamps.
* Integrity: SHA-256 of each file from the Hugging Face LFS pointer, verified at import.
* Imported subsets:
  * `h1-teststand`: 36 sine trials of the H1 elbow test stand (0.5/1.0/1.5 Hz × small/medium/
    large × stand positions 8–11). Fields `elbow_q`, `elbow_dq`, `elbow_tau`,
    `elbow_current`, `elbow_temp`, `elbow_voltage` at 2 ms.
  * `so101`: the train trial `single-joint-elbow` and the eight `heldout` trials. Per joint
    `actual_q` (~2 ms), `command_q` (~29 ms), `dq`, `tau_abs`, `temperature`, `voltage`,
    `is_moving`.
* Units (not stated on the card; assumed and checked for plausibility): angles in rad,
  velocities in rad/s, torque in N·m, current in A, voltage in V, temperature in °C (converted
  to K). `present_load_raw` is raw servo units and is not imported.
* Not measured: backlash, transmission error, load-cell torque. `elbow_tau` is the actuator's
  torque estimate.

## Stuttgart transmission error (DaRUS-5760)

* Source: https://darus.uni-stuttgart.de/dataset.xhtml?persistentId=doi:10.18419/DARUS-5760,
  version 1.0.
* Licence: CC BY 4.0.
* Citation: C. J. E. Bauer et al., "Replication Data for: Transmission Error Compensation for
  Industrial Robots Using Fourier Series", DaRUS, V1, 2026, doi:10.18419/DARUS-5760. Supplement
  to C. Bauer, S. Nowinski, V. Kamm, L. Steinle, A. Lechler, A. Verl, "Transmission Error
  Compensation for Industrial Robots Using Fourier Series", MHI 2026.
* System: gearboxes of a Stäubli TX2-40 on an experimental setup.
* Format: one file per measurement, columns `theta` (input-side position, rad), `q_set` (joint
  angle setpoint, rad), `theta_TE` (transmission error, rad). Position domain, no time stamps.
  The velocity setpoint is in the file name (`q_set_dot=...`, rad/s).
* Integrity: MD5 per file from the DaRUS API, verified at import (original CSV format).
* Split: published `identification/` and `validation/` folders for axes 2 and 3. Axis 1 has
  identification files only and is not used.

## NIST UR5 accuracy degradation

* Source: https://www.nist.gov/el/intelligent-systems-division-73500/degradation-measurement-robot-arm-position-accuracy
  (data.gov record: https://catalog.data.gov/dataset/degradation-measurement-of-robot-arm-position-accuracy).
* DOI: 10.18434/M31962. Last updated 2018-09-07.
* Licence: NIST licence statement, https://www.nist.gov/open/license.
* Citation: G. Qiao, NIST, "Degradation Measurement of Robot Arm Position Accuracy", 2018,
  doi:10.18434/M31962; related paper G. Qiao, B. A. Weiss, J. Manuf. Syst. 48 (2018),
  doi:10.1016/j.jmsy.2018.04.004.
* Files: `UR5TestResult_header.xlsx` (column meanings), `calculated_deviation.xlsx` (TCP
  deviation for 6 positions) and 18 runs: speed half/full × payload 16/45 lb × repeats 1–3,
  plus cold-start runs at 45 lb.
* Format: each CSV row is 13 bracketed vectors (time; target and actual joint position;
  target and actual velocity; target and actual current; target acceleration; target torque;
  control current; tool pose; TCP force; joint temperature). About 125 Hz.
* Integrity: no published checksums; SHA-256 recorded at import.
* Units: not stated in the header. Joint angles reach about 160, so they are degrees and are
  converted to rad (**inferred**). Velocities are already rad/s: before conversion, the
  differentiated positions were 57.3 (= 180/π) times the reported velocities on J1–J5
  (`nist_ur5.check_units`; J6 does not move). Accelerations are taken as rad/s² (inferred
  from the velocities, not checkable). Temperatures are °C, converted to K.
* Not measured per run: TCP deviation. The 6 published TCP values have no run or condition
  attached, so TCP accuracy cannot be validated (X6 INSUFFICIENT DATA).

## KUKA KR300 R2500 ultra SE identification benchmark

* Source: https://www.nonlinearbenchmark.org/benchmarks/industrial-robot, data
  doi:10.26204/data/5 (files dated 17 January 2022).
* Licence: as stated by the publisher at the data DOI; cite the benchmark paper.
* Citation: J. Weigand, J. Götz, J. Ulmen, M. Ruskowski, "Dataset and Baseline for an
  Industrial Robot Identification Benchmark", 6th Workshop on Nonlinear System Identification
  Benchmarks, Leuven, 2022, urn:nbn:de:hbz:386-kluedo-67317.
* File used: `Robot_Identification_Benchmark_Without_Raw_Data.rar` (MD5 published, verified),
  extracted with libarchive `tar`. Inside, `inverse_identification_without_raw_data.mat` holds
  `u` = axis position, velocity, acceleration (deg, deg/s, deg/s²; filtered, 10 Hz) and `y` =
  motor torques (N·m), with the benchmark's train/test split.
* Not used: raw high-rate runs (the benchmark forbids them for comparability), videos.
