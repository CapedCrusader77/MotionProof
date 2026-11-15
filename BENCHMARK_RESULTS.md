# Benchmark results

Generated 2026-11-15T11:06:43+00:00 by `uv run motionproof benchmark run` on Windows-11-10.0.26300-SP0, MotionProof 0.3.0, MuJoCo 3.14.0, NumPy 2.5.4.

Every number below comes from this run. Benchmarks marked synthetic use generated data with known ground truth; none of them is physical validation.

| ID | Benchmark | Status | Checks | Synthetic | Time (s) |
|---|---|---|---|---|---|
| A | Shaft and bearing fit; as-built scan recovery | **PASS** | 7/7 | yes | 5.29 |
| B | Two-stage planetary gearbox (NEMA 17 reference, 33:1) | **PASS** | 8/8 | yes | 0.09 |
| C | Two-link arm kinematics and gravity torque | **PASS** | 10/10 | yes | 0.02 |
| D | Joint reversal and replay | **PASS** | 7/7 | yes | 3.27 |
| E | Misaligned assembly | **PASS** | 5/5 | yes | 0.25 |
| F | Loaded arm: torque requirement and motor margin | **PASS** | 10/10 | yes | 0.31 |
| G | Hierarchical manufacturing variation | **PASS** | 6/6 | yes | 0.0 |
| H | Workspace reliability map | **PASS** | 3/3 | yes | 1.98 |
| I | Lifetime degradation | **PASS** | 2/2 | yes | 0.06 |
| J | Hardware measurements | **NOT RUN** | 0/0 | no | 0.0 |
| K | Adaptive versus random sampling | **PASS** | 2/2 | yes | 4.19 |
| L | Multi-fidelity agreement and sufficiency | **PASS** | 3/3 | yes | 0.1 |
| M | Engineering Challenge on an analytic case | **PASS** | 6/6 | yes | 22.97 |
| N | Root cause of a deliberate failure | **PASS** | 2/2 | yes | 3.14 |

## A. Shaft and bearing fit; as-built scan recovery

- Status: **PASS**
- Purpose: Fit limits, Monte Carlo clearance statistics, exact B-rep gap and diameter recovery from a scan, each against an independent value.
- Formulation: clearance = bore - shaft; var = var_bore + var_shaft (independent); radial gap = (D - d)/2 - offset
- Fidelity: F1 geometry

| Quantity | Expected | Actual | Error | Criterion | Result |
|---|---|---|---|---|---|
| min clearance (bore LSL - shaft USL) | -0.003 | -0.003 | 0 | |error| <= 1e-12 mm | pass |
| max clearance (bore USL - shaft LSL) | 0.014 | 0.014 | 0 | |error| <= 1e-12 mm | pass |
| clearance mean (Monte Carlo vs analytic) | 0.0055 | 0.00549714 | -2.85525e-06 | |error| <= 2e-05 mm | pass |
| clearance std (Monte Carlo vs RSS) | 0.00196047 | 0.00195642 | -4.05057e-06 | |error| <= 0.01 x expected | pass |
| exact B-rep radial gap with 10 um offset | 0.015 | 0.015 | 4.76424e-14 | |error| <= 1e-07 mm | pass |
| diameter recovered from SYNTHETIC noisy scan (unknown pose) | 8.03 | 8.03009 | 8.69494e-05 | |error| <= 0.002 mm | pass |
| registration accepted for inspection | - | RMS 0.0144 mm, 10 iterations | - | condition holds | pass |
- Reproduce: `uv run motionproof benchmark run fit`

## B. Two-stage planetary gearbox (NEMA 17 reference, 33:1)

- Status: **PASS**
- Purpose: Ratios, lost-motion relation, transmission error and the static torque path of the reference gearbox.
- Formulation: i = 1 + z_r/z_s; backlash = ((j_sp + j_pr)/2 + c)/a; TE = (e/2)/r_sun/i; static: tau_m = tau_out/N, defl = b/2 + tau/k
- Fidelity: F2 reduced order

