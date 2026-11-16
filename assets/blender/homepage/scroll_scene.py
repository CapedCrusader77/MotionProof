"""Scroll-sequence variant of blender_hero_scene.py (per-frame look, lens, f-stop, exposure).
Blender (Cycles) scene for the README hero render. Run by scripts/make_hero_render.py:

    blender -b --factory-startup -P scripts/blender_hero_scene.py -- <job.json>

The job file lists the meshes (STL, metres, gear axis along +Y) with a material each, and the
per-frame position and Y rotation of every part. Frames are written as PNG.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Euler, Vector

job = json.loads(Path(sys.argv[sys.argv.index("--") + 1]).read_text(encoding="utf-8"))
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene


def principled(name: str, color: tuple[float, float, float], metallic: float, rough: float,
               aniso: float = 0.0, alpha: float = 1.0, coat: float = 0.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*color, 1.0)
    b.inputs["Metallic"].default_value = metallic
    b.inputs["Roughness"].default_value = rough
    if "Anisotropic" in b.inputs:
        b.inputs["Anisotropic"].default_value = aniso
    if "Coat Weight" in b.inputs:
        b.inputs["Coat Weight"].default_value = coat
    if alpha < 1.0:
        b.inputs["Alpha"].default_value = alpha
        if hasattr(m, "surface_render_method"):
            m.surface_render_method = "DITHERED"
    return m


MATS = {
    "steel": principled("steel", (0.62, 0.63, 0.65), 1.0, 0.22, aniso=0.5),
    "steel_dark": principled("steel_dark", (0.32, 0.33, 0.35), 1.0, 0.35),
    "brass": principled("brass", (0.86, 0.62, 0.30), 1.0, 0.18),
    "anodised": principled("anodised", (0.52, 0.11, 0.06), 0.55, 0.34, coat=0.4),
    "black": principled("black", (0.012, 0.012, 0.014), 0.0, 0.55),
    "glass": principled("glass", (0.50, 0.52, 0.55), 1.0, 0.25, alpha=0.18),
}

objs = {}
for part in job["parts"]:
    bpy.ops.wm.stl_import(filepath=part["file"])
    o = bpy.context.selected_objects[0]
    o.name = part["name"]
    bpy.ops.object.shade_auto_smooth(angle=math.radians(35))
    mod = o.modifiers.new("bevel", "BEVEL")
    mod.width = part.get("bevel", 0.00012)
    mod.segments = 2
    mod.limit_method = "ANGLE"
    o.data.materials.append(MATS[part["material"]])
    o.rotation_mode = "XYZ"
    objs[o.name] = o

# floor: dark, slightly glossy, catches soft reflections and contact shadows
bpy.ops.mesh.primitive_plane_add(size=30, location=(0, 0, job["floor_z"]))
floor = bpy.context.active_object
floor.data.materials.append(principled("floor", (0.010, 0.011, 0.013), 0.0, 0.42))

# vermilion reveal ring on the floor (staging only)
bpy.ops.mesh.primitive_torus_add(major_radius=0.17, minor_radius=0.0006, major_segments=160, minor_segments=8, location=(0.01, -0.03, job["floor_z"] + 0.0006))
ring = bpy.context.active_object
ring.data.materials.append(principled("vermilion_ring", (0.78, 0.15, 0.06), 0.0, 0.3))

# world: near-black studio
world = bpy.data.worlds.new("w")
scene.world = world
world.use_nodes = True
world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.004, 0.0045, 0.006, 1)
world.node_tree.nodes["Background"].inputs["Strength"].default_value = 1.0


def area(name: str, loc, size: float, energy: float, color=(1, 1, 1)):
    d = bpy.data.lights.new(name, "AREA")
    d.size = size
    d.energy = energy
    d.color = color
    o = bpy.data.objects.new(name, d)
    scene.collection.objects.link(o)
    o.location = loc
    direction = Vector((0.0, -0.02, 0.0)) - Vector(loc)
    o.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


area("key", (0.18, 0.10, 0.22), 0.20, 4.0, (1.0, 0.95, 0.88))
area("rim", (-0.20, -0.18, 0.10), 0.12, 3.0, (0.70, 0.80, 1.0))
area("fill", (0.05, -0.25, -0.02), 0.25, 0.6, (0.85, 0.9, 1.0))
area("top", (0.0, -0.02, 0.30), 0.35, 1.0)
area("warm", (-0.14, 0.16, 0.08), 0.10, 2.2, (1.0, 0.62, 0.38))

cam_data = bpy.data.cameras.new("cam")
cam_data.lens = job["lens"]
cam_data.dof.use_dof = True
cam_data.dof.aperture_fstop = job.get("fstop", 4.0)
cam = bpy.data.objects.new("cam", cam_data)
scene.collection.objects.link(cam)
scene.camera = cam
target = bpy.data.objects.new("target", None)
scene.collection.objects.link(target)
target.location = job["look"]
cam_data.dof.focus_object = target
track = cam.constraints.new("TRACK_TO")
track.target = target
track.track_axis = "TRACK_NEGATIVE_Z"
track.up_axis = "UP_Y"

scene.render.engine = "CYCLES"
scene.cycles.samples = job["samples"]
scene.cycles.use_denoising = True
if job.get("gpu", True):
    prefs = bpy.context.preferences.addons["cycles"].preferences
    for kind in ("OPTIX", "CUDA", "HIP", "METAL", "ONEAPI"):
        try:
            prefs.compute_device_type = kind
            prefs.get_devices()
        except TypeError:
            continue
        if any(d.type == kind for d in prefs.devices):
            for d in prefs.devices:
                d.use = d.type == kind
            scene.cycles.device = "GPU"
            break
scene.render.resolution_x, scene.render.resolution_y = job["size"]
scene.render.film_transparent = False
scene.view_settings.view_transform = "AgX"
scene.view_settings.look = "AgX - Medium High Contrast"
scene.render.image_settings.file_format = "PNG"

out = Path(job["out"])
out.mkdir(parents=True, exist_ok=True)
start = int(job.get("start", 0))
for f, frame in enumerate(job["frames"]):
    if f < start:
        continue
    for name, (pos, ry) in frame["parts"].items():
        o = objs[name]
        o.location = pos
        o.rotation_euler = Euler((0.0, ry, 0.0), "XYZ")
    cam.location = frame["camera"]
    if "look" in frame: target.location = frame["look"]
    if "lens" in frame: cam_data.lens = frame["lens"]
    if "fstop" in frame: cam_data.dof.aperture_fstop = frame["fstop"]
    scene.view_settings.exposure = frame.get("exposure", 0.0)
    scene.render.filepath = str(out / f"{f:03d}.png")
    bpy.ops.render.render(write_still=True)
    print(f"frame {f} done", flush=True)
