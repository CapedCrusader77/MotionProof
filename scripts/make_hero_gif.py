"""Render docs/images/hero.gif: the reference gearbox and arm in 3D, rendered with MuJoCo.

Geometry follows the reference design's parameters (two planetary stages, module 0.5 mm,
12/21/54 and 12/24/60 teeth, 33:1; arm links of 200 mm and 150 mm). Gear teeth are generated
here for the picture (simple trapezoidal profiles); the analysis itself uses pitch cylinders.
Kinematics are exact: ring fixed, carrier = sun * z_s / (z_s + z_r), planet spin from rolling.

    uv run python scripts/make_hero_gif.py
"""

from __future__ import annotations

import math
import tempfile
from pathlib import Path

import mujoco
import numpy as np
import trimesh
from PIL import Image, ImageDraw, ImageFont
from shapely.geometry import Polygon as SPoly

OUT = Path(__file__).resolve().parents[1] / "docs" / "images" / "hero.gif"
W, H = 800, 380
FRAMES = 64
S = 0.001  # mm to m
MODULE = 0.5
import os  # noqa: E402

AZ = float(os.environ.get("HERO_AZ", 128))
EL = float(os.environ.get("HERO_EL", -18))
DIST = float(os.environ.get("HERO_DIST", 0.085))
LOOK = [float(v) for v in os.environ.get("HERO_LOOK", "0.0 -0.03 0.004").split()]
FRAMES = int(os.environ.get("HERO_FRAMES", FRAMES))
STAGES = [(12, 21, 54, -40.0, 8.0), (12, 24, 60, -16.0, 8.0)]  # zs, zp, zr, y0 (exploded), width


def gear_outline(z: int, internal: bool = False, outer_r: float | None = None) -> SPoly:
    r = MODULE * z / 2
    add, ded = MODULE, 1.25 * MODULE
    pts = []
    for k in range(z):
        a0 = 2 * math.pi * k / z
        w = 2 * math.pi / z
        r_tip, r_root = (r - add, r + ded) if internal else (r + add, r - ded)
        for frac, rad in ((0.0, r_root), (0.18, r_root), (0.36, r_tip), (0.64, r_tip),
                          (0.82, r_root)):
            a = a0 + frac * w
            pts.append((rad * math.cos(a), rad * math.sin(a)))
    teeth = SPoly(pts)
    if internal:
        assert outer_r is not None
        ring = SPoly([(outer_r * math.cos(t), outer_r * math.sin(t))
                      for t in np.linspace(0, 2 * math.pi, 160, endpoint=False)])
        return ring.difference(teeth)
    return teeth


def extrude(poly: SPoly, width: float, hole: float = 0.0) -> trimesh.Trimesh:
    """Extrude with CadQuery (exact solid), tessellate, and turn the axis to +y."""
    import cadquery as cq

    ext = list(poly.exterior.coords)[:-1]
    wp = cq.Workplane("XY").polyline(ext).close().extrude(width)
    for interior in poly.interiors:
        wp = wp.cut(cq.Workplane("XY").polyline(list(interior.coords)[:-1]).close()
                    .extrude(width))
    if hole:
        wp = wp.cut(cq.Workplane("XY").circle(hole).extrude(width))
    with tempfile.NamedTemporaryFile(suffix=".stl", delete=False) as fh:
        name = fh.name
    cq.exporters.export(wp, name, tolerance=0.02, angularTolerance=0.1)
    m = trimesh.load(name)
    m.apply_transform(trimesh.transformations.rotation_matrix(-math.pi / 2, [1, 0, 0]))
    m.apply_scale(S)
    return m


