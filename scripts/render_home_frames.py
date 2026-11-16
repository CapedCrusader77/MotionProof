"""Clean (text-free) Cycles frames of the reference gearbox for the web homepage.

    uv run python scripts/render_home_frames.py --blender E:/Blender/blender.exe --work <dir>

Reuses scripts/make_hero_render.py geometry and kinematics; writes <dir>/frames/NNN.png.
"""
import argparse, json, subprocess, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import make_hero_render as m

ap = argparse.ArgumentParser()
ap.add_argument("--blender", default="blender")
ap.add_argument("--work", required=True)
ap.add_argument("--frames", type=int, default=48)
ap.add_argument("--samples", type=int, default=48)
a = ap.parse_args()
tmp = Path(a.work); tmp.mkdir(parents=True, exist_ok=True)
fr = m.frames(a.frames)
job = {"parts": m.build_parts(tmp), "frames": fr, "out": str(tmp / "frames"),
       "size": [m.W * 2, m.H * 2], "samples": a.samples, "lens": 50, "fstop": 11.0,
       "look": [-0.004, -0.034, 0.0], "floor_z": -0.0215}
(tmp / "job.json").write_text(json.dumps(job), encoding="utf-8")
subprocess.run([a.blender, "-b", "--factory-startup", "-P",
                str(m.ROOT / "scripts" / "blender_hero_scene.py"), "--", str(tmp / "job.json")], check=True)
