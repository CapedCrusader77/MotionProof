# Technical roadmap

Order reflects what would most increase trust in the results, not feature count.

| Step | Work | Done when |
|---|---|---|
| 1 | Real inputs: a Fusion-exported MJCF and a real STEP assembly through import, feature mapping and an experiment | Both run end to end; defects fixed with regression tests |
| 2 | Physical validation: firmware for the documented protocol on an ESP32 rig with input and output encoders; low-risk reversal sessions; calibration with a separate holdout | A validation report from real data exists; benchmark J has data |
| 3 | Real scan data: a scanned shaft and housing with independent caliper or CMM reference values | Measured diameters agree within the scanner's stated accuracy |
| 4 | Frontend verification: component tests for every screen; layout below 1100 px | Each screen has an automated interaction test |
| 5 | Type safety: clear the mypy backlog | `mypy --strict motionproof` is clean |
| 6 | Level B geometry: resize cylindrical features of imported STEP solids | Shaft and bore variation verified against measured dimensions |
| 7 | Adaptive sampling in many dimensions: sensitivity-driven input reduction, importance sampling | Benefit shown on the reference reversal problem, or the limitation documented with data |
| 8 | Drive-train detail: planet load sharing, per-tooth transmission error, harmonic-drive stage | Each has an analytic or published reference case |
| 9 | Challenge: costed shift variables, NSGA-II comparison | Better fronts at equal budget, or the screen kept |
| 10 | Fidelity 3 (contact, CalculiX) | Only with documented equations, assumptions and validation |

Not planned: cloud infrastructure, message queues, GPU simulation.
