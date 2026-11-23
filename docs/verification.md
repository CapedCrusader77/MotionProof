# Verification and honesty

What has been checked, how, and what has not.

* **Benchmarks.** `uv run python benchmarks/publish.py` regenerates the inputs and raw data,
  runs the suite, and re-checks 57 quantities with
  [`reference_calculations.py`](../benchmarks/reference_calculations.py), which uses only NumPy
  and SciPy and never imports MotionProof. Published outputs are reproducible byte for byte.
  Results: [`BENCHMARK_RESULTS.md`](../BENCHMARK_RESULTS.md).
* **Tests.** 280 backend tests, including analytic physics checks, an API contract that no route
  answers 5xx to bad input, account isolation, and 14 Playwright end-to-end tests against the
  real backend.
* **External experimental validation.** Public measurements of other robots (Stäubli TX2-40,
  Unitree H1, SO-101, KUKA KR300, UR5) test MotionProof's model components on unseen trials,
  under acceptance criteria committed before the runs. Current result: 1 PASS, 4 FAIL, 1
  INSUFFICIENT DATA, all reported in
  [`EXTERNAL_VALIDATION_RESULTS.md`](../EXTERNAL_VALIDATION_RESULTS.md). This is not validation of
  the reference gearbox. See [`external-validation.md`](external-validation.md).
* **Honesty.** [`development-status.md`](development-status.md) lists what is verified, what is
  not and the known defects. No physical measurement has been made yet. The rig procedure is in
  [`rig-build-and-test.md`](rig-build-and-test.md).