| Quantity | Expected | Actual | Error | Criterion | Result |
|---|---|---|---|---|---|
| stage 1 ratio 1 + 54/12 | 5.5 | 5.5 | 0 | |error| <= 1e-12  | pass |
| stage 2 ratio 1 + 60/12 | 6 | 6 | 0 | |error| <= 1e-12  | pass |
| overall 33:1 from tooth counts | 33 | 33 | 0 | |error| <= 1e-12  | pass |
| stage 2 backlash ((0.04 + 0.04)/2 + 0.012) / 9 mm | 0.00577778 | 0.00577778 | 8.67362e-19 | |error| <= 1e-12 rad | pass |
| output backlash = s2 + s1 / 6 | 0.00682828 | 0.00682828 | 0 | |error| <= 1e-12 rad | pass |
| transmission error amplitude e / r_sun / 33 | 0.00010101 | 0.00010101 | 0 | |error| <= 1e-12 rad | pass |
| motor torque = output torque / 33 (eta does not act at rest) | 0.0102416 | 0.0102416 | -9.28066e-12 | |error| <= 0.01 x expected | pass |
| output deflection = b/2 + tau/k | 0.00363946 | 0.00363946 | -1.85775e-13 | |error| <= 0.01 x expected | pass |
- Note: Efficiency acts on transmitted power; at rest it does not change the motor torque in this model. The dynamic efficiency check is in tests/physics (mid-stroke torque).
- Reproduce: `uv run motionproof benchmark run gearbox`

## C. Two-link arm kinematics and gravity torque

- Status: **PASS**
- Purpose: Forward and inverse kinematics against closed form, gravity torque against the mass distribution.
- Formulation: x = l1 cos q1 + l2 cos(q1+q2); cos q2 = (r^2 - l1^2 - l2^2)/(2 l1 l2)
- Fidelity: kinematics

| Quantity | Expected | Actual | Error | Criterion | Result |
|---|---|---|---|---|---|
| FK error at q = (0.0, 0.0) | 0 | 0 | 0 | |error| <= 1e-09 m | pass |
| FK error at q = (0.7, 0.0) | 0 | 5.55112e-17 | 5.55112e-17 | |error| <= 1e-09 m | pass |
| FK error at q = (0.4, 1.1) | 0 | 6.20634e-17 | 6.20634e-17 | |error| <= 1e-09 m | pass |
| FK error at q = (-0.9, -0.5) | 0 | 1.00074e-16 | 1.00074e-16 | |error| <= 1e-09 m | pass |
| IK (damped least squares, SciPy) reaches the target | 0 | 1.93978e-10 | 1.93978e-10 | |error| <= 1e-09 m | pass |
| IK elbow angle vs law of cosines | 1.32843 | 1.32843 | -6.78896e-10 | |error| <= 1e-06 rad | pass |
| shoulder gravity torque = sum m g x_com | 0.337974 | 0.337974 | 0 | |error| <= 1e-09 x expected | pass |
| shoulder upper limit compiled from the model file | 3 | 3 | 0 | |error| <= 1e-09 rad | pass |
| pose inside the limit reachable, pose outside not | - | limit 3.0 rad | - | condition holds | pass |
| workspace outer radius | 0.35 | 0.35 | 0 | |error| <= 1e-09 m | pass |
- Note: IK is a SciPy least-squares solve over the model's own kinematics, done in this benchmark; MotionProof has no general IK module.
- Reproduce: `uv run motionproof benchmark run two_link`

## D. Joint reversal and replay

- Status: **PASS**
- Purpose: Dead-band lost motion on reversal and bit-exact replay.
- Formulation: no gravity: lost motion = b (friction windup relaxes, see limitations); tip error = L b
- Fidelity: F2 reduced order

