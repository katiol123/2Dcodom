"""Seamless terrain tiles (default 16x16).

Every generator wraps its noise / features around the tile edges, so tiles
repeat without visible seams.  Light comes from the top-left like the units.
"""

from __future__ import annotations

import math
import random
from typing import List, Optional, Tuple

from ..anim import Animation, Sprite
from ..canvas import Canvas
from ..color import ColorLike, ramp, rgba, shade
from ..fx import ValueNoise, bayer, dither_pick


def _tone_map(base: ColorLike, n: int = 4) -> List:
    """n tones around base (darker..lighter) using the hue-shifted ramp."""
    r = ramp(base, darker=2, lighter=2)
    return r[:n] if n <= 5 else r


def grass(seed: int = 1, size: int = 16, base: ColorLike = "#3e8948", flowers: bool = True) -> Canvas:
    rnd = random.Random(seed)
    noise = ValueNoise(seed, period=4)
    tones = ramp(base, 1, 2)                     # shadow, base, light, highlight
    c = Canvas(size, size)
    for y in range(size):
        for x in range(size):
            v = noise.fbm(x / size * 4, y / size * 4, 2)
            c.set(x, y, dither_pick(tones[:3], v * 0.9 + 0.05, x, y))
    # blades: little light ticks with a shadow pixel under them
    for _ in range(size * size // 18):
        x, y = rnd.randrange(size), rnd.randrange(size)
        c.set(x, y, tones[2])
        c.set(x, (y - 1) % size, tones[3] if rnd.random() < 0.3 else tones[2])
        c.set(x, (y + 1) % size, tones[0])
    if flowers:
        for _ in range(rnd.randint(0, 2)):
            x, y = rnd.randrange(size), rnd.randrange(size)
            col = rgba(rnd.choice(["#fee761", "#ffffff", "#f6757a", "#2ce8f5"]))
            for dx, dy in ((0, -1), (-1, 0), (1, 0), (0, 1)):
                c.set((x + dx) % size, (y + dy) % size, col)
            c.set(x, y, rgba("#feae34"))
    return c


def dirt(seed: int = 2, size: int = 16, base: ColorLike = "#b86f50") -> Canvas:
    rnd = random.Random(seed)
    noise = ValueNoise(seed, period=4)
    tones = ramp(base, 2, 1)
    c = Canvas(size, size)
    for y in range(size):
        for x in range(size):
            v = noise.fbm(x / size * 4, y / size * 4, 3)
            c.set(x, y, dither_pick(tones[1:4], v, x, y))
    for _ in range(size // 3):   # pebbles: lit top-left pixel, dark bottom-right
        x, y = rnd.randrange(size), rnd.randrange(size)
        c.set(x, y, tones[3])
        c.set((x + 1) % size, y, tones[2])
        c.set((x + 1) % size, (y + 1) % size, tones[0])
        c.set(x, (y + 1) % size, tones[1])
    return c


def sand(seed: int = 3, size: int = 16, base: ColorLike = "#e4a672") -> Canvas:
    noise = ValueNoise(seed, period=4)
    tones = ramp(base, 1, 1)
    c = Canvas(size, size)
    for y in range(size):
        for x in range(size):
            # wind ripples: diagonal sine bands broken up by noise
            v = 0.5 + 0.35 * math.sin((x * 2 + y * 4) / size * math.tau) + 0.3 * (noise(x / 4, y / 4) - 0.5)
            c.set(x, y, dither_pick(tones, v, x, y))
    return c


def _cells(seed: int, size: int, count: int) -> List[Tuple[float, float]]:
    rnd = random.Random(seed)
    return [(rnd.uniform(0, size), rnd.uniform(0, size)) for _ in range(count)]


def cobblestone(seed: int = 4, size: int = 16, base: ColorLike = "#8b9bb4",
                mortar: ColorLike = "#3a4466", stones: int = 6) -> Canvas:
    """Voronoi stones with toroidal distance (seamless), each shaded as a dome."""
    pts = _cells(seed, size, stones)
    tones = ramp(base, 2, 2)
    mor = rgba(mortar)
    c = Canvas(size, size)
    rnd = random.Random(seed)
    jitter = [rnd.choice((-1, 0, 0, 1)) for _ in pts]

    def nearest2(x, y):
        best = []
        for i, (px, py) in enumerate(pts):
            dx = min(abs(x - px), size - abs(x - px))
            dy = min(abs(y - py), size - abs(y - py))
            best.append((math.hypot(dx, dy), i))
        best.sort()
        return best[0], best[1]

    owner = {}
    for y in range(size):
        for x in range(size):
            (d1, i1), (d2, _) = nearest2(x + 0.5, y + 0.5)
            owner[(x, y)] = i1 if d2 - d1 > 1.1 else -1
    for y in range(size):
        for x in range(size):
            i = owner[(x, y)]
            if i < 0:
                c.set(x, y, mor)
                continue
            up = owner[(x, (y - 1) % size)] != i or owner[((x - 1) % size, y)] != i
            down = owner[(x, (y + 1) % size)] != i or owner[((x + 1) % size, y)] != i
            lvl = 2 + jitter[i]
            if up and not down:
                lvl += 1
            elif down and not up:
                lvl -= 1
            c.set(x, y, tones[max(0, min(4, lvl))])
    return c


def bricks(size: int = 16, base: ColorLike = "#a22633", mortar: ColorLike = "#3e2731",
           brick_w: int = 8, brick_h: int = 4, seed: int = 5) -> Canvas:
    rnd = random.Random(seed)
    tones = ramp(base, 2, 2)
    mor = rgba(mortar)
    c = Canvas(size, size)
    for y in range(size):
        row = y // brick_h
        off = (brick_w // 2) * (row % 2)
        for x in range(size):
            bx = (x + off) % brick_w
            by = y % brick_h
            if by == brick_h - 1 or bx == brick_w - 1:
                c.set(x, y, mor)
                continue
            lvl = 2
            if by == 0 or bx == 0:
                lvl = 3
            elif by == brick_h - 2:
                lvl = 1
            c.set(x, y, tones[lvl])
    for _ in range(size // 2):   # wear
        x, y = rnd.randrange(size), rnd.randrange(size)
        if c.get(x, y) != mor:
            c.set(x, y, tones[1])
    return c


def wood_planks(size: int = 16, base: ColorLike = "#b86f50", seed: int = 6) -> Canvas:
    rnd = random.Random(seed)
    tones = ramp(base, 2, 1)
    c = Canvas(size, size)
    plank_h = 4
    for y in range(size):
        by = y % plank_h
        for x in range(size):
            lvl = 2 if by not in (0, plank_h - 1) else (3 if by == 0 else 0)
            grain = math.sin((x + (y // plank_h) * 5) * 0.9 + rnd.random() * 0.4)
            if lvl == 2 and grain > 0.85:
                lvl = 1
            c.set(x, y, tones[lvl])
        if by == 1:
            nail_x = (y // plank_h * 7 + 3) % size
            c.set(nail_x, y, tones[0])
    return c


def water(frames: int = 4, size: int = 16, base: ColorLike = "#0099db", seed: int = 7) -> Animation:
    """Looping animated water; foam highlights drift and shimmer."""
    noise = ValueNoise(seed, period=4)
    tones = ramp(base, 2, 2)
    anim = Animation("water")
    for f in range(frames):
        t = f / frames
        c = Canvas(size, size)
        for y in range(size):
            for x in range(size):
                v = noise.fbm(x / size * 4 + t * 4, y / size * 4, 2)
                wave = math.sin((x / size + t) * math.tau + y / size * math.tau * 2)
                val = 0.35 + 0.35 * v + 0.15 * wave
                c.set(x, y, dither_pick(tones[1:4], val, x, y))
                if wave > 0.93 and bayer(x, y) > 0.4:
                    c.set(x, y, tones[4])
        anim.add(c, 220)
    return anim


def tileset(seed: int = 1, size: int = 16) -> Sprite:
    """All terrain tiles as one sprite: static tiles are 1-frame animations."""
    sp = Sprite("tiles", size, size)
    for name, fn in (("grass", grass), ("dirt", dirt), ("sand", sand), ("cobblestone", cobblestone),
                     ("bricks", bricks), ("wood", wood_planks)):
        kw = {"size": size}
        if name not in ("bricks", "wood"):
            kw["seed"] = seed
        sp.add(Animation(name, loop=False).add(fn(**kw), 1000))
    sp.add(water(size=size))
    return sp


def tiled_preview(tile: Canvas, nx: int = 3, ny: int = 3) -> Canvas:
    """Repeat a tile to check seams."""
    c = Canvas(tile.width * nx, tile.height * ny)
    for j in range(ny):
        for i in range(nx):
            c.blit(tile, i * tile.width, j * tile.height)
    return c
