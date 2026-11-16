"""Public experimental datasets known to the external validation framework.

Each entry records where the data come from, under which licence, how to cite it, and which
files each validation protocol uses. Nothing here is downloaded until a user runs
``motionproof external import <dataset>``.

None of these systems is the MotionProof reference gearbox. Each external system is its own
validation case.
"""

from __future__ import annotations

from dataclasses import dataclass, field

ADAPTER_VERSION = "1.0.0"


@dataclass(frozen=True)
class DatasetInfo:
    key: str
    title: str
    system: str
    publisher: str
    url: str
    doi: str | None
    version: str
    licence: str
    licence_url: str
    citation: str
    measured: tuple[str, ...]
    not_measured: tuple[str, ...]
    notes: tuple[str, ...] = field(default_factory=tuple)


ANCHOR_LAB_REVISION = "647edd5787cd764cdc041103ad282dc59214d919"

DATASETS: dict[str, DatasetInfo] = {
    "anchor-lab": DatasetInfo(
        key="anchor-lab",
        title="Anchor-Lab: sim-to-real robot telemetry (NVIDIA Robotics)",
        system="Unitree H1 elbow actuator on a test stand; SO-101 arm (Feetech servos)",
        publisher="NVIDIA Corporation / NVIDIA Robotics",
        url="https://huggingface.co/datasets/nvidia/Anchor-Lab",
        doi=None,
        version=f"v1.0 (Hugging Face revision {ANCHOR_LAB_REVISION})",
        licence="Apache-2.0",
        licence_url="https://www.apache.org/licenses/LICENSE-2.0",
        citation="NVIDIA Robotics, \"Anchor-Lab Dataset\", v1.0, Hugging Face, June 2026, "
                 "https://huggingface.co/datasets/nvidia/Anchor-Lab (Apache License 2.0).",
        measured=("joint position", "joint velocity", "joint torque estimate (actuator firmware)",
                  "motor current", "temperature", "supply voltage",
                  "commanded position (SO-101)"),
        not_measured=("gear backlash directly", "output-side load-cell torque",
                      "link inertia", "transmission error"),
        notes=("H1 'elbow_tau' is the actuator's own torque estimate, not a load-cell "
               "measurement.",
               "SO-101 'command_q' is sampled at about 34 Hz and 'actual_q' at about 485 Hz."),
    ),
    "stuttgart-te": DatasetInfo(
        key="stuttgart-te",
        title="Replication Data for: Transmission Error Compensation for Industrial Robots "
              "Using Fourier Series",
        system="Staubli TX2-40 industrial robot gearboxes (axes 1-3) on an experimental setup",
        publisher="University of Stuttgart (ISW), DaRUS",
        url="https://darus.uni-stuttgart.de/dataset.xhtml?persistentId=doi%3A10.18419%2FDARUS-5760",
        doi="10.18419/DARUS-5760",
        version="1.0",
        licence="CC BY 4.0",
        licence_url="https://creativecommons.org/licenses/by/4.0/",
        citation="C. J. E. Bauer et al., \"Replication Data for: Transmission Error "
                 "Compensation for Industrial Robots Using Fourier Series\", DaRUS, V1, 2026, "
                 "doi:10.18419/DARUS-5760 (CC BY 4.0). Supplement to C. Bauer, S. Nowinski, "
                 "V. Kamm, L. Steinle, A. Lechler, A. Verl, \"Transmission Error Compensation "
                 "for Industrial Robots Using Fourier Series\", MHI 2026.",
        measured=("input-side position theta", "joint angle setpoint q_set",
                  "transmission error theta_TE"),
        not_measured=("time stamps (data are in the position domain)", "torque", "load"),
        notes=("Identification and validation recordings are separate files, as published.",
               "Axis 1 has identification recordings only and is not used for validation."),
    ),
    "nist-ur5": DatasetInfo(
        key="nist-ur5",
        title="Degradation Measurement of Robot Arm Position Accuracy",
        system="Universal Robots UR5",
        publisher="National Institute of Standards and Technology (NIST)",
        url="https://www.nist.gov/el/intelligent-systems-division-73500/"
            "degradation-measurement-robot-arm-position-accuracy",
        doi="10.18434/M31962",
        version="dataset last updated 2018-09-07",
        licence="NIST licence statement (linked from the data.gov record): "
                "https://www.nist.gov/open/license",
        licence_url="https://www.nist.gov/open/license",
        citation="G. Qiao, NIST, \"Degradation Measurement of Robot Arm Position Accuracy\", "
                 "2018, doi:10.18434/M31962. Related: G. Qiao, B. A. Weiss, J. Manuf. Syst. "
                 "48 (2018), doi:10.1016/j.jmsy.2018.04.004.",
        measured=("target and actual joint positions", "target and actual joint velocities",
                  "target and actual joint currents", "target joint accelerations",
                  "target joint torques", "joint temperatures", "tool Cartesian pose "
                  "(controller estimate)", "TCP deviation for 6 positions (7-D system)"),
        not_measured=("TCP deviation per run and condition (only 6 values, condition not "
                      "stated)", "measured joint torque"),
        notes=("No checksums are published; MotionProof records SHA-256 at import.",
               "Joint angles are in degrees: inferred from the values (up to about 160), "
               "the header gives no unit. Velocities are rad/s (differentiated positions "
               "give 57.3 x the reported velocity before conversion)."),
    ),
    "kuka-kr300": DatasetInfo(
        key="kuka-kr300",
        title="Dataset and Baseline for an Industrial Robot Identification Benchmark",
        system="KUKA KR300 R2500 ultra SE industrial robot (6 axes)",
        publisher="TU Kaiserslautern (RPTU)",
        url="https://www.nonlinearbenchmark.org/benchmarks/industrial-robot",
        doi="10.26204/data/5",
        version="2022 release (files dated 17-Jan-2022)",
        licence="as stated by the publisher at doi:10.26204/data/5 (benchmark data for "
                "research use with citation)",
        licence_url="https://doi.org/10.26204/data/5",
        citation="J. Weigand, J. Goetz, J. Ulmen, M. Ruskowski, \"Dataset and Baseline for "
                 "an Industrial Robot Identification Benchmark\", 6th Workshop on Nonlinear "
                 "System Identification Benchmarks, Leuven, 2022, "
                 "urn:nbn:de:hbz:386-kluedo-67317; data doi:10.26204/data/5.",
        measured=("axis positions, velocities, accelerations (filtered)", "motor torques"),
        not_measured=("backlash directly", "temperature (raw data only)"),
        notes=("Uses the prepared inverse-identification split (train/test) without raw data, "
               "as the benchmark prescribes for comparability.",),
    ),
}