| Quantity | Expected | Actual | Error | Criterion | Result |
|---|---|---|---|---|---|
| lost motion = b for b = 0.0 | 0 | 1.29684e-10 | 1.29684e-10 | |error| <= 2e-05 rad | pass |
| direction error at the tip = L b for b = 0.0 | 0 | 3.93576e-11 | 3.93576e-11 | |error| <= 6e-06 m | pass |
| lost motion = b for b = 0.005 | 0.005 | 0.00499774 | -2.25934e-06 | |error| <= 2e-05 rad | pass |
| direction error at the tip = L b for b = 0.005 | 0.0015 | 0.00149932 | -6.79361e-07 | |error| <= 6e-06 m | pass |
| lost motion = b for b = 0.012 | 0.012 | 0.0119976 | -2.37468e-06 | |error| <= 2e-05 rad | pass |
| direction error at the tip = L b for b = 0.012 | 0.0036 | 0.00359927 | -7.3399e-07 | |error| <= 6e-06 m | pass |
| replay reproduces every stored scenario exactly | - | 6/6 reproduced | - | condition holds | pass |
- Reproduce: `uv run motionproof benchmark run reversal`

## E. Misaligned assembly

- Status: **PASS**
- Purpose: A known offset, tilt and clearance change propagate to the expected tip error and joint misalignment.
- Formulation: tip error = offset; d(error)/d(tilt) = L; tilt = play / span
- Fidelity: F2 reduced order

| Quantity | Expected | Actual | Error | Criterion | Result |
|---|---|---|---|---|---|
| tip error from 0.05 mm joint offset | 5e-05 | 5e-05 | 0 | |error| <= 0.001 x expected | pass |
| tip error from 0.2 mm joint offset | 0.0002 | 0.0002 | 0 | |error| <= 0.001 x expected | pass |
| sensitivity d(tip error)/d(tilt) = arm length | 0.3 | 0.3 | -8.75e-08 | |error| <= 0.01 x expected | pass |
| radial play grows with seat clearance (6 um) | 6e-06 | 6e-06 | 2.27005e-19 | |error| <= 1e-12 m | pass |
| axis tilt from extra play = play / bearing span | 0.0004 | 0.0004 | 1.51246e-17 | |error| <= 1e-12 rad | pass |
- Reproduce: `uv run motionproof benchmark run misalignment`

## F. Loaded arm: torque requirement and motor margin

- Status: **PASS**
- Purpose: Payload torque, utilisation, deflection and overload behaviour.
- Formulation: tau = (m + mp) g L; tau_motor = tau / N; deflection = tau / k
- Fidelity: F2 reduced order

| Quantity | Expected | Actual | Error | Criterion | Result |
|---|---|---|---|---|---|
| motor torque with 0.0 kg payload = (m+mp) g L / N | 0.14715 | 0.14715 | -1.59312e-07 | |error| <= 0.005 x expected | pass |
| torque utilisation with 0.0 kg | 0.073575 | 0.0735749 | -7.96562e-08 | |error| <= 0.03 x expected | pass |
| tip error with 0.0 kg = L tau / k | 0.00044145 | 0.000441449 | -5.17766e-10 | |error| <= 0.01 x expected | pass |
| motor torque with 0.5 kg payload = (m+mp) g L / N | 0.220725 | 0.220724 | -5.37678e-07 | |error| <= 0.005 x expected | pass |
| torque utilisation with 0.5 kg | 0.110362 | 0.110362 | -2.68839e-07 | |error| <= 0.03 x expected | pass |
| tip error with 0.5 kg = L tau / k | 0.000662175 | 0.000662173 | -1.74745e-09 | |error| <= 0.01 x expected | pass |
| motor torque with 1.5 kg payload = (m+mp) g L / N | 0.367875 | 0.367873 | -2.48923e-06 | |error| <= 0.005 x expected | pass |
| torque utilisation with 1.5 kg | 0.183938 | 0.183936 | -1.24461e-06 | |error| <= 0.03 x expected | pass |
| tip error with 1.5 kg = L tau / k | 0.00110362 | 0.00110362 | -8.08998e-09 | |error| <= 0.01 x expected | pass |
| overload saturates the motor and loses position | - | saturated 1.00, angle error 0.355 rad | - | condition holds | pass |
- Reproduce: `uv run motionproof benchmark run loaded_arm`

## G. Hierarchical manufacturing variation

