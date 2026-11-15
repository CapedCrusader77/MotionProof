"""Render docs/images/hero.gif: a drafting-sheet banner for the README.

Left: two meshing teeth at 10:1 with the backlash gap dimensioned. The driving tooth moves back
and forth; the driven tooth only follows once the gap has closed (a dead band of width j).
Middle: the resulting output-versus-input trace, drawn as it happens: the backlash loop.
Right: the title block.

Kinematic illustration of the dead band only; no simulation output is shown.

    uv run python scripts/make_hero_gif.py
"""

from __future__ import annotations

import io
import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Circle, Polygon, Rectangle  # noqa: E402
from PIL import Image  # noqa: E402

OUT = Path(__file__).resolve().parents[1] / "docs" / "images" / "hero.gif"
PAPER, INK, FAINT, RED = "#f4f1ea", "#1d1d1b", "#b9b4a8", "#b3261e"
W, H = 12.0, 4.2
FRAMES, FPS = 80, 20
GAP = 0.9      # backlash in drawing units
AMP = 1.6      # input stroke
plt.rcParams["font.family"] = "DejaVu Sans"


def tooth(x: float, y: float, up: bool) -> list[tuple[float, float]]:
    """Trapezoidal tooth (rack form), root on y, pointing up or down."""
    h, base, tip = 0.55, 0.48, 0.205
    s = 1 if up else -1
    return [(x - base / 2, y), (x - tip / 2, y + s * h), (x + tip / 2, y + s * h),
            (x + base / 2, y)]


def output_of(inp: float, prev_out: float) -> float:
    if inp - prev_out > GAP / 2:
        return inp - GAP / 2
    if inp - prev_out < -GAP / 2:
        return inp + GAP / 2
    return prev_out


def dim_h(ax: plt.Axes, x0: float, x1: float, y: float, text: str, color: str = INK) -> None:
    ax.annotate("", (x0, y), (x1, y), arrowprops={"arrowstyle": "<|-|>", "lw": 0.7,
                                                  "color": color, "shrinkA": 0, "shrinkB": 0,
                                                  "mutation_scale": 7})
    ax.text((x0 + x1) / 2, y + 0.12, text, ha="center", va="bottom", fontsize=7.5, color=color)


def sheet(ax: plt.Axes) -> None:
    ax.add_patch(Rectangle((0.15, 0.15), W - 0.3, H - 0.3, fill=False, lw=1.4, ec=INK))
    ax.add_patch(Rectangle((0.3, 0.3), W - 0.6, H - 0.6, fill=False, lw=0.5, ec=INK))
    for i, lab in enumerate("1234"):
        x = 0.3 + (W - 0.6) * (i + 0.5) / 4
        ax.text(x, 0.2, lab, ha="center", va="center", fontsize=5.5, color=INK)
        ax.text(x, H - 0.2, lab, ha="center", va="center", fontsize=5.5, color=INK)
    for i, lab in enumerate("BA"):
        y = 0.3 + (H - 0.6) * (i + 0.5) / 2
        ax.text(0.22, y, lab, ha="center", va="center", fontsize=5.5, color=INK)
        ax.text(W - 0.22, y, lab, ha="center", va="center", fontsize=5.5, color=INK)


def title_block(ax: plt.Axes) -> None:
    x0, y0, x1, y1 = 8.15, 0.3, W - 0.3, H - 0.3
    ax.add_patch(Rectangle((x0, y0), x1 - x0, y1 - y0, fill=False, lw=0.9, ec=INK))
    ax.text(x0 + 0.18, y1 - 0.42, "MOTIONPROOF", fontsize=21, weight="bold", color=INK,
            va="center")
    ax.text(x0 + 0.2, y1 - 0.86, "tolerance-to-dynamics engineering lab", fontsize=8.5,
            color=INK, va="center")
    ax.plot([x0, x1], [y1 - 1.1, y1 - 1.1], lw=0.6, color=INK)
    lines = ["CAD model + tolerance spec", "virtual as-manufactured assemblies",
             "MuJoCo dynamics with gearbox backlash", "pass rate, sensitivity, worst case",
             "least-cost tolerances, verified"]
    for i, t in enumerate(lines):
        y = y1 - 1.38 - i * 0.27
        ax.text(x0 + 0.2, y, f"{i + 1}", fontsize=7, color=FAINT, va="center", weight="bold")
        ax.text(x0 + 0.45, y, t, fontsize=7.6, color=INK, va="center")
    yb = y0 + 0.62
    ax.plot([x0, x1], [yb, yb], lw=0.6, color=INK)
    cells = [("REV", "0.3.0"), ("SCALE", "10:1"), ("LICENCE", "MIT"), ("SHEET", "1 / 1")]
    cw = (x1 - x0) / len(cells)
    for i, (k, v) in enumerate(cells):
        cx = x0 + i * cw
        if i:
            ax.plot([cx, cx], [y0, yb], lw=0.6, color=INK)
        ax.text(cx + 0.1, yb - 0.15, k, fontsize=5.2, color=FAINT, va="center")
        ax.text(cx + 0.1, y0 + 0.2, v, fontsize=8, color=INK, va="center")


