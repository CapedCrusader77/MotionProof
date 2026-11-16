# Redesign roadmap

Staged as the brief asks. "Done" means implemented, built, type-checked, exercised in Playwright
and captured on all 29 screens at 1440 × 900 (light and dark) and 390 × 844.

| Stage | Scope | State |
|---|---|---|
| 1. Foundation | audit, tokens, light and dark themes, self-hosted Geist and IBM Plex Mono, status language, chart ink, radius, motion, contrast | **Done** |
| 2. Shell | navigation (groups per the product map, collapsible, icon rail, phone drawer), top bar (breadcrumbs, selectors, backend status, palette, theme), skip link, page header, skeleton loading, empty states | **Done** |
| 3. 3D workbench | workbench and virtual assemblies rebuilt as viewport-first workspaces; shading modes, shortcuts, docked toolbar and status bar | **Gate passed** at 1920×1080 and 1366×768, light and dark. Not done: measure tool, side-by-side linked cameras, as-built and features screens in the new workspace layout |
| 4. Manufacturing and configuration | tolerances, process batches, mechanical model, hardware, calibration | **Tolerances rebuilt (gate passed).** Others system-level only. Not done: drive-train schematic from gear stages, instrument-style hardware layout |
| 5. Experimentation | builder, monitor, adaptive | **System-level only**. Not done: wizard progress rail with inline validation summary |
| 6. Reliability and analysis | robustness, sensitivity, investigation, worst case, workspace, degradation, fidelity | **System-level only**; robustness and sensitivity charts now use neutral data ink with failing bins in the failure colour |
| 7. Optimisation and evidence | challenge, optimisation, comparison, external validation, trust, reports, benchmarks, settings | **System-level only**, plus external validation hides superseded protocols from the dataset row (they stay in the run list). Not done: PARTIAL and INVALID PROTOCOL status variants |
| 8. Polish | micro-interactions, loading, empty, error, responsive, accessibility | **Done for shared primitives** (hover, press, focus ring, page entry, drawer, reduced motion, skip link, status roles) |
| 9. Verification | Playwright, build, type check, backend regression | **Done**: 10 E2E tests, typecheck, build, backend suite |

## Next, in order

1. Apply the gate approach to the remaining screens in this order: robustness, external
   validation, engineering challenge, hardware testing, as-built inspection, features.
2. 3D: measure tool; linked-camera side-by-side comparison.
3. Mechanical model: a drive-train schematic (motor, gearbox stages, joint) bound to the form.
4. Experiment builder: a step rail with per-step validation and a live configuration summary.
5. External validation: PARTIAL (some parts pass) and INVALID PROTOCOL (superseded comparison)
   status variants derived from the run records.
6. Tables: column visibility, density toggle and sorting as a shared `DataTable` primitive.
