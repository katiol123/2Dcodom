"""World map screen: a big hand-designed, code-drawn map you drag around with the mouse.

* LMB drag (or arrows / WASD) - scroll; click on the minimap - jump there.
* Click a city - its owner, recruit pool and roads.  Click a faction on the
  bottom bar - its lore, leader, proposed mechanics and relations.
* ДИПЛОМАТИЯ - relation matrix of the eight playable factions (goblins: always war).
* МЕНЮ / ESC - back to the title screen (returns "quit"; the campaign is autosaved).

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
                       NEW_UNITS, City, Faction, cities_of, neighbors, relation, unit_exists,
                       unit_name, unit_role)
from .render import INK, Renderer, _c
from .sim import H, W
from .campaign import Campaign
from .cards import COUNCIL_SEATS
from .campaign_runner import Runner
from .cardui import CardTable
from .officercard import OfficerCard
from .diplomacy import status, tier
from .officers import OFFICER, SQUAD_SLOTS, STAT_HELP, STATS
from .units import ROSTER, TEAMS, TIER_NAMES

TOP, BOTTOM = 15, 23                 # UI bars
FOCUS_EDGE = 130                    # how far past the east edge a storm's camera may look
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


def _great_card(key: str):
    """The horde's great building shown as a big card (like a world event)."""
    from types import SimpleNamespace
    from .horde import GREAT
    g = GREAT[key.split(":", 1)[1]]
    return SimpleNamespace(name=g.name, text=f"{g.manner}. {g.text}", color=g.color, header="ОРДА УСИЛИЛАСЬ")


from .text import plural  # noqa: E402  (re-exported for the screens)


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


def _snowflake() -> pygame.Surface:
    rows = ("...#...", ".#.#.#.", "..###..", "#######", "..###..", ".#.#.#.", "...#...")
    img = pygame.Surface((9, 9), pygame.SRCALPHA)
    for y, row in enumerate(rows):                       # outline first, then the ice
        for x, ch in enumerate(row):
            if ch == "#":
                for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                    img.set_at((x + 1 + dx, y + 1 + dy), (24, 20, 37))
    for y, row in enumerate(rows):
        for x, ch in enumerate(row):
            if ch == "#":
                img.set_at((x + 1, y + 1), (255, 255, 255) if (x, y) == (3, 3) else (155, 211, 240))
    return img


