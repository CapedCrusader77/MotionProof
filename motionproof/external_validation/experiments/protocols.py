"""Pre-registered validation protocols: data splits, models and acceptance criteria.

These definitions were written and committed before any validation run was executed. They
must not be changed after results have been seen; a changed protocol is a new protocol with a
new ID, and the old result stays in the record.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Protocol:
    id: str
    benchmark: str
    dataset: str
    title: str
    system: str
    quantity: str
    identification: str
    validation: str
    unused: str
    baseline: str
    model: str
    acceptance: str
    motionproof_components: tuple[str, ...]
    reproduce: str


PROTOCOLS: dict[str, Protocol] = {
    "transmission-error": Protocol(
        id="transmission-error", benchmark="X1-v1", dataset="stuttgart-te",
        title="Gearbox transmission error, Staubli TX2-40 axes 2 and 3",
        system="Staubli TX2-40 gearboxes on an experimental setup",
        quantity="theta_TE (rad), as published, at every published sample",
        identification="all files in identification/axis_2 and identification/axis_3",
        validation="all files in validation/axis_2 and validation/axis_3 (published split)",
        unused="identification/axis_1 (no validation recordings exist for axis 1)",
        baseline="B0: constant transmission error equal to the identification mean, per axis",
        model="MotionProof TE: c0 + (b/2) sign(q_set_dot) + sum_k [a_k sin(k q_set) + "
              "c_k cos(k q_set)], the periodic TE term and dead-band offset of the drive "
              "model; orders k: the 30 largest integer orders 1..4000 cycles per joint "
              "revolution in the identification spectrum (uniform q grid, step 1e-4 rad)",
        acceptance="per axis: validation RMSE(model) <= 0.5 x validation RMSE(B0) and "
                   "validation RMSE(model) <= 1.5 x identification RMSE(model); X1 passes "
                   "only if both axes pass",
        motionproof_components=("simulation.engine drive gap equation: TE(theta) term "
                                "sum a sin(c theta + phi)", "backlash dead band b/2"),
        reproduce="motionproof external validate transmission-error"),
    # v2 added after v1 was run (VALIDATION_001, FAIL). Reason: v1 allowed orders that complete
    # less than about one period over the measured joint range (about 3.4 rad); those columns
    # are nearly collinear with the offset (scaled condition number about 4e11) and are not
    # identifiable from the data. v2 changes only the order selection rule; data split and
    # acceptance thresholds are identical to v1. v1 and its result stay on record.
    "transmission-error-v2": Protocol(
        id="transmission-error-v2", benchmark="X1-v2", dataset="stuttgart-te",
        title="Gearbox transmission error, Staubli TX2-40 axes 2 and 3 (identifiable orders)",
        system="Staubli TX2-40 gearboxes on an experimental setup",
        quantity="theta_TE (rad), as published, at every published sample",
        identification="all files in identification/axis_2 and identification/axis_3",
        validation="all files in validation/axis_2 and validation/axis_3 (published split)",
        unused="identification/axis_1 (no validation recordings exist for axis 1)",
        baseline="B0: constant transmission error equal to the identification mean, per axis",
        model="as transmission-error (v1), but orders k are restricted to those completing at "
              "least 2 full periods over the shortest identification recording of the axis "
              "(k >= ceil(4 pi / span)); the 30 largest such orders up to 4000 are used",
        acceptance="per axis: validation RMSE(model) <= 0.5 x validation RMSE(B0) and "
                   "validation RMSE(model) <= 1.5 x identification RMSE(model); X1 passes "
                   "only if both axes pass (unchanged from v1)",
        motionproof_components=("simulation.engine drive gap equation: TE(theta) term "
                                "sum a sin(c theta + phi)", "backlash dead band b/2"),
        reproduce="motionproof external validate transmission-error-v2"),
    # v3 added after v1 (VALIDATION_001) and v2 (VALIDATION_003) failed. Reason: the dataset's
    # own plot_figures.m shows that the validation recordings were made with the authors'
    # Fourier compensation active ("excluding ramp-up of compensation"); their theta_TE is the
    # residual after compensation, about 6.5x smaller than the uncompensated identification
    # TE. Comparing a predicted uncompensated TE with it compares different physical
    # quantities, so v1 and v2 are invalid comparisons (kept on record). v3 holds out whole
    # uncompensated recordings at alternate velocity setpoints. Orders and acceptance
    # thresholds as v2.
    "transmission-error-v3": Protocol(
        id="transmission-error-v3", benchmark="X1", dataset="stuttgart-te",
        title="Gearbox transmission error, Staubli TX2-40 axes 2 and 3 (speed holdout)",
        system="Staubli TX2-40 gearboxes on an experimental setup",
        quantity="theta_TE (rad) without compensation, at every published sample",
        identification="identification/axis_k files whose velocity setpoint has an even rank "
                       "(0, 2, 4, ...) when the setpoints of each sign are sorted by magnitude",
        validation="identification/axis_k files with odd rank (whole recordings, never mixed)",
        unused="validation/ folder: residual TE with the authors' compensation active (a "
               "different quantity); identification/axis_1",
        baseline="B0: constant transmission error equal to the identification mean, per axis",
        model="as transmission-error-v2 (orders with >= 2 periods over the shortest "
              "identification recording, 30 largest up to 4000)",
        acceptance="per axis: validation RMSE(model) <= 0.5 x validation RMSE(B0) and "
                   "validation RMSE(model) <= 1.5 x identification RMSE(model); X1 passes "
                   "only if both axes pass (unchanged)",
        motionproof_components=("simulation.engine drive gap equation: TE(theta) term "
                                "sum a sin(c theta + phi)", "backlash dead band b/2"),
        reproduce="motionproof external validate transmission-error-v3"),
    "h1-friction": Protocol(
        id="h1-friction", benchmark="X2", dataset="anchor-lab",
        title="Joint friction and dynamics, Unitree H1 elbow test stand",
        system="Unitree H1 elbow actuator on the Anchor-Lab test stand",
        quantity="elbow_tau (actuator torque estimate, N*m), on a uniform 2 ms grid",
        identification="36 sine trials (0.5/1.0/1.5 Hz x small/medium/large) at stand "
                       "positions 8, 9 and 10",
        validation="the 12 sine trials at stand position 11 (whole trials, never mixed)",
        unused="all other Anchor-Lab trials",
        baseline="B0: rigid joint without friction, tau = J ddq + g1 sin q + g2 cos q + tau0",
        model="MotionProof joint friction: B0 + c dq + Fc tanh(dq / 0.02 rad/s) (viscous "
              "damping plus smoothed Coulomb friction, as the drive model's damping and "
              "frictionloss)",
        acceptance="validation RMSE(model) <= 0.8 x validation RMSE(B0) and validation "
                   "NRMSE(model) <= 0.35",
        motionproof_components=("drive friction (Coulomb frictionloss) and damping",
                                "calibration practice: fit on one set, validate on a "
                                "separate holdout"),
        reproduce="motionproof external validate h1-friction"),
    "so101-tracking": Protocol(
        id="so101-tracking", benchmark="X3", dataset="anchor-lab",
        title="Simulated joint response to the recorded command, SO-101 elbow servo",
        system="SO-101 arm, elbow joint (Feetech servo)",
        quantity="elbow/actual_q (rad) at its own sample instants",
        identification="trial so101-sysid-50motion-train-single-joint-elbow",
        validation="every heldout trial in which the elbow command spans >= 0.1 rad",
        unused="heldout trials in which the elbow command spans < 0.1 rad (elbow not "
               "excited); all other train trials",
        baseline="B0: actual = command held between samples (zero-order hold) + constant "
                 "offset fitted on identification",
        model="MotionProof drive response: second-order position loop (wn, zeta) with "
              "velocity limit vmax driving the joint through a dead band b (the drive "
              "model's backlash), plus offset; simulated at 1 ms from the recorded command",
        acceptance="pooled validation RMSE(model) <= 0.6 x pooled validation RMSE(B0)",
        motionproof_components=("backlash dead band", "motor-side position control with "
                                "speed limit"),
        reproduce="motionproof external validate so101-tracking"),
    "kuka-inverse": Protocol(
        id="kuka-inverse", benchmark="X4", dataset="kuka-kr300",
        title="Inverse dynamics per axis, KUKA KR300 R2500 ultra SE",
        system="KUKA KR300 R2500 ultra SE (6 axes)",
        quantity="motor torque per axis (N*m), benchmark test set",
        identification="benchmark training set (inverse identification, without raw data)",
        validation="benchmark test set",
        unused="raw high-rate runs (excluded by the benchmark for comparability)",
        baseline="B0 per axis: tau = J ddq + g1 sin q + g2 cos q + tau0",
        model="MotionProof single-joint drive model per axis: B0 + c dq + Fc tanh(dq / 0.02 "
              "rad/s). Joint coupling, pose-dependent inertia and the axis-2 hydraulic "
              "counterbalance are NOT modelled",
        acceptance="every axis: test RMSE(model) <= 0.8 x test RMSE(B0)",
        motionproof_components=("drive friction and damping", "single-joint dynamics"),
        reproduce="motionproof external validate kuka-inverse"),
    "nist-tracking": Protocol(
        id="nist-tracking", benchmark="X5", dataset="nist-ur5",
        title="Joint position error under speed, payload and temperature, UR5",
        system="Universal Robots UR5",
        quantity="joint position error e = target q - actual q (rad), controller data",
        identification="repeats 1 and 2 of every condition",
        validation="repeat 3 of every condition",
        unused="tool pose, TCP force",
        baseline="B0 per joint: constant error equal to the identification mean",
        model="MotionProof static drive deflection per joint: e = e0 + tau_target / k + "
              "(b/2) sign(dq_target) + lag x dq_target (compliance, dead band and a "
              "velocity lag of the position loop)",
        acceptance="every joint J1..J6: validation RMSE(model) <= 0.8 x validation RMSE(B0)",
        motionproof_components=("static deflection b/2 + tau/k", "position-loop lag"),
        reproduce="motionproof external validate nist-tracking"),
    "nist-tcp": Protocol(
        id="nist-tcp", benchmark="X6", dataset="nist-ur5",
        title="TCP accuracy degradation, UR5",
        system="Universal Robots UR5",
        quantity="TCP deviation from the 7-D measurement system",
        identification="-", validation="-", unused="-",
        baseline="-", model="-",
        acceptance="requires measured TCP deviation per run and condition",
        motionproof_components=("workspace accuracy, degradation",),
        reproduce="motionproof external validate nist-tcp"),
}

# Protocols whose comparison was found invalid after running; their records stay unchanged.
SUPERSEDED = {
    "transmission-error": "superseded by v2 (unidentifiable low orders) and v3; also compared "
                          "against compensated validation recordings (different quantity)",
    "transmission-error-v2": "superseded by v3: validation recordings contain the residual "
                             "after the authors' compensation, a different quantity",
}

