"""Animated README banner: the long exposure of scripts/make_signin_art.py, drawn live.

Points fixed on the planets of the reference gearbox's first stage (sun 12, planets 21,
ring 54 fixed) leave light trails that fade, with a bright head on each point. Every planet
carries the same set of points, so the picture has three-fold symmetry and repeats exactly
after the carrier turns 7/3 of a turn (sun 77/6 turns); one period is one seamless loop.

    uv run python scripts/make_banner_anim.py
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy.ndimage import gaussian_filter

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "images" / "banner.webp"
W, H = 1200, 374
FRAMES, FPS = 240, 30
ZS, ZP, ZR = 12, 21, 54
RATIO = (ZS + ZR) / ZS
RP, CD, RR = ZP / 2, (ZS + ZP) / 2, ZR / 2
SCALE = 0.45 * H / (RR + 1)
CX, CY = 0.76 * W, 0.5 * H
PERIOD = RATIO * 2 * math.pi * 7 / 3     # sun angle for one exact repeat
DECAY = 0.982                            # per frame; ~0.013 left after a period
SUB = 36                                 # sub-steps per frame for smooth trails

rng = np.random.default_rng(7)
TRACERS = [(RP * (0.18 + 0.82 * (j + rng.uniform(0.2, 0.8)) / 7), rng.uniform(0, 2 * math.pi))
           for j in range(7)]


def colour(t: float) -> np.ndarray:
    stops = [(0.0, (0.36, 0.55, 0.85)), (0.55, (0.95, 0.90, 0.82)), (1.0, (1.0, 0.58, 0.20))]
    for (a, ca), (b, cb) in zip(stops, stops[1:], strict=False):
        if t <= b:
            u = (t - a) / (b - a)
            return np.array([ca[i] + u * (cb[i] - ca[i]) for i in range(3)])
    return np.array(stops[-1][1])


def positions(sun: np.ndarray) -> list[tuple[np.ndarray, np.ndarray, np.ndarray, float]]:
    out = []
    car = sun / RATIO
    for k in range(3):
        phi = car + 2 * math.pi * k / 3
        planet = (ZS * (phi - sun) + ZP * (phi + math.pi) - math.pi) / ZP
        for rho, alpha in TRACERS:
            x = CX + SCALE * (CD * np.cos(phi) + rho * np.cos(planet + alpha))
            y = CY + SCALE * (CD * np.sin(phi) + rho * np.sin(planet + alpha))
            out.append((x, y, colour(rho / RP), rho))
    return out


acc = np.zeros((H, W, 3))


def splat(x: np.ndarray, y: np.ndarray, c: np.ndarray, w: float) -> None:
    x0, y0 = np.floor(x).astype(int), np.floor(y).astype(int)
    fx, fy = x - x0, y - y0
    for dx, dy, k in ((0, 0, (1 - fx) * (1 - fy)), (1, 0, fx * (1 - fy)),
                      (0, 1, (1 - fx) * fy), (1, 1, fx * fy)):
        xi, yi = x0 + dx, y0 + dy
        ok = (xi >= 0) & (xi < W) & (yi >= 0) & (yi < H)
        for ch in range(3):
            np.add.at(acc[..., ch], (yi[ok], xi[ok]), w * k[ok] * c[ch])


step = PERIOD / FRAMES


def advance(sun: float) -> None:
    global acc
    acc *= DECAY
    s = np.linspace(sun, sun + step, SUB, endpoint=False)
    for x, y, c, rho in positions(s):
        splat(x, y, c, 0.16 * (0.55 + rho / RP))


# static parts: ring and sun outlines, title text
yy, xx = np.mgrid[0:H, 0:W]
outline = np.zeros((H, W))
for r in (RR + 1.0, RR - 1.25, ZS / 2):
    d = np.abs(np.hypot(xx - CX, yy - CY) - SCALE * r)
    outline += np.clip(1 - d, 0, 1) * 0.28
vignette = 1 - 0.5 * np.clip(np.hypot((xx - CX) / W, (yy - CY) / H) - 0.2, 0, 1)
base = np.array([0.020, 0.022, 0.028])

fonts = Path("C:/Windows/Fonts")


def font(name: str, size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    try:
        return ImageFont.truetype(str(fonts / name), size)
    except OSError:
        return ImageFont.load_default(size)


def finish(sun: float) -> Image.Image:
    img = acc + 0.5 * (gaussian_filter(acc, (4, 4, 0)) + gaussian_filter(acc, (12, 12, 0)))
    img = 1 - np.exp(-1.4 * img)
    img = np.maximum(img, outline[..., None] * np.array([0.55, 0.6, 0.66]))
    img = (base + (1 - base) * img) * vignette[..., None]
    pic = Image.fromarray((np.clip(img, 0, 1) ** (1 / 1.1) * 255).astype(np.uint8))
    d = ImageDraw.Draw(pic, "RGBA")
    for x, y, c, _ in positions(np.array([sun])):
        r, g, b = (int(255 * min(1, v * 1.1)) for v in c)
        for rad, a in ((7, 40), (4, 90), (2, 255)):
            d.ellipse((x[0] - rad, y[0] - rad, x[0] + rad, y[0] + rad), fill=(r, g, b, a))
    d.text((64, 118), "MotionProof", font=font("segoeuib.ttf", 64), fill=(236, 238, 234))
    d.text((67, 207), "Tolerances in. Motion out.", font=font("segoeuisl.ttf", 27),
           fill=(240, 161, 74))
    d.text((68, 258), "Virtual as-manufactured copies of your mechanism, simulated and ranked.",
           font=font("segoeui.ttf", 16), fill=(160, 168, 176))
    return pic


sun = 0.0
for _ in range(FRAMES):          # one period to reach the steady state
    advance(sun)
    sun += step
frames = []
for i in range(FRAMES):
    advance(sun)
    sun += step
    frames.append(finish(sun))
    if i % 40 == 0:
        print(f"frame {i}/{FRAMES}")
frames[0].save(OUT, "WEBP", save_all=True, append_images=frames[1:], duration=1000 // FPS,
               loop=0, quality=78, method=4)
print("wrote", OUT, f"{OUT.stat().st_size / 1e6:.1f} MB")
