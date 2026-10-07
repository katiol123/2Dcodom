"""Colors and hue-shifted ramps.

A color is a plain ``(r, g, b, a)`` tuple of ints in 0..255.  Everything in the
engine accepts either such a tuple or a hex string (``"#e43b44"``,
``"e43b44"``, ``"#e43b44ff"``) wherever a color is expected.

Pixel-art ramps are *not* made by simply darkening/lightening a color.  Following
common practice (Lospec, Slynyrd, Saint11 tutorials) we shift the hue as well:
shadows rotate toward cool blue/purple and gain saturation, highlights rotate
toward warm yellow and lose a little saturation.  See :func:`ramp`.
"""

from __future__ import annotations

import colorsys
from typing import Iterable, Sequence, Tuple, Union

RGBA = Tuple[int, int, int, int]
ColorLike = Union[str, Sequence[int]]

TRANSPARENT: RGBA = (0, 0, 0, 0)

# Hue (degrees) that shadows and highlights drift toward.
COOL_HUE = 245.0   # blue-violet
WARM_HUE = 55.0    # yellow-orange


def _clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return lo if v < lo else hi if v > hi else v


def rgba(c: ColorLike) -> RGBA:
    """Normalize any color-like value to an ``(r, g, b, a)`` tuple."""
    if isinstance(c, str):
        s = c.strip().lstrip("#")
        if len(s) == 3:
            s = "".join(ch * 2 for ch in s)
        if len(s) == 6:
            s += "ff"
        if len(s) != 8:
            raise ValueError(f"bad hex color: {c!r}")
        return tuple(int(s[i:i + 2], 16) for i in (0, 2, 4, 6))  # type: ignore[return-value]
    t = tuple(int(v) for v in c)
    if len(t) == 3:
        return (t[0], t[1], t[2], 255)
    if len(t) == 4:
        return t  # type: ignore[return-value]
    raise ValueError(f"bad color: {c!r}")


def to_hex(c: ColorLike) -> str:
    r, g, b, a = rgba(c)
    return f"#{r:02x}{g:02x}{b:02x}" + ("" if a == 255 else f"{a:02x}")


def to_hsv(c: ColorLike) -> Tuple[float, float, float]:
    """Return (hue degrees 0..360, saturation 0..1, value 0..1)."""
    r, g, b, _ = rgba(c)
    h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
    return h * 360.0, s, v


def from_hsv(h: float, s: float, v: float, a: int = 255) -> RGBA:
    r, g, b = colorsys.hsv_to_rgb((h % 360.0) / 360.0, _clamp(s), _clamp(v))
    return (round(r * 255), round(g * 255), round(b * 255), a)


def luminance(c: ColorLike) -> float:
    """Perceived brightness 0..1 (Rec. 601 luma)."""
    r, g, b, _ = rgba(c)
    return (0.299 * r + 0.587 * g + 0.114 * b) / 255.0


def mix(a: ColorLike, b: ColorLike, t: float) -> RGBA:
    ca, cb = rgba(a), rgba(b)
    return tuple(round(x + (y - x) * t) for x, y in zip(ca, cb))  # type: ignore[return-value]


def rotate_hue_toward(h: float, target: float, amount: float) -> float:
    """Rotate hue ``h`` toward ``target`` by at most ``amount`` degrees (shortest way)."""
    diff = (target - h + 540.0) % 360.0 - 180.0
    step = max(-abs(amount), min(abs(amount), diff))
    return (h + step) % 360.0


def shade(c: ColorLike, step: float, hue_shift: float = 18.0,
          value_step: float = 0.16, sat_step: float = 0.08) -> RGBA:
    """Shift a color ``step`` levels darker (negative) or lighter (positive).

    Darker levels rotate the hue toward :data:`COOL_HUE` and add saturation,
    lighter levels rotate toward :data:`WARM_HUE`, add value and drop a bit of
    saturation.  Grays (low saturation) get only a subtle tint.
    """
    h, s, v = to_hsv(c)
    a = rgba(c)[3]
    if step == 0:
        return rgba(c)
    tint = hue_shift * (0.35 + 0.65 * min(1.0, s * 2.0))  # grays shift less
    if step < 0:
        n = -step
        h = rotate_hue_toward(h, COOL_HUE, tint * n)
        s = s + sat_step * n * (0.6 if s < 0.15 else 1.0)
        v = v - value_step * n * (0.9 + 0.2 * v)
    else:
        n = step
        h = rotate_hue_toward(h, WARM_HUE, tint * n)
        s = s - sat_step * n * 0.9
        v = v + value_step * n * (1.0 - 0.35 * v)
        if v > 1.0:  # out of headroom: push into desaturation instead
            s -= (v - 1.0) * 0.8
    return from_hsv(h, _clamp(s), _clamp(v, 0.04, 1.0), a)


def ramp(base: ColorLike, darker: int = 2, lighter: int = 2, **kw) -> list:
    """Build a hue-shifted ramp ``[darkest, ..., base, ..., lightest]``.

    The default (2, 2) gives the 5-level ramp used by :class:`~pixelforge.shading.Material`:
    index 0 = outline/deep shadow, 1 = shadow, 2 = base, 3 = light, 4 = highlight.
    """
    return [shade(base, i, **kw) for i in range(-darker, lighter + 1)]


def color_distance(a: ColorLike, b: ColorLike) -> float:
    """Cheap perceptual distance ("redmean" approximation)."""
    r1, g1, b1, _ = rgba(a)
    r2, g2, b2, _ = rgba(b)
    rm = (r1 + r2) / 2.0
    dr, dg, db = r1 - r2, g1 - g2, b1 - b2
    return ((2 + rm / 256) * dr * dr + 4 * dg * dg + (2 + (255 - rm) / 256) * db * db) ** 0.5


def nearest(c: ColorLike, colors: Iterable[ColorLike]) -> RGBA:
    c = rgba(c)
    best = min((rgba(p) for p in colors), key=lambda p: color_distance(c, p))
    return (best[0], best[1], best[2], c[3])
