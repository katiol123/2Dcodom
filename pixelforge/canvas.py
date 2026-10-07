"""Pixel grids and pixel-perfect raster primitives.

:class:`Grid` stores arbitrary per-pixel values (``None`` = empty) and owns all
drawing primitives.  :class:`Canvas` is a Grid of RGBA colors with image
operations (blit, flip, scale, quantize, export).  The rig renderer uses a Grid
of *part references* instead of colors so shading can be done afterwards.

All primitives sample at pixel centers (``x + 0.5``), which keeps shapes
symmetric and stable between animation frames.
"""

from __future__ import annotations

import math
from typing import Callable, Dict, Iterable, Iterator, List, Optional, Sequence, Tuple

from .color import RGBA, ColorLike, rgba, nearest

Point = Tuple[float, float]


class Grid:
    def __init__(self, width: int, height: int, fill=None):
        self.width = int(width)
        self.height = int(height)
        self.px: List = [fill] * (self.width * self.height)

    # --- basic access ---------------------------------------------------------
    def in_bounds(self, x: int, y: int) -> bool:
        return 0 <= x < self.width and 0 <= y < self.height

    def get(self, x: int, y: int, default=None):
        if 0 <= x < self.width and 0 <= y < self.height:
            return self.px[y * self.width + x]
        return default

    def set(self, x: int, y: int, v) -> None:
        x, y = int(x), int(y)
        if 0 <= x < self.width and 0 <= y < self.height:
            self.px[y * self.width + x] = v

    def plot(self, x: int, y: int, v) -> None:
        """Hook used by all primitives; subclasses may add depth tests etc."""
        self.set(x, y, v)

    def filled(self, x: int, y: int) -> bool:
        return self.get(x, y) is not None

    def clear(self, v=None) -> None:
        self.px = [v] * (self.width * self.height)

    def coords(self) -> Iterator[Tuple[int, int]]:
        for y in range(self.height):
            for x in range(self.width):
                yield x, y

    def items(self) -> Iterator[Tuple[int, int, object]]:
        w = self.width
        for i, v in enumerate(self.px):
            if v is not None:
                yield i % w, i // w, v

    def copy(self):
        g = self.__class__.__new__(self.__class__)
        g.__dict__.update(self.__dict__)
        g.px = list(self.px)
        return g

    def bbox(self) -> Optional[Tuple[int, int, int, int]]:
        """(x0, y0, x1, y1) inclusive bounds of non-empty pixels, or None."""
        xs, ys = [], []
        for x, y, _ in self.items():
            xs.append(x)
            ys.append(y)
        if not xs:
            return None
        return min(xs), min(ys), max(xs), max(ys)

    def shifted(self, dx: int, dy: int):
        g = self.copy()
        g.clear()
        for x, y, v in self.items():
            g.set(x + dx, y + dy, v)
        return g

    # --- primitives -----------------------------------------------------------
    def line(self, x0: float, y0: float, x1: float, y1: float, v) -> None:
        """1px Bresenham line (pixel-perfect: no doubled corners)."""
        x0, y0, x1, y1 = int(math.floor(x0)), int(math.floor(y0)), int(math.floor(x1)), int(math.floor(y1))
        dx, dy = abs(x1 - x0), -abs(y1 - y0)
        sx, sy = (1 if x0 < x1 else -1), (1 if y0 < y1 else -1)
        err = dx + dy
        while True:
            self.plot(x0, y0, v)
            if x0 == x1 and y0 == y1:
                break
            e2 = 2 * err
            if e2 >= dy:
                err += dy
                x0 += sx
            if e2 <= dx:
                err += dx
                y0 += sy

    def polyline(self, pts: Sequence[Point], v, closed: bool = False) -> None:
        pts = list(pts)
        if closed and pts:
            pts.append(pts[0])
        for a, b in zip(pts, pts[1:]):
            self.line(a[0], a[1], b[0], b[1], v)

    def rect(self, x: int, y: int, w: int, h: int, v, fill: bool = True) -> None:
        for yy in range(int(y), int(y + h)):
            for xx in range(int(x), int(x + w)):
                if fill or yy in (y, y + h - 1) or xx in (x, x + w - 1):
                    self.plot(xx, yy, v)

    def ellipse(self, cx: float, cy: float, rx: float, ry: float, v, fill: bool = True) -> None:
        """Ellipse centred at (cx, cy) in continuous coordinates.

        ``ellipse(8, 8, 3, 3)`` covers exactly 6 pixels across (5..10);
        use half-integer centres (8.5) for odd diameters.
        """
        rx, ry = max(rx, 0.5), max(ry, 0.5)
        inside = set()
        for y in range(int(math.floor(cy - ry)) - 1, int(math.ceil(cy + ry)) + 1):
            for x in range(int(math.floor(cx - rx)) - 1, int(math.ceil(cx + rx)) + 1):
                ex = (x + 0.5 - cx) / rx
                ey = (y + 0.5 - cy) / ry
                if ex * ex + ey * ey <= 1.0 + 1e-9:
                    inside.add((x, y))
        for x, y in inside:
            if fill or any((x + dx, y + dy) not in inside for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))):
                self.plot(x, y, v)

    def circle(self, cx: float, cy: float, r: float, v, fill: bool = True) -> None:
        self.ellipse(cx, cy, r, r, v, fill)

    def capsule(self, x0: float, y0: float, x1: float, y1: float, width: float, v) -> None:
        """Thick line with round caps; ``width <= 1`` falls back to Bresenham."""
        if width <= 1.0:
            self.line(x0, y0, x1, y1, v)
            return
        r = width / 2.0
        vx, vy = x1 - x0, y1 - y0
        ll = vx * vx + vy * vy
        for y in range(int(math.floor(min(y0, y1) - r)) - 1, int(math.ceil(max(y0, y1) + r)) + 1):
            for x in range(int(math.floor(min(x0, x1) - r)) - 1, int(math.ceil(max(x0, x1) + r)) + 1):
                px, py = x + 0.5, y + 0.5
                t = 0.0 if ll == 0 else max(0.0, min(1.0, ((px - x0) * vx + (py - y0) * vy) / ll))
                qx, qy = x0 + vx * t - px, y0 + vy * t - py
                if qx * qx + qy * qy <= r * r + 1e-9:
                    self.plot(x, y, v)

    def polygon(self, pts: Sequence[Point], v) -> None:
        """Filled polygon (even-odd rule, pixel-centre sampling)."""
        pts = [(float(a), float(b)) for a, b in pts]
        if len(pts) < 3:
            self.polyline(pts, v)
            return
        ys = [p[1] for p in pts]
        n = len(pts)
        for y in range(int(math.floor(min(ys))), int(math.ceil(max(ys))) + 1):
            sy = y + 0.5
            xs = []
            for i in range(n):
                (ax, ay), (bx, by) = pts[i], pts[(i + 1) % n]
                if (ay <= sy < by) or (by <= sy < ay):
                    xs.append(ax + (sy - ay) * (bx - ax) / (by - ay))
            xs.sort()
            for a, b in zip(xs[::2], xs[1::2]):
                for x in range(int(math.ceil(a - 0.5)), int(math.floor(b - 0.5)) + 1):
                    self.plot(x, y, v)

    def flood_fill(self, x: int, y: int, v) -> None:
        if not self.in_bounds(x, y):
            return
        target = self.get(x, y)
        if target == v:
            return
        stack = [(x, y)]
        while stack:
            cx, cy = stack.pop()
            if self.in_bounds(cx, cy) and self.get(cx, cy) == target:
                self.set(cx, cy, v)
                stack.extend(((cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)))

    def stamp(self, rows: Sequence[str], x: int, y: int, mapping: Dict[str, object],
              flip_x: bool = False) -> None:
        """Draw ASCII art: each char is looked up in ``mapping``; unknown chars
        (conventionally ``.`` or space) are skipped."""
        for j, row in enumerate(rows):
            w = len(row)
            for i, ch in enumerate(row):
                if ch in mapping:
                    xx = x + (w - 1 - i if flip_x else i)
                    self.plot(xx, y + j, mapping[ch])