- Status: **PASS**
- Purpose: Variance components, shared setup effects and drift are recovered from a SYNTHETIC batch with known parameters.
- Formulation: x = target + drift + batch + setup + tool + part; shared setup cancels in bore - shaft
- Fidelity: statistical process model

| Quantity | Expected | Actual | Error | Criterion | Result |
|---|---|---|---|---|---|
| batch std recovered | 0.01 | 0.00937739 | -0.000622613 | |error| <= 0.12 x expected | pass |
| setup std recovered | 0.006 | 0.00609936 | 9.93592e-05 | |error| <= 0.08 x expected | pass |
| part std recovered | 0.004 | 0.00398219 | -1.78129e-05 | |error| <= 0.03 x expected | pass |
| clearance std, setup error independent | 0.0174356 | 0.0179307 | 0.000495137 | |error| <= 0.06 x expected | pass |
| clearance std, setup error shared | 0.0152315 | 0.0155944 | 0.000362849 | |error| <= 0.06 x expected | pass |
| tool-wear drift rate recovered | 2e-05 | 1.94015e-05 | -5.98495e-07 | |error| <= 0.1 x expected | pass |
- Reproduce: `uv run motionproof benchmark run process`

## H. Workspace reliability map

- Status: **PASS**
- Purpose: Level 1 workspace map against direct dynamic simulation at grid poses.
- Formulation: per pose: static deflection b/2 + tau(q)/k propagated through FK
- Fidelity: L1 map checked against L2

| Quantity | Expected | Actual | Error | Criterion | Result |
|---|---|---|---|---|---|
| map RMS error vs direct Level 2 simulation at q = -1.0 | 0.0012841 | 0.00128407 | -3.22469e-08 | |error| <= 0.05 x expected | pass |
| map RMS error vs direct Level 2 simulation at q = 0.0 | 0.00147362 | 0.00147358 | -4.14094e-08 | |error| <= 0.05 x expected | pass |
| map RMS error vs direct Level 2 simulation at q = 1.0 | 0.00131579 | 0.00131576 | -3.25724e-08 | |error| <= 0.05 x expected | pass |
- Reproduce: `uv run motionproof benchmark run workspace`

## I. Lifetime degradation

- Status: **PASS**
- Purpose: Recovery of a SYNTHETIC linear wear law and its requirement crossing.
- Formulation: b(n) = b0 + r n; crossing where b/2 + tau/k = limit
- Fidelity: L1

| Quantity | Expected | Actual | Error | Criterion | Result |
|---|---|---|---|---|---|
| wear rate recovered from SYNTHETIC data | 2e-09 | 2.00371e-09 | 3.70519e-12 | |error| <= 0.05 x expected | pass |
| threshold crossing (cycles) | 1.5285e+06 | 1.52852e+06 | 18.4036 | |error| <= 0.001 x expected | pass |
- Reproduce: `uv run motionproof benchmark run degradation`

## J. Hardware measurements

- Status: **NOT RUN**
- Purpose: Predicted versus measured behaviour of a physical rig.
- Formulation: -
- Fidelity: L4 physical

- Note: No physical rig or measurements exist. The software path is verified with a SIMULATED DEVICE in tests/integration/test_hardware.py; that is not physical validation.
- Reproduce: `uv run motionproof benchmark run hardware`

## K. Adaptive versus random sampling

- Status: **PASS**
- Purpose: Failure-probability accuracy at equal true-evaluation budgets, 10 seeds.
- Formulation: g = 3 - (x1 + x2)/sqrt(2), x ~ N(0, I); P(fail) = Phi(-3) = 1.35e-3
- Fidelity: analytic limit state

| Quantity | Expected | Actual | Error | Criterion | Result |
|---|---|---|---|---|---|
| median relative error, adaptive (<= 60 true evaluations) | 0 | 0.138608 | 0.138608 | |error| <= 0.4  | pass |
| adaptive beats random at the same number of true evaluations | - | median relative error adaptive 0.139, random 1.000; mean true evaluations 22.0 | - | condition holds | pass |
- Note: Rare-event case chosen on purpose; for failure fractions of tens of percent random sampling is competitive and no advantage is claimed.
- Reproduce: `uv run motionproof benchmark run adaptive`

