"""Interface animations for the world map (pygame): cards dealt and played, banners, floating
numbers, sparks and rings. Every effect is a small object with ``update(dt)`` and ``draw(s)``;
``FX`` runs them and plays their sounds (``audio.ui``) on the frame they belong to, so picture and
sound stay together. Pixel art is scaled only with nearest neighbour (crisp); no rotation.
"""

from __future__ import annotations

import math
import random
from typing import Callable, List, Optional, Sequence, Tuple

import pygame

from . import audio
from .render import INK, _c


def ease_out(t: float) -> float:
    return 1 - (1 - t) ** 3


def ease_in(t: float) -> float:
    return t ** 3


def ease_back(t: float) -> float:
    c1 = 1.70158
    return 1 + (c1 + 1) * (t - 1) ** 3 + c1 * (t - 1) ** 2


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def lerp_rect(a: pygame.Rect, b: pygame.Rect, t: float) -> pygame.Rect:
    return pygame.Rect(round(lerp(a.x, b.x, t)), round(lerp(a.y, b.y, t)),
                       max(1, round(lerp(a.w, b.w, t))), max(1, round(lerp(a.h, b.h, t))))


class Effect:
    """``cues``: (time, sound) pairs played once when the effect's clock passes them."""
    layer = 1

    def __init__(self, dur: float, delay: float = 0.0, cues: Sequence[Tuple[float, str]] = ()):
        self.t = -delay
        self.dur = dur
        self.cues = sorted(cues)

    @property
    def done(self) -> bool:
        return self.t >= self.dur

    @property
    def k(self) -> float:
        return max(0.0, min(1.0, self.t / self.dur))

    def update(self, dt: float) -> None:
        before = self.t
        self.t += dt
        while self.cues and before <= self.cues[0][0] < self.t + 1e-9:
            audio.ui(self.cues.pop(0)[1])
        while self.cues and self.cues[0][0] < before:
            self.cues.pop(0)

    def draw(self, s: pygame.Surface) -> None:
        pass


class FX:
    def __init__(self):
        self.items: List[Effect] = []

    def add(self, e: Effect) -> Effect:
        self.items.append(e)
        return e

    def update(self, dt: float) -> None:
        for e in self.items:
            e.update(dt)
        self.items = [e for e in self.items if not e.done]

    def draw(self, s: pygame.Surface, layer: int = 1) -> None:
        for e in self.items:
            if e.t >= 0 and e.layer == layer:
                e.draw(s)

    def busy(self, cls) -> bool:
        return any(isinstance(e, cls) for e in self.items)


# --- small effects -------------------------------------------------------------------------------
class Sparks(Effect):
    """A burst of square pixels flying out and falling."""

    def __init__(self, x: float, y: float, color: str, n: int = 18, speed: float = 70, delay: float = 0.0,
                 life: float = 0.8):
        super().__init__(life, delay)
        rnd = random.Random(int(x * 31 + y * 17 + n))
        self.parts = []
        for _ in range(n):
            a = rnd.uniform(0, 2 * math.pi)
            v = rnd.uniform(0.3, 1.0) * speed
            self.parts.append([x, y, math.cos(a) * v, math.sin(a) * v - speed * 0.4, rnd.choice((1, 1, 2))])
        self.cols = [_c(color), _c("#ffffff")]

    def update(self, dt: float) -> None:
        super().update(dt)
        if self.t < 0:
            return
        for p in self.parts:
            p[0] += p[2] * dt
            p[1] += p[3] * dt
            p[3] += 140 * dt

    def draw(self, s: pygame.Surface) -> None:
        if self.k > 0.85 and int(self.t * 30) % 2:
            return                                       # flicker out
        for i, (x, y, _, _, size) in enumerate(self.parts):
            s.fill(self.cols[i % 4 == 0], (int(x), int(y), size, size))


class Ring(Effect):
    def __init__(self, x: float, y: float, color: str, r0: float = 4, r1: float = 30, dur: float = 0.45,
                 delay: float = 0.0, width: int = 2):
        super().__init__(dur, delay)
        self.x, self.y, self.col, self.r0, self.r1, self.w = x, y, _c(color), r0, r1, width

    def draw(self, s: pygame.Surface) -> None:
        r = lerp(self.r0, self.r1, ease_out(self.k))
        w = max(1, round(self.w * (1 - self.k) + 0.5))
        pygame.draw.circle(s, self.col, (round(self.x), round(self.y)), round(r), w)


