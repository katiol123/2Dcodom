"""Squad builder screen: pick up to 7 units for each side, then start the battle.

Mouse: left click on a card adds it to the active squad (highlighted), right
click adds it to the other one; click a squad's header to make it active;
click a unit in a squad to remove it.  Keys: ENTER - fight, ESC - world map.
"""

from __future__ import annotations

import json
import random
import textwrap
from typing import List, Optional, Tuple

import pygame

from .assets import cache_dir
from .render import INK, Renderer, _c
from .sim import H, W
from .match import random_squad
from .units import ALL, CLASSIC, ROSTER, SQUAD_MAX, TEAMS, TIER_NAMES

PANEL_W = 116
GRID_X, GRID_Y = 124, 37
CARD_W, CARD_H = 38, 24
COLS = 6
ROWS = 3                 # visible card rows; the rest scrolls (mouse wheel or the arrows)
TABS_Y = 24              # faction filter tabs above the cards
TAB_W = 20


def faction_units() -> dict:
    """Units each faction can hire somewhere in its cities (filter tabs of the builder)."""
    from .factions import ALL_FACTIONS, CITIES
    out = {}
    for f in ALL_FACTIONS:
        keys = {u for c in CITIES if c.faction == f.key for u in c.pool}
        out[f.key] = [k for k in ALL if k in keys]
    return out
SAVE = "squads.json"


# --- the unit card (squad builder and campaign screens) -------------------------------------------------
INFO_COLORS = {"perks": ("#a7f070", "#63c74d"), "flaws": ("#f6757a", "#e43b44"), "behavior": ("#73eff7", "#41a6f6")}
INFO_WRAP, INFO_LINE = 53, 6


def preview_box(rend, look: str, boxes: dict) -> pygame.Rect:
    """Union of the visible pixels of the attack and walk frames (stable crop, no jitter)."""
    if look not in boxes:
        art = rend.art(look)
        rects = [fr.get_bounding_rect() for a in ("attack", "walk") for fr in art.frames[a]]
        box = rects[0].unionall(rects[1:])
        boxes[look] = box.clip(pygame.Rect(0, 0, art.w, art.h))
    return boxes[look]


def info_wrap(text: str, y0: int, preview_bottom: int, narrow: int, wide: int = INFO_WRAP) -> List[str]:
    """Word wrap where lines beside the preview are shorter; continuation lines indented."""
    import re
    text = re.sub(r" (\S{1,2})(?= |$)", "\u00a0\\1", text)   # "2.5 С": a short tail never starts a line
    words, lines, cur, y = text.split(" "), [], "", y0
    for wd in words:
        limit = narrow if y < preview_bottom else wide
        cand = (cur + " " + wd) if cur else (("  " + wd) if lines else wd)
        if len(cand) > limit and cur:
            lines.append(cur)
            y += INFO_LINE
            cur = "  " + wd
        else:
            cur = cand
    if cur:
        lines.append(cur)
    return [ln.replace("\u00a0", " ") for ln in lines]