def main() -> None:
    # precompute the motion: smooth back-and-forth input, dead-band output
    inp, out = [], []
    o = -AMP + GAP / 2
    for f in range(FRAMES * 2):  # first pass settles the state, second is recorded
        t = (f % FRAMES) / FRAMES
        i = -AMP * math.cos(2 * math.pi * t)
        o = output_of(i, o)
        if f >= FRAMES:
            inp.append(i)
            out.append(o)

    frames = []
    for f in range(FRAMES):
        fig = plt.figure(figsize=(W, H), dpi=90, facecolor=PAPER)
        ax = fig.add_axes((0, 0, 1, 1))
        ax.set_xlim(0, W)
        ax.set_ylim(0, H)
        ax.axis("off")
        sheet(ax)
        title_block(ax)

        # ---- view A: tooth mesh, inside a detail circle -----------------------------
        cx, cy, R = 2.3, 2.15, 1.45
        ax.text(0.55, H - 0.55, "DETAIL A   tooth mesh, 10:1", fontsize=7.5, color=INK,
                weight="bold")
        clip = Circle((cx, cy), R, transform=ax.transData)
        ax.add_patch(Circle((cx, cy), R, fill=False, lw=0.9, ec=INK))
        k, pitch = 0.35, 1.0
        di, do = inp[f] * k, out[f] * k
        arts = []
        for n in range(-3, 4):
            arts.append(ax.add_patch(Polygon(tooth(cx + n * pitch + di, cy + 0.3, up=False),
                                             closed=True, fc=PAPER, ec=INK, lw=1.0,
                                             hatch="//////")))
            arts.append(ax.add_patch(Polygon(tooth(cx + n * pitch + pitch / 2 + do,
                                                   cy - 0.3, up=True),
                                             closed=True, fc=PAPER, ec=INK, lw=1.0)))
        arts.append(ax.add_patch(Rectangle((cx - R, cy + 0.3), 2 * R, 0.08, fc=INK, lw=0)))
        arts.append(ax.add_patch(Rectangle((cx - R, cy - 0.38), 2 * R, 0.08, fc=INK, lw=0)))
        arts += ax.plot([cx - R, cx + R], [cy, cy], lw=0.5, color=FAINT, ls=(0, (6, 2, 1, 2)))
        for a_ in arts:
            a_.set_clip_path(clip)
        # flank positions at mid height; one gap is closed, the other is the backlash j
        w = (0.48 + 0.205) / 4
        drive_r = cx + di + w
        driven_l = cx + pitch / 2 + do - w
        driven_r_prev = cx - pitch / 2 + do + w
        drive_l = cx + di - w
        g_right, g_left = driven_l - drive_r, drive_l - driven_r_prev
        if g_right >= g_left:
            x0, x1, gap = drive_r, driven_l, g_right
        else:
            x0, x1, gap = driven_r_prev, drive_l, g_left
        engaged = min(g_right, g_left) < 1e-6
        if gap > 0.02:
            yd = cy + 0.95
            for xx in (x0, x1):
                ax.plot([xx, xx], [cy, yd + 0.05], lw=0.45, color=RED)
            dim_h(ax, x0, x1, yd, f"j = {gap / (GAP * k) * 0.040:.3f} mm", RED)
        ax.plot([cx + R * 0.71, cx + R * 0.71 + 0.35], [cy - R * 0.71, cy - R * 0.71 - 0.35],
                lw=0.6, color=INK)
        ax.text(cx + R * 0.71 + 0.4, cy - R * 0.71 - 0.42, "A", fontsize=9, weight="bold",
                color=INK)
        ax.text(cx, 0.48, "flanks in contact" if engaged else "crossing the dead band",
                ha="center", fontsize=7, color=INK if engaged else RED, style="italic")

        # ---- view B: output vs input ----------------------------------------------
        ox, oy, sx = 6.0, 2.15, 0.62
        ax.text(4.65, H - 0.55, "VIEW B   output vs input", fontsize=7.5, color=INK,
                weight="bold")
        ax.plot([ox - 1.25, ox + 1.25], [oy, oy], lw=0.5, color=FAINT)
        ax.plot([ox, ox], [oy - 1.25, oy + 1.25], lw=0.5, color=FAINT)
        ax.text(ox + 1.28, oy - 0.05, "θ in", fontsize=6.5, color=INK, va="top", ha="right")
        ax.text(ox + 0.05, oy + 1.25, "θ out", fontsize=6.5, color=INK, va="top")
        ax.plot([ox - 1.1, ox + 1.1], [oy - 1.1, oy + 1.1], lw=0.5, color=FAINT,
                ls=(0, (2, 2)))
        xs = [ox + v * sx for v in inp]
        ys = [oy + v * sx for v in out]
        ax.plot(xs, ys, lw=0.5, color=FAINT)          # full loop, faint
        ax.plot(xs[: f + 1], ys[: f + 1], lw=1.3, color=INK)  # pen so far
        ax.plot(xs[f], ys[f], "o", ms=3.5, color=RED)
        dim_h(ax, ox + (-GAP / 2) * sx, ox + (GAP / 2) * sx, oy - 1.42, "dead band = j")
        ax.text(ox, 0.48, "dashed: ideal gear, no backlash", ha="center", fontsize=6.5, color=FAINT)

        buf = io.BytesIO()
        fig.savefig(buf, format="png", facecolor=PAPER)
        plt.close(fig)
        buf.seek(0)
        frames.append(Image.open(buf).convert("RGB"))

    strip = Image.new("RGB", (frames[0].width, frames[0].height * 3))
    for n_, fi in enumerate((5, 30, 55)):
        strip.paste(frames[fi], (0, n_ * frames[0].height))
    pal = strip.quantize(40, method=Image.Quantize.MAXCOVERAGE)
    q = [fr.quantize(palette=pal, dither=Image.Dither.NONE) for fr in frames]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    q[0].save(OUT, save_all=True, append_images=q[1:], duration=int(1000 / FPS), loop=0,
              optimize=True)
    print(OUT, OUT.stat().st_size // 1024, "KB")


if __name__ == "__main__":
    main()
