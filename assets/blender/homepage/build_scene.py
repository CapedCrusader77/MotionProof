"""Build the MotionProof homepage assembly in Blender from ENGINE-GENERATED geometry.

    blender -b --factory-startup -P assets/blender/homepage/build_scene.py -- <repo-root>

Inputs  (written by scripts/export_homepage_data.py):
    assets/blender/homepage/build/nominal/meshes/*.stl           nominal reference design (mm)
    assets/blender/homepage/build/variants/<id>/meshes/*.stl     engine-regenerated scenario geometry
Outputs:
    assets/blender/homepage/motionproof_homepage.blend
    frontend/public/assets/motionproof/assembly.glb

Everything in collection "Engineering" is real engine geometry (plain pitch-cylinder gears, as the
engine models them). The cinematic-only tooth detail lives in "RenderOnly" (see render_cinematic.py)
and is never exported to the GLB.

Coordinates: Blender metres, gearbox axis +Y, arm +X, Z up (glTF export converts to Y up).
"""
from __future__ import annotations
import json, math, sys
from pathlib import Path
import bpy, bmesh
from mathutils import Vector, kdtree

ROOT = Path(sys.argv[sys.argv.index("--") + 1]).resolve()
HP = ROOT / "assets/blender/homepage"
NOM, VAR = HP / "build/nominal", HP / "build/variants"
OUT_GLB = ROOT / "frontend/public/assets/motionproof/assembly.glb"
inv = json.loads((NOM / "inventory.json").read_text())
MM = 0.001

bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
scene.unit_settings.system = "METRIC"; scene.unit_settings.scale_length = 1.0
eng = bpy.data.collections.new("Engineering"); scene.collection.children.link(eng)


# ------------------------------------------------------------------ materials
def mat(name, base, metal, rough, aniso=0.0, coat=0.0, clear=0.0):
    m = bpy.data.materials.new(name); m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*base, 1)
    b.inputs["Metallic"].default_value = metal; b.inputs["Roughness"].default_value = rough
    if "Anisotropic" in b.inputs: b.inputs["Anisotropic"].default_value = aniso
    if "Coat Weight" in b.inputs: b.inputs["Coat Weight"].default_value = coat
    return m

MATS = {
    "steel": mat("MP_Steel_Brushed", (0.62, 0.64, 0.66), 1.0, 0.34, aniso=0.5),
    "steel_dark": mat("MP_Steel_Dark", (0.20, 0.21, 0.22), 1.0, 0.42, aniso=0.3),
    "brass": mat("MP_Brass", (0.78, 0.55, 0.26), 1.0, 0.28),
    "alu": mat("MP_Aluminium_Anodised", (0.30, 0.32, 0.35), 0.9, 0.38),
    "black": mat("MP_Motor_Black", (0.035, 0.037, 0.04), 0.4, 0.5, coat=0.2),
    "polished": mat("MP_Steel_Polished", (0.78, 0.79, 0.80), 1.0, 0.14),
    "vermilion": mat("MP_Vermilion", (0.78, 0.21, 0.12), 0.0, 0.38, coat=0.6),
}
MATERIAL_OF = {  # component id -> material
    "motor_body": "black", "input_shaft": "polished", "housing": "alu",
    "output_bearing_0": "vermilion", "output_bearing_1": "vermilion",
    "output_shaft": "polished", "upper_arm_link": "alu", "forearm_link": "steel",
}
for s in (1, 2):
    MATERIAL_OF[f"stage{s}_ring"] = "steel_dark"; MATERIAL_OF[f"stage{s}_carrier"] = "steel_dark"
    MATERIAL_OF[f"stage{s}_sun"] = "brass"
    for k in range(3): MATERIAL_OF[f"stage{s}_planet_{k}"] = "steel"


# ------------------------------------------------------------------ import
def import_stl(path: Path, name: str) -> bpy.types.Object:
    before = set(bpy.data.objects)
    bpy.ops.wm.stl_import(filepath=str(path), global_scale=MM)
    obj = next(o for o in bpy.data.objects if o not in before)
    obj.name = name; obj.data.name = name
    bm = bmesh.new(); bm.from_mesh(obj.data)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-7)
    bm.to_mesh(obj.data); bm.free()
    return obj


