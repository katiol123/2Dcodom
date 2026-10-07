"""Visual effects animations: explosion, hit spark, fireball, dust, heal.

Effects follow the usual pixel-art recipe: a 1-frame bright flash, shapes
that expand fast then slow down (ease-out), colors that cool down over time
(white -> yellow -> orange -> red -> smoke) and a dithered dissolve at the end.
"""

from __future__ import annotations

import math
import random
from typing import List

from ..anim import Animation, Sprite, ease_out
from ..canvas import Canvas
from ..color import ColorLike, mix, rgba, ramp
from ..fx import bayer, dissolve
from ..palette import INK

FIRE = [rgba(c) for c in ("#ffffff", "#fee761", "#feae34", "#f77622", "#e43b44", "#a22633", "#5a6988", "#3a4466")]


def _fire_color(heat: float):
    """heat 1 = white hot ... 0 = smoke."""
    i = int((1.0 - max(0.0, min(0.999, heat))) * (len(FIRE)))
    return FIRE[min(len(FIRE) - 1, i)]


def explosion(size: int = 32, frames: int = 8, seed: int = 3) -> Animation:
    rnd = random.Random(seed)
    blobs = [(rnd.uniform(0, math.tau), rnd.uniform(0.3, 1.0), rnd.uniform(0.5, 1.0)) for _ in range(7)]
    anim = Animation("explosion", loop=False)
    c0 = size / 2
    for f in range(frames):
        t = f / (frames - 1)
        img = Canvas(size, size)
        if f == 0:
            img.circle(c0, c0, size * 0.18, FIRE[0])
            anim.add(img, 50)
            continue
        R = size * 0.45 * ease_out(min(1.0, t * 1.4))
        for a, dist, rad in blobs:
            bx = c0 + math.cos(a) * dist * R * 0.6
            by = c0 + math.sin(a) * dist * R * 0.6 - t * size * 0.12   # smoke rises
            br = rad * R * 0.55 * (1.0 - 0.3 * t)
            for y in range(int(by - br) - 1, int(by + br) + 2):
                for x in range(int(bx - br) - 1, int(bx + br) + 2):
                    d = math.hypot(x + 0.5 - bx, y + 0.5 - by) / max(0.5, br)
                    if d <= 1.0:
                        # hotter in the core and early on; dithered ramp steps
                        heat = (1.0 - d) * 0.8 + (1.0 - t) * 0.7 - 0.25 + (bayer(x, y) - 0.5) * 0.25
                        img.set(x, y, _fire_color(heat))
        if t > 0.6:
            img = dissolve(img, (t - 0.6) / 0.4 * 0.9)
        anim.add(img, 70 if f < 3 else 90)
    return anim


def hit_spark(size: int = 16, frames: int = 4, color: ColorLike = "#ffffff") -> Animation:
    anim = Animation("hit_spark", loop=False)
    c0 = size / 2 - 0.5
    hi = rgba(color)
    mid = rgba("#fee761")
    for f in range(frames):
        img = Canvas(size, size)
        r_out = 2 + f * 2
        r_in = max(0, f * 2 - 1)
        for k in range(8):
            a = k * math.pi / 4 + (math.pi / 8 if f % 2 else 0)
            ln = r_out if k % 2 == 0 else r_out * 0.6
            x0, y0 = c0 + math.cos(a) * r_in, c0 + math.sin(a) * r_in
            x1, y1 = c0 + math.cos(a) * ln, c0 + math.sin(a) * ln
            img.line(round(x0), round(y0), round(x1), round(y1), hi if f < 2 else mid)
        if f == 0:
            img.circle(c0 + 0.5, c0 + 0.5, 2, hi)
        anim.add(img, 50 if f == 0 else 60)
    return anim


def fireball(size: int = 16, frames: int = 4) -> Animation:
    """Looping projectile flying right, with a flickering trail."""
    anim = Animation("fireball")
    for f in range(frames):
        img = Canvas(size, size)
        cx, cy = size - 6, size / 2
        for i in range(6):   # trail puffs, cooler and smaller to the left
            x = cx - 2 - i * 1.6
            y = cy + math.sin(f * 1.7 + i * 1.3) * 0.9
            r = 2.6 - i * 0.35
            img.circle(math.floor(x) + 0.5, math.floor(y) + 0.5, max(0.6, r), _fire_color(0.75 - i * 0.12))
        img.circle(cx, cy, 3.4, FIRE[3])
        img.circle(cx + 0.5, cy, 2.4, FIRE[1])
        img.circle(cx + 1, cy - 0.5, 1.2, FIRE[0])
        anim.add(img, 70)
    return anim


def dust(size: int = 16, frames: int = 5, color: ColorLike = "#c0cbdc") -> Animation:
    """Footstep / landing puff."""
    anim = Animation("dust", loop=False)
    tones = ramp(color, 1, 1)
    for f in range(frames):
        t = f / (frames - 1)
        img = Canvas(size, size)
        for side in (-1, 1):
            x = size / 2 + side * (2 + t * 5)
            y = size - 3 - t * 3
            r = 2.2 - t * 1.2
            img.circle(math.floor(x) + 0.5, math.floor(y) + 0.5, max(0.6, r), tones[2 if t < 0.5 else 1])
        if t > 0.5:
            img = dissolve(img, (t - 0.5) * 1.6)
        anim.add(img, 70)
    return anim


def heal(size: int = 24, frames: int = 6, color: ColorLike = "#63c74d", seed: int = 5) -> Animation:
    """Rising plus-shaped sparkles."""
    rnd = random.Random(seed)
    parts = [(rnd.uniform(4, size - 4), rnd.uniform(size * 0.5, size - 2), rnd.uniform(0, 1)) for _ in range(6)]
    tones = ramp(color, 1, 2)
    anim = Animation("heal", loop=False)
    for f in range(frames):
        img = Canvas(size, size)
        for x0, y0, ph in parts:
            t = (f / frames + ph * 0.5)
            y = y0 - t * size * 0.6
            if y < 1:
                continue
            x, yy = int(x0), int(y)
            col = tones[3] if (f + int(ph * 3)) % 2 else tones[2]
            img.set(x, yy, tones[3])
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                img.set(x + dx, yy + dy, col)
        anim.add(img, 80)
    return anim


def vfx_set() -> List[Sprite]:
    out = []
    for size, fns in ((32, [explosion]), (16, [hit_spark, fireball, dust]), (24, [heal])):
        sp = Sprite(f"vfx{size}", size, size)
        for fn in fns:
            sp.add(fn(size=size))
        out.append(sp)
    return out
