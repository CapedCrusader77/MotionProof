# Benchmark methodology

`motionproof/benchmarks/suite.py`; run with `motionproof benchmark run [--write
BENCHMARK_RESULTS.md]`, the Benchmarks screen or `POST /api/v1/benchmarks/run`.

Each benchmark states purpose, formulation, fidelity, and for every check the expected value
(closed form or an independent method), the actual value, the error and the acceptance
criterion. A crashing benchmark is reported as ERROR, not skipped. Synthetic data are flagged.
Benchmark J (hardware) reports NOT RUN because no measurements exist.

Benchmarks: A fits and scan recovery, B planetary gearbox, C two-link kinematics, D reversal and
replay, E misalignment, F loaded arm, G process variation, H workspace map, I degradation,
J hardware, K adaptive versus random, L multi-fidelity, M Engineering Challenge, N root cause.
