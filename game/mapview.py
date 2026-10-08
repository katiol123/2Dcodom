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
from .campaign import Campaign
from .campaign_runner import Runner
from .cardui import CardTable
from .officercard import OfficerCard
from .officers import OFFICER, SQUAD_SLOTS, STAT_HELP, STATS
from .units import ROSTER, TEAMS, TIER_NAMES

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


ZOOMS = (1.0, 0.5, 0.25)        # mouse wheel: the map can be pulled back (never closer than 1:1)


class WorldMapScreen:
    def __init__(self, renderer: Renderer, progress=None, campaign: Optional[Campaign] = None):
        self.r = renderer
        self.font = renderer.font
        self.camp = campaign or Campaign(None)
        self.map = load_map(progress)
        self.mini = self._minimap()
        self.maps = {1.0: self.map, 0.5: self._shrunk(2), 0.25: self._shrunk(4)}
        self.zoom = 1.0
        home = CITY[FACTION[self.camp.player].capital] if self.camp.player else CITY["kronholm"]
        self.cam = [float(home.x - W // 2), float(home.y - H // 2)]
        self.window: Optional[Tuple[str, str]] = None      # ("army" | "hire", city)
        self.win_officer = 0
        self.win_scroll = 0
        self.win_hover: Optional[Tuple[str, int]] = None
        self.toast: Tuple[str, str, float] = ("", "#ffffff", 0.0)
        self.flash = 0.0                                  # white fade-in after the faction choice
        self.cards = OfficerCard(renderer, self.camp)    # clickable faces/names and the officer card
        self._mouse = (0, 0)
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
            Button((W - 236, 2, 34, 11), "СОВЕТ", "council", "#124e89"),
            Button((W - 200, 2, 44, 11), "ХРОНИКА", "chronicle", "#5a4a1a"),
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
        self.table = CardTable(self)                      # the hand, targeting, council, chronicle
        self.runner = Runner(self.camp)                   # card plays and turns run in a worker thread
        self.running: Optional[tuple] = None              # what the runner is doing (for its result)
        self.frozen: Optional[pygame.Surface] = None      # the last frame, shown while it runs
        self._clamp()

    # --- helpers -----------------------------------------------------------------------------
    def _minimap(self) -> pygame.Surface:
        arr = pygame.surfarray.array3d(self.map)                    # (w, h, 3)
        w, h = MAP_W // MINI_K, MAP_H // MINI_K
        a = arr[:w * MINI_K, :h * MINI_K].reshape(w, MINI_K, h, MINI_K, 3).mean(axis=(1, 3))
        return pygame.surfarray.make_surface(a.astype(np.uint8))

    def _art(self, kind: str, faction: str) -> Tuple[pygame.Surface, int]:
        key = (kind, faction)
        if key not in self.city_art:
            f = FACTION[faction]
            grid, pole = city_grid(kind)
            self.city_art[key] = (_outlined(grid_surface(grid, dict(STONE, r=f.color, R=f.dark))), pole + 1)
        return self.city_art[key]

    def _shrunk(self, k: int) -> pygame.Surface:
        """The map pulled back k times: k x k pixel blocks averaged (clean, no dropped pixels)."""
        arr = pygame.surfarray.array3d(self.map)
        w, h = MAP_W // k, MAP_H // k
        a = arr[:w * k, :h * k].reshape(w, k, h, k, 3).mean(axis=(1, 3))
        return pygame.surfarray.make_surface(a.astype(np.uint8)).convert()

    def _clamp(self) -> None:
        z = self.zoom
        vw, vh = W / z, (H - TOP - BOTTOM) / z
        for i, (size, view, pad) in enumerate(((MAP_W, vw, 0.0), (MAP_H, vh, TOP / z))):
            lo, hi = -pad, size - view - pad
            self.cam[i] = (lo + hi) / 2 if hi < lo else max(lo, min(hi, self.cam[i]))

    def _to_screen(self, x: float, y: float) -> Tuple[int, int]:
        return round((x - self.cam[0]) * self.zoom), round((y - self.cam[1]) * self.zoom)

    def _zoom_at(self, step: int, mx: int, my: int) -> None:
        i = ZOOMS.index(self.zoom)
        j = max(0, min(len(ZOOMS) - 1, i + step))
        if j == i:
            return
        wx, wy = self.cam[0] + mx / self.zoom, self.cam[1] + my / self.zoom
        self.zoom = ZOOMS[j]
        self.cam = [wx - mx / self.zoom, wy - my / self.zoom]
        self._clamp()

    def _mini_rect(self) -> pygame.Rect:
        w, h = self.mini.get_size()
        return pygame.Rect(W - w - 4, H - BOTTOM - h - 4, w, h)

    def _city_rects(self, c: City) -> Tuple[pygame.Rect, pygame.Rect]:
        """Screen rects of a city's sprite (incl. flag) and its name ribbon."""
        art, _ = self._art(c.kind, self.camp.owner[c.key])
        sx, sy = self._to_screen(c.x, c.y)
        if self.zoom < 1:                              # pulled back: a flag marker, the ribbon on hover only
            return pygame.Rect(sx - 7, sy - 16, 14, 18), pygame.Rect(sx - 1, sy - 1, 2, 2)
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
    def run(self, fn, what: tuple) -> None:
        """Play a card / end the turn in the background: a storm may stop it for a real battle."""
        self.running = what
        self.runner.start(fn)

    def battle_request(self):
        """The storm the runner waits on to be fought for real (or None)."""
        req = self.runner.request
        return req["battle"] if req and req["kind"] == "battle" else None

    def finish_battle(self) -> None:
        self.runner.reply(True)

    def handle(self, ev, mouse: Tuple[int, int]) -> Optional[str]:
        mx, my = mouse
        if self.runner.busy():                            # only the runner's questions are live
            self.table.handle_request(ev, mouse)
            if ev.type == pygame.QUIT:
                return "quit"
            return None
        if self.cards.handle(ev, mouse):                 # a face or a name anywhere opens the card
            return None
        if self.window is None and not self.faction_panel and not self.diplomacy:
            if self.table.handle(ev, mouse):               # cards: the hand, targets, council, chronicle
                return None
        if self.window is not None:
            return self._window_handle(ev, mx, my)
        if ev.type == pygame.MOUSEWHEEL and not (self.diplomacy or self.faction_panel):
            self._zoom_at(1 if ev.y < 0 else -1, mx, my)
            return None
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
                    if b.action == "council":
                        self.table.open_council()
                        return None
                    if b.action == "chronicle":
                        self.table.chronicle_open = True
                        self.table.chron_scroll = 0
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
            if self.selected:
                for rect, action in self._city_buttons():
                    if rect.collidepoint(mx, my):
                        self.window = (action, self.selected)
                        self.win_officer, self.win_scroll = 0, 0
                        return None
                if self._city_panel_rect().collidepoint(mx, my):
                    return None
            mini = self._mini_rect()
            if mini.collidepoint(mx, my):
                self._mini_jump(mx, my)
                self.drag = (mx, my, -1.0, -1.0)
                return None
            self.drag = (mx, my, self.cam[0], self.cam[1])
            self.dragged = False
        elif ev.type == pygame.MOUSEBUTTONUP and ev.button == 1 and self.drag:
            if not self.dragged and self.drag[2] >= 0 and not self.table.play:
                self.selected = self._city_at(mx, my)
            self.drag = None
        elif ev.type == pygame.MOUSEMOTION and self.drag:
            x0, y0, cx, cy = self.drag
            mini = self._mini_rect()
            if cx < 0:                                   # dragging inside the minimap
                if mini.collidepoint(mx, my):
                    self._mini_jump(mx, my)
                return None
            if abs(mx - x0) + abs(my - y0) > 2:
                self.dragged = True
            if self.dragged:
                self.cam = [cx - (mx - x0) / self.zoom, cy - (my - y0) / self.zoom]
                self._clamp()
        return None

    def _mini_jump(self, mx: int, my: int) -> None:
        mini = self._mini_rect()
        self.cam = [(mx - mini.x) * MINI_K - W / 2 / self.zoom, (my - mini.y) * MINI_K - H / 2 / self.zoom]
        self._clamp()

    def update(self, dt: float, mouse: Tuple[int, int]) -> None:
        self.time += dt
        self.flash = max(0.0, self.flash - dt * 1.6)
        self._mouse = mouse
        done = self.runner.collect()
        if done and self.running:
            what, self.running = self.running, None
            self.table.finished(what, done)
        if self.runner.busy():
            return
        self.table.update(dt, mouse)
        if self.window is not None:
            self._window_update(mouse)
            return
        k = self.keys
        vx = (k.get(pygame.K_RIGHT) or k.get(pygame.K_d) or 0) - (k.get(pygame.K_LEFT) or k.get(pygame.K_a) or 0)
        vy = (k.get(pygame.K_DOWN) or k.get(pygame.K_s) or 0) - (k.get(pygame.K_UP) or k.get(pygame.K_w) or 0)
        if vx or vy:
            self.cam[0] += vx * 260 * dt / self.zoom
            self.cam[1] += vy * 260 * dt / self.zoom
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
        if self.runner.busy() and self.frozen is not None:
            self.cards.begin(self._mouse)
            s.blit(self.frozen, (0, 0))
            req = self.runner.request
            if not req:
                label = "ХОДЯТ ДРУГИЕ ДЕРЖАВЫ..." if self.running and self.running[0] != "play" else "..."
                w = self.font.render(label, "#fff").get_width() + 16
                rect = pygame.Rect((W - w) // 2, H // 2 - 8, w, 15)
                s.blit(self.r.panel(rect.w, rect.h, base="#181425", border="#fee761"), rect.topleft)
                self.font.draw(s, label, rect.centerx, rect.centery, "#fee761", anchor="center")
            self.table.draw_request(s)
            return
        self._draw(s)
        self.frozen = s.copy()

    def _draw(self, s: pygame.Surface) -> None:
        self.cards.begin(self._mouse)
        s.fill(INK)
        z = self.zoom
        src = self.maps[z]
        ox, oy = self._to_screen(0, 0)
        s.blit(src, (ox, oy))
        self._landmarks(s)
        self._cities(s)
        self.table.draw_targets(s)
        self._bars(s)
        self._minimap_draw(s)
        free = self.window is None and not self.faction_panel and not self.diplomacy
        if free:
            self.table.draw_hand(s)
        if self.selected:
            self._city_panel(s, CITY[self.selected])
            self._city_buttons_draw(s)
        if free:
            text, col, until = self.toast
            if self.time < until and not self.table.busy():
                w = self.font.render(text, col).get_width() + 12
                rect = pygame.Rect((W - w) // 2, TOP + 18, w, 13)
                s.blit(self.r.panel(rect.w, rect.h, base="#181425", border=col), rect.topleft)
                self.font.draw(s, text, rect.centerx, rect.centery, col, anchor="center")
        if self.window is not None or self.faction_panel or self.diplomacy:
            self.cards.cover()                           # a window covers the faces on the map panels
        if self.window is not None:
            s.blit(self.dim, (0, 0))
            self._window_draw(s)
        if self.faction_panel:
            s.blit(self.dim, (0, 0))
            self._faction_window(s, FACTION[self.faction_panel])
        if self.diplomacy:
            s.blit(self.dim, (0, 0))
            self._diplo_window(s)
        self.table.draw_windows(s)
        self.cards.draw(s)
        if self.flash > 0:
            veil = pygame.Surface((W, H))
            veil.fill((255, 244, 214))
            veil.set_alpha(int(255 * self.flash))
            s.blit(veil, (0, 0))

    def _landmarks(self, s: pygame.Surface) -> None:
        for name, x, y in worldgen.LANDMARKS:
            sx, sy = self._to_screen(x, y)
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
            sx, sy = self._to_screen(c.x, c.y)
            if not (-60 < sx < W + 60 and -50 < sy < H + 30):
                continue
            f = FACTION[self.camp.owner[c.key]]
            if self.zoom < 1:
                self._city_marker(s, c, f, sx, sy, phase)
                continue
            art, pole = self._art(c.kind, f.key)
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

    def _city_marker(self, s: pygame.Surface, c: City, f: Faction, sx: int, sy: int, phase: int) -> None:
        """Pulled-back view: a banner on a pole (half zoom) or a small shield (quarter zoom)."""
        hot = c.key in (self.hover_city, self.selected)
        if self.zoom >= 0.5:
            pygame.draw.line(s, INK, (sx, sy - 16), (sx, sy))
            ban = self.banners[f.key][(phase + c.x) % 8]
            s.blit(ban, (sx - ban.get_width() // 2, sy - 16))
            if c.key == f.capital:
                s.blit(self.crown, (sx - 2, sy - 21))
        else:
            sh = self.shields[f.key]
            s.blit(sh, (sx - sh.get_width() // 2, sy - sh.get_height()))
        if hot:
            pygame.draw.ellipse(s, _c("#fee761"), (sx - 9, sy - 3, 18, 6), 1)
            self.font.draw(s, c.name, sx, sy + 2, "#fee761", anchor="midtop")

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
        p = self.camp.player
        if p is None:
            f.draw(s, "РЕЖИМ ЗРИТЕЛЯ", 5, 4, "#c0cbdc")
            x = 5 + text_width("РЕЖИМ ЗРИТЕЛЯ") + 10
        else:
            fac = FACTION[p]
            s.blit(self.shields[p], (3, -1))
            f.draw(s, fac.short, 20, 4, fac.light)
            x = 20 + text_width(fac.short) + 8
            f.draw(s, f"ЗОЛОТО {self.camp.gold[p]}", x, 4, "#fee761")
            x += text_width(f"ЗОЛОТО {self.camp.gold[p]}") + 8
            r = self.camp.realms[p]
            f.draw(s, "ОД", x, 4, "#41a6f6")
            x += 13
            for i in range(max(self.camp.ap_max(p), r.ap)):
                pygame.draw.rect(s, INK, (x - 1, 3, 7, 9))
                pygame.draw.rect(s, _c("#41a6f6") if i < r.ap else _c("#262b44"), (x, 4, 5, 7))
                x += 7
            x += 4
        f.draw(s, f"ХОД {self.camp.turn}", x, 4, "#c0cbdc")
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
            n = len(self.camp.cities_of(fac.key))
            label = (f"{n} ГОР." if fac.playable else f"{n} ЛОГОВ") if n else "ПАЛА"
            f.draw(s, label, x + 19, y + 12, "#8b9bb4" if n else "#e43b44")

    def _bar_faction(self, mx: int) -> Optional[str]:
        i = mx // (W // len(ALL_FACTIONS))
        return ALL_FACTIONS[i].key if 0 <= i < len(ALL_FACTIONS) else None

    def _minimap_draw(self, s: pygame.Surface) -> None:
        r = self._mini_rect()
        pygame.draw.rect(s, INK, r.inflate(4, 4))
        pygame.draw.rect(s, _c("#c9a24a"), r.inflate(2, 2), 1)
        s.blit(self.mini, r.topleft)
        for c in CITIES:
            col = _c(FACTION[self.camp.owner[c.key]].color)
            px, py = r.x + c.x // MINI_K, r.y + c.y // MINI_K
            pygame.draw.rect(s, INK, (px - 1, py - 1, 3, 3))
            s.set_at((px, py), col)
        vr = pygame.Rect(r.x + int(self.cam[0]) // MINI_K, r.y + int(self.cam[1]) // MINI_K,
                         int(W / self.zoom) // MINI_K, int(H / self.zoom) // MINI_K)
        pygame.draw.rect(s, _c("#ffffff"), vr.clip(r), 1)

    # --- city panel ----------------------------------------------------------------------------
    def _city_panel_rect(self) -> pygame.Rect:
        c = CITY[self.selected]
        w = 166
        roads = wrap("ДОРОГИ: " + ", ".join(CITY[n].name for n in neighbors(c.key)), w - 10)
        h = 25 + 7 * len(wrap(c.desc, w - 10)) + 10 + 17 * len(c.pool) + 1 + 7 * len(roads) + 4 + 9 + 21 + 17
        return pygame.Rect(W - w - 4, TOP + 3, w, h)

    PANEL_FACES = 9

    def _city_panel(self, s: pygame.Surface, c: City) -> None:
        r = self._city_panel_rect()
        f = FACTION[self.camp.owner[c.key]]
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
        y += 1
        pros = self.camp.prosperity[c.key]
        font.draw(s, "ПРОЦВЕТАНИЕ", r.x + 5, y, "#feae34")
        for i in range(self.camp.max_prosperity(c.key)):
            pygame.draw.rect(s, INK, (r.x + 62 + i * 6, y, 5, 6))
            pygame.draw.rect(s, _c("#feae34") if i < pros else _c("#3a4466"), (r.x + 63 + i * 6, y + 1, 3, 4))
        font.draw(s, f"ПОДАТЬ {self.camp.income_of(c.key, self.camp.owner[c.key])}", r.right - 5, y, "#fee761",
                  anchor="topright")
        y += 8
        notes = []
        if c.key in self.camp.siege:
            notes.append(f"В ОСАДЕ ({FACTION[self.camp.siege[c.key][0]].short})")
        if c.key in self.camp.defense:
            notes.append(f"ОБОРОНА x{self.camp.defense[c.key][0]:.2g}")
        notes.append(f"ЗАЩИТА {int(self.camp.defense_power(c.key))}")
        font.draw(s, "  ".join(notes), r.x + 5, y, "#8b9bb4")
        y += 9
        offs = self.camp.officers_in(c.key)
        font.draw(s, f"ОФИЦЕРОВ: {len(offs)}   СВОБОДНЫХ ВОИНОВ: {len(self.camp.free[c.key])}", r.x + 5, y, "#a7f070")
        y += 9
        for i, o in enumerate(offs[:self.PANEL_FACES]):
            self.cards.face(s, pygame.Rect(r.x + 6 + i * 17, y, 15, 18), o.key)
        hot = next((k for rect, k in self.cards.hits if rect.collidepoint(self._mouse)), None)
        if hot:
            font.draw(s, OFFICER[hot].name, r.right - 5, y + 5, "#ffffff", anchor="topright")
        y += 22
        font.draw(s, "НАЙМ В ГОРОДЕ:", r.x + 5, y, "#fee761")
        left = self.camp.muster.get(c.key, 0)
        font.draw(s, f"ОТКРЫТ ЕЩЁ {left} Х." if left else "ЗАКРЫТ (КАРТА СБОР ВОЙСК)", r.right - 5, y,
                  "#a7f070" if left else "#5a6988", anchor="topright")
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
        # every officer serving the faction: click a face for the card
        offs = self.camp.officers_of(f.key)
        per = 12
        rows = (len(offs) + per - 1) // per
        y = r.bottom - 6 - rows * 23
        font.draw(s, f"ОФИЦЕРЫ: {len(offs)}", r.x + 6, y - 9, "#fee761")
        hot = None
        for i, o in enumerate(offs):
            rect = pygame.Rect(r.x + 7 + (i % per) * 20, y + (i // per) * 23, 18, 21)
            self.cards.face(s, rect, o.key)
            if rect.collidepoint(self._mouse):
                hot = o
        if hot:
            font.draw(s, f"{hot.name} - {hot.title}", r.x + 62, y - 9, "#ffffff")
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

    # --- city buttons: ARMY / HIRE (own cities only) ----------------------------------------------
    def _city_buttons(self) -> List[Tuple[pygame.Rect, str]]:
        if self.selected is None or not self.camp.controls(self.selected):
            return []
        r = self._city_panel_rect()
        return [(pygame.Rect(r.x - 50, r.y + 4, 47, 15), "army"), (pygame.Rect(r.x - 50, r.y + 22, 47, 15), "hire")]

    def _city_buttons_draw(self, s: pygame.Surface) -> None:
        mx, my = self._mouse
        for rect, action in self._city_buttons():
            hot = rect.collidepoint(mx, my)
            base = "#3e8948" if action == "hire" else "#124e89"
            s.blit(self.r.panel(rect.w, rect.h, base="#5a6988" if hot else base, border="#c0cbdc"), rect.topleft)
            self.font.draw(s, "АРМИЯ" if action == "army" else "НАЙМ", rect.centerx, rect.centery, "#ffffff",
                           anchor="center")

    # --- portraits ---------------------------------------------------------------------------------
    # --- army / hire windows -----------------------------------------------------------------------
    WIN = pygame.Rect(8, TOP + 3, W - 16, H - TOP - BOTTOM - 6)

    def _win_close_rect(self) -> pygame.Rect:
        return pygame.Rect(self.WIN.right - 16, self.WIN.y + 3, 12, 11)

    def _say(self, text: str, color: str = "#e43b44") -> None:
        self.toast = (text, color, self.time + 2.0)

    def _win_officers(self) -> list:
        return self.camp.officers_in(self.window[1])

    def _slot_rect(self, i: int) -> pygame.Rect:
        x0, y0 = self.WIN.x + 6, self.WIN.y + 118
        return pygame.Rect(x0 + (i % 2) * 113, y0 + (i // 2) * 21, 110, 19)

    def _free_rect(self, i: int) -> pygame.Rect:
        return pygame.Rect(self.WIN.x + 238, self.WIN.y + 30 + i * 21, self.WIN.w - 244, 19)

    def _hire_rect(self, i: int) -> pygame.Rect:
        return pygame.Rect(self.WIN.x + 6, self.WIN.y + 30 + i * 30, 220, 28)

    def _hire_button(self, i: int) -> pygame.Rect:
        r = self._hire_rect(i)
        return pygame.Rect(r.right - 46, r.y + 7, 42, 14)

    FREE_ROWS = 8

    def _window_handle(self, ev, mx: int, my: int) -> Optional[str]:
        kind, city = self.window
        if ev.type == pygame.KEYDOWN:
            if ev.key in (pygame.K_ESCAPE, pygame.K_a if kind == "army" else pygame.K_h):
                self.window = None
            elif ev.key in (pygame.K_LEFT, pygame.K_RIGHT) and kind == "army":
                self._cycle(1 if ev.key == pygame.K_RIGHT else -1)
            return None
        if ev.type == pygame.MOUSEWHEEL:
            self.win_scroll = max(0, self.win_scroll - ev.y)
            return None
        if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 3:
            self.window = None
            return None
        if ev.type != pygame.MOUSEBUTTONDOWN or ev.button != 1:
            return None
        if self._win_close_rect().collidepoint(mx, my) or not self.WIN.collidepoint(mx, my):
            self.window = None
            return None
        free = self.camp.free[city]
        rows = free[self.win_scroll:self.win_scroll + self.FREE_ROWS]
        if kind == "army":
            offs = self._win_officers()
            for d, rect in ((-1, self._arrow(-1)), (1, self._arrow(1))):
                if rect.collidepoint(mx, my):
                    self._cycle(d)
                    return None
            if not offs:
                return None
            off = offs[self.win_officer % len(offs)]
            squad = self.camp.squads[off.key]
            for i in range(SQUAD_SLOTS):
                if self._slot_rect(i).collidepoint(mx, my) and i < len(squad):
                    t = squad[i]
                    self.camp.unassign(off.key, t.id)
                    self._say(f"{ROSTER[t.key].name} - В ГОРОД", "#c0cbdc")
                    return None
            for i, t in enumerate(rows):
                if self._free_rect(i).collidepoint(mx, my):
                    ok, why = self.camp.can_assign(off.key, t.id)
                    if ok:
                        self.camp.assign(off.key, t.id)
                        self._say(f"{ROSTER[t.key].name} - К {off.name}", "#a7f070")
                    else:
                        self._say(why)
                    return None
        else:
            for i, key in enumerate(CITY[city].pool):
                if self._hire_button(i).collidepoint(mx, my):
                    ok, why = self.camp.can_hire(city, key)
                    if ok:
                        self.camp.hire(city, key)
                        self._say(f"НАНЯТ: {ROSTER[key].name}", "#a7f070")
                    else:
                        self._say(why)
                    return None
        return None

    def _cycle(self, d: int) -> None:
        n = len(self._win_officers())
        if n:
            self.win_officer = (self.win_officer + d) % n

    def _arrow(self, d: int) -> pygame.Rect:
        return pygame.Rect(self.WIN.x + (6 if d < 0 else 212), self.WIN.y + 17, 14, 11)

    def _window_update(self, mouse) -> None:
        mx, my = mouse
        self._mouse = mouse
        self.win_hover = None
        kind, city = self.window
        if kind == "army":
            for i in range(SQUAD_SLOTS):
                if self._slot_rect(i).collidepoint(mx, my):
                    self.win_hover = ("slot", i)
        for i in range(self.FREE_ROWS):
            if self._free_rect(i).collidepoint(mx, my):
                self.win_hover = ("free", i)
        if kind == "hire":
            for i in range(len(CITY[city].pool)):
                if self._hire_rect(i).collidepoint(mx, my):
                    self.win_hover = ("hire", i)

    def _troop_row(self, s: pygame.Surface, rect: pygame.Rect, key: Optional[str], hot: bool, bad: bool = False,
                   empty_label: str = "+ ПУСТО") -> None:
        pygame.draw.rect(s, (58, 68, 102) if hot else (38, 43, 68), rect)
        pygame.draw.rect(s, _c("#e43b44") if bad else ((139, 155, 180) if hot else (90, 105, 136)), rect, 1)
        if key is None:
            self.font.draw(s, empty_label, rect.centerx, rect.centery, "#3a4466" if not hot else "#8b9bb4",
                           anchor="center")
            return
        u = ROSTER[key]
        por = self.r.portrait(f"{key}_{TEAMS[0].key}")
        s.blit(por, (rect.x + 1, rect.y + 2), area=pygame.Rect(0, 0, 18, 13))
        name = u.short if len(u.name) > 16 and u.short else u.name
        self.font.draw(s, name, rect.x + 22, rect.y + 2, "#ffffff")
        self.font.draw(s, f"МОЩЬ {u.cost}", rect.x + 22, rect.y + 10, "#feae34")

    def _window_draw(self, s: pygame.Surface) -> None:
        kind, city = self.window
        c = CITY[city]
        f = FACTION[self.camp.owner[city]]
        r = self.WIN
        font = self.font
        s.blit(self.r.panel(r.w, r.h, base="#181425", border=f.color), r.topleft)
        cr = self._win_close_rect()
        pygame.draw.rect(s, (162, 38, 51), cr)
        font.draw(s, "X", cr.centerx + 1, cr.centery, "#ffffff", anchor="center")
        title = ("АРМИЯ" if kind == "army" else "НАЙМ") + f" - {c.name}"
        font.draw(s, title, r.centerx, r.y + 4, "#fee761", anchor="midtop")
        font.draw(s, f"ЗОЛОТО {self.camp.gold[f.key]}", r.x + 8, r.y + 4, "#feae34")
        if kind == "army":
            self._army_left(s, f)
        else:
            self._hire_left(s, c, f)
        # right column: unassigned troops in the city
        free = self.camp.free[city]
        self.win_scroll = max(0, min(self.win_scroll, max(0, len(free) - self.FREE_ROWS)))
        x = r.x + 238
        pygame.draw.line(s, (58, 68, 102), (x - 5, r.y + 16), (x - 5, r.bottom - 14))
        font.draw(s, f"СВОБОДНЫЕ ВОИНЫ В ГОРОДЕ: {len(free)}", x, r.y + 18, "#a7f070")
        if self.win_scroll or len(free) > self.FREE_ROWS:
            font.draw(s, f"{self.win_scroll + 1}-{min(len(free), self.win_scroll + self.FREE_ROWS)}", r.right - 6,
                      r.y + 18, "#5a6988", anchor="topright")
        off = None
        if kind == "army" and self._win_officers():
            offs = self._win_officers()
            off = offs[self.win_officer % len(offs)]
        for i, t in enumerate(free[self.win_scroll:self.win_scroll + self.FREE_ROWS]):
            hot = self.win_hover == ("free", i)
            bad = hot and off is not None and not self.camp.can_assign(off.key, t.id)[0]
            self._troop_row(s, self._free_rect(i), t.key, hot, bad)
        if not free:
            font.draw(s, "НИКОГО - НАЙМИТЕ ВОИНОВ", x + (r.right - x) // 2, r.y + 60, "#3a4466", anchor="midtop")
        # hint / toast
        text, col, until = self.toast
        if self.time < until:
            font.draw(s, text, r.centerx, r.bottom - 10, col, anchor="midtop")
        else:
            hint = ("КЛИК ПО СВОБОДНОМУ ВОИНУ - В ОТРЯД ОФИЦЕРА, ПО СЛОТУ - ВЕРНУТЬ В ГОРОД   < > - ОФИЦЕР"
                    if kind == "army" else "НАНЯТЫЕ ВОИНЫ ВСТАЮТ В ГОРОДЕ. В ОТРЯД ИХ БЕРЁТ ОФИЦЕР В ОКНЕ АРМИИ")
            font.draw(s, hint, r.centerx, r.bottom - 10, "#5a6988", anchor="midtop")

    def _army_left(self, s: pygame.Surface, f: Faction) -> None:
        r = self.WIN
        font = self.font
        offs = self._win_officers()
        for d in (-1, 1):
            a = self._arrow(d)
            pygame.draw.rect(s, (58, 68, 102) if len(offs) > 1 else (38, 43, 68), a)
            font.draw(s, "<" if d < 0 else ">", a.centerx, a.centery, "#ffffff", anchor="center")
        if not offs:
            font.draw(s, "В ГОРОДЕ НЕТ ОФИЦЕРОВ", r.x + 116, r.y + 60, "#8b9bb4", anchor="midtop")
            return
        i = self.win_officer % len(offs)
        o = offs[i]
        font.draw(s, f"ОФИЦЕР {i + 1} ИЗ {len(offs)}", r.x + 116, r.y + 19, "#c0cbdc", anchor="midtop")
        # card
        card = pygame.Rect(r.x + 6, r.y + 31, 220, 46)
        pygame.draw.rect(s, (38, 43, 68), card)
        pygame.draw.rect(s, _c(f.color), card, 1)
        self.cards.face(s, pygame.Rect(card.x + 3, card.y + 3, 34, 40), o.key)
        self.cards.name(s, o.key, card.x + 48, card.y + 4)
        font.draw(s, o.title, card.x + 48, card.y + 12, f.light)
        lead = self.camp.leadership(o.key)
        font.draw(s, f"ЛИДЕРСТВО {lead}   УР. {self.camp.level[o.key]}", card.x + 48, card.y + 22, "#ffffff")
        power = self.camp.power(o.key)
        bar = pygame.Rect(card.x + 48, card.y + 31, 166, 5)
        pygame.draw.rect(s, INK, bar.inflate(2, 2))
        pygame.draw.rect(s, (38, 43, 68), bar)
        frac = power / max(1, lead)
        pygame.draw.rect(s, _c("#63c74d" if frac < 0.95 else "#feae34"), (bar.x, bar.y, int(bar.w * min(1, frac)), bar.h))
        font.draw(s, f"МОЩЬ ОТРЯДА {power} / {lead}", card.x + 48, card.y + 37, "#a7f070")
        # six non-combat stats (1..20)
        mx, my = getattr(self, "_mouse", (0, 0))
        for k, st in enumerate(STATS):
            x = r.x + 6 + (k % 2) * 113
            y = r.y + 82 + (k // 2) * 11
            v = self.camp.ostats[o.key][k]
            hot = pygame.Rect(x, y, 110, 10).collidepoint(mx, my)
            font.draw(s, st, x, y, "#fee761" if hot else "#c0cbdc")
            font.draw(s, str(v), x + 108, y, "#ffffff", anchor="topright")
            pygame.draw.rect(s, (38, 43, 68), (x, y + 7, 92, 2))
            pygame.draw.rect(s, _c("#41a6f6"), (x, y + 7, int(92 * v / 20), 2))
            if hot:
                font.draw(s, STAT_HELP[st], r.centerx, r.bottom - 10, "#41a6f6", anchor="midtop")
                self.toast = ("", "#ffffff", 0.0)
        squad = self.camp.squads[o.key]
        for k in range(SQUAD_SLOTS):
            key = squad[k].key if k < len(squad) else None
            self._troop_row(s, self._slot_rect(k), key, self.win_hover == ("slot", k))

    def _hire_left(self, s: pygame.Surface, c: City, f: Faction) -> None:
        font = self.font
        gold = self.camp.gold[f.key]
        left = self.camp.muster.get(c.key, 0)
        font.draw(s, f"СБОР ВОЙСК: НАЙМ ОТКРЫТ ЕЩЁ {left} Х." if left else "НАЙМ ЗАКРЫТ: СЫГРАЙТЕ СБОР ВОЙСК",
                  self.WIN.x + 116, self.WIN.y + 18, "#a7f070" if left else "#f6757a", anchor="midtop")
        for i, key in enumerate(c.pool):
            u = ROSTER[key]
            r = self._hire_rect(i)
            hot = self.win_hover == ("hire", i)
            pygame.draw.rect(s, (58, 68, 102) if hot else (38, 43, 68), r)
            pygame.draw.rect(s, (90, 105, 136), r, 1)
            por = self.r.portrait(f"{key}_{TEAMS[0].key}")
            s.blit(por, (r.x + 2, r.y + 2), area=pygame.Rect(0, 0, 18, 13))
            name = u.short if len(u.name) > 18 and u.short else u.name
            font.draw(s, name, r.x + 23, r.y + 2, "#ffffff")
            font.draw(s, f"{u.role}, {TIER_NAMES[u.tier]}", r.x + 23, r.y + 10, "#8b9bb4")
            font.draw(s, f"ЦЕНА {u.cost}   СОДЕРЖ. {u.upkeep}/ХОД", r.x + 23, r.y + 18, "#feae34")
            b = self._hire_button(i)
            ok = u.cost <= gold and left > 0
            s.blit(self.r.panel(b.w, b.h, base="#3e8948" if ok else "#3a4466", border="#a7f070" if ok else "#5a6988"),
                   b.topleft)
            font.draw(s, "НАНЯТЬ", b.centerx, b.centery, "#ffffff" if ok else "#5a6988", anchor="center")
