# Competitor gap analysis

Reviewed 2026-11-15. Sources are the public project pages listed below, read on that date.
Statements about other projects describe what those pages say; "not mentioned" means the page
did not mention it, not that the capability is absent.

## What already exists (and is not claimed as new here)

Monte Carlo simulation, worst-case and RSS tolerance stacks, Cp/Cpk, CAD interference checks,
rigid-body robot dynamics, backlash dead-band models, rank-correlation and Sobol sensitivity,
Wilson intervals, differential evolution and Pareto filtering are all established methods.
MotionProof uses them; it does not invent them.

## Closest projects

| Project | What it does (from its page) | Tolerances | Dynamics | Backlash | Calibration to measurements |
|---|---|---|---|---|---|
| [CADCLAW](https://github.com/sunnyday-technologies/CADCLAW) (MIT) | Places authored STEP parts by connector frames and datum chains (CadQuery/OCCT) and runs gates: inventory, interference, dimensional, structural, **tolerance** ("worst-case, RSS, Monte Carlo tolerance stacking with Cpk and variance decomposition"), BOM audit | Yes, geometric stack-up | Not mentioned | Not mentioned | Not mentioned |
| [OmniSim](https://github.com/omnilink-tech/omnisim) (Apache-2.0) | Robot and machine-twin simulator for agents (Newton / MuJoCo), URDF and STEP input, ROS 2, MCP tools | Not mentioned (reports a simulated CNC wall "within 0.007 mm" of an ideal machine) | Yes | Not mentioned | Page states "No twin has been validated against its real machine" |
| [cad-to-urdf](https://github.com/arugoa/cad-to-urdf) (MIT) | Converts CAD assemblies to URDF/SRDF, MJCF, USD and other simulator formats, with convex decomposition and sim-to-sim checks | Not mentioned | Export target only | Not mentioned | Not mentioned (compares simulators with each other) |
| [ACDC4Robot](https://github.com/ACDC4Robot/Fusion360) (MIT) | Fusion 360 add-in exporting URDF, SDFormat and MJCF; rigid, revolute and slider joints | Not mentioned | Export target only | Not mentioned | Not mentioned |
| [Fusion2Mujoco](https://github.com/jgillick/Fusion2Mujoco) (MIT) | Fusion 360 add-in exporting MJCF; rigid, revolute and slider joints, CoACD collision hulls | Not mentioned | Export target only | Not mentioned | Not mentioned |
| [MoveIt 2](https://github.com/moveit/moveit2) (BSD-3) | ROS 2 manipulation platform: planning, servo, perception | Not mentioned | Planning, not tolerance studies | Not mentioned | Not mentioned |
| [OMPL](https://github.com/ompl/ompl) | Sampling-based motion-planning library | Not mentioned | Not applicable | Not mentioned | Not mentioned |

## Reading of the landscape

* **Tolerance stacking on CAD geometry is covered.** CADCLAW is the closest project: it already
  does worst-case, RSS and Monte Carlo stacks with Cpk on STEP assemblies. MotionProof should not
  compete on static stack-up breadth, PMI handling or BOM auditing.
* **CAD-to-simulator conversion is covered** by cad-to-urdf, ACDC4Robot and Fusion2Mujoco. This
  is why MotionProof imports URDF/MJCF and does **not** ship its own Fusion exporter. The
  recommended Fusion path is: export with ACDC4Robot or Fusion2Mujoco, then import the MJCF.
  That path has **not** been tested here with a real Fusion assembly.
* **Motion planning is covered** by MoveIt 2 and OMPL and is out of scope.
* None of the reviewed pages describes carrying a sampled manufacturing variant through a
  drive-train model (backlash, stiffness, friction, motor limits) into task-level dynamic
  metrics, nor fitting such a model to measurements with a holdout assessment.

## Proposed differentiators and the evidence for each

| Differentiator | Implemented evidence in this repository | Caveat |
|---|---|---|
| Tolerance values drive physical drive-train parameters: centre distance, pin position and bearing clearance become backlash, mesh binding, radial play and axis tilt | `motionproof/transmissions/gears.py`, `manufacturing/variants.py`; unit tests of the relations | Reduced-order relations, not tooth contact |
| The same sampled variant regenerates real solids and is measured with the CAD kernel | `reference/nema17_arm.py::measure_variant_geometry`; tests compare OpenCascade measurements with the sampled values | Only for the parametric reference design (Level A); imported STEP is not regenerated |
| Task-level dynamic metrics per variant (lost motion, positioning error, torque utilisation) | `simulation/engine.py`; 14 analytic physics tests | Fidelity 2 only |
| Statistics matched to the sampling design | `statistics/robustness.py`; tests | — |
| Optimiser results are always re-confirmed by a fresh simulation; failures can be minimised | `optimisation/worst_case.py`; end-to-end test | Worst found within a budget, not a proven global worst case |
| Calibration with separate holdout and identifiability warnings | `calibration/fit.py`; synthetic recovery tests | Verified on synthetic recordings only; no physical data yet |
| Immutable experiment snapshots and exact replay | `experiments/runner.py`; resume and replay tests | — |

## What is not established

No claim of novelty or of a research gap is made. The comparison rests on eight project pages
read once; it is not a systematic survey, and commercial tolerance-analysis and multibody
packages were not reviewed. Whether the integrated workflow is new in the literature is an
open question (see `RESEARCH_REVIEW.md`).
