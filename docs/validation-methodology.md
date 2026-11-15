# Validation methodology

Three kinds of evidence, kept separate:

1. **Numerical verification** (done): each method is tested against a closed-form value or an
   independent calculation. Examples: gravity torque `m·g·L`; static deflection `b/2 + τ/k`;
   OpenCascade-measured radial gap equals `(D − d)/2`; CAD-kernel mass properties against
   Trimesh integration of the exported mesh; Wilson interval against a textbook value; Sobol
   indices of an additive function; correlated sampling against the requested coefficient.
2. **Reproducibility** (done): identical runs give identical bits; resumed experiments equal
   uninterrupted ones; replay matches stored metrics to 1e-9 relative.
3. **Physical validation** (not done): comparison with measurements of real hardware. Until
   this exists, every result is a model prediction.

A model that compiles is not evidence that its physics are right, and a model that fits its
calibration data is not validated.