class FloatText(Effect):
    def __init__(self, font, text: str, x: float, y: float, color: str, rise: float = 14, dur: float = 1.1,
                 delay: float = 0.0, cue: str = ""):
        super().__init__(dur, delay, [(0.0, cue)] if cue else [])
        self.img = font.render(text, color)
        self.x, self.y, self.rise = x, y, rise

    def draw(self, s: pygame.Surface) -> None:
        if self.k > 0.8 and int(self.t * 24) % 2:
            return
        y = self.y - self.rise * ease_out(self.k)
        s.blit(self.img, (round(self.x - self.img.get_width() / 2), round(y)))


class Banner(Effect):
    """A ribbon that sweeps in from the left, holds and leaves to the right."""
    layer = 2

    def __init__(self, font, title: str, sub: str, color: str, y: int, width: int, cue: str = "turn",
                 dur: float = 1.7):
        super().__init__(dur, 0.0, [(0.0, cue)] if cue else [])
        self.font, self.title, self.sub, self.col, self.y, self.W = font, title, sub, color, y, width

    def draw(self, s: pygame.Surface) -> None:
        k = self.t
        if k < 0.35:
            x = lerp(-self.W, 0, ease_out(k / 0.35))
        elif k < self.dur - 0.35:
            x = 0
        else:
            x = lerp(0, self.W, ease_in((k - (self.dur - 0.35)) / 0.35))
        band = pygame.Rect(round(x), self.y, self.W, 26)
        pygame.draw.rect(s, INK, band.inflate(0, 4))
        pygame.draw.rect(s, _c("#181425"), band)
        pygame.draw.line(s, _c(self.col), band.topleft, band.topright)
        pygame.draw.line(s, _c(self.col), band.bottomleft, band.bottomright)
        cx = band.centerx
        self.font.draw(s, self.title, cx, band.y + 3, self.col, scale=2, anchor="midtop")
        if self.sub:
            self.font.draw(s, self.sub, cx, band.y + 18, "#c0cbdc", anchor="midtop")
        shine = int((k * 260) % (self.W + 80)) - 40          # a glint running along the ribbon
        pygame.draw.line(s, _c("#ffffff"), (band.x + shine, band.y + 1), (band.x + shine + 6, band.y + 1))


# --- cards ---------------------------------------------------------------------------------------
def _scaled(img: pygame.Surface, w: int, h: int) -> pygame.Surface:
    return img if img.get_size() == (w, h) else pygame.transform.scale(img, (max(1, w), max(1, h)))


