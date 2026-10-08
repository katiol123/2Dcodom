"""Cards on the world map: card art, the hand, targeting, the council and the chronicle.

``CardTable`` sits on top of ``WorldMapScreen``: it draws the player's hand along the bottom,
the end-turn button and the action points, walks the player through a card's targets (cities
are clicked on the map, officers and realms are picked from a list), and owns two windows:
the council (who sits in it, its stat thresholds, its deck) and the chronicle of what every
realm did. In spectator mode it only advances the rounds.
"""

from __future__ import annotations

import math
from typing import Dict, List, Optional, Sequence, Tuple

import pygame

from pixelforge.text import text_width

from .cardplay import MAX_GROUP, MULTI
from .cards import CARDS, COUNCIL_SEATS, COURSES, KIND_NAMES, STATS, THRESHOLD_CARDS, THRESHOLDS, TIER_NAMES
from .factions import CITY, FACTION
from .officers import OFFICER
from .render import INK, _c
from .sim import H, W

CARD_W, CARD_H = 88, 128
TIER_COLOR = {"basic": "#8b9bb4", "junk": "#5a6988", "moderate": "#41a6f6", "strong": "#feae34",
              "unique": "#e07ad8", "faction": "#fee761", "curse": "#e43b44", "vice": "#b86f50",
              "feat": "#ffd36b", "fate": "#7a9e48"}
KIND_COLOR = {"economy": ("#c9a24a", "#4a3a14"), "military": ("#e43b44", "#4a1418"),
              "intrigue": ("#b07ad8", "#2e1a40"), "diplomacy": ("#5fb7d9", "#14304a"),
              "council": ("#63c74d", "#173a1a"), "recruit": ("#d08a4a", "#3e2414"),
              "curse": ("#e43b44", "#1a0a0e"), "vice": ("#b86f50", "#2a1610")}

