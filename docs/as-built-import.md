# As-built import

Purpose: compare a measured part with its CAD geometry and feed approved measurements into the
mechanical model.

Workflow (screen *As-built inspection*, API `/scans/*`, CLI `motionproof scan`):

1. **Import** a point cloud and state its length unit. Without a unit the scan is stored but
   cannot be compared with CAD. Scanner and capture date are recorded when given.
2. **Align** it to a nominal component mesh (see `geometric-registration.md`).
3. **Analyse**: deviation statistics and heatmap, plus fitted measurements of registered
   cylindrical features (see `dimensional-inspection.md`).
4. **Review**: each measured value is `pending` until approved or rejected. Values from an
   alignment that failed its quality checks cannot be approved.
5. **As-built model**: approved values replace the sampled tolerance values in a variant.
   This is a reduced-order representation: fits, radial play, misalignment and backlash are
   recomputed from the measured dimensions; the CAD mesh is not modified.

Each measurement stores value, unit, standard error, extraction method, scan id, registration
id, feature id, the tolerance it replaces and its status.

The interface shows three states side by side: nominal CAD, the virtual as-manufactured state
(the tolerance limits and distributions of that component; no modified mesh is drawn) and the
measured as-built scan coloured by deviation. The nominal and as-built 3D views share one
camera.

Verified only with SYNTHETIC scans of known geometry (tests/integration/test_scans.py,
test_advanced_api.py, benchmark A). No real scanner data have been processed.
