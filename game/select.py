"""Faction selection: a hall of banners over the dimmed world map.

Nine banners hang from a beam: the eight playable realms and the Chronicler (spectator mode).
Hovering a banner lowers it, makes it glow and lights the realm's cities on the map behind;
the panel below tells its story, shows its leader (a painted portrait - click it for the
officer card) and what the realm starts with. A click takes the banner: the others fly up
and the screen flashes into the world map.
"""

from __future__ import annotations

import math
import random
from typing import List, Optional, Tuple

import pygame

from .campaign import Campaign, START_GOLD, DEFAULT_GOLD
from .factions import CITIES, CITY, EMBLEMS, FACTION, FACTIONS, Faction, cities_of, relation
from .mapview import _shade, load_map, shield_surface, wrap
from .officercard import OfficerCard
from .officers import OFFICERS
from .render import INK, Renderer, _c
from .sim import H, W

BANNER_W, BANNER_H = 40, 70
BEAM_Y = 38
STEP = 52
SPECTATOR = None

# the Chronicler's emblem: an open eye
_EYE = (".........",
        "..#####..",
        ".#.....#.",
        "#..###..#",
        "#.#####.#",
        "#..###..#",
        ".#.....#.",
        "..#####..",
        ".........")
_CHRONICLER = Faction("chronicler", "ЛЕТОПИСЕЦ", "ЛЕТОПИСЕЦ", "#3a4466", "#c0cbdc", "#262b44", "#e6dfd0", "eye",
                      "", "", "", "", (), "", False)
_SPECTATOR_LORE = ("Летописец не правит ни одним городом и не ведёт ни одного войска. Он смотрит, как восемь "
                   "держав и гоблинские орды делят материк, и записывает всё: войны, союзы, измены и подвиги. "
                   "Режим зрителя - игра идёт без тебя.")


