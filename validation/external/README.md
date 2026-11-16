# Published external validation records

Copies of the run records produced by `motionproof external benchmark` and the import
manifests (source URLs, published and computed checksums, retrieval times) of the datasets
they used. The raw datasets themselves are not redistributed here; import them with
`motionproof external import <dataset>` and the checksums in `manifests/` will be verified.

* `runs/VALIDATION_NNN/record.json`: protocol, status, trial IDs, parameters, metrics,
  transformations, evidence, checksums of the files used, versions, reproduce command.
* `runs/VALIDATION_NNN/report.md` and `plot*.png`: the human-readable report.

Summary: `EXTERNAL_VALIDATION_RESULTS.md` in the repository root.
