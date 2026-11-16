"""Cinematic presentation renders for the MotionProof homepage (render-only assets).

    blender -b -P assets/blender/homepage/render_cinematic.py -- <repo-root> <sequence> [--still N] [--samples S]

sequence: reveal   chapter 1, ~5 s: slit of light on the machined shaft, macro track, planetary stage, pull-back
          finale   chapter 9, ~4 s: orbit of the fully assembled reference design

The shot adds RENDER-ONLY detail that the engine does not model: individual gear teeth (the engine
draws pitch cylinders), a cutaway of the housing, studio lighting and a floor. None of it is exported
to the interactive GLB and none of it is simulated by MotionProof. Mechanical dimensions, component
identity and positions come from the engine geometry in motionproof_homepage.blend.
"""
from __future__ import annotations
import math, sys
from pathlib import Path
import bpy, bmesh
from mathutils import Vector

args = sys.argv[sys.argv.index("--") + 1:]
ROOT = Path(args[0]).resolve(); SEQ = args[1]
still = int(args[args.index("--still") + 1]) if "--still" in args else None
samples = int(args[args.index("--samples") + 1]) if "--samples" in args else 48
HP = ROOT / "assets/blender/homepage"
PUB = ROOT / "frontend/public/assets/motionproof"
bpy.ops.wm.open_mainfile(filepath=str(HP / "motionproof_homepage.blend"))
scene = bpy.context.scene
MM = 0.001
FPS = 24
FRAMES = {"reveal": 144, "finale": 120}[SEQ]
scene.frame_start, scene.frame_end = 1, FRAMES

# clear baked clips: the shot drives its own motion
for o in bpy.data.objects:
    if o.animation_data:
        for t in list(o.animation_data.nla_tracks): o.animation_data.nla_tracks.remove(t)
        o.animation_data.action = None
    if o.type == "MESH" and o.data.shape_keys is not None: pass
eng = bpy.data.collections["Engineering"]
P = {o.name: o for o in eng.objects if o.type == "MESH"}
for o in P.values(): o.rotation_euler = (0, 0, 0)

# ------------------------------------------------------------------ render-only tooth detail
detail = bpy.data.collections.new("RenderOnly"); scene.collection.children.link(detail)
STEEL = bpy.data.materials["MP_Steel_Brushed"]; BRASS = bpy.data.materials["MP_Brass"]; DARK = bpy.data.materials["MP_Steel_Dark"]
MODULE = 0.5


def tooth_points(z, internal=False):
    r = MODULE * z / 2; add, ded = MODULE, 1.25 * MODULE
    pts = []
    for k in range(z):
        a0, w = 2 * math.pi * k / z, 2 * math.pi / z
        rt, rr = (r - add, r + ded) if internal else (r + add, r - ded)
        for frac, rad in ((0.0, rr), (0.17, rr), (0.35, rt), (0.65, rt), (0.83, rr)):
            a = a0 + frac * w
            pts.append((rad * math.cos(a) * MM, rad * math.sin(a) * MM))
    return pts


def prism(name, pts, width_mm, mat, bore_mm=0.0):
    me = bpy.data.meshes.new(name); bm = bmesh.new()
    vs = [bm.verts.new((x, 0, z)) for x, z in pts]
    f = bm.faces.new(vs)
    if f.normal.y > 0: f.normal_flip()
    bmesh.ops.extrude_face_region(bm, geom=[f])
    ext = [v for v in bm.verts if v.co.y == 0 and False]
    geom = [v for v in bm.verts]
    new = bm.verts[len(vs):]
    for v in new: v.co.y -= width_mm * MM  # extrude along -Y then recentre below
    for v in bm.verts: v.co.y += width_mm * MM / 2
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(me); bm.free()
    o = bpy.data.objects.new(name, me); me.materials.append(mat); detail.objects.link(o)
    for p in me.polygons: p.use_smooth = False
    return o


def gear_like(cid, z, width, mat, internal=False):
    src = P[cid]
    o = prism(cid + "_teeth", tooth_points(z, internal), width, mat)
    o.parent = src.parent; o.matrix_world = src.matrix_world.copy()
    return o


