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
from .units import ALL, CLASSIC, ROSTER, SQUAD_MAX, TEAMS

PANEL_W = 116
GRID_X, GRID_Y = 124, 26
CARD_W, CARD_H = 38, 24
COLS = 6
SAVE = "squads.json"


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
        if ev.type == pygame.MOUSEBUTTONDOWN and ev.button in (1, 3):
            mx, my = mouse
            for i, key in enumerate(ALL):
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
        for i, key in enumerate(ALL):
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
        for i, key in enumerate(ALL):
            self._draw_card(s, i, key)
        self._draw_info(s)
        for b in self.buttons:
            disabled = b.action == "start" and not (self.squads[0] and self.squads[1])
            s.blit(self.r.panel(b.rect.w, b.rect.h, base="#3a4466" if disabled else b.color,
                                border="#8b9bb4"), b.rect.topleft)
            f.draw(s, b.label, b.rect.centerx, b.rect.centery, "#5a6988" if disabled else "#ffffff",
                   scale=b.scale, anchor="center")
        f.draw(s, "ЛКМ - В АКТИВНЫЙ ОТРЯД   ПКМ - В ДРУГОЙ   КЛИК ПО БОЙЦУ - УБРАТЬ   ESC - КАРТА", W // 2, H - 8,
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
        rows = -(-len(ALL) // COLS)
        x, y = GRID_X, GRID_Y + rows * CARD_H + 1
        w, h = 6 * CARD_W - 2, 231 - y
        s.blit(self.r.panel(w, h, base="#181425", border="#5a6988"), (x, y))
        key = self.hover
        f = self.font
        if key is None:
            f.draw(s, "НАВЕДИ НА БОЙЦА, ЧТОБЫ УЗНАТЬ О НЁМ", x + w // 2, y + h // 2 - 3, "#5a6988", anchor="center")
            for i, (grp, label) in enumerate((("perks", "ПЕРК"), ("flaws", "НЕДОСТАТОК"), ("behavior", "ПОВЕДЕНИЕ"))):
                f.draw(s, label, x + w // 2 + (i - 1) * 64, y + h // 2 + 8, self.COLORS[grp][0], anchor="midtop")
            return
        u = ROSTER[key]
        f.draw(s, u.name, x + 6, y + 4, "#fee761", scale=2 if len(u.name) <= 13 else 1)
        f.draw(s, u.role, x + 6, y + 18, "#8b9bb4")
        lo, hi = u.damage
        dtype = {"physical": "", "magic": " МАГ", "holy": " СВЯТ"}[u.damage_type]
        f.draw(s, f"HP {u.hp}   УРОН {lo}-{hi}{dtype}   ДАЛЬН {int(u.attack_range)}", x + 6, y + 26, "#c0cbdc")
        extra = f"   УКЛОН {int(u.dodge * 100)}%" if u.dodge else ""
        f.draw(s, f"БРОНЯ {int(u.armor * 100)}%   МАГЗАЩ {int(u.resist * 100)}%   СКОР {int(u.speed)}{extra}",
               x + 6, y + 33, "#c0cbdc")
        # animated preview (top right): the unit attacking, then walking
        look = f"{key}_{TEAMS[self.active].key}"
        art = self.r.art(look)
        box = self._preview_box(look)
        cyc = self.time % 3.0
        anim = "attack" if cyc < 1.4 else "walk"
        meta = self.r.metas[look]["animations"][anim]["frames"]
        t = (cyc if anim == "attack" else cyc - 1.4) * 1000
        idx = len(meta) - 1
        for j, fr in enumerate(meta):
            if t < fr["duration"]:
                idx = j
                break
            t -= fr["duration"]
        img = art.frames[anim][idx].subsurface(box)
        if self.active == 1:
            img = pygame.transform.flip(img, True, False)
        px, py = x + w - box.w - 4, y + 3
        s.blit(img, (px, py))
        # perks (green), then flaws (red), then behavior (blue); one trait per entry,
        # text flows around the preview
        yy = y + 43
        for grp in ("perks", "flaws", "behavior"):
            bright, dim = self.COLORS[grp]
            for name, desc in getattr(u, grp):
                first = True
                for line in self._wrap(f"{name} - {desc}", yy, py + box.h + 1, (px - x - 8) // 4):
                    if first:
                        head = f.render(name, bright)
                        s.blit(head, (x + 5, yy - 1))
                        if line[len(name):]:
                            s.blit(f.render(line[len(name):], dim), (x + 5 + head.get_width() - 2, yy - 1))
                        first = False
                    else:
                        s.blit(f.render(line, dim), (x + 5, yy - 1))
                    yy += self.LINE
            yy += 1
        self.text_bottom = (yy, y + h)

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
