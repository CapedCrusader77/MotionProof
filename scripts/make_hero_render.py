"""Render docs/images/hero.gif with Blender Cycles.

Builds the reference gearbox (two planetary stages, module 0.5 mm, 12/21/54 and 12/24/60
teeth, 33:1) and arm with CadQuery, computes exact planetary kinematics per frame, has Blender
render the frames, then adds the title and writes the GIF. The ring gears are cut away so the
planets are visible. Teeth are simple trapezoidal profiles drawn for the picture; the analysis
itself uses pitch cylinders.

    uv run python scripts/make_hero_render.py --blender E:/Blender/blender.exe
"""

from __future__ import annotations

import argparse
import json
import math
import subprocess
import tempfile
from pathlib import Path

import cadquery as cq
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "images" / "hero.gif"
MODULE = 0.5
STAGES = [(12, 21, 54, -40.0, 8.0), (12, 24, 60, -16.0, 8.0)]  # zs, zp, zr, y0 (mm), width
W, H = 720, 342


def gear_points(z: int, internal: bool = False) -> list[tuple[float, float]]:
    r = MODULE * z / 2
    add, ded = MODULE, 1.25 * MODULE
    pts = []
    for k in range(z):
        a0, w = 2 * math.pi * k / z, 2 * math.pi / z
        r_tip, r_root = (r - add, r + ded) if internal else (r + add, r - ded)
        for frac, rad in ((0.0, r_root), (0.17, r_root), (0.35, r_tip), (0.65, r_tip),
                          (0.83, r_root)):
            a = a0 + frac * w
            pts.append((rad * math.cos(a), rad * math.sin(a)))
    return pts


def to_y_axis(wp: cq.Workplane) -> cq.Workplane:
    """Solids are built along +Z; the gearbox axis in the model is +Y."""
    return wp.rotate((0, 0, 0), (1, 0, 0), -90)


def spur(z: int, width: float, bore: float) -> cq.Workplane:
    g = cq.Workplane("XY").polyline(gear_points(z)).close().extrude(width)
    return to_y_axis(g.cut(cq.Workplane("XY").circle(bore).extrude(width)))


def ring_cutaway(z: int, width: float) -> cq.Workplane:
    outer = MODULE * z / 2 + 2.8
    body = cq.Workplane("XY").circle(outer).extrude(width)
    body = body.cut(cq.Workplane("XY").polyline(gear_points(z, internal=True)).close()
                    .extrude(width))
    # remove the half facing the camera so the planets show
    body = body.cut(cq.Workplane("XY").center(0, -outer).rect(3 * outer, 2 * outer)
                    .extrude(width))
    return to_y_axis(body)


def carrier(a: float) -> cq.Workplane:
    plate = (cq.Workplane("XY").circle(a + 3.0).extrude(1.6)
             .faces(">Z").workplane().circle(1.4).cutThruAll())
    pins = cq.Workplane("XY").polarArray(a, 0, 360, 3).circle(1.1).extrude(-8.0)
    return to_y_axis(plate.union(pins))


def export(wp: cq.Workplane, path: Path) -> str:
    cq.exporters.export(wp.val().scale(0.001), str(path), tolerance=0.01,
                        angularTolerance=0.08)
    return str(path)


def build_parts(tmp: Path) -> list[dict]:
    parts = []
    for i, (zs, zp, zr, _y0, wd) in enumerate(STAGES, start=1):
        a = MODULE * (zs + zp) / 2
        parts += [
            {"name": f"sun{i}", "file": export(spur(zs, wd, 1.0), tmp / f"sun{i}.stl"),
             "material": "brass"},
            {"name": f"ring{i}", "file": export(ring_cutaway(zr, wd), tmp / f"ring{i}.stl"),
             "material": "steel_dark"},
            {"name": f"carrier{i}", "file": export(carrier(a), tmp / f"carrier{i}.stl"),
             "material": "steel_dark"},
        ]
        planet = export(spur(zp, wd, 1.15), tmp / f"planet{i}.stl")
        parts += [{"name": f"planet{i}_{k}", "file": planet, "material": "steel"}
                  for k in range(3)]
    motor = (cq.Workplane("XY").box(42.3, 42.3, 40).edges("|Z").fillet(3.0)
             .faces(">Z").workplane().circle(11).extrude(2)
             .faces("<Z").workplane().rect(31, 31, forConstruction=True).vertices()
             .hole(3, 4))
    parts.append({"name": "motor", "file": export(to_y_axis(motor), tmp / "motor.stl"),
                  "material": "black", "bevel": 0.0004})
    shaft = cq.Workplane("XY").circle(4.0).extrude(64)
    parts.append({"name": "shaft", "file": export(to_y_axis(shaft), tmp / "shaft.stl"),
                  "material": "steel"})
    upper = (cq.Workplane("XY").box(220, 18, 12).edges("|Z").fillet(8.9)
             .faces(">Z").workplane().pushPoints([(-100, 0), (100, 0)]).hole(8))
    fore = (cq.Workplane("XY").box(170, 15, 10).edges("|Z").fillet(7.4)
            .faces(">Z").workplane().pushPoints([(-75, 0)]).hole(7))
    arm = (to_y_axis(upper).translate((100, 44, 0))
           .union(to_y_axis(fore).translate((275, 56, 0)))
           .union(to_y_axis(cq.Workplane("XY").circle(11).extrude(24)).translate((200, 38, 0))))
    parts.append({"name": "arm", "file": export(arm, tmp / "arm.stl"),
                  "material": "anodised", "bevel": 0.0005})
    return parts


