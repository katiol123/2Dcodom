"""UI pieces: beveled panels / 9-slice frames, buttons, bars, cursor."""

from __future__ import annotations

from typing import Optional

from ..canvas import Canvas
from ..color import ColorLike, ramp, rgba
from ..palette import INK
from ..text import draw_text, text_width


def panel(w: int, h: int, base: ColorLike = "#3a4466", border: ColorLike = "#8b9bb4",
          ink: ColorLike = INK, corner: int = 2) -> Canvas:
    """Rounded beveled frame: dark ink outline, lit top-left border, shaded
    bottom-right, flat fill.  Works as a 9-slice source as well."""
    c = Canvas(w, h)
    b = ramp(border, 1, 1)
    f = rgba(base)
    k = rgba(ink)
    for y in range(h):
        for x in range(w):
            # cut corners for a rounded look
            cx = min(x, w - 1 - x)
            cy = min(y, h - 1 - y)
            if cx + cy < corner - 1:
                continue
            edge = cx == 0 or cy == 0 or cx + cy == corner - 1
            if edge:
                c.set(x, y, k)
            elif cx == 1 or cy == 1 or cx + cy == corner:
                lit = (x < w / 2 and cx == 1) or (y < h / 2 and cy == 1)
                c.set(x, y, b[2] if lit else b[0])
            else:
                c.set(x, y, f)
    return c


def nine_slice(src: Canvas, w: int, h: int, border: int = 4) -> Canvas:
    """Stretch a frame to (w, h) keeping its ``border``-px edges crisp."""
    out = Canvas(w, h)
    sw, sh = src.width, src.height

    def sx(x):
        if x < border:
            return x
        if x >= w - border:
            return sw - (w - x)
        return border + (x - border) % max(1, sw - 2 * border)

    def sy(y):
        if y < border:
            return y
        if y >= h - border:
            return sh - (h - y)
        return border + (y - border) % max(1, sh - 2 * border)
    for y in range(h):
        for x in range(w):
            out.set(x, y, src.get(sx(x), sy(y)))
    return out


def button(label: str, pressed: bool = False, base: ColorLike = "#124e89", text: ColorLike = "#ffffff",
           pad: int = 4) -> Canvas:
    w = text_width(label) + pad * 2 + 2
    h = 5 + pad * 2 - 1
    r = ramp(base, 1, 1)
    c = Canvas(w, h + 1)
    face = panel(w, h, base=r[1] if pressed else r[1], border=base)
    c.blit(face, 0, 1 if pressed else 0)
    if not pressed:   # 1px drop "thickness" under the button
        for x in range(1, w - 1):
            c.set(x, h, INK)
    draw_text(c, label, pad + 1, pad - 1 + (1 if pressed else 0), text, shadow=r[0])
    return c


def bar(w: int, value: float, color: ColorLike = "#e43b44", back: ColorLike = "#262b44", h: int = 5) -> Canvas:
    """Health/mana bar with a lit top row and dark bottom row in the fill."""
    c = Canvas(w, h)
    fill = ramp(color, 1, 1)
    k = rgba(INK)
    c.rect(0, 0, w, h, k)
    c.rect(1, 1, w - 2, h - 2, rgba(back))
    n = round((w - 2) * max(0.0, min(1.0, value)))
    for x in range(1, 1 + n):
        for y in range(1, h - 1):
            c.set(x, y, fill[2] if y == 1 else fill[0] if y == h - 2 else fill[1])
    c.set(0, 0, None)
    c.set(w - 1, 0, None)
    c.set(0, h - 1, None)
    c.set(w - 1, h - 1, None)
    return c


CURSOR = [
    "K.........",
    "KK........",
    "KWK.......",
    "KWWK......",
    "KWWWK.....",
    "KWWWWK....",
    "KWWWWWK...",
    "KWWWWWWK..",
    "KWWWWKKKK.",
    "KWKWWK....",
    "KK.KWWK...",
    "K...KWK...",
    ".....KK...",
]


def cursor(fill: ColorLike = "#ffffff", ink: ColorLike = INK) -> Canvas:
    return Canvas.from_ascii(CURSOR, {"K": ink, "W": fill})


def label(text: str, color: ColorLike = "#ffffff", shadow: Optional[ColorLike] = INK) -> Canvas:
    c = Canvas(text_width(text) + 1, 6)
    draw_text(c, text, 0, 0, color, shadow=shadow)
    return c