CITY_STEPS = {"own_city", "own_city_officers", "own_city_pair", "own_city_pair2", "dest_adj", "dest_2", "enemy_built",
              "dest_any", "dest_any_one", "enemy_adj", "enemy_adj_any", "enemy_reach", "enemy_port",
              "enemy_city", "enemy_city_officers", "city_buyable", "enemy_town", "enemy_lair"}
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
    "hand_card": "КАКУЮ КАРТУ СЖЕЧЬ НАВСЕГДА", "city_buyable": "КАКОЙ ГОРОД КУПИТЬ",
    "building": "ЧТО ПОСТРОИТЬ", "enemy_built": "ГДЕ РУШИТЬ",
    "enemy_town": "КАКОЙ ВРАЖЕСКИЙ ГОРОД", "enemy_lair": "КАКОЕ ЛОГОВО",
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
    elif kind == "vice":                                      # a goblet tipped over
        pygame.draw.polygon(s, d, [(4, 4), (18, 4), (13, 12), (9, 12)])
        pygame.draw.polygon(s, c, [(6, 5), (16, 5), (12, 11), (10, 11)])
        pygame.draw.rect(s, d, (9, 12, 4, 6))
        pygame.draw.rect(s, d, (5, 17, 12, 3))
        pygame.draw.rect(s, c, (6, 18, 10, 1))
        pygame.draw.circle(s, (160, 30, 40), (17, 15), 2)
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
        if card.gold:                                        # a coin and the price (a "З" read as a 3)
            r = self.font.draw(s, str(card.gold), band.right - 2, band.y + 2, "#fee761", anchor="topright")
            pygame.draw.circle(s, INK, (r.x - 5, r.y + 3), 4)
            pygame.draw.circle(s, _c("#feae34"), (r.x - 5, r.y + 3), 3)
            s.set_at((r.x - 6, r.y + 2), _c("#fee761"))
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
    return {"base": "ДЕРЖАВА", "faction": "ПРАВИТЕЛЬ", "threshold": "СОВЕТ", "curse": "ПРОКЛЯТИЕ",
            "stolen": "ДОБЫЧА", "legacy": "НАСЛЕДИЕ"}.get(origin, "")


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
        self.arrows_from = 0                            # storms shown as arrows on the map
        self.council_seat: Optional[int] = None
        self.council_tab = "officers"
        self.council_scroll = 0
        self.hover_card: Optional[Tuple[str, str]] = None   # (card key, origin) shown big
        self.auto = False
        self.auto_t = 0.0
        self.hand_hover: Optional[int] = None
        self.seen_ids: set = set()                      # hand cards already dealt (animations)
        self.dealing: Dict[int, float] = {}             # card id -> time its flight from the deck starts
        self.sounded: set = set()
        self.launch = None                              # (inst, rect, image) of the card being played
        self.last_req = None

    # --- state -----------------------------------------------------------------------------
    @property
    def player(self) -> Optional[str]:
        return self.camp.player

    def watching(self) -> bool:
        """A spectator - or a player whose realm has fallen: the world goes on, round by round."""
        return self.player is None or not self.camp.realms[self.player].alive

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

    def deck_rect(self) -> pygame.Rect:
        e = self.end_rect()
        return pygame.Rect(e.x - 54, e.y - 2, 22, 32)

    def discard_rect(self) -> pygame.Rect:
        e = self.end_rect()
        return pygame.Rect(e.x - 28, e.y - 2, 22, 32)

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
        if self.watching():
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
        n = self.camp.reserve(r.council)
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
        """The next step's choices - only those that can still lead to a whole set of targets."""
        from .cardplay import MULTI as _MULTI, completable
        key, chosen = self.play["inst"].key, self.play["chosen"]
        opts = self.camp.options(self.player, key, chosen)
        multi = self._step() in _MULTI
        return [o for o in opts if completable(self.camp, self.player, key, chosen + [(o,) if multi else o])]

    def _advance(self) -> None:
        """Ask for the next target, or play the card when all are chosen."""
        step = self._step()
        if step is None:
            inst = self.play["inst"]
            chosen = list(self.play["chosen"])
            self.play = None
            hand = self.hand()
            rects = self.hand_rects()
            rect = rects[hand.index(inst)] if inst in hand else self.deck_rect()
            self.launch = (inst, pygame.Rect(rect), self.art.full(inst.key, origin_label(inst.origin), self.player))
            self.attacks_before = len(self.camp.attacks)
            self.ms.run(lambda: self.camp.play(self.player, inst, chosen), ("play", inst.card.name))
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
            if self.watching():
                self.next_round()
            elif not self.ms.runner.busy():               # a realm come back to life: let the others play up to it
                self.ms.run(self.camp.run_ai, ("end", ""))
            return
        self.cancel()
        self.chron_from = len(self.camp.log)
        self.arrows_from = len(self.camp.attacks)

        def turn():
            self.camp.end_turn()
            self.camp.run_ai()
        self.ms.run(turn, ("end", ""))

    def next_round(self) -> None:
        """Spectator: every realm plays once."""
        self.chron_from = len(self.camp.log)
        self.arrows_from = len(self.camp.attacks)
        # a fallen player watches round by round; should his realm rise again, the round stops at his turn
        self.ms.run(lambda: self.camp.run_ai(stop_at_player=self.player is not None, max_turns=1), ("round", ""))

    def finished(self, what, result) -> None:
        """A background action is over: say what came of it."""
        kind, name = what
        status, value = result
        if status == "error":
            self.ms._say("ОШИБКА: " + value.strip().splitlines()[-1][:60])
            return
        if kind == "play":
            ok, msg = value
            if self.launch and ok:
                from .fx import PlayShow
                inst, rect, img = self.launch
                hi, _ = KIND_COLOR[inst.card.kind]
                self.ms.fx.add(PlayShow(self.ms, img, rect, inst.card.kind, hi,
                                        inst.origin if inst.origin in OFFICER else None, msg, ok,
                                        self.discard_rect))
                self.storm_flashes(getattr(self, "attacks_before", len(self.camp.attacks)), delay=1.1)
            else:
                self.ms._say(f"{name}: {msg}" if ok and msg else (name if ok else msg), "#a7f070" if ok else "#e43b44")
                from .audio import ui
                ui("refuse")
            self.launch = None
        elif kind == "end":
            self.chronicle_open = True
            self.chron_scroll = 0
            self.storm_flashes(self.arrows_from, delay=0.2, gap=0.25)

    def storm_flashes(self, since: int, delay: float = 0.0, gap: float = 0.0) -> None:
        """Rings and sparks over the cities stormed since ``since`` (taken: the stormer's colour,
        held: red), with war drums."""
        from .fx import Ring, Sparks
        storms = self.camp.attacks[since:]
        for j, (_, by, _, city, won) in enumerate(storms[-12:]):
            c = CITY[city]
            x, y = self.ms._to_screen(c.x, c.y - 8)
            col = FACTION[by].light if won else "#e43b44"
            d = delay + j * gap
            self.ms.fx.add(Ring(x, y, col, 3, 24, 0.5, delay=d))
            self.ms.fx.add(Sparks(x, y, col, 14, 50, delay=d))
        if storms:
            self.ms.fx.add(Ring(-50, -50, "#000000", 1, 2, 0.1, delay=delay)).cues = [(0.0, "drums")]

    # --- requests from a running action: watch a battle? answer a storm? ------------------------
    def _req_rect(self) -> pygame.Rect:
        from .mapview import TOP
        if self.ms.focus is not None:                     # a storm on the map: the question sits beside the city
            req = self.ms.runner.request
            h = 66 if req and req["kind"] == "ask" else 180
            x = 6 if self.ms.focus.get("left") else W - 326
            return pygame.Rect(x, TOP + 34, 320, h)           # under the battle's banner
        return pygame.Rect(W // 2 - 160, 36, 320, 180)

    def _req_buttons(self, req) -> List[Tuple[pygame.Rect, object]]:
        r = self._req_rect()
        if req["kind"] == "diplo":
            return [(pygame.Rect(r.x + 40, r.bottom - 22, 110, 15), True),
                    (pygame.Rect(r.right - 150, r.bottom - 22, 110, 15), False)]
        if req["kind"] == "ask":
            labels = [("СМОТРЕТЬ БОЙ", "watch"), ("РАССЧИТАТЬ", "calc"), ("ВСЕГДА СЧИТАТЬ", "never")]
            return [(pygame.Rect(r.x + 8 + i * 102, r.bottom - 22, 98, 15), v) for i, (_, v) in enumerate(labels)]
        out = [(pygame.Rect(r.x + 8 + i * 70, r.y + 42, 66, 96), c) for i, c in enumerate(req["cards"][:3])]
        out.append((pygame.Rect(r.x + 8, r.bottom - 22, 98, 15), None))
        return out

    def handle_request(self, ev, mouse) -> None:
        req = self.ms.runner.request
        if not req or req["kind"] == "battle":
            return
        mx, my = mouse
        if ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE:
            self.ms.runner.reply("calc" if req["kind"] == "ask" else False if req["kind"] == "diplo" else None)
            return
        if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
            for rect, value in self._req_buttons(req):
                if rect.collidepoint(mx, my):
                    if req["kind"] == "diplo":
                        from .audio import ui
                        ui("harp" if value else "refuse")
                    self.ms.runner.reply(value)
                    return

    def draw_request(self, s: pygame.Surface) -> None:
        req = self.ms.runner.request
        if req is not self.last_req:
            self.last_req = req
            if req:
                from .audio import ui
                ui({"answer": "drums", "diplo": "horn", "ask": "drums"}.get(req["kind"], ""))
        if not req or req["kind"] == "battle":
            return
        if req["kind"] == "diplo":
            return self._draw_diplo(s, req)
        b = req["battle"]
        camp = self.camp
        font = self.font
        r = self._req_rect()
        if self.ms.focus is None:                         # with a storm on the map the city stays in plain sight
            s.blit(self.ms.dim, (0, 0))
        mine = req["kind"] == "answer"
        s.blit(self.ms.r.panel(r.w, r.h, base="#181425", border="#e43b44" if mine else "#c9a24a"), r.topleft)
        a = camp.attack_power(b.attacker, b.officers, b.city, b.mult)
        d = camp.defense_power(b.city) * b.def_mult
        p = camp.win_chance(a, d)
        att, deff = FACTION[b.attacker], FACTION[b.defender]
        title = "НА ВАШ ГОРОД НАПАЛИ!" if mine else "БОЙ ДРУГИХ ДЕРЖАВ"
        font.draw(s, title, r.centerx, r.y + 5, "#f6757a" if mine else "#fee761", anchor="midtop")
        font.draw(s, f"{att.short} ШТУРМУЕТ {CITY[b.city].name} ({deff.short})", r.centerx, r.y + 16, att.light,
                  anchor="midtop")
        odds = f"СИЛА {int(a)} ПРОТИВ {int(d)}: " + (f"ШАНС УДЕРЖАТЬ {int((1 - p) * 100)}%" if mine
                                                       else f"ШАНС ШТУРМА {int(p * 100)}%")
        font.draw(s, odds, r.centerx, r.y + 26, "#c0cbdc", anchor="midtop")
        mouse = self.ms._mouse
        preview = None
        for rect, value in self._req_buttons(req):
            hot = rect.collidepoint(mouse)
            if mine and value is not None:                 # a crisp little card: name and cost (preview at full size)
                card = value.card
                s.blit(self.ms.r.panel(rect.w, rect.h, base="#1c1830", border=TIER_COLOR[card.tier]), rect.topleft)
                pygame.draw.circle(s, INK, (rect.x + 9, rect.y + 9), 6)
                pygame.draw.circle(s, _c("#124e89") if card.cost else _c("#3a4466"), (rect.x + 9, rect.y + 9), 5)
                self.font.draw(s, str(card.cost), rect.x + 9, rect.y + 9, "#ffffff", anchor="center")
                from .mapview import wrap
                for i, line in enumerate(wrap(card.name, rect.w - 8)[:3]):
                    self.font.draw(s, line, rect.centerx, rect.y + 20 + i * 8, "#fee761", anchor="midtop")
                s.blit(_icon(card.kind, KIND_COLOR[card.kind][0]), (rect.centerx - 11, rect.y + 48))
                self.font.draw(s, "ОТВЕТ", rect.centerx, rect.bottom - 11, "#8b9bb4", anchor="midtop")
                if hot or preview is None:
                    preview = value
                if hot:
                    pygame.draw.rect(s, _c("#fee761"), rect.inflate(2, 2), 1)
                continue
            label = {"watch": "СМОТРЕТЬ БОЙ", "calc": "РАССЧИТАТЬ", "never": "ВСЕГДА СЧИТАТЬ", None: "НЕ ОТВЕЧАТЬ"}[
                value if not hasattr(value, "key") else None]
            base = "#3e8948" if value == "watch" else "#a22633" if value is None else "#3a4466"
            s.blit(self.ms.r.panel(rect.w, rect.h, base="#5a6988" if hot else base, border="#c0cbdc"), rect.topleft)
            font.draw(s, label, rect.centerx, rect.centery, "#ffffff", anchor="center")
        if mine:
            font.draw(s, "КЛИК ПО КАРТЕ - ОТВЕТИТЬ ЕЮ", r.x + 8, r.bottom - 32, "#8b9bb4")
            if preview is not None:
                s.blit(self.art.full(preview.key, "ОТВЕТ", self.player), (r.right - CARD_W - 8, r.y + 40))

    def _draw_diplo(self, s: pygame.Surface, req) -> None:
        """A realm's envoys: their offer and what they say for it; accept or refuse."""
        from .diplomacy import KIND_NAMES, TRUCE_TURNS, ALLIANCE_TURNS, for_recipient, tier
        font = self.font
        r = self._req_rect()
        frm = FACTION[req["from"]]
        s.blit(self.ms.dim, (0, 0))
        s.blit(self.ms.r.panel(r.w, r.h, base="#181425", border=frm.color), r.topleft)
        s.blit(self.ms.shields[frm.key], (r.x + 8, r.y + 6))
        font.draw(s, f"ПОСЛЫ: {frm.name}", r.x + 26, r.y + 6, frm.light)
        kind = req["treaty"]
        what = {"truce": f"МИР НА {TRUCE_TURNS} Х.: НИКТО НЕ НАПАДАЕТ",
                "alliance": f"СОЮЗ НА {ALLIANCE_TURNS} Х.: МИР, ПОМОЩЬ ОТРЯДАМИ В БОЯХ ДРУГ ДРУГА",
                "trade": "ТОРГОВЛЯ НА 8 Х.: ЗОЛОТО ОБЕИМ СТОРОНАМ КАЖДЫЙ ХОД"}[kind]
        font.draw(s, f"ПРЕДЛАГАЮТ: {KIND_NAMES[kind]}", r.x + 26, r.y + 15, "#fee761")
        font.draw(s, what, r.x + 8, r.y + 27, "#ffffff")
        v = self.camp.relation(self.player, frm.key)
        _, name, col = tier(v)
        font.draw(s, f"ВАШИ ОТНОШЕНИЯ: {v} ({name}), ГОРОДОВ У НИХ {len(self.camp.cities_of(frm.key))}, "
                     f"АРМИЯ {self.camp.army(frm.key)}", r.x + 8, r.y + 36, col)
        font.draw(s, "ЧТО ГОВОРЯТ ВАШИ СОВЕТНИКИ (+ ЗА, - ПРОТИВ):", r.x + 8, r.y + 48, "#8b9bb4")
        y = r.y + 57
        for text, val in sorted(for_recipient(req["reasons"]), key=lambda t: -abs(t[1]))[:9]:
            font.draw(s, f"{val:+d}", r.x + 24, y, "#63c74d" if val > 0 else "#e43b44", anchor="topright")
            font.draw(s, text, r.x + 28, y, "#c0cbdc")
            y += 7
        font.draw(s, "ОТКАЗ НЕМНОГО ЗАДЕНЕТ ИХ (ОТНОШЕНИЯ -2)", r.centerx, r.bottom - 32, "#5a6988", anchor="midtop")
        mouse = self.ms._mouse
        for rect, value in self._req_buttons(req):
            hot = rect.collidepoint(mouse)
            base = "#3e8948" if value else "#a22633"
            s.blit(self.ms.r.panel(rect.w, rect.h, base="#5a6988" if hot else base, border="#c0cbdc"), rect.topleft)
            font.draw(s, "ПРИНЯТЬ" if value else "ОТКАЗАТЬ", rect.centerx, rect.centery, "#ffffff", anchor="center")

    def _deal_check(self) -> None:
        """New cards in the hand fly in from the deck, one after another."""
        hand = self.hand()
        ids = {c.id for c in hand}
        self.seen_ids &= ids
        self.sounded &= ids
        new = [c for c in hand if c.id not in self.seen_ids]
        now = self.ms.time
        start = max([now] + [t + 0.09 for t in self.dealing.values()])
        for j, c in enumerate(new):
            self.seen_ids.add(c.id)
            self.dealing[c.id] = start + 0.09 * j
        for cid, t in list(self.dealing.items()):
            if cid not in ids or now - t > self.DEAL:
                del self.dealing[cid]

    DEAL = 0.4

    def back(self) -> pygame.Surface:
        """The back of the realm's cards: its shield on a patterned field."""
        key = ("back", self.player)
        if key not in self.art.cache:
            f = FACTION[self.player] if self.player else None
            img = self.ms.r.panel(CARD_W, CARD_H, base="#1c1830", border="#c9a24a").copy()
            col = _c(f.color if f else "#5a6988")
            light = _c(f.light if f else "#8b9bb4")
            inner = pygame.Rect(5, 5, CARD_W - 10, CARD_H - 10)
            pygame.draw.rect(img, col, inner, 1)
            for y in range(inner.y + 4, inner.bottom - 2, 8):          # a lattice of small diamonds
                for x in range(inner.x + 4 + (y // 8 % 2) * 4, inner.right - 2, 8):
                    pygame.draw.polygon(img, col, [(x, y - 2), (x + 2, y), (x, y + 2), (x - 2, y)])
            pygame.draw.circle(img, INK, (CARD_W // 2, CARD_H // 2), 17)
            pygame.draw.circle(img, light, (CARD_W // 2, CARD_H // 2), 16, 1)
            if self.player:
                sh = pygame.transform.scale(self.ms.shields[self.player],
                                            (self.ms.shields[self.player].get_width() * 2,
                                             self.ms.shields[self.player].get_height() * 2))
                img.blit(sh, sh.get_rect(center=(CARD_W // 2, CARD_H // 2)))
            self.art.cache[key] = img
        return self.art.cache[key]

    def _piles(self, s: pygame.Surface) -> None:
        """The draw pile and the discard pile next to the end-turn button."""
        r = self.camp.realms[self.player]
        d = self.deck_rect()
        small = pygame.transform.scale(self.back(), d.size)
        for k in range(min(3, len(r.draw)) - 1, -1, -1):
            s.blit(small, (d.x - k, d.y - k))
        if not r.draw:
            pygame.draw.rect(s, (38, 43, 68), d, 1)
        self.font.draw(s, str(len(r.draw)), d.centerx, d.bottom + 1, "#c0cbdc", anchor="midtop")
        x = self.discard_rect()
        if r.discard:
            top = r.discard[-1]
            s.blit(pygame.transform.scale(self.art.full(top.key, origin_label(top.origin), self.player), x.size),
                   x.topleft)
        else:
            pygame.draw.rect(s, (38, 43, 68), x, 1)
        self.font.draw(s, str(len(r.discard)), x.centerx, x.bottom + 1, "#8b9bb4", anchor="midtop")

    def update(self, dt: float, mouse) -> None:
        if self.player and self.camp.realms[self.player].alive:
            self._deal_check()
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
        if self.watching() and self.auto and not self.busy():
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
        if not self.camp.realms[self.player].alive:          # a plaque above the hand area, the world goes on
            pr = pygame.Rect(W // 2 - 110, H - 22 - 44, 220, 36)
            s.blit(self.ms.r.panel(pr.w, pr.h, base="#181425", border="#e43b44"), pr.topleft)
            self.font.draw(s, "ВАША ДЕРЖАВА ПАЛА", pr.centerx, pr.y + 5, "#e43b44", scale=2, anchor="midtop")
            self.font.draw(s, "МИР ЖИВЁТ ДАЛЬШЕ - СЛЕДИТЕ ЗА ХРОНИКОЙ", pr.centerx, pr.y + 24, "#c0cbdc",
                           anchor="midtop")
            self._spectator_bar(s)
            return
        r = self.camp.realms[self.player]
        self._piles(s)
        rects = self.hand_rects()
        order = list(range(len(rects)))
        if self.hand_hover is not None:
            order.remove(self.hand_hover)
            order.append(self.hand_hover)
        playing = self.play["inst"] if self.play else None
        flying = []
        for i in order:
            inst = r.hand[i]
            rect = rects[i]
            img = self.art.full(inst.key, origin_label(inst.origin), self.player)
            t0 = self.dealing.get(inst.id)
            if t0 is not None:
                flying.append((t0, inst, rect, img))
                continue
            from .mapview import BOTTOM
            if i != self.hand_hover:                     # resting cards peek out above the bottom bar
                rect = pygame.Rect(rect.x, rect.y, rect.w, max(0, H - BOTTOM - rect.y))
            s.blit(img, rect.topleft, area=pygame.Rect(0, 0, rect.w, rect.h))
            cost = self.camp.card_cost(self.player, inst)
            if cost < inst.card.cost:                    # a devoted adviser's card is cheaper
                pygame.draw.circle(s, INK, (rect.x + 12, rect.y + 14), 8)
                pygame.draw.circle(s, _c("#c28a2e"), (rect.x + 12, rect.y + 14), 7)
                self.font.draw(s, str(cost), rect.x + 12, rect.y + 14, "#ffffff", anchor="center")
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
        if self.hand_hover is not None and self.hand_hover != getattr(self, "_hover_was", None):
            from .audio import ui as _ui
            _ui("flip")
        self._hover_was = self.hand_hover
        # cards still flying in from the deck (face down, turning over on the way)
        from .fx import ease_out
        from .audio import ui
        now = self.ms.time
        back = self.back()
        deck = self.deck_rect()
        for t0, inst, rect, img in sorted(flying, key=lambda f: f[0]):
            k = (now - t0) / self.DEAL
            if k < 0:
                continue
            if inst.id not in self.sounded:
                self.sounded.add(inst.id)
                ui("deal")
            e = ease_out(min(1.0, k))
            x = deck.x + (rect.x - deck.x) * e
            y = deck.y + (rect.y - deck.y) * e - math.sin(min(1.0, k) * math.pi) * 18
            w = deck.w + (rect.w - deck.w) * e
            h = deck.h + (rect.h - deck.h) * e
            turn = abs(1 - 2 * min(1.0, k * 1.25))
            face = back if k * 1.25 < 0.5 else img
            ww = max(1, int(w * turn))
            s.blit(pygame.transform.scale(face, (ww, max(1, int(h)))), (int(x + (w - ww) / 2), int(y)))
        # end turn and the reserve
        er = self.end_rect()
        hot = er.collidepoint(self.ms._mouse)
        mine = self.my_turn()
        s.blit(self.ms.r.panel(er.w, er.h, base=("#c28a2e" if hot else "#9a6a1e") if mine else "#3a4466",
                                border="#fee761" if mine else "#5a6988"), er.topleft)
        self.font.draw(s, "КОНЕЦ ХОДА (E)" if mine else "ЖДЁМ...", er.centerx, er.centery, "#ffffff", anchor="center")
        n = self.camp.reserve(r.council)
        info = f"РУКА {len(r.hand)}/{self.camp.hand_size(r.council)}  КОЛОДА {len(r.draw)}  СБРОС {len(r.discard)}"
        keep = f"ПКМ ПО КАРТЕ - ОСТАВИТЬ ({len(r.keep)}/{n})" if n else ""
        if len(r.council) < COUNCIL_SEATS:                    # an empty seat: say so where the eye is
            keep = f"СВОБОДНО В СОВЕТЕ: {COUNCIL_SEATS - len(r.council)} - НАЗНАЧЬТЕ СОВЕТНИКА"
            n = n or 1
        wide = max(text_width(info), text_width(keep)) + 6
        plate = pygame.Rect(er.right - wide, er.y - (18 if n else 10), wide, 18 if n else 10)
        s.blit(self.ms.r.panel(plate.w, plate.h, base="#181425", border="#3a4466"), plate.topleft)
        self.font.draw(s, info, er.right - 3, er.y - 8, "#8b9bb4", anchor="topright")
        if n:
            self.font.draw(s, keep, er.right - 3, er.y - 16,
                           "#fee761" if len(r.council) < COUNCIL_SEATS else "#63c74d", anchor="topright")
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
        chosen = self.play["chosen"]
        where = f" - {CITY[chosen[0]].name}" if chosen and isinstance(chosen[0], str) and chosen[0] in CITY else ""
        font.draw(s, f"{card.name}{where}: {PROMPTS.get(p['step'], '')}", r.x + 6, r.y + 6, "#fee761")
        ruler = self.camp.leader.get(self.player)
        if p["step"] in ("attackers", "attackers_far", "attackers_port") and ruler in p["picked"]:
            font.draw(s, "ПРАВИТЕЛЬ РИСКУЕТ ЖИЗНЬЮ В ШТУРМЕ", r.right - 6, r.y + 15, "#f6757a", anchor="topright")
        s.blit(self.art.full(card.key, "", self.player), (r.x - CARD_W - 6, r.y))
        camp = self.camp
        for i, opt in enumerate(p["options"][p["scroll"]:p["scroll"] + self.ROWS]):
            row = self._picker_row(i)
            hot = row.collidepoint(self.ms._mouse)
            picked = opt in p["picked"]
            pygame.draw.rect(s, (58, 68, 102) if hot else (38, 43, 68), row)
            pygame.draw.rect(s, _c("#fee761") if picked else (90, 105, 136), row, 1)
            if p["step"] == "hand_card":
                inst = next((c for c in camp.realms[self.player].hand if c.id == opt), None)
                if inst is not None:
                    s.blit(self.art.chip(inst.key), (row.x + 4, row.y + 2))
                    font.draw(s, f"{TIER_NAMES[inst.card.tier]}   {origin_label(inst.origin)}", row.x + 4, row.y + 10,
                              "#8b9bb4")
                    if hot:
                        s.blit(self.art.full(inst.key, origin_label(inst.origin), self.player),
                               (r.right + 6, r.y))
            elif p["step"] == "building":
                from .buildings import BUILDINGS
                b = BUILDINGS[opt]
                font.draw(s, b.name, row.x + 4, row.y + 2, "#fee761")
                from .mapview import wrap
                from .buildings import price_for
                cost = f"{price_for(self.player, b.cost // 2)} ЗОЛ. (ПОЛЦЕНЫ)   "
                tail = wrap(b.text, row.w - 8 - text_width(cost))
                more = "..." if len(tail) > 1 else ""
                font.draw(s, cost + tail[0] + more, row.x + 4, row.y + 10, "#8b9bb4")

            elif p["step"] in RIVAL_STEPS:
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
        import re
        mine = set(self.camp.cities_of(self.player)) if self.player else set()
        names = [CITY[c].name for c in mine] + ([FACTION[self.player].short] if self.player else [])
        # whole words only: СЕВЕР must not match СЕВЕРНЫЙ БРОД
        pat = re.compile(r"(?<![А-ЯЁA-Z])(" + "|".join(re.escape(n) for n in names) + r")(?![А-ЯЁA-Z])") if names else None
        for i, (turn, f, text) in enumerate(self.camp.log):
            hurt = pat is not None and f != self.player and bool(pat.search(text.upper()))
            out.append((turn, f, text, i >= self.chron_from, hurt))
        return out

    def _watch_rect(self) -> pygame.Rect:
        r = self._chron_rect()
        return pygame.Rect(r.x + 8, r.y + 3, 150, 9)

    def _chronicle_handle(self, ev, mx, my) -> None:
        if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1 and self._watch_rect().collidepoint(mx, my):
            from .campaign_runner import WATCH_MODES
            m = self.ms.runner
            m.watch_ai = WATCH_MODES[(WATCH_MODES.index(m.watch_ai) + 1) % len(WATCH_MODES)]
            return
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
        mode = {"ask": "СПРАШИВАТЬ", "calc": "РАССЧИТЫВАТЬ", "watch": "ВСЕГДА СМОТРЕТЬ"}[self.ms.runner.watch_ai]
        tr = self._watch_rect()
        hot = tr.collidepoint(self.ms._mouse)
        font.draw(s, f"БОИ ДРУГИХ ДЕРЖАВ: {mode}", tr.x, tr.y + 1, "#ffffff" if hot else "#41a6f6")
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
        council = self._council()
        offs = [o for o in self.camp.officers_of(f) if o.key not in council]
        return [o.key for o in sorted(offs, key=lambda o: -self.camp.presence(o.key))]

    def _deck_rows(self) -> List[Tuple[str, int, str]]:
        r = self.camp.realms[self.player]
        from collections import Counter
        cnt = Counter((c.key, c.origin) for c in r.all_cards())
        rows = sorted(cnt.items(), key=lambda kv: (["feat", "faction", "unique", "strong", "moderate", "basic",
                                                     "junk", "vice", "fate", "curse"].index(CARDS[kv[0][0]].tier),
                                                    CARDS[kv[0][0]].name))
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
        before = list(self._council())
        self.camp.set_council(self.player, members)
        self.council_seat = None
        self.ms._say("СОВЕТ ОБНОВЛЁН: КОЛОДА ПЕРЕСОБРАНА", "#a7f070")
        from .fx import Ring, Sparks
        from .audio import ui
        after = self._council()
        for i in range(COUNCIL_SEATS):
            old = before[i] if i < len(before) else None
            new = after[i] if i < len(after) else None
            if old == new:
                continue
            r = self._seat_rect(i)
            face = (r.x + 12, r.y + 14)
            if new:                                       # the seal comes down on the new adviser
                self.ms.fx.add(Ring(*face, "#fee761", 4, 26, 0.4)).layer = 2
                self.ms.fx.add(Sparks(*face, "#fee761", 16, 60)).layer = 2
                ui("seal")
            else:
                self.ms.fx.add(Sparks(r.centerx, r.centery, "#e43b44", 22, 80)).layer = 2
                ui("tear")

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
        without = None                                    # the council minus the adviser under the mouse's X
        xtip = None
        # seats
        for i in range(COUNCIL_SEATS):
            rect = self._seat_rect(i)
            sel = i == self.council_seat
            pygame.draw.rect(s, (58, 68, 102) if sel else (38, 43, 68), rect)
            pygame.draw.rect(s, _c("#fee761") if sel else (90, 105, 136), rect, 1)
            if i >= len(council):                         # a free seat invites an adviser
                pulse = int(abs(math.sin(self.ms.time * 3)) * 80)
                font.draw(s, "+ СВОБОДНО: НАЗНАЧЬТЕ СОВЕТНИКА СПРАВА", rect.centerx, rect.centery,
                          (120 + pulse, 120 + pulse, 60), anchor="center")
                continue
            key = council[i]
            o = OFFICER[key]
            self.ms.cards.face(s, pygame.Rect(rect.x + 2, rect.y + 2, 21, 25), key)
            self.ms.cards.name(s, key, rect.x + 27, rect.y + 2)
            if i == 0:                                    # the ruler: no loyalty, but an heir
                from .succession import contenders
                heirs = contenders(self.camp, self.player)
                if heirs:
                    font.draw(s, "ПРЕЕМНИК: " + OFFICER[heirs[0]].name.split()[0], rect.right - 4, rect.y + 2,
                              "#c0cbdc", anchor="topright")
            else:
                loy = self.camp.loyalty[key]
                col = "#fee761" if self.camp.devoted(key) else "#f6757a" if loy < 35 else "#8b9bb4"
                font.draw(s, f"УР.{self.camp.level[key]} ВЕРН. {loy}", rect.right - 14, rect.y + 2, col,
                          anchor="topright")
            cards = self.camp.personal(key)
            if i == 0:
                from .succession import leader_cards
                legacy = self.camp.realms[self.player].legacy
                cards = leader_cards(self.camp, self.player) + ([None] + legacy if legacy else [])
            x, y = rect.x + 27, rect.y + 11
            label = o.name
            for k in cards:
                if k is None:                             # the dead ruler's cards follow
                    label = "НАСЛЕДИЕ"
                    chip = self.font.render("НАСЛЕДИЕ:", "#8b9bb4")
                    if x + chip.get_width() > rect.right - 4:
                        x, y = rect.x + 27, y + 8
                    s.blit(chip, (x, y))
                    x += chip.get_width() + 3
                    continue
                chip = self.art.chip(k)
                if x + chip.get_width() > rect.right - 4:
                    x, y = rect.x + 27, y + 8
                s.blit(chip, (x, y))
                if pygame.Rect(x, y, chip.get_width(), 7).collidepoint(mouse):
                    self.hover_card = (k, label)
                x += chip.get_width() + 4
            if i:
                xr = pygame.Rect(rect.right - 11, rect.y + 2, 9, 9)
                xhot = xr.collidepoint(mouse)
                pygame.draw.rect(s, (220, 70, 80) if xhot else (162, 38, 51), xr)
                font.draw(s, "X", xr.centerx + 1, xr.centery, "#ffffff", anchor="center")
                if xhot:
                    without = [k for k in council if k != key]
        # competence (and what it would be without the adviser under the X)
        comp = self.camp.competence(council)
        y = r.y + 18 + COUNCIL_SEATS * 31 + 2
        if without is not None:
            comp2 = self.camp.competence(without)
            col = "#f6757a" if comp2 < comp else "#a7f070" if comp2 > comp else "#fee761"
            from .mapview import plural
            font.draw(s, f"КОМПЕТЕНТНОСТЬ: {comp} -> {comp2} {plural(comp2, 'ПОРОГ', 'ПОРОГА', 'ПОРОГОВ')}",
                      r.x + 6, y, col)
            lost = [k for k in self.camp.thresholds(council) if k not in self.camp.thresholds(without)]
            gone = ", ".join(CARDS[k].name for k in lost) or "ничего"
            him = "НЕЁ" if OFFICER[[k for k in council if k not in without][0]].female else "НЕГО"
            xtip = f"БЕЗ {him}: РУКА {self.camp.hand_size(without)}, ОСТАВИТЬ {self.camp.reserve(without)}; " \
                  f"УЙДУТ ПОРОГОВЫЕ КАРТЫ: {gone}"
        else:
            from .mapview import plural
            font.draw(s, f"КОМПЕТЕНТНОСТЬ: {comp} {plural(comp, 'ПОРОГ', 'ПОРОГА', 'ПОРОГОВ')} ИЗ 12", r.x + 6, y,
                      "#fee761")
        perks = [f"РУКА {self.camp.hand_size(council)} КАРТ"]
        n = self.camp.reserve(council)
        perks.append(f"МОЖНО ОСТАВИТЬ {n}" if n else "КАРТЫ НЕ ОСТАЮТСЯ")
        if self.camp.intercepts(council):
            perks.append("ЛОВИТ ШПИОНОВ")
        col = "#a7f070"
        if self.camp.strife(council):
            perks.append("РАСПРИ!")
            col = "#f6757a"
        for j, line in enumerate(wrap(", ".join(perks), 200)):
            font.draw(s, line, r.x + 6, y + 9 + j * 8, col)
        cb = self._course_button()
        hot = cb.collidepoint(mouse)
        realm = self.camp.realms[self.player]
        s.blit(self.ms.r.panel(cb.w, cb.h, base="#5a6988" if hot else "#3a2a10", border="#fee761"), cb.topleft)
        cd = f", ЗАКРЕПЛЁН ЕЩЁ {realm.course_cd} Х." if realm.course_cd else ""
        font.draw(s, f"КУРС: {COURSES[realm.course].name}{cd}", cb.centerx, cb.centery, "#fee761", anchor="center")
        from .succession import contenders, heir_score
        heirs = contenders(self.camp, self.player)[:3]
        heir_tip = None
        if heirs and self._seat_rect(0).collidepoint(mouse):
            heir_tip = "ЗАСЛУГИ: " + ", ".join(f"{OFFICER[h].name} {int(heir_score(self.camp, h))}" for h in heirs) + \
                " (СОВЕТ, КАРТЫ, ПОБЕДЫ, ПОДВИГИ)"
        # thresholds
        x0 = r.x + 214
        font.draw(s, "НАВЫКИ СОВЕТА", x0, r.y + 18, "#fee761")
        totals = self.camp.totals(council)
        for i, st in enumerate(STATS):
            yy = r.y + 27 + i * 29
            v = totals[st]
            from .cards import localize
            fk = self.camp.allegiance.get(council[0]) if council else None
            mid, top = (localize(fk, k) for k in THRESHOLD_CARDS[st])
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
                labels = self.camp.personal(key)
                best = max(labels, key=lambda k: ["junk", "basic", "moderate", "strong", "unique"].index(
                    CARDS[k].tier) if CARDS[k].tier in ("junk", "basic", "moderate", "strong", "unique") else 0) \
                    if labels else None
                if any(CARDS[k].tier == "vice" for k in labels):
                    font.draw(s, "ПОРОК", row.right - 3, row.y + 1, "#b86f50", anchor="topright")
                if best:
                    chip = self.art.chip(best)
                    s.blit(chip, (row.x + 17, row.y + 9), area=pygame.Rect(0, 0, row.w - 20, 8))
                    if hot:
                        self.hover_card = (best, o.name)
                if hot:
                    tip = f"{o.name} УР.{self.camp.level[key]}: НАВЫКИ " + " ".join(str(v) for v in self.camp.ostats[key]) + \
                          f"  ВЕРНОСТЬ {self.camp.loyalty[key]}  КАРТЫ: " + \
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
            shown = f"{self.council_scroll + 1}-{min(len(rows), self.council_scroll + self.CROWS)} ИЗ {len(rows)}, " \
                if len(rows) > self.CROWS else ""
            font.draw(s, f"{shown}ВСЕГО КАРТ {total}", r.right - 6, r.y + 18 + 12 + self.CROWS * 19, "#5a6988",
                      anchor="topright")
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
        if xtip and not tip:                               # over the perks and the course, under the competence
            from .mapview import wrap
            cb = self._course_button()
            y0 = r.y + 18 + COUNCIL_SEATS * 31 + 12
            lines = wrap(xtip, cb.w - 6)[:4]
            box = pygame.Rect(cb.x - 1, y0 - 2, cb.w + 2, max(cb.bottom - y0 + 3, 8 * len(lines) + 3))
            s.blit(self.ms.r.panel(box.w, box.h, base="#181425", border="#a22633"), box.topleft)
            for j, line in enumerate(lines):
                font.draw(s, line, box.x + 4, box.y + 2 + 8 * j, "#c0cbdc")
        elif tip:
            font.draw(s, tip[:120], r.centerx, r.bottom - 10, "#c0cbdc", anchor="midtop")
        elif heir_tip:
            font.draw(s, heir_tip, r.centerx, r.bottom - 10, "#fee761", anchor="midtop")
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
                from .audio import ui
                ui("horn")
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
        font.draw(s, "КУРС ДЕРЖАВЫ: КАКИЕ 6 КАРТ ОСНОВЫ ЛЕЖАТ В КОЛОДЕ", r.centerx, r.y + 4, "#fee761",
                  anchor="midtop")
        cd = self.camp.course_cooldown(realm.council)
        gov = self.camp.totals(realm.council)["УПРАВЛЕНИЕ"]
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
            from .cards import course_base
            for k, n in Counter(course_base(realm.key, key)).items():
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
            s.blit(img, (min(mx + 8, W - CARD_W - 2), max(r.y + 40, min(H - CARD_H - 2, my - CARD_H // 2))))
