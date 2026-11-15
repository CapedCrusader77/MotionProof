# Datum model

A datum names a registered feature as a reference: `{id: A, feature: housing_axis, type: axis}`.
Features and tolerances point to a datum by id; the schema rejects references to datums or
features that do not exist.

What datums do today: they document which reference a tolerance is measured from, and the
validation panel warns about geometric tolerances that have none.

What they do not do: MotionProof does not build datum reference frames, apply material
modifiers, or check ASME Y14.5 / ISO 1101 conformance. Geometric tolerances are propagated as
scalar deviations (see `tolerance-modelling.md`).