def build(tmp: Path) -> str:
    meshes: dict[str, trimesh.Trimesh] = {}
    for i, (zs, zp, zr, _, wd) in enumerate(STAGES, start=1):
        meshes[f"sun{i}"] = extrude(gear_outline(zs), wd, hole=1.0)
        meshes[f"planet{i}"] = extrude(gear_outline(zp), wd, hole=1.2)
        meshes[f"ring{i}"] = extrude(
            gear_outline(zr, internal=True, outer_r=MODULE * zr / 2 + 2.6), wd)
        a = MODULE * (zs + zp) / 2
        plate = SPoly([(a * 1.18 * math.cos(t), a * 1.18 * math.sin(t))
                       for t in np.linspace(0, 2 * math.pi, 120, endpoint=False)])
        meshes[f"carrier{i}"] = extrude(plate, 1.2, hole=1.0)
    for name, m in meshes.items():
        m.export(tmp / f"{name}.stl")
    asset = "\n".join(f'<mesh name="{n}" file="{tmp.as_posix()}/{n}.stl"/>' for n in meshes)
    nc = 'contype="0" conaffinity="0"'
    bodies = []

    def mocap(name: str, mesh: str, mat: str) -> None:
        bodies.append(f'<body name="{name}" mocap="true"><geom type="mesh" mesh="{mesh}" '
                      f'material="{mat}" {nc}/></body>')

    for i in (1, 2):
        mocap(f"sun{i}", f"sun{i}", "brass")
        mocap(f"ring{i}", f"ring{i}", "steel_dark")
        mocap(f"carrier{i}", f"carrier{i}", "steel")
        for k in range(3):
            mocap(f"planet{i}_{k}", f"planet{i}", "steel")
    bodies.append(
        f'<body name="arm" mocap="true">'
        f'<geom type="cylinder" fromto="0 -0.006 0 0 0.052 0" size="0.004" material="steel" {nc}/>'
        f'<geom type="box" pos="0.1 0.044 0" size="0.11 0.006 0.009" material="anodised" {nc}/>'
        f'<geom type="cylinder" fromto="0.2 0.036 0 0.2 0.058 0" size="0.011" material="brass" {nc}/>'
        f'<geom type="box" pos="0.275 0.055 0" size="0.085 0.005 0.0075" material="anodised" {nc}/>'
        f'</body>')
    return f"""
<mujoco>
  <visual>
    <global offwidth="{W * 2}" offheight="{H * 2}"/>
    <quality shadowsize="4096" offsamples="8"/>
    <headlight ambient="0.12 0.12 0.14" diffuse="0.25 0.25 0.28" specular="0.1 0.1 0.1"/>
    <rgba haze="0.05 0.06 0.08 1"/>
  </visual>
  <asset>
    {asset}
    <texture name="sky" type="skybox" builtin="gradient" rgb1="0.07 0.08 0.10" rgb2="0.02 0.02 0.03" width="512" height="512"/>
    <texture name="floor" type="2d" builtin="checker" rgb1="0.055 0.06 0.07" rgb2="0.045 0.05 0.06" width="512" height="512" mark="edge" markrgb="0.09 0.1 0.12"/>
    <material name="floor" texture="floor" texrepeat="40 40" reflectance="0.25"/>
    <material name="steel" rgba="0.62 0.65 0.69 1" specular="0.9" shininess="0.85" reflectance="0.15"/>
    <material name="steel_dark" rgba="0.34 0.36 0.40 0.28" specular="0.6" shininess="0.6" reflectance="0.08"/>
    <material name="brass" rgba="0.80 0.62 0.30 1" specular="1" shininess="0.9" reflectance="0.2"/>
    <material name="motor" rgba="0.10 0.11 0.12 1" specular="0.3" shininess="0.3"/>
    <material name="anodised" rgba="0.16 0.30 0.42 1" specular="0.7" shininess="0.7" reflectance="0.1"/>
  </asset>
  <worldbody>
    <light pos="0.25 -0.25 0.45" dir="-0.5 0.5 -1" diffuse="0.9 0.88 0.84" specular="0.4 0.4 0.4" castshadow="true"/>
    <light pos="-0.3 0.2 0.25" dir="1 -0.4 -0.6" diffuse="0.25 0.32 0.45" specular="0.1 0.1 0.15" castshadow="false"/>
    {chr(10).join(bodies)}
  </worldbody>
</mujoco>"""


def quat_y(a: float) -> np.ndarray:
    """Rotation by a about +y (the gearbox axis)."""
    return np.array([math.cos(a / 2), 0.0, math.sin(a / 2), 0.0])