class Canvas(Grid):
    """RGBA image. Empty pixels are ``None`` (fully transparent)."""

    def __init__(self, width: int, height: int, fill: Optional[ColorLike] = None):
        super().__init__(width, height, None if fill is None else rgba(fill))

    def set(self, x: int, y: int, v) -> None:
        if v is not None and not (isinstance(v, tuple) and len(v) == 4):
            v = rgba(v)
        if v is not None and v[3] == 0:
            v = None
        super().set(x, y, v)

    @classmethod
    def from_ascii(cls, rows: Sequence[str], mapping: Dict[str, ColorLike]) -> "Canvas":
        c = cls(max(len(r) for r in rows), len(rows))
        c.stamp(rows, 0, 0, {k: rgba(v) for k, v in mapping.items()})
        return c

    # --- compositing ----------------------------------------------------------
    def blit(self, src: "Canvas", x: int = 0, y: int = 0, flip_x: bool = False,
             flip_y: bool = False, alpha: bool = True) -> None:
        for sx, sy, c in src.items():
            dx = x + (src.width - 1 - sx if flip_x else sx)
            dy = y + (src.height - 1 - sy if flip_y else sy)
            if alpha and c[3] < 255:
                under = self.get(dx, dy)
                if under is not None:
                    a = c[3] / 255
                    c = tuple(round(u + (v - u) * a) for u, v in zip(under[:3], c[:3])) + (max(under[3], c[3]),)
            self.set(dx, dy, c)

    def flipped(self, horizontal: bool = True) -> "Canvas":
        out = Canvas(self.width, self.height)
        out.blit(self, flip_x=horizontal, flip_y=not horizontal, alpha=False)
        return out

    def scaled(self, k: int) -> "Canvas":
        out = Canvas(self.width * k, self.height * k)
        for x, y, c in self.items():
            out.rect(x * k, y * k, k, k, c)
        return out

    def map_colors(self, fn: Callable[[RGBA], Optional[RGBA]]) -> "Canvas":
        out = self.copy()
        out.px = [None if c is None else fn(c) for c in self.px]
        return out

    def replace(self, mapping: Dict[ColorLike, ColorLike]) -> "Canvas":
        """Palette swap: ``{old: new}`` (great for team colors / variants)."""
        m = {rgba(k): rgba(v) for k, v in mapping.items()}
        return self.map_colors(lambda c: m.get(c, c))

    def quantize(self, palette) -> "Canvas":
        colors = palette.colors if hasattr(palette, "colors") else [rgba(c) for c in palette]
        cache: Dict[RGBA, RGBA] = {}

        def q(c):
            if c not in cache:
                cache[c] = nearest(c, colors)
            return cache[c]
        return self.map_colors(q)

    def colors(self) -> List[RGBA]:
        return sorted({c for c in self.px if c is not None})

    # --- export ---------------------------------------------------------------
    def to_image(self, scale: int = 1, background: Optional[ColorLike] = None):
        from PIL import Image
        img = Image.new("RGBA", (self.width, self.height), (0, 0, 0, 0) if background is None else rgba(background))
        data = [c if c is not None else (0, 0, 0, 0) for c in self.px]
        layer = Image.new("RGBA", (self.width, self.height))
        layer.putdata(data)
        img.alpha_composite(layer)
        if scale != 1:
            img = img.resize((self.width * scale, self.height * scale), Image.NEAREST)
        return img

    def save(self, path: str, scale: int = 1, background: Optional[ColorLike] = None) -> None:
        self.to_image(scale, background).save(path)

    @classmethod
    def from_image(cls, img) -> "Canvas":
        img = img.convert("RGBA")
        c = cls(img.width, img.height)
        c.px = [p if p[3] else None for p in img.getdata()]
        return c

    @classmethod
    def load(cls, path: str) -> "Canvas":
        from PIL import Image
        return cls.from_image(Image.open(path))
