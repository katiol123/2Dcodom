"""World map screen: a big hand-designed, code-drawn map you drag around with the mouse.

* LMB drag (or arrows / WASD) - scroll; click on the minimap - jump there.
* Click a city - its owner, recruit pool and roads.  Click a faction on the
  bottom bar - its lore, leader, proposed mechanics and relations.
* ДИПЛОМАТИЯ - relation matrix of the eight playable factions (goblins: always war).
* БЫСТРЫЙ БОЙ - the squad builder (returns "battle").

Turns, diplomacy actions and attacks come later; this screen already holds
everything they need (cities, owners, roads, pools, relations).
"""

from __future__ import annotations

import math
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import pygame

from pixelforge.text import text_width

from . import worldgen
from .assets import CACHE
from .factions import (ALL_FACTIONS, CITIES, CITY, EMBLEMS, FACTION, FACTIONS, GOBLINS, KIND_NAMES, MAP_H, MAP_W,
                       NEW_UNITS, City, Faction, cities_of, neighbors, relation, relation_status, unit_exists,
                       unit_name, unit_role)
from .render import INK, Renderer, _c
from .sim import H, W
from .units import TEAMS

TOP, BOTTOM = 15, 23                 # UI bars
MINI_K = 16                          # minimap = map / 16
STONE = {"o": "#2a2233", "L": "#e6dfd0", "M": "#b9ae9d", "D": "#867b6f", "w": "#2a2030", "b": "#9a6a3a",
         "B": "#5e3c22", "s": "#f4f0e0", "m": "#7a6a4a", "n": "#54462f", "k": "#e6dcc8", "g": "#c9a24a"}


# --- sprite building --------------------------------------------------------------------------
Grid = List[List[str]]


def _blank(w: int, h: int) -> Grid:
    return [["." for _ in range(w)] for _ in range(h)]


def _paste(dst: Grid, src: Grid, x: int, y: int) -> None:
    for j, row in enumerate(src):
        for i, ch in enumerate(row):
            if ch != "." and 0 <= y + j < len(dst) and 0 <= x + i < len(dst[0]):
                dst[y + j][x + i] = ch


def _rows(rows: Sequence[str]) -> Grid:
    return [list(r) for r in rows]


def _tower(w: int, h: int, windows: Sequence[Tuple[int, int]] = (), door: bool = False, merlons: bool = True) -> Grid:
    g = _blank(w, h)
    for y in range(h):
        for x in range(w):
            f = x / max(1, w - 1)
            g[y][x] = "L" if f < 0.45 else ("M" if f < 0.75 else "D")
            if x in (0, w - 1) or y == h - 1:
                g[y][x] = "o"
    if merlons:
        for x in range(w):
            if x % 3 == 2:
                g[0][x] = "."
                g[1][x] = "o"
            else:
                g[0][x] = "o"
    else:
        g[0] = ["o"] * w
    for wx, wy in windows:
        g[wy][wx] = g[wy + 1][wx] = "w"
    if door:
        cx = w // 2
        for dy in range(1, 4):
            for dx in (-1, 0, 1):
                if not (dy == 3 and dx != 0):
                    g[h - 1 - dy][cx + dx] = "w"
    return g


def _roof(w: int) -> Grid:
    """Cone roof in the faction colour (r lit, R shade)."""
    h = (w + 1) // 2
    g = _blank(w, h)
    for y in range(h):
        half = y
        c = w // 2
        for x in range(c - half, c + half + 1):
            if 0 <= x < w:
                edge = x in (c - half, c + half) or y == 0
                g[y][x] = "o" if edge else ("r" if x <= c else "R")
    return g


HOUSE = ("...o...", "..oro..", ".orrRo.", "orrrRRo", "oLLMMDo", "oLwMwDo", "ooooooo")
BOAT = ("....o....", "...oso...", "..osso...", "..osss...", "....o....", "oBBBBBBBo", ".obbbbbo.", "..ooooo..")
LAIR = (".....ooooo.....", "...ooMmmmmoo...", "..oMmmmmmmnno..", ".oMmmmwwwmnnno.", "oMmmmwwwwwmnnno",
        "ooooowwwwwooooo")
SKULL_POLE = (".kk", ".kw", ".kk", "..b", "..b", "..b", "..b", "..b")


def _palisade(w: int, h: int) -> Grid:
    g = _blank(w, h)
    for y in range(h):
        for x in range(w):
            if y == 0:
                g[y][x] = "o" if x % 2 == 0 else "."
            elif y == 1:
                g[y][x] = "b" if x % 2 == 0 else "o"
            else:
                g[y][x] = "b" if x % 2 == 0 else "B"
            if (x in (0, w - 1) and y > 0) or y == h - 1:
                g[y][x] = "o"
    return g