parts: dict[str, bpy.types.Object] = {}
for c in inv["components"]:
    o = import_stl(NOM / c["mesh"], c["id"])
    for col in list(o.users_collection): col.objects.unlink(o)
    eng.objects.link(o)
    o.data.materials.append(MATS[MATERIAL_OF[c["id"]]])
    bpy.context.view_layer.objects.active = o; o.select_set(True)
    bpy.ops.object.origin_set(type="ORIGIN_GEOMETRY", center="BOUNDS")
    o.select_set(False)
    bpy.ops.object.shade_smooth_by_angle(angle=math.radians(35))  # active object
    o["component"] = c["id"]; o["group"] = c["group"]; o["body"] = c["body"]
    o["mass_kg"] = float(c.get("mass_kg") or 0.0); o["source"] = "engine geometry (CadQuery), nominal"
    parts[c["id"]] = o

# ------------------------------------------------------------------ variants as shape keys
variant_ids = sorted(p.name for p in VAR.iterdir() if p.is_dir())
max_dev = {}
for vid in variant_ids:
    for cid, o in parts.items():
        tmp = import_stl(VAR / vid / "meshes" / f"{cid}.stl", f"_tmp_{cid}")
        # tmp keeps the engine's world coordinates; bring both into the same frame
        tree = kdtree.KDTree(len(tmp.data.vertices))
        for i, v in enumerate(tmp.data.vertices): tree.insert(tmp.matrix_world @ v.co, i)
        tree.balance()
        if not o.data.shape_keys: o.shape_key_add(name="Basis", from_mix=False)
        sk = o.shape_key_add(name=f"variant_{vid}", from_mix=False)
        inv_m = o.matrix_world.inverted()
        worst = 0.0
        for i, v in enumerate(o.data.vertices):
            world = o.matrix_world @ v.co
            co, j, d = tree.find(world)
            if d < 0.0002:  # engine variants move features by microns: match by proximity
                sk.data[i].co = inv_m @ co
                worst = max(worst, d)
        max_dev[f"{vid}/{cid}"] = worst / MM
        bpy.data.objects.remove(tmp)
(HP / "build/variant_deviation_mm.json").write_text(json.dumps(max_dev, indent=1))

# ------------------------------------------------------------------ hierarchy
def empty(name, parent=None):
    e = bpy.data.objects.new(name, None); e.empty_display_type = "PLAIN_AXES"; e.empty_display_size = 0.01
    eng.objects.link(e)
    if parent: e.parent = parent
    return e

root = empty("MotionProof_Assembly")
root["note"] = "Synthetic reference design. Geometry from the MotionProof engine; gears are pitch cylinders."
G = {n: empty(n, root) for n in ("Motor", "Housing", "Bearings", "Stage1", "Stage2")}
out_axis = empty("OutputAxis", root)
G["Output"] = empty("Output", out_axis); G["Link"] = empty("Link", out_axis)
GROUP_OF = {"motor_body": "Motor", "input_shaft": "Motor", "housing": "Housing",
            "output_bearing_0": "Bearings", "output_bearing_1": "Bearings", "output_shaft": "Output",
            "upper_arm_link": "Link", "forearm_link": "Link"}
for s in (1, 2):
    for n in ("ring", "sun", "carrier", "planet_0", "planet_1", "planet_2"): GROUP_OF[f"stage{s}_{n}"] = f"Stage{s}"
for cid, o in parts.items():
    world = o.matrix_world.copy(); o.parent = G[GROUP_OF[cid]]; o.matrix_world = world

# ------------------------------------------------------------------ animation clips
rest = {cid: (o.location.copy(), o.rotation_euler.copy()) for cid, o in parts.items()}
FPS = scene.render.fps = 24
STAGES = [(12, 21, 54, "stage1"), (12, 24, 60, "stage2")]
MODULE = 0.5

ORDER = ["motor_body", "input_shaft", "stage1_sun", "stage1_planet", "stage1_ring", "stage1_carrier",
         "stage2_sun", "stage2_planet", "stage2_ring", "stage2_carrier", "output_bearing_0",
         "output_bearing_1", "output_shaft", "housing", "upper_arm_link", "forearm_link"]
EXPLODE = {}
for rank, key in enumerate(ORDER):
    off = (rank - 6.5) * 15.0 * MM
    for cid in parts:
        if cid == key or (key.endswith("planet") and cid.startswith(key)): EXPLODE[cid] = off


