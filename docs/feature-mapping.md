# Feature mapping

A feature is a named geometric element that tolerances refer to: shaft, bore, bearing seat,
mounting hole, datum plane, datum axis, mating face, joint interface, gear interface.

Each feature stores its component, type, nominal values with a unit, an optional datum, an
optional mating feature, a geometry reference, its source and a status (`confirmed` or
`suggested`).

For STEP imports MotionProof lists the cylindrical faces it finds, grouped by axis and radius,
with measured diameter and length and whether the surface is external or internal. These are
suggestions: STEP has no feature history, so a detected cylinder may be a shaft, a pin, a fillet
or a hole. Press Use, check the values, and save to confirm. Features can always be registered
by hand. Plane and non-cylindrical features are not suggested automatically in the interface.
