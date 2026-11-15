# Gearbox modelling

**Ratio.** Planetary stage, sun input, carrier output, ring fixed: `i = 1 + z_ring / z_sun`.
The reference design uses 12/21/54 and 12/24/60 teeth: 5.5 × 6 = 33. That is the target ratio
realised by chosen tooth counts, not a measurement of any gearbox.

**Backlash from geometry (reduced order, not tooth contact).** For an involute mesh, a change
`Δa` in operating centre distance changes circumferential backlash by `2·tan(α)·Δa` (external
mesh: more distance, more backlash; internal mesh: less).

With sun and ring held, a planet centre can travel tangentially by `d` until both meshes close:
`2d = j_sun-planet + j_planet-ring`. Diametral clearance `c` in the planet bearing adds directly:

```
d_k   = (j_sp,k + j_pr,k) / 2 + c
stage backlash angle = min_k(d_k) / a      (a = pin circle radius)
```

A pin displaced radially loosens one mesh and tightens the other by the same amount, so it does
not change lost motion but can make a mesh **bind**; binding is reported when a mesh backlash
goes negative anywhere in a revolution (sun runout and ring offset sweep past each planet).

Total output backlash = each stage's angle divided by the ratio downstream of it, plus the
gearbox's own additional backlash value.

**Transmission error.** Sun runout `e` produces a once-per-sun-revolution error of amplitude
`e / r_sun` at the sun, referred to the output through the ratio.

Assumptions: rigid teeth; load sharing ignored (the first planet to engage defines backlash);
tooth-thickness and profile errors lumped into the design-backlash input.
