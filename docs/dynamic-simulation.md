# Dynamic simulation

Engine: MuJoCo 3.14 for the rigid bodies, `implicitfast` integrator, default time step 0.5 ms.
Payload is added as a point mass at the end effector. Joint misalignment (tilt, offset) is
applied to the model geometry of the variant.

**Tasks:** point-to-point, joint reversal, static hold, repeated cycles, workspace sweep. Motion
between poses is a rest-to-rest quintic.

**Metrics:** end-effector error (final, max, mean, RMS) against the nominal design at the
commanded pose; angle error; tracking error; lost motion and direction-dependent error
(reversal); repeatability (cycles); backlash; radial play; torque utilisation (peak demand over
peak torque), RMS torque over continuous torque, speed ratio, saturated fraction; minimum mesh
backlash; fit clearance.

**Traces:** time, command, motor and output angle, velocity, acceleration, motor torque,
available torque, tracking error, end-effector error (about 400 points per run).

A run is `invalid` when the state is non-finite or MuJoCo reports unstable acceleration;
invalid runs are counted separately and never as passes.

Typical cost on the development laptop: about 0.05–0.1 s per reversal scenario.
