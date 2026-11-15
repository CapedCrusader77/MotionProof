# Virtual as-manufactured assemblies

A variant is one set of actual dimensions drawn from the tolerance distributions, together with
everything derived from it. Each derived quantity is labelled with the level that produced it.

| Level | Meaning | Available for |
|---|---|---|
| A | Solids are regenerated with the actual dimensions and measured with OpenCascade (diameters, hole-pattern shift, radial clearance, exact minimum distance, interference volume) | The parametric reference design |
| B | Features of imported CAD are modified | **Not implemented** |
| C | A documented reduced-order relation; geometry is not regenerated | Every model |

Level C relations:

* Fit clearance = bore − shaft (diametral); state clearance, line or interference; violation
  when interference exceeds the allowed value.
* Radial play = bearing internal clearance + positive fit clearances. The shaft is seated in a
  worst-case position: dropped by half the play and tilted by play ÷ bearing span.
* Gear-stage backlash and binding (see `gearbox-modelling.md`).
* Direct effects: a tolerance added to, set as, or scaling a joint parameter (backlash,
  efficiency, stiffness, friction, tilt, offset, zero offset, torque scale).

The viewer overlays the variant on the nominal assembly. Misalignments of a few micrometres are
invisible, so the overlay magnifies the pose deviation by a factor you choose; the factor is
shown in the legend. Regenerated diameters are reported as numbers, not drawn.
