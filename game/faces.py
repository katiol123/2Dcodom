"""Painted officer portraits (Pillow only, no pygame).

Unlike everything else in the game these are *not* pixel art: every face is a smooth vector
drawing (supersampled curves, soft shading clipped to shapes, crisp ink lines), rendered at
whatever size the screen needs. The game blits them after the integer upscale of the pixel
frame, so they stay sharp on any display.

Faces are deterministic per officer key. How much care a face gets follows the officer's
**presence**: strong leaders (high leadership and stats) get a lifted chin, a stern gaze, a
confident smirk, rich gear, rim light and a glowing backdrop; mediocre ones get softer
features, tired eyes, plain clothes and a dull background.

All drawing happens in a 100 x 120 design space (head centred at x=50).
"""

from __future__ import annotations

import math
import random
from typing import Dict, List, Optional, Sequence, Tuple

from PIL import Image, ImageChops, ImageDraw, ImageFilter

from .factions import FACTION
from .officers import OFFICER, Officer

DW, DH = 100, 120
ZOOM, ZOOM_Y = 1.22, 60          # the head is drawn larger than the design space (shoulders get cut)
Pt = Tuple[float, float]
RGB = Tuple[int, int, int]


# --- colour helpers ---------------------------------------------------------------------------
def rgb(h: str) -> RGB:
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def mix(a: RGB, b: RGB, t: float) -> RGB:
    return tuple(int(round(x + (y - x) * t)) for x, y in zip(a, b))  # type: ignore[return-value]


def dark(c: RGB, k: float) -> RGB:
    return mix(c, (20, 12, 30), k)


def light(c: RGB, k: float) -> RGB:
    return mix(c, (255, 248, 228), k)


def grey(c: RGB, k: float) -> RGB:
    g = int(sum(c) / 3)
    return mix(c, (g, g, g), k)


# --- curves -------------------------------------------------------------------------------------
def spline(pts: Sequence[Pt], closed: bool = True, n: int = 10) -> List[Pt]:
    """Catmull-Rom curve through the points."""
    p = list(pts)
    if len(p) < 3:
        return p
    out: List[Pt] = []
    m = len(p)
    rng = range(m) if closed else range(m - 1)
    for i in rng:
        p0 = p[(i - 1) % m] if closed or i > 0 else p[0]
        p1, p2 = p[i], p[(i + 1) % m]
        p3 = p[(i + 2) % m] if closed or i + 2 < m else p[-1]
        for j in range(n):
            t = j / n
            t2, t3 = t * t, t * t * t
            out.append(tuple(0.5 * (2 * b + (-a + c) * t + (2 * a - 5 * b + 4 * c - d) * t2
                                    + (-a + 3 * b - 3 * c + d) * t3)
                             for a, b, c, d in zip(p0, p1, p2, p3)))  # type: ignore[arg-type]
    if not closed:
        out.append(p[-1])
    return out


def mirror(pts: Sequence[Pt], cx: float = 50) -> List[Pt]:
    """Points of the left half mirrored to the right, in reverse order (to close a shape)."""
    return [(2 * cx - x, y) for x, y in reversed(pts)]


class Painter:
    def __init__(self, w: int, h: int, ss: int = 3):
        self.size = (w * ss, h * ss)
        self.k = w * ss / DW
        self.z = ZOOM
        self.img = Image.new("RGB", self.size)

    def _p(self, pts: Sequence[Pt]) -> List[Tuple[float, float]]:
        k, z = self.k, self.z
        return [(((x - 50) * z + 50) * k, ((y - ZOOM_Y) * z + ZOOM_Y) * k) for x, y in pts]

    # masks
    def blank(self) -> Image.Image:
        return Image.new("L", self.size, 0)

    def poly(self, pts: Sequence[Pt], smooth: bool = True) -> Image.Image:
        m = self.blank()
        ImageDraw.Draw(m).polygon(self._p(spline(pts) if smooth else pts), fill=255)
        return m

    def ell(self, cx: float, cy: float, rx: float, ry: float) -> Image.Image:
        m = self.blank()
        (x, y), = self._p([(cx, cy)])
        rx, ry = rx * self.k * self.z, ry * self.k * self.z
        ImageDraw.Draw(m).ellipse([x - rx, y - ry, x + rx, y + ry], fill=255)
        return m

    def stroke(self, pts: Sequence[Pt], width: float, smooth: bool = True, closed: bool = False) -> Image.Image:
        m = self.blank()
        p = self._p(spline(pts, closed=closed) if smooth else pts)
        w = max(1, int(round(width * self.k * self.z)))
        d = ImageDraw.Draw(m)
        d.line(p, fill=255, width=w, joint="curve")
        r = w / 2
        for x, y in (p[0], p[-1]):                               # round caps
            d.ellipse([x - r, y - r, x + r, y + r], fill=255)
        return m

    def taper(self, pts: Sequence[Pt], w0: float, w1: float) -> Image.Image:
        """A brush stroke whose width goes from w0 to w1 (hair strands, brows, lid lines)."""
        p = spline(pts, closed=False, n=6)
        left, right = [], []
        for i, (x, y) in enumerate(p):
            a = p[max(0, i - 1)]
            b = p[min(len(p) - 1, i + 1)]
            dx, dy = b[0] - a[0], b[1] - a[1]
            ln = math.hypot(dx, dy) or 1
            w = (w0 + (w1 - w0) * i / max(1, len(p) - 1)) / 2
            nx, ny = -dy / ln * w, dx / ln * w
            left.append((x + nx, y + ny))
            right.append((x - nx, y - ny))
        return self.poly(left + right[::-1], smooth=False)

    # painting
    def fill(self, mask: Image.Image, color: RGB, alpha: float = 1.0, clip: Optional[Image.Image] = None,
             blur: float = 0.0) -> None:
        box = mask.getbbox()
        if box is None:
            return
        if blur:                                   # work on the shape's bounding box only (fast)
            pad = int(blur * self.k * self.z * 3) + 1
            box = (max(0, box[0] - pad), max(0, box[1] - pad), min(self.size[0], box[2] + pad),
                   min(self.size[1], box[3] + pad))
            m = mask.crop(box).filter(ImageFilter.GaussianBlur(blur * self.k * self.z))
        else:
            m = mask.crop(box)
        if clip is not None:
            m = ImageChops.multiply(m, clip.crop(box))
        if alpha < 1.0:
            m = m.point(lambda v: int(v * alpha))
        self.img.paste(color, box, m)

    def gradient(self, top: RGB, bottom: RGB, mask: Optional[Image.Image] = None) -> None:
        g = Image.new("RGB", (1, 256))
        for y in range(256):
            g.putpixel((0, y), mix(top, bottom, y / 255))
        g = g.resize(self.size, Image.BILINEAR)
        self.img.paste(g, (0, 0), mask)

    def result(self, w: int, h: int) -> Image.Image:
        return self.img.resize((w, h), Image.LANCZOS)