def city_grid(kind: str) -> Tuple[Grid, int]:
    """Character grid of a city sprite and the x of its flag pole."""
    if kind == "capital":
        g = _blank(29, 25)
        _paste(g, _tower(13, 19, windows=((3, 5), (9, 5), (6, 9)), door=True), 8, 6)
        for x in (1, 21):
            _paste(g, _roof(7), x, 7)
            _paste(g, _tower(7, 13, windows=((3, 3),), merlons=False), x, 11)
        _paste(g, _tower(4, 8, merlons=True), 0, 16)
        _paste(g, _tower(4, 8, merlons=True), 25, 16)
        return g, 14
    if kind == "castle":
        g = _blank(23, 18)
        _paste(g, _tower(5, 8), 0, 10)
        _paste(g, _tower(5, 8), 18, 10)
        _paste(g, _tower(11, 16, windows=((3, 4), (7, 4)), door=True), 6, 2)
        return g, 11
    if kind == "fort":
        g = _blank(21, 14)
        _paste(g, _palisade(7, 7), 0, 7)
        _paste(g, _palisade(7, 7), 14, 7)
        _paste(g, _tower(9, 13, windows=((4, 4),), door=True), 6, 1)
        return g, 10
    if kind == "lair":
        g = _blank(17, 14)
        _paste(g, _rows(LAIR), 1, 8)
        _paste(g, _rows(SKULL_POLE), 13, 4)
        return g, 7
    # town / port: a slim tower with a roof and houses around it
    g = _blank(23 if kind == "port" else 21, 17)
    _paste(g, _roof(7), 7, 0)
    _paste(g, _tower(7, 13, windows=((3, 3), (3, 7)), merlons=False), 7, 4)
    _paste(g, _rows(HOUSE), 0, 10)
    if kind == "port":
        _paste(g, _rows(BOAT), 14, 9)
    else:
        _paste(g, _rows(HOUSE), 14, 10)
    return g, 10


def grid_surface(g: Grid, pal: Dict[str, str]) -> pygame.Surface:
    h, w = len(g), len(g[0])
    s = pygame.Surface((w, h), pygame.SRCALPHA)
    for y, row in enumerate(g):
        for x, ch in enumerate(row):
            if ch in pal:
                s.set_at((x, y), _c(pal[ch]))
    return s


def _outlined(s: pygame.Surface, color=INK) -> pygame.Surface:
    w, h = s.get_size()
    out = pygame.Surface((w + 2, h + 2), pygame.SRCALPHA)
    mask = pygame.mask.from_surface(s)
    sil = mask.to_surface(setcolor=(*color, 255), unsetcolor=(0, 0, 0, 0))
    for dx, dy in ((0, 1), (2, 1), (1, 0), (1, 2)):
        out.blit(sil, (dx, dy))
    out.blit(s, (1, 1))
    return out


def banner_surface(f: Faction, phase: float) -> pygame.Surface:
    """11x13 hanging banner with the faction emblem; ``phase`` waves the free end."""
    w, h = 11, 13
    rows = []
    em = EMBLEMS[f.emblem]
    for y in range(h):
        row = []
        for x in range(w):
            if y >= h - 2 and 3 <= x <= 7 and (y == h - 1 or 4 <= x <= 6):
                row.append(".")                                  # swallow tail
            elif x in (0, w - 1) or y == 0 or (y >= h - 3 and (y == h - 1 or x in (2, 8))):
                row.append("d")
            elif 1 <= x <= 9 and 1 <= y <= 9 and em[y - 1][x - 1] == "#":
                row.append("e")
            else:
                row.append("f" if x < 7 else "F")
        rows.append(row)
    pal = {"d": f.dark, "f": f.color, "F": _shade(f.color), "e": f.metal}
    s = pygame.Surface((w + 2, h), pygame.SRCALPHA)
    for y, row in enumerate(rows):
        dx = 0 if y < 4 else int(round(math.sin(phase + y * 0.5) * 0.9))
        for x, ch in enumerate(row):
            if ch in pal:
                s.set_at((x + 1 + dx, y), _c(pal[ch]))
    return _outlined(s)


def _shade(hexcol: str, k: float = 0.82) -> str:
    r, g, b = _c(hexcol)
    return "#%02x%02x%02x" % (int(r * k), int(g * k), int(b * k))