pairs = []  # (engine part, toothed replacement)
ring_objs = []
for s, (zs, zp, zr) in enumerate([(12, 21, 54), (12, 24, 60)], start=1):
    pairs.append((f"stage{s}_sun", gear_like(f"stage{s}_sun", zs, 8, BRASS)))
    for k in range(3): pairs.append((f"stage{s}_planet_{k}", gear_like(f"stage{s}_planet_{k}", zp, 8, STEEL)))
    # ring: toothed bore cut from the engine's own ring body (outer radius from the engine mesh)
    ring = P[f"stage{s}_ring"]
    o = ring.copy(); o.data = ring.data.copy(); o.name = f"stage{s}_ring_teeth"; detail.objects.link(o)
    o.data.shape_keys and None
    cutter = prism(f"cut{s}", tooth_points(zr, True), 8.2, DARK)
    cutter.parent = ring.parent; cutter.matrix_world = ring.matrix_world.copy()
    mod = o.modifiers.new("teeth", "BOOLEAN"); mod.operation = "DIFFERENCE"; mod.object = cutter; mod.solver = "EXACT"
    pairs.append((ring.name, o)); o["cutter"] = cutter.name; ring_objs.append(o)
for src, _ in pairs: P[src].hide_render = True; P[src].hide_viewport = True

# cutaway of the housing for the cinematic view (render copy only)
hs = P["housing"]
hc = hs.copy(); hc.data = hs.data.copy(); hc.name = "housing_cutaway"; detail.objects.link(hc)
box = bpy.data.objects.new("cutbox", None)
cube = bpy.data.meshes.new("cutbox"); bm = bmesh.new(); bmesh.ops.create_cube(bm, size=1.0); bm.to_mesh(cube); bm.free()
cb = bpy.data.objects.new("cutbox", cube); detail.objects.link(cb)
cb.scale = (0.2, 0.2, 0.1); cb.location = (0, 0.0, 0.05); cb.display_type = "WIRE"; cb.hide_render = True
m = hc.modifiers.new("cut", "BOOLEAN"); m.operation = "DIFFERENCE"; m.object = cb; m.solver = "EXACT"
hs.hide_render = True; hs.hide_viewport = True
for ro in ring_objs:
    mm = ro.modifiers.new('cut', 'BOOLEAN'); mm.operation = 'DIFFERENCE'; mm.object = cb; mm.solver = 'EXACT'

# ------------------------------------------------------------------ studio
scene.render.engine = "CYCLES"
cy = scene.cycles; cy.samples = samples; cy.use_denoising = True; cy.denoiser = "OPENIMAGEDENOISE"
prefs = bpy.context.preferences.addons["cycles"].preferences
try:
    prefs.compute_device_type = "OPTIX"; prefs.get_devices()
    for d in prefs.devices: d.use = d.type in ("OPTIX", "CUDA")
    cy.device = "GPU"
except Exception as e: print("GPU unavailable, CPU render:", e)
scene.view_settings.view_transform = "AgX"; scene.view_settings.look = "AgX - Medium High Contrast"
scene.render.resolution_x, scene.render.resolution_y = 1920, 1080
scene.render.resolution_percentage = int(args[args.index("--scale") + 1]) if "--scale" in args else 100

w = bpy.data.worlds.new("studio"); scene.world = w; w.use_nodes = True
w.node_tree.nodes["Background"].inputs["Color"].default_value = (0.012, 0.013, 0.014, 1)
w.node_tree.nodes["Background"].inputs["Strength"].default_value = 1.0

floor_m = bpy.data.materials.new("MP_Floor"); floor_m.use_nodes = True
fb = floor_m.node_tree.nodes["Principled BSDF"]
fb.inputs["Base Color"].default_value = (0.012, 0.013, 0.014, 1); fb.inputs["Roughness"].default_value = 0.28; fb.inputs["Metallic"].default_value = 0.0
bpy.ops.mesh.primitive_plane_add(size=6, location=(0.1, 0, -0.0215))
fl = bpy.context.active_object; fl.name = "Floor"; fl.data.materials.append(floor_m); detail.objects.link(fl)
bpy.context.scene.collection.objects.unlink(fl) if fl.name in scene.collection.objects else None


def area(name, loc, size, energy, color=(1, 1, 1), shape="RECTANGLE", sy=None):
    d = bpy.data.lights.new(name, "AREA"); d.energy = energy; d.shape = shape; d.size = size
    if sy: d.size_y = sy
    d.color = color
    o = bpy.data.objects.new(name, d); o.location = loc; detail.objects.link(o)
    tr = o.constraints.new("TRACK_TO"); tr.target = look; tr.track_axis = "TRACK_NEGATIVE_Z"; tr.up_axis = "UP_Y"
    return o


