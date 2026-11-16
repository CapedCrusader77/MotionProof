# MotionProof design system

Swiss-industrial technical workbench, restrained industrial brutalism. Dials: variance 5,
motion 3, density 7. Everything lives in `src/styles.css` (tokens and primitives) and
`src/components/ui.tsx` / `charts.tsx` (React primitives). Screens compose these; they do not
style themselves.

## Tokens

| Token | Light | Dark | Use |
|---|---|---|---|
| `--mp-background` | `#f2f2ee` | `#121413` | application ground |
| `--mp-surface` | `#ffffff` | `#1a1d1b` | panels, tables, inputs |
| `--mp-surface-muted` | `#ebebe6` | `#222623` | hover, active nav, panel foot |
| `--mp-surface-sunken` | `#e4e4de` | `#0e100f` | skeleton shimmer |
| `--mp-border` / `--mp-border-strong` | `#d6d7d0` / `#a9aca5` | `#2f3431` / `#4a514c` | hairlines / controls |
| `--mp-rule` | `#171918` | `#e9ebe6` | the strong rule under table headers |
| `--mp-foreground` / `-muted` / `-faint` | `#171918` / `#4f5551` / `#6a706b` | `#e9ebe6` / `#b0b6b0` / `#8d948e` | text; faint is ≥ 4.5:1 on surface |
| `--mp-accent` / `-hover` / `-weak` | `#c8402b` / `#a83321` / `#f6e3dd` | `#e5603f` / `#f07655` / `#3a221b` | brand vermilion: primary actions, active navigation, focus, the mark |
| `--mp-pass` | `#1d6b45` | `#5cc08a` | passed |
| `--mp-warn` | `#8a5a00` | `#e0ad4c` | warning, assumed |
| `--mp-fail` | `#a3201a` | `#f07f76` | failed (deeper crimson than the brand vermilion) |
| `--mp-info` | `#285a8c` | `#8bb5e3` | information |
| `--mp-unknown` | `#5c625e` | `#a3a9a4` | unknown, unavailable |
| `--mp-data` / `--mp-data-2` | `#34505f` / `#8a7a52` | `#8fb3c6` / `#cbb889` | chart data ink; never a status, never the brand colour |
| `--mp-viewport-top/bottom` | `#f7f7f4` | `#141716` | flat 3D viewport ground (no gradient) |
| `--mp-radius` / `-sm` | 3 px / 2 px | | all corners |
| `--mp-fast` / `--mp-med` | 120 ms / 200 ms, `cubic-bezier(0.2, 0, 0, 1)` | | hover / page, drawer, toast |

The legacy names (`--bg`, `--surface`, `--accent`, `--ok`, ...) alias these tokens so every
existing component follows them.

## Type

* **Geist Variable** (self-hosted via `@fontsource-variable/geist`): interface text and headings.
  Body 13.5 px, page title 20 px / 600, panel title 13–14 px / 600, sentence case.
* **IBM Plex Mono** 400/500/600 (self-hosted via `@fontsource/ibm-plex-mono`): measured values,
  identifiers and engineering metadata. Tabular numerals everywhere a number is shown
  (`font-variant-numeric: tabular-nums`).
* Sentence case everywhere: navigation groups, table headers, metric labels and status words
  are sans-serif. Monospace is used only where it helps reading: measured values, identifiers,
  counts and units in tables and inspectors.

## Status language

Status is colour **plus a glyph plus a word**, never colour alone. Badges (tinted, no outline,
sentence case) are reserved for states that need attention; inside dense tables status is a
coloured glyph followed by a plain word (`.evidence`, `.check-row`). Evidence levels use ■
specified, ● measured, ◐ estimated, ○ assumed. The brand vermilion is never used for a status.

## Primitives

| Primitive | Where | Notes |
|---|---|---|
| Shell | `App.tsx`, `.shell` | 212 px navigation (48 px collapsed; icon rail under 1100 px; drawer under 760 px), 44 px top bar |
| Navigation | `.nav`, `.nav-item`, `.nav-group` | groups per the product map; active item: surface fill, 2 px vermilion bar, accent icon |
| Top bar | `.topbar`, `.crumbs`, `.status-dot` | breadcrumb, model and experiment selectors, backend status, command palette, theme |
| Page header | `.page-head` | title, description, actions; a hairline below |
| Panel | `Panel`, `.panel` | 1 px border, 3 px radius, no shadow; head 38 px |
| Metric readout | `Stat`, `.stat` | mono label above, 22 px mono value, note below; grouped readouts share one frame (`.grid4`) |
| Engineering table | `table.grid` | sticky mono headers on a strong rule, right-aligned tabular numbers, row hover, selected row bar |
| Status | `Badge`, `Alert` | as above; alerts have a 3 px left bar |
| Tabs, steps | `Tabs`, `.steps` | underline / top bar in vermilion |
| Loading | `Skeleton` (used by `Load`) | holds layout, shimmer bars, `role="status"` label |
| Empty state | `Empty` | left-aligned title, one line of guidance, optional action |
| Chart | `charts.tsx` | data ink `--mp-data`, failures in `--mp-fail`, mono axis text |
| 3D viewport | `.viewport`, `Viewer` | gradient ground, grouped toolbar, refit on load |
| Toast, modal, command palette | existing components | pop shadow, 200 ms entry |

## Workspaces

Screens are built around their workflow, not one template.

* `.ws` (workbench, virtual assemblies, tolerances): fills the window under a thin header
  (`.ws-head`: title, model, inline controls, primary action). Sidebars (`.ws-side`) are docked
  and flush, separated by hairlines, not cards.
* Viewport (`Viewer`): docked toolbar along the top edge (fit; shaded, edges, wire; axes;
  x-ray; section; explode), status bar along the bottom edge, keyboard shortcuts (F, 1, 2, 3,
  A, X, S, Esc), refit on load and on isolation, neutral materials, selection as a faint
  accent tint plus accent edges.
* Inspector: tabs where a selection has distinct aspects (properties and readiness; validity,
  geometry and deviations), sections separated by rules, numbers rounded to their engineering
  precision (floating-point noise below 1e-9 of the scale shown as 0).

## Motion

120–200 ms, one easing curve. Used for navigation width and drawer, hover fills, page entry
(3 px rise), toasts and modals. No scroll effects, no ambient motion. `prefers-reduced-motion`
reduces every transition and animation to effectively zero.

## Accessibility

Skip link as the first Tab stop; visible 2 px vermilion focus ring; the navigation drawer's
button reports `aria-expanded`; loading and backend status are `role="status"`; status never
relies on colour; text contrast at least 4.5:1 in both themes for body and metadata text.
