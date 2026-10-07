"""Palettes: named color sets plus a few classic, well-tested pixel-art palettes.

Restricting the final art to a palette is one of the defining traits of pixel
art; it keeps sprites, tiles and UI visually coherent.  Use
:meth:`Palette.quantize` (or ``Canvas.quantize``) to snap generated art to one.
"""

from __future__ import annotations

from typing import Dict, Iterable, List, Optional

from .color import RGBA, ColorLike, nearest, rgba, ramp, luminance


class Palette:
    def __init__(self, name: str, colors: Iterable[ColorLike],
                 names: Optional[Dict[str, int]] = None):
        self.name = name
        self.colors: List[RGBA] = [rgba(c) for c in colors]
        self.names = dict(names or {})

    def __len__(self) -> int:
        return len(self.colors)

    def __getitem__(self, key) -> RGBA:
        if isinstance(key, str):
            return self.colors[self.names[key]]
        return self.colors[key]

    def nearest(self, c: ColorLike) -> RGBA:
        return nearest(c, self.colors)

    def sorted_by_luminance(self) -> List[RGBA]:
        return sorted(self.colors, key=luminance)

    def quantize_ramp(self, base: ColorLike, **kw) -> List[RGBA]:
        """Hue-shifted ramp of ``base`` with each step snapped to this palette.

        Duplicate neighbours (two steps snapping to the same entry) are kept, so
        the ramp length is always stable.
        """
        return [self.nearest(c) for c in ramp(base, **kw)]


# --- classic palettes ---------------------------------------------------------

PICO8 = Palette("pico-8", [
    "#000000", "#1d2b53", "#7e2553", "#008751", "#ab5236", "#5f574f", "#c2c3c7", "#fff1e8",
    "#ff004d", "#ffa300", "#ffec27", "#00e436", "#29adff", "#83769c", "#ff77a8", "#ffccaa",
])

# ENDESGA 32 by Endesga (lospec.com/palette-list/endesga-32)
ENDESGA32 = Palette("endesga-32", [
    "#be4a2f", "#d77643", "#ead4aa", "#e4a672", "#b86f50", "#733e39", "#3e2731", "#a22633",
    "#e43b44", "#f77622", "#feae34", "#fee761", "#63c74d", "#3e8948", "#265c42", "#193c3e",
    "#124e89", "#0099db", "#2ce8f5", "#ffffff", "#c0cbdc", "#8b9bb4", "#5a6988", "#3a4466",
    "#262b44", "#181425", "#ff0044", "#68386c", "#b55088", "#f6757a", "#e8b796", "#c28569",
])

# Sweetie 16 by GrafxKid
SWEETIE16 = Palette("sweetie-16", [
    "#1a1c2c", "#5d275d", "#b13e53", "#ef7d57", "#ffcd75", "#a7f070", "#38b764", "#257179",
    "#29366f", "#3b5dc9", "#41a6f6", "#73eff7", "#f4f4f4", "#94b0c2", "#566c86", "#333c57",
])

# DawnBringer 16
DB16 = Palette("db16", [
    "#140c1c", "#442434", "#30346d", "#4e4a4e", "#854c30", "#346524", "#d04648", "#757161",
    "#597dce", "#d27d2c", "#8595a1", "#6daa2c", "#d2aa99", "#6dc2ca", "#dad45e", "#deeed6",
])

PALETTES: Dict[str, Palette] = {p.name: p for p in (PICO8, ENDESGA32, SWEETIE16, DB16)}

# Default dark used for outlines when selective outlining is off: a deep
# desaturated violet reads better than pure black (ENDESGA's darkest entry).
INK: RGBA = rgba("#181425")
