"""Export: sprite sheets (PNG + JSON), animated GIF previews, contact sheets.

Sheet layout: one row per animation, frames left to right, fixed cell size.
The JSON is engine-agnostic::

    {"image": "knight.png", "frame_width": 32, "frame_height": 32,
     "anchor": [16, 30],
     "animations": {"walk": {"row": 1, "loop": true,
                             "frames": [{"x": 0, "y": 32, "w": 32, "h": 32,
                                         "duration": 100, "events": []}, ...]}}}
"""

from __future__ import annotations

import json
import os
from typing import Dict, Iterable, List, Optional

from .anim import Animation, Sprite
from .canvas import Canvas
from .color import ColorLike, rgba


def sheet(sprite: Sprite, padding: int = 0) -> (Canvas, dict):
    anims = list(sprite.animations.values())
    cols = max((len(a.frames) for a in anims), default=1)
    cw, ch = sprite.width + padding, sprite.height + padding
    img = Canvas(cols * cw, max(1, len(anims)) * ch)
    meta = {"frame_width": sprite.width, "frame_height": sprite.height,
            "anchor": list(sprite.anchor), "animations": {}}
    for row, a in enumerate(anims):
        frames = []
        for i, f in enumerate(a.frames):
            x, y = i * cw, row * ch
            img.blit(f.image, x, y, alpha=False)
            frames.append({"x": x, "y": y, "w": sprite.width, "h": sprite.height,
                           "duration": f.duration, "events": list(f.events)})
        meta["animations"][a.name] = {"row": row, "loop": a.loop, "frames": frames}
    return img, meta


def save_sheet(sprite: Sprite, path_png: str, padding: int = 0, scale: int = 1) -> dict:
    """Write ``name.png`` and ``name.json`` (same basename). Returns the metadata."""
    img, meta = sheet(sprite, padding)
    os.makedirs(os.path.dirname(path_png) or ".", exist_ok=True)
    img.save(path_png, scale=scale)
    meta["image"] = os.path.basename(path_png)
    meta["scale"] = scale
    with open(os.path.splitext(path_png)[0] + ".json", "w", encoding="utf-8") as fh:
        json.dump(meta, fh, indent=1)
    return meta


def save_gif(anim: Animation, path: str, scale: int = 6, background: ColorLike = "#3a4466") -> None:
    """Animated GIF preview on an opaque background (GIF alpha is 1-bit)."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    frames = [f.image.to_image(scale, background).convert("RGB") for f in anim.frames]
    durations = [max(20, f.duration) for f in anim.frames]
    frames[0].save(path, save_all=True, append_images=frames[1:], duration=durations,
                   loop=0, disposal=2, optimize=False)


def save_sprite_gif(sprite: Sprite, path: str, scale: int = 5, background: ColorLike = "#3a4466",
                    gap: int = 2, order: Optional[Iterable[str]] = None) -> None:
    """One GIF playing every animation side by side (each loops on its own clock)."""
    from PIL import Image
    names = list(order or sprite.animations)
    anims = [sprite.animations[n] for n in names]
    step = 50
    total = max(a.duration for a in anims)
    total = max(total, 1200)
    cw = sprite.width + gap
    frames = []
    for t in range(0, total, step):
        c = Canvas(cw * len(anims) + gap, sprite.height + 2 * gap, background)
        for i, a in enumerate(anims):
            c.blit(a.frame_at(t).image, gap + i * cw, gap)
        frames.append(c.to_image(scale).convert("RGB"))
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    frames[0].save(path, save_all=True, append_images=frames[1:], duration=step, loop=0)


def contact_sheet(sprites: List[Sprite], path: str, scale: int = 4,
                  background: ColorLike = "#262b44", label: bool = True) -> None:
    """Static overview: every sprite, every animation, every frame."""
    from .text import draw_text
    gap = 2
    rows = []
    for s in sprites:
        for a in s.animations.values():
            rows.append((s, a))
    width = max(len(a.frames) * (s.width + gap) for s, a in rows) + gap + (44 if label else 0)
    height = sum(s.height + gap for s, _ in rows) + gap
    c = Canvas(width, height, background)
    y = gap
    for s, a in rows:
        x = gap
        if label:
            draw_text(c, f"{s.name[:6]}", x, y + 2, "#8b9bb4")
            draw_text(c, a.name[:10], x, y + 9, "#c0cbdc")
            x += 44
        for f in a.frames:
            c.blit(f.image, x, y)
            x += s.width + gap
        y += s.height + gap
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    c.save(path, scale=scale)
