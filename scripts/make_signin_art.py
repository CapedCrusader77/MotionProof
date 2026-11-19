"""Long-exposure image of the reference gearbox's first stage for the sign-in page.

Points fixed on the three 21-tooth planets are traced while the 12-tooth sun turns eleven
times (two carrier turns, ring fixed): the exact planetary kinematics used by MotionProof,
drawn as light trails accumulated in a float buffer and tone mapped, like a photograph of a
moving mechanism with the shutter left open. No renderer, NumPy and Pillow only.

    uv run python scripts/make_signin_art.py
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "frontend" / "public" / "home" / "signin.webp"
W, H, SS = 1200, 1500, 2                 # output size, supersampling
ZS, ZP, ZR = 12, 21, 54
RATIO = (ZS + ZR) / ZS
RP, CD, RR = ZP / 2, (ZS + ZP) / 2, ZR / 2  # module 1
SCALE = 19.0 * SS                        # px per module unit
CX, CY = 0.52 * W * SS, 0.40 * H * SS    # mechanism centre

rng = np.random.default_rng(7)
acc = np.zeros((H * SS, W * SS, 3), np.float64)


def splat(x: np.ndarray, y: np.ndarray, colour: np.ndarray, w: float) -> None:
    """Bilinear additive splat of points (x, y) in pixels."""
    x0, y0 = np.floor(x).astype(int), np.floor(y).astype(int)
    fx, fy = x - x0, y - y0
    for dx, dy, k in ((0, 0, (1 - fx) * (1 - fy)), (1, 0, fx * (1 - fy)),
                      (0, 1, (1 - fx) * fy), (1, 1, fx * fy)):
        xi, yi = x0 + dx, y0 + dy
        ok = (xi >= 0) & (xi < W * SS) & (yi >= 0) & (yi < H * SS)
        for c in range(3):
            np.add.at(acc[..., c], (yi[ok], xi[ok]), w * k[ok] * colour[c])


def palette(t: float) -> np.ndarray:
    """Amber (outer) through warm white to steel blue (inner)."""
    stops = [(0.0, (0.36, 0.55, 0.85)), (0.55, (0.95, 0.90, 0.82)), (1.0, (1.0, 0.58, 0.20))]
    for (a, ca), (b, cb) in zip(stops, stops[1:], strict=False):
        if t <= b:
            u = (t - a) / (b - a)
            return np.array([ca[i] + u * (cb[i] - ca[i]) for i in range(3)])
    return np.array(stops[-1][1])


sun = np.linspace(0, 2 * math.pi * RATIO * 2, 260_000)  # two carrier turns
car = sun / RATIO
for k in range(3):
    phi = car + 2 * math.pi * k / 3
    planet = (ZS * (phi - sun) + ZP * (phi + math.pi) - math.pi) / ZP
    px, py = CD * np.cos(phi), CD * np.sin(phi)
    for j in range(7):
        rho = RP * (0.18 + 0.82 * (j + rng.uniform(0.2, 0.8)) / 7)
        alpha = rng.uniform(0, 2 * math.pi)
        x = CX + SCALE * (px + rho * np.cos(planet + alpha))
        y = CY + SCALE * (py + rho * np.sin(planet + alpha))
        splat(x, y, palette(rho / RP), 0.11 * (0.55 + rho / RP))

# the fixed ring and the sun, as faint static outlines (they barely move in the exposure)
for r, w in ((RR + 1.0, 0.9), (RR - 1.25, 0.5), (ZS / 2, 0.7)):
    t = np.linspace(0, 2 * math.pi, 40_000)
    splat(CX + SCALE * r * np.cos(t), CY + SCALE * r * np.sin(t), np.array([0.55, 0.6, 0.66]), w)

# soft bloom: a few box blurs of the bright part, added back
img = acc
from scipy.ndimage import gaussian_filter  # noqa: E402

glow = (gaussian_filter(img, sigma=(9 * SS, 9 * SS, 0))
        + gaussian_filter(img, sigma=(28 * SS, 28 * SS, 0)))
img = img + 0.5 * glow

# tone map, downsample, vignette, film grain
img = 1 - np.exp(-1.4 * img)
img = img.reshape(H, SS, W, SS, 3).mean(axis=(1, 3))
yy, xx = np.mgrid[0:H, 0:W]
d = np.hypot((xx - CX / SS) / W, (yy - CY / SS) / H)
img *= (1 - 0.55 * np.clip(d - 0.15, 0, 1))[..., None]
base = np.array([0.020, 0.022, 0.028])
img = base + (1 - base) * img
img += rng.normal(0, 0.012, img.shape)
Image.fromarray((np.clip(img, 0, 1) ** (1 / 1.1) * 255).astype(np.uint8)).save(
    OUT, "WEBP", quality=88, method=6)
print("wrote", OUT)