def shield_surface(f: Faction, scale: int = 1) -> pygame.Surface:
    """Coat of arms: heater shield in the faction colours with its emblem."""
    w, h = 15, 17
    s = pygame.Surface((w, h), pygame.SRCALPHA)
    em = EMBLEMS[f.emblem]
    for y in range(h):
        inset = 0 if y < 9 else int((y - 8) ** 1.35 * 0.95)
        x0, x1 = inset, w - 1 - inset
        if x0 > x1:
            continue
        for x in range(x0, x1 + 1):
            border = x in (x0, x1) or y in (0, h - 1) or (y >= 9 and (x == x0 + 1 or x == x1 - 1))
            if x in (x0, x1) or y == 0 or x0 + 1 > x1 - 1:
                c = INK
            elif border or y == 1 or x in (x0 + 1, x1 - 1):
                c = _c(f.dark)
            elif 3 <= x <= 11 and 3 <= y <= 11 and em[y - 3][x - 3] == "#":
                c = _c(f.metal)
            else:
                c = _c(f.color) if x < 9 else _c(_shade(f.color))
            s.set_at((x, y), c)
    if scale != 1:
        s = pygame.transform.scale(s, (w * scale, h * scale))
    return s


def wrap(text: str, width_px: int) -> List[str]:
    lines, cur = [], ""
    for word in text.split():
        cand = f"{cur} {word}" if cur else word
        if text_width(cand.upper()) > width_px and cur:
            lines.append(cur)
            cur = word
        else:
            cur = cand
    if cur:
        lines.append(cur)
    return lines


def load_map(progress=None) -> pygame.Surface:
    """The world map surface, generated once and cached as PNG."""
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / f"worldmap_{worldgen.map_key()}.png"
    if path.exists():
        try:
            return pygame.image.load(str(path)).convert()
        except pygame.error:
            pass
    if progress:
        progress()
    m = worldgen.generate()
    surf = pygame.image.frombuffer(m.rgb.tobytes(), (MAP_W, MAP_H), "RGB").convert()
    try:
        pygame.image.save(surf, str(path))
    except pygame.error:
        pass
    return surf


# --- the screen ------------------------------------------------------------------------------------
class Button:
    def __init__(self, rect, label: str, action: str, color: str = "#3a4466"):
        self.rect = pygame.Rect(rect)
        self.label = label
        self.action = action
        self.color = color


