# Verification and honesty

What has been checked, how, and what has not.

* **Benchmarks.** `uv run python benchmarks/publish.py` regenerates the inputs and raw data,
  runs the suite, and re-checks 57 quantities with
  [`reference_calculations.py`](../benchmarks/reference_calculations.py), which uses only NumPy
  and SciPy and never imports MotionProof. Published outputs are reproducible byte for byte.
  Results: [`BENCHMARK_RESULTS.md`](../BENCHMARK_RESULTS.md).
* **Tests.** 315 backend tests, including analytic physics checks, an API contract that no route
  answers 5xx to bad input, account isolation, and 14 Playwright end-to-end tests against the
  real backend.
* **External experimental validation.** Public measurements of other robots (Stäubli TX2-40,
  Unitree H1, SO-101, KUKA KR300, UR5) test MotionProof's model components on unseen trials,
  under acceptance criteria committed before the runs. Current result: 5 PASS (X3; X10, a
  blind test of X3 on three more joints; X1 and X4 as non-blind revisions that each add one
  physical term after the first version failed; X8, a blind test of the X1 revision on an
  unseen axis), 3 FAIL (X2; X5, also revised, not blind; X9, a blind test of the X4 revision on
  the UR5, J6 only),
  1 INSUFFICIENT DATA; and X7, a non-blind check of the planetary backlash model against a
  published 3D-printed gearbox: FAIL. All reported in
  [`EXTERNAL_VALIDATION_RESULTS.md`](../EXTERNAL_VALIDATION_RESULTS.md). This is not validation of
  the reference gearbox. See [`external-validation.md`](external-validation.md).
* **Honesty.** [`development-status.md`](development-status.md) lists what is verified, what is
  not and the known defects. No physical measurement has been made yet. The rig procedure is in
  [`rig-build-and-test.md`](rig-build-and-test.md).
