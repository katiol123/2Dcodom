"""Procedural pixel-art world map (numpy only - no pygame, so tests can build it).

The map is generated, not painted by hand, but its *design* is data:
coastlines, the lake and rivers follow control points below, every region's
ground is the culture of the nearest city (so faction lands look different),
and roads/cities come from :mod:`game.factions`.

Look: flat ground in a few close tones, relief as quantised light/shadow
bands (light from the top-left), hand-shaped sprites for trees, mountains,
reeds, graves... with a dark outline, y-sorted so nearer things overlap
farther ones.  No gradients, no anti-aliasing - every pixel is one of a
small palette, so the map stays crisp when scaled up.
"""

from __future__ import annotations

import hashlib
import math
import random
from dataclasses import dataclass
from typing import Dict, List, Sequence, Tuple

import numpy as np

from .factions import CITIES, CITY, FACTION, FROST_CITIES, MAP_H, MAP_W, ROADS

MAP_VERSION = "1"


def _hex(c: str) -> Tuple[int, int, int]:
    c = c.lstrip("#")
    return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)


# --- noise ------------------------------------------------------------------------------------
def _value_noise(h: int, w: int, cell: float, rng: np.random.Generator) -> np.ndarray:
    gh, gw = int(h / cell) + 3, int(w / cell) + 3
    g = rng.random((gh, gw))
    ys, xs = np.arange(h) / cell, np.arange(w) / cell
    y0, x0 = ys.astype(int), xs.astype(int)
    fy, fx = ys - y0, xs - x0
    fy, fx = fy * fy * (3 - 2 * fy), fx * fx * (3 - 2 * fx)
    a, b = g[y0][:, x0], g[y0][:, x0 + 1]
    c, d = g[y0 + 1][:, x0], g[y0 + 1][:, x0 + 1]
    top = a + (b - a) * fx[None, :]
    bot = c + (d - c) * fx[None, :]
    return top + (bot - top) * fy[:, None]


def fbm(h: int, w: int, cell: float, octaves: int, rng: np.random.Generator) -> np.ndarray:
    out = np.zeros((h, w))
    amp, total = 1.0, 0.0
    for _ in range(octaves):
        out += _value_noise(h, w, max(1.0, cell), rng) * amp
        total += amp
        amp *= 0.5
        cell /= 2
    return out / total


# --- palettes ---------------------------------------------------------------------------------
# ground ramps per land culture: shadow, base, base2 (blotches), light
GROUND = {
    "tundra": ("#b4c4da", "#d5e0ec", "#c8d5e5", "#f0f5fa"),
    "mountain": ("#6d5f55", "#8a7b6a", "#80705f", "#a39280"),
    "plains": ("#4f8a3c", "#64a347", "#5d9a42", "#7ab855"),
    "forest": ("#2c5c2f", "#3a723a", "#356a35", "#4a8644"),
    "blight": ("#4f4857", "#68616e", "#5f5866", "#7d7682"),
    "coast": ("#79a24a", "#90b95a", "#88b053", "#a6c96b"),
    "steppe": ("#8c8a48", "#a9a659", "#a09c50", "#c0bc6c"),
    "desert": ("#c99a56", "#e2bd78", "#dab26c", "#f2d896"),
    "swamp": ("#3f4d2a", "#556538", "#4d5c33", "#677a45"),
}
SHORE = {"tundra": "#e6edf5", "mountain": "#b9a888", "plains": "#e0cf98", "forest": "#cfc08c", "blight": "#8d8494",
         "coast": "#ecdca4", "steppe": "#e2c88a", "desert": "#f6e3b0", "swamp": "#6f6a3c"}
WATER = ("#7cc3e8", "#4f8fc8", "#3b74b0", "#2e5f97", "#29548a")    # shallow -> deep
RIVER, RIVER_EDGE = "#4f8fc8", "#2e5f97"
ROAD, ROAD_EDGE = "#e8d3a0", "#6b4a2e"
PLANK, PLANK_DARK = "#a0703f", "#5e3c22"
FRAME = ("#181425", "#c9a24a", "#5e3c22")