def frames(n: int) -> list[dict]:
    out = []
    for f in range(n):
        t = f / n
        q_out = 0.30 * math.sin(2 * math.pi * t)
        sun = q_out * 33.0
        poses: dict[str, tuple[list[float], float]] = {}
        for i, (zs, zp, zr, y0, _wd) in enumerate(STAGES, start=1):
            c = sun * zs / (zs + zr)
            p = c - (sun - c) * zs / zp
            a = MODULE * (zs + zp) / 2 * 0.001
            y = y0 * 0.001
            poses[f"sun{i}"] = ([0, y, 0], sun)
            poses[f"ring{i}"] = ([0, y, 0], 0.0)
            poses[f"carrier{i}"] = ([0, y + 0.0098, 0], c)
            for k in range(3):
                phi = c + 2 * math.pi * k / 3
                # rotation about +Y takes +X towards -Z
                poses[f"planet{i}_{k}"] = ([a * math.cos(phi), y, -a * math.sin(phi)],
                                           p + math.pi / zp)
            sun = c
        poses["motor"] = ([0, -0.082, 0], 0.0)
        poses["shaft"] = ([0, -0.008, 0], q_out)
        poses["arm"] = ([0, 0, 0], q_out)
        az = math.radians(142 + 8 * math.sin(2 * math.pi * t))
        el = math.radians(24 - 3 * math.cos(2 * math.pi * t))
        dist, look = 0.19, (-0.004, -0.034, 0.0)
        cam = [look[0] + dist * math.cos(el) * math.cos(az),
               look[1] + dist * math.cos(el) * math.sin(az),
               look[2] + dist * math.sin(el)]
        out.append({"parts": poses, "camera": cam, "q_out": q_out})
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--blender", default="blender")
    ap.add_argument("--frames", type=int, default=48)
    ap.add_argument("--samples", type=int, default=64)
    ap.add_argument("--work", default=None)
    ap.add_argument("--assemble-only", action="store_true")
    ap.add_argument("--step", type=int, default=1, help="use every n-th rendered frame")
    args = ap.parse_args()
    tmp = Path(args.work or tempfile.mkdtemp(prefix="mp_hero_"))
    tmp.mkdir(parents=True, exist_ok=True)
    fr = frames(args.frames)
    if not args.assemble_only:
        job = {"parts": build_parts(tmp), "frames": fr, "out": str(tmp / "frames"),
               "size": [W * 2, H * 2], "samples": args.samples, "lens": 50, "fstop": 11.0,
               "look": [-0.004, -0.034, 0.0], "floor_z": -0.0215}
        (tmp / "job.json").write_text(json.dumps(job), encoding="utf-8")
        subprocess.run([args.blender, "-b", "--factory-startup", "-P",
                        str(ROOT / "scripts" / "blender_hero_scene.py"), "--",
                        str(tmp / "job.json")], check=True)
    bold = ImageFont.truetype("C:/Windows/Fonts/bahnschrift.ttf", 40)
    bold.set_variation_by_name("SemiBold")
    light = ImageFont.truetype("C:/Windows/Fonts/bahnschrift.ttf", 18)
    light.set_variation_by_name("Light")
    mono = ImageFont.truetype("C:/Windows/Fonts/consola.ttf", 13)
    imgs = []
    for f, frame in list(enumerate(fr))[:: args.step]:
        im = Image.open(tmp / "frames" / f"{f:03d}.png").convert("RGB").resize((W, H),
                                                                                Image.LANCZOS)
        d = ImageDraw.Draw(im)
        d.text((38, 28), "MotionProof", font=bold, fill=(238, 234, 226))
        d.text((40, 76), "manufacturing tolerances in, motion out", font=light,
               fill=(150, 156, 166))
        d.text((40, H - 34), f"2-stage planetary   33:1   module 0.5   "
               f"output {math.degrees(frame["q_out"]):+5.1f}°", font=mono, fill=(196, 200, 208))
        imgs.append(im)
    strip = Image.new("RGB", (W, H * 3))
    for n, fi in enumerate((0, len(imgs) // 3, 2 * len(imgs) // 3)):
        strip.paste(imgs[fi], (0, n * H))
    pal = strip.quantize(128, method=Image.Quantize.MEDIANCUT)
    q = [im.quantize(palette=pal, dither=Image.Dither.FLOYDSTEINBERG) for im in imgs]
    q[0].save(OUT, save_all=True, append_images=q[1:], duration=70 * args.step, loop=0, optimize=True)
    imgs[len(imgs) // 4].save(tmp / "preview.png")
    print(OUT, OUT.stat().st_size // 1024, "KB", (tmp / "preview.png").as_posix())


if __name__ == "__main__":
    main()
