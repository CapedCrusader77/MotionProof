# Redesign changelog

## 2026-11-16, restraint pass and the three gate screens

* System: removed uppercase mono labels from tables, navigation, metrics, badges and section
  headings; monospace now only for values and identifiers. Flat viewport ground. Smaller page
  titles inside workspaces.
* Viewer: shaded, shaded with edges and wireframe modes; keyboard shortcuts; docked toolbar
  and status bar; neutral materials and even lighting in both themes; refit on isolation;
  selection tint with accent edges.
* Assembly workbench: viewport-first workspace; flush component tree with counts and hover
  actions; joint sliders; inspector with Properties and Readiness tabs; assembly summary with
  total mass; inertia and centre of mass free of floating-point noise.
* Tolerances: full-height engineering table with a per-row distribution strip drawn from the
  backend's density curve and limits; evidence as glyph and word; findings, fits and
  correlations in a bottom dock; inspector leads with the distribution against LSL and USL,
  statistics, then specification, distribution model, provenance, correlations and the mapped
  feature; Component column hidden below 1500 px.
* Virtual assemblies: generation controls in the header; variant list with set summary;
  Nominal / Variant / Overlay comparison; inspector tabs Validity (violations, fits, gear
  meshes), Geometry (Level A measurements, interfaces, changed components) and Deviations
  (each value placed inside its tolerance zone).
* Favicon added (missing file caused a 404 on every page).
* E2E: 13 tests, adding workbench select, isolate and keyboard shading; tolerance inspector and
  fits dock; virtual assembly generation, overlay and deviations.

## 2026-11-16, stages 1, 2, 8 and 9 (system and shell)

* New design system in `src/styles.css`: Swiss-industrial tokens for light and dark, brand
  vermilion separate from status colours, data ink for charts, 3 px radius, 120–200 ms motion,
  reduced-motion support. All existing class names kept, so every screen follows.
* Self-hosted fonts: Geist Variable (interface) and IBM Plex Mono (values, metadata) via
  `@fontsource` packages bundled by Vite; no runtime Google Fonts.
* Status: badges carry a glyph and a word (✓ ✕ ! i), never colour alone.
* Shell: navigation groups in the product order (Evidence: external validation, model trust,
  reports, benchmarks), icon rail under 1100 px, drawer with a menu button and scrim under
  760 px; top bar with backend status (`role="status"`), selectors without fixed widths; skip
  link; focusable main region.
* Loading: `Skeleton` replaces the centred spinner (layout holds, status announced).
* Empty states: left-aligned title and guidance.
* Tables: sticky mono headers on a strong rule, tabular numbers, wrapping description columns.
* Metric readouts: mono labels above 22 px mono values; four-up readouts share one frame.
* Charts: data in neutral ink, failures in the failure colour (robustness histograms,
  sensitivity bars, process density).
* 3D viewport: gradient ground, grouped toolbar, refit once meshes and pose have loaded.
* Phone layouts: stacked splits, one-column forms (inline desktop column counts overridden),
  projects list and detail stacked.
* External validation: superseded protocols removed from the dataset row (still listed under
  recorded runs); header action runs the current X1 protocol.
* Tests: Playwright adds phone drawer navigation, skip link and backend status, and external
  validation datasets with citation (10 tests). `scripts/capture_screens.mjs` captures every
  screen at any size and theme and reports overflow and page errors.