# --- geography (control points) ----------------------------------------------------------------
WEST_COAST = [(0, 46), (180, 60), (330, 40), (480, 58), (640, 34), (760, 64), (900, 44), (1100, 56)]   # (y, x)
SOUTH_COAST = [(0, 1062), (260, 1060), (340, 1046), (470, 1024), (560, 1018), (660, 1016), (760, 984),
               (840, 990), (920, 1034), (1040, 1024), (1120, 1060), (1300, 1072), (1460, 1080), (1600, 1085)]  # (x, y)
NORTH_COAST = [(0, 24), (220, 30), (300, 52), (380, 30), (620, 22), (800, 36), (1000, 18), (1600, 8)]  # (x, y)
LAKE = (842, 540, 74, 40)            # cx, cy, rx, ry - Зеркальное озеро
RIVERS = [
    [(905, 52), (860, 140), (790, 215), (748, 292), (772, 360), (812, 420), (832, 504)],
    [(852, 576), (836, 650), (862, 722), (822, 800), (796, 868), (752, 930), (742, 1000)],
    [(1262, 262), (1226, 380), (1188, 470), (1150, 566), (1120, 642), (1132, 742), (1152, 830),
     (1136, 906), (1116, 970), (1104, 1060)],
    [(424, 248), (378, 336), (330, 420), (302, 520), (334, 598), (342, 650), (296, 724), (196, 760),
     (110, 744), (30, 752)],
    [(486, 690), (452, 790), (468, 880), (466, 960), (468, 1040)],
    [(1566, 516), (1492, 620), (1462, 720), (1446, 830), (1440, 930), (1416, 1000), (1404, 1095)],
]
LANDMARKS = [
    ("ЗЕРКАЛЬНОЕ ОЗЕРО", 842, 540), ("ВЕЧНЫЙ ЛЕС", 250, 540), ("ПЕПЕЛЬНЫЕ ПУСТОШИ", 330, 850),
    ("СНЕЖНЫЕ ФЬОРДЫ", 420, 170), ("ЖЕЛЕЗНЫЕ ГОРЫ", 1320, 300), ("ВЕЛИКАЯ СТЕПЬ", 1330, 540),
    ("ПЕСКИ ЗАРХАДА", 1450, 905), ("ЛАЗУРНОЕ МОРЕ", 820, 1075), ("ДОЛИНЫ АЛЬДЕРНА", 700, 520),
    ("ЗАКАТНЫЙ ОКЕАН", 24, 470),
]


# --- sprites ------------------------------------------------------------------------------------
Sprite = np.ndarray     # (h, w, 4) uint8, alpha 0/255


def _ascii(rows: Sequence[str], pal: Dict[str, str]) -> Sprite:
    h, w = len(rows), max(len(r) for r in rows)
    out = np.zeros((h, w, 4), np.uint8)
    for y, row in enumerate(rows):
        for x, ch in enumerate(row):
            if ch in pal:
                out[y, x, :3] = _hex(pal[ch])
                out[y, x, 3] = 255
    return out


TREE = ("..ooo..", ".oLLMo.", "oLLMMDo", "oLMMMDo", "oMMMDDo", ".oDDDo.", "..oto..")
TREE_S = (".ooo.", "oLMMo", "oMMDo", ".oDo.", "..t..")
TREE_BIG = ("...ooo...", ".ooLLMoo.", "oLLLMMMDo", "oLLMMMMDo", "oLMMMMDDo", "oMMMMDDDo", ".oMMDDDo.",
            "..oDDDo..", "...oto...", "...oto...")