# --- per-faction looks --------------------------------------------------------------------------
_SKIN = {
    "aldern": ("#f2c7a5", "#e8b48f", "#d9a07a"),
    "sylvan": ("#efc9a2", "#d9ae84", "#e6bfa0"),
    "ashen": ("#d9cfd6", "#cbbfcc", "#e2d6d2"),
    "khanate": ("#d6a274", "#c48c5e", "#b97f52"),
    "sultanate": ("#a8704a", "#8f5a38", "#b77d52"),
    "north": ("#f6d2bc", "#f0c4a8", "#f8dccb"),
    "league": ("#e7b78f", "#d9a57a", "#c99068"),
    "highland": ("#e8a98a", "#dc9a78", "#efb898"),
    "goblin": ("#8fb04a", "#7f9e3e", "#9cbb52"),
}
_HAIR = {
    "aldern": ("#5a3a22", "#a8702e", "#e0c070", "#2e1e14"),
    "sylvan": ("#7a4a22", "#c27a3a", "#3a2a18", "#d8b070"),
    "ashen": ("#1c1820", "#e8e4ee", "#3a2e40", "#8a8090"),
    "khanate": ("#16110e", "#2a1c14", "#100c0a"),
    "sultanate": ("#120d0b", "#24160f", "#3a2418"),
    "north": ("#e8cf86", "#d9a85a", "#c0703a", "#e0c070", "#8a5a2a", "#b0602a"),
    "league": ("#2a1a12", "#6a3e22", "#a05a2a", "#1a1210"),
    "highland": ("#b0502a", "#7a3a1e", "#d07a3a", "#3a2a22"),
    "goblin": ("#2a2a1a", "#3a2e1a"),
}
_EYES = {"aldern": ("#4a78c0", "#5a8a5a", "#6a4a2a"), "sylvan": ("#3a9a5a", "#7aa04a", "#a07a3a"),
         "ashen": ("#8a6ab0", "#5a5a6a", "#a03040"), "khanate": ("#3a2416", "#5a3a1e"),
         "sultanate": ("#2a1a10", "#5a3a1a", "#8a6a2a"), "north": ("#5ab0e0", "#7ac0d0", "#4a7aa0"),
         "league": ("#6a4a2a", "#3a6a4a", "#2a2a3a"), "highland": ("#4a6aa0", "#6a5a3a", "#5a7a5a"),
         "goblin": ("#f0d030", "#e08a20", "#d0e040")}

# headwear by faction for ordinary officers (weighted by repetition); leaders are fixed below
_HATS = {
    "aldern": ("none", "none", "helm", "none"),
    "sylvan": ("hood", "none", "none", "hood", "leaves"),
    "ashen": ("hood", "none", "none", "cowl"),
    "khanate": ("furhat", "none", "furhat", "spike"),
    "sultanate": ("turban", "turban", "turban", "none"),
    "north": ("none", "nasal", "none", "nasal"),
    "league": ("beret", "none", "none", "beret"),
    "highland": ("helm", "none", "none", "helm"),
    "goblin": ("none", "rag", "none", "pot"),
}
_LEADER = {
    "aldern": dict(hat="crown", hair="short", beard="none", age=0.05, color=1),
    "sylvan": dict(hat="antlers", hair="long", beard="none", age=0.25, color=3),
    "ashen": dict(hat="circlet", hair="bald", beard="goatee", age=0.75, color=0),
    "khanate": dict(hat="furhat", hair="queue", beard="mustache", age=0.45, color=0),
    "sultanate": dict(hat="crownturban", hair="short", beard="full", age=0.5, color=0),
    "north": dict(hat="none", hair="long", beard="long", age=0.95, color=3),
    "league": dict(hat="none", hair="up", beard="none", age=0.4, color=0),
    "highland": dict(hat="crownhelm", hair="short", beard="braided", age=0.85, color=3),
    "goblin": dict(hat="none", hair="none", beard="none", age=0.6, color=0),
}


def presence(o: Officer) -> float:
    """0 (a grey nobody) .. 1 (a born leader): leadership and the average of the six stats."""
    lead = (o.leadership - 200) / 600
    stats = (sum(o.stats) / len(o.stats) - 6) / 10
    return max(0.0, min(1.0, 0.5 * lead + 0.5 * stats))


class Face:
    """All the random choices of one face."""

    def __init__(self, o: Officer):
        r = random.Random(f"face:{o.key}:{o.name}")
        f = o.faction
        self.o, self.f, self.r = o, FACTION[f], r
        self.p = 1.0 if o.rank == 0 else presence(o)
        self.hero = self.p >= 0.6
        self.plain = self.p < 0.36
        self.troll = f == "goblin" and o.rank == 0
        self.goblin = f == "goblin"
        lead = _LEADER[f] if o.rank == 0 else {}
        self.age = lead.get("age", r.random() ** 1.6)
        self.skin = rgb(r.choice(_SKIN[f]))
        if self.troll:
            self.skin = rgb("#7f9a8a")
        hc = _HAIR[f]
        self.hair = rgb(hc[lead["color"]] if "color" in lead else r.choice(hc))
        if self.age > 0.72 and not self.goblin:
            self.hair = mix(self.hair, (214, 214, 220), min(1.0, (self.age - 0.6) * 2.2))
        self.eye = rgb(r.choice(_EYES[f]))
        if o.look == "vampire":
            self.eye = rgb("#e03040")
        fem = o.female
        # geometry
        self.hw = r.uniform(17.5, 20) - (1.2 if fem else 0) + (2.5 if self.troll else 0)
        self.jw = (r.uniform(10.5, 12.5) if fem else r.uniform(13, 16.5)) + (1.5 if self.hero and not fem else 0)
        self.jw += 3 if self.troll else 0
        self.cw = r.uniform(3.5, 5) if fem else r.uniform(4.5, 7.5) + (1 if self.hero else 0)
        self.chin = r.uniform(80, 84) - (1.5 if fem else 0) + (2 if self.troll else 0)
        self.top = r.uniform(21, 24)
        self.ey = 50 + r.uniform(-1, 1)
        self.ex = r.uniform(7.8, 9.2)
        self.nose = r.uniform(0.85, 1.25) * (1.6 if self.goblin else 1)
        self.mw = r.uniform(5, 7)
        self.lift = -1.5 if self.hero else (1.0 if self.plain else 0)     # chin up / down
        self.gaze = r.choice((-0.6, 0, 0.5, 0.8))
        # style
        f_hats = _HATS[f]
        self.hat = lead.get("hat") or r.choice(f_hats)
        if o.look in ("knight", "paladin", "death_knight") and r.random() < 0.6:
            self.hat = "helm"
        if self.hat in ("helm", "nasal") and self.hero and r.random() < 0.5:
            self.hat = "none"           # heroes like to show their face
        styles = ("short", "short", "long", "bald", "tied") if not fem else ("long", "long", "tied", "up", "short")
        if f in ("north", "sylvan"):
            styles += ("long", "braids")
        if f == "khanate":
            styles = ("queue", "shaved", "queue") if not fem else ("braids", "long")
        if f == "goblin":
            styles = ("none", "tuft", "none")
        self.style = lead.get("hair") or r.choice(styles)
        beards = ("none", "stubble", "full", "goatee", "mustache", "short")
        if f in ("north", "highland"):
            beards = ("full", "long", "braided", "short", "long")
        if f == "khanate":
            beards = ("mustache", "mustache", "goatee", "none")
        if f == "sultanate":
            beards = ("full", "short", "goatee", "full")
        if f in ("sylvan", "league"):
            beards = ("none", "none", "goatee", "stubble", "short")
        self.beard = "none" if fem or self.goblin else (lead.get("beard") or r.choice(beards))
        if self.plain and self.beard == "none" and not fem and not self.goblin and r.random() < 0.5:
            self.beard = "stubble"
        self.scar = r.random() < (0.25 if not fem else 0.1) and o.rank > 0
        self.patch = r.random() < 0.06 and o.rank > 0
        self.paint = f in ("khanate", "north", "sylvan") and r.random() < 0.3
        self.earring = r.random() < (0.5 if fem else 0.2)


