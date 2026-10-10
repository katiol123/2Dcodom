"""The spectator's view of the computer realms' turns (pygame): every card a realm plays and every
embassy it sends is shown on the map while the turn waits (``Runner._show_hook``).

A card flies out of its realm's banner on the bottom bar and goes where it was played:
  * on a city - the camera glides there, the card stands beside the city, rings and sparks burst
    on it and the effect rises above it ("+45 золота", "в осаде"...);
  * on a realm - a trail of light runs from the player's banner to the target's, which flares up;
  * on an officer - his portrait shows beside the card;
  * on nothing - the card stands in the middle under its realm's shield.
A plate at the top names the realm, the card and the effect. Envoys (sent by a card or by the
realm's own diplomacy) carry a sealed letter from banner to banner and come back with a stamp:
ПРИНЯТО (green) or ОТКАЗ (red), with the reason the other side gave.
A click, Space or Enter moves on; Esc stops the showing (the chronicle still tells everything).
"""

from __future__ import annotations

import math
from typing import List, Optional, Tuple

import pygame

from . import audio
from .cards import CARDS
from .factions import ALL_FACTIONS, CITY, FACTION
from .fx import Ring, Sparks, ease_in, ease_out, lerp
from .officers import OFFICER
from .render import INK, _c
from .sim import H, W

CURSE_KINDS = ("curse", "vice")
KIND_SOUND = {"economy": "coins", "military": "drums", "intrigue": "whisper", "diplomacy": "horn",
              "council": "seal", "recruit": "march", "curse": "tear", "vice": "tear"}
TREATY_NAMES = {"truce": "ПЕРЕМИРИЕ", "alliance": "СОЮЗ", "trade": "ТОРГОВЛЮ", "war": "ВОЙНА"}


def slot_rect(f: str) -> pygame.Rect:
    """A realm's banner on the bottom bar of the map."""
    from .mapview import BOTTOM
    keys = [x.key for x in ALL_FACTIONS]
    cw = W // len(keys)
    i = keys.index(f) if f in keys else 0
    return pygame.Rect(i * cw + 2, H - BOTTOM + 2, cw - 3, BOTTOM - 4)


def target_of(card_key: str, targets: list) -> Tuple[str, object]:
    """What a card was played on: ("city", key) | ("realm", key) | ("officer", key) | ("self", None).
    The last city named wins (a march's destination, a storm's target)."""
    flat: List[str] = []
    for t in targets:
        flat.extend(t if isinstance(t, (list, tuple)) else [t])
    cities = [t for t in flat if isinstance(t, str) and t in CITY]
    if cities:
        return "city", cities[-1]
    realms = [t for t in flat if isinstance(t, str) and t in FACTION]
    if realms:
        return "realm", realms[-1]
    officers = [t for t in flat if isinstance(t, str) and t in OFFICER]
    if officers:
        return "officer", officers[0]
    return "self", None


