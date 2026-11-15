# Validation limitations

* **No physical validation.** No real scanner data, hardware measurements or production data
  have been used. Scans, batches, wear data and device sessions in tests and examples are
  synthetic and labelled.
* **Fidelity.** L3 and L4 are not implemented beyond the software path. No contact, structural,
  thermal or fatigue result is produced.
* **Inspection.** Fitted-geometry measurements, not GD&T conformance; registration quality is
  checked but no measurement-system analysis is done.
* **Process models** are statistical and only as good as the stated variance sources.
* **Adaptive sampling** helps on smooth, low-dimensional limit states (benchmark K); on the
  28-input reference reversal the surrogate was not predictive.
* **Engineering Challenge**: worst found within the search budget; shifts are cost-free unless
  costed; reliability claims rest on the exact binomial bound and the stated distributions.
* **Degradation**: projections of user-chosen progressions; no wear physics.
* **Root cause**: causal statements are within the model only.
* **Hardware safety**: software limits only; not a safety system.
* Fusion 360 integration remains untested.