class CardFly(Effect):
    """A card flying between two rects; with ``back`` it turns over halfway (face down -> face up)."""
    layer = 2

    def __init__(self, front: pygame.Surface, src: pygame.Rect, dst: Callable[[], pygame.Rect], dur: float = 0.42,
                 delay: float = 0.0, back: Optional[pygame.Surface] = None, cues=(), on_done=None):
        super().__init__(dur, delay, cues)
        self.front, self.back, self.src, self.dst, self.on_done = front, back, pygame.Rect(src), dst, on_done

    def update(self, dt: float) -> None:
        was = self.done
        super().update(dt)
        if self.done and not was and self.on_done:
            self.on_done()

    def draw(self, s: pygame.Surface) -> None:
        r = lerp_rect(self.src, self.dst(), ease_out(self.k))
        r.y -= round(math.sin(self.k * math.pi) * 16)          # a little arc
        img = self.front
        if self.back is not None:
            turn = abs(1 - 2 * min(1.0, self.k * 1.3))           # 1 -> 0 -> 1 across the flip
            img = self.back if self.k * 1.3 < 0.5 else self.front
            w = max(1, round(r.w * turn))
            r = pygame.Rect(r.centerx - w // 2, r.y, w, r.h)
        s.blit(_scaled(img, r.w, r.h), r.topleft)


KIND_SOUND = {"economy": "coins", "military": "drums", "intrigue": "whisper", "diplomacy": "horn",
              "council": "seal", "recruit": "march", "curse": "tear", "vice": "tear"}


class PlayShow(Effect):
    """A played card: it leaps from the hand to the middle, shows itself (with the adviser who
    brought it), bursts in its kind's colour and drops onto the discard pile."""
    layer = 2
    FLY, HOLD, LEAVE = 0.26, 0.75, 0.3

    def __init__(self, ms, img: pygame.Surface, src: pygame.Rect, kind: str, color: str,
                 adviser: Optional[str], result: str, ok: bool, dst: Callable[[], pygame.Rect]):
        super().__init__(self.FLY + self.HOLD + self.LEAVE,
                         cues=[(0.0, "play"), (self.FLY, KIND_SOUND.get(kind, "seal") if ok else "refuse")]
                         + ([(self.FLY + 0.12, "stamp")] if adviser else [])
                         + [(self.FLY + self.HOLD, "deal")])
        from .sim import H, W
        self.ms, self.img, self.src, self.kind, self.col = ms, img, pygame.Rect(src), kind, color
        self.adviser, self.result, self.ok, self.dst = adviser, result, ok, dst
        w, h = img.get_size()                                   # 1:1 keeps the pixel art crisp
        self.mid = pygame.Rect(W // 2 - w // 2, (H - h) // 2 - 14, w, h)
        self.burst = False

    def update(self, dt: float) -> None:
        super().update(dt)
        if not self.burst and self.t >= self.FLY:
            self.burst = True
            cx, cy = self.mid.center
            self.ms.fx.add(Ring(cx, cy, self.col, 16, 72, 0.45, width=2))
            self.ms.fx.add(Sparks(cx, cy, self.col if self.ok else "#e43b44", 36, 120))
            self.ms.fx.items[-1].layer = 2
            self.ms.fx.items[-2].layer = 2

    def draw(self, s: pygame.Surface) -> None:
        t = self.t
        if t < self.FLY:
            r = lerp_rect(self.src, self.mid, ease_out(t / self.FLY))
        elif t < self.FLY + self.HOLD:
            h = (t - self.FLY) / self.HOLD
            r = self.mid.move(0, -round(3 * math.sin(h * math.pi)))
            glow = r.inflate(6 + 2 * (int(h * 12) % 2), 6 + 2 * (int(h * 12) % 2))
            pygame.draw.rect(s, _c(self.col), glow, 2)
            for i in range(8):                                   # rays
                a = i * math.pi / 4 + h * 1.2
                x0, y0 = r.centerx + math.cos(a) * (r.w * 0.62), r.centery + math.sin(a) * (r.h * 0.56)
                x1, y1 = r.centerx + math.cos(a) * (r.w * 0.8), r.centery + math.sin(a) * (r.h * 0.66)
                pygame.draw.line(s, _c(self.col), (x0, y0), (x1, y1), 1)
        else:
            k = (t - self.FLY - self.HOLD) / self.LEAVE
            r = lerp_rect(self.mid, self.dst(), ease_in(k))
        s.blit(_scaled(self.img, r.w, r.h), r.topleft)
        if self.FLY <= t < self.FLY + self.HOLD:
            h = (t - self.FLY) / self.HOLD
            font = self.ms.font
            if self.adviser:                                      # the adviser's seal
                from .officers import OFFICER
                k = min(1.0, (t - self.FLY) / 0.18)
                size = round(lerp(54, 30, ease_out(k)))
                face = pygame.Rect(r.x - size - 6, r.y + 10, size, round(size * 1.2))
                pygame.draw.rect(s, INK, face.inflate(4, 4))
                pygame.draw.rect(s, _c(self.col), face.inflate(2, 2))
                self.ms.cards.face(s, face, self.adviser)
                font.draw(s, "СОВЕТНИК", face.right, face.bottom + 4, "#8b9bb4", anchor="topright")
                font.draw(s, OFFICER[self.adviser].name, face.right, face.bottom + 12, "#fee761", anchor="topright")
            if self.result and h > 0.15:
                from .mapview import wrap
                y = r.bottom + 8
                for line in wrap(self.result, 220)[:2]:
                    font.draw(s, line, r.centerx, y, "#a7f070" if self.ok else "#f6757a", anchor="midtop")
                    y += 8


class Reveal(Effect):
    """Something (a big card, a window) popping up: scaled from small with a little overshoot."""
    layer = 3

    def __init__(self, dur: float = 0.35, cue: str = ""):
        super().__init__(dur, 0.0, [(0.0, cue)] if cue else [])

    def scale(self) -> float:
        return lerp(0.25, 1.0, ease_back(self.k))