class Show:
    """One thing shown: a card played (and the envoys it sent) or envoys on their own."""
    CARD = (0.45, 2.15, 0.4)           # fly in, hold, leave: 3 s, then the next one by itself
    ENVOYS = (0.8, 1.9, 0.3)           # the letter's flight, the answer, fade: 3 s

    def __init__(self, ms, req: dict):
        self.ms, self.req = ms, req
        self.t = 0.0
        self.parts: List[str] = []
        if req["what"] == "card":
            self.parts.append("card")
        if req["what"] == "diplo" or req.get("envoys"):
            self.parts.append("envoys")
        self.part = 0
        self.part_t = 0.0
        self.env = req if req["what"] == "diplo" else req.get("envoys")
        self.fired = set()
        if req["what"] == "card":
            self.card = CARDS[req["card"]]
            self.kind, self.target = target_of(req["card"], req.get("targets") or [])
            from .cardui import origin_label
            self.img = ms.table.art.full(req["card"], origin_label(req.get("origin", "")), req["faction"])
            if self.kind == "city":
                self._look_at(self.target)

    # --- timing ------------------------------------------------------------------------------
    def _len(self, part: str) -> float:
        return sum(self.CARD if part == "card" else self.ENVOYS)

    @property
    def done(self) -> bool:
        return self.part >= len(self.parts)

    def skip(self) -> None:
        self.part = len(self.parts)

    def update(self, dt: float) -> None:
        if self.done:
            return
        self.t += dt
        self.part_t += dt
        if self.cam_to is not None:                       # the camera glides to the city
            k = ease_out(min(1.0, self.t / 0.45))
            self.ms.cam = [lerp(a, b, k) for a, b in zip(self.cam_from, self.cam_to)]
        part = self.parts[self.part]
        self._cues(part)
        if self.part_t >= self._len(part):
            self.part += 1
            self.part_t = 0.0
            self.fired = set()

    def _once(self, key: str, at: float) -> bool:
        if key in self.fired or self.part_t < at:
            return False
        self.fired.add(key)
        return True

    def _cues(self, part: str) -> None:
        fx = self.ms.fx
        if part == "card":
            fly = self.CARD[0]
            if self._once("play", 0.0):
                audio.ui("play")
            if self._once("burst", fly):
                audio.ui(KIND_SOUND.get(self.card.kind, "seal"))
                col = self._color()
                x, y = self._target_point()
                for e in (Ring(x, y, col, 4, 34, 0.55, width=2), Ring(x, y, "#ffffff", 2, 20, 0.35),
                          Sparks(x, y, col, 28, 90)):
                    e.layer = 2
                    fx.add(e)
                if self.kind == "city":
                    fx.add(Ring(x, y, col, 4, 26, 0.55, delay=0.5)).layer = 2
            if self.req.get("origin") in OFFICER and self._once("stamp", fly + 0.15):
                audio.ui("stamp")
        else:
            fly = self.ENVOYS[0]
            if self._once("send", 0.0):
                audio.ui("horn" if self.env["treaty"] != "war" else "betrayal")
            if self._once("answer", fly):
                yes = self.env["yes"]
                audio.ui("harp" if yes and self.env["treaty"] != "war" else "refuse")
                r = slot_rect(self.env["to"])
                col = "#63c74d" if yes and self.env["treaty"] != "war" else "#e43b44"
                for e in (Ring(r.centerx, r.centery, col, 4, 30, 0.5, width=2), Sparks(r.centerx, r.y, col, 20, 70)):
                    e.layer = 2
                    fx.add(e)

    # --- geometry ----------------------------------------------------------------------------
    cam_to = None

    def _look_at(self, city: str) -> None:
        """Bring the city into the middle of the view when it is off screen or near an edge."""
        from .mapview import BOTTOM, TOP
        ms = self.ms
        c = CITY[city]
        x, y = ms._to_screen(c.x, c.y)
        if 70 < x < W - 70 and TOP + 60 < y < H - BOTTOM - 40:
            return
        from .mapview import MAP_H, MAP_W
        z = ms.zoom
        self.cam_from = list(ms.cam)
        vw, vh = W / z, (H - TOP - BOTTOM) / z               # the view stays on the map (no void past its edge)
        self.cam_to = [max(0.0, min(MAP_W - vw, c.x - vw / 2)),
                       max(-TOP / z, min(MAP_H - vh - TOP / z, c.y - (TOP + (H - TOP - BOTTOM) * 0.55) / z))]

    def _target_point(self) -> Tuple[int, int]:
        if self.kind == "city":
            c = CITY[self.target]
            return self.ms._to_screen(c.x, c.y - 6)
        if self.kind == "realm":
            return slot_rect(self.target).center
        return self._anchor().center

    def _anchor(self) -> pygame.Rect:
        """Where the card stands while it shows itself."""
        from .mapview import BOTTOM, TOP
        w, h = self.img.get_size()
        if self.kind == "city":
            x, y = self._target_point()
            left = x > W // 2                              # beside the city, on the roomier side
            r = pygame.Rect(x - 24 - w if left else x + 24, y - h // 2, w, h)
        else:
            r = pygame.Rect(W // 2 - w // 2, TOP + 56, w, h)
        r.clamp_ip(pygame.Rect(4, TOP + 52, W - 8, H - TOP - BOTTOM - 54))
        return r

    def _color(self) -> str:
        from .cardui import KIND_COLOR
        return KIND_COLOR.get(self.card.kind, ("#fee761", ""))[0]

    # --- drawing -----------------------------------------------------------------------------
    def draw(self, s: pygame.Surface) -> None:
        if self.done:
            return
        part = self.parts[self.part]
        if part == "card":
            self._draw_card(s)
        else:
            self._draw_envoys(s)
        r = self.plate
        if r is not None:                                  # under the plate
            hint = self.ms.font.render("КЛИК - ДАЛЬШЕ, ESC - НЕ ПОКАЗЫВАТЬ ХОДЫ", "#8b9bb4")
            box = pygame.Rect(r.centerx - hint.get_width() // 2 - 3, r.bottom + 1, hint.get_width() + 6, 9)
            pygame.draw.rect(s, _c("#181425"), box)
            s.blit(hint, (box.x + 3, box.y + 1))

    plate: Optional[pygame.Rect] = None

    def _plate(self, s: pygame.Surface, faction: str, title: str, title_col: str, lines: List[Tuple[str, str]],
               to: Optional[str] = None) -> None:
        """The plate at the top: the realm's shield and name, what it did, what came of it."""
        from .mapview import TOP, wrap
        font = self.ms.font
        f = FACTION[faction]
        rows: List[Tuple[str, str]] = []
        for text, col in lines:
            rows += [(line, col) for line in wrap(text, 250)[:2]]
        w, h = 270, 22 + 8 * len(rows)
        r = self.plate = pygame.Rect(W // 2 - w // 2, TOP + 4, w, h)
        s.blit(self.ms.r.panel(r.w, r.h, base="#181425", border=f.color), r.topleft)
        pygame.draw.line(s, _c(f.light), (r.x + 2, r.y + 1), (r.right - 3, r.y + 1))
        s.blit(self.ms.shields[faction], (r.x + 5, r.y + 4))
        font.draw(s, f.name, r.x + 22, r.y + 4, f.light)
        if to:
            s.blit(self.ms.shields[to], (r.right - 20, r.y + 4))
            font.draw(s, FACTION[to].short, r.right - 23, r.y + 4, FACTION[to].light, anchor="topright")
        font.draw(s, title, r.x + 22, r.y + 12, title_col)
        y = r.y + 21
        for line, col in rows:
            font.draw(s, line, r.centerx, y, col, anchor="midtop")
            y += 8

    def _draw_card(self, s: pygame.Surface) -> None:
        fly, hold, leave = self.CARD
        t = self.part_t
        req = self.req
        src = slot_rect(req["faction"])
        dst = self._anchor()
        col = self._color()
        if t < fly:
            k = ease_out(t / fly)
            w = max(4, round(lerp(src.h * 0.7, dst.w, k)))
            h = max(6, round(lerp(src.h, dst.h, k)))
            cx = lerp(src.centerx, dst.centerx, k)
            cy = lerp(src.centery, dst.centery, k) - math.sin(k * math.pi) * 30
            r = pygame.Rect(round(cx - w / 2), round(cy - h / 2), w, h)
        elif t < fly + hold:
            r = dst.move(0, -round(2 * math.sin((t - fly) * 4)))
        else:
            k = ease_in(min(1.0, (t - fly - hold) / leave))
            end = pygame.Rect(0, 0, 8, 12)
            end.center = self._target_point()
            r = pygame.Rect(round(lerp(dst.x, end.x, k)), round(lerp(dst.y, end.y, k)),
                            max(2, round(lerp(dst.w, end.w, k))), max(2, round(lerp(dst.h, end.h, k))))
        live = fly <= t < fly + hold
        if live and self.kind == "realm":                  # a trail of light from banner to banner
            self._trail(s, src.center, slot_rect(self.target).center, col, (t - fly) / 0.6)
        if live and self.kind == "city":                   # a beam from the card to the city
            x, y = self._target_point()
            pygame.draw.line(s, INK, (dst.centerx, dst.centery + 1), (x, y + 1), 3)
            pygame.draw.line(s, _c(col), dst.center, (x, y), 1)
            pulse = 10 + 4 * math.sin((t - fly) * 8)
            pygame.draw.circle(s, _c(col), (x, y), round(pulse), 1)
        if live:
            glow = r.inflate(4 + 2 * (int(t * 10) % 2), 4 + 2 * (int(t * 10) % 2))
            pygame.draw.rect(s, _c(col), glow, 1)
        img = self.img if r.size == self.img.get_size() else pygame.transform.scale(self.img, r.size)
        s.blit(img, r.topleft)
        if not live:
            return
        font = self.ms.font
        o = req.get("origin")
        if o in OFFICER:                                    # the adviser who brought the card
            face = pygame.Rect(r.x - 22 if r.x > W // 2 else r.right + 6, r.y + 4, 18, 22)
            pygame.draw.rect(s, INK, face.inflate(4, 4))
            pygame.draw.rect(s, _c(col), face.inflate(2, 2))
            self.ms.cards.face(s, face, o, click=False)
        if self.kind == "officer" and self.target in OFFICER:
            face = pygame.Rect(r.x - 30 if r.x > W // 2 else r.right + 6, r.bottom - 34, 24, 29)
            pygame.draw.rect(s, INK, face.inflate(4, 4))
            pygame.draw.rect(s, _c("#ffffff"), face.inflate(2, 2))
            self.ms.cards.face(s, face, self.target, click=False)
            font.draw(s, OFFICER[self.target].name, face.centerx, face.bottom + 3, "#ffffff", anchor="midtop")
        msg = req.get("msg") or ""
        bad = self.card.kind in CURSE_KINDS or any(w in msg for w in ("сорвал", "перехвачен", "презрени"))
        short = msg.split(": ", 1)[-1] if self.kind == "city" and msg.startswith(CITY[self.target].name) else msg
        if self.kind == "city" and short and len(short) <= 28 and t - fly > 0.2:   # a short effect rises above it
            x, y = self._target_point()
            k = min(1.0, (t - fly - 0.2) / 0.5)
            img = font.render(short[:40], "#a7f070" if not bad else "#f6757a")
            bx = max(2, min(W - img.get_width() - 2, x - img.get_width() // 2))
            by = y - 16 - round(10 * ease_out(k))
            pygame.draw.rect(s, (24, 20, 37), (bx - 2, by - 1, img.get_width() + 4, img.get_height() + 2))
            s.blit(img, (bx, by))
        where = {"city": lambda: f"НА ГОРОД {CITY[self.target].name}",
                 "realm": lambda: f"ПРОТИВ ДЕРЖАВЫ {FACTION[self.target].short}"
                 if self.card.kind in ("curse", "intrigue", "military") else f"ДЕРЖАВЕ {FACTION[self.target].short}",
                 "officer": lambda: f"НА ОФИЦЕРА {OFFICER[self.target].name}",
                 "self": lambda: ""}[self.kind]()
        from .cardui import TIER_COLOR
        lines = [(where, "#c0cbdc")] if where else []
        if msg:
            lines.append((msg.upper(), "#a7f070" if not bad else "#f6757a"))
        self._plate(s, req["faction"], f"РАЗЫГРЫВАЕТ: {self.card.name}", TIER_COLOR.get(self.card.tier, "#fee761"),
                    lines, to=self.target if self.kind == "realm" else None)

    def _trail(self, s: pygame.Surface, a, b, col: str, k: float) -> None:
        """A dotted arc rising over the map from banner ``a`` to banner ``b``, drawn up to ``k``."""
        k = max(0.0, min(1.0, k))
        n = 28
        pts = []
        for i in range(n + 1):
            u = i / n
            if u > k:
                break
            x = lerp(a[0], b[0], u)
            y = lerp(a[1], b[1], u) - math.sin(u * math.pi) * (40 + abs(b[0] - a[0]) * 0.25)
            pts.append((round(x), round(y)))
        for i, p in enumerate(pts):
            if i % 2 == 0:
                pygame.draw.rect(s, INK, (p[0] - 1, p[1] - 1, 4, 4))
                pygame.draw.rect(s, _c(col), (p[0], p[1], 2, 2))
        if pts:
            pygame.draw.circle(s, _c("#ffffff"), pts[-1], 2)

    def _draw_envoys(self, s: pygame.Surface) -> None:
        fly, hold, leave = self.ENVOYS
        env = self.env
        t = self.part_t
        a, b = slot_rect(env["faction"]), slot_rect(env["to"])
        war = env["treaty"] == "war"
        fa = FACTION[env["faction"]]
        col = "#e43b44" if war else fa.light
        k = min(1.0, t / fly)
        self._trail(s, a.center, b.center, col, k)
        # the letter (a little scroll with the sender's seal) riding the arc
        u = ease_out(k)
        x = lerp(a.centerx, b.centerx, u)
        y = lerp(a.centery, b.centery, u) - math.sin(u * math.pi) * (40 + abs(b.centerx - a.centerx) * 0.25)
        if t < fly + hold:
            letter = pygame.Rect(round(x) - 5, round(y) - 4, 10, 8)
            pygame.draw.rect(s, INK, letter.inflate(2, 2))
            pygame.draw.rect(s, _c("#ead4aa"), letter)
            pygame.draw.line(s, _c("#b86f50"), letter.topleft, (letter.right - 1, letter.top))
            pygame.draw.circle(s, _c(fa.color), letter.center, 2)
        name = TREATY_NAMES.get(env["treaty"], env["treaty"])
        if war:
            title, lines = "ВЕРОЛОМСТВО!", [(env.get("terms") or f"РАЗРЫВАЮТ МИР С {FACTION[env['to']].short}",
                                             "#f6757a")]
        else:
            title = f"ПОСЛЫ ПРЕДЛАГАЮТ {name}"
            lines = []
        if t >= fly and not war:                         # the answer
            yes = env["yes"]
            stamp = "ПРИНЯТО" if yes else "ОТКАЗ"
            scol = "#63c74d" if yes else "#e43b44"
            h = min(1.0, (t - fly) / 0.2)
            font = self.ms.font
            img = font.render(stamp, scol, scale=2)
            sx, sy = b.centerx - img.get_width() // 2, b.y - 26 - round(6 * (1 - h))
            sx = max(2, min(W - img.get_width() - 2, sx))
            plate = pygame.Rect(sx - 3, sy - 2, img.get_width() + 6, img.get_height() + 4)
            pygame.draw.rect(s, INK, plate.inflate(2, 2))
            pygame.draw.rect(s, _c("#181425"), plate)
            pygame.draw.rect(s, _c(scol), plate, 1)
            s.blit(img, (sx, sy))
            lines.append(((env.get("terms") or stamp) if yes else f"{FACTION[env['to']].short} ОТВЕРГЛИ", scol))
            if env.get("why"):
                lines.append((("ПРИЧИНА: " if not yes else "ДОВОД: ") + env["why"], "#c0cbdc"))
        self._plate(s, env["faction"], title, "#5fb7d9" if not war else "#e43b44", lines, to=env["to"])