_SNOWFLAKE = None


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
        self.zoom_back: List[Tuple[float, List[float]]] = []   # views left by zooming out, to come back to
        self.unit_card: Optional[str] = None               # a unit class shown in its card (click on a portrait)
        self._unit_boxes: dict = {}
        self._unit_h: dict = {}                            # unit card heights, by class
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
        from .diploui import DiploWindow
        self.diplo = DiploWindow(self)
        self.events_seen = len(self.camp.world_events)
        from .fx import FX
        self.fx = FX()                                     # interface animations (and their sounds)
        p = self.camp.player
        self.gold_shown = float(self.camp.gold[p]) if p else 0.0
        self.gold_last = self.camp.gold[p] if p else 0
        self.was_my_turn = False
        self.seen_levels = self.camp.stats["levels"][p] if p else 0
        self.seen_feats = sum(1 for o in self.camp.feats.values() if self.camp.allegiance.get(o) == p)
        self.event_t = 0.0
        self.seen_leader = self.camp.leader.get(p) if p else None
        self.event_show: Optional[Tuple[int, str, str]] = None     # a world event shown as a big card
        self.hover_rel: Optional[Tuple[str, str]] = None
        self.keys: Dict[int, bool] = {}
        self.buttons = [
            Button((W - 192, 2, 34, 11), "СОВЕТ", "council", "#124e89"),
            Button((W - 156, 2, 44, 11), "ХРОНИКА", "chronicle", "#5a4a1a"),
            Button((W - 110, 2, 74, 11), "ДИПЛОМАТИЯ", "diplomacy"),
            Button((W - 34, 2, 32, 11), "МЕНЮ", "menu", "#5a6988"),
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
        if self.camp.turn > 1:                            # a loaded campaign: only the last round is news
            last = self.camp.turn - 1
            self.table.chron_from = next((i for i, e in enumerate(self.camp.log) if e[0] >= last),
                                         len(self.camp.log))
            self.table.arrows_from = next((i for i, a in enumerate(self.camp.attacks) if a[0] >= last),
                                          len(self.camp.attacks))
        self.runner = Runner(self.camp)                   # card plays and turns run in a worker thread
        self.running: Optional[tuple] = None              # what the runner is doing (for its result)
        self.frozen: Optional[pygame.Surface] = None      # the last frame, shown while it runs
        global _SNOWFLAKE
        _SNOWFLAKE = _SNOWFLAKE or _snowflake()
        self.focus: Optional[dict] = None                 # a storm the camera flies to (battle_focus)
        self.saved_turn = self.camp.turn                  # a fresh campaign is saved on its first new round
        self.autosaving = False                           # battle.py turns it on (tests never touch the save)
        self._clamp()

    # --- helpers -----------------------------------------------------------------------------
    def _minimap(self) -> pygame.Surface:
        arr = pygame.surfarray.array3d(self.map)                    # (w, h, 3)
        w, h = MAP_W // MINI_K, MAP_H // MINI_K
        a = arr[:w * MINI_K, :h * MINI_K].reshape(w, MINI_K, h, MINI_K, 3).mean(axis=(1, 3))
        grey = a.mean(axis=2, keepdims=True)              # muted and darker, so the realms' colours stand out
        a = (a * 0.35 + grey * 0.65) * 0.62 + np.array([10, 9, 18]) * 0.38
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
        """Keep the map on screen, but let it slide up to half a screen past its edges, so that a city
        on the very edge can still be brought to the centre. A map smaller than the view (zoomed far out)
        moves too: any of its edges may reach the middle of the screen."""
        z = self.zoom
        vw, vh = W / z, (H - TOP - BOTTOM) / z
        for i, (size, view, pad) in enumerate(((MAP_W, vw, 0.0), (MAP_H, vh, TOP / z))):
            lo, hi = -pad, size - view - pad
            self.cam[i] = max(min(lo, hi) - view / 2, min(max(lo, hi) + view / 2, self.cam[i]))

    def _to_screen(self, x: float, y: float) -> Tuple[int, int]:
        return round((x - self.cam[0]) * self.zoom), round((y - self.cam[1]) * self.zoom)

    def _zoom_at(self, step: int, mx: int, my: int) -> None:
        i = ZOOMS.index(self.zoom)
        j = max(0, min(len(ZOOMS) - 1, i + step))
        if j == i:
            return
        if ZOOMS[j] < self.zoom:                         # pulling back: remember where we were
            self.zoom_back.append((self.zoom, list(self.cam)))
        elif self.zoom_back and self.zoom_back[-1][0] == ZOOMS[j]:
            self.zoom, self.cam = self.zoom_back.pop()   # coming back: exactly the old view
            return
        else:
            self.zoom_back.clear()
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
        if self.event_show is not None:                  # the world event card: any click or key closes it
            if ev.type in (pygame.MOUSEBUTTONDOWN, pygame.KEYDOWN):
                self.event_show = None
            return None
        if self.unit_card is not None:                   # the unit card: any click or key closes it
            if ev.type in (pygame.MOUSEBUTTONDOWN, pygame.KEYDOWN):
                self.unit_card = None
            return None
        if ev.type == pygame.MOUSEBUTTONDOWN:            # a click on a unit's portrait anywhere: its card
            hit = next((key for rect, key, button in getattr(self.cards, "units", ())
                        if button == ev.button and rect.collidepoint(mx, my) and unit_exists(key)), None)
            if hit:
                from .audio import ui
                ui("click")
                self.unit_card = hit
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
        elif ev.type == pygame.KEYUP:
            self.keys[ev.key] = False
        elif ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 3:
            self.diplomacy, self.faction_panel, self.selected = False, None, None
        elif ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
            for b in self.buttons:
                if b.rect.collidepoint(mx, my):
                    from .audio import ui
                    ui("click")
                    if b.action == "diplomacy":
                        self.diplomacy = not self.diplomacy
                        self.faction_panel = None
                        if self.diplomacy:
                            self.diplo.open()
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
                self.diplomacy = self.diplo.handle(ev, mx, my)
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
                self.zoom_back.clear()                   # moved by hand: zooming in follows the mouse
        return None

    def _mini_jump(self, mx: int, my: int) -> None:
        mini = self._mini_rect()
        self.cam = [(mx - mini.x) * MINI_K - W / 2 / self.zoom, (my - mini.y) * MINI_K - H / 2 / self.zoom]
        self._clamp()
        self.zoom_back.clear()

    def autosave(self, force: bool = False) -> None:
        """Each new round is saved for ПРОДОЛЖИТЬ (only while the runner is idle: a still campaign)."""
        if not self.autosaving or self.runner.busy() or not (force or self.camp.turn != self.saved_turn):
            return
        from . import saves
        if saves.save(self.camp):
            self.saved_turn = self.camp.turn

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
        self.autosave()
        self.fx.update(dt)
        if self.event_show is None and self.events_seen < len(self.camp.world_events):
            self.event_show = self.camp.world_events[self.events_seen]
            self.events_seen += 1
            self.event_t = self.time
            from .audio import ui
            ui("gong")
        self._watch_changes()
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
            self.zoom_back.clear()
        mx, my = mouse
        busy = self.diplomacy or self.faction_panel or my < TOP or my >= H - BOTTOM
        self.hover_city = None if busy or self.drag and self.dragged else self._city_at(mx, my)
        self.hover_rel = None
        if self.diplomacy:
            self.diplo.update(mouse)
        elif self.faction_panel:
            self.hover_rel = self._faction_rel_at(mx, my)

    # --- drawing ------------------------------------------------------------------------------
    def draw(self, s: pygame.Surface) -> None:
        req = self.runner.request
        if self.runner.busy() and req and req.get("battle") is not None and req["kind"] in ("ask", "answer"):
            if self._battle_focus(s, req):               # the camera flies to the storm, then the question
                self.table.draw_request(s)
            return
        self.focus = None
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
        self._attack_arrows(s)
        self._cities(s)
        self._city_badges(s)
        self._hot_names(s)
        self.fx.draw(s, 1)
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
            self.diplo.draw(s)
        self.table.draw_windows(s)
        self.fx.draw(s, 2)
        self.cards.draw(s)
        if self.event_show is not None:
            self._event_card(s)
        if self.unit_card is not None:
            self._unit_card_draw(s)
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

    FOCUS_FLY = 0.9                                      # seconds the camera flies to a storm
    FOCUS_X = 84                                         # where the stormed city settles on the screen

    def _battle_focus(self, s: pygame.Surface, req: dict) -> bool:
        """A storm: the camera glides to the city, the attackers' arrow grows towards it, the city flashes
        under crossed blades and a banner names the battle. True once the question may be asked."""
        from .fx import ease_back, ease_out
        b = req["battle"]
        c = CITY[b.city]
        if self.focus is None or self.focus["req"] is not req:
            if self.zoom != 1.0:                         # the storm is shown up close: keep the view's centre
                z = self.zoom
                mid = (self.cam[0] + W / z / 2, self.cam[1] + (TOP + (H - TOP - BOTTOM) / 2) / z)
                self.zoom = 1.0
                self.cam = [mid[0] - W / 2, mid[1] - TOP - (H - TOP - BOTTOM) / 2]
            # the map must cover the whole view (no void past its edge), so a city by the edge sits off-centre
            # (a little sea may show in the east: the city must stay clear of the hand and the minimap)
            to = [max(0.0, min(MAP_W - W + FOCUS_EDGE, c.x - self.FOCUS_X)),
                  max(-TOP, min(MAP_H - H + BOTTOM, c.y - TOP - (H - TOP - BOTTOM) * 0.55))]
            left = c.x - to[0] > W - 340                  # the city is under the question: ask on the left
            src = next((a[2] for a in reversed(self.camp.attacks) if a[3] == b.city), None)
            self.focus = {"req": req, "t0": self.time, "from": list(self.cam), "to": to, "src": src,
                          "sound": False, "left": left}
            self.zoom_back.clear()
        fo = self.focus
        t = self.time - fo["t0"]
        k = ease_out(min(1.0, t / self.FOCUS_FLY))
        self.cam = [a + (bb - a) * k for a, bb in zip(fo["from"], fo["to"])]
        self._draw(s)                                    # the living map under the storm
        att, deff = FACTION[b.attacker], FACTION[b.defender]
        cx, cy = self._to_screen(c.x, c.y - 6)
        # the attackers' arrow grows from their city
        if fo["src"] and fo["src"] != b.city:
            a = CITY[fo["src"]]
            ax, ay = self._to_screen(a.x, a.y - 6)
            g = max(0.0, min(1.0, (t - 0.3) / 0.6))
            d = max(1.0, math.hypot(cx - ax, cy - ay))
            g *= max(0.0, 1 - 12 / d)                     # stops short of the city, off its name ribbon
            ex, ey = ax + (cx - ax) * g, ay + (cy - ay) * g
            pygame.draw.line(s, INK, (ax, ay + 1), (ex, ey + 1), 5)
            pygame.draw.line(s, _c(att.color), (ax, ay), (ex, ey), 3)
            pygame.draw.line(s, _c(att.light), (ax, ay), (ex, ey), 1)
        if t > self.FOCUS_FLY * 0.8:
            if not fo["sound"]:
                fo["sound"] = True
                from .audio import ui
                ui("gong")
            p = (self.time * 2.2) % 1.0                   # rings rolling out of the city
            for off in (0.0, 0.5):
                q = (p + off) % 1.0
                rad = int(8 + 22 * q)
                pygame.draw.ellipse(s, _c("#e43b44") if q < 0.6 else _c("#a22633"),
                                    (cx - rad, cy - rad // 2, rad * 2, rad), 1)
            pop = ease_back(min(1.0, (t - self.FOCUS_FLY * 0.8) / 0.35))
            size = int(9 * pop)                          # crossed blades over the city
            if size > 1:
                for d in (-1, 1):
                    pygame.draw.line(s, INK, (cx - size * d, cy - 14 - size), (cx + size * d, cy - 14 + size), 4)
                    pygame.draw.line(s, _c("#e6dfd0"), (cx - size * d, cy - 14 - size), (cx + size * d, cy - 14 + size), 2)
                pygame.draw.rect(s, _c("#feae34"), (cx - 2, cy - 16, 4, 4))
            # the banner slides in under the top bar
            slide = ease_out(min(1.0, (t - self.FOCUS_FLY * 0.8) / 0.4))
            title = f"ШТУРМ: {c.name}"
            w = max(text_width(title) * 2, text_width(f"{att.short} ПРОТИВ {deff.short}")) + 20
            bx = int(-w + (w + 6) * slide)
            s.blit(self.r.panel(w, 26, base="#181425", border=att.color), (bx, TOP + 4))
            self.font.draw(s, title, bx + w // 2, TOP + 7, "#fee761", scale=2, anchor="midtop")
            vs = self.font.draw(s, f"{att.short}", bx + 10, TOP + 20, att.light)
            self.font.draw(s, " ПРОТИВ ", vs.right, TOP + 20, "#8b9bb4")
            self.font.draw(s, deff.short, vs.right + text_width(" ПРОТИВ "), TOP + 20, deff.light)
        return t > self.FOCUS_FLY + 0.35

    def _unit_card_draw(self, s: pygame.Surface) -> None:
        """The squad builder's unit card, over everything."""
        from .menu import draw_unit_info
        s.blit(self.dim, (0, 0))
        self.cards.cover()
        w = 236
        if self.unit_card not in self._unit_h:              # the card fits its text
            scratch = pygame.Surface((w, 400), pygame.SRCALPHA)
            bottom, _ = draw_unit_info(scratch, self.r, self.font, self.unit_card, 0, 0, w, 400, 0, 0.0,
                                       self._unit_boxes)
            self._unit_h[self.unit_card] = max(90, bottom + 12)
        h = self._unit_h[self.unit_card]
        x, y = W // 2 - w // 2, TOP + 30
        s.blit(self.r.panel(w, h, base="#181425", border="#c9a24a"), (x, y))
        draw_unit_info(s, self.r, self.font, self.unit_card, x, y, w, h, 0, self.time, self._unit_boxes)
        self.font.draw(s, "КЛИК - ЗАКРЫТЬ", x + w // 2, y + h - 9, "#5a6988", anchor="midtop")

    def _event_card(self, s: pygame.Surface) -> None:
        """A world event: a big card in the middle of the screen."""
        from .events import EVENT
        from .fx import ease_back
        turn, key, text = self.event_show
        e = EVENT[key] if key in EVENT else _great_card(key)
        s.blit(self.dim, (0, 0))
        k = min(1.0, (self.time - self.event_t) / 0.45)
        body = len(wrap(e.text, 196)) + len(wrap(text if not getattr(e, "header", None)
                                                   else text.split(". ", 1)[0] + ".", 196))
        final = pygame.Rect(W // 2 - 110, TOP + 18, 220, min(H - TOP - 30, 48 + 7 * body + 15 + 16))
        if k < 1:                                          # the card arrives: grows with a little overshoot
            card = pygame.Surface(final.size)
            self._event_face(card, card.get_rect(), e, turn, text)
            sc = 0.2 + 0.8 * ease_back(k)
            w, h = max(1, round(final.w * sc)), max(1, round(final.h * sc))
            s.blit(pygame.transform.scale(card, (w, h)), (final.centerx - w // 2, final.centery - h // 2))
            return
        self._event_face(s, final, e, turn, text)
        glint = int(((self.time - self.event_t) * 120) % (final.w + 60)) - 30
        if 0 <= glint < final.w - 4:
            pygame.draw.line(s, _c("#ffffff"), (final.x + glint, final.y + 2), (final.x + glint + 5, final.y + 2))

    def _event_face(self, s: pygame.Surface, r: pygame.Rect, e, turn: int, text: str) -> None:
        s.blit(self.r.panel(r.w, r.h, base="#1c1830", border=e.color), r.topleft)
        pygame.draw.rect(s, _c(e.color), r.inflate(-4, -4), 1)
        self.font.draw(s, getattr(e, "header", "СОБЫТИЕ МИРА"), r.centerx, r.y + 7, "#8b9bb4", anchor="midtop")
        self.font.draw(s, e.name, r.centerx, r.y + 17, e.color, scale=2 if text_width(e.name) * 2 < r.w - 16 else 1,
                       anchor="midtop")
        band = pygame.Rect(r.x + 10, r.y + 38, r.w - 20, 3)
        pygame.draw.rect(s, _c(e.color), band)
        y = r.y + 48
        for line in wrap(e.text, r.w - 24):
            self.font.draw(s, line, r.x + 12, y, "#c0cbdc")
            y += 7
        y += 6
        if getattr(e, "header", None):                     # the horde's great building: the text says it all
            text = text.split(". ", 1)[0] + "."
        self.font.draw(s, f"ХОД {turn}:", r.x + 12, y, "#fee761")
        y += 9
        for line in wrap(text, r.w - 24):
            self.font.draw(s, line, r.x + 12, y, "#ffffff")
            y += 7
        self.font.draw(s, "КЛИК - ДАЛЬШЕ", r.centerx, r.bottom - 11, "#5a6988", anchor="midtop")

    def _attack_arrows(self, s: pygame.Surface) -> None:
        """Storms since the player's last turn: an arrow from where the stormers came, in their colour;
        a taken city gets a solid head, a failed storm a red cross."""
        for turn, by, src, city, won in self.camp.attacks[self.table.arrows_from:]:
            if not src or src == city:
                continue
            a, b = CITY[src], CITY[city]
            x0, y0 = self._to_screen(a.x, a.y - 6)
            x1, y1 = self._to_screen(b.x, b.y - 6)
            dx, dy = x1 - x0, y1 - y0
            d = math.hypot(dx, dy) or 1
            ux, uy = dx / d, dy / d
            sx, sy = x0 + ux * 8, y0 + uy * 8                  # leave the cities themselves visible
            ex, ey = x1 - ux * 10, y1 - uy * 10
            col = _c(FACTION[by].light)
            dark = _c(FACTION[by].dark)
            pygame.draw.line(s, INK, (sx, sy + 1), (ex, ey + 1), 4)
            pygame.draw.line(s, dark, (sx, sy), (ex, ey), 3)
            pygame.draw.line(s, col, (sx, sy), (ex, ey), 1)
            px, py = -uy, ux
            head = [(ex + ux * 5, ey + uy * 5), (ex - ux * 3 + px * 4, ey - uy * 3 + py * 4),
                    (ex - ux * 3 - px * 4, ey - uy * 3 - py * 4)]
            pygame.draw.polygon(s, INK, [(x, y + 1) for x, y in head])
            pygame.draw.polygon(s, col if won else dark, head)
            k = (self.time * 0.7 + len(city) * 0.13) % 1.0        # a spark running along the arrow
            pygame.draw.rect(s, _c("#ffffff"), (round(sx + (ex - sx) * k) - 1, round(sy + (ey - sy) * k) - 1, 2, 2))
            if not won:
                cx, cy = ex + ux * 6, ey + uy * 6
                for k in (-1, 1):
                    pygame.draw.line(s, _c("#e43b44"), (cx - 3, cy - 3 * k), (cx + 3, cy + 3 * k), 2)

    def _city_badges(self, s: pygame.Surface) -> None:
        """Officers and garrison strength under every city; a red plaque over a besieged one."""
        if self.zoom < 0.5:
            return
        font = self.font
        for c in CITIES:
            sx, sy = self._to_screen(c.x, c.y)
            if not (-40 < sx < W + 40 and -40 < sy < H + 30):
                continue
            offs = self.camp.officers_in(c.key)
            power = int(self.camp.defense_power(c.key))
            label = f"{power / 1000:.1f}K" if power >= 1000 else str(power)
            y = sy + (12 if self.zoom >= 1 else 3)
            w = 18 + font.render(label, "#fff").get_width() + (10 if offs else 0)
            box = pygame.Rect(sx - w // 2, y, w, 8)
            pygame.draw.rect(s, INK, box.inflate(2, 2))
            pygame.draw.rect(s, (24, 20, 37), box)
            x = box.x + 2
            if offs:                                         # a little helmet and the count
                pygame.draw.rect(s, _c("#c0cbdc"), (x, box.y + 2, 4, 3))
                pygame.draw.rect(s, _c("#8b9bb4"), (x - 1, box.y + 5, 6, 1))
                x = font.draw(s, str(len(offs)), x + 6, box.y, "#ffffff").right + 3
            pygame.draw.polygon(s, _c("#41a6f6"), [(x, box.y + 1), (x + 5, box.y + 1), (x + 5, box.y + 4),
                                                    (x + 2, box.y + 6), (x, box.y + 4)])   # a shield
            font.draw(s, label, x + 8, box.y, "#a7d8ff")
            sieged = self.camp.siege.get(c.key)
            if sieged and sieged[0] != self.camp.owner[c.key]:
                top = sy - (46 if self.zoom >= 1 else 26)
                text = "В ОСАДЕ"
                tw = font.render(text, "#fff").get_width() + 8
                plaque = pygame.Rect(sx - tw // 2, top, tw, 9)
                pygame.draw.rect(s, INK, plaque.inflate(2, 2))
                pygame.draw.rect(s, _c("#a22633"), plaque)
                pygame.draw.line(s, _c(FACTION[sieged[0]].light), (plaque.x, plaque.bottom - 1),
                                 (plaque.right - 1, plaque.bottom - 1))
                font.draw(s, text, plaque.centerx, plaque.y + 1, "#ffffff", anchor="midtop")

    def _hot_names(self, s: pygame.Surface) -> None:
        """The hovered and the selected city's names go over everything else on the map (badges, other
        cities): up close its ribbon again, pulled back a plaque above its banner."""
        for key in dict.fromkeys(k for k in (self.selected, self.hover_city) if k):
            c = CITY[key]
            f = FACTION[self.camp.owner[key]]
            sx, sy = self._to_screen(c.x, c.y)
            if self.zoom >= 1:
                self._ribbon(s, c, f, sx, sy, True)
                continue
            tw = text_width(c.name) + 8
            y = sy - (36 if self.zoom >= 0.5 else 24)
            rect = pygame.Rect(sx - tw // 2, y, tw, 11)
            s.blit(self.r.panel(rect.w, rect.h, base=f.color, border="#fee761" if key == self.selected else f.light),
                   rect.topleft)
            self.font.draw(s, c.name, rect.centerx, rect.centery, "#ffffff", anchor="center")

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
        self.font.draw(s, c.name, x, r.y + 1, "#ffffff")         # white on every ribbon: readable on gold too
        law = self.camp.law.get(c.key)
        if c.key in self.camp.dens or (law is not None and law < 4 and self.camp.owner[c.key] != "goblin"):
            den = c.key in self.camp.dens                  # crime at a glance: a red pip (a den), amber (low order)
            pygame.draw.rect(s, INK, (r.right - 4, r.y - 4, 7, 7))
            pygame.draw.rect(s, _c("#e43b44" if den else "#feae34"), (r.right - 3, r.y - 3, 5, 5))
            s.set_at((r.right - 1, r.y - 2), _c("#ffffff"))
            if hot:                                        # the pip explains itself under the cursor
                label = "ВОРОВСКОЙ ПРИТОН" if den else f"НИЗКИЙ ПОРЯДОК {law}/10"
                tw = text_width(label) + 6
                s.blit(self.r.panel(tw, 10, base="#181425", border="#e43b44" if den else "#feae34"),
                       (r.right + 5, r.y - 6))
                self.font.draw(s, label, r.right + 8, r.y - 4, "#f6757a" if den else "#feae34")

        from .factions import CITY_FEATS
        if c.key in CITY_FEATS:                              # a city with a feature: a gold gem on the ribbon
            gx, gy = r.right - 1, r.bottom - 1
            pygame.draw.polygon(s, INK, [(gx, gy - 4), (gx + 4, gy), (gx, gy + 4), (gx - 4, gy)])
            pygame.draw.polygon(s, _c("#ffd36b"), [(gx, gy - 3), (gx + 3, gy), (gx, gy + 3), (gx - 3, gy)])
            s.set_at((gx - 1, gy - 1), _c("#ffffff"))
        if self.camp.frosted(c.key):                       # СТУЖА: a snowflake on the ribbon's left end
            fx, fy = r.x - 4, r.y - 4
            s.blit(_SNOWFLAKE, (fx, fy))
            if hot:
                label = "СТУЖА: ВОЙСКА +30% СОДЕРЖАНИЯ, В БОЮ -30% СКОРОСТИ (СЕВЕРУ НИПОЧЁМ)"
                tw = text_width(label) + 6
                x = max(2, min(W - tw - 2, r.centerx - tw // 2))
                s.blit(self.r.panel(tw, 10, base="#181425", border="#9bd3f0"), (x, r.y - 17))
                self.font.draw(s, label, x + 3, r.y - 15, "#c0e8ff")

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
            shown = round(self.gold_shown)
            f.draw(s, f"ЗОЛОТО {shown}", x, 4, "#fee761")
            x += text_width(f"ЗОЛОТО {shown}") + 8
            r = self.camp.realms[p]
            f.draw(s, "ОД", x, 4, "#41a6f6")
            x += 13
            for i in range(max(self.camp.ap_max(p), r.ap)):
                pygame.draw.rect(s, INK, (x - 1, 3, 7, 9))
                pygame.draw.rect(s, _c("#41a6f6") if i < r.ap else _c("#262b44"), (x, 4, 5, 7))
                x += 7
            x += 4
        x = f.draw(s, f"ХОД {self.camp.turn}", x, 4, "#c0cbdc").right + 6
        from .events import EVENT
        tags = []                                          # own unrest first, then running world events
        if p and self.camp.realms[p].unrest:
            tags.append((f"СМУТА {self.camp.realms[p].unrest}Х.", "#e43b44"))
        for key, left in self.camp.active.items():
            e = EVENT[key]
            tags.append((f"{e.name.split()[-1]} {left}Х.", e.color))   # short: СТУЖА, ЗАСУХА...
        limit = self.buttons[0].rect.x - 4 if self.buttons else W
        for i, (text, col) in enumerate(tags):
            rest = len(tags) - i - 1
            room = limit - (text_width(f"+{rest}") + 2 if rest else 0)
            if x + text_width(text) > room:                       # no room: say how many are hidden
                f.draw(s, f"+{len(tags) - i}", min(x, limit - text_width(f"+{len(tags) - i}")), 4, "#fee761")
                break
            x = f.draw(s, text, x, 4, col).right + 4
        free_seats = COUNCIL_SEATS - len(self.camp.realms[p].council) if p and self.camp.realms[p].alive else 0
        for b in self.buttons:
            active = b.action == "diplomacy" and self.diplomacy
            s.blit(self.r.panel(b.rect.w, b.rect.h, base="#5a6988" if active else b.color, border="#8b9bb4"),
                   b.rect.topleft)
            f.draw(s, b.label, b.rect.centerx, b.rect.centery, "#ffffff", anchor="center")
            if b.action == "council" and free_seats > 0:   # free seats: the button calls for an adviser
                glow = int(abs(math.sin(self.time * 3)) * 255)
                pygame.draw.rect(s, (255, glow, 60), b.rect.inflate(2, 2), 1)
                badge = pygame.Rect(b.rect.x - 12, b.rect.y, 9, 11)       # inside the bar, left of the button
                pygame.draw.rect(s, INK, badge.inflate(2, 2))
                pygame.draw.rect(s, _c("#e43b44"), badge)
                pygame.draw.line(s, _c("#f6757a"), badge.topleft, (badge.right - 1, badge.top))
                f.draw(s, str(free_seats), badge.centerx, badge.centery, "#ffffff", anchor="center")
        y = H - BOTTOM
        s.blit(self.r.panel(W, BOTTOM, base="#181425", border="#5a6988"), (0, y))
        cw = W // len(ALL_FACTIONS)
        for i, fac in enumerate(ALL_FACTIONS):
            x = i * cw + 2
            hot = self.faction_panel == fac.key
            if hot:
                pygame.draw.rect(s, _c(fac.color), (x, y + 2, cw - 3, BOTTOM - 4), 1)
            s.blit(self.shields[fac.key], (x + 2, y + 3))
            name = fac.short if text_width(fac.short) <= cw - 22 else fac.short[:5] + "."   # ВЕЛЬД., ДУРГХ.
            f.draw(s, name, x + 19, y + 4, fac.light)
            n = len(self.camp.cities_of(fac.key))
            label = (f"{n} ГОР." if fac.playable else f"{n} {plural(n, 'ЛОГОВО', 'ЛОГОВА', 'ЛОГОВ')}") if n \
                else "РАЗГРОМ"
            f.draw(s, label, x + 19, y + 12, "#8b9bb4" if n else "#e43b44")

    def _bar_faction(self, mx: int) -> Optional[str]:
        i = mx // (W // len(ALL_FACTIONS))
        return ALL_FACTIONS[i].key if 0 <= i < len(ALL_FACTIONS) else None

    def _minimap_draw(self, s: pygame.Surface) -> None:
        r = self._mini_rect()
        pygame.draw.rect(s, INK, r.inflate(4, 4))
        pygame.draw.rect(s, _c("#c9a24a"), r.inflate(2, 2), 1)
        s.blit(self.mini, r.topleft)
        for c in CITIES:                                  # a bright square per city in its owner's colours
            f = FACTION[self.camp.owner[c.key]]
            px, py = r.x + c.x // MINI_K, r.y + c.y // MINI_K
            n = 4 if c.key == f.capital else 3
            pygame.draw.rect(s, INK, (px - 1, py - 1, n + 2, n + 2))
            pygame.draw.rect(s, _c(f.color), (px, py, n, n))
            pygame.draw.line(s, _c(f.light), (px, py), (px + n - 1, py))   # lit top edge
            if c.key == f.capital:
                s.set_at((px + 1, py + 1), _c(f.metal))
        vr = pygame.Rect(r.x + int(self.cam[0]) // MINI_K, r.y + int(self.cam[1]) // MINI_K,
                         int(W / self.zoom) // MINI_K, int(H / self.zoom) // MINI_K)
        pygame.draw.rect(s, _c("#ffffff"), vr.clip(r), 1)

    # --- city panel ----------------------------------------------------------------------------
    def _city_panel_rect(self) -> pygame.Rect:
        c = CITY[self.selected]
        w = 166
        roads = wrap("ДОРОГИ: " + ", ".join(CITY[n].name for n in neighbors(c.key)), w - 10)
        status = sum(1 if isinstance(t, tuple) else len(wrap(t, w - 10)) for t, _ in self._city_status(c))
        h = 25 + 7 * len(wrap(c.desc, w - 10)) + 1 + 8 + 8 * status + 9 + 22 + 8 + 17 + 8 + 1 + 7 * len(roads) + 4
        return pygame.Rect(W - w - 4, TOP + 3, w, min(h, H - BOTTOM - TOP - 6))   # never over the bottom bar

    def _city_status(self, c: City) -> List[Tuple[str, str]]:
        """The city's state, one line (wrapped) per topic: tax and order, defence and troubles, buildings."""
        camp = self.camp
        owner = camp.owner[c.key]
        out = []
        from .factions import CITY_FEATS
        if c.key in CITY_FEATS:                                # the city's own feature, first and in gold
            _, name, desc = CITY_FEATS[c.key]
            out.append((f"{name}: {desc}".upper(), "#ffd36b"))
        tax = f"ПОДАТЬ {camp.income_of(c.key, owner)}"
        if c.key in camp.law and owner != "goblin":           # tax and order share a line, in their own colours
            law = camp.law[c.key]
            out.append(((tax, "#fee761"), (f"ПОРЯДОК {law}/10",
                                             "#a7f070" if law >= 6 else "#feae34" if law >= 4 else "#f6757a")))
            if c.key in camp.dens:
                out.append(("ВОРОВСКОЙ ПРИТОН: ПОДАТЬ -30%", "#e43b44"))
        else:
            out.append((tax, "#fee761"))
        notes = [f"ЗАЩИТА {int(camp.defense_power(c.key))}"]
        if c.key in camp.siege:
            notes.append(f"В ОСАДЕ ({FACTION[camp.siege[c.key][0]].short})")
        if c.key in camp.defense:
            notes.append(f"ОБОРОНА x{camp.defense[c.key][0]:.2g}")
        out.append(("   ".join(notes), "#8b9bb4"))
        trouble = []
        if c.key in camp.sick:
            trouble.append(f"БОЛЕЗНЬ {camp.sick[c.key]} Х.")
        if camp.ravaged.get(c.key):
            trouble.append(f"РАЗОРЁН БОЯМИ {camp.ravaged[c.key]} Х.")
        if trouble:
            out.append(("   ".join(trouble), "#f6757a"))
        from .buildings import BUILDINGS, slots
        from .horde import GREAT, great_in
        big = great_in(camp, c.key)
        have = camp.buildings.get(c.key, [])
        if big:                                          # the horde's great building outshines the rest
            out.append((f"ВЕЛИКАЯ ПОСТРОЙКА: {GREAT[big].name}", GREAT[big].color))
        else:
            out.append(("ЗДАНИЯ: " + (", ".join(BUILDINGS[k].name for k in have) or "НЕТ")
                        + f" ({len(have)}/{slots(c.key)})", "#feae34" if have else "#5a6988"))
        return out

    PANEL_FACES = 9

    def _city_panel(self, s: pygame.Surface, c: City) -> None:
        r = self._city_panel_rect()
        f = FACTION[self.camp.owner[c.key]]
        font = self.font
        s.blit(self.r.panel(r.w, r.h, base="#181425", border=f.color), r.topleft)
        s.blit(self.shields[f.key], (r.x + 5, r.y + 5))
        font.draw(s, c.name, r.x + 24, r.y + 5, "#fee761")
        kind = KIND_NAMES[c.kind] + (" (СТОЛИЦА)" if c.key == f.capital and c.kind != "capital" else "")
        if c.kind == "capital" and c.faction != f.key:
            kind = "ЗАХВАЧЕННАЯ СТОЛИЦА"
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
        y += 8
        for text, col in self._city_status(c):
            if isinstance(text, tuple):                       # two coloured parts on one line
                font.draw(s, col[0], r.x + 5 + text_width(text[0]) + 12, y, col[1])
                font.draw(s, text[0], r.x + 5, y, text[1])
                y += 8
                continue
            for line in wrap(text, r.w - 10):
                font.draw(s, line, r.x + 5, y, col)
                y += 8
        offs = self.camp.officers_in(c.key)
        hot = next((k for rect, k in self.cards.hits if rect.collidepoint(self._mouse)), None)
        if hot and hot in [o.key for o in offs]:              # the hovered face's name, on its own line
            font.draw(s, OFFICER[hot].name, r.x + 5, y, "#ffffff")
        else:
            font.draw(s, f"ОФИЦЕРОВ: {len(offs)}   СВОБОДНЫХ ВОИНОВ: {len(self.camp.free[c.key])}", r.x + 5, y,
                      "#a7f070")
        y += 9
        shown = offs[:self.PANEL_FACES] if len(offs) <= self.PANEL_FACES else offs[:self.PANEL_FACES - 1]
        for i, o in enumerate(shown):
            self.cards.face(s, pygame.Rect(r.x + 6 + i * 17, y, 15, 18), o.key)
        if len(offs) > len(shown):                            # the rest as "+N"
            box = pygame.Rect(r.x + 6 + len(shown) * 17, y, 15, 18)
            pygame.draw.rect(s, (38, 43, 68), box)
            pygame.draw.rect(s, (90, 105, 136), box, 1)
            font.draw(s, f"+{len(offs) - len(shown)}", box.centerx, box.centery, "#ffffff", anchor="center")
        y += 22
        font.draw(s, "НАЙМ В ГОРОДЕ:", r.x + 5, y, "#fee761")
        left = self.camp.muster.get(c.key, 0)
        font.draw(s, f"ОТКРЫТ ЕЩЁ {left} Х." if left else "ЗАКРЫТ (КАРТА СБОР ВОЙСК)", r.right - 5, y,
                  "#a7f070" if left else "#5a6988", anchor="topright")
        y += 8
        team = TEAMS[0]                                 # the pool: one row of portraits, details of the hovered one
        from .units import ROSTER
        pool = self.camp.hire_pool(c.key)
        shown = pool[0]
        for i, key in enumerate(pool):
            box = pygame.Rect(r.x + 5 + i * 23, y, 20, 15)
            hot = box.collidepoint(self._mouse)
            if hot:
                shown = key
            pygame.draw.rect(s, (58, 68, 102) if hot else (38, 43, 68), box)
            pygame.draw.rect(s, _c("#fee761") if hot else (90, 105, 136), box, 1)
            if unit_exists(key):
                por = self.r.portrait(f"{key}_{team.key}")
                s.blit(por, (box.x + 1, box.y + 1), area=pygame.Rect(0, 0, 18, 13))
                self.cards.units.append((box, key, 1))
            else:
                font.draw(s, "?", box.centerx, box.centery, "#5a6988", anchor="center")
        y += 17
        info = (f"{unit_name(shown)} - {unit_role(shown)}, {ROSTER[shown].cost} ЗОЛ." if unit_exists(shown)
                else f"{unit_name(shown)} - {unit_role(shown)} (НОВЫЙ)")
        font.draw(s, info, r.x + 5, y, "#c0cbdc")
        y += 9
        names = ", ".join(CITY[n].name for n in neighbors(c.key))
        for line in wrap("ДОРОГИ: " + names, r.w - 10):
            if y + 7 > r.bottom - 2:
                break
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
        ruler = self.camp.leader.get(f.key)
        alive = self.camp.realms[f.key].alive
        who = (f"{OFFICER[ruler].name} - {OFFICER[ruler].title}" if ruler and alive else "ДЕРЖАВА ПАЛА")
        font.draw(s, f"{'ПРАВИТЕЛЬ' if f.playable else 'ВОЖАК'}: {who}", r.x + 42, r.y + 15,
                  "#ffffff" if alive else "#e43b44")
        cap = CITY[f.capital].name + ("" if self.camp.owner[f.capital] == f.key else " (ПОТЕРЯНА)")
        n = len(self.camp.cities_of(f.key))
        font.draw(s, f"СТОЛИЦА: {cap}   ГОРОДОВ: {n}" if f.playable else
                  f"ЛОГОВО БОССА: {cap}   {n} {plural(n, 'ЛОГОВО', 'ЛОГОВА', 'ЛОГОВ')}", r.x + 42, r.y + 24, "#c0cbdc")
        if not f.playable:
            font.draw(s, "НЕИГРОВАЯ ФРАКЦИЯ", r.x + 42, r.y + 33, "#e43b44")
        y = r.y + 44
        for line in wrap(f.lore, 246):
            font.draw(s, line, r.x + 6, y, "#c0cbdc")
            y += 7
        y += 4
        font.draw(s, "ОСОБЕННОСТИ:", r.x + 6, y, "#fee761")
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
        top = y + 10                                       # below the features
        per, px, py, fw, fh = 12, 20, 23, 18, 21
        rows = (len(offs) + per - 1) // per
        if rows * py > r.bottom - 6 - top:                 # a big court: smaller faces, more per row
            per, px, py, fw, fh = 16, 15, 18, 14, 17
            rows = (len(offs) + per - 1) // per
        y = max(top, r.bottom - 6 - rows * py)
        font.draw(s, f"ОФИЦЕРЫ: {len(offs)}", r.x + 6, y - 9, "#fee761")
        hot = None
        for i, o in enumerate(offs):
            rect = pygame.Rect(r.x + 7 + (i % per) * px, y + (i // per) * py, fw, fh)
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
        font.draw(s, "НАВЕДИ НА СТРОКУ - ЧТО МЕЖДУ НИМИ БЫЛО", x0, r.y + 14, "#5a6988")
        for rect, other in self._faction_rows(f):
            o = FACTION[other]
            v = self.camp.relation(f.key, other)
            _, label, col = tier(v)
            st = status(self.camp, f.key, other)
            if st != "war":
                label += " (СОЮЗ)" if st == "alliance" else " (МИР)"
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
        if self.hover_rel:                                # what happened between them in this campaign
            from .diploui import live_reason
            y = goblin.bottom + 4
            for line in wrap(live_reason(self.camp, *self.hover_rel), r.right - x0 - 8):
                font.draw(s, line, x0, y, "#ffffff")
                y += 7

    # --- city buttons: ARMY / HIRE (own cities only) ----------------------------------------------
    def _city_buttons(self) -> List[Tuple[pygame.Rect, str]]:
        if self.selected is None or not self.camp.controls(self.selected):
            return []
        r = self._city_panel_rect()
        return [(pygame.Rect(r.x - 50, r.y + 4, 47, 15), "army"), (pygame.Rect(r.x - 50, r.y + 22, 47, 15), "hire"),
                (pygame.Rect(r.x - 50, r.y + 40, 47, 15), "build")]

    def _city_buttons_draw(self, s: pygame.Surface) -> None:
        mx, my = self._mouse
        for rect, action in self._city_buttons():
            hot = rect.collidepoint(mx, my)
            base = {"hire": "#3e8948", "army": "#124e89", "build": "#8a6410"}[action]
            s.blit(self.r.panel(rect.w, rect.h, base="#5a6988" if hot else base, border="#c0cbdc"), rect.topleft)
            self.font.draw(s, {"army": "АРМИЯ", "hire": "НАЙМ", "build": "СТРОЙКА"}[action], rect.centerx, rect.centery,
                           "#ffffff",
                           anchor="center")

    # --- portraits ---------------------------------------------------------------------------------
    # --- army / hire windows -----------------------------------------------------------------------
    WIN = pygame.Rect(8, TOP + 3, W - 16, H - TOP - BOTTOM - 6)

    def _win_close_rect(self) -> pygame.Rect:
        return pygame.Rect(self.WIN.right - 16, self.WIN.y + 3, 12, 11)

    def _watch_changes(self) -> None:
        """Turn the campaign's changes into animations: gold, the player's turn, levels and feats."""
        from .fx import Banner, FloatText, Sparks
        from .audio import ui
        p = self.camp.player
        if not p:
            return
        gold = self.camp.gold[p]
        diff = gold - self.gold_last
        if diff:
            self.gold_last = gold
            self.fx.add(FloatText(self.font, f"{diff:+d}", 62, 14, "#fee761" if diff > 0 else "#f6757a",
                                  rise=-10, cue="coins" if diff > 0 else ""))
        self.gold_shown += (gold - self.gold_shown) * 0.25 if abs(gold - self.gold_shown) > 1 else gold - self.gold_shown
        mine = self.table.my_turn()
        if mine and not self.was_my_turn and self.event_show is None:
            self.fx.add(Banner(self.font, "ВАШ ХОД", f"ХОД {self.camp.turn} - {FACTION[p].name}", FACTION[p].light,
                               H // 2 - 40, W))
        self.was_my_turn = mine
        ruler = self.camp.leader.get(p)
        if ruler != self.seen_leader:
            from .officers import OFFICER
            self.seen_leader = ruler
            ui("gong")
            self.fx.add(Banner(self.font, "ПРАВИТЕЛЬ МЁРТВ", (f"НА ТРОН ВСХОДИТ {OFFICER[ruler].name}. "
                                                              "ПОЛИТИЧЕСКАЯ НЕСТАБИЛЬНОСТЬ") if ruler else
                               "ТРОН ПУСТ", "#e43b44", H // 2 - 70, W, cue="", dur=2.6))
        lv = self.camp.stats["levels"][p]
        if lv > self.seen_levels:
            self.seen_levels = lv
            self.fx.add(FloatText(self.font, "ОФИЦЕР ПОЛУЧИЛ УРОВЕНЬ!", W // 2, TOP + 30, "#41a6f6", cue="levelup"))
        feats = sum(1 for o in self.camp.feats.values() if self.camp.allegiance.get(o) == p)
        if feats > self.seen_feats:
            self.seen_feats = feats
            ui("fanfare")
            self.fx.add(Banner(self.font, "ПОДВИГ!", "ОФИЦЕР ПОЛУЧИЛ КАРТУ ПОДВИГА", "#ffd36b", H // 2 - 70, W, cue=""))
            self.fx.add(Sparks(W // 2, H // 2 - 60, "#ffd36b", 40, 140))

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
        n = len(self.camp.hire_pool(self.window[1])) if self.window else 6
        step = min(30, (self.WIN.h - 34) // max(1, n))       # a tiltyard's cavalry may add a seventh row
        return pygame.Rect(self.WIN.x + 6, self.WIN.y + 30 + i * step, 220, min(28, step - 2))

    def _hire_button(self, i: int) -> pygame.Rect:
        r = self._hire_rect(i)
        return pygame.Rect(r.right - 46, r.y + 7, 42, 14)

    FREE_ROWS = 8

    def _build_rect(self, i: int) -> pygame.Rect:
        r = self.WIN
        return pygame.Rect(r.x + 8, r.y + 30 + i * 27, r.w - 16, 25)

    def _build_button(self, i: int) -> pygame.Rect:
        row = self._build_rect(i)
        return pygame.Rect(row.right - 84, row.y + 5, 80, 15)

    def _build_handle(self, ev, mx: int, my: int, city: str) -> None:
        from .buildings import ORDER, build
        if ev.type != pygame.MOUSEBUTTONDOWN or ev.button != 1:
            return
        for i, key in enumerate(ORDER):
            if self._build_button(i).collidepoint(mx, my):
                p = self.camp.player
                if self.camp.whose_turn() != p:
                    self._say("СТРОЯТ В СВОЙ ХОД")
                    return
                ok, msg = build(self.camp, p, city, key)
                self._say(msg, "#a7f070" if ok else "#e43b44")
                if ok:
                    from .audio import ui
                    ui("seal")
                return

    def _build_window(self, s: pygame.Surface, city: str) -> None:
        from .buildings import BUILDINGS, ORDER, can_build, sickness_block, slots
        camp, font = self.camp, self.font
        r = self.WIN
        have = camp.buildings.get(city, [])
        font.draw(s, f"МЕСТ ДЛЯ ЗДАНИЙ: {len(have)} ИЗ {slots(city)}. ЗДАНИЕ СТОИТ ЗОЛОТА И 1 ОД; НАБЕГ, "
                     "ШТУРМ И ЗАХВАТ МОГУТ ЕГО РАЗРУШИТЬ", r.x + 8, r.y + 18, "#8b9bb4")
        p = camp.player
        mine = camp.whose_turn() == p
        for i, key in enumerate(ORDER):
            b = BUILDINGS[key]
            row = self._build_rect(i)
            built = key in have
            hot = row.collidepoint(self._mouse)
            pygame.draw.rect(s, (48, 56, 86) if built else (58, 68, 102) if hot else (38, 43, 68), row)
            pygame.draw.rect(s, _c("#fee761") if built else (90, 105, 136), row, 1)
            font.draw(s, b.name, row.x + 4, row.y + 2, "#fee761" if built else "#ffffff")
            from .buildings import price_for
            font.draw(s, f"{price_for(self.camp.player, b.cost)} ЗОЛ.", row.x + 70, row.y + 2, "#feae34")
            for j, line in enumerate(wrap(b.text, row.w - 100)[:2]):
                font.draw(s, line, row.x + 4, row.y + 10 + j * 7, "#c0cbdc")
            btn = self._build_button(i)
            if built:
                font.draw(s, "ПОСТРОЕНО", btn.centerx, btn.centery, "#a7f070", anchor="center")
                continue
            ok, why = can_build(camp, p, city, key)
            ok = ok and mine and camp.realms[p].ap >= 1
            s.blit(self.r.panel(btn.w, btn.h, base="#3e8948" if ok else "#3a4466",
                                border="#a7f070" if ok else "#5a6988"), btn.topleft)
            short = {"НЕ ХВАТАЕТ ЗОЛОТА": "МАЛО ЗОЛОТА", "НЕТ МЕСТА ДЛЯ СТРОЙКИ": "НЕТ МЕСТА",
                     "ЭТО НЕ ВАШ ГОРОД": "ЧУЖОЙ ГОРОД"}.get(why, why)
            font.draw(s, "ПОСТРОИТЬ" if ok else (short if why else "НЕТ ОД"), btn.centerx, btn.centery,
                      "#ffffff" if ok else "#8b9bb4", anchor="center")
        block = sickness_block(camp, city)
        if block:
            font.draw(s, f"ЛАЗАРЕТЫ РЯДОМ ОСТАНАВЛИВАЮТ БОЛЕЗНЬ ЗДЕСЬ С ШАНСОМ {int(block * 100)}%", r.x + 8,
                      r.bottom - 12, "#7a9e48")

    def _window_handle(self, ev, mx: int, my: int) -> Optional[str]:
        kind, city = self.window
        if kind == "build":
            if ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE or \
                    ev.type == pygame.MOUSEBUTTONDOWN and (ev.button == 3 or self._win_close_rect().collidepoint(mx, my)
                                                           or not self.WIN.collidepoint(mx, my)):
                self.window = None
                return None
            self._build_handle(ev, mx, my, city)
            return None
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
            for i, key in enumerate(self.camp.hire_pool(city)):
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
        if kind == "build":
            return
        if kind == "army":
            for i in range(SQUAD_SLOTS):
                if self._slot_rect(i).collidepoint(mx, my):
                    self.win_hover = ("slot", i)
        for i in range(self.FREE_ROWS):
            if self._free_rect(i).collidepoint(mx, my):
                self.win_hover = ("free", i)
        if kind == "hire":
            for i in range(len(self.camp.hire_pool(city))):
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
        self.cards.units.append((rect, key, 3))              # a left click moves him, a right click shows him
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
        title = {"army": "АРМИЯ", "hire": "НАЙМ", "build": "СТРОЙКА"}[kind] + f" - {c.name}"
        font.draw(s, title, r.centerx, r.y + 4, "#fee761", anchor="midtop")
        font.draw(s, f"ЗОЛОТО {self.camp.gold[f.key]}", r.x + 8, r.y + 4, "#feae34")
        if kind == "build":
            self._build_window(s, city)
            return
        if kind == "army":
            self._stat_tip = None
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
        if getattr(self, "_stat_tip", None):
            font.draw(s, self._stat_tip, r.centerx, r.bottom - 10, "#41a6f6", anchor="midtop")
        elif self.time < until:
            font.draw(s, text, r.centerx, r.bottom - 10, col, anchor="midtop")
        else:
            hint = ("КЛИК - В ОТРЯД ИЛИ В ГОРОД, ПКМ - КАРТОЧКА ВОИНА   < > - ОФИЦЕР"
                    if kind == "army" else "НАНЯТЫЕ ВСТАЮТ В ГОРОДЕ, В ОТРЯД ИХ БЕРЁТ ОФИЦЕР. КЛИК ПО ПОРТРЕТУ - КАРТОЧКА")
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
                self._stat_tip = STAT_HELP[st]           # shown in the footer instead of the hint
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
        for i, key in enumerate(self.camp.hire_pool(c.key)):
            u = ROSTER[key]
            r = self._hire_rect(i)
            hot = self.win_hover == ("hire", i)
            pygame.draw.rect(s, (58, 68, 102) if hot else (38, 43, 68), r)
            pygame.draw.rect(s, (90, 105, 136), r, 1)
            por = self.r.portrait(f"{key}_{TEAMS[0].key}")
            s.blit(por, (r.x + 2, r.y + 2), area=pygame.Rect(0, 0, 18, 13))
            self.cards.units.append((pygame.Rect(r.x + 1, r.y + 1, 21, 16), key, 1))
            self.cards.units.append((r, key, 3))
            name = u.short if len(u.name) > 18 and u.short else u.name
            font.draw(s, name, r.x + 23, r.y + 2, "#ffffff")
            font.draw(s, f"{u.role}, {TIER_NAMES[u.tier]}", r.x + 23, r.y + 10, "#8b9bb4")
            font.draw(s, f"ЦЕНА {self.camp.hire_price(c.key, key)}   СОДЕРЖ. {u.upkeep}/ХОД", r.x + 23, r.y + 18,
                      "#feae34")
            b = self._hire_button(i)
            ok = self.camp.hire_price(c.key, key) <= gold and left > 0
            s.blit(self.r.panel(b.w, b.h, base="#3e8948" if ok else "#3a4466", border="#a7f070" if ok else "#5a6988"),
                   b.topleft)
            font.draw(s, "НАНЯТЬ", b.centerx, b.centery, "#ffffff" if ok else "#5a6988", anchor="center")
