import pathlib
import sys
import tempfile

import cadquery as cq
import mujoco
import numpy as np
import trimesh

DENSITY = 2700.0  # kg/m3 (aluminium)
res = {}
def check(name, ok, detail=""):
    res[name] = ok
    print(("PASS " if ok else "FAIL ") + name + (" - " + str(detail) if detail else ""))

tmp = pathlib.Path(tempfile.mkdtemp(prefix="motionproof_cad_test_"))
print("temp dir:", tmp)

# ---------- Test A: CAD creation (mm) ----------
L, W, H, HOLE_D, HOLE_X = 300.0, 40.0, 40.0, 10.0, 15.0
link = cq.Workplane("XY").box(L, W, H, centered=(False, True, True))
hole = cq.Workplane("XZ").center(HOLE_X, 0).circle(HOLE_D / 2).extrude(W, both=True)
link = link.cut(hole)
step_p, stl_p = tmp / "link.step", tmp / "link.stl"
cq.exporters.export(link, str(step_p))
cq.exporters.export(link, str(stl_p), tolerance=0.01, angularTolerance=0.1)
check("A.step_exported", step_p.exists() and step_p.stat().st_size > 0, f"{step_p.stat().st_size} B")
check("A.stl_exported", stl_p.exists() and stl_p.stat().st_size > 0, f"{stl_p.stat().st_size} B")

# ---------- Test B: STEP import ----------
imp = cq.importers.importStep(str(step_p))
shape = imp.val()
bb = shape.BoundingBox()
dims = (bb.xlen, bb.ylen, bb.zlen)
expected_vol = L * W * H - np.pi * (HOLE_D / 2) ** 2 * W
check("B.valid", shape.isValid())
check("B.bbox", np.allclose(dims, (L, W, H), atol=1e-3), dims)
check("B.volume", abs(shape.Volume() - expected_vol) < 1e-3 * expected_vol, f"{shape.Volume():.2f} vs analytic {expected_vol:.2f} mm3")
faces = shape.Faces()
types = sorted({f.geomType() for f in faces})
check("B.surfaces", len(faces) == 8 and {"PLANE", "CYLINDER"} <= set(types), f"{len(faces)} faces, types={types}")

# ---------- Test C: mesh processing ----------
mesh = trimesh.load(str(stl_p), force="mesh")
mesh.merge_vertices()
check("C.triangles", len(mesh.faces) > 12, f"{len(mesh.faces)} tris")
check("C.bbox", np.allclose(mesh.extents, (L, W, H), atol=1e-3), mesh.extents.tolist())
check("C.watertight", mesh.is_watertight and mesh.is_winding_consistent)
check("C.volume", abs(mesh.volume - shape.Volume()) / shape.Volume() < 0.01, f"mesh {mesh.volume:.2f} vs OCC {shape.Volume():.2f}")

# mass/inertia in SI (metres)
mesh_m = mesh.copy(); mesh_m.apply_scale(0.001)
mesh_m.density = DENSITY
mp = mesh_m.mass_properties
mass, com, inertia = float(mp.mass), np.array(mp.center_mass), np.array(mp.inertia)
print(f"mass={mass:.4f} kg com={com.round(5).tolist()} diag inertia={np.diag(inertia).tolist()}")
# collision representation: convex hull of the mesh (mm)
hull = mesh.convex_hull
hull_p = tmp / "link_collision.stl"; hull.export(str(hull_p))
check("C.collision_hull", hull.is_convex and len(hull.faces) > 0, f"{len(hull.faces)} tris")
vis_p = tmp / "link_visual.stl"; mesh.export(str(vis_p))

# ---------- Test D: MJCF generation ----------
fi = [inertia[0, 0], inertia[1, 1], inertia[2, 2], inertia[0, 1], inertia[0, 2], inertia[1, 2]]
def mjcf(with_inertial=True):
    inert = (f'<inertial pos="{com[0]:.6f} {com[1]:.6f} {com[2]:.6f}" mass="{mass:.6f}" '
             f'fullinertia="{" ".join(f"{v:.9g}" for v in fi)}"/>') if with_inertial else ""
    dens = "" if with_inertial else f'density="{DENSITY}"'
    return f"""<mujoco model="cad_link_test">
  <compiler meshdir="." angle="degree"/>
  <option gravity="0 0 -9.81" timestep="0.001"/>
  <asset>
    <mesh name="link_vis" file="link_visual.stl" scale="0.001 0.001 0.001"/>
    <mesh name="link_col" file="link_collision.stl" scale="0.001 0.001 0.001"/>
  </asset>
  <worldbody>
    <geom name="ground" type="plane" size="2 2 0.1"/>
    <body name="link" pos="0 0 0.25">
      <joint name="hinge" type="hinge" axis="0 1 0" range="-90 90" limited="true" damping="0.05"/>
      {inert}
      <geom name="link_visual" type="mesh" mesh="link_vis" contype="0" conaffinity="0" group="1" {dens}/>
      <geom name="link_collision" type="mesh" mesh="link_col" group="0" {dens if not with_inertial else ""}/>
    </body>
  </worldbody>
  <actuator>
    <motor name="motor" joint="hinge" gear="1" ctrlrange="-5 5"/>
  </actuator>
</mujoco>"""
(tmp / "model.xml").write_text(mjcf(True))
check("D.mjcf_written", (tmp / "model.xml").exists())

