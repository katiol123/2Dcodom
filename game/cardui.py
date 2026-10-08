"""Cards on the world map: card art, the hand, targeting, the council and the chronicle.

``CardTable`` sits on top of ``WorldMapScreen``: it draws the player's hand along the bottom,
the end-turn button and the action points, walks the player through a card's targets (cities
are clicked on the map, officers and realms are picked from a list), and owns two windows:
the council (who sits in it, its stat thresholds, its deck) and the chronicle of what every
realm did. In spectator mode it only advances the rounds.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

import pygame

from .cardplay import MAX_GROUP, MULTI
from .cards import (CARDS, COUNCIL_SEATS, COURSES, course_cooldown, KIND_NAMES, PERSONAL, STATS, THRESHOLD_CARDS, THRESHOLDS, TIER_NAMES,
                    competence, council_totals, hand_size, intercepts, reserve, strife)
from .factions import CITY, FACTION
from .officers import OFFICER
from .render import INK, _c
from .sim import H, W

CARD_W, CARD_H = 88, 128
TIER_COLOR = {"basic": "#8b9bb4", "junk": "#5a6988", "moderate": "#41a6f6", "strong": "#feae34",
              "unique": "#e07ad8", "faction": "#fee761", "curse": "#e43b44"}
KIND_COLOR = {"economy": ("#c9a24a", "#4a3a14"), "military": ("#e43b44", "#4a1418"),
              "intrigue": ("#b07ad8", "#2e1a40"), "diplomacy": ("#5fb7d9", "#14304a"),
              "council": ("#63c74d", "#173a1a"), "recruit": ("#d08a4a", "#3e2414"),
              "curse": ("#e43b44", "#1a0a0e")}

CITY_STEPS = {"own_city", "own_city_officers", "own_city_pair", "own_city_pair2", "dest_adj", "dest_2",
              "dest_any", "dest_any_one", "enemy_adj", "enemy_adj_any", "enemy_reach", "enemy_port",
              "enemy_city", "enemy_city_officers"}
RIVAL_STEPS = {"rival", "rival_diplo", "rival_neighbor"}
PROMPTS = {
    "own_city": "ВЫБЕРИТЕ СВОЙ ГОРОД", "own_city_officers": "ГОРОД, ОТКУДА ВЫСТУПАЮТ",
    "own_city_pair": "ПЕРВЫЙ ГОРОД КАРАВАНА", "own_city_pair2": "ВТОРОЙ ГОРОД (СОСЕДНИЙ)",
    "dest_adj": "КУДА ИДУТ (СОСЕДНИЙ СВОЙ ГОРОД)", "dest_2": "КУДА ИДУТ (ДО 2 ДОРОГ)",
    "dest_any": "КУДА ПЕРЕЙТИ", "dest_any_one": "КУДА ПЕРЕЙТИ",
    "enemy_adj": "КАКОЙ ГОРОД АТАКОВАТЬ", "enemy_adj_any": "КАКОЙ ГОРОД ПОРАЗИТЬ",
    "enemy_reach": "КАКОЙ ГОРОД АТАКОВАТЬ", "enemy_port": "КАКОЙ ПОРТ АТАКОВАТЬ",
    "enemy_city": "ЧУЖОЙ ГОРОД-ЦЕЛЬ", "enemy_city_officers": "ГОРОД, ГДЕ СТОИТ ЦЕЛЬ",
    "officers_here": "КТО ИДЁТ (ДО 3)", "attackers": "КТО ШТУРМУЕТ (ДО 3)", "attackers_far": "КТО ШТУРМУЕТ (ДО 3)",
    "attackers_port": "КТО ПЛЫВЁТ (ДО 3)", "raider": "КТО ГРАБИТ", "enemy_officer_there": "КОГО",
    "own_officer": "КАКОЙ ОФИЦЕР", "own_officer_ready": "КАКОЙ ОФИЦЕР", "own_officer_spent": "КТО СНОВА В СТРОЮ",
    "rival": "КАКАЯ ДЕРЖАВА", "rival_diplo": "С КАКОЙ ДЕРЖАВОЙ", "rival_neighbor": "КАКОЙ СОСЕД",
}


# --- card art -----------------------------------------------------------------------------------
def _icon(kind: str, color: str) -> pygame.Surface:
    """A 22x22 emblem for the card's kind, drawn with plain shapes (crisp at 1x)."""
    s = pygame.Surface((22, 22), pygame.SRCALPHA)
    c, d, w = _c(color), INK, (255, 244, 214)
    if kind == "economy":
        for x, y in ((8, 13), (14, 9)):
            pygame.draw.circle(s, d, (x, y), 7)
            pygame.draw.circle(s, c, (x, y), 6)
            pygame.draw.circle(s, w, (x - 2, y - 2), 2)
            pygame.draw.line(s, d, (x - 2, y), (x + 2, y))
    elif kind == "military":
        pygame.draw.line(s, d, (4, 18), (18, 4), 5)
        pygame.draw.line(s, (220, 226, 236), (4, 18), (18, 4), 3)
        pygame.draw.line(s, d, (4, 11), (11, 18), 5)
        pygame.draw.line(s, c, (5, 12), (10, 17), 3)
        pygame.draw.rect(s, d, (2, 16, 5, 5))
        pygame.draw.rect(s, c, (3, 17, 3, 3))
    elif kind == "intrigue":
        pygame.draw.ellipse(s, d, (1, 5, 20, 12))
        pygame.draw.ellipse(s, c, (2, 6, 18, 10))
        pygame.draw.ellipse(s, d, (5, 8, 5, 4))
        pygame.draw.ellipse(s, d, (12, 8, 5, 4))
        pygame.draw.line(s, d, (11, 14), (11, 20), 2)
    elif kind == "diplomacy":
        pygame.draw.rect(s, d, (3, 4, 16, 14))
        pygame.draw.rect(s, w, (4, 5, 14, 12))
        for y in (8, 11, 14):
            pygame.draw.line(s, d, (6, y), (15, y))
        pygame.draw.circle(s, d, (15, 16), 4)
        pygame.draw.circle(s, c, (15, 16), 3)
    elif kind == "council":
        pts = [(2, 17), (2, 6), (7, 11), (11, 3), (15, 11), (20, 6), (20, 17)]
        pygame.draw.polygon(s, d, pts)
        pygame.draw.polygon(s, c, [(3, 16), (3, 8), (7, 12), (11, 5), (15, 12), (19, 8), (19, 16)])
        pygame.draw.line(s, w, (4, 15), (18, 15))
    elif kind == "recruit":
        pygame.draw.circle(s, d, (11, 12), 9)
        pygame.draw.circle(s, c, (11, 12), 8)
        pygame.draw.rect(s, (0, 0, 0, 0), (2, 13, 18, 9))
        pygame.draw.rect(s, d, (2, 12, 18, 3))
        pygame.draw.rect(s, d, (10, 12, 3, 8))
        pygame.draw.circle(s, w, (8, 8), 2)
    else:                                                     # curse: a skull
        pygame.draw.circle(s, d, (11, 9), 8)
        pygame.draw.circle(s, (220, 214, 200), (11, 9), 7)
        pygame.draw.rect(s, d, (6, 14, 11, 6))
        pygame.draw.rect(s, (220, 214, 200), (7, 14, 9, 5))
        pygame.draw.circle(s, c, (8, 9), 2)
        pygame.draw.circle(s, c, (14, 9), 2)
        for x in (9, 11, 13):
            pygame.draw.line(s, d, (x, 15), (x, 18))
    return s


