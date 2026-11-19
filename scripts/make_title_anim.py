"""Animated README title from a real MotionProof experiment (no numbers made up here).

Replays an experiment's results.jsonl in order: each virtual assembly lands on the backlash /
direction-error plane as it finishes, failures in red, while the pass rate and its 95 % Wilson
interval settle in the panel on the left.

    uv run python scripts/make_title_anim.py workspace/projects/PRJ_001/experiments/EXP_001
"""

from __future__ import annotations

import io
import json
import math
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "images" / "title.gif"
INK, MUTED, GRID = "#1d2125", "#6b7177", "#e6e8ea"
PASS, FAIL = "#41698f", "#d2452f"
STEPS, HOLD = 64, 28


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return c - h, c + h


def main(exp_dir: Path) -> None:
    manifest = json.loads((exp_dir / "manifest.json").read_text(encoding="utf-8"))
    lines = (exp_dir / "results.jsonl").read_text(encoding="utf-8").splitlines()
    rows = [r for r in (json.loads(x) for x in lines) if r["valid"]]
    limit = 1e3 * next(c["limit"] for c in manifest["config"]["constraints"]
                       if c["metric"] == "direction_error_ee")
    ok = np.array([r["passed"] for r in rows])
    bx = np.array([r["metrics"]["backlash"] for r in rows]) * 1e3
    ey = np.array([r["metrics"]["direction_error_ee"] for r in rows]) * 1e3
    n_all = len(rows)
    rate = np.cumsum(ok) / np.arange(1, n_all + 1)
    ci = np.array([wilson(int(ok[:i].sum()), i) for i in range(1, n_all + 1)])
    # reveal slowly at first, then faster, like a run whose estimate settles
    counts = np.unique(np.round(n_all * (np.linspace(0, 1, STEPS + 1)[1:] ** 1.8)).astype(int))
    counts = np.maximum(counts, 3)

    plt.rcParams.update({"font.family": "DejaVu Sans", "axes.edgecolor": INK,
                         "xtick.color": MUTED, "ytick.color": MUTED, "axes.labelcolor": INK,
                         "axes.spines.top": False, "axes.spines.right": False})
    frames: list[Image.Image] = []
    for f, n in enumerate(list(counts) + [n_all] * HOLD):
        fig = plt.figure(figsize=(12, 4.2), dpi=100)
        fig.patch.set_facecolor("white")
        fig.text(0.035, 0.80, "MotionProof", fontsize=34, fontweight="bold", color=INK)
        fig.text(0.037, 0.70, "Tolerances in. Motion out.", fontsize=15, color=FAIL)
        k = int(ok[:n].sum())
        lo, hi = ci[n - 1]
        mono = {"fontsize": 12, "color": INK, "family": "DejaVu Sans Mono"}
        fig.text(0.037, 0.52, f"{n:>4} virtual assemblies simulated", **mono)
        fig.text(0.037, 0.445, f"{100 * k / n:5.1f} % pass   95 % {100 * lo:.1f} to "
                 f"{100 * hi:.1f}", **mono)

        r = fig.add_axes((0.04, 0.12, 0.33, 0.24))
        x = np.arange(1, n + 1)
        r.fill_between(x, ci[:n, 0] * 100, ci[:n, 1] * 100, color=PASS, alpha=0.18, lw=0)
        r.plot(x, rate[:n] * 100, color=PASS, lw=1.4)
        r.set_xlim(1, n_all)
        r.set_ylim(40, 100)
        r.set_yticks([50, 75, 100])
        r.tick_params(labelsize=8)
        r.set_xlabel("assemblies", fontsize=8.5, color=MUTED)
        r.set_ylabel("pass %", fontsize=8.5, color=MUTED)

        a = fig.add_axes((0.47, 0.15, 0.50, 0.78))
        old = slice(0, max(0, n - 12))
        new = slice(max(0, n - 12), n) if n < n_all else slice(n, n)
        for sl, size, alpha in ((old if n < n_all else slice(0, n), 9, 0.55), (new, 34, 0.95)):
            o = ok[sl]
            a.scatter(bx[sl][o], ey[sl][o], s=size, c=PASS, alpha=alpha, linewidths=0)
            a.scatter(bx[sl][~o], ey[sl][~o], s=size * 1.2, c=FAIL, alpha=alpha, linewidths=0)
        a.axhline(limit, color=FAIL, lw=1, ls=(0, (4, 3)))
        a.text(bx.max(), limit, f"requirement {limit:g} mm ", color=FAIL, ha="right",
               va="bottom", fontsize=9)
        a.set_xlim(bx.min() - 0.15, bx.max() + 0.15)
        a.set_ylim(-0.1, ey.max() * 1.06)
        a.grid(color=GRID, lw=0.8)
        a.set_axisbelow(True)
        a.tick_params(labelsize=8.5)
        a.set_xlabel("output backlash of the assembly (mrad)", fontsize=9.5)
        a.set_ylabel("direction error at the tool (mm)", fontsize=9.5)
        fig.text(0.47, 0.015, "Reference 33:1 planetary elbow, synthetic design, assumed "
                 "tolerances. Model predictions.", fontsize=8, color=MUTED)
        buf = io.BytesIO()
        fig.savefig(buf, format="png", facecolor="white")
        plt.close(fig)
        frames.append(Image.open(buf).convert("RGB"))
        if f % 20 == 0:
            print(f"frame {f}")
    pal = frames[-1].quantize(colors=96, method=Image.Quantize.MEDIANCUT)
    q = [fr.quantize(palette=pal, dither=Image.Dither.NONE) for fr in frames]
    q[0].save(OUT, save_all=True, append_images=q[1:],
              duration=[70] * len(counts) + [140] * HOLD, loop=0, optimize=True)
    print("wrote", OUT, f"{OUT.stat().st_size / 1e6:.1f} MB, {len(q)} frames")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