def push(obj, clip):
    ad = obj.animation_data
    act = ad.action
    track = ad.nla_tracks.new(); track.name = clip
    strip = track.strips.new(clip, int(act.frame_range[0]), act)
    strip.name = clip
    ad.action = None


def key_loc(o, f, loc): o.location = loc; o.keyframe_insert("location", frame=f)
def key_rot(o, f, y): o.rotation_euler = (rest_rot(o)[0], y, rest_rot(o)[2]); o.keyframe_insert("rotation_euler", frame=f)
def rest_rot(o): return (0.0, 0.0, 0.0)


animated = list(parts.values()) + [out_axis]
for o in animated: o.animation_data_create()

# --- Explode: axial, 120 frames, parts keep orientation
for cid, o in parts.items():
    o.animation_data.action = bpy.data.actions.new(f"Explode_{cid}")
    base = rest[cid][0]
    key_loc(o, 1, base)
    key_loc(o, 120, Vector((base.x, base.y + EXPLODE[cid], base.z)))
    for fc in o.animation_data.action.fcurves if hasattr(o.animation_data.action, "fcurves") else []:
        for kp in fc.keyframe_points: kp.interpolation = "BEZIER"
    push(o, "Explode")
out_axis.animation_data.action = bpy.data.actions.new("Explode_axis")
out_axis.keyframe_insert("location", frame=1); out_axis.keyframe_insert("location", frame=120)
push(out_axis, "Explode")

# --- Run: ideal nominal 33:1 kinematics, one 96-frame loop (output swings +-0.30 rad)
N = 96
for o in animated: o.animation_data.action = bpy.data.actions.new(f"Run_{o.name}")
for f in range(1, N + 2):
    t = (f - 1) / N
    q_out = 0.30 * math.sin(2 * math.pi * t)
    sun = q_out * 33.0
    for zs, zp, zr, sid in STAGES:
        c = sun * zs / (zs + zr)
        p = c - (sun - c) * zs / zp
        a = MODULE * (zs + zp) / 2 * MM
        key_rot(parts[f"{sid}_sun"], f, sun)
        key_rot(parts[f"{sid}_carrier"], f, c)
        key_loc(parts[f"{sid}_sun"], f, rest[f"{sid}_sun"][0])
        key_loc(parts[f"{sid}_carrier"], f, rest[f"{sid}_carrier"][0])
        for k in range(3):
            po = parts[f"{sid}_planet_{k}"]; y = rest[po.name][0].y
            phi = c + 2 * math.pi * k / 3
            key_loc(po, f, Vector((a * math.cos(phi), y, -a * math.sin(phi))))
            key_rot(po, f, p)
        sun = c
    key_rot(parts["input_shaft"], f, q_out * 33.0)
    key_loc(parts["input_shaft"], f, rest["input_shaft"][0])
    out_axis.rotation_euler = (0, q_out, 0); out_axis.keyframe_insert("rotation_euler", frame=f)
    for cid in ("motor_body", "housing", "output_bearing_0", "output_bearing_1", "stage1_ring", "stage2_ring",
                "output_shaft", "upper_arm_link", "forearm_link"):
        key_loc(parts[cid], f, rest[cid][0]); parts[cid].keyframe_insert("rotation_euler", frame=f)
for o in animated: push(o, "Run")
scene.frame_start, scene.frame_end = 1, 120
for o in parts.values(): o.location = rest[o.name][0]; o.rotation_euler = (0, 0, 0)
out_axis.location = (0, 0, 0); out_axis.rotation_euler = (0, 0, 0)

# ------------------------------------------------------------------ save + export
bpy.ops.wm.save_as_mainfile(filepath=str(HP / "motionproof_homepage.blend"))
OUT_GLB.parent.mkdir(parents=True, exist_ok=True)
bpy.ops.object.select_all(action="DESELECT")
for o in eng.objects: o.select_set(True)
bpy.ops.export_scene.gltf(
    filepath=str(OUT_GLB), export_format="GLB", use_selection=True, export_yup=True,
    export_animations=True, export_animation_mode="NLA_TRACKS", export_morph=True,
    export_extras=True, export_cameras=False, export_lights=False, export_apply=False,
    export_draco_mesh_compression_enable=False)
print("GLB", OUT_GLB.stat().st_size // 1024, "KB;", len(parts), "components;", variant_ids)
