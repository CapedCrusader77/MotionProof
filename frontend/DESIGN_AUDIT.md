# MotionProof frontend design audit

Audited 2026-11-16 against the running application (backend on a seeded workspace: reference
design, a 200-scenario Monte Carlo experiment, external validation runs). Screenshots of all 29
screens were taken at 1440 × 900 (light) and of four screens at 390 × 844 with
`frontend/scripts/capture_screens.mjs`. No page errors were raised on any screen.

Reading this as: a complete redesign of a high-density B2B mechanical engineering and robotics
application for mechanical engineers, robotics engineers and research users, using a
Swiss-industrial technical workbench language with restrained industrial brutalism.
Dials: variance 5, motion 3, density 7.

## Note on the requested skills

The brief names two skills, `redesign-existing-projects` and `industrial-brutalist-ui`, from
github.com/Leonxlnx/taste-skill. Neither is installed, and the repository's tree contains only
`skills/taste-skill/SKILL.md`, which builds marketing websites (hero dealing, photographs, a
finish gate for landing pages). The brief rules out a landing-page treatment, so that skill's
scripts were not used; its general principles (one system, real product UI, equal edges, quiet
purposeful motion, no slop copy) were kept. The design rules below come from the brief.

## Architecture (what makes a system-wide redesign possible)

* React 19, TypeScript, Vite, Zustand, Recharts, three.js through React Three Fiber and Drei,
  lucide-react icons (one family, kept).
* One stylesheet, `src/styles.css` (173 lines), built on CSS custom properties, with
  `[data-theme="dark"]` overrides. Every screen uses the shared primitives in
  `components/ui.tsx` (Panel, Stat, Badge, Alert, Empty, Tabs, Load, Field, Num, Modal) and
  `components/charts.tsx` (Lines, Histogram, HBars, Points). Changing tokens and primitives
  therefore changes all 29 screens consistently.
* State: one small Zustand store (route, project, model, experiment, theme, nav collapse),
  persisted to localStorage. Routing is hash based.

## Findings

| Area | Finding | Severity |
|---|---|---|
| Identity | Generic: Segoe UI at 13 px, corporate blue `#1f5fa8` accent, a circle-in-circle mark. Nothing says engineering instrument. | high |
| Typography | One size for almost everything (13 px body, 16 px h1, 13 px h2); h3 is grey uppercase with letter spacing, used as a section label everywhere. Numbers use the same proportional face as prose; tabular numerals only in some `.num` cells. | high |
| Hierarchy | Page title, panel titles and table headers have nearly the same weight; the primary action is the only strong element. | medium |
| Navigation | Group labels are 10.5 px uppercase faint grey; the active state is a pale blue fill. 29 items with no grouping affordance beyond the label. Collapse works. | medium |
| Top bar | Breadcrumb truncates mid-word at 1440 ("0-0.5 kg payloa"); model and experiment selects are fixed 210 px and clip their content. No backend status indicator on the bar (health is read but not shown prominently). | medium |
| Cards | Empty states are full panels with a centred icon (as-built: four empty panels side by side; hardware: a large empty right pane). Empty space dominates first use. | medium |
| Loading | Tolerances, robustness, sensitivity, model trust and reports show a centred spinner on an otherwise empty page for over a second; no skeleton, the layout jumps when data arrive. | medium |
| Tables | `table.grid` is consistent and dense, but headers are not sticky inside long panels, units sit in the value cell, and long text wraps unevenly (external datasets table: the System column wraps into 8 lines). | medium |
| 3D viewport | The workbench viewport leaves the model small and off-centre until Fit is pressed; at capture time only the axes were visible. The grid and background are flat grey. | high |
| Charts | Recharts with token colours; axis labels are small; series colours reuse the accent (blue) for "measured" in some screens and for "model" in others. | low |
| Contrast | Faint text `#8a94a3` on white is 3.0:1 (fails WCAG AA for body text); used for metadata and group labels. Dark theme faint `#717c8c` on `#1c2129` is 3.6:1. | high |
| Mobile (390 px) | Two-column layouts (`.split`, projects list + detail) do not stack: the project detail column is squeezed to about 30 px. The top-bar selects collapse to empty boxes. The 46 px icon rail stays permanently, wasting width. | high |
| Laptop (1366 × 768) | Three-column `.split` (250 / 1fr / 300) leaves a narrow centre for the 3D views. | medium |
| Interaction feedback | Hover states exist on nav and list items; buttons have no pressed state; focus rings are browser defaults and invisible on some controls. | medium |
| Status language | Status badges are coloured text only (pass and fail differ only by colour plus wording; acceptable, but icons would help scanning). External validation lacks PARTIAL and INVALID PROTOCOL treatments for superseded runs. | medium |
| Motion | None besides the spinner. Acceptable for the dial (3), but view changes are abrupt. | low |

No fabricated data was found: every screen reads the backend, and unavailable features (local
AI, L3 fidelity, hardware without a device) say so.

## Screens

Per-screen before state, change and verification are recorded in `SCREEN_AUDIT.md`.