# --- painting ----------------------------------------------------------------------------------
def paint_face(key: str, w: int, h: int) -> Image.Image:
    """Portrait of officer ``key`` as an RGB image of exactly w x h pixels."""
    o = OFFICER[key]
    F = Face(o)
    P = Painter(w, h, ss=max(2, min(4, 400 // max(1, w))))
    _background(P, F)
    _back_hair(P, F)
    _body(P, F)
    head = _head(P, F)
    _features(P, F, head)
    _facial_hair(P, F, head)
    _front_hair(P, F, head)
    _headwear(P, F, head)
    _finish(P, F)
    return P.result(w, h)


def _background(P: Painter, F: Face) -> None:
    f = F.f
    col, dk, lt = rgb(f.color), rgb(f.dark), rgb(f.light)
    if F.plain:
        P.gradient(grey(dark(col, 0.55), 0.6), grey(dark(col, 0.75), 0.6))
        return
    P.gradient(dark(col, 0.35), dark(dk, 0.55))
    if F.hero:                                     # sunburst rays and a halo of the faction's colour
        for i in range(16):
            a0 = i * math.pi * 2 / 16
            a1 = a0 + math.pi / 16
            ray = P.poly([(50, 46), (50 + 120 * math.cos(a0), 46 + 120 * math.sin(a0)),
                          (50 + 120 * math.cos(a1), 46 + 120 * math.sin(a1))], smooth=False)
            P.fill(ray, lt, 0.07)
        P.fill(P.ell(50, 48, 42, 42), lt, 0.35, blur=12)
    else:
        P.fill(P.ell(50, 44, 36, 34), col, 0.4, blur=10)


def _shoulders() -> List[Pt]:
    return [(-4, 124), (-2, 104), (10, 95), (30, 90), (50, 89), (70, 90), (90, 95), (102, 104), (104, 124)]


def _body(P: Painter, F: Face) -> None:
    f, fk = F.f, F.f.key
    col, dk, met = rgb(f.color), rgb(f.dark), rgb(f.metal)
    if F.plain:
        col, dk = grey(col, 0.45), grey(dk, 0.45)
    cloth = col
    body = P.poly(_shoulders())
    # neck
    neck = P.poly([(41, 72), (59, 72), (60, 92), (40, 92)], smooth=False)
    P.fill(neck, F.skin)
    P.fill(P.ell(50, 74, 14, 8), dark(F.skin, 0.45), 0.8, clip=neck, blur=2)
    armour = fk in ("aldern", "highland", "north") and (F.hero or F.r.random() < 0.4) or F.o.look in (
        "knight", "paladin", "death_knight", "hammerer", "shieldbearer")
    if F.goblin:
        P.fill(body, rgb("#6a5236"))
        for i in range(5):                         # patched rags and a strap
            x = F.r.uniform(8, 88)
            P.fill(P.poly([(x, 100), (x + 9, 98), (x + 10, 110), (x + 1, 112)]), rgb("#8a6a40"), 0.8, clip=body)
        P.fill(P.stroke([(20, 124), (66, 90)], 5), rgb("#3a2a1a"), clip=body)
        P.fill(P.stroke([(20, 124), (66, 90)], 1.2), rgb("#8a6a3a"), clip=body)
    elif armour:
        steel = rgb("#9aa4b8") if fk != "highland" else rgb("#a8a0a0")
        if F.plain:
            steel = grey(steel, 0.4)
        P.fill(body, dark(steel, 0.25))
        tabard = P.poly([(34, 124), (36, 94), (50, 92), (64, 94), (66, 124)])
        P.fill(tabard, cloth)
        P.fill(P.poly([(50, 96), (54, 106), (50, 118), (46, 106)]), met, 0.9, clip=tabard)
        for side in (-1, 1):                       # pauldrons: two overlapping lames
            cx = 50 + side * 34
            for k, (y0, wd) in enumerate(((100, 19), (94, 17))):
                pts = [(cx - wd, y0 + 12), (cx - wd + 2, y0 + 2), (cx - side * 4, y0 - 3), (cx + side * 8, y0 - 2),
                       (cx + wd, y0 + 4), (cx + wd, y0 + 13), (cx, y0 + 9)]
                pl = P.poly(pts)
                P.fill(pl, steel if k else dark(steel, 0.15))
                P.fill(P.ell(cx - side * 5, y0 + 1, 10, 4), light(steel, 0.55), 0.7, clip=pl, blur=1.5)
                P.fill(P.ell(cx + side * 8, y0 + 9, 12, 5), dark(steel, 0.5), 0.7, clip=pl, blur=1.5)
                edge = ImageChops.subtract(pl, P.poly([(x, y + 1.4) for x, y in pts]))
                P.fill(edge, met if F.hero else light(steel, 0.3), 0.9)
                P.fill(P.ell(cx - side * 6, y0 + 4, 1.1, 1.1), light(steel, 0.7))
        P.fill(P.poly([(40, 90), (60, 90), (61, 95), (39, 95)], smooth=False), dark(steel, 0.35))   # gorget
    else:
        P.fill(body, cloth)
        P.fill(P.poly([(-4, 124), (-2, 104), (10, 95), (24, 92), (20, 124)]), dark(cloth, 0.3), 0.6, clip=body)
        P.fill(P.poly([(104, 124), (102, 104), (90, 95), (76, 92), (80, 124)]), dark(cloth, 0.45), 0.8, clip=body)
        P.fill(P.ell(30, 98, 20, 6), light(cloth, 0.3), 0.35, clip=body, blur=3)
        # collar shape by culture
        if fk == "league":
            P.fill(P.poly([(38, 90), (50, 106), (62, 90), (58, 89), (50, 98), (42, 89)], smooth=False), rgb("#f2ece0"))
            if not F.plain:
                chain = P.stroke([(30, 96), (40, 106), (50, 109), (60, 106), (70, 96)], 1.6)
                P.fill(chain, met if met != rgb("#7a1f2b") else rgb("#f2c84b"))
                P.fill(chain, rgb("#f2c84b"))
                P.fill(P.ell(50, 110, 3.4, 3.4), rgb("#f2c84b"))
                P.fill(P.ell(50, 110, 1.6, 1.6), rgb("#7a1f2b"))
        elif fk == "khanate":
            fur = P.poly([(26, 92), (40, 87), (50, 100), (60, 87), (74, 92), (64, 104), (50, 112), (36, 104)])
            P.fill(fur, rgb("#6a4a2e"))
            for i in range(26):
                x, y = F.r.uniform(28, 72), F.r.uniform(88, 110)
                P.fill(P.taper([(x, y), (x + F.r.uniform(-2, 2), y + 3)], 1.2, 0.2),
                       rgb("#a07a50") if i % 2 else rgb("#4a321e"), clip=fur)
            P.fill(P.stroke([(50, 100), (50, 124)], 1.2), dark(cloth, 0.5))
        elif fk == "north":
            base = rgb("#cfc8bc") if F.hero else rgb("#8a7a66")
            tufts = [(8 + i * 7, 96 + 3 * math.sin(i * 1.7)) for i in range(13)]
            fur = P.blank()
            for x, y in tufts:
                fur = ImageChops.lighter(fur, P.ell(x, y + 3, 7, 6.5))
            fur = ImageChops.multiply(fur, P.poly([(-10, 89), (110, 89), (110, 124), (-10, 124)], smooth=False))
            P.fill(fur, base)
            P.fill(fur, dark(base, 0.45), 0.7, clip=P.poly([(-10, 102), (110, 102), (110, 124), (-10, 124)],
                                                          smooth=False), blur=2)
            for i in range(70):
                x, y = F.r.uniform(4, 96), F.r.uniform(90, 104)
                P.fill(P.taper([(x, y), (x + (x - 50) * 0.04, y + 3), (x + (x - 50) * 0.06, y + 5)], 1.0, 0.15),
                       light(base, 0.45) if i % 2 else dark(base, 0.3), 0.8, clip=fur)
        elif fk == "sultanate":
            P.fill(P.poly([(40, 90), (50, 118), (60, 90)], smooth=False), rgb("#f6e7b0"))
            P.fill(P.stroke([(41, 90), (50, 117), (59, 90)], 1.4, smooth=False), rgb("#e0a832"))
        elif fk in ("ashen",):
            P.fill(P.poly([(28, 74), (38, 92), (50, 96), (62, 92), (72, 74), (66, 96), (50, 100), (34, 96)]),
                   dark(cloth, 0.55))
            if not F.plain:
                P.fill(P.ell(50, 99, 3, 3.6), rgb("#e6dcc8"))
        elif fk == "sylvan":
            P.fill(P.poly([(40, 89), (50, 97), (60, 89), (58, 92), (50, 101), (42, 92)], smooth=False), dark(cloth, 0.5))
            P.fill(P.poly([(50, 98), (54, 102), (50, 106), (46, 102)]), rgb("#c8a040"))
        else:
            P.fill(P.poly([(41, 89), (50, 97), (59, 89)], smooth=False), dark(cloth, 0.5))
    if F.hero and not F.goblin:                    # a cloak over one shoulder with a gold clasp
        cloak = P.poly([(70, 124), (76, 96), (92, 93), (104, 104), (104, 124)])
        P.fill(cloak, dark(rgb(f.color), 0.2) if fk != "league" else rgb("#7a1f2b"))
        P.fill(P.poly([(82, 124), (84, 100), (104, 104), (104, 124)]), (0, 0, 0), 0.25, clip=cloak)
        P.fill(P.ell(73, 97, 3.6, 3.6), rgb("#f2c84b"))
        P.fill(P.ell(72.2, 96.2, 1.3, 1.3), rgb("#fff4c0"))


def _head_outline(F: Face) -> List[Pt]:
    cx, hw, jw, cw, ch, top = 50, F.hw, F.jw, F.cw, F.chin, F.top
    left = [(cx - cw, ch - 1.2), (cx - jw, 71), (cx - hw + 0.6, 58), (cx - hw, 44), (cx - hw * 0.8, 29)]
    pts = [(cx, ch)] + left + [(cx, top)] + mirror(left)
    return pts


def _ears(P: Painter, F: Face) -> None:
    for side in (-1, 1):
        x = 50 + side * (F.hw - 0.5)
        if F.goblin:
            tip = (50 + side * (F.hw + 17), 40 - (4 if not F.troll else -6))
            ear = P.poly([(x, 50), tip, (x + side * 1, 62)], smooth=False)
            P.fill(ear, F.skin)
            P.fill(P.poly([(x + side * 1, 52), (tip[0] - side * 5, tip[1] + 4), (x + side * 1.5, 59)], smooth=False),
                   dark(F.skin, 0.35))
            continue
        pointy = F.f.key == "sylvan" and F.r.random() < 0.0   # Veldmar folk are human: round ears
        ear = P.ell(x + side * 1.6, 56, 3.2, 5.6) if not pointy else P.poly([(x, 51), (x + side * 7, 44), (x, 62)])
        P.fill(ear, F.skin)
        P.fill(P.ell(x + side * 1.8, 56.5, 1.5, 3.4), dark(F.skin, 0.35), 0.8)
        if F.earring:
            P.fill(P.ell(x + side * 2.2, 62.5, 1.3, 1.3), rgb("#f2c84b"))


def _head(P: Painter, F: Face) -> Image.Image:
    _ears(P, F)
    head = P.poly(_head_outline(F))
    s = F.skin
    P.fill(head, s)
    # form shading: light from the top left
    shadow = ImageChops.subtract(head, P.poly([(x - 4.5, y - 2) for x, y in _head_outline(F)]))
    P.fill(shadow, dark(s, 0.35), 0.85 if not F.plain else 0.6, blur=1.6)
    P.fill(P.ell(43, 40, 10, 9), light(s, 0.35), 0.5 if not F.plain else 0.25, clip=head, blur=4)
    if not F.plain:
        for side in (-1, 1):                       # cheekbones
            P.fill(P.poly([(50 + side * (F.hw - 1), 60), (50 + side * 10, 63), (50 + side * (F.jw - 1), 70)]),
                   dark(s, 0.3), 0.45 if side > 0 else 0.25, clip=head, blur=1.8)
    # jaw shadow onto neck and the chin
    P.fill(P.ell(53, F.chin - 2, F.cw + 2, 2.2), dark(s, 0.25), 0.35, clip=head, blur=1.2)
    if F.age > 0.55:                               # age lines
        a = min(1.0, (F.age - 0.5) * 2)
        P.fill(P.stroke([(42, 35), (50, 34.5), (58, 35)], 0.5), dark(s, 0.4), 0.5 * a, clip=head)
        P.fill(P.stroke([(44, 38), (56, 38)], 0.4), dark(s, 0.4), 0.4 * a, clip=head)
        for side in (-1, 1):
            P.fill(P.stroke([(50 + side * 6.5, 64), (50 + side * 8, 70)], 0.6), dark(s, 0.4), 0.6 * a, clip=head)
    if F.hero:                                     # rim light on the shadow side
        rim = ImageChops.subtract(head, P.poly([(x - 1.0, y + 0.3) for x, y in _head_outline(F)]))
        P.fill(rim, light(rgb(F.f.light), 0.3), 0.75)
    return head


def _eye(P: Painter, F: Face, side: int, head: Image.Image) -> None:
    cx, ey = 50 + side * F.ex, F.ey + F.lift * 0.3
    fem = F.o.female
    oh = 2.2 if F.hero else 2.9 if F.plain else 2.6       # opening height
    oh += 0.4 if fem else 0
    ln = 4.6 if not F.goblin else 4.0
    inner, outer = (cx - side * ln, ey + 0.2), (cx + side * ln, ey - (0.5 if fem or F.hero else 0))
    up = (cx, ey - oh)
    low = (cx, ey + oh * 0.6)
    eye = P.poly([inner, up, outer, low])
    socket = P.ell(cx + 0.5, ey - 0.6, 6.2, 4.4)
    P.fill(socket, dark(F.skin, 0.35), 0.45 if not F.hero else 0.6, clip=head, blur=1.6)
    if F.patch and side == 1:
        P.fill(P.ell(cx, ey, 5.2, 4.4), rgb("#1a1418"))
        P.fill(P.stroke([(cx - 5, ey - 4), (cx - 22, ey - 12)], 1.0), rgb("#1a1418"))
        P.fill(P.stroke([(cx + 5, ey - 3), (cx + 14, ey - 6)], 1.0), rgb("#1a1418"))
        return
    white = (236, 230, 220) if not F.goblin else (240, 226, 140)
    if F.f.key == "ashen" and F.o.look == "vampire":
        white = (230, 200, 200)
    P.fill(eye, white)
    gx = cx + F.gaze
    iris = P.ell(gx, ey - 0.3, 2.1 if not F.goblin else 2.5, 2.1 if not F.goblin else 2.5)
    P.fill(iris, F.eye, clip=eye)
    P.fill(P.ell(gx, ey + 0.4, 2.1, 1.2), light(F.eye, 0.35), 0.6, clip=ImageChops.multiply(iris, eye))
    pupil = P.ell(gx, ey - 0.3, 0.95, 0.95) if not F.goblin else P.ell(gx, ey - 0.3, 0.5, 1.8)
    P.fill(pupil, (14, 10, 16), clip=eye)
    P.fill(P.ell(cx, ey - oh, ln, 1.6), (0, 0, 0), 0.35, clip=eye, blur=0.5)      # lid shadow
    P.fill(P.ell(gx - 0.8, ey - 1.1, 0.55, 0.55), (255, 255, 255), clip=eye)        # catchlight
    lid = P.taper([inner, (cx - side * 1.5, ey - oh - 0.2), (cx + side * 2, ey - oh + 0.1), outer],
                  0.6, 1.1 if not fem else 1.4)
    P.fill(lid, dark(F.skin, 0.8))
    if fem:                                    # lashes
        P.fill(P.taper([outer, (outer[0] + side * 1.4, outer[1] - 1.2)], 0.9, 0.2), dark(F.skin, 0.85))
    P.fill(P.stroke([(cx - side * 3, ey + oh * 0.6 + 0.4), (cx + side * 3, ey + oh * 0.55 + 0.3)], 0.35),
           dark(F.skin, 0.5), 0.6)
    if F.plain or F.age > 0.6:                     # tired bags
        P.fill(P.stroke([(cx - side * 3, ey + 3.2), (cx, ey + 3.8), (cx + side * 3.5, ey + 3.0)], 0.4),
               dark(F.skin, 0.4), 0.6)


def _brow(P: Painter, F: Face, side: int) -> None:
    cx, ey = 50, F.ey + F.lift * 0.3
    if F.hero:
        inner, mid, outer = (cx + side * 2.8, ey - 3.8), (cx + side * 8, ey - 5.4), (cx + side * 13, ey - 5.6)
    elif F.plain:
        inner, mid, outer = (cx + side * 3.2, ey - 5.6), (cx + side * 8, ey - 6.2), (cx + side * 12.5, ey - 4.6)
    else:
        inner, mid, outer = (cx + side * 3, ey - 4.6), (cx + side * 8, ey - 6.2), (cx + side * 12.8, ey - 5.2)
    thick = (1.4 if F.o.female else 2.2) * (1.15 if F.hero else 1.0)
    col = dark(F.hair, 0.25) if not F.goblin else dark(F.skin, 0.6)
    if F.age > 0.8:
        col = mix(col, (200, 200, 205), 0.5)
    P.fill(P.taper([inner, mid, outer], thick, thick * 0.35), col)


def _features(P: Painter, F: Face, head: Image.Image) -> None:
    for side in (-1, 1):
        _eye(P, F, side, head)
        _brow(P, F, side)
    s = F.skin
    n = F.nose
    ny = 62 + F.lift * 0.2
    # nose: shadow side, bridge light, nostrils
    P.fill(P.poly([(51, F.ey + 1), (51 + 2.2 * n, ny - 2), (50 + 3.2 * n, ny + 0.8), (51, ny + 1)]),
           dark(s, 0.35), 0.75, blur=0.8)
    P.fill(P.stroke([(48.6, F.ey + 2), (48.4, ny - 2.5)], 0.9), light(s, 0.35), 0.7)
    P.fill(P.ell(49.3, ny - 0.8, 1.6 * n, 1.4 * n), light(s, 0.3), 0.6)
    P.fill(P.stroke([(50 - 3.4 * n, ny + 0.2), (50 - 1.6 * n, ny + 1.4), (50, ny + 1.6), (50 + 1.6 * n, ny + 1.4),
                     (50 + 3.4 * n, ny + 0.2)], 0.6), dark(s, 0.55), 0.85)
    for side in (-1, 1):
        P.fill(P.ell(50 + side * 1.9 * n, ny + 0.9, 0.9, 0.5), dark(s, 0.7), 0.9)
    # mouth
    my = 71 + F.lift * 0.15 + (2 if F.troll else 0)
    mw = F.mw * (1.5 if F.goblin else 1)
    if F.hero:
        corners = ((50 - mw, my + 0.2), (50 + mw, my - 0.9))          # confident half-smile
    elif F.plain:
        corners = ((50 - mw, my + 0.9), (50 + mw, my + 1.0))          # slack, a little down
    else:
        corners = ((50 - mw, my), (50 + mw, my - 0.2))
    lip = rgb("#b8584e") if F.o.female else dark(s, 0.25)
    if F.o.female:
        upper = P.poly([corners[0], (47, my - 1.6), (50, my - 1.0), (53, my - 1.6), corners[1], (50, my + 0.2)])
        lower = P.poly([corners[0], (50, my + 0.1), corners[1], (50, my + 2.6)])
        P.fill(upper, dark(lip, 0.15))
        P.fill(lower, lip)
        P.fill(P.ell(49, my + 1.4, 2.2, 0.6), light(lip, 0.5), 0.6)
    else:
        P.fill(P.ell(50, my + 2.6, mw * 0.55, 1.2), dark(s, 0.3), 0.45, blur=0.6)      # under-lip shadow
        P.fill(P.ell(50, my + 1.6, mw * 0.5, 0.7), light(s, 0.25), 0.4)
    P.fill(P.taper([corners[0], (50, my + 0.2 if not F.hero else my - 0.1), corners[1]], 0.8, 0.8),
           dark(lip, 0.65))
    if F.goblin:                                   # fangs (troll: tusks)
        for side in (-1, 1):
            x = 50 + side * (mw - 1.8)
            t = 4.5 if F.troll else 2.2
            P.fill(P.poly([(x - 1, my - 0.2 + (0 if F.troll else 0)), (x + 1, my - 0.2), (x + side * 0.4, my - t if F.troll else my + t)],
                          smooth=False), rgb("#f2ead0"))
    if F.scar:
        P.fill(P.stroke([(55, 40), (57, 47), (60, 55)], 0.8), rgb("#c0786a"), 0.9, clip=head)
        P.fill(P.stroke([(55.4, 40.4), (57.4, 47), (60.3, 54.6)], 0.3), light(F.skin, 0.4), 0.8, clip=head)
    if F.paint:                                    # war paint stripes across the eyes or cheeks
        col = rgb("#b0303a") if F.f.key == "khanate" else rgb("#3a6ad0") if F.f.key == "north" else rgb("#2a6a3a")
        for side in (-1, 1):
            P.fill(P.taper([(50 + side * 5, 58), (50 + side * 15, 56)], 1.8, 0.6), col, 0.8, clip=head)
    if F.f.key == "ashen":                         # deathly pallor: dark rings around the eyes
        for side in (-1, 1):
            P.fill(P.ell(50 + side * F.ex, F.ey + 1.4, 5.5, 3.6), rgb("#5a3a6a"), 0.25, clip=head, blur=1.4)


def _facial_hair(P: Painter, F: Face, head: Image.Image) -> None:
    b = F.beard
    if b == "none":
        return
    col = F.hair
    cx, ch = 50, F.chin
    my = 71
    if b == "stubble":
        m = ImageChops.multiply(head, P.poly([(cx - F.hw + 1, 60), (cx - F.jw, 72), (cx, ch + 1), (cx + F.jw, 72),
                                              (cx + F.hw - 1, 60), (cx + 8, 66), (cx - 8, 66)]))
        P.fill(m, dark(col, 0.1), 0.3, blur=0.6)
        return
    long = {"short": 3, "full": 8, "long": 18, "braided": 20, "goatee": 4, "mustache": 0}[b]
    if b in ("short", "full", "long", "braided"):
        pts = [(cx - F.hw + 0.5, 55), (cx - F.jw - 1.5, 70), (cx - F.cw - 4, ch + long * 0.6),
               (cx, ch + long), (cx + F.cw + 4, ch + long * 0.6), (cx + F.jw + 1.5, 70), (cx + F.hw - 0.5, 55),
               (cx + F.hw - 3, 64), (cx + 6, 67), (cx + F.mw + 1, my + 1.6), (cx, my + 3.2),
               (cx - F.mw - 1, my + 1.6), (cx - 6, 67), (cx - F.hw + 3, 64)]
        beard = P.poly(pts)
        P.fill(beard, col)
        P.fill(ImageChops.subtract(beard, P.poly([(x - 3, y - 2) for x, y in pts])), dark(col, 0.4), 0.8, blur=1)
        for i in range(36 if not F.plain else 14):               # strands
            x = F.r.uniform(cx - F.jw, cx + F.jw)
            y = F.r.uniform(66, ch + long * 0.7)
            ln = F.r.uniform(3, 6)
            bend = (x - cx) * 0.12
            P.fill(P.taper([(x, y), (x + bend, y + ln * 0.6), (x + bend * 1.5, y + ln)], 0.7, 0.15),
                   light(col, 0.35) if i % 3 == 0 else dark(col, 0.35), 0.8, clip=beard)
        if b == "braided":
            for side in (-1, 1):
                x0 = cx + side * 4
                for k in range(5):
                    y = ch + long * 0.4 + k * 3.2
                    P.fill(P.ell(x0, y, 2.4, 1.9), col)
                    P.fill(P.ell(x0 - 0.6, y - 0.6, 1.2, 0.8), light(col, 0.35), 0.8)
                P.fill(P.ell(x0, ch + long * 0.4 + 16.5, 2.2, 1.4), rgb("#f2c84b"))
    if b == "goatee":
        g = P.poly([(cx - F.mw + 0.5, my + 2), (cx, my + 2.8), (cx + F.mw - 0.5, my + 2), (cx + 3.5, ch + 3),
                    (cx, ch + 5), (cx - 3.5, ch + 3)])
        P.fill(g, col)
        P.fill(g, dark(col, 0.4), 0.5, clip=P.ell(cx + 4, ch + 2, 4, 6), blur=0.8)
    # mustache for everything but the short beard and goatee-only
    if b in ("full", "long", "braided", "mustache", "goatee", "short"):
        droop = 7 if b == "mustache" else 1.5
        for side in (-1, 1):
            m = P.taper([(cx + side * 0.6, my - 2.4), (cx + side * (F.mw * 0.7), my - 1.6),
                         (cx + side * (F.mw + 1.4), my + droop * 0.5), (cx + side * (F.mw + 1.6), my + droop)],
                        2.4, 0.6)
            P.fill(m, col)
            P.fill(P.taper([(cx + side * 1, my - 2.6), (cx + side * (F.mw * 0.7), my - 2.2)], 0.6, 0.3),
                   light(col, 0.35), 0.8)


def _hair_cap(F: Face) -> List[Pt]:
    """Hair mass on top of the head: crown to temples, hairline across the forehead."""
    cx, hw, top = 50, F.hw, F.top
    hl = 34 + F.r.uniform(-1, 1.5) + (2.5 if F.age > 0.75 and not F.o.female else 0)
    return [(cx - hw - 1.2, 50), (cx - hw - 1.6, 36), (cx - hw * 0.75, top - 2.5), (cx, top - 4),
            (cx + hw * 0.75, top - 2.5), (cx + hw + 1.6, 36), (cx + hw + 1.2, 50), (cx + hw - 1.6, 47),
            (cx + hw - 3, 39), (cx + 6, hl - 0.5), (cx, hl + 0.8), (cx - 7, hl - 1.5), (cx - hw + 3, 40),
            (cx - hw + 1.6, 47)]


def _strands(P: Painter, F: Face, mask: Image.Image, area: Tuple[float, float, float, float], n: int,
             down: bool = False) -> None:
    x0, y0, x1, y1 = area
    col = F.hair
    for i in range(n):
        x = F.r.uniform(x0, x1)
        y = F.r.uniform(y0, y1)
        if down:
            pts = [(x, y), (x + F.r.uniform(-1, 1), y + 6), (x + F.r.uniform(-2, 2), y + 12)]
        else:
            dx = (x - 50) * 0.25
            pts = [(x, y), (x + dx, y + 4), (x + dx * 1.6, y + 8)]
        c = light(col, 0.35) if i % 3 == 0 else dark(col, 0.3)
        P.fill(P.taper(pts, 0.9, 0.2), c, 0.8, clip=mask)


def _back_hair(P: Painter, F: Face) -> None:
    st = F.style
    if F.hat in ("hood", "cowl"):                   # the hood's back drapes behind the head
        col = dark(rgb(F.f.color), 0.35) if F.f.key != "ashen" else rgb("#2a1c34")
        if F.plain:
            col = grey(col, 0.4)
        hood = P.poly([(50 - F.hw - 9, 92), (50 - F.hw - 8, 40), (50, F.top - 10), (50 + F.hw + 8, 40),
                       (50 + F.hw + 9, 92)])
        P.fill(hood, col)
        P.fill(P.ell(58, 50, 16, 30), dark(col, 0.4), 0.6, clip=hood, blur=4)
        return
    if st in ("long", "braids") and F.hat not in ("helm", "crownhelm"):
        ln = 98 if st == "long" else 90
        pts = [(50 - F.hw - 3, 44), (50 - F.hw - 5, 70), (50 - F.hw - 6, ln), (50 - F.hw + 2, ln + 2),
               (50 + F.hw - 2, ln + 2), (50 + F.hw + 6, ln), (50 + F.hw + 5, 70), (50 + F.hw + 3, 44),
               (50, 26)]
        hair = P.poly(pts)
        P.fill(hair, dark(F.hair, 0.15))
        P.fill(P.ell(60, 70, 14, 30), dark(F.hair, 0.45), 0.6, clip=hair, blur=3)
        _strands(P, F, hair, (30, 50, 70, 90), 24, down=True)
    if st == "queue":
        q = P.taper([(56, 30), (66, 40), (70, 60), (68, 90)], 4, 2.6)
        P.fill(q, F.hair)
    if st == "tied" and not F.o.female:
        P.fill(P.ell(50 + F.hw - 2, 34, 4, 4), F.hair)


def _front_hair(P: Painter, F: Face, head: Image.Image) -> None:
    st = F.style
    hidden = F.hat in ("helm", "crownhelm", "turban", "crownturban", "hood", "cowl", "furhat", "nasal", "pot", "rag")
    col = F.hair
    if st in ("bald", "none", "shaved") or hidden and st not in ("long", "braids"):
        if st in ("bald", "shaved") and not hidden:
            P.fill(P.ell(44, 28, 7, 4), light(F.skin, 0.6), 0.5, blur=1.5)        # scalp shine
        if st == "shaved" and not hidden:
            P.fill(P.poly(_hair_cap(F)), dark(col, 0.1), 0.25, clip=head)
        if st == "tuft" or (F.goblin and st == "tuft"):
            pass
        if F.goblin and st == "tuft":
            for i in range(5):
                P.fill(P.taper([(46 + i * 2, F.top + 1), (44 + i * 3, F.top - 6)], 1.4, 0.2), rgb("#2a2a1a"))
        if hidden and st in ("long", "braids"):
            pass
        return
    if hidden:
        # only the locks that fall out from under the hat
        for side in (-1, 1):
            lock = P.poly([(50 + side * (F.hw - 1), 42), (50 + side * (F.hw + 3), 46), (50 + side * (F.hw + 4), 80),
                           (50 + side * (F.hw - 0.5), 78)])
            P.fill(lock, col)
            _strands(P, F, lock, (50 + side * F.hw - 2, 44, 50 + side * F.hw + 2, 74), 6, down=True)
        return
    if F.goblin:
        return
    cap = P.poly(_hair_cap(F))
    P.fill(cap, col)
    P.fill(ImageChops.subtract(cap, P.poly([(x - 3, y - 2.5) for x, y in _hair_cap(F)])), dark(col, 0.45), 0.8,
           blur=1)
    P.fill(P.ell(42, F.top + 3, 8, 3.2), light(col, 0.45), 0.55 if not F.plain else 0.3, clip=cap, blur=1.2)
    _strands(P, F, cap, (34, F.top - 2, 66, 36), 26 if not F.plain else 10)
    if st in ("long", "braids"):
        for side in (-1, 1):
            lock = P.poly([(50 + side * (F.hw - 2), 38), (50 + side * (F.hw + 3), 44), (50 + side * (F.hw + 5), 86),
                           (50 + side * (F.hw - 0.5), 84), (50 + side * (F.hw - 2.5), 56)])
            P.fill(lock, col)
            P.fill(lock, dark(col, 0.35), 0.6 if side > 0 else 0.2)
            _strands(P, F, lock, (50 + side * F.hw - 2, 44, 50 + side * F.hw + 3, 78), 10, down=True)
        if st == "braids":
            for side in (-1, 1):
                x0 = 50 + side * (F.hw + 2)
                for k in range(6):
                    P.fill(P.ell(x0, 70 + k * 3.4, 2.4, 2.0), col)
                    P.fill(P.ell(x0 - 0.7, 69.4 + k * 3.4, 1.1, 0.8), light(col, 0.35), 0.8)
                P.fill(P.ell(x0, 91, 1.8, 1.4), rgb("#c0c6d8"))
    if st == "up":                                 # a high bun held by a golden pin
        P.fill(P.ell(50, F.top - 5, 8, 6), col)
        P.fill(P.ell(47, F.top - 7, 4, 2), light(col, 0.4), 0.6)
        P.fill(P.stroke([(38, F.top - 9), (62, F.top - 2)], 1.0), rgb("#f2c84b"))
    if st == "tied" and F.o.female:
        P.fill(P.taper([(60, F.top), (68, F.top + 10), (66, 70)], 5, 2), col)


def _headwear(P: Painter, F: Face, head: Image.Image) -> None:
    h = F.hat
    gold, gem = rgb("#f2c84b"), rgb(F.f.color)
    cx, top, hw = 50, F.top, F.hw
    fcol = rgb(F.f.color)
    if F.plain:
        fcol = grey(fcol, 0.45)
    if h == "crown":
        band = P.poly([(cx - hw - 1, 34), (cx + hw + 1, 34), (cx + hw, 28), (cx - hw, 28)], smooth=False)
        pts = [(cx - hw, 29), (cx - hw - 1, 14), (cx - hw * 0.55, 23), (cx - hw * 0.3, 10), (cx, 21),
               (cx + hw * 0.3, 10), (cx + hw * 0.55, 23), (cx + hw + 1, 14), (cx + hw, 29)]
        crown = P.poly(pts, smooth=False)
        P.fill(crown, gold)
        P.fill(band, dark(gold, 0.15))
        P.fill(ImageChops.subtract(crown, P.poly([(x - 2, y - 1) for x, y in pts], smooth=False)), dark(gold, 0.35))
        for x in (cx - hw * 0.5, cx, cx + hw * 0.5):
            P.fill(P.ell(x, 31, 1.7, 1.7), gem)
            P.fill(P.ell(x - 0.5, 30.5, 0.6, 0.6), (255, 255, 255))
        for x, y in ((cx - hw - 1, 14), (cx - hw * 0.3, 10), (cx + hw * 0.3, 10), (cx + hw + 1, 14)):
            P.fill(P.ell(x, y, 1.4, 1.4), light(gold, 0.5))
    elif h in ("circlet",):
        P.fill(P.stroke([(cx - hw, 33), (cx, 36), (cx + hw, 33)], 1.6), rgb("#c0c6d8"))
        P.fill(P.poly([(cx, 33), (cx + 2.5, 37), (cx, 41), (cx - 2.5, 37)], smooth=False), rgb("#8a3ad0"))
        P.fill(P.ell(cx - 0.6, 36, 0.7, 1), (255, 255, 255), 0.8)
    elif h == "antlers":                           # a living crown of antlers and leaves
        for side in (-1, 1):
            base = (cx + side * 10, top + 4)
            P.fill(P.taper([base, (cx + side * 16, top - 6), (cx + side * 22, top - 18)], 3, 1.2), rgb("#c8b088"))
            P.fill(P.taper([(cx + side * 15, top - 4), (cx + side * 24, top - 8)], 2, 0.8), rgb("#c8b088"))
            P.fill(P.taper([(cx + side * 19, top - 12), (cx + side * 16, top - 22)], 1.8, 0.6), rgb("#c8b088"))
        for i in range(7):
            x = cx - hw + i * hw / 3
            leaf = P.poly([(x - 3, top + 6), (x, top + 2 - (i % 2) * 2), (x + 3, top + 6), (x, top + 8)])
            P.fill(leaf, rgb("#3aa06a") if i % 2 else rgb("#6fe0a8"))
    elif h == "leaves":
        for i in range(6):
            x = cx - hw + 3 + i * (2 * hw - 6) / 5
            P.fill(P.poly([(x - 2.5, top + 7), (x, top + 2), (x + 2.5, top + 7), (x, top + 9)]), rgb("#4ab07a"))
    elif h in ("helm", "crownhelm", "nasal"):
        steel = rgb("#a8b0c0") if not F.plain else rgb("#8a8e96")
        pts = [(cx - hw - 2.5, 50), (cx - hw - 3, 34), (cx - hw * 0.7, top - 4), (cx, top - 6.5),
               (cx + hw * 0.7, top - 4), (cx + hw + 3, 34), (cx + hw + 2.5, 50), (cx + hw - 1, 50),
               (cx + hw - 2, 40), (cx, 39), (cx - hw + 2, 40), (cx - hw + 1, 50)]
        helm = P.poly(pts)
        P.fill(helm, steel)
        P.fill(P.ell(cx + 9, 36, 14, 18), dark(steel, 0.45), 0.7, clip=helm, blur=2)
        P.fill(P.ell(cx - 7, top + 2, 6, 7), light(steel, 0.6), 0.8, clip=helm, blur=1.5)
        P.fill(P.stroke([(cx - hw - 2.5, 38), (cx, 41.5), (cx + hw + 2.5, 38)], 2.4), dark(steel, 0.25))
        for x in (cx - hw * 0.7, cx - hw * 0.25, cx + hw * 0.25, cx + hw * 0.7):
            P.fill(P.ell(x, 40.6, 0.8, 0.8), light(steel, 0.5))
        if h == "nasal" or F.f.key == "north":
            nas = P.poly([(cx - 1.6, 40), (cx + 1.6, 40), (cx + 1.2, 59), (cx - 1.2, 59)], smooth=False)
            P.fill(nas, steel)
            P.fill(P.stroke([(cx + 0.9, 41), (cx + 0.7, 58)], 0.6), dark(steel, 0.4))
        if h == "crownhelm":
            band = [(cx - hw - 2, 33), (cx - hw * 0.5, 26), (cx, 21), (cx + hw * 0.5, 26), (cx + hw + 2, 33)]
            P.fill(P.stroke(band, 2.4), gold)
            for side in (-1, 1):                   # dwarven wings of rune-steel
                P.fill(P.poly([(cx + side * (hw + 2), 34), (cx + side * (hw + 12), 20), (cx + side * (hw + 9), 30),
                               (cx + side * (hw + 13), 27), (cx + side * (hw + 4), 40)], smooth=False), gold)
            P.fill(P.ell(cx, 26, 2.2, 2.2), rgb("#f08a2c"))
        elif F.hero:
            P.fill(P.stroke([(cx, top - 6), (cx, 39)], 1.6), gold)
    elif h in ("turban", "crownturban"):
        col = rgb("#f6e7b0") if h == "crownturban" else rgb(F.r.choice(("#efe6d0", "#e8dcc0", "#3a4a8a", "#8a2a2a")))
        if F.plain:
            col = grey(col, 0.4)
        pts = [(cx - hw - 4, 42), (cx - hw - 5, 30), (cx - hw * 0.6, top - 9), (cx, top - 11),
               (cx + hw * 0.6, top - 9), (cx + hw + 5, 30), (cx + hw + 4, 42), (cx, 38)]
        tur = P.poly(pts)
        P.fill(tur, col)
        for k in range(5):                         # wrapped folds
            y = 26 + k * 3.4
            P.fill(P.taper([(cx - hw - 4, y + 6), (cx - 4, y - 1), (cx + hw + 4, y - 7)], 1.3, 0.6),
                   dark(col, 0.3), 0.7, clip=tur)
        P.fill(P.ell(cx + 9, 34, 12, 14), dark(col, 0.35), 0.5, clip=tur, blur=2)
        if h == "crownturban" or F.hero:
            P.fill(P.ell(cx, 34, 3.2, 3.6), gold)
            P.fill(P.ell(cx, 34, 1.9, 2.2), rgb("#d0302a") if h == "crownturban" else rgb("#3a8ad0"))
            plume = P.taper([(cx + 1, 31), (cx + 5, 20), (cx + 12, 12)], 3.4, 0.8)
            P.fill(plume, rgb("#f2ece0"))
    elif h in ("hood", "cowl"):
        col = dark(rgb(F.f.color), 0.2) if F.f.key != "ashen" else rgb("#3a2848")
        if F.plain:
            col = grey(col, 0.4)
        pts = [(cx - hw - 6, 70), (cx - hw - 6, 38), (cx - hw * 0.5, top - 8), (cx, top - 9), (cx + hw * 0.5, top - 8),
               (cx + hw + 6, 38), (cx + hw + 6, 70), (cx + hw - 1, 66), (cx + hw - 1.5, 42), (cx + 4, 33),
               (cx, 32), (cx - 4, 33), (cx - hw + 1.5, 42), (cx - hw + 1, 66)]
        hood = P.poly(pts)
        P.fill(hood, col)
        P.fill(P.ell(cx + 12, 46, 10, 26), dark(col, 0.45), 0.7, clip=hood, blur=2.5)
        P.fill(P.ell(cx - 12, 34, 6, 12), light(col, 0.25), 0.5, clip=hood, blur=2)
        P.fill(P.ell(cx, 36, hw, 7), (0, 0, 0), 0.3, clip=head, blur=2)      # shadow under the hood
        if h == "cowl":
            P.fill(P.stroke([(cx - hw - 4, 40), (cx, 30), (cx + hw + 4, 40)], 1.0), rgb("#c49be8"), 0.8)
    elif h in ("furhat", "spike"):
        fur = rgb("#5a3e26") if not F.hero else rgb("#7a5a3a")
        if h == "spike":
            cap = P.poly([(cx - hw, 33), (cx, top - 16), (cx + hw, 33)], smooth=False)
            P.fill(cap, rgb("#8a8e96"))
            P.fill(P.poly([(cx, top - 16), (cx + hw, 33), (cx + 2, 33)], smooth=False), rgb("#5a5e66"))
            P.fill(P.taper([(cx, top - 15), (cx + 4, top - 26), (cx + 10, top - 30)], 2.4, 0.6), fcol)
        else:
            cap = P.poly([(cx - hw + 2, 30), (cx - hw * 0.4, top - 12), (cx + hw * 0.4, top - 12), (cx + hw - 2, 30)])
            P.fill(cap, fcol)
            P.fill(P.ell(cx + 6, top - 4, 9, 10), dark(fcol, 0.45), 0.6, clip=cap, blur=2)
            if F.hero:
                P.fill(P.stroke([(cx, top - 11), (cx, 31)], 1.2), gold)
                P.fill(P.ell(cx, top - 12, 2, 2), gold)
        rim = P.poly([(cx - hw - 4, 40), (cx - hw - 4, 30), (cx, 27), (cx + hw + 4, 30), (cx + hw + 4, 40), (cx, 37)])
        P.fill(rim, fur)
        for i in range(30):
            x, y = F.r.uniform(cx - hw - 3, cx + hw + 3), F.r.uniform(28, 38)
            P.fill(P.taper([(x, y), (x + F.r.uniform(-1.5, 1.5), y + 3)], 1.2, 0.2),
                   light(fur, 0.35) if i % 2 else dark(fur, 0.4), clip=rim)
    elif h == "beret":
        col = rgb("#7a1f2b") if not F.plain else rgb("#5a4a4a")
        ber = P.poly([(cx - hw - 4, 32), (cx - hw, top - 7), (cx + 6, top - 10), (cx + hw + 7, top - 3),
                      (cx + hw + 2, 30), (cx, 34)])
        P.fill(ber, col)
        P.fill(P.ell(cx + 8, top, 12, 6), dark(col, 0.4), 0.6, clip=ber, blur=1.5)
        if not F.plain:
            plume = P.taper([(cx + hw, top - 4), (cx + hw + 8, top - 12), (cx + hw + 16, top - 14)], 3.6, 0.6)
            P.fill(plume, rgb("#f2ece0"))
            P.fill(P.taper([(cx + hw + 1, top - 5), (cx + hw + 9, top - 11)], 0.6, 0.3), rgb("#c0b8a8"))
            P.fill(P.ell(cx + hw - 1, top - 3, 1.8, 1.8), gold)
    elif h == "pot":                               # goblin: an upturned cooking pot
        pot = P.poly([(cx - hw - 2, 34), (cx - hw + 1, top - 6), (cx + hw - 1, top - 6), (cx + hw + 2, 34)],
                     smooth=False)
        P.fill(pot, rgb("#5a5e66"))
        P.fill(P.ell(cx + 8, top, 8, 12), rgb("#3a3e44"), 0.7, clip=pot, blur=1.5)
        P.fill(P.stroke([(cx - hw - 3, 34), (cx + hw + 3, 34)], 2), rgb("#3a3e44"))
        P.fill(P.ell(cx - 6, top + 3, 2.4, 1.6), rgb("#a05a2a"), 0.7)
    elif h == "rag":
        rag = P.poly([(cx - hw - 1, 38), (cx - hw * 0.5, top - 5), (cx + hw * 0.5, top - 5), (cx + hw + 1, 38),
                      (cx, 33)])
        P.fill(rag, rgb("#8a3a2a"))
        P.fill(P.taper([(cx + hw, 34), (cx + hw + 8, 42), (cx + hw + 6, 50)], 3, 1), rgb("#8a3a2a"))
        for i in range(3):
            P.fill(P.ell(cx - 8 + i * 7, top + 2 + i, 1.4, 1.4), rgb("#e8d8a0"), 0.8)


def _finish(P: Painter, F: Face) -> None:
    """Vignette (heavier for nobodies) and a thin inner frame line."""
    vig = ImageChops.invert(P.ell(50, 56, 62, 72))
    P.fill(vig, (6, 4, 10), 0.55 if F.plain else 0.35, blur=10)


# --- cache ------------------------------------------------------------------------------------
_CACHE: Dict[Tuple[str, int, int], Image.Image] = {}


def face(key: str, w: int, h: int) -> Image.Image:
    k = (key, w, h)
    img = _CACHE.get(k)
    if img is None:
        img = _CACHE[k] = paint_face(key, w, h)
    return img


# --- the stat web -----------------------------------------------------------------------------
def web_points(cx: float, cy: float, r: float, values: Sequence[float], top: float = 20) -> List[Pt]:
    n = len(values)
    return [(cx + r * v / top * math.cos(-math.pi / 2 + i * math.tau / n),
             cy + r * v / top * math.sin(-math.pi / 2 + i * math.tau / n)) for i, v in enumerate(values)]


def paint_web(stats: Sequence[int], color: str, edge: str, w: int, h: int) -> Image.Image:
    """Spider chart of six 1..20 stats on a transparent background (RGBA, w x h)."""
    ss = 4
    W_, H_ = w * ss, h * ss
    img = Image.new("RGBA", (W_, H_), (0, 0, 0, 0))
    d = ImageDraw.Draw(img, "RGBA")
    cx, cy, r = W_ / 2, H_ / 2, min(W_, H_) / 2 - 2 * ss
    lw = max(1, ss * w // 120)
    d.polygon(web_points(cx, cy, r, [20] * len(stats)), fill=(24, 20, 37, 220))
    for ring in (5, 10, 15, 20):
        pts = web_points(cx, cy, r, [ring] * len(stats))
        d.line(pts + pts[:1], fill=(139, 155, 180, 110 if ring < 20 else 220), width=lw)
    for x, y in web_points(cx, cy, r, [20] * len(stats)):
        d.line([(cx, cy), (x, y)], fill=(139, 155, 180, 90), width=lw)
    pts = web_points(cx, cy, r, [max(1, v) for v in stats])
    c, e = rgb(color), rgb(edge)
    d.polygon(pts, fill=c + (150,))
    d.line(pts + pts[:1], fill=e + (255,), width=lw * 2, joint="curve")
    for x, y in pts:
        rr = lw * 2.4
        d.ellipse([x - rr, y - rr, x + rr, y + rr], fill=(255, 255, 255, 255), outline=e + (255,), width=lw)
    return img.resize((w, h), Image.LANCZOS)