PINE = ("...o...", "..oLo..", "..oMo..", ".oLMDo.", ".oMMDo.", "oLMMDDo", "ooooooo", "...t...")
CYPRESS = (".o.", "oLo", "oMo", "oMD", "oMD", "oMD", "oDo", ".t.")
DEAD_TREE = ("o...o", "o.o.o", ".ooo.", "..o..", "..o..", ".ooo.")
REEDS = ("L.L.L", "L.LML", "MLM.M", "MMMMM")
TUFT = (".L.L.", "LML.L", "MMMMM")
ROCK = (".ooo.", "oLLMo", "oLMDo", "ooooo")
GRAVE = (".o.", "oLo", "oMo", "oMo", "ooo")
BONES = ("L...L", ".L.L.", "..L..", ".L.L.")
MUSHROOM = (".rrr.", "rwrrr", "..t..")
FLOWERS = ("y.p", ".y.", "p.y")
WAVE = (".ww.", "w..w")
POOL = (".ooooo.", "oDDMDDo", "oDMMMDo", ".ooooo.")
MESA = ("..ooooo..", ".oLLLMMo.", "oLLLMMMDo", "oLLMMMDDo", "oLMMMDDDo", "ooooooooo")
PALM = ("oo.oo", "LMoML", "..o..", "..t..", "..t..", ".t...", ".t...")
DUNE = ("...LLL...", ".LLLMMMD.", "LLMMMMDDD")
JUNK = ("..o.o..", ".oLMo..", "oLMDMoo", "oMDoLMo", "ooooooo")
WINDMILL = ("o...o", ".o.o.", "..o..", ".o.o.", "oLLMo", "oLLMo", "oLMMo", "ooooo")

PAL = {
    "elf": dict(o="#163a22", L="#5cae5a", M="#3d8a44", D="#2a6234", t="#5a3a26"),
    "aldern": dict(o="#1f3f22", L="#82c45e", M="#5ca246", D="#3e7a37", t="#5a3a26"),
    "league": dict(o="#2f3f24", L="#b2cc72", M="#86a453", D="#5f7a42", t="#5a3a26"),
    "snow": dict(o="#13281f", L="#f4f8fc", M="#2f6a4f", D="#1f4a3a", t="#4a3426"),
    "pine": dict(o="#10281c", L="#4f9a5c", M="#2f7046", D="#1f5236", t="#4a3426"),
    "dead": dict(o="#3a2e38"),
    "deadswamp": dict(o="#2c2a1c"),
    "reeds": dict(L="#a3b55a", M="#6f8040"),
    "tuft_orc": dict(L="#e2c482", M="#9c7a46"),
    "tuft_aldern": dict(L="#8fca63", M="#4f8a3c"),
    "rock": dict(o="#3b302c", L="#b3a597", M="#8a7c70", D="#655a52"),
    "snowrock": dict(o="#4a5a70", L="#f4f8fc", M="#c8d5e5", D="#9fb2ca"),
    "grave": dict(o="#2a2430", L="#a59fb0", M="#7a7484"),
    "bones": dict(L="#e6dcc8"),
    "mushroom": dict(r="#d0423f", w="#f4f0e0", t="#e6dcc8"),
    "flowers": dict(y="#fee761", p="#f6a0c8"),
    "wave": dict(w="#5f9fd8"),
    "pool": dict(o="#2a3220", D="#2f4a3f", M="#3f6252"),
    "mesa": dict(o="#4a2a20", L="#d98a5a", M="#b0603e", D="#80402c"),
    "windmill": dict(o="#3a2a24", L="#e6dcc8", M="#b8a890"),
    "palm": dict(o="#1f4a2a", L="#7cc35a", M="#3f8a44", t="#8a5a32"),
    "dune": dict(L="#f6e0a0", M="#e2bd78", D="#c49450"),
    "junk": dict(o="#2a2420", L="#b0a090", M="#7a5a40", D="#5a4a40"),
}


