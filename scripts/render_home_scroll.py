"""Frames for the homepage scroll sequence. Geometry and kinematics: scripts/make_hero_render.py
(toothed gears are render-only detail; the engine models pitch cylinders).

    uv run python scripts/render_home_scroll.py --blender E:/Blender/blender.exe --work E:/mp_scroll \
        [--frames 120] [--samples 48] [--only 0,30,60] [--size 1600x900]
"""
import argparse, json, math, subprocess, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import make_hero_render as m

ap = argparse.ArgumentParser()
ap.add_argument("--blender", default="blender"); ap.add_argument("--work", required=True)
ap.add_argument("--frames", type=int, default=240); ap.add_argument("--samples", type=int, default=48)
ap.add_argument("--only", default=""); ap.add_argument("--size", default="1600x900")
a = ap.parse_args()
N = a.frames
W, H = (int(v) for v in a.size.split("x"))
base = m.frames(4 * N)[:N]  # rising quarter of the 33:1 sweep: output 0 -> 0.30 rad, monotonic
ease = lambda t: t * t * (3 - 2 * t)
lerp = lambda p, q, t: p + (q - p) * t
look0, look1, look2 = (-0.012, -0.030, 0.0), (-0.004, -0.034, 0.0), (0.045, -0.020, 0.0)

def cam(az, el, d, look):
    az, el = math.radians(az), math.radians(el)
    return [look[0] + d * math.cos(el) * math.cos(az), look[1] + d * math.cos(el) * math.sin(az), look[2] + d * math.sin(el)]

# shot: macro on the planet stage (dark, light grows) -> slow orbit -> wide with the arm
KEYS = [  # u, az, el, dist, lens, fstop, exposure, look  (macro -> reveal -> exploded -> reassembly -> motion -> finale)
    (0.00, 168, 6, 0.050, 85, 2.8, -2.6, look0),
    (0.08, 160, 9, 0.055, 85, 3.2, -0.3, look0),
    (0.18, 148, 14, 0.105, 65, 5.0, 0.0, look1),
    (0.30, 134, 20, 0.230, 50, 9.0, 0.0, look1),
    (0.42, 128, 18, 0.330, 42, 11.0, 0.0, (0.0, -0.025, 0.0)),
    (0.56, 108, 16, 0.370, 40, 11.0, 0.0, (0.0, -0.020, 0.0)),
    (0.66, 120, 18, 0.340, 42, 11.0, 0.0, (0.0, -0.025, 0.0)),
    (0.80, 150, 12, 0.130, 60, 5.6, 0.0, look1),
    (0.90, 138, 20, 0.260, 46, 9.0, 0.0, look1),
    (1.00, 112, 22, 0.360, 40, 11.0, 0.0, look2),
]
# explode: axial (+Y) offsets by rank along the gearbox axis, parts keep orientation
ORDER = ["motor", "sun1", "planet1", "carrier1", "ring1", "sun2", "planet2", "carrier2", "ring2", "shaft", "arm"]
def spread(u):  # 0 assembled, 1 fully separated; separate 0.34-0.46, hold, return 0.58-0.70
    return ease(clamp((u - 0.34) / 0.12)) * (1 - ease(clamp((u - 0.58) / 0.12)))
def clamp(v): return min(1.0, max(0.0, v))
def explode(parts, u):
    e = spread(u)
    out = {}
    for name, (pos, ry) in parts.items():
        key = name.split("_")[0]
        rank = ORDER.index(key) if key in ORDER else 5
        out[name] = ([pos[0], pos[1] + e * (rank - 5) * 0.016, pos[2]], ry)
    return out
def at(u):
    for k0, k1 in zip(KEYS, KEYS[1:]):
        if k0[0] <= u <= k1[0]:
            t = ease((u - k0[0]) / (k1[0] - k0[0]))
            vals = [lerp(x, y, t) for x, y in zip(k0[1:7], k1[1:7])]
            look = tuple(lerp(x, y, t) for x, y in zip(k0[7], k1[7]))
            return vals, look
    return list(KEYS[-1][1:7]), KEYS[-1][7]
fr = []
for i, f in enumerate(base):
    u = i / (N - 1)
    (az, el, d, lens, fs, ex), look = at(u)
    fr.append({"parts": explode(f["parts"], u), "camera": cam(az, el, d, look), "look": list(look), "lens": lens, "fstop": fs, "exposure": ex})
tmp = Path(a.work); tmp.mkdir(parents=True, exist_ok=True)
only = [int(v) for v in a.only.split(",") if v]
job = {"parts": m.build_parts(tmp), "frames": [fr[i] for i in only] if only else fr, "out": str(tmp / ("test" if only else "frames")),
       "size": [W, H], "samples": a.samples, "lens": 50, "fstop": 8.0, "look": list(look0), "floor_z": -0.0215}
(tmp / "job.json").write_text(json.dumps(job), encoding="utf-8")
subprocess.run([a.blender, "-b", "--factory-startup", "-P", str(m.ROOT / "assets/blender/homepage/scroll_scene.py"), "--", str(tmp / "job.json")], check=True)
