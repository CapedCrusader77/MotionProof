"""README result figure from a real MotionProof experiment (no numbers made up here).

Reads an experiment's results.jsonl and draws three panels:
  a) every virtual assembly: output backlash against the direction error at the tool,
     failures in red, the requirement as a line;
  b) which tolerances drive the error (|Spearman rho| computed from the same runs);
  c) the distribution of the direction error against its limit.

    uv run python scripts/make_result_figures.py workspace/projects/PRJ_001/experiments/EXP_001
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from scipy import stats  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "images" / "results.png"
INK, MUTED, GRID = "#1d2125", "#6b7177", "#e6e8ea"
PASS, FAIL = "#41698f", "#d2452f"


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return c - h, c + h


def main(exp_dir: Path) -> None:
    manifest = json.loads((exp_dir / "manifest.json").read_text(encoding="utf-8"))
    lines = (exp_dir / "results.jsonl").read_text(encoding="utf-8").splitlines()
    rows = [json.loads(line) for line in lines]
    rows = [r for r in rows if r["valid"]]
    limit = next(c["limit"] for c in manifest["config"]["constraints"]
                 if c["metric"] == "direction_error_ee")
    ok = np.array([r["passed"] for r in rows])
    backlash = np.array([r["metrics"]["backlash"] for r in rows]) * 1e3        # mrad
    err = np.array([r["metrics"]["direction_error_ee"] for r in rows]) * 1e3   # mm
    lim = limit * 1e3
    n, k = len(rows), int(ok.sum())
    lo, hi = wilson(k, n)

    names = [p for p in rows[0]["values"] if not p.endswith("_phase")]
    rho = []
    for p in names:
        x = np.array([r["values"][p] for r in rows])
        if np.ptp(x) > 0:
            rho.append((p, abs(stats.spearmanr(x, err).statistic)))
    rho.sort(key=lambda t: t[1], reverse=True)
    top = rho[:8][::-1]

    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10.5, "axes.edgecolor": INK,
                         "axes.labelcolor": INK, "xtick.color": MUTED, "ytick.color": MUTED,
                         "axes.spines.top": False, "axes.spines.right": False})
    fig = plt.figure(figsize=(15.5, 4.9), dpi=150)
    gs = fig.add_gridspec(1, 3, width_ratios=[1.25, 1, 1], wspace=0.62)

    a = fig.add_subplot(gs[0])
    a.scatter(backlash[ok], err[ok], s=9, c=PASS, alpha=0.55, linewidths=0, label=f"pass ({k})")
    a.scatter(backlash[~ok], err[~ok], s=12, c=FAIL, alpha=0.85, linewidths=0,
              label=f"fail ({n - k})")
    a.axhline(lim, color=FAIL, lw=1, ls=(0, (4, 3)))
    a.text(backlash.min(), lim, f" requirement {lim:g} mm", color=FAIL, va="bottom",
           fontsize=9.5)
    a.set_xlabel("output backlash of the assembly (mrad)")
    a.set_ylabel("direction error at the tool (mm)")
    a.legend(frameon=False, loc="upper left", fontsize=9.5, markerscale=1.8)
    a.grid(color=GRID, lw=0.8)
    a.set_axisbelow(True)
    a.set_title(f"a   {n} virtual assemblies: {100 * k / n:.1f} % pass\n"
                f"     95 % interval {100 * lo:.1f} to {100 * hi:.1f} %", loc="left", color=INK,
                fontsize=11)

    b = fig.add_subplot(gs[1])
    b.barh([p.replace("_", " ") for p, _ in top], [v for _, v in top],
           color=[FAIL if i >= len(top) - 3 else "#9aa3ab" for i in range(len(top))], height=0.62)
    for i, (_, v) in enumerate(top):
        b.text(v + 0.01, i, f"{v:.2f}", va="center", fontsize=9, color=MUTED)
    b.set_xlabel("|Spearman ρ| with direction error")
    b.set_xlim(0, max(v for _, v in top) * 1.18)
    b.tick_params(axis="y", colors=INK, length=0)
    b.spines["left"].set_visible(False)
    b.set_title("b   which inputs drive it", loc="left", color=INK, fontsize=11)

    c = fig.add_subplot(gs[2])
    bins = np.linspace(0, err.max() * 1.02, 34)
    c.hist([err[ok], err[~ok]], bins=bins, stacked=True, color=[PASS, FAIL], alpha=0.85)
    c.axvline(lim, color=FAIL, lw=1, ls=(0, (4, 3)))
    c.set_xlabel("direction error at the tool (mm)")
    c.set_ylabel("assemblies")
    c.grid(axis="y", color=GRID, lw=0.8)
    c.set_axisbelow(True)
    c.set_title("c   how far past the limit", loc="left", color=INK, fontsize=11)

    fig.text(0.01, -0.04, f"{manifest['name']}: reference NEMA 17 two-stage 33:1 planetary "
             "elbow, synthetic reference design with assumed tolerances. "
             "Model predictions, not measurements.", color=MUTED, fontsize=9)
    fig.savefig(OUT, bbox_inches="tight", facecolor="white")
    print("wrote", OUT, f"pass {k}/{n}", "top drivers:", [p for p, _ in rho[:3]])


if __name__ == "__main__":
    main(Path(sys.argv[1]))