## L. Multi-fidelity agreement and sufficiency

- Status: **PASS**
- Purpose: Analytic vs L1 vs L2, and the rule that refuses an L1 verdict near a limit.
- Formulation: deflection = b/2 + m g L cos q / k
- Fidelity: L1 vs L2

| Quantity | Expected | Actual | Error | Criterion | Result |
|---|---|---|---|---|---|
| L1 deflection vs closed form | 0.0064715 | 0.00647147 | -3.0813e-08 | |error| <= 0.0001 x expected | pass |
| L1 - L2 tip error difference (frictionless) | 0 | 0 | 0 | |error| <= 2e-05 m | pass |
| near-limit L1 result flagged as insufficient | - | L1/L2 difference with friction 0.0 um; verdict undecided | - | condition holds | pass |
- Note: Level 3 (contact, flexible bodies) is not implemented; no comparison.
- Reproduce: `uv run motionproof benchmark run fidelity`

## M. Engineering Challenge on an analytic case

- Status: **PASS**
- Purpose: Known feasible and infeasible requirements; optimum against the analytic band.
- Formulation: uniform: F(s) = max(0, (0.01 + 0.01 s - b_lim) / (0.02 s)), cost = 1/s; yield: process N(0.01, 0.004) sorted to 0.01 +- 0.01 s, cost = 1 / (2 Phi(0.01 s / 0.004) - 1)
- Fidelity: L1 search, L2 verification

| Quantity | Expected | Actual | Error | Criterion | Result |
|---|---|---|---|---|---|
| a verified candidate exists | - | C018 | - | condition holds | pass |
| chosen scale inside the analytic feasible band 0.5 to 0.75 | - | scale 0.6026 | - | condition holds | pass |
| infeasible requirement reported as infeasible | - | no candidate met the requirement in the search within the given variable ranges | - | condition holds | pass |
| yield model: a verified candidate exists | - | C003 | - | condition holds | pass |
| yield model: cost per accepted part = 1 / yield | 1.09473 | 1.09473 | 0 | |error| <= 1e-12 x expected | pass |
| yield model: chosen scale inside the analytic band 0.5 to 0.75 | - | scale 0.6856 | - | condition holds | pass |
- Reproduce: `uv run motionproof benchmark run challenge`

## N. Root cause of a deliberate failure

- Status: **PASS**
- Purpose: The variable that causes the failure is ranked first by counterfactual rerun.
- Formulation: tip error = L (b/2 + tau/k); payload minor
- Fidelity: F2 reduced order

| Quantity | Expected | Actual | Error | Criterion | Result |
|---|---|---|---|---|---|
| dominant variable identified | - | backlash_tol | - | condition holds | pass |
| counterfactual rerun removes the failure | - | metric after rerun 0.000442261 | - | condition holds | pass |
- Reproduce: `uv run motionproof benchmark run root_cause`

## Independent cross-check

`benchmarks/reference_calculations.py` recomputed the expected values and re-analysed the raw data in `benchmarks/data` in a separate interpreter that does not import MotionProof (NumPy, SciPy, PyYAML only). Inputs, raw data, the suite's full output and the hashes of every file are published there (`MANIFEST.json`).

Cross-check: **57/57 agree**.