def main() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="mp_hero_"))
    model = mujoco.MjModel.from_xml_string(build(tmp))
    data = mujoco.MjData(model)
    ids = {model.body(b).name: int(model.body_mocapid[b]) for b in range(model.nbody)
           if model.body_mocapid[b] >= 0}
    r = mujoco.Renderer(model, H * 2, W * 2)
    cam = mujoco.MjvCamera()
    cam.lookat[:] = LOOK
    cam.distance = DIST
    font_b = ImageFont.truetype("C:/Windows/Fonts/bahnschrift.ttf", 40)
    font_b.set_variation_by_name("SemiBold")
    font_s = ImageFont.truetype("C:/Windows/Fonts/bahnschrift.ttf", 18)
    font_s.set_variation_by_name("Light")
    font_m = ImageFont.truetype("C:/Windows/Fonts/consola.ttf", 14)

    frames = []
    for f in range(FRAMES):
        t = f / FRAMES
        out = 0.30 * math.sin(2 * math.pi * t)          # output (arm) angle, rad
        sun = out * 33.0                                # motor drives the stage-1 sun
        for i, (zs, zp, zr, y0, _wd) in enumerate(STAGES, start=1):
            carrier = sun * zs / (zs + zr)
            planet = carrier - (sun - carrier) * zs / zp
            a = MODULE * (zs + zp) / 2 * S
            data.mocap_pos[ids[f"sun{i}"]] = [0, y0 * S, 0]
            data.mocap_quat[ids[f"sun{i}"]] = quat_y(sun)
            data.mocap_pos[ids[f"ring{i}"]] = [0, y0 * S, 0]
            data.mocap_quat[ids[f"ring{i}"]] = quat_y(math.pi / zr)
            data.mocap_pos[ids[f"carrier{i}"]] = [0, (y0 + 8.2) * S, 0]
            data.mocap_quat[ids[f"carrier{i}"]] = quat_y(carrier)
            for k in range(3):
                phi = carrier + 2 * math.pi * k / 3
                data.mocap_pos[ids[f"planet{i}_{k}"]] = [a * math.cos(phi), y0 * S,
                                                         -a * math.sin(phi)]
                data.mocap_quat[ids[f"planet{i}_{k}"]] = quat_y(planet + math.pi / zp)
            sun = carrier                               # next stage is driven by this carrier
        data.mocap_pos[ids["arm"]] = [0, 0, 0]
        data.mocap_quat[ids["arm"]] = quat_y(out)
        mujoco.mj_forward(model, data)

        cam.azimuth = AZ + 10 * math.sin(2 * math.pi * t)
        cam.elevation = EL + 3 * math.cos(2 * math.pi * t)
        r.update_scene(data, cam)
        img = Image.fromarray(r.render()).resize((W, H), Image.LANCZOS)

        d = ImageDraw.Draw(img)
        d.text((40, 30), "MotionProof", font=font_b, fill=(236, 232, 224))
        d.text((42, 78), "manufacturing tolerances in, motion out", font=font_s,
               fill=(150, 156, 166))
        spec = f"2-stage planetary   33:1   module 0.5   output {math.degrees(out):+5.1f}°"
        d.text((42, H - 38), spec, font=font_m, fill=(120, 128, 140))
        frames.append(img)

    strip = Image.new("RGB", (W, H * 3))
    for n, fi in enumerate((0, FRAMES // 3, 2 * FRAMES // 3)):
        strip.paste(frames[fi], (0, n * H))
    palette = strip.quantize(96, method=Image.Quantize.MEDIANCUT)
    q = [fr.quantize(palette=palette, dither=Image.Dither.NONE) for fr in frames]
    q[0].save(OUT, save_all=True, append_images=q[1:], duration=55, loop=0, optimize=True)
    frames[FRAMES // 4].save(os.environ.get("HERO_PREVIEW", str(tmp / "preview.png")))
    print(OUT, OUT.stat().st_size // 1024, "KB", tmp / "preview.png")


if __name__ == "__main__":
    main()