look = bpy.data.objects.new("Look", None); detail.objects.link(look)
key = area("Key", (0.16, 0.22, 0.20), 0.30, 0, (1.0, 0.93, 0.84), sy=0.12)
rim = area("Rim", (-0.18, -0.12, 0.10), 0.25, 0, (0.78, 0.86, 1.0), sy=0.06)
slit = area("Slit", (0.0, 0.0, 0.12), 0.01, 0, (1.0, 0.95, 0.88), sy=0.30)
fill = area("Fill", (0.0, 0.30, 0.05), 0.5, 0, (0.9, 0.92, 1.0))

cam_d = bpy.data.cameras.new("Cam"); cam_d.lens = 65
cam = bpy.data.objects.new("Cam", cam_d); detail.objects.link(cam); scene.camera = cam
cam_d.dof.use_dof = True; cam_d.dof.focus_object = look; cam_d.dof.aperture_fstop = 4.0
tr = cam.constraints.new("TRACK_TO"); tr.target = look; tr.track_axis = "TRACK_NEGATIVE_Z"; tr.up_axis = "UP_Y"


def kf(obj, prop, frame, value, idx=-1):
    setattr(obj, prop, value) if idx < 0 else None
    obj.keyframe_insert(prop, frame=frame)


def at(f, **k):
    for obj, attr, val in k.values():
        setattr(obj, attr, val); obj.keyframe_insert(attr, frame=f)


def light_energy(l, f, e): l.data.energy = e; l.data.keyframe_insert("energy", frame=f)


# continuous, ratio-correct rotation (ideal nominal kinematics; not a simulation result)
def drive(f, q):
    sun = q * 33.0
    for zs, zp, zr, sid in [(12, 21, 54, "stage1"), (12, 24, 60, "stage2")]:
        c = sun * zs / (zs + zr); p = c - (sun - c) * zs / zp; a = MODULE * (zs + zp) / 2 * MM
        for src, ob in pairs:
            if src == f"{sid}_sun": ob.rotation_euler = (0, sun, 0); ob.keyframe_insert("rotation_euler", frame=f)
        for k in range(3):
            tooth = next(ob for src, ob in pairs if src == f"{sid}_planet_{k}")
            phi = c + 2 * math.pi * k / 3; y = P[f"{sid}_planet_{k}"].matrix_world.translation.y
            tooth.matrix_world = tooth.matrix_world  # keep parent
        sun = c
    return


# animate by evaluating the same kinematics on the toothed copies in WORLD space
rest_y = {k: P[k].matrix_world.translation.y for k in P}
planet_obj = {src: ob for src, ob in pairs}
for src, ob in pairs: ob.parent = None


def pose(f, q):
    sun = q * 33.0
    for zs, zp, zr, sid in [(12, 21, 54, "stage1"), (12, 24, 60, "stage2")]:
        c = sun * zs / (zs + zr); p = c - (sun - c) * zs / zp; a = MODULE * (zs + zp) / 2 * MM
        s = planet_obj[f"{sid}_sun"]; s.location = (0, rest_y[f"{sid}_sun"], 0); s.rotation_euler = (0, sun, 0)
        for t in ("location", "rotation_euler"): s.keyframe_insert(t, frame=f)
        for k in range(3):
            ob = planet_obj[f"{sid}_planet_{k}"]; phi = c + 2 * math.pi * k / 3
            ob.location = (a * math.cos(phi), rest_y[f"{sid}_planet_{k}"], -a * math.sin(phi))
            ob.rotation_euler = (0, p + math.pi / zp, 0)
            for t in ("location", "rotation_euler"): ob.keyframe_insert(t, frame=f)
        r = planet_obj[f"stage{sid[-1]}_ring"]; r.location = (0, rest_y[f"{sid}_ring"], 0)
        r.keyframe_insert("location", frame=f)
        cut = bpy.data.objects[r["cutter"]]; cut.location = (0, rest_y[f"{sid}_ring"], 0); cut.keyframe_insert("location", frame=f)
        c1 = P[f"{sid}_carrier"]; c1.rotation_euler = (0, c, 0); c1.keyframe_insert("rotation_euler", frame=f)
        sun = c
    P["input_shaft"].rotation_euler = (0, q * 33.0, 0); P["input_shaft"].keyframe_insert("rotation_euler", frame=f)
    arm = [P["output_shaft"], P["upper_arm_link"], P["forearm_link"]]
    # these three rotate about the output axis (world Y through the origin)
    for ob in arm:
        loc = Vector(ob["rest"]) if "rest" in ob else ob.matrix_world.translation.copy()
        ob["rest"] = tuple(loc)
        rot = Vector((loc.x * math.cos(q) + loc.z * math.sin(q), loc.y, -loc.x * math.sin(q) + loc.z * math.cos(q)))
        ob.parent = None; ob.location = rot; ob.rotation_euler = (0, q, 0)
        for t in ("location", "rotation_euler"): ob.keyframe_insert(t, frame=f)


