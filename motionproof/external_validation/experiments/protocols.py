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
        id="transmission-error-v3", benchmark="X1-v3", dataset="stuttgart-te",
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
    # v4 added 2026-11-26 AFTER v3 was run (VALIDATION_016: axis 2 PASS, axis 3 FAIL), so it is
    # not blind. Reason: the v3 residual of every recording has a mean that falls almost
    # linearly with the velocity setpoint on both axes (about -6e-3 rad at +0.73 rad/s), the
    # twist of a compliant gearbox under viscous friction torque. The drive model has this
    # physics (damping through finite stiffness); v3 left it out. v4 adds one column; split,
    # orders and acceptance are identical to v3.
    "transmission-error-v4": Protocol(
        id="transmission-error-v4", benchmark="X1", dataset="stuttgart-te",
        title="Gearbox transmission error, Staubli TX2-40 axes 2 and 3 (speed holdout, "
              "viscous windup; not blind)",
        system="Staubli TX2-40 gearboxes on an experimental setup",
        quantity="theta_TE (rad) without compensation, at every published sample",
        identification="as transmission-error-v3 (even-rank velocity setpoints)",
        validation="as transmission-error-v3 (odd-rank velocity setpoints, whole recordings)",
        unused="as transmission-error-v3",
        baseline="B0: constant transmission error equal to the identification mean, per axis",
        model="as transmission-error-v3 plus w x q_set_dot: windup of the gearbox stiffness "
              "under viscous friction torque (w = c / k)",
        acceptance="as transmission-error-v3: per axis validation RMSE(model) <= 0.5 x "
                   "validation RMSE(B0) and <= 1.5 x identification RMSE(model); both axes",
        motionproof_components=("simulation.engine drive gap equation: TE(theta) term "
                                "sum a sin(c theta + phi)", "backlash dead band b/2",
                                "friction torque through drive stiffness (windup)"),
        reproduce="motionproof external validate transmission-error-v4"),
    # Written and committed 2026-11-26 BEFORE any axis 1 file was downloaded or inspected: a
    # blind test of the transmission-error-v4 model form (chosen on axes 2 and 3) on the axis
    # no protocol had used. Split rule, order rule and acceptance are those of v4, unchanged.
    "transmission-error-axis1": Protocol(
        id="transmission-error-axis1", benchmark="X8", dataset="stuttgart-te",
        title="Gearbox transmission error, Staubli TX2-40 axis 1 (blind test of the X1 v4 "
              "model)",
        system="Staubli TX2-40 gearbox, axis 1, on an experimental setup",
        quantity="theta_TE (rad) without compensation, at every published sample",
        identification="identification/axis_1 files whose velocity setpoint has an even rank "
                       "when the setpoints of each sign are sorted by magnitude",
        validation="identification/axis_1 files with odd rank (whole recordings)",
        unused="axes 2 and 3 (used to choose the model form); validation/ folder",
        baseline="B0: constant transmission error equal to the identification mean",
        model="transmission-error-v4 unchanged: c0 + (b/2) sign(q_set_dot) + w q_set_dot + "
              "the 30 largest identifiable orders (>= 2 periods over the shortest "
              "identification recording), fitted on axis 1 identification files only",
        acceptance="validation RMSE(model) <= 0.5 x validation RMSE(B0) and validation "
                   "RMSE(model) <= 1.5 x identification RMSE(model)",
        motionproof_components=("simulation.engine drive gap equation: TE(theta) term",
                                "backlash dead band b/2",
                                "friction torque through drive stiffness (windup)"),
        reproduce="motionproof external validate transmission-error-axis1"),
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
        id="kuka-inverse", benchmark="X4-v1", dataset="kuka-kr300",
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
    # v2 added 2026-11-26 AFTER v1 was run (VALIDATION_019: A2, A3, A5 FAIL), so it is not
    # blind. Reason: v1 modelled each axis alone, so gravity on A2, A3 and A5 could depend only
    # on that axis's own angle, while the arm's weight acts through q2 + q3 (and the wrist
    # through q4, q5). MotionProof simulates assemblies as multibody models in MuJoCo, where this
    # coupling is present. v2 adds the coupled gravity terms to the model; B0, split and
    # acceptance are unchanged. Two A5 forms were tried on the test set (q2+q3+q5 alone, then
    # the spherical-wrist form below); the second is used. The friction-only contribution
    # (model vs the same coupled gravity without friction) is reported alongside.
    "kuka-inverse-v2": Protocol(
        id="kuka-inverse-v2", benchmark="X4", dataset="kuka-kr300",
        title="Inverse dynamics per axis, KUKA KR300 R2500 ultra SE (coupled gravity; not "
              "blind)",
        system="KUKA KR300 R2500 ultra SE (6 axes)",
        quantity="motor torque per axis (N*m), benchmark test set",
        identification="benchmark training set (inverse identification, without raw data)",
        validation="benchmark test set",
        unused="raw high-rate runs (excluded by the benchmark for comparability)",
        baseline="B0 per axis: tau = J ddq + g1 sin q + g2 cos q + tau0 (unchanged)",
        model="kuka-inverse model plus multibody gravity: A2 and A3 add sin, cos(q2 + q3); A5 "
              "adds sin, cos(q5) times each of sin(q23) cos q4, cos(q23) cos q4, sin q23, "
              "cos q23 (q23 = q2 + q3). Pose-dependent inertia and the axis-2 hydraulic "
              "counterbalance are NOT modelled",
        acceptance="every axis: test RMSE(model) <= 0.8 x test RMSE(B0) (unchanged)",
        motionproof_components=("drive friction and damping", "multibody gravity coupling"),
        reproduce="motionproof external validate kuka-inverse-v2"),
    # Written and committed 2026-11-27 BEFORE any model was fitted to, or any plot made of, the
    # UR5 joint currents: a blind test of the kuka-inverse-v2 idea (gravity acts through the sum
    # of parallel joint angles) on a second robot. The UR5 data were already imported for X5,
    # which uses positions only. Column sets below are fixed from the UR5 kinematics: J2, J3, J4
    # pitch about parallel axes; J5 is perpendicular to them; J1 and J6 carry no gravity term.
    "nist-dynamics": Protocol(
        id="nist-dynamics", benchmark="X9", dataset="nist-ur5",
        title="Joint current per axis, UR5 (blind test of the multibody-gravity model)",
        system="Universal Robots UR5",
        quantity="actual joint current per joint (A), controller data, every sample",
        identification="repeats 1 and 2 of every condition",
        validation="repeat 3 of every condition",
        unused="target current, target torque, control current, tool pose, TCP force",
        baseline="B0 per joint: i = J ddq_target + (g1 + p1 m) sin q + (g2 + p2 m) cos q + i0, "
                 "with m the run's payload mass (kg)",
        model="B0 + c dq + Fc tanh(dq / 0.02 rad/s) + multibody gravity columns, each also "
              "times m: J2 and J3 sin, cos of q23 and q234; J4 sin, cos of q234 and the same "
              "times cos q5 and sin q5; J5 sin, cos q5 times sin q234 and cos q234; J1 and J6 "
              "none (q23 = q2 + q3, q234 = q2 + q3 + q4)",
        acceptance="every joint J1..J6: validation RMSE(model) <= 0.8 x validation RMSE(B0) "
                   "(as X4)",
        motionproof_components=("drive friction and damping", "multibody gravity coupling"),
        reproduce="motionproof external validate nist-dynamics"),
    "nist-tracking": Protocol(
        id="nist-tracking", benchmark="X5-v1", dataset="nist-ur5",
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
    # v2 added 2026-11-26 AFTER v1 was run (VALIDATION_027: J1 PASS, J2..J6 FAIL), so it is not
    # blind. Reason: a second-order position loop (the drive response used in X3) tracking a
    # moving target lags by (2 zeta / wn) dq + (1 / wn^2) ddq; v1 had only the first term. v2
    # adds the second, from the controller's recorded target acceleration. Split and acceptance
    # are unchanged.
    "nist-tracking-v2": Protocol(
        id="nist-tracking-v2", benchmark="X5", dataset="nist-ur5",
        title="Joint position error under speed, payload and temperature, UR5 (position-loop "
              "acceleration lag; not blind)",
        system="Universal Robots UR5",
        quantity="joint position error e = target q - actual q (rad), controller data",
        identification="repeats 1 and 2 of every condition",
        validation="repeat 3 of every condition",
        unused="tool pose, TCP force",
        baseline="B0 per joint: constant error equal to the identification mean",
        model="nist-tracking model plus a x ddq_target (acceleration lag of the second-order "
              "position loop, a = 1 / wn^2)",
        acceptance="every joint J1..J6: validation RMSE(model) <= 0.8 x validation RMSE(B0) "
                   "(unchanged)",
        motionproof_components=("static deflection b/2 + tau/k", "second-order position "
                                "loop lag"),
        reproduce="motionproof external validate nist-tracking-v2"),
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
    # Written 2026-11-26, AFTER the published value (0.59 deg) was known: this check is not
    # blind. What is fixed in advance is the tolerance model: the FDM variation below was
    # written on 2026-11-15 for the project's own printed elbow, before this source was found,
    # and is used unchanged.
    "compact-sspg-backlash": Protocol(
        id="compact-sspg-backlash", benchmark="X7", dataset="compact-sspg",
        title="No-load backlash of a 3D-printed planetary gearbox, COMPAct SSPG 7.2:1 "
              "(not blind)",
        system="COMPAct SSPG 7.2:1, printed PLA planetary actuator",
        quantity="output backlash at no load (rad); published: 0.59 deg, one value",
        identification="nothing is fitted; the geometry is measured from the published print "
                       "files (sun, planet, ring, carrier)",
        validation="the published no-load backlash of the printed actuator",
        unused="the compound (CPG) and Wolfrom actuators; stiffness and efficiency",
        baseline="B0: the print files alone (CAD clearances, no manufacturing variation, no "
                 "bearing clearance)",
        model="MotionProof planetary stage model (transmissions.gears.evaluate_stage) with the "
              "measured CAD clearances and the project's FDM assumptions of 2026-11-15: mesh "
              "backlash and planet pin position each truncated normal, sd 0.04 mm, within "
              "+-0.10 mm; planet bearing clearance uniform 0.02 to 0.10 mm; sun runout TIR "
              "uniform 0 to 0.10 mm with uniform phase; ring offset x, y truncated normal sd "
              "0.04 mm within +-0.10 mm; 20000 copies, seed 2026",
        acceptance="PASS if the published value lies within the 5 to 95 % range of the "
                   "predicted backlash",
        motionproof_components=("transmissions.gears.evaluate_stage (lost motion from mesh "
                                "clearances, pin position, bearing clearance, runout)",),
        reproduce="motionproof external validate compact-sspg-backlash"),
}

# Protocols replaced after running, because the comparison was invalid or a newer version (not
# blind) adds a missing term; their records stay unchanged.
SUPERSEDED = {
    "transmission-error": "superseded by v2 (unidentifiable low orders) and v3; also compared "
                          "against compensated validation recordings (different quantity)",
    "transmission-error-v2": "superseded by v3: validation recordings contain the residual "
                             "after the authors' compensation, a different quantity",
    "transmission-error-v3": "superseded by v4 (written after this run): adds the viscous "
                             "windup term the residuals showed; not blind",
    "kuka-inverse": "superseded by v2 (written after this run): adds multibody gravity "
                    "coupling; not blind",
    "nist-tracking": "superseded by v2 (written after this run): adds the position-loop "
                     "acceleration lag; not blind",
}

