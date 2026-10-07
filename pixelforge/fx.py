"""Frame effects, dithering and procedural noise.

Pixel art avoids smooth alpha; transparency and gradients are expressed with
ordered (Bayer) dithering instead.  Everything here keeps hard pixels.
"""

from __future__ import annotations

import math
import random
from typing import Callable, Optional, Sequence

from .canvas import Canvas, Grid
from .color import ColorLike, RGBA, mix, rgba
from .shading import Ink, Material

BAYER4 = (
    (0, 8, 2, 10),
    (12, 4, 14, 6),
    (3, 11, 1, 9),
    (15, 7, 13, 5),
)


def bayer(x: int, y: int) -> float:
    """Ordered-dither threshold in [0, 1)."""
    return (BAYER4[y & 3][x & 3] + 0.5) / 16.0


# --- whole-frame effects ------------------------------------------------------

def flash(img: Canvas, color: ColorLike = "#ffffff") -> Canvas:
    """Hit flash: paint the silhouette a single color."""
    c = rgba(color)
    return img.map_colors(lambda p: (c[0], c[1], c[2], p[3]))


def tint(img: Canvas, color: ColorLike, amount: float) -> Canvas:
    c = rgba(color)
    return img.map_colors(lambda p: mix(p, (c[0], c[1], c[2], p[3]), amount))


def dissolve(img: Canvas, t: float, color: Optional[ColorLike] = None) -> Canvas:
    """Remove pixels with an ordered-dither pattern as ``t`` goes 0 -> 1.
    If ``color`` is given, pixels about to vanish are drawn in it first
    (a "burning edge")."""
    out = Canvas(img.width, img.height)
    edge = None if color is None else rgba(color)
    for x, y, c in img.items():
        th = bayer(x, y)
        if th >= t:
            out.set(x, y, edge if (edge is not None and th < t + 0.12) else c)
    return out


def fade_dither(img: Canvas, t: float) -> Canvas:
    """Dithered fade-out (alias for :func:`dissolve` without edge color)."""
    return dissolve(img, t)


def drop_shadow(img: Canvas, color: ColorLike = (24, 20, 37, 110), rx: float = 6.0,
                ry: float = 1.5, cx: Optional[float] = None, cy: Optional[float] = None) -> Canvas:
    """Ellipse shadow under the sprite (drawn behind it)."""
    out = Canvas(img.width, img.height)
    box = img.bbox()
    if box is None:
        return img.copy()
    cx = (box[0] + box[2] + 1) / 2 if cx is None else cx
    cy = box[3] + 0.5 if cy is None else cy
    out.ellipse(cx, cy, rx, ry, rgba(color))
    out.blit(img)
    return out


def offset(img: Canvas, dx: int, dy: int) -> Canvas:
    return img.shifted(dx, dy)


# --- part-buffer effects (used as Pose.fx) -------------------------------------

def smear_arc(pivot, r0: float, r1: float, a0: float, a1: float, material: Material,
              z: float = 50.0, level: int = 4, taper: float = 0.25):
    """Return a Pose.fx callback drawing a crescent motion smear.

    ``pivot`` is an (x, y) point or a callable ``states -> (x, y)``.  The arc
    sweeps from ``a0`` (trailing end, thin) to ``a1`` (leading end, full
    ``r0..r1`` thickness), angles in degrees.  Smears carry no outline and
    use the two lightest ramp steps, like hand-drawn ones.
    """
    def fx(buf, states, rig):
        cx, cy = pivot(states) if callable(pivot) else pivot
        span = a1 - a0
        if abs(span) < 1e-6:
            return
        hi = Ink(material, "smear", z, level=level, contour=False, outline=False)
        lo = Ink(material, "smear", z, level=max(1, level - 1), contour=False, outline=False)
        for y in range(buf.height):
            for x in range(buf.width):
                dx, dy = x + 0.5 - cx, y + 0.5 - cy
                r = math.hypot(dx, dy)
                if r < r0 or r > r1:
                    continue
                a = math.degrees(math.atan2(dy, dx))
                u = ((a - a0) % 360.0) / span if span > 0 else ((a0 - a) % 360.0) / -span
                if 0.0 <= u <= 1.0:
                    k = (r - r0) / max(0.01, r1 - r0)       # 0 inner .. 1 outer
                    if k >= 1.0 - (taper + (1.0 - taper) * u):
                        buf.plot(x, y, hi if (k > 0.55 or u > 0.8) else lo)
    return fx


# --- noise --------------------------------------------------------------------

class ValueNoise:
    """Tileable value noise (wraps every ``period`` cells)."""

    def __init__(self, seed: int = 0, period: int = 8):
        rnd = random.Random(seed)
        self.period = period
        self.v = [[rnd.random() for _ in range(period)] for _ in range(period)]

    def __call__(self, x: float, y: float) -> float:
        p = self.period
        x0, y0 = math.floor(x), math.floor(y)
        fx, fy = x - x0, y - y0
        sx, sy = fx * fx * (3 - 2 * fx), fy * fy * (3 - 2 * fy)
        v = self.v
        a = v[y0 % p][x0 % p]
        b = v[y0 % p][(x0 + 1) % p]
        c = v[(y0 + 1) % p][x0 % p]
        d = v[(y0 + 1) % p][(x0 + 1) % p]
        return (a + (b - a) * sx) * (1 - sy) + (c + (d - c) * sx) * sy

    def fbm(self, x: float, y: float, octaves: int = 3) -> float:
        total, amp, norm = 0.0, 1.0, 0.0
        for o in range(octaves):
            f = 2 ** o
            # sample a scaled copy that still tiles: the period stays a multiple
            total += amp * self(x * f, y * f)
            norm += amp
            amp *= 0.5
        return total / norm


def dither_pick(colors: Sequence[RGBA], value: float, x: int, y: int) -> RGBA:
    """Map ``value`` in [0, 1] onto ``colors`` using ordered dithering between
    neighbouring entries (classic retro gradient)."""
    n = len(colors) - 1
    v = max(0.0, min(0.9999, value)) * n
    i = int(v)
    frac = v - i
    return colors[min(n, i + (1 if frac > bayer(x, y) else 0))]