| Benchmark | Quantity | Kind | Reference | MotionProof | Result | Comment |
|---|---|---|---|---|---|---|
| A | min clearance (bore LSL - shaft USL) | expected value | -0.003 | -0.003 | agree | suite expected value equals independent reference |
| A | max clearance (bore USL - shaft LSL) | expected value | 0.014 | 0.014 | agree | suite expected value equals independent reference |
| A | clearance mean (Monte Carlo vs analytic) | expected value | 0.0055 | 0.0055 | agree | suite expected value equals independent reference |
| A | clearance std (Monte Carlo vs RSS) | expected value | 0.00196047108 | 0.00196047108 | agree | suite expected value equals independent reference |
| A | exact B-rep radial gap with 10 um offset | expected value | 0.015 | 0.015 | agree | suite expected value equals independent reference |
| A | diameter recovered from SYNTHETIC noisy scan (unknown pose) | expected value | 8.03 | 8.03 | agree | suite expected value equals independent reference |
| B | stage 1 ratio 1 + 54/12 | expected value | 5.5 | 5.5 | agree | suite expected value equals independent reference |
| B | stage 2 ratio 1 + 60/12 | expected value | 6 | 6 | agree | suite expected value equals independent reference |
| B | overall 33:1 from tooth counts | expected value | 33 | 33 | agree | suite expected value equals independent reference |
| B | stage 2 backlash ((0.04 + 0.04)/2 + 0.012) / 9 mm | expected value | 0.00577777778 | 0.00577777778 | agree | suite expected value equals independent reference |
| B | output backlash = s2 + s1 / 6 | expected value | 0.00682828283 | 0.00682828283 | agree | suite expected value equals independent reference |
| B | transmission error amplitude e / r_sun / 33 | expected value | 0.000101010101 | 0.000101010101 | agree | suite expected value equals independent reference |
| C | IK elbow angle vs law of cosines | expected value | 1.32843048 | 1.32843048 | agree | suite expected value equals independent reference |
| C | shoulder gravity torque = sum m g x_com | expected value | 0.33797412 | 0.33797412 | agree | suite expected value equals independent reference |
| C | shoulder upper limit compiled from the model file | expected value | 3 | 3 | agree | suite expected value equals independent reference |
| C | workspace outer radius | expected value | 0.35 | 0.35 | agree | suite expected value equals independent reference |
| D | lost motion = b for b = 0.0 | expected value | 0 | 0 | agree | suite expected value equals independent reference |
| D | direction error at the tip = L b for b = 0.0 | expected value | 0 | 0 | agree | suite expected value equals independent reference |
| D | lost motion = b for b = 0.005 | expected value | 0.005 | 0.005 | agree | suite expected value equals independent reference |
| D | direction error at the tip = L b for b = 0.005 | expected value | 0.0015 | 0.0015 | agree | suite expected value equals independent reference |
| D | lost motion = b for b = 0.012 | expected value | 0.012 | 0.012 | agree | suite expected value equals independent reference |
| D | direction error at the tip = L b for b = 0.012 | expected value | 0.0036 | 0.0036 | agree | suite expected value equals independent reference |
| E | tip error from 0.05 mm joint offset | expected value | 5e-05 | 5e-05 | agree | suite expected value equals independent reference |
| E | tip error from 0.2 mm joint offset | expected value | 0.0002 | 0.0002 | agree | suite expected value equals independent reference |
| E | sensitivity d(tip error)/d(tilt) = arm length | expected value | 0.3 | 0.3 | agree | suite expected value equals independent reference |
| E | radial play grows with seat clearance (6 um) | expected value | 6e-06 | 6e-06 | agree | suite expected value equals independent reference |
| E | axis tilt from extra play = play / bearing span | expected value | 0.0004 | 0.0004 | agree | suite expected value equals independent reference |
| F | motor torque with 0.0 kg payload = (m+mp) g L / N | expected value | 0.14715 | 0.14715 | agree | suite expected value equals independent reference |
| F | torque utilisation with 0.0 kg | expected value | 0.073575 | 0.073575 | agree | suite expected value equals independent reference |
| F | tip error with 0.0 kg = L tau / k | expected value | 0.00044145 | 0.00044145 | agree | suite expected value equals independent reference |
| F | motor torque with 0.5 kg payload = (m+mp) g L / N | expected value | 0.220725 | 0.220725 | agree | suite expected value equals independent reference |
| F | torque utilisation with 0.5 kg | expected value | 0.1103625 | 0.1103625 | agree | suite expected value equals independent reference |
| F | tip error with 0.5 kg = L tau / k | expected value | 0.000662175 | 0.000662175 | agree | suite expected value equals independent reference |
| F | motor torque with 1.5 kg payload = (m+mp) g L / N | expected value | 0.367875 | 0.367875 | agree | suite expected value equals independent reference |
| F | torque utilisation with 1.5 kg | expected value | 0.1839375 | 0.1839375 | agree | suite expected value equals independent reference |
| F | tip error with 1.5 kg = L tau / k | expected value | 0.001103625 | 0.001103625 | agree | suite expected value equals independent reference |
| I | wear rate recovered from SYNTHETIC data | expected value | 2e-09 | 2e-09 | agree | suite expected value equals independent reference |
| I | threshold crossing (cycles) | expected value | 1528500 | 1528500 | agree | suite expected value equals independent reference |
| L | L1 deflection vs closed form | expected value | 0.0064715 | 0.0064715 | agree | suite expected value equals independent reference |
| L | L1 - L2 tip error difference (frictionless) | expected value | 0 | 0 | agree | suite expected value equals independent reference |
| G | batch std recovered | expected value | 0.01 | 0.01 | agree | suite expected value equals independent reference |
| G | setup std recovered | expected value | 0.006 | 0.006 | agree | suite expected value equals independent reference |
| G | part std recovered | expected value | 0.004 | 0.004 | agree | suite expected value equals independent reference |
| G | clearance std, setup error independent | expected value | 0.0174355958 | 0.0174355958 | agree | suite expected value equals independent reference |
| G | clearance std, setup error shared | expected value | 0.0152315462 | 0.0152315462 | agree | suite expected value equals independent reference |
| G | tool-wear drift rate recovered | expected value | 2e-05 | 2e-05 | agree | suite expected value equals independent reference |
| K | true failure probability Phi(-3) (reference only) | reference value | 0.00134989803 | - | - | no matching suite check; reported for context |
| M | largest scale with zero failures | reference value | 0.6 | - | - | no matching suite check; reported for context |
| M | largest scale meeting the reliability target (point estimate; cost optimum 1/s without confidence margin) | reference value | 0.74999 | - | - | no matching suite check; reported for context |
| A | Kasa circle fit of the raw posed scan (no registration) | estimate | 8.02982702 | 8.03 | agree | vs true diameter; |difference| <= 0.002 |
| C | max deviation of MotionProof FK from the closed form | estimate | 1.00074151e-16 | 0 | agree | vs zero; |difference| <= 1e-09 |
| I | wear rate, numpy.polyfit on the raw data | estimate | 2.00370519e-09 | 2.00370519e-09 | agree | vs suite: wear rate recovered from SYNTHETIC data; |difference| <= 2e-18 |
| G | batch std, own nested ANOVA | estimate | 0.00937738736 | 0.00937738736 | agree | vs suite: batch std recovered; |difference| <= 9.38e-12 |
| G | setup std, own nested ANOVA | estimate | 0.00609935922 | 0.00609935922 | agree | vs suite: setup std recovered; |difference| <= 6.1e-12 |
| G | part std, own nested ANOVA | estimate | 0.00398218715 | 0.00398218715 | agree | vs suite: part std recovered; |difference| <= 3.98e-12 |
| G | clearance std (independent setup), numpy std of bore - shaft | estimate | 0.0179307332 | 0.0179307332 | agree | vs suite: clearance std, setup error independent; |difference| <= 1.79e-11 |
| G | clearance std (shared setup), numpy std of bore - shaft | estimate | 0.0155943947 | 0.0155943947 | agree | vs suite: clearance std, setup error shared; |difference| <= 1.56e-11 |
| G | drift rate, numpy.polyfit | estimate | 1.94015049e-05 | 1.94015049e-05 | agree | vs suite: tool-wear drift rate recovered; |difference| <= 1.94e-11 |
| M | yield cost (unit cost 1.0) / yield at the chosen scale 0.685584 | estimate | 1.09473396 | 1.09473396 | agree | vs MotionProof cost of the chosen candidate; |difference| <= 1.09e-12 |
| M | chosen scale (reciprocal cost) within [0.5, point-estimate optimum]; 0.5 is the suite's lower bound allowing for the confidence margin | estimate | [0.5, 0.74999] | 0.602575304 | agree | MotionProof choice inside the reference band |

Reproduce: `uv run python benchmarks/publish.py`; references alone: `python -I benchmarks/reference_calculations.py benchmarks/data`.