# ---------- Test E: simulation ----------
m = mujoco.MjModel.from_xml_path(str(tmp / "model.xml"))
d = mujoco.MjData(m)
check("E.compiles", True, f"nbody={m.nbody} njnt={m.njnt} nu={m.nu} ngeom={m.ngeom} nmesh={m.nmesh}")
check("E.mass", abs(m.body_mass[1] - mass) < 1e-6, f"{m.body_mass[1]:.4f} kg")
check("E.inertia_pd", bool(np.all(m.body_inertia[1] > 0)), m.body_inertia[1].tolist())

# without explicit inertial, MuJoCo computes from density; compare to trimesh/OCC (collision hull is convex hull so only compare visual-based)
def single_mesh_mass(mode):
    x = (f'<mujoco><compiler meshdir="{tmp.as_posix()}"/><asset><mesh name="m" file="link_visual.stl" '
         f'scale="0.001 0.001 0.001" inertia="{mode}"/></asset><worldbody><body><freejoint/>'
         f'<geom type="mesh" mesh="m" density="{DENSITY}"/></body></worldbody></mujoco>')
    return float(mujoco.MjModel.from_xml_string(x).body_mass[1])
m_legacy, m_exact = single_mesh_mass("legacy"), single_mesh_mass("exact")
print(f"MuJoCo density-derived mass: legacy={m_legacy:.4f} exact={m_exact:.4f} trimesh={mass:.4f} OCC={shape.Volume()*1e-9*DENSITY:.4f}")
check("E.mass_crosscheck_exact", abs(m_exact - mass) / mass < 0.01, f"exact {m_exact:.4f} vs trimesh {mass:.4f}")
check("E.legacy_mass_overestimates_nonconvex", m_legacy > mass * 1.05, f"legacy {m_legacy:.4f} (+{(m_legacy/mass-1)*100:.1f}%) -> always supply explicit inertial or inertia=exact")

# 1) actuator lifts link against gravity to upper limit
mujoco.mj_resetData(m, d); d.ctrl[0] = -5.0
for _ in range(3000): mujoco.mj_step(m, d)
q_up = float(np.degrees(d.qpos[0]))
check("E.actuator_moves_joint", q_up < -60, f"hinge={q_up:.2f} deg")
check("E.joint_limit_respected", q_up >= -90.5, f"limit -90, got {q_up:.2f}")
# 2) gravity drops it onto ground -> collision with ground
mujoco.mj_resetData(m, d); d.ctrl[0] = 0.0
hit = None
for _ in range(5000):
    mujoco.mj_step(m, d)
    for i in range(d.ncon):
        c = d.contact[i]
        names = {mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_GEOM, c.geom1), mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_GEOM, c.geom2)}
        if names == {"ground", "link_collision"}: hit = (d.time, float(np.degrees(d.qpos[0])))
    if hit: break
check("E.collision_detected", hit is not None, f"t={hit[0]:.3f}s hinge={hit[1]:.1f} deg" if hit else "none")
check("E.visual_geom_no_collision", all(
    mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_GEOM, d.contact[i].geom1) != "link_visual" and
    mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_GEOM, d.contact[i].geom2) != "link_visual" for i in range(d.ncon)))
check("E.finite", bool(np.isfinite(d.qpos).all() and np.isfinite(d.qvel).all() and np.isfinite(d.qacc).all()))
# 3) gravity-only swing without limit contact: energy sanity, hinge torque balance
mujoco.mj_resetData(m, d); d.qpos[0] = 0; mujoco.mj_forward(m, d)
g_torque = -d.qfrc_bias[0]  # gravity torque about hinge
exp_torque = mass * 9.81 * com[0]
check("E.gravity_torque", abs(abs(g_torque) - exp_torque) / exp_torque < 0.02, f"{abs(g_torque):.4f} vs m*g*x={exp_torque:.4f} N*m")

print("\nSUMMARY:", sum(res.values()), "/", len(res), "passed")
sys.exit(0 if all(res.values()) else 1)
