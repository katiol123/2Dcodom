"""The title screen: НАЧАТЬ (a new campaign), ПРОДОЛЖИТЬ (the autosave) and БЫСТРЫЙ БОЙ (squad builder).

The world map drifts slowly behind a dark veil, embers rise, the eight realms' shields stand in a row.
``result`` becomes "new" / "continue" / "battle" once a button is taken; ESC quits.
"""

from __future__ import annotations

import math
import random
from typing import List, Optional, Tuple

import pygame

from . import saves
from .factions import FACTIONS
from .mapview import load_map, shield_surface
from .render import INK, Renderer, _c
from .sim import H, W

BTN_W, BTN_H, BTN_GAP = 132, 19, 13


class TitleScreen:
    def __init__(self, renderer: Renderer, progress=None):
        self.r = renderer
        self.font = renderer.font
        world = load_map(progress)
        arr = pygame.surfarray.array3d(world)[::2, ::2]     # nearest pixels: the backdrop stays crisp
        self.bg = pygame.surfarray.make_surface(arr).convert()
        self.shade = pygame.Surface((W, H), pygame.SRCALPHA)
        self.shade.fill((16, 12, 26, 170))
        self.shields = [shield_surface(f, 2) for f in FACTIONS]
        self.saved = saves.load()                       # the campaign ПРОДОЛЖИТЬ resumes
        self.items: List[Tuple[str, str, bool]] = [
            ("НАЧАТЬ", "new", True),
            ("ПРОДОЛЖИТЬ", "continue", self.saved is not None),
            ("БЫСТРЫЙ БОЙ", "battle", True),
        ]
        self.focus = 1 if self.saved is not None else 0
        self.hover: Optional[int] = None
        self.time = 0.0
        self.result: Optional[str] = None
        self.picked: Optional[int] = None
        self.confirm = False                              # НАЧАТЬ over a saved campaign asks first
        self.picked_at = 0.0
        rng = random.Random(11)
        self.embers = [[rng.uniform(0, W), rng.uniform(0, H), rng.uniform(6, 18), rng.uniform(0, 6.3)]
                       for _ in range(54)]

    def _rect(self, i: int) -> pygame.Rect:
        y0 = 112
        return pygame.Rect((W - BTN_W) // 2, y0 + i * (BTN_H + BTN_GAP) + (8 if i >= 2 else 0), BTN_W, BTN_H)

    def _yes_no(self) -> Tuple[pygame.Rect, pygame.Rect]:
        return pygame.Rect(W // 2 - 64, 172, 56, 15), pygame.Rect(W // 2 + 8, 172, 56, 15)

    def _at(self, mx: int, my: int) -> Optional[int]:
        for i in range(len(self.items)):
            if self._rect(i).collidepoint(mx, my):
                return i
        return None

    # --- input ---------------------------------------------------------------------------------
    def handle(self, ev, mouse: Tuple[int, int]) -> Optional[str]:
        if self.picked is not None:
            return None
        n = len(self.items)
        if self.confirm:
            yes, no = self._yes_no()
            if ev.type == pygame.KEYDOWN and ev.key in (pygame.K_RETURN, pygame.K_y):
                self._pick(0, sure=True)
            elif ev.type == pygame.KEYDOWN and ev.key in (pygame.K_ESCAPE, pygame.K_n):
                self.confirm = False
            elif ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
                if yes.collidepoint(mouse):
                    self._pick(0, sure=True)
                elif no.collidepoint(mouse):
                    self.confirm = False
            return None
        if ev.type == pygame.KEYDOWN:
            if ev.key == pygame.K_ESCAPE:
                return "quit"
            if ev.key in (pygame.K_UP, pygame.K_w, pygame.K_DOWN, pygame.K_s):
                step = -1 if ev.key in (pygame.K_UP, pygame.K_w) else 1
                for _ in range(n):
                    self.focus = (self.focus + step) % n
                    if self.items[self.focus][2]:
                        break
            elif ev.key in (pygame.K_RETURN, pygame.K_SPACE):
                self._pick(self.focus)
        elif ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
            i = self._at(*mouse)
            if i is not None:
                self._pick(i)
        return None

    def _pick(self, i: int, sure: bool = False) -> None:
        if not self.items[i][2]:
            return
        from .audio import ui
        ui("click")
        if i == 0 and self.saved is not None and not sure:
            self.confirm = True
            return
        self.confirm = False
        self.picked, self.picked_at, self.focus = i, self.time, i

    def update(self, dt: float, mouse: Tuple[int, int]) -> None:
        self.time += dt
        if self.picked is None and not self.confirm:
            self.hover = self._at(*mouse)
            if self.hover is not None and self.items[self.hover][2]:
                self.focus = self.hover
        elif self.time - self.picked_at > 0.35:
            self.result = self.items[self.picked][1]
        for e in self.embers:
            e[1] -= e[2] * dt
            e[0] += math.sin(self.time * 1.3 + e[3]) * 6 * dt
            if e[1] < -4:
                e[1] = H + 2
                e[0] = (e[0] * 7.3 + 91) % W

    # --- drawing -------------------------------------------------------------------------------
    def draw(self, s: pygame.Surface) -> None:
        bw, bh = self.bg.get_size()
        t = self.time * 0.035
        cx = (math.sin(t) * 0.5 + 0.5) * (bw - W)
        cy = (math.sin(t * 0.7 + 1.0) * 0.5 + 0.5) * (bh - H)
        s.blit(self.bg, (-int(cx), -int(cy)))
        s.blit(self.shade, (0, 0))
        for x, y, v, ph in self.embers:
            k = 0.5 + 0.5 * math.sin(self.time * 5 + ph)
            s.set_at((int(x), int(y)), (255, int(140 + 90 * k), int(40 + 40 * k)))
            if v > 13:
                s.set_at((int(x), int(y) + 1), (180, 70, 30))
        # the title
        glow = 0.5 + 0.5 * math.sin(self.time * 1.6)
        self.font.draw(s, "ВОСЕМЬ КОРОН", W // 2, 34, "#fee761", scale=4, anchor="midtop")
        self.font.draw(s, "ХРОНИКА ВОЙНЫ ЗА МАТЕРИК", W // 2, 70, "#c0cbdc", scale=2, anchor="midtop")
        line = _c("#feae34")
        half = 90 + int(6 * glow)
        pygame.draw.line(s, INK, (W // 2 - half, 91), (W // 2 + half, 91), 3)
        pygame.draw.line(s, line, (W // 2 - half + 1, 91), (W // 2 + half - 1, 91))
        pygame.draw.rect(s, INK, (W // 2 - 3, 88, 7, 7))
        pygame.draw.rect(s, line, (W // 2 - 2, 89, 5, 5))
        # the shields of the realms
        sw = self.shields[0].get_width()
        gap = 10
        x0 = (W - len(self.shields) * (sw + gap) + gap) // 2
        for i, sh in enumerate(self.shields):
            bob = int(round(math.sin(self.time * 1.2 + i * 0.8) * 1.5))
            s.blit(sh, (x0 + i * (sw + gap), H - sh.get_height() - 15 + bob))
        # the buttons
        for i, (label, _, ok) in enumerate(self.items):
            self._button(s, i, label, ok)
        if self.saved is not None:
            r = self._rect(1)
            self.font.draw(s, saves.describe(self.saved), W // 2, r.bottom + 1, "#8b9bb4", anchor="midtop")
        self.font.draw(s, "ESC - ВЫХОД   F - ВО ВЕСЬ ЭКРАН", W // 2, H - 9, "#5a6988", anchor="midtop")
        if self.confirm:
            self._confirm(s)
        if self.picked is not None:                          # a short fade before the next screen
            a = int(255 * min(1.0, (self.time - self.picked_at) / 0.35))
            veil = pygame.Surface((W, H))
            veil.fill((16, 12, 26))
            veil.set_alpha(a)
            s.blit(veil, (0, 0))

    def _button(self, s: pygame.Surface, i: int, label: str, ok: bool) -> None:
        r = self._rect(i)
        on = ok and i == self.focus
        base = "#a22633" if i == 2 else "#124e89" if i == 1 else "#3e8948"
        if not ok:
            base = "#3a4466"
        pygame.draw.rect(s, INK, r.inflate(2, 2))
        pygame.draw.rect(s, _c(base), r)
        pygame.draw.line(s, _c("#ffffff" if on else "#8b9bb4"), r.topleft, (r.right - 1, r.top))
        pygame.draw.line(s, (0, 0, 0), (r.left, r.bottom - 1), (r.right - 1, r.bottom - 1))
        if on:
            pulse = 0.5 + 0.5 * math.sin(self.time * 6)
            gold = _c("#fee761")
            pygame.draw.rect(s, gold, r.inflate(4 + int(2 * pulse), 4 + int(2 * pulse)), 1)
            for side in (-1, 1):                             # little arrowheads point at the choice
                x = r.centerx + side * (r.w // 2 + 8 + int(2 * pulse))
                pts = [(x, r.centery), (x + side * 4, r.centery - 4), (x + side * 4, r.centery + 4)]
                pygame.draw.polygon(s, gold, pts)
        self.font.draw(s, label, r.centerx, r.centery + 1, "#ffffff" if ok else "#5a6988", scale=2,
                       anchor="center")

    def _confirm(self, s: pygame.Surface) -> None:
        s.blit(self.shade, (0, 0))
        box = pygame.Rect(W // 2 - 120, 120, 240, 74)
        s.blit(self.r.panel(box.w, box.h, base="#181425", border="#e43b44"), box.topleft)
        self.font.draw(s, "НАЧАТЬ НОВУЮ КАМПАНИЮ?", box.centerx, box.y + 7, "#fee761", scale=2, anchor="midtop")
        self.font.draw(s, f"СОХРАНЁННАЯ ({saves.describe(self.saved)})", box.centerx, box.y + 26, "#c0cbdc",
                       anchor="midtop")
        self.font.draw(s, "БУДЕТ ПЕРЕЗАПИСАНА", box.centerx, box.y + 34, "#f6757a", anchor="midtop")
        for rect, label, col in zip(self._yes_no(), ("ДА", "НЕТ"), ("#a22633", "#3a4466")):
            pygame.draw.rect(s, INK, rect.inflate(2, 2))
            pygame.draw.rect(s, _c(col), rect)
            pygame.draw.line(s, _c("#8b9bb4"), rect.topleft, (rect.right - 1, rect.top))
            self.font.draw(s, label, rect.centerx, rect.centery + 1, "#ffffff", anchor="center")