for ob in P.values(): ob.parent = None if ob.parent and ob.parent.name in ("OutputAxis",) else ob.parent
for ob in P.values():
    mw = ob.matrix_world.copy(); ob.parent = None; ob.matrix_world = mw
for ob in P.values():
    ob["rest"] = tuple(ob.matrix_world.translation)
hc.matrix_world = P["housing"].matrix_world.copy()

# ------------------------------------------------------------------ the two shots
def ease(t): return t * t * (3 - 2 * t)
def lerp(a, b, t): return a + (b - a) * t
def lerp3(a, b, t): return tuple(lerp(x, y, t) for x, y in zip(a, b))

if SEQ == "reveal":
    for f in range(1, FRAMES + 1):
        u = (f - 1) / (FRAMES - 1); pose(f, 0.35 * u)
        # slit of light sweeps over the shaft, then the key and rim bloom
        sweep = min(1.0, u / 0.28)
        slit.location = (lerp(-0.012, 0.012, ease(sweep)), 0.032, 0.05); slit.keyframe_insert("location", frame=f)
        light_energy(slit, f, 0.5 * math.sin(math.pi * min(1, u / 0.30)) ** 2 + 0)
        light_energy(key, f, 2.2 * ease(min(1, max(0, (u - 0.34) / 0.35))))
        light_energy(rim, f, 1.0 * ease(min(1, max(0, (u - 0.30) / 0.4))))
        light_energy(fill, f, 0.35 * ease(min(1, max(0, (u - 0.62) / 0.3))))
        # camera: macro on the shaft -> track along it -> into the stage -> pull back wide
        if u < 0.30: cp, lk = lerp3((0.030, 0.030, 0.014), (0.026, 0.026, 0.012), u / 0.30), (0.0, 0.032, 0.0)
        elif u < 0.58:
            t = ease((u - 0.30) / 0.28); cp = lerp3((0.026, 0.026, 0.012), (0.045, -0.004, 0.030), t); lk = lerp3((0.0, 0.032, 0.0), (0.0, -0.008, 0.0), t)
        else:
            t = ease((u - 0.58) / 0.42); cp = lerp3((0.045, -0.004, 0.030), (0.30, 0.38, 0.17), t); lk = lerp3((0.0, -0.008, 0.0), (0.07, 0.0, 0.0), t)
        cam.location = cp; look.location = lk
        cam.keyframe_insert("location", frame=f); look.keyframe_insert("location", frame=f)
        cam_d.lens = lerp(100, 55, ease(u)); cam_d.keyframe_insert("lens", frame=f)
        cam_d.dof.aperture_fstop = lerp(5.6, 8.0, ease(u)); cam_d.dof.keyframe_insert("aperture_fstop", frame=f)
else:  # finale
    for f in range(1, FRAMES + 1):
        u = (f - 1) / (FRAMES - 1); pose(f, 0.12 * math.sin(2 * math.pi * u * 0.5))
        az = math.radians(lerp(20, 150, ease(u))); el = math.radians(lerp(30, 20, ease(u))); dist = lerp(0.62, 0.46, ease(u))
        look.location = (0.09, 0.0, 0.0)
        cam.location = (look.location.x + dist * math.cos(el) * math.cos(az), look.location.y + dist * math.cos(el) * math.sin(az), dist * math.sin(el))
        cam_d.lens = 60; cam.keyframe_insert("location", frame=f); look.keyframe_insert("location", frame=f)
        for l, e in ((key, 2.4), (rim, 1.0), (fill, 0.4), (slit, 0)): light_energy(l, f, e)

# ------------------------------------------------------------------ output
out = HP / "renders"; out.mkdir(exist_ok=True)
if still:
    scene.frame_set(still); scene.render.filepath = str(out / f"{SEQ}_still_{still:03d}.png")
    scene.render.image_settings.file_format = "PNG"; bpy.ops.render.render(write_still=True)
else:
    scene.render.image_settings.file_format = "FFMPEG"
    ff = scene.render.ffmpeg; ff.format = "WEBM"; ff.codec = "WEBM"; ff.constant_rate_factor = "MEDIUM"; ff.gopsize = 1
    scene.render.fps = FPS; scene.render.filepath = str(out / f"{SEQ}_")
    bpy.ops.render.render(animation=True)
bpy.ops.wm.save_as_mainfile(filepath=str(HP / "motionproof_homepage_cinematic.blend"))