def _mountain(rng: random.Random, w: int, h: int, snow: bool, dark: bool = False) -> Sprite:
    """Peak with a lit left face, shadowed right face, optional snow cap and an outline."""
    lit, base, shade = ("#b7a38a", "#8f7c66", "#5f5048") if not dark else ("#8a8a92", "#686874", "#474552")
    snow_l, snow_s = "#f4f8fc", "#b9c9dd"
    out = np.zeros((h + 1, w + 2, 4), np.uint8)
    peak = w // 2 + rng.randint(-w // 6, w // 6)
    tops = []
    for x in range(w):
        side = peak if x <= peak else max(1, w - 1 - peak)
        d = abs(x - peak) / side
        tops.append(min(h - 1, int(d ** 0.9 * (h - 1) + rng.choice((0, 0, 1)))))
    tops[peak] = 0
    ridge = [peak + int(y * 0.18 * w / h) for y in range(h)]
    snow_line = int(h * rng.uniform(0.25, 0.4)) if snow else -1
    c0 = rng.uniform(0.3, 0.5)
    crease = [peak - int(y * c0 * w / h) + h // 3 for y in range(h)]
    for x in range(w):
        for y in range(tops[x], h):
            right = x > ridge[y] or (x == ridge[y] and y > 0)
            if y < snow_line - (abs(x - peak) % 3 == 1):
                c = snow_s if right else snow_l
            else:
                c = shade if right else (lit if x < ridge[y] - 1 or y < 3 else base)
                if not right and x == crease[y] and y > snow_line + 1:
                    c = base                                   # a second ridge line on the lit face
            out[y, x + 1, :3] = _hex(c)
            out[y, x + 1, 3] = 255
    # outline (sides and top only; the foot melts into the ground)
    filled = out[..., 3] > 0
    edge = np.zeros_like(filled)
    for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
        edge |= np.roll(np.roll(filled, dy, 0), dx, 1)
    edge &= ~filled
    edge[h:, :] = False
    out[edge] = (*_hex("#2e2626"), 255)
    return out[:h]


def _hill(rng: random.Random, w: int, h: int, ramp: Sequence[str]) -> Sprite:
    out = np.zeros((h, w, 4), np.uint8)
    for x in range(w):
        t = 1 - ((x - (w - 1) / 2) / ((w - 1) / 2)) ** 2
        top = int(round((1 - math.sqrt(max(0.0, t))) * (h - 1)))
        for y in range(top, h):
            c = ramp[3] if x < w * 0.45 else (ramp[1] if x < w * 0.7 else ramp[0])
            if y == top:
                c = ramp[0] if x >= w * 0.5 else ramp[3]
            out[y, x, :3] = _hex(c)
            out[y, x, 3] = 255
    return out


def _paste(img: np.ndarray, spr: Sprite, x: int, y: int) -> None:
    """Paste with the sprite's bottom-centre at (x, y)."""
    h, w = spr.shape[:2]
    x0, y0 = x - w // 2, y - h + 1
    sx0, sy0 = max(0, -x0), max(0, -y0)
    x1, y1 = min(img.shape[1], x0 + w), min(img.shape[0], y0 + h)
    if x1 <= x0 + sx0 or y1 <= y0 + sy0:
        return
    region = img[y0 + sy0:y1, x0 + sx0:x1]
    sp = spr[sy0:sy0 + region.shape[0], sx0:sx0 + region.shape[1]]
    m = sp[..., 3] > 0
    region[m] = sp[..., :3][m]


# --- curves -------------------------------------------------------------------------------------
def _meander(pts: Sequence[Tuple[float, float]], rng: random.Random, depth: int = 3, amp: float = 0.18):
    pts = [tuple(map(float, p)) for p in pts]
    for _ in range(depth):
        out = [pts[0]]
        for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
            mx, my = (x0 + x1) / 2, (y0 + y1) / 2
            dx, dy = x1 - x0, y1 - y0
            off = rng.uniform(-amp, amp)
            out += [(mx - dy * off, my + dx * off), (x1, y1)]
        pts = out
    return pts


def road_curve(a: str, b: str, step: float = 0.5) -> List[Tuple[float, float]]:
    """Points along the road between cities a and b (a gentle, deterministic curve)."""
    ca, cb = CITY[a], CITY[b]
    x0, y0, x1, y1 = ca.x, ca.y + 2, cb.x, cb.y + 2
    rng = random.Random(f"{min(a, b)}-{max(a, b)}")
    dx, dy = x1 - x0, y1 - y0
    length = math.hypot(dx, dy)
    off = rng.uniform(-0.14, 0.14)
    cx, cy = (x0 + x1) / 2 - dy * off, (y0 + y1) / 2 + dx * off
    pts = []
    n = max(2, int(length / step))
    for i in range(n + 1):
        t = i / n
        px = (1 - t) ** 2 * x0 + 2 * (1 - t) * t * cx + t * t * x1
        py = (1 - t) ** 2 * y0 + 2 * (1 - t) * t * cy + t * t * y1
        wob = math.sin(t * math.pi * 3 + off * 40) * min(4.0, length / 60) * math.sin(t * math.pi)
        pts.append((px - dy / length * wob, py + dx / length * wob))
    return pts


def _stamp_line(mask: np.ndarray, pts, r: int) -> None:
    h, w = mask.shape
    for x, y in pts:
        xi, yi = int(round(x)), int(round(y))
        mask[max(0, yi - r):min(h, yi + r + 1), max(0, xi - r):min(w, xi + r + 1)] = True


# --- the map --------------------------------------------------------------------------------------
@dataclass
class WorldMap:
    rgb: np.ndarray          # (H, W, 3) uint8
    water: np.ndarray        # sea and lake (bool)
    river: np.ndarray
    road: np.ndarray
    culture: np.ndarray      # index into CULTURES per pixel


CULTURES = list(GROUND)


def map_key() -> str:
    """Changes whenever the map design data changes (used to name the cached PNG)."""
    h = hashlib.sha1(MAP_VERSION.encode())
    h.update(repr((CITIES, ROADS, WEST_COAST, SOUTH_COAST, NORTH_COAST, LAKE, RIVERS, sorted(FROST_CITIES))).encode())
    try:
        with open(__file__, "rb") as f:
            h.update(f.read())
    except OSError:
        pass
    return h.hexdigest()[:12]


def water_mask(seed: int = 7) -> np.ndarray:
    rng = np.random.default_rng(seed)
    H, W = MAP_H, MAP_W
    n1 = (fbm(H, W, 90, 4, rng) - 0.5) * 2
    ys, xs = np.mgrid[0:H, 0:W]
    wy, wx = zip(*WEST_COAST)
    west = np.interp(ys, wy, wx) + n1 * 26
    sx, sy = zip(*SOUTH_COAST)
    south = np.interp(xs, sx, sy) + n1 * 16
    nx, ny = zip(*NORTH_COAST)
    north = np.interp(xs, nx, ny) + n1 * 14
    cx, cy, rx, ry = LAKE
    lake = ((xs - cx) / rx) ** 2 + ((ys - cy) / ry) ** 2 + n1 * 0.35 < 1.0
    return (xs < west) | (ys > south) | (ys < north) | lake


def generate(seed: int = 7) -> WorldMap:
    H, W = MAP_H, MAP_W
    rng = np.random.default_rng(seed)
    prng = random.Random(seed)
    ys, xs = np.mgrid[0:H, 0:W]

    water = water_mask(seed)

    # --- culture regions: nearest city (warped), capitals reach a bit farther
    wx = xs + (fbm(H, W, 120, 3, rng) - 0.5) * 110
    wy = ys + (fbm(H, W, 120, 3, rng) - 0.5) * 110
    best = np.full((H, W), np.inf)
    culture = np.zeros((H, W), np.int8)
    for c in CITIES:
        if c.faction == "goblin":
            continue                     # goblins squat in other lands: a swamp pocket below
        d = (wx - c.x) ** 2 + (wy - c.y) ** 2
        if c.kind == "capital":
            d *= 0.75
        m = d < best
        best[m] = d[m]
        culture[m] = CULTURES.index("tundra" if c.key in FROST_CITIES else FACTION[c.faction].culture)
    blob = fbm(H, W, 18, 3, rng)
    for c in CITIES:
        if c.faction == "goblin" and c.key not in FROST_CITIES:   # a frozen lair stays under the snow
            d = np.sqrt((wx - c.x) ** 2 + ((wy - c.y) * 1.3) ** 2) / 46 + (blob - 0.5) * 1.1
            culture[d < 1.0] = CULTURES.index("swamp")

    # --- ground: quantised relief light + blotches
    elev = fbm(H, W, 70, 4, rng)
    grad = elev - np.roll(np.roll(elev, 3, 0), 3, 1)
    blot = fbm(H, W, 10, 2, rng)
    level = np.where(blot > 0.56, 2, 1)
    level = np.where(grad > 0.035, 3, level)
    level = np.where(grad < -0.035, 0, level)
    rgb = np.zeros((H, W, 3), np.uint8)
    for ci, name in enumerate(CULTURES):
        ramp = np.array([_hex(c) for c in GROUND[name]], np.uint8)
        m = culture == ci
        rgb[m] = ramp[level[m]]

    # --- water: distance bands from the shore
    land = ~water
    dist = np.where(land, 0, 99)
    frontier = land.copy()
    for i in range(1, 14):
        grown = frontier.copy()
        for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            grown |= np.roll(np.roll(frontier, dy, 0), dx, 1)
        new = grown & ~frontier
        dist[new & water] = i
        frontier = grown
    wcol = np.array([_hex(c) for c in WATER], np.uint8)
    band = np.select([dist <= 1, dist <= 4, dist <= 8, dist <= 13], [0, 1, 2, 3], 4)
    deep_blot = (fbm(H, W, 30, 2, rng) > 0.6) & (band == 4)
    band = np.where(deep_blot, 3, band)
    rgb[water] = wcol[band[water]]
    # shore: land next to water (2px) takes the culture's beach colour
    near = np.zeros_like(water)
    grown = water.copy()
    for _ in range(2):
        g2 = grown.copy()
        for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            g2 |= np.roll(np.roll(grown, dy, 0), dx, 1)
        grown = g2
    near = grown & land
    for ci, name in enumerate(CULTURES):
        m = near & (culture == ci)
        rgb[m] = _hex(SHORE[name])

    # --- rivers
    river = np.zeros((H, W), bool)
    river_core = np.zeros((H, W), bool)
    for i, pts in enumerate(RIVERS):
        path = _meander(pts, random.Random(seed * 100 + i))
        dense = []
        for (x0, y0), (x1, y1) in zip(path, path[1:]):
            n = max(1, int(math.hypot(x1 - x0, y1 - y0) * 2))
            dense += [(x0 + (x1 - x0) * t / n, y0 + (y1 - y0) * t / n) for t in range(n)]
        _stamp_line(river, dense, 2)
        _stamp_line(river_core, dense, 1)
    river &= land
    river_core &= land
    rgb[river] = _hex(RIVER_EDGE)
    rgb[river_core] = _hex(RIVER)

    # --- roads (mask first: decorations keep away from them)
    road = np.zeros((H, W), bool)
    road_core = np.zeros((H, W), bool)
    for a, b in ROADS:
        pts = road_curve(a, b)
        _stamp_line(road, pts, 1)
        core = [(x - 0.25, y - 0.25) for x, y in pts]
        for x, y in core:
            xi, yi = int(round(x)), int(round(y))
            if 0 <= yi < H - 1 and 0 <= xi < W - 1:
                road_core[yi:yi + 2, xi:xi + 2] = True
    keep_clear = road.copy()
    for _ in range(3):
        g2 = keep_clear.copy()
        for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            g2 |= np.roll(np.roll(keep_clear, dy, 0), dx, 1)
        keep_clear = g2
    for c in CITIES:
        r = 30 if c.kind == "capital" else 24
        keep_clear[max(0, c.y - 34):c.y + 18, max(0, c.x - r):c.x + r] = True
        keep_clear[c.y:c.y + 20, max(0, c.x - 44):c.x + 44] = True     # name ribbon

    # --- fields around farming towns
    for c in CITIES:
        if c.faction not in ("aldern", "league", "sultanate") or c.kind == "fort":
            continue
        frng = random.Random(c.key)
        crops = [("#d9bf5c", "#c4a848"), ("#94c452", "#7fae44"), ("#a87048", "#8c5a3a"), ("#c9d46a", "#b0bb56")]
        if c.faction == "league":
            crops = [("#6f8a3e", "#a6c46a"), ("#d9bf5c", "#c4a848"), ("#b07a4c", "#946240")]
        if c.faction == "sultanate":
            crops = [("#5f8a3a", "#7aa848"), ("#6f9a40", "#e2bd78")]
        for _ in range(frng.randint(9, 14)):
            ang = frng.uniform(0, math.tau)
            d = frng.uniform(36, 80)
            fx, fy = int(c.x + math.cos(ang) * d), int(c.y + math.sin(ang) * d * 0.8)
            fw, fh = frng.randint(8, 16), frng.randint(5, 9)
            x0, y0 = fx - fw // 2, fy - fh // 2
            if x0 < 4 or y0 < 4 or x0 + fw >= W - 4 or y0 + fh >= H - 4:
                continue
            area = (slice(y0, y0 + fh), slice(x0, x0 + fw))
            if water[area].any() or river[area].any() or road[area].any():
                continue
            a, b = (_hex(v) for v in frng.choice(crops))
            patch = np.zeros((fh, fw, 3), np.uint8)
            patch[:] = a
            patch[1::2] = b                                   # furrows
            patch[-1, :] = _hex("#4a3a2a")
            patch[:, -1] = _hex("#4a3a2a")
            rgb[area] = patch
            keep_clear[area] = True

    # --- decorations (y-sorted)
    decos: List[Tuple[int, int, Sprite]] = []
    forest = fbm(H, W, 60, 3, rng)
    S = {k: _ascii(v, PAL[p]) for k, v, p in (
        ("tree_elf", TREE, "elf"), ("tree_big", TREE_BIG, "elf"), ("tree_s_elf", TREE_S, "elf"),
        ("pine_elf", PINE, "pine"), ("tree_ald", TREE, "aldern"), ("tree_s_ald", TREE_S, "aldern"),
        ("tree_lea", TREE_S, "league"), ("cypress", CYPRESS, "pine"), ("pine_snow", PINE, "snow"),
        ("dead", DEAD_TREE, "dead"), ("dead_sw", DEAD_TREE, "deadswamp"), ("reeds", REEDS, "reeds"),
        ("tuft_orc", TUFT, "tuft_orc"), ("tuft_ald", TUFT, "tuft_aldern"), ("rock", ROCK, "rock"),
        ("snowrock", ROCK, "snowrock"), ("grave", GRAVE, "grave"), ("bones", BONES, "bones"),
        ("mushroom", MUSHROOM, "mushroom"), ("flowers", FLOWERS, "flowers"), ("pool", POOL, "pool"),
        ("mesa", MESA, "mesa"), ("windmill", WINDMILL, "windmill"), ("wave", WAVE, "wave"),
        ("palm", PALM, "palm"), ("dune", DUNE, "dune"), ("junk", JUNK, "junk"))}

    def free(x: int, y: int, r: int = 1) -> bool:
        if not (6 <= x < W - 6 and 8 <= y < H - 6):
            return False
        y0, y1, x0, x1 = y - r, y + 1, x - r, x + r + 1
        return not (water[y0:y1 + 1, x0:x1].any() or river[y0:y1, x0:x1].any() or keep_clear[y, x])

    cell = 6
    for gy in range(0, H, cell):
        for gx in range(0, W, cell):
            x = gx + prng.randrange(cell)
            y = gy + prng.randrange(cell)
            if not (0 <= x < W and 0 <= y < H):
                continue
            cul = CULTURES[culture[y, x]]
            f = forest[y, x]
            r = prng.random()
            spr = None
            if water[y, x]:
                if dist[y, x] > 6 and r < 0.035:
                    spr = S["wave"]
                if spr is not None and not keep_clear[y, x]:
                    decos.append((y, x, spr))
                continue
            if cul == "forest":
                if f > 0.42 and r < 0.8:
                    spr = prng.choice([S["tree_elf"]] * 5 + [S["tree_big"], S["pine_elf"], S["tree_s_elf"]])
                elif r < 0.12:
                    spr = S["tree_s_elf"] if r < 0.09 else S["flowers"]
            elif cul == "plains":
                if f > 0.6 and r < 0.6:
                    spr = prng.choice([S["tree_ald"], S["tree_ald"], S["tree_s_ald"]])
                elif r < 0.025:
                    spr = S["tree_s_ald"]
                elif r < 0.05:
                    spr = S["tuft_ald"]
                elif r < 0.06:
                    spr = S["flowers"]
            elif cul == "coast":
                if f > 0.62 and r < 0.35:
                    spr = prng.choice([S["tree_lea"], S["cypress"]])
                elif r < 0.03:
                    spr = prng.choice([S["tree_lea"], S["cypress"], S["cypress"]])
                elif r < 0.045:
                    spr = S["flowers"]
            elif cul == "tundra":
                if f > 0.5 and r < 0.45:
                    spr = S["pine_snow"]
                elif r < 0.02:
                    spr = S["snowrock"]
                elif r < 0.035:
                    spr = S["pine_snow"]
            elif cul == "blight":
                if r < 0.07 + max(0.0, f - 0.5) * 0.4:
                    spr = S["dead"]
                elif r < 0.1:
                    spr = S["grave"]
                elif r < 0.12:
                    spr = S["bones"]
                elif r < 0.13:
                    spr = S["rock"]
            elif cul == "steppe":
                if r < 0.05:
                    spr = S["tuft_orc"]
                elif r < 0.07:
                    spr = S["rock"]
                elif r < 0.078:
                    spr = S["mesa"]
                elif r < 0.084:
                    spr = S["dead"]
            elif cul == "desert":
                if r < 0.06:
                    spr = S["dune"]
                elif r < 0.075:
                    spr = S["palm"]
                elif r < 0.085:
                    spr = S["rock"]
            elif cul == "swamp":
                if r < 0.03:
                    spr = S["junk"]
                elif r < 0.07:
                    spr = S["pool"]
                elif r < 0.17:
                    spr = S["reeds"]
                elif r < 0.22:
                    spr = S["dead_sw"]
                elif r < 0.25:
                    spr = S["mushroom"]
            elif cul == "mountain":
                continue                                     # mountains below
            if spr is not None and free(x, y, spr.shape[1] // 2):
                decos.append((y, x, spr))

    # mountains: bigger cells, dwarf lands and the hills around them
    for gy in range(0, H, 13):
        for gx in range(0, W, 15):
            x = gx + prng.randrange(15)
            y = gy + prng.randrange(13)
            if not (0 <= x < W and 0 <= y < H) or water[y, x]:
                continue
            cul = CULTURES[culture[y, x]]
            r = prng.random()
            w = h = 0
            if cul == "mountain" and r < 0.72:
                w = prng.randint(14, 40)
                h = int(w * prng.uniform(0.6, 0.85))
            elif cul in ("tundra", "steppe", "blight") and r < 0.05:
                w = prng.randint(12, 20)
                h = int(w * 0.6)
            elif cul in ("plains", "coast") and r < 0.05:
                spr = _hill(prng, prng.randint(10, 16), prng.randint(4, 6), GROUND[cul])
                if free(x, y, spr.shape[1] // 2):
                    decos.append((y, x, spr))
                continue
            if w and free(x, y, w // 2):
                snow = cul in ("mountain", "tundra") and (w > 22 or cul == "tundra")
                decos.append((y, x, _mountain(prng, w, h, snow, dark=cul in ("blight", "tundra"))))
    # windmills near the breadbasket
    for c in CITIES:
        if c.key in ("hartwell", "tremont", "kronholm"):
            mrng = random.Random(c.key + "mill")
            for _ in range(2):
                x, y = c.x + mrng.choice((-1, 1)) * mrng.randint(40, 60), c.y + mrng.randint(-30, 30)
                if free(x, y, 3):
                    decos.append((y, x, S["windmill"]))

    decos.sort(key=lambda d: (d[0], d[1]))
    for y, x, spr in decos:
        _paste(rgb, spr, x, y)

    # --- roads on top, bridges over rivers
    rgb[road] = _hex(ROAD_EDGE)
    rgb[road_core] = _hex(ROAD)
    bridge = road & (river | water)
    rgb[bridge] = _hex(PLANK_DARK)
    rgb[road_core & (river | water)] = _hex(PLANK)

    # --- frame
    for i, c in enumerate(FRAME):
        col = _hex(c)
        rgb[i, :] = rgb[-1 - i, :] = col
        rgb[:, i] = rgb[:, -1 - i] = col
    return WorldMap(rgb, water, river, road, culture)


def roads_cross_sea(seed: int = 7) -> List[Tuple[str, str]]:
    """Roads that run over the sea or the lake for more than a bridge's length."""
    water = water_mask(seed)
    bad = []
    for a, b in ROADS:
        wet = sum(1 for x, y in road_curve(a, b, step=2.0)
                  if 0 <= int(y) < MAP_H and 0 <= int(x) < MAP_W and water[int(y), int(x)])
        if wet > 3:
            bad.append((a, b))
    return bad
