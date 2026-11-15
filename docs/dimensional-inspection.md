# Dimensional inspection

`motionproof/scans/inspection.py`. These are fitted-geometry measurements, not a
standards-conformant GD&T inspection: no tolerance-zone construction, no material conditions,
no measurement-system analysis.

* **Deviation**: signed distance along the nominal surface normal (positive = outside the
  material) for every scan point; mean, standard deviation, RMS, min, max, percentiles,
  fraction within a symmetric limit. Nominal surface that no scan point reaches is reported as
  *missing coverage*, never as zero deviation.
* **Cylinder**: least-squares fit (axis direction, axis point, radius) of the points near a
  nominal cylinder; reports diameter, its standard error, RMS, points and the covered arc. Less
  than 120 degrees of arc is flagged as poorly constrained.
* **Axis offset**: eccentricity and tilt of a fitted axis relative to a datum axis.
* **Centre distance** between two fitted axes.
* **Flatness (approximate)**: range of residuals about a least-squares plane.

Accuracy demonstrated on SYNTHETIC data: 30 um diameter change on an 8 mm shaft recovered within
2 um with 5 um noise and an unknown pose.
