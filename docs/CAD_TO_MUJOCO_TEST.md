# CAD → Mesh → MuJoCo Verification Test

Run 2026-11-14. Script: `scripts/verify_cad_to_mujoco.py` (run with `uv run python scripts/verify_cad_to_mujoco.py`). Files are generated in a fresh temp directory, never in an existing project.

**Result: 23 / 23 checks passed** (first run: 20/22 — both failures were wrong expectations in the test, fixed; see findings).

**Scope: this verifies a CadQuery-generated pipeline. Autodesk Fusion integration is NOT verified.** No assembly exported from Fusion has been tested yet.

## Test part
Aluminium link, 300 × 40 × 40 mm, 10 mm cross-hole at x = 15 mm, density 2700 kg/m³.

## A — CAD creation
- CadQuery built the part; exported STEP (22,115 B) and STL (38,684 B). PASS

## B — STEP import (CadQuery / OpenCascade)
- Shape valid. PASS
- Bounding box 300.0 × 40.0 × 40.0 mm. PASS
- Volume 476,858.41 mm³, identical to the analytic value. PASS
- Surfaces accessible: 8 faces (PLANE and CYLINDER; OCC splits the hole wall into 2 faces). PASS

## C — Mesh processing (Trimesh)
- 772 triangles; bounding box matches; watertight and winding-consistent. PASS
- Mesh volume 476,859.71 mm³ vs OCC 476,858.41 mm³ (0.0003 % difference). PASS
- Mass 1.2875 kg, COM x = 0.15089 m, principal inertia ≈ [3.44e-4, 9.74e-3, 9.74e-3] kg·m². Computed from the mesh.
- Convex-hull collision mesh generated (12 triangles). PASS

## D — MJCF generation
Generated: ground plane, one body, hinge joint (axis Y, ±90°, limited, damping), motor actuator (gear 1, ±5 N·m), gravity −9.81. Separate visual mesh (`contype=0 conaffinity=0`, group 1) and collision mesh (convex hull, group 0). Meshes in mm with `scale="0.001"`; mass/COM/full inertia written explicitly from Trimesh.

## E — Simulation (MuJoCo 3.14.0)
| Check | Result |
|---|---|
| Model compiles (2 bodies, 1 joint, 1 actuator, 3 geoms, 2 meshes) | PASS |
| MuJoCo body mass equals Trimesh mass (1.2875 kg) | PASS |
| Inertia positive-definite | PASS |
| Actuator (−5 N·m) lifts link against gravity to −90.15° | PASS |
| Joint limit respected (−90°, 0.15° soft-constraint overshoot) | PASS |
| Link under gravity strikes ground; contact `ground`–`link_collision` at t = 0.206 s | PASS |
| Visual geom never produces contacts | PASS |
| qpos, qvel, qacc all finite | PASS |
| Gravity torque at hinge 1.9058 N·m = m·g·x_com | PASS |

## Findings that matter for MotionProof
1. **MuJoCo's default mesh inertia (`inertia="legacy"`) is wrong for non-convex parts.** For this link it gave 1.3855 kg (+7.6 %). `inertia="exact"` gave 1.2875 kg, matching Trimesh and OpenCascade. MotionProof must write an explicit `<inertial>` (as this test does) or set `inertia="exact"`. `inertia="shell"` is wildly wrong (141 kg) and must not be used for solid parts.
2. Unit handling: CAD data is in mm; MuJoCo is SI. Use mesh `scale` and convert mass properties explicitly.
3. Mesh collision in MuJoCo uses the convex hull, so concave parts need a hull or a decomposition.
4. Hinge position, axis, limits, actuator and material density cannot be read from STEP/STL; they were specified by hand.

## Not tested
- Fusion-exported STEP/STL or assemblies, multi-body assemblies and joint inference.
- Pinocchio (not installed).
- GPU-accelerated MuJoCo rendering (see installation report).
