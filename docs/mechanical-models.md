# Mechanical models

A model file (`model.yaml`) declares the source geometry and dynamics, features, datums,
tolerances, correlations, fits, radial supports, gear stages, drives, held joints, effects, the
end effector and simulation settings. `motionproof model validate` checks it.

| Fidelity | Contents | Status |
|---|---|---|
| F1 geometry and kinematics | Transforms, dimensional variation, fits, clearance, interference | Implemented |
| F2 reduced-order dynamics | Rigid bodies, motor limit, gearbox ratio, backlash, stiffness, efficiency, friction, payload | Implemented |
| F3 contact and compliance | Gear mesh, bearing contact, elastic deformation | Not implemented |
| F4 structural and thermal | FEA coupling | Not implemented |

Every result carries the fidelity that produced it. Only revolute joints can be driven. Joints
listed under `held_joints` are locked at a fixed angle (an ideal servo).

Motor data are user input: continuous and peak torque, maximum speed, optional torque-speed
curve, rotor inertia, friction torque, source and confidence. MotionProof supplies no
manufacturer data; the reference design's motor values are labelled assumed.