class WorldMapScreen:
    def __init__(self, renderer: Renderer, progress=None):
        self.r = renderer
        self.font = renderer.font
        self.map = load_map(progress)
        self.mini = self._minimap()
        self.cam = [float(CITY["kronholm"].x - W // 2), float(CITY["kronholm"].y - H // 2)]
        self.time = 0.0
        self.drag: Optional[Tuple[int, int, float, float]] = None
        self.dragged = False
        self.hover_city: Optional[str] = None
        self.selected: Optional[str] = None
        self.faction_panel: Optional[str] = None
        self.diplomacy = False
        self.hover_rel: Optional[Tuple[str, str]] = None
        self.keys: Dict[int, bool] = {}
        self.buttons = [
            Button((W - 154, 2, 74, 11), "ДИПЛОМАТИЯ", "diplomacy"),
            Button((W - 78, 2, 76, 11), "БЫСТРЫЙ БОЙ", "battle", "#a22633"),
        ]
        # sprites
        self.city_art: Dict[Tuple[str, str], Tuple[pygame.Surface, int]] = {}
        for c in CITIES:
            key = (c.kind, c.faction)
            if key not in self.city_art:
                f = FACTION[c.faction]
                grid, pole = city_grid(c.kind)
                pal = dict(STONE, r=f.color, R=f.dark)
                self.city_art[key] = (_outlined(grid_surface(grid, pal)), pole + 1)
        self.banners = {f.key: [banner_surface(f, i * math.tau / 8) for i in range(8)] for f in ALL_FACTIONS}
        self.shields = {f.key: shield_surface(f) for f in ALL_FACTIONS}
        self.big_shields = {f.key: shield_surface(f, 2) for f in ALL_FACTIONS}
        self.crown = grid_surface(_rows(("g.g.g", "ggggg", "ggggg")), STONE)
        self.dim = pygame.Surface((W, H), pygame.SRCALPHA)
        self.dim.fill((24, 20, 37, 150))
        self.bar = pygame.Surface((W, 1), pygame.SRCALPHA)
        self._clamp()

    # --- helpers -----------------------------------------------------------------------------
    def _minimap(self) -> pygame.Surface:
        arr = pygame.surfarray.array3d(self.map)                    # (w, h, 3)
        w, h = MAP_W // MINI_K, MAP_H // MINI_K
        a = arr[:w * MINI_K, :h * MINI_K].reshape(w, MINI_K, h, MINI_K, 3).mean(axis=(1, 3))
        return pygame.surfarray.make_surface(a.astype(np.uint8))

    def _clamp(self) -> None:
        self.cam[0] = max(0.0, min(MAP_W - W, self.cam[0]))
        self.cam[1] = max(-TOP, min(MAP_H - H + BOTTOM, self.cam[1]))

    def _mini_rect(self) -> pygame.Rect:
        w, h = self.mini.get_size()
        return pygame.Rect(W - w - 4, H - BOTTOM - h - 4, w, h)

    def _city_rects(self, c: City) -> Tuple[pygame.Rect, pygame.Rect]:
        """Screen rects of a city's sprite (incl. flag) and its name ribbon."""
        art, _ = self.city_art[(c.kind, c.faction)]
        sx, sy = round(c.x - self.cam[0]), round(c.y - self.cam[1])
        aw, ah = art.get_size()
        sprite = pygame.Rect(sx - aw // 2, sy - ah - 10, aw, ah + 10)
        tw = text_width(c.name) + 12 + (6 if c.key == FACTION[c.faction].capital else 0)
        ribbon = pygame.Rect(sx - tw // 2, sy + 2, tw, 9)
        return sprite, ribbon

    def _city_at(self, mx: int, my: int) -> Optional[str]:
        for c in reversed(sorted(CITIES, key=lambda c: c.y)):
            s, r = self._city_rects(c)
            if s.collidepoint(mx, my) or r.collidepoint(mx, my):
                return c.key
        return None

    # --- input -------------------------------------------------------------------------------
    def handle(self, ev, mouse: Tuple[int, int]) -> Optional[str]:
        mx, my = mouse
        if ev.type == pygame.KEYDOWN:
            self.keys[ev.key] = True
            if ev.key == pygame.K_ESCAPE:
                if self.diplomacy or self.faction_panel or self.selected:
                    self.diplomacy, self.faction_panel, self.selected = False, None, None
                else:
                    return "quit"
            if ev.key in (pygame.K_RETURN, pygame.K_b):
                return "battle"
        elif ev.type == pygame.KEYUP:
            self.keys[ev.key] = False
        elif ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 3:
            self.diplomacy, self.faction_panel, self.selected = False, None, None
        elif ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
            for b in self.buttons:
                if b.rect.collidepoint(mx, my):
                    if b.action == "diplomacy":
                        self.diplomacy = not self.diplomacy
                        self.faction_panel = None
                        return None
                    return b.action
            if self.diplomacy:
                if not self._diplo_rect().collidepoint(mx, my):
                    self.diplomacy = False
                return None
            if self.faction_panel:
                if not self._faction_rect().collidepoint(mx, my):
                    self.faction_panel = None
                return None
            if my >= H - BOTTOM:
                f = self._bar_faction(mx)
                if f:
                    self.faction_panel = f
                    self.selected = None
                return None
            if my < TOP:
                return None
            if self.selected and self._city_panel_rect().collidepoint(mx, my):
                return None
            mini = self._mini_rect()
            if mini.collidepoint(mx, my):
                self.cam = [(mx - mini.x) * MINI_K - W / 2, (my - mini.y) * MINI_K - H / 2]
                self._clamp()
                self.drag = (mx, my, -1.0, -1.0)
                return None
            self.drag = (mx, my, self.cam[0], self.cam[1])
            self.dragged = False
        elif ev.type == pygame.MOUSEBUTTONUP and ev.button == 1 and self.drag:
            if not self.dragged and self.drag[2] >= 0:
                self.selected = self._city_at(mx, my)
            self.drag = None
        elif ev.type == pygame.MOUSEMOTION and self.drag:
            x0, y0, cx, cy = self.drag
            mini = self._mini_rect()
            if cx < 0:                                   # dragging inside the minimap
                if mini.collidepoint(mx, my):
                    self.cam = [(mx - mini.x) * MINI_K - W / 2, (my - mini.y) * MINI_K - H / 2]
                    self._clamp()
                return None
            if abs(mx - x0) + abs(my - y0) > 2:
                self.dragged = True
            if self.dragged:
                self.cam = [cx - (mx - x0), cy - (my - y0)]
                self._clamp()
        return None

    def update(self, dt: float, mouse: Tuple[int, int]) -> None:
        self.time += dt
        k = self.keys
        vx = (k.get(pygame.K_RIGHT) or k.get(pygame.K_d) or 0) - (k.get(pygame.K_LEFT) or k.get(pygame.K_a) or 0)
        vy = (k.get(pygame.K_DOWN) or k.get(pygame.K_s) or 0) - (k.get(pygame.K_UP) or k.get(pygame.K_w) or 0)
        if vx or vy:
            self.cam[0] += vx * 260 * dt
            self.cam[1] += vy * 260 * dt
            self._clamp()
        mx, my = mouse
        busy = self.diplomacy or self.faction_panel or my < TOP or my >= H - BOTTOM
        self.hover_city = None if busy or self.drag and self.dragged else self._city_at(mx, my)
        self.hover_rel = None
        if self.diplomacy:
            self.hover_rel = self._diplo_cell(mx, my)
        elif self.faction_panel:
            self.hover_rel = self._faction_rel_at(mx, my)

    # --- drawing ------------------------------------------------------------------------------
    def draw(self, s: pygame.Surface) -> None:
        s.fill(INK)
        cx, cy = int(round(self.cam[0])), int(round(self.cam[1]))
        s.blit(self.map, (0, 0), pygame.Rect(cx, cy, W, H))
        if cy < 0:
            s.blit(self.map, (0, -cy), pygame.Rect(cx, 0, W, H + cy))
        self._landmarks(s)
        self._cities(s)
        self._bars(s)
        self._minimap_draw(s)
        if self.selected:
            self._city_panel(s, CITY[self.selected])
        if self.faction_panel:
            s.blit(self.dim, (0, 0))
            self._faction_window(s, FACTION[self.faction_panel])
        if self.diplomacy:
            s.blit(self.dim, (0, 0))
            self._diplo_window(s)

    def _landmarks(self, s: pygame.Surface) -> None:
        for name, x, y in worldgen.LANDMARKS:
            sx, sy = x - self.cam[0], y - self.cam[1]
            if -120 < sx < W + 120 and -10 < sy < H + 10:
                col = "#d8e8f8" if "МОРЕ" in name or "ОКЕАН" in name or "ОЗЕРО" in name else "#f4ead0"
                if "ОКЕАН" in name:
                    for i, ch in enumerate(name):          # vertical along the west coast
                        self.font.draw(s, ch, sx, sy - len(name) * 4 + i * 8, col, anchor="midtop", outline=(30, 60, 100))
                    continue
                self.font.draw(s, name, sx, sy, col, anchor="center",
                               outline=(30, 60, 100) if col == "#d8e8f8" else (60, 44, 30))

    def _cities(self, s: pygame.Surface) -> None:
        phase = int(self.time * 8) % 8
        for c in sorted(CITIES, key=lambda c: c.y):
            sx, sy = round(c.x - self.cam[0]), round(c.y - self.cam[1])
            if not (-60 < sx < W + 60 and -50 < sy < H + 30):
                continue
            f = FACTION[c.faction]
            art, pole = self.city_art[(c.kind, c.faction)]
            aw, ah = art.get_size()
            top = sy - ah + 1
            hot = c.key in (self.hover_city, self.selected)
            if c.key == self.selected:
                ring = 18 + int(math.sin(self.time * 6) * 1.5)
                pygame.draw.ellipse(s, _c("#fee761"), (sx - ring, sy - 5, ring * 2, 10), 1)
            elif c.key == self.hover_city:
                pygame.draw.ellipse(s, _c("#ffffff"), (sx - 17, sy - 5, 34, 10), 1)
            # flag pole + banner
            px = sx - aw // 2 + pole
            pole_top = top - 12
            pygame.draw.line(s, INK, (px, pole_top), (px, top + 2))
            pygame.draw.line(s, _c("#c9a24a"), (px - 6, pole_top + 1), (px + 6, pole_top + 1))
            pygame.draw.rect(s, _c("#fee761"), (px - 1, pole_top - 2, 2, 2))
            ban = self.banners[f.key][(phase + c.x) % 8]
            s.blit(ban, (px - ban.get_width() // 2, pole_top + 1))
            s.blit(art, (sx - aw // 2, top))
            self._ribbon(s, c, f, sx, sy, hot)

    def _ribbon(self, s: pygame.Surface, c: City, f: Faction, sx: int, sy: int, hot: bool) -> None:
        _, r = self._city_rects(c)
        r.topleft = (r.x, r.y)
        dark, base, light = _c(f.dark), _c(f.color), _c(f.light)
        # folded tails
        for side in (-1, 1):
            tx = r.left - 3 if side < 0 else r.right
            pygame.draw.rect(s, INK, (tx - (1 if side < 0 else 0), r.y + 2, 5, 8))
            pygame.draw.rect(s, dark, (tx + (0 if side < 0 else 0), r.y + 3, 3, 6))
        pygame.draw.rect(s, INK, r.inflate(2, 2))
        pygame.draw.rect(s, base, r)
        pygame.draw.line(s, light, (r.x, r.y), (r.right - 1, r.y))
        pygame.draw.line(s, dark, (r.x, r.bottom - 1), (r.right - 1, r.bottom - 1))
        if hot:
            pygame.draw.rect(s, _c("#ffffff"), r.inflate(2, 2), 1)
        x = r.x + 6
        if c.key == f.capital:
            s.blit(self.crown, (x - 1, r.y + 3))
            x += 6
        self.font.draw(s, c.name, x, r.y + 1, "#fee761" if hot else "#ffffff")

    def _bars(self, s: pygame.Surface) -> None:
        f = self.font
        s.blit(self.r.panel(W, TOP, base="#181425", border="#5a6988"), (0, 0))
        f.draw(s, "КАРТА МИРА", 5, 4, "#fee761")
        f.draw(s, "ЛКМ: ТЯНИ КАРТУ, КЛИК ПО ГОРОДУ ИЛИ ФРАКЦИИ - СВЕДЕНИЯ", 52, 4, "#8b9bb4")
        for b in self.buttons:
            active = b.action == "diplomacy" and self.diplomacy
            s.blit(self.r.panel(b.rect.w, b.rect.h, base="#5a6988" if active else b.color, border="#8b9bb4"),
                   b.rect.topleft)
            f.draw(s, b.label, b.rect.centerx, b.rect.centery, "#ffffff", anchor="center")
        y = H - BOTTOM
        s.blit(self.r.panel(W, BOTTOM, base="#181425", border="#5a6988"), (0, y))
        cw = W // len(ALL_FACTIONS)
        for i, fac in enumerate(ALL_FACTIONS):
            x = i * cw + 2
            hot = self.faction_panel == fac.key
            if hot:
                pygame.draw.rect(s, _c(fac.color), (x, y + 2, cw - 3, BOTTOM - 4), 1)
            s.blit(self.shields[fac.key], (x + 2, y + 3))
            f.draw(s, fac.short, x + 19, y + 4, fac.light)
            n = len(cities_of(fac.key))
            f.draw(s, f"{n} ГОР." if fac.playable else f"{n} ЛОГОВ", x + 19, y + 12, "#8b9bb4")

    def _bar_faction(self, mx: int) -> Optional[str]:
        i = mx // (W // len(ALL_FACTIONS))
        return ALL_FACTIONS[i].key if 0 <= i < len(ALL_FACTIONS) else None

    def _minimap_draw(self, s: pygame.Surface) -> None:
        r = self._mini_rect()
        pygame.draw.rect(s, INK, r.inflate(4, 4))
        pygame.draw.rect(s, _c("#c9a24a"), r.inflate(2, 2), 1)
        s.blit(self.mini, r.topleft)
        for c in CITIES:
            col = _c(FACTION[c.faction].color)
            px, py = r.x + c.x // MINI_K, r.y + c.y // MINI_K
            pygame.draw.rect(s, INK, (px - 1, py - 1, 3, 3))
            s.set_at((px, py), col)
        vr = pygame.Rect(r.x + int(self.cam[0]) // MINI_K, r.y + int(self.cam[1]) // MINI_K, W // MINI_K, H // MINI_K)
        pygame.draw.rect(s, _c("#ffffff"), vr.clip(r), 1)

    # --- city panel ----------------------------------------------------------------------------
    def _city_panel_rect(self) -> pygame.Rect:
        c = CITY[self.selected]
        w = 166
        roads = wrap("ДОРОГИ: " + ", ".join(CITY[n].name for n in neighbors(c.key)), w - 10)
        h = 25 + 7 * len(wrap(c.desc, w - 10)) + 10 + 17 * len(c.pool) + 1 + 7 * len(roads) + 4
        return pygame.Rect(W - w - 4, TOP + 3, w, h)

    def _city_panel(self, s: pygame.Surface, c: City) -> None:
        r = self._city_panel_rect()
        f = FACTION[c.faction]
        font = self.font
        s.blit(self.r.panel(r.w, r.h, base="#181425", border=f.color), r.topleft)
        s.blit(self.shields[f.key], (r.x + 5, r.y + 5))
        font.draw(s, c.name, r.x + 24, r.y + 5, "#fee761")
        kind = KIND_NAMES[c.kind] + (" (СТОЛИЦА)" if c.key == f.capital and c.kind != "capital" else "")
        font.draw(s, f"{kind} - {f.short}", r.x + 24, r.y + 13, f.light)
        y = r.y + 25
        for line in wrap(c.desc, r.w - 10):
            font.draw(s, line, r.x + 5, y, "#c0cbdc")
            y += 7
        y += 2
        font.draw(s, "НАЙМ В ГОРОДЕ:", r.x + 5, y, "#fee761")
        y += 8
        team = TEAMS[0]
        for key in c.pool:
            box = pygame.Rect(r.x + 5, y, 20, 15)
            pygame.draw.rect(s, (38, 43, 68), box)
            pygame.draw.rect(s, (90, 105, 136), box, 1)
            if unit_exists(key):
                por = self.r.portrait(f"{key}_{team.key}")
                s.blit(por, (box.x + 1, box.y + 1), area=pygame.Rect(0, 0, 18, 13))
                from .units import ROSTER
                font.draw(s, unit_name(key), box.right + 4, y + 1, "#ffffff")
                font.draw(s, f"{unit_role(key)}  {ROSTER[key].cost} ЗОЛ.", box.right + 4, y + 8, "#8b9bb4")
            else:
                font.draw(s, "?", box.centerx, box.centery, "#5a6988", anchor="center")
                font.draw(s, unit_name(key), box.right + 4, y + 1, "#c0cbdc")
                font.draw(s, unit_role(key) + " - НОВЫЙ", box.right + 4, y + 8, "#41a6f6")
            y += 17
        y += 1
        names = ", ".join(CITY[n].name for n in neighbors(c.key))
        for line in wrap("ДОРОГИ: " + names, r.w - 10):
            font.draw(s, line, r.x + 5, y, "#8b9bb4")
            y += 7

    # --- faction window --------------------------------------------------------------------------
    def _faction_rect(self) -> pygame.Rect:
        return pygame.Rect(10, TOP + 4, W - 20, H - TOP - BOTTOM - 8)

    def _faction_rows(self, f: Faction) -> List[Tuple[pygame.Rect, str]]:
        r = self._faction_rect()
        x0 = r.x + 262
        return [(pygame.Rect(x0, r.y + 24 + i * 16, r.right - x0 - 6, 15), o.key)
                for i, o in enumerate(o for o in FACTIONS if o.key != f.key)]

    def _faction_rel_at(self, mx: int, my: int) -> Optional[Tuple[str, str]]:
        f = FACTION[self.faction_panel]
        if not f.playable:
            return None
        for rect, other in self._faction_rows(f):
            if rect.collidepoint(mx, my):
                return f.key, other
        return None

    def _faction_window(self, s: pygame.Surface, f: Faction) -> None:
        r = self._faction_rect()
        font = self.font
        s.blit(self.r.panel(r.w, r.h, base="#181425", border=f.color), r.topleft)
        s.blit(self.big_shields[f.key], (r.x + 6, r.y + 6))
        font.draw(s, f.name, r.x + 42, r.y + 6, f.light)
        font.draw(s, f"{'ЛИДЕР' if f.playable else 'ГЛАВАРЬ'}: {f.leader} - {f.leader_title}", r.x + 42, r.y + 15,
                  "#ffffff")
        cap = CITY[f.capital].name
        n = len(cities_of(f.key))
        font.draw(s, f"СТОЛИЦА: {cap}   ГОРОДОВ: {n}" if f.playable else f"ЛОГОВО БОССА: {cap}   ЛОГОВ: {n}",
                  r.x + 42, r.y + 24, "#c0cbdc")
        if not f.playable:
            font.draw(s, "НЕИГРОВАЯ ФРАКЦИЯ", r.x + 42, r.y + 33, "#e43b44")
        y = r.y + 44
        for line in wrap(f.lore, 246):
            font.draw(s, line, r.x + 6, y, "#c0cbdc")
            y += 7
        y += 4
        font.draw(s, "ОСОБЕННОСТИ (БУДУТ В ПОШАГОВОМ РЕЖИМЕ):", r.x + 6, y, "#fee761")
        y += 9
        for name, desc in f.mechanics:
            head = font.render(name, "#a7f070")
            s.blit(head, (r.x + 6, y - 1))
            lines = wrap(f"{name} - {desc}", 246)
            first = lines[0][len(name):]
            s.blit(font.render(first, "#63c74d"), (r.x + 6 + head.get_width() - 2, y - 1))
            y += 7
            for line in lines[1:]:
                font.draw(s, "  " + line, r.x + 6, y, "#63c74d")
                y += 7
            y += 1
        # relations
        x0 = r.x + 262
        pygame.draw.line(s, _c("#3a4466"), (x0 - 6, r.y + 6), (x0 - 6, r.bottom - 6))
        font.draw(s, "ОТНОШЕНИЯ", x0, r.y + 6, "#fee761")
        if not f.playable:
            for i, line in enumerate(wrap("Гоблины не ведут переговоров. Они воюют со всеми, и любая фракция "
                                          "может отбить их логова.", r.right - x0 - 8)):
                font.draw(s, line, x0, r.y + 18 + i * 7, "#f6757a")
            return
        font.draw(s, "НАВЕДИ НА СТРОКУ - ПРИЧИНА", x0, r.y + 14, "#5a6988")
        for rect, other in self._faction_rows(f):
            o = FACTION[other]
            v, _ = relation(f.key, other)
            label, col = relation_status(v)
            hot = self.hover_rel == (f.key, other)
            if hot:
                pygame.draw.rect(s, (38, 43, 68), rect)
            s.blit(self.shields[other], (rect.x, rect.y - 1))
            font.draw(s, o.short, rect.x + 18, rect.y + 1, o.light)
            bar = pygame.Rect(rect.x + 18, rect.y + 9, 60, 3)
            pygame.draw.rect(s, (38, 43, 68), bar)
            pygame.draw.rect(s, _c(col), (bar.x, bar.y, max(1, bar.w * v // 100), 3))
            font.draw(s, str(v), rect.x + 82, rect.y + 5, "#ffffff")
            font.draw(s, label, rect.x + 96, rect.y + 5, col)
        goblin = pygame.Rect(x0, r.y + 24 + 7 * 16, r.right - x0 - 6, 15)
        s.blit(self.shields["goblin"], (goblin.x, goblin.y - 1))
        font.draw(s, GOBLINS.short, goblin.x + 18, goblin.y + 1, GOBLINS.light)
        font.draw(s, "ВЕЧНАЯ ВОЙНА", goblin.x + 96, goblin.y + 5, "#e43b44")
        if self.hover_rel:
            _, reason = relation(*self.hover_rel)
            y = goblin.bottom + 4
            for line in wrap(reason, r.right - x0 - 8):
                font.draw(s, line, x0, y, "#ffffff")
                y += 7

    # --- diplomacy window -----------------------------------------------------------------------
    CELL_W, CELL_H = 39, 17

    def _diplo_rect(self) -> pygame.Rect:
        return pygame.Rect(20, TOP + 4, W - 40, H - TOP - BOTTOM - 8)

    def _diplo_origin(self) -> Tuple[int, int]:
        r = self._diplo_rect()
        return r.x + 64, r.y + 36

    def _diplo_cell(self, mx: int, my: int) -> Optional[Tuple[str, str]]:
        x0, y0 = self._diplo_origin()
        i, j = (mx - x0) // self.CELL_W, (my - y0) // self.CELL_H
        n = len(ALL_FACTIONS)
        if mx >= x0 and my >= y0 and i < n and j < n and i != j:
            return ALL_FACTIONS[j].key, ALL_FACTIONS[i].key
        return None

    def _diplo_window(self, s: pygame.Surface) -> None:
        r = self._diplo_rect()
        font = self.font
        s.blit(self.r.panel(r.w, r.h, base="#181425", border="#c9a24a"), r.topleft)
        font.draw(s, "ДИПЛОМАТИЯ", r.centerx, r.y + 5, "#fee761", anchor="midtop")
        x0, y0 = self._diplo_origin()
        cw, ch = self.CELL_W, self.CELL_H
        for i, f in enumerate(ALL_FACTIONS):
            s.blit(self.shields[f.key], (x0 + i * cw + (cw - 15) // 2, y0 - 18))
            s.blit(self.shields[f.key], (x0 - 18, y0 + i * ch))
            font.draw(s, f.short, x0 - 20, y0 + i * ch + 5, f.light, anchor="topright")
        for j, a in enumerate(ALL_FACTIONS):
            for i, b in enumerate(ALL_FACTIONS):
                cell = pygame.Rect(x0 + i * cw, y0 + j * ch, cw - 1, ch - 1)
                hot = self.hover_rel in ((a.key, b.key), (b.key, a.key))
                if a.key == b.key:
                    pygame.draw.rect(s, (38, 43, 68), cell)
                    continue
                v, _ = relation(a.key, b.key)
                _, col = relation_status(v)
                pygame.draw.rect(s, (58, 68, 102) if hot else (38, 43, 68), cell)
                pygame.draw.rect(s, _c(col), (cell.x, cell.bottom - 2, cell.w, 2))
                font.draw(s, str(v) if v > 0 else "X", cell.centerx, cell.centery - 1, col, anchor="center")
        if self.hover_rel:
            a, b = self.hover_rel
            v, reason = relation(a, b)
            label, col = relation_status(v)
            y = y0 + len(ALL_FACTIONS) * ch + 4
            font.draw(s, f"{FACTION[a].short} - {FACTION[b].short}: {label}", r.x + 8, y, col)
            for k, line in enumerate(wrap(reason, r.w - 16)):
                font.draw(s, line, r.x + 8, y + 8 + k * 7, "#ffffff")
        else:
            y = y0 + len(ALL_FACTIONS) * ch + 5
            x = r.x + 8
            for label, col in (("ДО 19 ВОЙНА", "#e43b44"), ("20-40 НАПРЯЖЕНИЕ", "#feae34"),
                               ("41-59 НЕЙТРАЛИТЕТ", "#c0cbdc"), ("60-79 ДРУЖБА", "#a7f070"),
                               ("80+ СОЮЗ", "#63c74d"), ("X ГОБЛИНЫ: ТОЛЬКО ВОЙНА", "#e43b44")):
                x = font.draw(s, label, x, y, col).right + 8
            font.draw(s, "НАВЕДИ НА КЛЕТКУ, ЧТОБЫ УЗНАТЬ ПРИЧИНУ", r.centerx, y + 10, "#5a6988", anchor="midtop")
