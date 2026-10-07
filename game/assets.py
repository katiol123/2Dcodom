"""Builds every sprite the battle needs with PixelForge and caches the sheets.

Sheets are written as PNG+JSON (the engine's normal export) into
``.cache/battle/``; the cache key is a hash of the unit specs and the engine
source, so editing the art code regenerates the sprites automatically.
Nothing here imports pygame - the simulation only needs animation timings.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from pixelforge import fx as pfx
from pixelforge.canvas import Canvas
from pixelforge.color import mix, ramp, rgba
from pixelforge.export import save_sheet, sheet
from pixelforge.anim import Animation, Sprite
from pixelforge.shading import Ink, Material, PartBuffer, Shader
from pixelforge.units.humanoid import build_humanoid

from .units import ORDER, TEAMS, spec_for

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / ".cache" / "battle"


@dataclass
class AnimInfo:
    name: str
    durations: List[int]          # ms per frame
    events: List[List[str]]
    loop: bool

    @property
    def total(self) -> float:
        return sum(self.durations) / 1000.0

    def event_time(self, event: str) -> Optional[float]:
        """Seconds from animation start to the start of the frame carrying ``event``."""
        t = 0
        for d, ev in zip(self.durations, self.events):
            if event in ev:
                return t / 1000.0
            t += d
        return None

    def frame_at(self, t: float) -> int:
        ms = t * 1000.0
        if self.loop:
            ms %= max(1, sum(self.durations))
        for i, d in enumerate(self.durations):
            if ms < d:
                return i
            ms -= d
        return len(self.durations) - 1


def _source_hash() -> str:
    h = hashlib.sha1()
    for p in sorted((ROOT / "pixelforge").rglob("*.py")):
        h.update(p.read_bytes())
    h.update((ROOT / "game" / "units.py").read_bytes())
    return h.hexdigest()[:12]


def ensure_unit_sheets(progress: Optional[Callable[[str, int, int], None]] = None) -> Dict[str, dict]:
    """Return ``{"knight_blue": meta, ...}``; builds missing sheets (~0.6 s each)."""
    key = _source_hash()
    out_dir = CACHE / key
    out_dir.mkdir(parents=True, exist_ok=True)
    metas: Dict[str, dict] = {}
    jobs = [(k, t) for t in TEAMS for k in ORDER]
    for i, (k, team) in enumerate(jobs):
        name = f"{k}_{team.key}"
        png = out_dir / f"{name}.png"
        js = out_dir / f"{name}.json"
        if progress:
            progress(name, i, len(jobs))
        if not (png.exists() and js.exists()):
            sp = build_humanoid(spec_for(k, team))
            save_sheet(sp, str(png))
        with open(js, encoding="utf-8") as fh:
            meta = json.load(fh)
        meta["path"] = str(png)
        metas[name] = meta
    return metas


def anim_infos(meta: dict) -> Dict[str, AnimInfo]:
    return {name: AnimInfo(name, [f["duration"] for f in a["frames"]], [f["events"] for f in a["frames"]], a["loop"])
            for name, a in meta["animations"].items()}


# --- extra art made with the engine ---------------------------------------------

def arrow_canvas(angle_deg: float, length: int = 9) -> Canvas:
    """Arrow pointing at ``angle_deg`` on an 13x13 canvas (centre = arrow middle)."""
    c = Canvas(13, 13)
    a = math.radians(angle_deg)
    dx, dy = math.cos(a), math.sin(a)
    cx = cy = 6
    tail = (round(cx - dx * length / 2), round(cy - dy * length / 2))
    head = (round(cx + dx * length / 2), round(cy + dy * length / 2))
    c.line(*tail, *head, "#b86f50")
    c.set(*head, "#ffffff")
    c.set(round(cx + dx * (length / 2 - 1)), round(cy + dy * (length / 2 - 1)), "#c0cbdc")
    # fletching: two light pixels beside the tail
    nx, ny = -dy, dx
    for s in (-1, 1):
        c.set(round(tail[0] + nx * s + dx), round(tail[1] + ny * s + dy), "#ead4aa")
    return c


def background(w: int, h: int, horizon: int, seed: int = 4) -> Canvas:
    """Sky gradient, two mountain ranges (atmospheric perspective), forest line,
    grass field with dirt patches, rocks, flowers and tufts."""
    rnd = random.Random(seed)
    c = Canvas(w, h)
    sky = [rgba(x) for x in ("#3a4466", "#5a6988", "#8b9bb4", "#c0cbdc", "#ead4aa")]
    for y in range(horizon):
        t = y / horizon
        for x in range(w):
            c.set(x, y, pfx.dither_pick(sky, t ** 1.2, x, y))
    # sun glow
    c.circle(w * 0.72, horizon * 0.42, 9, "#fee761")
    c.circle(w * 0.72, horizon * 0.42, 6, "#ffffff")
    # two mountain ranges; the far one lighter and bluer (atmospheric perspective)
    noise = pfx.ValueNoise(seed, period=16)
    for layer, (col, base, amp, freq) in enumerate((("#8b9bb4", 0.62, 0.42, 4.0), ("#5a6988", 0.86, 0.30, 7.0))):
        tones = ramp(col, 1, 1)
        snow = rgba("#ffffff") if layer == 0 else tones[2]
        for x in range(w):
            ridge = 1.0 - abs(noise.fbm(x / w * freq + layer * 3.7, layer * 1.3, 3) * 2 - 1)  # sharp crests
            top = int(horizon * (base - amp * ridge ** 1.6))
            # light from the left: slopes falling to the right are lit
            nxt = 1.0 - abs(noise.fbm((x + 1) / w * freq + layer * 3.7, layer * 1.3, 3) * 2 - 1)
            lit = nxt < ridge
            for y in range(top, horizon):
                depth = y - top
                if layer == 0 and depth < 3 and ridge > 0.8:
                    c.set(x, y, snow)
                elif depth < 6 and lit and pfx.bayer(x, y) < 0.8 - depth * 0.12:
                    c.set(x, y, tones[2])
                else:
                    c.set(x, y, tones[1] if depth > 1 else tones[2])
    # forest line on the horizon
    fr = ramp("#265c42", 2, 1)
    for x in range(-4, w + 4, 5):
        r = rnd.uniform(4, 7)
        cy = horizon - r * 0.6 + rnd.uniform(-1, 1)
        c.ellipse(x + 0.5, cy, r * 0.8, r, fr[1])
        c.ellipse(x - 0.5, cy - 1, r * 0.5, r * 0.7, fr[2])
    for x in range(w):
        for y in range(horizon - 2, horizon + 3):
            c.set(x, y, fr[0] if y >= horizon else c.get(x, y))
    # field
    g = ramp("#3e8948", 2, 2)
    d = ramp("#b86f50", 2, 1)
    fnoise = pfx.ValueNoise(seed + 1, period=12)
    for y in range(horizon + 3, h):
        depth = (y - horizon) / (h - horizon)        # 0 far .. 1 near
        for x in range(w):
            v = fnoise.fbm(x / 40, y / 22, 3)
            patch = fnoise(x / 70 + 5, y / 30 + 5)
            if patch > 0.72 and depth > 0.15:
                col = pfx.dither_pick(d[1:4], v, x, y)
            else:
                col = pfx.dither_pick(g[1:4] if depth > 0.25 else g[0:3], v * 0.8 + depth * 0.25, x, y)
            c.set(x, y, col)
    # tufts / flowers / rocks, denser and bigger near the camera
    rock = Material.of("rock", "#8b9bb4")
    for _ in range(int(w * h / 260)):
        x, y = rnd.randrange(w), rnd.randrange(horizon + 6, h)
        k = rnd.random()
        if k < 0.75:
            c.set(x, y, g[3])
            c.set(x, y - 1, g[4] if rnd.random() < 0.3 else g[3])
            c.set(x + 1, y, g[1])
        elif k < 0.92:
            c.set(x, y, rnd.choice(["#fee761", "#ffffff", "#f6757a", "#2ce8f5"]))
        else:
            buf = PartBuffer(9, 7)
            r = 1.5 + (y - horizon) / (h - horizon) * 2
            buf.ellipse(4.5, 4, r + 0.5, r * 0.75, Ink(rock, "r"))
            c.blit(Shader().render(buf), x - 4, y - 4)
    return c


def scorch(r: int = 9) -> Canvas:
    """Burnt ground decal under an explosion."""
    c = Canvas(r * 2 + 2, r + 2)
    tones = [rgba("#181425"), rgba("#262b44"), rgba("#3e2731")]
    for y in range(c.height):
        for x in range(c.width):
            d = math.hypot((x + 0.5 - c.width / 2) / r, (y + 0.5 - c.height / 2) / (r / 2))
            if d < 1 and pfx.bayer(x, y) > d * 0.9:
                c.set(x, y, tones[min(2, int(d * 3))])
    return c


