"""Rebuild docs/images/workflow-tour.gif from the product screenshots in docs/images.

The screenshots come from frontend/tools/capture-screens.mjs. Each frame is shown for 1.8 s, in the
order a project is worked: project, assembly, tolerances, virtual assemblies, robustness,
sensitivity, model trust, benchmarks.

    uv run python scripts/make_tour.py
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image

IMAGES = Path(__file__).resolve().parents[1] / "docs" / "images"
ORDER = ["projects", "workbench", "tolerances", "virtual", "robustness", "sensitivity", "trust",
         "benchmarks"]
SIZE = (960, 600)

frames = []
for name in ORDER:
    im = Image.open(IMAGES / f"{name}.png").convert("RGB").resize(SIZE, Image.Resampling.LANCZOS)
    # one adaptive palette per frame keeps the thin text and chart colours of each screen
    frames.append(im.quantize(colors=256, method=Image.Quantize.MEDIANCUT,
                              dither=Image.Dither.NONE))
out = IMAGES / "workflow-tour.gif"
frames[0].save(out, save_all=True, append_images=frames[1:], duration=1800, loop=0, optimize=True)
print("wrote", out, f"{out.stat().st_size / 1e6:.1f} MB, {len(frames)} frames")
