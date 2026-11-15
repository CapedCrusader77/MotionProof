# Research review

Status 2026-11-15. This is a working review, not a systematic literature survey.

## The two papers named in the brief could not be read

| DOI | Result |
|---|---|
| 10.1016/j.rineng.2026.111597 (harmonic gear backlash, multi-source error sensitivity, force-thermal effect) | The DOI redirected to a publisher page that returned only a placeholder. Title, authors, method and findings were **not retrieved**. |
| 10.1007/s00170-026-17862-8 (simultaneous dimension and tolerance design of a manipulator, cost and positioning-accuracy reliability) | The DOI redirected to a publisher sign-in page. Content was **not retrieved**. |

Nothing in MotionProof is based on these papers, and nothing is asserted about their content
beyond the titles given in the brief. They should be read by a person with access before any
comparison is written.

## Established methods used, with their standard references

| Area | Reference | How it is used here |
|---|---|---|
| Fits and limits | ISO 286-1/-2 | Limit analysis of shaft/bore fits (clearance, transition, interference) |
| Geometric tolerancing | ASME Y14.5 / ISO 1101 | Vocabulary only. Position, runout and perpendicularity are propagated as scalar deviations; full zone semantics are **not** implemented |
| Gear accuracy and backlash | ISO 1328 (gear accuracy), ISO/TR 10064-2 (centre distance and backlash); standard involute relation `Δj = 2·tan(α)·Δa` | Centre-distance deviation to mesh backlash |
| Tolerance analysis | Chase & Parkinson, "A survey of research in the application of tolerance analysis to the design of mechanical assemblies", Research in Engineering Design, 1991 | Worst-case and RSS stacks, Monte Carlo propagation |
| Backlash in control | Nordin & Gutman, "Controlling mechanical systems with backlash — a survey", Automatica, 2002 | Dead-band with shaft stiffness and damping |
| Multibody simulation | Todorov, Erez & Tassa, "MuJoCo: a physics engine for model-based control", IROS 2012 | Rigid-body dynamics, constraint-based friction |
| Latin hypercube sampling | McKay, Beckman & Conover, Technometrics, 1979 | Stratified designs |
| Binomial interval | Wilson, JASA, 1927 | Pass-fraction intervals for independent draws |
| Global sensitivity | Saltelli et al., "Global Sensitivity Analysis: The Primer", Wiley, 2008 | Sobol indices (SciPy implementation) |
| Differential evolution | Storn & Price, Journal of Global Optimization, 1997 | Worst-case search (SciPy implementation) |
| Multi-objective optimisation | Deb et al., "A fast and elitist multiobjective genetic algorithm: NSGA-II", IEEE TEC, 2002 | **Not implemented.** Tolerance allocation uses a Latin-hypercube screen with non-dominated filtering |

## Research themes relevant to the roadmap (not yet reviewed in depth)

Manipulator tolerance allocation with reliability constraints; manufacturing variation and load
sharing in planetary gearboxes; harmonic-drive backlash and kinematic error; multi-source
geometric error propagation; gear transmission error and mesh stiffness; bearing clearance in
joints; experimental identification of joint friction and stiffness. No specific papers in
these themes have been read for this project yet, so no findings are attributed to them.

## Limitations of the present models against that literature

* Load sharing between planets is ignored; the first planet to engage defines the backlash.
* Tooth-profile, pitch and lead errors are lumped into a "design backlash" input.
* Mesh stiffness is a single constant; no time-varying stiffness or tooth contact.
* Bearing clearance seats the shaft in a fixed worst-case position; no bearing contact model.
* No thermal effects.

## Unresolved research questions

1. How well does the planetary lost-motion relation predict measured backlash of real small
   gearboxes? No measurement has been compared yet.
2. Which reduced-order parameters are identifiable from the signals a low-cost test rig can
   record (output angle, motor angle, current)?
3. Can feature-level variation be applied reliably to imported STEP geometry (Level B) without
   the original feature history?
4. Does the integrated tolerance-to-dynamics workflow add information beyond a static stack-up
   plus a nominal dynamic simulation? This needs a controlled comparison on real hardware.