class CardArt:
    def __init__(self, renderer):
        self.r = renderer
        self.font = renderer.font
        self.cache: Dict[tuple, pygame.Surface] = {}

    def full(self, key: str, origin: str = "", faction: Optional[str] = None) -> pygame.Surface:
        """The whole card (88x128)."""
        k = ("full", key, origin, faction)
        if k in self.cache:
            return self.cache[k]
        from .mapview import wrap
        card = CARDS[key]
        tier = TIER_COLOR[card.tier] if card.tier != "faction" or not faction else FACTION[faction].light
        hi, lo = KIND_COLOR[card.kind]
        s = self.r.panel(CARD_W, CARD_H, base="#1c1830", border=tier).copy()
        pygame.draw.rect(s, _c(tier), (1, 1, CARD_W - 2, CARD_H - 2), 1)
        # header: cost gem, name
        pygame.draw.rect(s, _c("#120e1c"), (4, 4, CARD_W - 8, 21))
        pygame.draw.circle(s, INK, (12, 14), 8)
        pygame.draw.circle(s, _c("#124e89") if card.cost else _c("#3a4466"), (12, 14), 7)
        pygame.draw.circle(s, _c("#41a6f6"), (10, 11), 2)
        self.font.draw(s, str(card.cost), 12, 14, "#ffffff", anchor="center")
        lines = wrap(card.name, CARD_W - 30)[:2]
        for i, line in enumerate(lines):
            y = 14 + (i - (len(lines) - 1) / 2) * 8
            self.font.draw(s, line, 23, int(y), "#fee761" if card.tier != "curse" else "#f6757a", anchor="midleft")
        # art band
        band = pygame.Rect(4, 27, CARD_W - 8, 26)
        pygame.draw.rect(s, _c(lo), band)
        for x in range(band.x, band.right, 2):                # a little texture
            pygame.draw.line(s, _c(hi), (x, band.bottom - 1 - (x * 7) % 5), (x, band.bottom - 1))
        s.blit(_icon(card.kind, hi), (band.centerx - 11, band.y + 2))
        self.font.draw(s, KIND_NAMES[card.kind], band.x + 2, band.bottom - 7, "#c0cbdc")
        if card.gold:
            self.font.draw(s, f"{card.gold}З", band.right - 2, band.y + 2, "#feae34", anchor="topright")
        # text
        y = 57
        for line in wrap(card.text, CARD_W - 9):
            self.font.draw(s, line, 5, y, "#e6dfd0")
            y += 7
        # footer
        foot = TIER_NAMES[card.tier]
        self.font.draw(s, foot, CARD_W // 2, CARD_H - 10, tier, anchor="midtop")
        self.cache[k] = s
        return s

    def chip(self, key: str) -> pygame.Surface:
        """The card's name in its tier colour, for lists."""
        return self.font.render(CARDS[key].name, TIER_COLOR[CARDS[key].tier])


def origin_label(origin: str) -> str:
    if origin in OFFICER:
        return OFFICER[origin].name
    return {"base": "ДЕРЖАВА", "faction": "ЛИДЕР", "threshold": "СОВЕТ", "curse": "ПРОКЛЯТИЕ",
            "stolen": "ДОБЫЧА"}.get(origin, "")


# --- the card table on the map ---------------------------------------------------------------------
class CardTable:
    def __init__(self, ms):
        self.ms = ms                       # the WorldMapScreen
        self.camp = ms.camp
        self.font = ms.font
        self.art = CardArt(ms.r)
        self.play: Optional[dict] = None   # {"inst", "chosen"}
        self.picker: Optional[dict] = None
        self.council_open = False
        self.course_open = False
        self.chronicle_open = False
        self.chron_scroll = 0
        self.chron_from = 0
        self.council_seat: Optional[int] = None
        self.council_tab = "officers"
        self.council_scroll = 0
        self.hover_card: Optional[Tuple[str, str]] = None   # (card key, origin) shown big
        self.auto = False
        self.auto_t = 0.0
        self.hand_hover: Optional[int] = None

    # --- state -----------------------------------------------------------------------------
    @property
    def player(self) -> Optional[str]:
        return self.camp.player

    def my_turn(self) -> bool:
        return self.player is not None and self.camp.whose_turn() == self.player and \
            self.camp.realms[self.player].alive

    def busy(self) -> bool:
        """A card window or a target picker is open (the map must not react)."""
        return bool(self.picker or self.council_open or self.chronicle_open or self.course_open)

    # --- geometry -------------------------------------------------------------------------
    def hand(self) -> list:
        return self.camp.realms[self.player].hand if self.player else []

    def hand_rects(self) -> List[pygame.Rect]:
        n = len(self.hand())
        if not n:
            return []
        from .mapview import BOTTOM
        right = W - 112
        step = min(CARD_W + 2, (right - 6 - CARD_W) / max(1, n - 1)) if n > 1 else 0
        y = H - BOTTOM - 27
        rects = []
        for i in range(n):
            r = pygame.Rect(int(6 + i * step), y, CARD_W, CARD_H)
            if i == self.hand_hover and not self.busy():
                r.y = H - BOTTOM - CARD_H - 2
            rects.append(r)
        return rects

    def _card_at(self, mx: int, my: int) -> Optional[int]:
        rects = self.hand_rects()
        if self.hand_hover is not None and self.hand_hover < len(rects) and rects[self.hand_hover].collidepoint(mx, my):
            return self.hand_hover
        for i in reversed(range(len(rects))):
            if rects[i].collidepoint(mx, my):
                return i
        return None

    def end_rect(self) -> pygame.Rect:
        mini = self.ms._mini_rect()
        return pygame.Rect(mini.x - 2, mini.y - 22, mini.w + 4, 17)

    # --- input ------------------------------------------------------------------------------
    def handle(self, ev, mouse: Tuple[int, int]) -> bool:
        """True if the event belonged to the cards."""
        mx, my = mouse
        if self.course_open:
            self._course_handle(ev, mx, my)
            return True
        if self.council_open:
            self._council_handle(ev, mx, my)
            return True
        if self.chronicle_open:
            self._chronicle_handle(ev, mx, my)
            return True
        if self.picker:
            self._picker_handle(ev, mx, my)
            return True
        if self.play:
            return self._target_handle(ev, mx, my)
        if self.ms.selected and ev.type == pygame.MOUSEBUTTONDOWN and (
                self.ms._city_panel_rect().collidepoint(mx, my)
                or any(rect.collidepoint(mx, my) for rect, _ in self.ms._city_buttons())):
            return False                                # the city panel lies on top of the hand
        if self.player is None:
            return ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1 and self.spectator_click(mx, my)
        if ev.type == pygame.MOUSEBUTTONDOWN and ev.button in (1, 3):
            if self.end_rect().collidepoint(mx, my):
                if ev.button == 1:
                    self.end_turn()
                return True
            i = self._card_at(mx, my)
            if i is not None and self.player:
                inst = self.hand()[i]
                if ev.button == 3:
                    self._toggle_keep(inst)
                else:
                    self._start(inst)
                return True
        if ev.type == pygame.KEYDOWN and ev.key == pygame.K_e and self.my_turn():
            self.end_turn()
            return True
        return False

    def _toggle_keep(self, inst) -> None:
        r = self.camp.realms[self.player]
        n = reserve(r.council)
        if inst.id in r.keep:
            r.keep.remove(inst.id)
        elif n == 0:
            self.ms._say("СЛАБЫЙ СОВЕТ НЕ ДАЁТ ОСТАВЛЯТЬ КАРТЫ")
        elif len(r.keep) >= n:
            self.ms._say(f"ОСТАВИТЬ МОЖНО ЛИШЬ {n}")
        else:
            r.keep.append(inst.id)

    def _start(self, inst) -> None:
        if not self.my_turn():
            self.ms._say("СЕЙЧАС НЕ ВАШ ХОД")
            return
        ok, why = self.camp.can_play(self.player, inst)
        if not ok:
            self.ms._say(why)
            return
        self.play = {"inst": inst, "chosen": []}
        self.ms.selected = None
        self._advance()

    def _step(self) -> Optional[str]:
        card = self.play["inst"].card
        n = len(self.play["chosen"])
        return card.targets[n] if n < len(card.targets) else None

    def _options(self) -> list:
        return self.camp.options(self.player, self.play["inst"].key, self.play["chosen"])

    def _advance(self) -> None:
        """Ask for the next target, or play the card when all are chosen."""
        step = self._step()
        if step is None:
            inst = self.play["inst"]
            ok, msg = self.camp.play(self.player, inst, self.play["chosen"])
            self.play = None
            self.ms._say(f"{inst.card.name}: {msg}" if ok and msg else (inst.card.name if ok else msg),
                         "#a7f070" if ok else "#e43b44")
            return
        opts = self._options()
        if not opts:
            self.ms._say("НЕТ ПОДХОДЯЩЕЙ ЦЕЛИ")
            self.play = None
            return
        if step not in CITY_STEPS:
            self.picker = {"step": step, "options": opts, "picked": [], "scroll": 0}

    def _choose(self, value) -> None:
        self.play["chosen"].append(value)
        self.picker = None
        self._advance()

    def cancel(self) -> None:
        self.play = None
        self.picker = None

    def _target_handle(self, ev, mx, my) -> bool:
        if ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE or \
                ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 3:
            self.cancel()
            return True
        if ev.type == pygame.MOUSEBUTTONUP and ev.button == 1 and not self.ms.dragged:
            city = self.ms._city_at(mx, my)
            if city and city in self._options():
                self.ms.drag = None
                self._choose(city)
                return True
        return False                                   # dragging and zooming still move the map

    # --- turns ------------------------------------------------------------------------------
    def end_turn(self) -> None:
        if not self.my_turn():
            if self.player is None:
                self.next_round()
            return
        self.cancel()
        self.chron_from = len(self.camp.log)
        self.camp.end_turn()
        self.camp.run_ai()
        self.chronicle_open = True
        self.chron_scroll = 0

    def next_round(self) -> None:
        """Spectator: every realm plays once."""
        self.chron_from = len(self.camp.log)
        self.camp.run_ai(stop_at_player=False, max_turns=1)

    def update(self, dt: float, mouse) -> None:
        mx, my = mouse
        prev = self.hand_hover
        self.hand_hover = None
        if not self.busy() and not self.play and self.ms.window is None:
            if prev is not None:                       # the raised card keeps the mouse while over it
                self.hand_hover = prev
                rects = self.hand_rects()
                if prev < len(rects) and rects[prev].collidepoint(mx, my):
                    return self._auto(dt)
                self.hand_hover = None
            rects = self.hand_rects()
            for j in reversed(range(len(rects))):
                if rects[j].collidepoint(mx, my):
                    self.hand_hover = j
                    break
        self._auto(dt)

    def _auto(self, dt: float) -> None:
        if self.player is None and self.auto and not self.busy():
            self.auto_t += dt
            if self.auto_t > 1.2:
                self.auto_t = 0
                self.next_round()

    # --- drawing on the map -------------------------------------------------------------------
    def draw_targets(self, s: pygame.Surface) -> None:
        """Rings around the cities the current card may target."""
        if not self.play or self.picker:
            return
        opts = set(self._options())
        t = self.ms.time
        for key in opts:
            c = CITY[key]
            sx, sy = self.ms._to_screen(c.x, c.y)
            own = self.camp.owner[key] == self.player
            col = _c("#63c74d" if own else "#e43b44")
            r = 13 + int(2 * abs(((t * 3) % 2) - 1)) if self.ms.zoom == 1 else 8
            pygame.draw.circle(s, INK, (sx, sy - 6), r + 1, 1)
            pygame.draw.circle(s, col, (sx, sy - 6), r, 2)
        chosen = [x for x in self.play["chosen"] if isinstance(x, str) and x in CITY]
        for key in chosen:
            c = CITY[key]
            sx, sy = self.ms._to_screen(c.x, c.y)
            pygame.draw.circle(s, _c("#fee761"), (sx, sy - 6), 15, 2)

    def draw_hand(self, s: pygame.Surface) -> None:
        if self.player is None:
            self._spectator_bar(s)
            return
        if not self.camp.realms[self.player].alive:
            self.font.draw(s, "ВАША ДЕРЖАВА ПАЛА", W // 2, H // 2, "#e43b44", scale=2, anchor="center")
            return
        r = self.camp.realms[self.player]
        rects = self.hand_rects()
        order = list(range(len(rects)))
        if self.hand_hover is not None:
            order.remove(self.hand_hover)
            order.append(self.hand_hover)
        playing = self.play["inst"] if self.play else None
        for i in order:
            inst = r.hand[i]
            rect = rects[i]
            img = self.art.full(inst.key, origin_label(inst.origin), self.player)
            from .mapview import BOTTOM
            if i != self.hand_hover:                     # resting cards peek out above the bottom bar
                rect = pygame.Rect(rect.x, rect.y, rect.w, max(0, H - BOTTOM - rect.y))
            s.blit(img, rect.topleft, area=pygame.Rect(0, 0, rect.w, rect.h))
            ok = self.my_turn() and self.camp.can_play(self.player, inst)[0]
            if not ok:
                veil = pygame.Surface(rect.size, pygame.SRCALPHA)
                veil.fill((10, 8, 18, 120))
                s.blit(veil, rect.topleft)
            if inst is playing:
                pygame.draw.rect(s, _c("#fee761"), rect.inflate(2, 2), 2)
            if inst.id in r.keep:
                pygame.draw.rect(s, _c("#63c74d"), (rect.x + 2, rect.y - 7, 40, 8))
                self.font.draw(s, "ОСТАВИТЬ", rect.x + 4, rect.y - 7, "#ffffff")
            if i == self.hand_hover:
                pygame.draw.rect(s, _c("#ffffff"), rect.inflate(2, 2), 1)
                label = origin_label(inst.origin)
                if label:
                    self.font.draw(s, label, rect.centerx, rect.y - 9, "#c0cbdc", anchor="midtop")
                if not ok and self.my_turn():
                    why = self.camp.can_play(self.player, inst)[1]
                    self.font.draw(s, why, rect.centerx, rect.y + 60, "#f6757a", anchor="center")
        # end turn and the reserve
        er = self.end_rect()
        hot = er.collidepoint(self.ms._mouse)
        mine = self.my_turn()
        s.blit(self.ms.r.panel(er.w, er.h, base=("#c28a2e" if hot else "#9a6a1e") if mine else "#3a4466",
                                border="#fee761" if mine else "#5a6988"), er.topleft)
        self.font.draw(s, "КОНЕЦ ХОДА (E)" if mine else "ЖДЁМ...", er.centerx, er.centery, "#ffffff", anchor="center")
        n = reserve(r.council)
        info = f"РУКА {len(r.hand)}/{hand_size(r.council)}  КОЛОДА {len(r.draw)}  СБРОС {len(r.discard)}"
        self.font.draw(s, info, er.right, er.y - 8, "#8b9bb4", anchor="topright")
        if n:
            self.font.draw(s, f"ПКМ ПО КАРТЕ - ОСТАВИТЬ ({len(r.keep)}/{n})", er.right, er.y - 16, "#63c74d",
                           anchor="topright")
        if self.play and not self.picker:
            self._prompt(s)

    def _prompt(self, s: pygame.Surface) -> None:
        step = self._step()
        card = self.play["inst"].card
        text = f"{card.name}: {PROMPTS.get(step, '')}   (ПКМ - ОТМЕНА)"
        from .mapview import TOP
        w = self.font.render(text, "#fff").get_width() + 12
        rect = pygame.Rect((W - w) // 2, TOP + 3, w, 13)
        s.blit(self.ms.r.panel(rect.w, rect.h, base="#3a2a10", border="#fee761"), rect.topleft)
        self.font.draw(s, text, rect.centerx, rect.centery, "#fee761", anchor="center")

    def _spectator_bar(self, s: pygame.Surface) -> None:
        er = self.end_rect()
        hot = er.collidepoint(self.ms._mouse)
        s.blit(self.ms.r.panel(er.w, er.h, base="#5a6988" if hot else "#3a4466", border="#c0cbdc"), er.topleft)
        self.font.draw(s, "СЛЕДУЮЩИЙ ХОД", er.centerx, er.centery, "#ffffff", anchor="center")
        ar = pygame.Rect(er.x, er.y - 15, er.w, 13)
        hot = ar.collidepoint(self.ms._mouse)
        s.blit(self.ms.r.panel(ar.w, ar.h, base="#3e8948" if self.auto else ("#5a6988" if hot else "#262b44"),
                                border="#8b9bb4"), ar.topleft)
        self.font.draw(s, "АВТО: ВКЛ" if self.auto else "АВТО: ВЫКЛ", ar.centerx, ar.centery, "#ffffff",
                       anchor="center")

    def spectator_click(self, mx, my) -> bool:
        er = self.end_rect()
        if er.collidepoint(mx, my):
            self.next_round()
            return True
        if pygame.Rect(er.x, er.y - 15, er.w, 13).collidepoint(mx, my):
            self.auto = not self.auto
            return True
        return False

    def draw_windows(self, s: pygame.Surface) -> None:
        if self.picker:
            s.blit(self.ms.dim, (0, 0))
            self._picker_draw(s)
        if self.council_open:
            s.blit(self.ms.dim, (0, 0))
            self.ms.cards.cover()
            self._council_draw(s)
        if self.chronicle_open:
            s.blit(self.ms.dim, (0, 0))
            self.ms.cards.cover()
            self._chronicle_draw(s)
        if self.course_open:
            s.blit(self.ms.dim, (0, 0))
            self.ms.cards.cover()
            self._course_draw(s)

    # --- picker: officers and realms ------------------------------------------------------------
    ROWS = 9

    def _picker_rect(self) -> pygame.Rect:
        return pygame.Rect(W // 2 - 130, 34, 260, 30 + self.ROWS * 20 + 20)

    def _picker_row(self, i: int) -> pygame.Rect:
        r = self._picker_rect()
        return pygame.Rect(r.x + 6, r.y + 24 + i * 20, r.w - 12, 19)

    def _picker_buttons(self) -> List[Tuple[pygame.Rect, str]]:
        r = self._picker_rect()
        out = [(pygame.Rect(r.right - 66, r.bottom - 18, 60, 14), "cancel")]
        if self.picker and self.picker["step"] in MULTI:
            out.append((pygame.Rect(r.x + 6, r.bottom - 18, 60, 14), "done"))
        return out

    def _picker_handle(self, ev, mx, my) -> None:
        p = self.picker
        if ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE or \
                ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 3:
            self.cancel()
            return
        if ev.type == pygame.MOUSEWHEEL:
            p["scroll"] = max(0, min(max(0, len(p["options"]) - self.ROWS), p["scroll"] - ev.y))
            return
        if ev.type == pygame.KEYDOWN and ev.key == pygame.K_RETURN and p["step"] in MULTI and p["picked"]:
            self._choose(tuple(p["picked"]))
            return
        if ev.type != pygame.MOUSEBUTTONDOWN or ev.button != 1:
            return
        for rect, action in self._picker_buttons():
            if rect.collidepoint(mx, my):
                if action == "cancel":
                    self.cancel()
                elif p["picked"]:
                    self._choose(tuple(p["picked"]))
                return
        for i, opt in enumerate(p["options"][p["scroll"]:p["scroll"] + self.ROWS]):
            if self._picker_row(i).collidepoint(mx, my):
                if p["step"] in MULTI:
                    if opt in p["picked"]:
                        p["picked"].remove(opt)
                    elif len(p["picked"]) < MAX_GROUP:
                        p["picked"].append(opt)
                    else:
                        self.ms._say(f"НЕ БОЛЬШЕ {MAX_GROUP}")
                else:
                    self._choose(opt)
                return

    def _picker_draw(self, s: pygame.Surface) -> None:
        p = self.picker
        r = self._picker_rect()
        font = self.font
        card = self.play["inst"].card
        s.blit(self.ms.r.panel(r.w, r.h, base="#181425", border="#fee761"), r.topleft)
        font.draw(s, f"{card.name}: {PROMPTS.get(p['step'], '')}", r.x + 6, r.y + 6, "#fee761")
        s.blit(self.art.full(card.key, "", self.player), (r.x - CARD_W - 6, r.y))
        camp = self.camp
        for i, opt in enumerate(p["options"][p["scroll"]:p["scroll"] + self.ROWS]):
            row = self._picker_row(i)
            hot = row.collidepoint(self.ms._mouse)
            picked = opt in p["picked"]
            pygame.draw.rect(s, (58, 68, 102) if hot else (38, 43, 68), row)
            pygame.draw.rect(s, _c("#fee761") if picked else (90, 105, 136), row, 1)
            if p["step"] in RIVAL_STEPS:
                fac = FACTION[opt]
                s.blit(self.ms.shields[opt], (row.x + 2, row.y + 1))
                font.draw(s, fac.name, row.x + 20, row.y + 2, fac.light)
                rel = camp.relation(self.player, opt)
                extra = f"ОТНОШЕНИЯ {rel}" if opt != "goblin" else "ВЕЧНАЯ ВОЙНА"
                if camp.at_peace(self.player, opt):
                    extra += ", МИР"
                font.draw(s, extra + f"   ГОРОДОВ {len(camp.cities_of(opt))}   КАРТ В РУКЕ {len(camp.realms[opt].hand)}",
                          row.x + 20, row.y + 10, "#8b9bb4")
            else:
                o = OFFICER[opt]
                face = pygame.Rect(row.x + 2, row.y + 1, 14, 17)
                self.ms.cards.face(s, face, opt, click=False)
                font.draw(s, o.name, row.x + 20, row.y + 2, "#ffffff")
                city = CITY[camp.officer_city[opt]].name
                font.draw(s, f"{city}   МОЩЬ {camp.power(opt)}   ВЕРНОСТЬ {camp.loyalty[opt]}", row.x + 20, row.y + 10,
                          "#8b9bb4")
                if p["step"] in MULTI:
                    box = pygame.Rect(row.right - 12, row.y + 5, 9, 9)
                    pygame.draw.rect(s, INK, box)
                    pygame.draw.rect(s, _c("#c0cbdc"), box, 1)
                    if picked:
                        pygame.draw.rect(s, _c("#fee761"), box.inflate(-4, -4))
        n = len(p["options"])
        if n > self.ROWS:
            font.draw(s, f"{p['scroll'] + 1}-{min(n, p['scroll'] + self.ROWS)} ИЗ {n} (КОЛЕСО)", r.centerx,
                      r.bottom - 15, "#5a6988", anchor="midtop")
        for rect, action in self._picker_buttons():
            hot = rect.collidepoint(self.ms._mouse)
            base = "#3e8948" if action == "done" else "#a22633"
            if action == "done" and not p["picked"]:
                base = "#3a4466"
            s.blit(self.ms.r.panel(rect.w, rect.h, base=base, border="#c0cbdc" if hot else "#8b9bb4"), rect.topleft)
            font.draw(s, "ГОТОВО" if action == "done" else "ОТМЕНА", rect.centerx, rect.centery, "#ffffff",
                      anchor="center")
        # a storm's odds
        if p["step"] in ("attackers", "attackers_far", "attackers_port") and p["picked"]:
            target = self.play["chosen"][0]
            mult = {"blitz": 1.15}.get(card.key, 1.0)
            a = camp.attack_power(self.player, p["picked"], target, mult)
            d = camp.defense_power(target)
            if (camp.owner[target], self.player) in camp.grudge:
                d *= 1.3
            ch = camp.win_chance(a, d)
            col = "#63c74d" if ch >= 0.6 else "#feae34" if ch >= 0.4 else "#e43b44"
            font.draw(s, f"СИЛА {int(a)} ПРОТИВ {int(d)}: ШАНС {int(ch * 100)}%", r.centerx, r.bottom - 26, col,
                      anchor="midtop")

    # --- chronicle -----------------------------------------------------------------------------
    def _chron_rect(self) -> pygame.Rect:
        return self.ms.WIN

    def _chron_lines(self) -> List[Tuple[int, str, str, bool]]:
        out = []
        mine = set(self.camp.cities_of(self.player)) if self.player else set()
        for i, (turn, f, text) in enumerate(self.camp.log):
            hurt = self.player is not None and f != self.player and \
                (any(CITY[c].name in text for c in mine) or FACTION[self.player].short in text)
            out.append((turn, f, text, i >= self.chron_from, hurt))
        return out

    def _chronicle_handle(self, ev, mx, my) -> None:
        if ev.type == pygame.KEYDOWN and ev.key in (pygame.K_ESCAPE, pygame.K_RETURN, pygame.K_SPACE) or \
                ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 3:
            self.chronicle_open = False
        elif ev.type == pygame.MOUSEWHEEL:
            self.chron_scroll = self.chron_scroll + ev.y * 3            # clamped when drawn
        elif ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
            r = self._chron_rect()
            if not r.collidepoint(mx, my) or pygame.Rect(r.right - 16, r.y + 3, 12, 11).collidepoint(mx, my):
                self.chronicle_open = False

    def _chronicle_draw(self, s: pygame.Surface) -> None:
        from .mapview import wrap
        r = self._chron_rect()
        font = self.font
        s.blit(self.ms.r.panel(r.w, r.h, base="#181425", border="#c9a24a"), r.topleft)
        cr = pygame.Rect(r.right - 16, r.y + 3, 12, 11)
        pygame.draw.rect(s, (162, 38, 51), cr)
        font.draw(s, "X", cr.centerx + 1, cr.centery, "#ffffff", anchor="center")
        font.draw(s, f"ХРОНИКА - ХОД {self.camp.turn}", r.centerx, r.y + 4, "#fee761", anchor="midtop")
        font.draw(s, "НОВОЕ - ЯРКО, БЕДЫ ВАШЕЙ ДЕРЖАВЫ - КРАСНЫМ. КОЛЕСО - ЛИСТАТЬ, ESC - ЗАКРЫТЬ", r.centerx,
                  r.bottom - 10, "#5a6988", anchor="midtop")
        y = r.y + 17
        lines = self._chron_lines()
        rows = []
        for turn, f, text, new, hurt in lines:
            for j, line in enumerate(wrap(text, r.w - 70)):
                rows.append((turn if j == 0 else None, f if j == 0 else None, line, new, hurt))
        per = 23
        self.chron_scroll = max(0, min(self.chron_scroll, max(0, len(rows) - per)))
        start = max(0, len(rows) - per - self.chron_scroll)          # scroll 0 = the latest page
        for turn, f, line, new, hurt in rows[start:start + per]:
            if f:
                font.draw(s, f"{turn}", r.x + 8, y, "#5a6988")
                s.blit(self.ms.shields[f], (r.x + 24, y - 4))
            col = "#f6757a" if hurt else ("#ffffff" if new else "#8b9bb4")
            font.draw(s, line, r.x + 44, y, col)
            y += 8

    # --- council ---------------------------------------------------------------------------------
    def _seat_rect(self, i: int) -> pygame.Rect:
        r = self.ms.WIN
        return pygame.Rect(r.x + 6, r.y + 18 + i * 31, 200, 29)

    def _cand_rect(self, i: int) -> pygame.Rect:
        r = self.ms.WIN
        return pygame.Rect(r.x + 336, r.y + 30 + i * 19, r.right - r.x - 342, 18)

    def _tab_rect(self, tab: str) -> pygame.Rect:
        r = self.ms.WIN
        return pygame.Rect(r.x + 336 + (0 if tab == "officers" else 64), r.y + 16, 62, 12)

    CROWS = 9

    def _council(self) -> List[str]:
        return list(self.camp.realms[self.player].council)

    def _candidates(self) -> List[str]:
        f = self.player
        from .faces import presence
        council = self._council()
        offs = [o for o in self.camp.officers_of(f) if o.key not in council]
        return [o.key for o in sorted(offs, key=lambda o: -presence(o))]

    def _deck_rows(self) -> List[Tuple[str, int, str]]:
        r = self.camp.realms[self.player]
        from collections import Counter
        cnt = Counter((c.key, c.origin) for c in r.all_cards())
        rows = sorted(cnt.items(), key=lambda kv: (["faction", "unique", "strong", "moderate", "basic", "junk",
                                                     "curse"].index(CARDS[kv[0][0]].tier), CARDS[kv[0][0]].name))
        return [(k, n, o) for (k, o), n in rows]

    def open_council(self) -> None:
        if self.player is None:
            self.ms._say("В РЕЖИМЕ ЗРИТЕЛЯ СОВЕТА НЕТ")
            return
        self.council_open = True
        self.council_seat = None
        self.council_scroll = 0

    def _council_handle(self, ev, mx, my) -> None:
        r = self.ms.WIN
        if ev.type == pygame.KEYDOWN and ev.key in (pygame.K_ESCAPE, pygame.K_c) or \
                ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 3:
            self.council_open = False
            return
        if ev.type == pygame.MOUSEWHEEL:
            n = len(self._candidates()) if self.council_tab == "officers" else len(self._deck_rows())
            self.council_scroll = max(0, min(max(0, n - self.CROWS), self.council_scroll - ev.y))
            return
        if ev.type != pygame.MOUSEBUTTONDOWN or ev.button != 1:
            return
        if not r.collidepoint(mx, my) or pygame.Rect(r.right - 16, r.y + 3, 12, 11).collidepoint(mx, my):
            self.council_open = False
            return
        if self._course_button().collidepoint(mx, my):
            self.course_open = True
            return
        for tab in ("officers", "deck"):
            if self._tab_rect(tab).collidepoint(mx, my):
                self.council_tab = tab
                self.council_scroll = 0
                return
        council = self._council()
        for i in range(COUNCIL_SEATS):
            rect = self._seat_rect(i)
            if rect.collidepoint(mx, my):
                if i == 0:
                    self.ms._say("ГЛАВА ФРАКЦИИ ВСЕГДА В СОВЕТЕ")
                    return
                x = pygame.Rect(rect.right - 11, rect.y + 2, 9, 9)
                if x.collidepoint(mx, my) and i < len(council):
                    self._set(council[:i] + council[i + 1:])
                    return
                self.council_seat = None if self.council_seat == i else i
                return
        if self.council_tab == "officers":
            for i, key in enumerate(self._candidates()[self.council_scroll:self.council_scroll + self.CROWS]):
                if self._cand_rect(i).collidepoint(mx, my):
                    seat = self.council_seat
                    if seat is not None and seat < len(council):
                        members = council[:seat] + [key] + council[seat + 1:]
                    elif len(council) < COUNCIL_SEATS:
                        members = council + [key]
                    else:
                        self.ms._say("ВЫБЕРИТЕ МЕСТО В СОВЕТЕ, КОГО ЗАМЕНИТЬ")
                        return
                    self._set(members)
                    return

    def _set(self, members: Sequence[str]) -> None:
        if not self.my_turn():
            self.ms._say("СОВЕТ МЕНЯЮТ В СВОЙ ХОД")
            return
        ok, why = self.camp.can_set_council(self.player, members)
        if not ok:
            self.ms._say(why)
            return
        self.camp.set_council(self.player, members)
        self.council_seat = None
        self.ms._say("СОВЕТ ОБНОВЛЁН: КОЛОДА ПЕРЕСОБРАНА", "#a7f070")

    def _council_draw(self, s: pygame.Surface) -> None:
        from .mapview import wrap
        r = self.ms.WIN
        font = self.font
        f = FACTION[self.player]
        mouse = self.ms._mouse
        self.hover_card = None
        s.blit(self.ms.r.panel(r.w, r.h, base="#181425", border=f.color), r.topleft)
        cr = pygame.Rect(r.right - 16, r.y + 3, 12, 11)
        pygame.draw.rect(s, (162, 38, 51), cr)
        font.draw(s, "X", cr.centerx + 1, cr.centery, "#ffffff", anchor="center")
        font.draw(s, f"СОВЕТ - {f.name}", r.centerx, r.y + 4, "#fee761", anchor="midtop")
        council = self._council()
        # seats
        for i in range(COUNCIL_SEATS):
            rect = self._seat_rect(i)
            sel = i == self.council_seat
            pygame.draw.rect(s, (58, 68, 102) if sel else (38, 43, 68), rect)
            pygame.draw.rect(s, _c("#fee761") if sel else (90, 105, 136), rect, 1)
            if i >= len(council):
                font.draw(s, "+ ПУСТОЕ МЕСТО: ВЫБЕРИТЕ СПРАВА", rect.centerx, rect.centery, "#3a4466", anchor="center")
                continue
            key = council[i]
            o = OFFICER[key]
            self.ms.cards.face(s, pygame.Rect(rect.x + 2, rect.y + 2, 21, 25), key)
            self.ms.cards.name(s, key, rect.x + 27, rect.y + 2)
            font.draw(s, f"ВЕРН. {self.camp.loyalty[key]}", rect.right - (14 if i else 4), rect.y + 2, "#8b9bb4",
                      anchor="topright")
            cards = list(PERSONAL[key])
            if i == 0:
                from .cards import FACTION_CARD
                cards = [FACTION_CARD[self.player]]
            x, y = rect.x + 27, rect.y + 11
            for k in cards:
                chip = self.art.chip(k)
                if x + chip.get_width() > rect.right - 4:
                    x, y = rect.x + 27, y + 8
                s.blit(chip, (x, y))
                if pygame.Rect(x, y, chip.get_width(), 7).collidepoint(mouse):
                    self.hover_card = (k, o.name)
                x += chip.get_width() + 4
            if i:
                xr = pygame.Rect(rect.right - 11, rect.y + 2, 9, 9)
                pygame.draw.rect(s, (162, 38, 51), xr)
                font.draw(s, "X", xr.centerx + 1, xr.centery, "#ffffff", anchor="center")
        # competence
        comp = competence(council)
        y = r.y + 18 + COUNCIL_SEATS * 31 + 2
        font.draw(s, f"КОМПЕТЕНТНОСТЬ: {comp} ПОРОГОВ ИЗ 12", r.x + 6, y, "#fee761")
        perks = [f"РУКА {hand_size(council)} КАРТ"]
        n = reserve(council)
        perks.append(f"МОЖНО ОСТАВИТЬ {n}" if n else "КАРТЫ НЕ ОСТАЮТСЯ")
        if intercepts(council):
            perks.append("ЛОВИТ ШПИОНОВ")
        col = "#a7f070"
        if strife(council):
            perks.append("РАСПРИ!")
            col = "#f6757a"
        for j, line in enumerate(wrap(", ".join(perks), 200)):
            font.draw(s, line, r.x + 6, y + 9 + j * 8, col)
        cb = self._course_button()
        hot = cb.collidepoint(mouse)
        realm = self.camp.realms[self.player]
        s.blit(self.ms.r.panel(cb.w, cb.h, base="#5a6988" if hot else "#3a2a10", border="#fee761"), cb.topleft)
        cd = f", ЗАМОК {realm.course_cd} Х." if realm.course_cd else ""
        font.draw(s, f"КУРС: {COURSES[realm.course].name}{cd}", cb.centerx, cb.centery, "#fee761", anchor="center")
        # thresholds
        x0 = r.x + 214
        font.draw(s, "НАВЫКИ СОВЕТА", x0, r.y + 18, "#fee761")
        totals = council_totals(council)
        for i, st in enumerate(STATS):
            yy = r.y + 27 + i * 29
            v = totals[st]
            mid, top = THRESHOLD_CARDS[st]
            font.draw(s, st, x0, yy, "#c0cbdc")
            font.draw(s, str(v), x0 + 116, yy, "#ffffff", anchor="topright")
            bar = pygame.Rect(x0, yy + 8, 116, 4)
            pygame.draw.rect(s, (38, 43, 68), bar)
            pygame.draw.rect(s, _c("#41a6f6"), (bar.x, bar.y, int(bar.w * min(1, v / 100)), bar.h))
            for t in THRESHOLDS:
                tx = bar.x + int(bar.w * t / 100)
                pygame.draw.line(s, _c("#fee761"), (tx, bar.y - 1), (tx, bar.bottom))
            for k, (card, need) in enumerate(((mid, THRESHOLDS[0]), (top, THRESHOLDS[1]))):
                got = v >= need
                chip = self.font.render(f"{need}: {CARDS[card].name}", TIER_COLOR[CARDS[card].tier] if got
                                        else "#3a4466")
                cy = yy + 13 + k * 7
                s.blit(chip, (x0, cy), area=pygame.Rect(0, 0, 118, 8))
                if pygame.Rect(x0, cy, 118, 7).collidepoint(mouse):
                    self.hover_card = (card, f"ПОРОГ {need}")
        # right: candidates or deck
        for tab, label in (("officers", "ОФИЦЕРЫ"), ("deck", "КОЛОДА")):
            tr = self._tab_rect(tab)
            pygame.draw.rect(s, (58, 68, 102) if self.council_tab == tab else (38, 43, 68), tr)
            font.draw(s, label, tr.centerx, tr.centery, "#ffffff", anchor="center")
        tip = None
        if self.council_tab == "officers":
            cands = self._candidates()
            for i, key in enumerate(cands[self.council_scroll:self.council_scroll + self.CROWS]):
                row = self._cand_rect(i)
                hot = row.collidepoint(mouse)
                pygame.draw.rect(s, (58, 68, 102) if hot else (38, 43, 68), row)
                self.ms.cards.face(s, pygame.Rect(row.x + 1, row.y + 1, 13, 16), key)
                o = OFFICER[key]
                font.draw(s, o.name, row.x + 17, row.y + 1, "#ffffff", )
                labels = PERSONAL[key]
                best = max(labels, key=lambda k: ["junk", "basic", "moderate", "strong", "unique"].index(
                    CARDS[k].tier) if CARDS[k].tier in ("junk", "basic", "moderate", "strong", "unique") else 0) \
                    if labels else None
                if best:
                    chip = self.art.chip(best)
                    s.blit(chip, (row.x + 17, row.y + 9), area=pygame.Rect(0, 0, row.w - 20, 8))
                    if hot:
                        self.hover_card = (best, o.name)
                if hot:
                    tip = f"{o.name}: НАВЫКИ " + " ".join(str(v) for v in o.stats) + "  КАРТЫ: " + \
                          ", ".join(CARDS[k].name for k in labels)
            if len(cands) > self.CROWS:
                font.draw(s, f"{self.council_scroll + 1}-{min(len(cands), self.council_scroll + self.CROWS)} ИЗ "
                             f"{len(cands)}", r.right - 6, r.y + 18 + 12 + self.CROWS * 19, "#5a6988",
                          anchor="topright")
            if tip is None and self.council_seat is not None:
                tip = "КЛИК ПО ОФИЦЕРУ СПРАВА - НА ВЫБРАННОЕ МЕСТО"
        else:
            rows = self._deck_rows()
            total = sum(n for _, n, _ in rows)
            font.draw(s, f"ВСЕГО {total}", r.right - 6, r.y + 18, "#8b9bb4", anchor="topright")
            for i, (key, n, origin) in enumerate(rows[self.council_scroll:self.council_scroll + self.CROWS]):
                row = self._cand_rect(i)
                hot = row.collidepoint(mouse)
                pygame.draw.rect(s, (58, 68, 102) if hot else (38, 43, 68), row)
                s.blit(self.art.chip(key), (row.x + 3, row.y + 1))
                font.draw(s, f"x{n}" if n > 1 else "", row.right - 3, row.y + 1, "#ffffff", anchor="topright")
                font.draw(s, origin_label(origin), row.x + 3, row.y + 9, "#5a6988")
                if hot:
                    self.hover_card = (key, origin_label(origin))
        text, colr, until = self.ms.toast
        if tip:
            font.draw(s, tip, r.centerx, r.bottom - 10, "#c0cbdc", anchor="midtop")
        elif self.ms.time < until:
            font.draw(s, text, r.centerx, r.bottom - 10, colr, anchor="midtop")
        else:
            font.draw(s, "МЕСТО СЛЕВА - ВЫБРАТЬ, X - ОСВОБОДИТЬ. СМЕНА СОВЕТА ПЕРЕСОБИРАЕТ КОЛОДУ", r.centerx,
                      r.bottom - 10, "#5a6988", anchor="midtop")
        if self.hover_card:                            # shown over the stats column: no portraits there
            key, label = self.hover_card
            img = self.art.full(key, label, self.player)
            x = r.x + 228 if mouse[0] > r.x + 330 or mouse[0] < r.x + 210 else r.x + 6 + 200 - CARD_W
            y = r.y + 30
            if x < r.x + 210:                          # over the seats: their portraits must give way
                self.ms.cards.cover()
            s.blit(img, (x, y))
            if label:
                self.font.draw(s, label, x + CARD_W // 2, y + CARD_H + 2, "#c0cbdc", anchor="midtop")

    # --- course of the realm ------------------------------------------------------------------------
    def _course_button(self) -> pygame.Rect:
        r = self.ms.WIN
        return pygame.Rect(r.x + 6, r.y + 200, 200, 13)

    def _course_row(self, i: int) -> pygame.Rect:
        r = self.ms.WIN
        return pygame.Rect(r.x + 6, r.y + 40 + i * 34, r.w - 12, 32)

    def _course_handle(self, ev, mx, my) -> None:
        r = self.ms.WIN
        if ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE or \
                ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 3:
            self.course_open = False
            return
        if ev.type != pygame.MOUSEBUTTONDOWN or ev.button != 1:
            return
        if not r.collidepoint(mx, my) or pygame.Rect(r.right - 16, r.y + 3, 12, 11).collidepoint(mx, my):
            self.course_open = False
            return
        for i, key in enumerate(COURSES):
            if self._course_row(i).collidepoint(mx, my):
                ok, why = self.camp.can_change_course(self.player, key)
                if not ok:
                    self.ms._say(why)
                    return
                self.camp.change_course(self.player, key)
                self.ms._say(f"НОВЫЙ КУРС: {COURSES[key].name}. КАРТЫ ОСНОВЫ ЗАМЕНЕНЫ", "#a7f070")
                self.course_open = False
                return

    def _course_draw(self, s: pygame.Surface) -> None:
        from .mapview import wrap
        r = self.ms.WIN
        font = self.font
        realm = self.camp.realms[self.player]
        mouse = self.ms._mouse
        s.blit(self.ms.r.panel(r.w, r.h, base="#181425", border="#c9a24a"), r.topleft)
        cr = pygame.Rect(r.right - 16, r.y + 3, 12, 11)
        pygame.draw.rect(s, (162, 38, 51), cr)
        font.draw(s, "X", cr.centerx + 1, cr.centery, "#ffffff", anchor="center")
        font.draw(s, "КУРС ДЕРЖАВЫ: КАКИЕ 5 КАРТ ОСНОВЫ ЛЕЖАТ В КОЛОДЕ", r.centerx, r.y + 4, "#fee761",
                  anchor="midtop")
        cd = course_cooldown(realm.council)
        from .cards import council_totals
        gov = council_totals(realm.council)["УПРАВЛЕНИЕ"]
        now = "МОЖНО СМЕНИТЬ СЕЙЧАС" if realm.course_cd == 0 else f"СМЕНИТЬ МОЖНО ЧЕРЕЗ {realm.course_cd} Х."
        font.draw(s, f"{now}. ПОСЛЕ СМЕНЫ КУРС ЗАКРЕПЛЁН НА {cd} Х. (УПРАВЛЕНИЕ СОВЕТА {gov}: ЧЕМ ВЫШЕ, ТЕМ "
                     f"КОРОЧЕ)", r.centerx, r.y + 16, "#a7f070" if realm.course_cd == 0 else "#feae34",
                  anchor="midtop")
        font.draw(s, "СМЕНА КУРСА СРАЗУ МЕНЯЕТ КАРТЫ ОСНОВЫ ВЕЗДЕ, ДАЖЕ В РУКЕ", r.centerx, r.y + 26, "#5a6988",
                  anchor="midtop")
        hover = None
        for i, (key, c) in enumerate(COURSES.items()):
            row = self._course_row(i)
            cur = key == realm.course
            hot = row.collidepoint(mouse)
            pygame.draw.rect(s, (58, 68, 102) if hot else (38, 43, 68), row)
            pygame.draw.rect(s, _c("#fee761") if cur else (90, 105, 136), row, 2 if cur else 1)
            font.draw(s, c.name + (" (СЕЙЧАС)" if cur else ""), row.x + 5, row.y + 3, "#fee761" if cur else "#ffffff")
            x = row.x + 110
            from collections import Counter
            for k, n in Counter(c.base).items():
                chip = self.art.chip(k)
                s.blit(chip, (x, row.y + 3))
                if pygame.Rect(x, row.y + 3, chip.get_width(), 7).collidepoint(mouse):
                    hover = k
                x += chip.get_width() + 2
                if n > 1:
                    font.draw(s, f"x{n}", x, row.y + 3, "#ffffff")
                    x += 12
                x += 6
            font.draw(s, "+ " + c.plus, row.x + 5, row.y + 12, "#63c74d")
            for j, line in enumerate(wrap("- " + c.minus, row.w - 10)[:2]):
                font.draw(s, line, row.x + 5, row.y + 20 + j * 7, "#f6757a")
        text, colr, until = self.ms.toast
        if self.ms.time < until:
            font.draw(s, text, r.centerx, r.bottom - 10, colr, anchor="midtop")
        if hover:
            mx, my = mouse
            img = self.art.full(hover, "ОСНОВА", self.player)
            s.blit(img, (min(mx + 8, W - CARD_W - 2), max(2, min(H - CARD_H - 2, my - CARD_H // 2))))
