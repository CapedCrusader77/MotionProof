# Engineering limitations

MotionProof is not a substitute for engineering approval. It does not certify structural
strength, fatigue life, thermal behaviour, material failure, manufacturability or real-world
reliability.

* Rigid multibody dynamics with a reduced-order drive train. No gear-tooth contact, no bearing
  contact, no structural deformation, no thermal effects, no wear.
* Backlash is a lost-motion relation from centre distance and clearance. Tooth profile, pitch
  and lead errors are not modelled; load sharing between planets is ignored.
* Radial play uses a fixed worst-case seating of the shaft.
* Trapped friction windup is under-estimated (soft friction constraint).
* The motor is an ideal position-controlled torque source within its torque-speed limit; no
  electrical, step-loss or thermal model.
* Geometric tolerances are scalar deviations, not full GD&T zones.
* Level A geometry regeneration exists only for the parametric reference design.
* Only revolute joints can be driven; only payload and speed scale vary as operating conditions.
* Worst-case results are the worst found within a search budget.
* Nothing has been validated against physical measurements. The reference design is synthetic
  and its numbers are assumptions.
* Fusion 360 integration has not been tested.
