"""Materials, part buffers and the pixel-art shader.

Workflow: draw *shapes* (not colors) into a :class:`PartBuffer` using an
:class:`Ink` (material + shading group + depth), then let :class:`Shader`
turn it into colors.  The shader reproduces what pixel artists do by hand:

* **directional light** (default top-left) - every shading group gets a
  1px lit rim on the side facing the light and a wider shadow band on the
  opposite side.  Normals come from the silhouette of the group, so there is
  no "pillow shading" (darkening every edge equally);
* **hue-shifted ramps** - shadows go cool, lights go warm (see :mod:`color`);
* **depth** - far limbs are drawn one ramp step darker, a classic trick for
  side-view sprites that separates left/right limbs;
* **occlusion contours** - where a part overlaps another, the part behind
  gets a shadow line so overlapping shapes stay readable at tiny sizes;
* **selective outline ("selout")** - the outline takes the darkest color of
  the material it wraps (instead of pure black) and is lighter on the lit
  side; or a solid outline color, or none.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
from typing import Dict, List, Optional, Sequence, Tuple

from .canvas import Canvas, Grid
from .color import RGBA, ColorLike, mix, ramp, rgba
from .palette import INK

# Shade levels inside a 5-step ramp.
OUTLINE, SHADOW, BASE, LIGHT, HIGHLIGHT = 0, 1, 2, 3, 4


@dataclass
class Material:
    name: str
    ramp: List[RGBA]
    shiny: bool = False          # allow specular HIGHLIGHT pixels
    flat: bool = False           # no automatic shading (eyes, glow, UI)
    outline: Optional[RGBA] = None

    @classmethod
    def of(cls, name: str, base: ColorLike, shiny: bool = False, flat: bool = False,
           outline: Optional[ColorLike] = None, **ramp_kw) -> "Material":
        return cls(name, ramp(base, **ramp_kw), shiny, flat, None if outline is None else rgba(outline))

    @classmethod
    def from_ramp(cls, name: str, colors: Sequence[ColorLike], **kw) -> "Material":
        cols = [rgba(c) for c in colors]
        while len(cols) < 5:  # pad short hand-made ramps symmetrically
            cols = ([cols[0]] + cols) if len(cols) % 2 == 0 else (cols + [cols[-1]])
        return cls(name, cols[:5], **kw)

    def color(self, level: int) -> RGBA:
        return self.ramp[max(0, min(len(self.ramp) - 1, level))]

    @property
    def base(self) -> RGBA:
        return self.ramp[len(self.ramp) // 2]


@dataclass(frozen=True)
class Ink:
    """What a pixel of a :class:`PartBuffer` holds."""
    material: Material = field(compare=False)
    group: str = ""              # pixels of one group are shaded as one volume
    z: float = 0.0               # higher draws on top
    depth: int = 0               # ramp offset (-1 = farther / darker)
    level: Optional[int] = None  # force a shade level (details like eyes)
    contour: bool = True         # cast occlusion contour on parts behind
    outline: bool = True         # take part in the outline pass

    def with_(self, **kw) -> "Ink":
        return replace(self, **kw)


class PartBuffer(Grid):
    """Grid of :class:`Ink` with a z-test: a plot only wins if z >= current z."""

    def plot(self, x: int, y: int, v) -> None:
        if v is None:
            return
        cur = self.get(x, y)
        if cur is None or v.z >= cur.z:
            self.set(x, y, v)


_N4 = ((1, 0), (-1, 0), (0, 1), (0, -1))
_N8 = _N4 + ((1, 1), (-1, -1), (1, -1), (-1, 1))


@dataclass
class Shader:
    light: Tuple[float, float] = (-1.0, -1.2)   # direction *toward* the light (screen space)
    outline: str = "selout"                     # "selout" | "color" | "none"
    outline_color: RGBA = INK
    corners: bool = False                       # include diagonal outline pixels
    normal_radius: int = 2
    light_threshold: float = 0.35
    shadow_threshold: float = -0.25
    shadow_width: int = 2                       # px depth of the shadow band
    contours: bool = True
    selout_lit_mix: float = 0.45                # how much lighter the lit outline is

    def __post_init__(self):
        lx, ly = self.light
        n = math.hypot(lx, ly) or 1.0
        self._L = (lx / n, ly / n)
        self.outline_color = rgba(self.outline_color)

    # --- per-pixel analysis ---------------------------------------------------
    def _is_outside(self, buf: PartBuffer, ink: Ink, x: int, y: int) -> bool:
        o = buf.get(x, y)
        if o is None:
            return True
        if o.group == ink.group:
            return False
        return o.z < ink.z   # a part behind us does not continue our volume

    def level_at(self, buf: PartBuffer, x: int, y: int) -> int:
        ink: Ink = buf.get(x, y)
        if ink.level is not None:
            return ink.level
        if ink.material.flat:
            return BASE
        r = self.normal_radius
        nx = ny = 0.0
        edge = 99
        for dy in range(-r, r + 1):
            for dx in range(-r, r + 1):
                if (dx or dy) and self._is_outside(buf, ink, x + dx, y + dy):
                    d2 = dx * dx + dy * dy
                    nx += dx / d2
                    ny += dy / d2
                    edge = min(edge, max(abs(dx), abs(dy)))
        level = BASE
        n = math.hypot(nx, ny)
        if n > 1e-6:
            d = (nx * self._L[0] + ny * self._L[1]) / n
            if edge == 1 and d > self.light_threshold:
                level = HIGHLIGHT if (ink.material.shiny and d > 0.85) else LIGHT
            elif edge <= self.shadow_width and d < self.shadow_threshold:
                level = SHADOW
        if self.contours:
            for dx, dy in _N4:
                o = buf.get(x + dx, y + dy)
                if o is not None and o.group != ink.group and o.z > ink.z and o.contour:
                    level = min(level, SHADOW)
                    break
        return max(SHADOW, min(HIGHLIGHT, level + ink.depth))

    # --- passes ---------------------------------------------------------------
    def render(self, buf: PartBuffer) -> Canvas:
        out = Canvas(buf.width, buf.height)
        for x, y, ink in buf.items():
            out.set(x, y, ink.material.color(self.level_at(buf, x, y)))
        if self.outline != "none":
            self._outline(buf, out)
        return out

    def _outline(self, buf: PartBuffer, out: Canvas) -> None:
        nbrs = _N8 if self.corners else _N4
        L = self._L
        for y in range(buf.height):
            for x in range(buf.width):
                if buf.get(x, y) is not None:
                    continue
                best = None
                lit = False
                for dx, dy in nbrs:
                    o = buf.get(x + dx, y + dy)
                    if o is None or not o.outline:
                        continue
                    if best is None or o.z > best.z:
                        best = o
                        # we sit on the lit side if the vector part->us points to the light
                        lit = (-dx * L[0] - dy * L[1]) > 0.5
                if best is None:
                    continue
                if self.outline == "color":
                    c = self.outline_color
                else:
                    m = best.material
                    c = m.outline or m.color(OUTLINE)
                    if lit and m.outline is None and self.selout_lit_mix > 0:
                        c = mix(c, m.color(SHADOW), self.selout_lit_mix)
                out.set(x, y, c)


def shade_mask(mask: Grid, material: Material, shader: Optional[Shader] = None) -> Canvas:
    """Shade any filled Grid (e.g. ``Grid.stamp``-ed ASCII) as one volume."""
    buf = PartBuffer(mask.width, mask.height)
    ink = Ink(material, "mask")
    for x, y, _ in mask.items():
        buf.set(x, y, ink)
    return (shader or Shader()).render(buf)