def draw_unit_info(s: pygame.Surface, rend, f, key: str, x: int, y: int, w: int, h: int, active: int, time: float,
                   boxes: dict) -> Tuple[int, int]:
    """Name, stats, price, an animated preview and the traits of a unit class in the box (x, y, w, h)."""
    u = ROSTER[key]
    from .mapview import text_width
    big = text_width(u.name) * 2 <= w - 70                # beside the preview
    f.draw(s, u.name, x + 6, y + 4 if big else y + 7, "#fee761", scale=2 if big else 1)
    f.draw(s, f"{u.role}   {TIER_NAMES[u.tier]}", x + 6, y + 18, "#8b9bb4")
    lo, hi = u.damage
    dtype = {"physical": "", "magic": " МАГ", "holy": " СВЯТ"}[u.damage_type]
    f.draw(s, f"HP {u.hp}   УРОН {lo}-{hi}{dtype}   ДАЛЬН {int(u.attack_range)}", x + 6, y + 26, "#c0cbdc")
    extra = f"   УКЛОН {int(u.dodge * 100)}%" if u.dodge else ""
    f.draw(s, f"БРОНЯ {int(u.armor * 100)}%   МАГЗАЩ {int(u.resist * 100)}%   СКОР {int(u.speed)}{extra}",
           x + 6, y + 33, "#c0cbdc")
    f.draw(s, f"ЦЕНА {u.cost} ЗОЛОТА   СОДЕРЖАНИЕ {u.upkeep} ЗА ХОД", x + 6, y + 40, "#feae34")
    # animated preview (top right): the unit attacking, then walking
    look = f"{key}_{TEAMS[active].key}"
    art = rend.art(look)
    box = preview_box(rend, look, boxes)
    cyc = time % 3.0
    anim = "attack" if cyc < 1.4 else "walk"
    meta = rend.metas[look]["animations"][anim]["frames"]
    t = (cyc if anim == "attack" else cyc - 1.4) * 1000
    idx = len(meta) - 1
    for j, fr in enumerate(meta):
        if t < fr["duration"]:
            idx = j
            break
        t -= fr["duration"]
    img = art.frames[anim][idx].subsurface(box)
    if active == 1:
        img = pygame.transform.flip(img, True, False)
    px, py = x + w - box.w - 4, y + 3
    s.blit(img, (px, py))
    # perks (green), then flaws (red), then behavior (blue); one trait per entry,
    # text flows around the preview
    yy = y + 50
    for grp in ("perks", "flaws", "behavior"):
        bright, dim = INFO_COLORS[grp]
        for name, desc in getattr(u, grp):
            first = True
            for line in info_wrap(f"{name} - {desc}", yy, py + box.h + 1, (px - x - 8) // 4, (w - 10) // 4):
                if first:
                    head = f.render(name, bright)
                    s.blit(head, (x + 5, yy - 1))
                    if line[len(name):]:
                        s.blit(f.render(line[len(name):], dim), (x + 5 + head.get_width() - 2, yy - 1))
                    first = False
                else:
                    s.blit(f.render(line, dim), (x + 5, yy - 1))
                yy += INFO_LINE
        yy += 1
    return yy, y + h


class Button:
    def __init__(self, rect: Tuple[int, int, int, int], label: str, action: str, color: str = "#3a4466",
                 scale: int = 1):
        self.rect = pygame.Rect(rect)
        self.label = label
        self.action = action
        self.color = color
        self.scale = scale


class Menu:
    def __init__(self, renderer: Renderer, squads: Optional[List[List[str]]] = None):
        self.r = renderer
        self.font = renderer.font
        self.squads = squads or self._load() or [list(CLASSIC), list(CLASSIC)]
        self.active = 0
        self.hover: Optional[str] = None
        self.hover_slot: Optional[Tuple[int, int]] = None
        self.time = 0.0
        self.rng = random.Random()
        bx = 4
        self.buttons = [
            Button((bx, 236, 55, 14), "СЛУЧАЙНО", "rand0"), Button((bx + 61, 236, 55, 14), "ОЧИСТИТЬ", "clear0"),
            Button((W - 4 - 116, 236, 55, 14), "СЛУЧАЙНО", "rand1"), Button((W - 4 - 55, 236, 55, 14), "ОЧИСТИТЬ", "clear1"),
            Button((GRID_X + 70, 232, 92, 24), "В БОЙ!", "start", "#a22633", scale=2),
            Button((GRID_X, 238, 64, 14), "КЛАССИКА", "classic"),
            Button((GRID_X + 168, 238, 64, 14), "ЗЕРКАЛО", "mirror"),
        ]
        self.filter: Optional[str] = None
        self.scroll = 0
        self.by_faction = faction_units()
        from .factions import ALL_FACTIONS, EMBLEMS
        self.tab_factions = ALL_FACTIONS
        self.tab_icons = {}
        for f in ALL_FACTIONS:
            icon = pygame.Surface((TAB_W - 2, 11))
            icon.fill(_c(f.color))
            pygame.draw.rect(icon, _c(f.dark), icon.get_rect(), 1)
            for y, row in enumerate(EMBLEMS[f.emblem]):
                for x, ch in enumerate(row):
                    if ch == "#" and y < 9:
                        icon.set_at(((TAB_W - 2 - 9) // 2 + x, 1 + y), _c(f.metal))
            self.tab_icons[f.key] = icon
        self.dim = pygame.Surface((W, H), pygame.SRCALPHA)
        self.dim.fill((24, 20, 37, 170))

    # --- persistence --------------------------------------------------------------------
    def _load(self) -> Optional[List[List[str]]]:
        try:
            data = json.loads((cache_dir().parent / SAVE).read_text(encoding="utf-8"))
            sq = [[k for k in s if k in ROSTER][:SQUAD_MAX] for s in data["squads"]]
            return sq if len(sq) == 2 else None
        except Exception:
            return None

    def save(self) -> None:
        try:
            (cache_dir().parent / SAVE).write_text(json.dumps({"squads": self.squads}), encoding="utf-8")
        except OSError:
            pass

    # --- layout helpers -------------------------------------------------------------------
    def _card_rect(self, i: int) -> pygame.Rect:
        return pygame.Rect(GRID_X + (i % COLS) * CARD_W, GRID_Y + (i // COLS) * CARD_H, CARD_W - 2, CARD_H - 2)

    def keys(self) -> List[str]:
        return self.by_faction[self.filter] if self.filter else ALL

    def visible(self) -> List[str]:
        """Cards on screen: the filtered list, scrolled by whole rows."""
        ks = self.keys()
        rows = -(-len(ks) // COLS)
        self.scroll = max(0, min(self.scroll, rows - ROWS))
        return ks[self.scroll * COLS:(self.scroll + ROWS) * COLS]

    def _tab_rect(self, i: int) -> pygame.Rect:
        return pygame.Rect(GRID_X + i * TAB_W, TABS_Y, TAB_W - 2, 11)

    def _arrow_rect(self, d: int) -> pygame.Rect:
        return pygame.Rect(GRID_X + 10 * TAB_W + (0 if d < 0 else 14), TABS_Y, 12, 11)

    def _panel_x(self, team: int) -> int:
        return 4 if team == 0 else W - 4 - PANEL_W

    def _slot_rect(self, team: int, i: int) -> pygame.Rect:
        return pygame.Rect(self._panel_x(team) + 4, 40 + i * 27, PANEL_W - 8, 25)

    def _header_rect(self, team: int) -> pygame.Rect:
        return pygame.Rect(self._panel_x(team), 24, PANEL_W, 14)

    # --- input -----------------------------------------------------------------------------
    def handle(self, ev, mouse: Tuple[int, int]) -> Optional[str]:
        """Returns "start" / "back" (to the world map) when the menu is done."""
        if ev.type == pygame.KEYDOWN:
            if ev.key == pygame.K_ESCAPE:
                return "back"
            if ev.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
                return self._start()
            if ev.key == pygame.K_TAB:
                self.active = 1 - self.active
        if ev.type == pygame.MOUSEWHEEL:
            self.scroll -= ev.y
            return None
        if ev.type == pygame.MOUSEBUTTONDOWN and ev.button in (4, 5):   # older pygame wheel events
            self.scroll += 1 if ev.button == 5 else -1
            return None
        if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
            mx, my = mouse
            for i in range(10):
                if self._tab_rect(i).collidepoint(mx, my):
                    self.filter = None if i == 0 else self.tab_factions[i - 1].key
                    self.scroll = 0
                    return None
            for d in (-1, 1):
                if self._arrow_rect(d).collidepoint(mx, my):
                    self.scroll += d
                    return None
        if ev.type == pygame.MOUSEBUTTONDOWN and ev.button in (1, 3):
            mx, my = mouse
            for i, key in enumerate(self.visible()):
                if self._card_rect(i).collidepoint(mx, my):
                    team = self.active if ev.button == 1 else 1 - self.active
                    if len(self.squads[team]) < SQUAD_MAX:
                        self.squads[team].append(key)
                    return None
            for team in (0, 1):
                if self._header_rect(team).collidepoint(mx, my):
                    self.active = team
                    return None
                for i in range(len(self.squads[team])):
                    if self._slot_rect(team, i).collidepoint(mx, my):
                        del self.squads[team][i]
                        return None
                if pygame.Rect(self._panel_x(team), 24, PANEL_W, 208).collidepoint(mx, my):
                    self.active = team
            for b in self.buttons:
                if b.rect.collidepoint(mx, my):
                    return self._press(b.action)
        return None

    def _press(self, action: str) -> Optional[str]:
        if action == "start":
            return self._start()
        if action.startswith("rand"):
            t = int(action[-1])
            self.squads[t] = random_squad(self.rng)
        elif action.startswith("clear"):
            self.squads[int(action[-1])] = []
        elif action == "classic":
            self.squads = [list(CLASSIC), list(CLASSIC)]
        elif action == "mirror":
            self.squads[1 - self.active] = list(self.squads[self.active])
        return None

    def _start(self) -> Optional[str]:
        if self.squads[0] and self.squads[1]:
            self.save()
            return "start"
        return None

    def update(self, dt: float, mouse: Tuple[int, int]) -> None:
        self.time += dt
        mx, my = mouse
        self.hover = None
        self.hover_slot = None
        for i, key in enumerate(self.visible()):
            if self._card_rect(i).collidepoint(mx, my):
                self.hover = key
        for team in (0, 1):
            for i, key in enumerate(self.squads[team]):
                if self._slot_rect(team, i).collidepoint(mx, my):
                    self.hover = key
                    self.hover_slot = (team, i)

    # --- drawing ---------------------------------------------------------------------------
    def draw(self, s: pygame.Surface) -> None:
        f = self.font
        s.blit(self.r.bg, (0, 0))
        s.blit(self.dim, (0, 0))
        f.draw(s, "СБОР ОТРЯДОВ", W // 2, 6, "#fee761", scale=2, anchor="midtop")
        for team in (0, 1):
            self._draw_squad(s, team)
        self._draw_tabs(s)
        for i, key in enumerate(self.visible()):
            self._draw_card(s, i, key)
        self._draw_info(s)
        for b in self.buttons:
            disabled = b.action == "start" and not (self.squads[0] and self.squads[1])
            s.blit(self.r.panel(b.rect.w, b.rect.h, base="#3a4466" if disabled else b.color,
                                border="#8b9bb4"), b.rect.topleft)
            f.draw(s, b.label, b.rect.centerx, b.rect.centery, "#5a6988" if disabled else "#ffffff",
                   scale=b.scale, anchor="center")
        f.draw(s, "ЛКМ - В АКТИВНЫЙ ОТРЯД   ПКМ - В ДРУГОЙ   КЛИК ПО БОЙЦУ - УБРАТЬ   ESC - МЕНЮ", W // 2, H - 8,
               "#8b9bb4", anchor="midtop")

    def _draw_squad(self, s: pygame.Surface, team: int) -> None:
        tm = TEAMS[team]
        x = self._panel_x(team)
        active = team == self.active
        s.blit(self.r.panel(PANEL_W, 208, base="#181425", border=tm.light if active else tm.color), (x, 24))
        f = self.font
        f.draw(s, tm.name, x + 6, 28, tm.light, anchor="topleft")
        f.draw(s, f"{len(self.squads[team])}/{SQUAD_MAX}", x + PANEL_W - 6, 28, "#c0cbdc", anchor="topright")
        if active and int(self.time * 3) % 2 == 0:
            f.draw(s, "<", x + PANEL_W // 2 + (14 if team == 0 else -14), 28, "#fee761", anchor="midtop")
        for i in range(SQUAD_MAX):
            r = self._slot_rect(team, i)
            if i < len(self.squads[team]):
                key = self.squads[team][i]
                hot = self.hover_slot == (team, i)
                pygame.draw.rect(s, _c("#e43b44" if hot else tm.color), r, 1)
                pygame.draw.rect(s, (38, 43, 68), r.inflate(-2, -2))
                por = self.r.portrait(f"{key}_{tm.key}", flip=team == 1)
                s.blit(por, (r.x + 2, r.y + 2), area=pygame.Rect(0, 0, 18, 13))
                u = ROSTER[key]
                f.draw(s, u.name, r.x + 23, r.y + 4, "#ffffff" if not hot else "#f6757a")
                f.draw(s, "УБРАТЬ" if hot else u.role, r.x + 23, r.y + 13, "#8b9bb4")
            else:
                pygame.draw.rect(s, (58, 68, 102), r, 1)
                f.draw(s, "+ ПУСТО", r.centerx, r.centery, "#3a4466", anchor="center")

    def _draw_tabs(self, s: pygame.Surface) -> None:
        f = self.font
        for i in range(10):
            r = self._tab_rect(i)
            on = (i == 0 and self.filter is None) or (i > 0 and self.filter == self.tab_factions[i - 1].key)
            if i == 0:
                pygame.draw.rect(s, (58, 68, 102) if on else (38, 43, 68), r)
                f.draw(s, "ВСЕ", r.centerx, r.centery, "#ffffff" if on else "#8b9bb4", anchor="center")
            else:
                s.blit(self.tab_icons[self.tab_factions[i - 1].key], r.topleft)
            if on:
                pygame.draw.rect(s, _c("#fee761"), r.inflate(2, 2), 1)
        rows = -(-len(self.keys()) // COLS)
        for d in (-1, 1):
            r = self._arrow_rect(d)
            live = (d < 0 and self.scroll > 0) or (d > 0 and self.scroll + ROWS < rows)
            pygame.draw.rect(s, (58, 68, 102) if live else (38, 43, 68), r)
            col = (255, 255, 255) if live else (90, 105, 136)
            cx, cy = r.centerx, r.centery
            pts = [(cx - 3, cy + 1), (cx + 3, cy + 1), (cx, cy - 2)] if d < 0 else [(cx - 3, cy - 1), (cx + 3, cy - 1), (cx, cy + 2)]
            pygame.draw.polygon(s, col, pts)

    def _draw_card(self, s: pygame.Surface, i: int, key: str) -> None:
        r = self._card_rect(i)
        hot = self.hover == key and self.hover_slot is None
        tm = TEAMS[self.active]
        pygame.draw.rect(s, _c(tm.light if hot else "#5a6988"), r, 1)
        pygame.draw.rect(s, (38, 43, 68) if not hot else (58, 68, 102), r.inflate(-2, -2))
        por = self.r.portrait(f"{key}_{tm.key}", flip=self.active == 1)
        s.blit(por, (r.centerx - 9, r.y + 1), area=pygame.Rect(0, 0, 18, 13))
        name = ROSTER[key].short or ROSTER[key].name
        if len(name) > 8:
            name = name[:7] + "."
        self.font.draw(s, name, r.centerx, r.bottom - 8, "#ffffff" if hot else "#c0cbdc", anchor="midtop")

    # perk colors: (name, description)
    COLORS = {"perks": ("#a7f070", "#63c74d"), "flaws": ("#f6757a", "#e43b44"), "behavior": ("#73eff7", "#41a6f6")}
    WRAP = 53          # characters per line in the info panel
    LINE = 6           # px between lines

    def _draw_info(self, s: pygame.Surface) -> None:
        x, y = GRID_X, GRID_Y + ROWS * CARD_H + 1
        w, h = 6 * CARD_W - 2, 231 - y
        s.blit(self.r.panel(w, h, base="#181425", border="#5a6988"), (x, y))
        key = self.hover
        f = self.font
        if key is None:
            f.draw(s, "НАВЕДИ НА БОЙЦА, ЧТОБЫ УЗНАТЬ О НЁМ", x + w // 2, y + h // 2 - 3, "#5a6988", anchor="center")
            for i, (grp, label) in enumerate((("perks", "ПЕРК"), ("flaws", "НЕДОСТАТОК"), ("behavior", "ПОВЕДЕНИЕ"))):
                f.draw(s, label, x + w // 2 + (i - 1) * 64, y + h // 2 + 8, self.COLORS[grp][0], anchor="midtop")
            return
        self.text_bottom = draw_unit_info(s, self.r, f, key, x, y, w, h, self.active, self.time,
                                          self.__dict__.setdefault("_boxes", {}))

    def _wrap(self, text: str, y0: int, preview_bottom: int, narrow: int) -> List[str]:
        """Word wrap where lines beside the preview are shorter; continuation lines indented."""
        words, lines, cur, y = text.split(" "), [], "", y0
        for wd in words:
            limit = narrow if y < preview_bottom else self.WRAP
            cand = (cur + " " + wd) if cur else (("  " + wd) if lines else wd)
            if len(cand) > limit and cur:
                lines.append(cur)
                y += self.LINE
                cur = "  " + wd
            else:
                cur = cand
        if cur:
            lines.append(cur)
        return lines

    def _preview_box(self, look: str) -> pygame.Rect:
        """Union of the visible pixels of the attack and walk frames (stable crop, no jitter)."""
        cache = self.__dict__.setdefault("_boxes", {})
        if look not in cache:
            art = self.r.art(look)
            rects = [fr.get_bounding_rect() for a in ("attack", "walk") for fr in art.frames[a]]
            box = rects[0].unionall(rects[1:])
            cache[look] = box.clip(pygame.Rect(0, 0, art.w, art.h))
        return cache[look]