def _banner_cloth(f: Faction, emblem: Tuple[str, ...]) -> pygame.Surface:
    """The banner without wind: cloth, trims, emblem and a swallowtail."""
    w, h = BANNER_W, BANNER_H
    s = pygame.Surface((w, h), pygame.SRCALPHA)
    main, shade, dark, metal = _c(f.color), _c(_shade(f.color)), _c(f.dark), _c(f.metal)
    notch = 12
    for y in range(h):
        cut = max(0, y - (h - notch))                       # the V of the swallowtail
        for x in range(w):
            if y > h - notch and abs(x - w / 2 + 0.5) < cut * 1.4:
                continue
            edge = x in (0, w - 1) or y == 0
            if edge:
                c = INK
            elif x in (1, w - 2) or y in (1, 2):
                c = dark
            elif y in (4, h - notch - 3) or x in (3, w - 4) and 4 <= y <= h - notch - 3:
                c = metal
            else:
                c = main if x < w * 0.62 else shade
            s.set_at((x, y), c)
        if y > h - notch:                                    # outline the tail cut
            for x in range(w):
                if s.get_at((x, y)).a and (x == 0 or x == w - 1 or not s.get_at((x - 1, y)).a
                                           or not s.get_at((x + 1, y)).a):
                    s.set_at((x, y), INK)
    for x in range(w):                                       # bottom outline of the tails
        if s.get_at((x, h - 1)).a:
            s.set_at((x, h - 1), INK)
    em = pygame.Surface((9, 9), pygame.SRCALPHA)
    for y, row in enumerate(emblem):
        for x, ch in enumerate(row):
            if ch == "#":
                em.set_at((x, y), metal)
    em = pygame.transform.scale(em, (27, 27))
    shadow = pygame.transform.scale(em, (27, 27))
    shadow.fill((0, 0, 0, 120), special_flags=pygame.BLEND_RGBA_MULT)
    s.blit(shadow, ((w - 27) // 2 + 1, 13))
    s.blit(em, ((w - 27) // 2, 12))
    return s


class SelectScreen:
    def __init__(self, renderer: Renderer, progress=None):
        self.r = renderer
        self.font = renderer.font
        world = load_map(progress)
        k = 3
        arr = pygame.surfarray.array3d(world)
        import numpy as np
        w, h = arr.shape[0] // k, arr.shape[1] // k
        a = arr[:w * k, :h * k].reshape(w, k, h, k, 3).mean(axis=(1, 3)).astype(np.uint8)
        self.bg = pygame.surfarray.make_surface(a).convert()
        self.bg_k = k
        self.sea = self.bg.get_at((2, self.bg.get_height() - 3))
        eye = pygame.Surface((9, 9), pygame.SRCALPHA)
        for y, row in enumerate(_EYE):
            for x, ch in enumerate(row):
                eye.set_at((x, y), _c("#e6dfd0") if ch == "#" else _c("#262b44"))
        self.eye = pygame.transform.scale(eye, (54, 54))
        self.shade = pygame.Surface((W, H), pygame.SRCALPHA)
        self.shade.fill((16, 12, 26, 165))
        self.choices: List[Optional[Faction]] = list(FACTIONS) + [SPECTATOR]
        self.cloth = [_banner_cloth(f, EMBLEMS[f.emblem]) for f in FACTIONS] + [_banner_cloth(_CHRONICLER, _EYE)]
        self.preview = Campaign(None)
        self.cards = OfficerCard(renderer, self.preview)
        self.shields = {f.key: shield_surface(f, 2) for f in FACTIONS}
        self.focus = 0
        self.hover: Optional[int] = None
        self.drop = [0.0] * len(self.choices)
        self.time = 0.0
        self.chosen: Optional[int] = None
        self.chosen_at = 0.0
        self.result: Optional[Tuple[str, Optional[str]]] = None     # ("play", faction key or None)
        self._mouse = (0, 0)
        self.cam = list(self._cam_target())
        rng = random.Random(7)
        self.embers = [[rng.uniform(0, W), rng.uniform(0, H), rng.uniform(6, 18), rng.uniform(0, 6.3)]
                       for _ in range(46)]

    # --- geometry -----------------------------------------------------------------------------
    def _banner_rect(self, i: int) -> pygame.Rect:
        x0 = (W - STEP * (len(self.choices) - 1) - BANNER_W) // 2
        return pygame.Rect(x0 + i * STEP, BEAM_Y + 3 + int(self.drop[i]), BANNER_W, BANNER_H)

    def _banner_at(self, mx: int, my: int) -> Optional[int]:
        for i in range(len(self.choices)):
            if self._banner_rect(i).inflate(8, 14).collidepoint(mx, my):
                return i
        return None

    def _leader_rect(self) -> pygame.Rect:
        return pygame.Rect(14, 158, 52, 63)

    def _cam_target(self) -> Tuple[float, float]:
        """The backdrop swings to the focused realm: its capital lands in the gap under the banners."""
        bw, bh = self.bg.get_size()
        c = self.choices[self.focus]
        if c is None:
            x = (math.sin(self.time * 0.07) * 0.5 + 0.5) * (bw - W)
            y = (bh - H) / 2
        else:
            cap = CITY[c.capital]
            x, y = cap.x / self.bg_k - W / 2, cap.y / self.bg_k - 132
        # past the map's edge lies open sea, so a southern capital can still come into view
        return max(-40.0, min(bw - W + 40, x)), max(-40.0, min(bh - 150, y))

    # --- input ---------------------------------------------------------------------------------
    def handle(self, ev, mouse: Tuple[int, int]) -> Optional[str]:
        if self.chosen is not None:
            return None
        if self.cards.handle(ev, mouse):
            return None
        mx, my = mouse
        n = len(self.choices)
        if ev.type == pygame.KEYDOWN:
            if ev.key == pygame.K_ESCAPE:
                return "quit"
            if ev.key in (pygame.K_LEFT, pygame.K_a):
                self.focus = (self.focus - 1) % n
            elif ev.key in (pygame.K_RIGHT, pygame.K_d):
                self.focus = (self.focus + 1) % n
            elif ev.key in (pygame.K_RETURN, pygame.K_SPACE):
                self._choose(self.focus)
        elif ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
            i = self._banner_at(mx, my)
            if i is not None:
                self._choose(i)
        return None

    def _choose(self, i: int) -> None:
        self.chosen, self.chosen_at, self.focus = i, self.time, i

    def update(self, dt: float, mouse: Tuple[int, int]) -> None:
        self.time += dt
        self._mouse = mouse
        if self.chosen is None and not self.cards.open:
            self.hover = self._banner_at(*mouse)
            if self.hover is not None:
                self.focus = self.hover
        for i in range(len(self.choices)):
            if self.chosen is not None:
                target = 10.0 if i == self.chosen else -120.0
            else:
                target = 9.0 if i == self.focus else 0.0
            self.drop[i] += (target - self.drop[i]) * min(1.0, dt * (5 if self.chosen is not None else 12))
        tx, ty = self._cam_target()
        self.cam[0] += (tx - self.cam[0]) * min(1.0, dt * 3)
        self.cam[1] += (ty - self.cam[1]) * min(1.0, dt * 3)
        for e in self.embers:
            e[1] -= e[2] * dt
            e[0] += math.sin(self.time * 1.3 + e[3]) * 6 * dt
            if e[1] < -4:
                e[1] = H + 2
                e[0] = (e[0] * 7.3 + 91) % W
        if self.chosen is not None and self.time - self.chosen_at > 1.1:
            c = self.choices[self.chosen]
            self.result = ("play", c.key if c else None)

    # --- drawing -------------------------------------------------------------------------------
    def draw(self, s: pygame.Surface) -> None:
        self.cards.begin(self._mouse)
        cx, cy = int(self.cam[0]), int(self.cam[1])
        s.fill(self.sea)
        s.blit(self.bg, (-cx, -cy))
        s.blit(self.shade, (0, 0))
        self._realm_glow(s, cx, cy)
        self._embers(s)
        # title
        self.font.draw(s, "ИЗБЕРИ СВОЁ ЗНАМЯ", W // 2, 6, "#fee761", scale=2, anchor="midtop")
        self.font.draw(s, "ВОСЕМЬ ДЕРЖАВ ДЕЛЯТ МАТЕРИК. ЗА КОГО ПОЙДЁШЬ ТЫ?", W // 2, 24, "#c0cbdc", anchor="midtop")
        self._beam(s)
        for i in range(len(self.choices)):
            self._banner(s, i)
        self._panel(s)
        if self.chosen is not None:                         # the flash into the world map
            k = (self.time - self.chosen_at) / 1.1
            a = int(255 * max(0.0, min(1.0, (k - 0.45) / 0.55)))
            if a:
                flash = pygame.Surface((W, H))
                flash.fill((255, 244, 214))
                flash.set_alpha(a)
                s.blit(flash, (0, 0))
        self.cards.draw(s)

    def _realm_glow(self, s: pygame.Surface, pan: int, oy: int) -> None:
        c = self.choices[self.focus]
        pulse = 0.5 + 0.5 * math.sin(self.time * 4)
        for city in CITIES:
            x = int(city.x / self.bg_k - pan)
            y = int(city.y / self.bg_k - oy)
            if not (0 <= x < W and 0 <= y < H):
                continue
            f = FACTION[city.faction]
            mine = c is None or city.faction == c.key
            if mine and city.faction != "goblin":
                r = 3 + int(pulse * 2) + (2 if c and city.key == c.capital else 0)
                pygame.draw.circle(s, _c(f.light), (x, y), r, 1)
                pygame.draw.rect(s, INK, (x - 2, y - 2, 5, 5))
                pygame.draw.rect(s, _c(f.color), (x - 1, y - 1, 3, 3))
                if c is not None and city.key == c.capital:
                    self.font.draw(s, city.name, x, y + r + 2, f.light, anchor="midtop")
            else:
                s.set_at((x, y), _c(f.dark))

    def _embers(self, s: pygame.Surface) -> None:
        for x, y, v, ph in self.embers:
            k = 0.5 + 0.5 * math.sin(self.time * 5 + ph)
            col = (255, int(140 + 90 * k), int(40 + 40 * k))
            s.set_at((int(x), int(y)), col)
            if v > 13:
                s.set_at((int(x), int(y) + 1), (180, 70, 30))

    def _beam(self, s: pygame.Surface) -> None:
        x0 = self._banner_rect(0).x - 14
        x1 = self._banner_rect(len(self.choices) - 1).right + 14
        y = BEAM_Y
        pygame.draw.rect(s, INK, (x0 - 1, y - 1, x1 - x0 + 2, 6))
        pygame.draw.rect(s, (122, 72, 65), (x0, y, x1 - x0, 4))
        pygame.draw.line(s, (190, 120, 80), (x0, y), (x1 - 1, y))
        pygame.draw.line(s, (62, 39, 49), (x0, y + 3), (x1 - 1, y + 3))
        for x in (x0 - 3, x1 - 2):                          # gilded finials
            pygame.draw.rect(s, INK, (x - 1, y - 3, 7, 10))
            pygame.draw.rect(s, (254, 174, 52), (x, y - 2, 5, 8))
            pygame.draw.rect(s, (254, 231, 97), (x, y - 2, 2, 3))

    def _banner(self, s: pygame.Surface, i: int) -> None:
        rect = self._banner_rect(i)
        if rect.bottom < 0:
            return
        f = self.choices[i] or _CHRONICLER
        cloth = self.cloth[i]
        focus = i == self.focus
        t = self.time
        # wind: rows sway more the further they hang from the beam
        wind = 1.0 + (1.2 if focus else 0.0)
        if focus:                                           # glow behind the chosen cloth
            glow = pygame.Surface((rect.w + 16, rect.h + 16), pygame.SRCALPHA)
            a = 70 + int(40 * math.sin(t * 5))
            pygame.draw.rect(glow, (*_c(f.light), a), glow.get_rect(), border_radius=8)
            pygame.draw.rect(glow, (*_c(f.light), a // 2), glow.get_rect().inflate(-4, -4), border_radius=6)
            s.blit(glow, (rect.x - 8, rect.y - 8))
        for y in range(rect.h):
            dx = round(math.sin(t * 2.2 + i * 1.7 + y * 0.09) * wind * (y / rect.h) ** 1.3 * 1.6)
            s.blit(cloth, (rect.x + dx, rect.y + y), area=pygame.Rect(0, y, rect.w, 1))
        # rings on the beam
        for x in (rect.x + 5, rect.right - 7):
            pygame.draw.rect(s, INK, (x - 1, BEAM_Y - 2, 4, rect.y - BEAM_Y + 4))
            pygame.draw.rect(s, (192, 203, 220), (x, BEAM_Y - 1, 2, rect.y - BEAM_Y + 2))
        if not focus and self.chosen is None:
            veil = pygame.Surface(rect.size, pygame.SRCALPHA)
            veil.fill((16, 12, 26, 70))
            s.blit(veil, rect.topleft)
        name = f.short if f is not _CHRONICLER else "ЗРИТЕЛЬ"
        self.font.draw(s, name, rect.centerx, rect.bottom + 3, f.light if focus else "#8b9bb4", anchor="midtop")

    def _panel(self, s: pygame.Surface) -> None:
        r = pygame.Rect(6, 152, W - 12, H - 158)
        c = self.choices[self.focus]
        f = c or _CHRONICLER
        s.blit(self.r.panel(r.w, r.h, base="#181425", border=f.color), r.topleft)
        font = self.font
        lr = self._leader_rect()
        x = lr.right + 8
        if c is None:
            pygame.draw.rect(s, _c("#c0cbdc"), lr.inflate(2, 2), 1)
            s.blit(self.eye, (lr.x - 1, lr.y + 4))
            font.draw(s, "РЕЖИМ ЗРИТЕЛЯ", x, r.y + 6, "#ffffff", scale=2)
            y = r.y + 22
            for line in wrap(_SPECTATOR_LORE, 250):
                font.draw(s, line, x, y, "#c0cbdc")
                y += 7
            col = r.x + 340
            font.draw(s, "ТЫ УВИДИШЬ:", col, r.y + 8, "#fee761")
            for k, line in enumerate(("ВСЕ ГОРОДА И ФРАКЦИИ", "ВСЕХ ОФИЦЕРОВ", "ДИПЛОМАТИЮ И ВОЙНЫ",
                                      "БЕЗ КНОПОК УПРАВЛЕНИЯ")):
                font.draw(s, line, col, r.y + 18 + k * 9, "#a7f070" if k < 3 else "#f6757a")
        else:
            leader = OFFICERS[c.key][0]
            self.cards.face(s, lr, leader.key, frame="#f2c84b")
            s.blit(self.shields[c.key], (x, r.y + 5))
            font.draw(s, c.name, x + 36, r.y + 6, c.light, scale=2 if font.render(c.name, "#fff").get_width() * 2 <= 252
                      else 1)
            self.cards.name(s, leader.key, x + 36, r.y + 23, "#ffffff")
            font.draw(s, c.leader_title, x + 36 + font.render(leader.name, "#fff").get_width() + 4, r.y + 23,
                      "#8b9bb4")
            y = r.y + 41
            for line in wrap(c.lore, 258):
                font.draw(s, line, x, y, "#c0cbdc")
                y += 7
            col = r.x + 340
            gold = START_GOLD.get(c.key, DEFAULT_GOLD)
            rows = [("СТОЛИЦА", CITY[c.capital].name), ("ГОРОДОВ", str(len(cities_of(c.key)))),
                    ("ОФИЦЕРОВ", str(len(OFFICERS[c.key]))), ("ЗОЛОТО", str(gold))]
            others = [o for o in FACTIONS if o.key != c.key]
            friend = max(others, key=lambda o: relation(c.key, o.key)[0])
            foe = min(others, key=lambda o: relation(c.key, o.key)[0])
            rows += [("ДРУГ", friend.short), ("ВРАГ", foe.short)]
            why = None
            for k, (label, value) in enumerate(rows):
                yy = r.y + 6 + k * 9
                if label in ("ДРУГ", "ВРАГ") and pygame.Rect(col, yy - 1, r.right - 8 - col, 9).collidepoint(self._mouse):
                    other = friend if label == "ДРУГ" else foe     # the old memories of the peoples, as the campaign starts
                    v, reason = relation(c.key, other.key)
                    why = (f"{c.short} И {other.short}: {v}", reason, "#a7f070" if label == "ДРУГ" else "#f6757a")
                    pygame.draw.line(s, _c("#5a6988"), (col, yy + 7), (r.right - 8, yy + 7))
                font.draw(s, label, col, yy, "#8b9bb4")
                vc = "#feae34" if label == "ЗОЛОТО" else "#a7f070" if label == "ДРУГ" else \
                    "#f6757a" if label == "ВРАГ" else "#ffffff"
                font.draw(s, value, r.right - 8, yy, vc, anchor="topright")
            y = r.y + 60
            from .cards import AP, AP_BONUS, CARDS, FACTION_CARD
            ap = AP + AP_BONUS.get(c.key, 0)
            font.draw(s, "ОД ЗА ХОД", col, y, "#8b9bb4")
            font.draw(s, f"{ap}" + (" (ОРДА: +1)" if ap > AP else ""), r.right - 8, y, "#41a6f6", anchor="topright")
            font.draw(s, "КАРТА ФРАКЦИИ:", col, y + 10, "#fee761")
            card = CARDS[FACTION_CARD[c.key]]
            chip = font.render(card.name, c.light)
            s.blit(chip, (col, y + 19))
            if pygame.Rect(col, y + 19, chip.get_width(), 8).collidepoint(self._mouse):
                from .cardui import CARD_H, CARD_W, CardArt
                if not hasattr(self, "art"):
                    self.art = CardArt(self.r)
                self.cards.cover()
                s.blit(self.art.full(card.key, "ЛИДЕР", c.key), (col - CARD_W - 8, r.y - CARD_H + 60))
            if why:                                        # the reason, in a box above the panel
                lines = wrap(why[1], 250)
                h = 14 + 7 * len(lines)                    # right by the hovered row, over the lore
                box = pygame.Rect(max(2, col - 262), max(2, self._mouse[1] - h - 4), 258, h)
                s.blit(self.r.panel(box.w, box.h, base="#181425", border=why[2]), box.topleft)
                font.draw(s, why[0], box.x + 4, box.y + 3, why[2])
                for i, line in enumerate(lines):
                    font.draw(s, line, box.x + 4, box.y + 11 + i * 7, "#e6dfd0")
        blink = int(self.time * 2) % 2 == 0
        who = ": " + f.short if c else " В РЕЖИМЕ ЗРИТЕЛЯ"
        hint = f"КЛИК ПО ЗНАМЕНИ ИЛИ ENTER - НАЧАТЬ{who}" if self.chosen is None else "В ПУТЬ!"
        font.draw(s, hint, r.centerx, r.bottom - 10, "#fee761" if blink or self.chosen is not None else "#feae34",
                  anchor="midtop")
