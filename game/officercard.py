"""Officer faces, clickable names and the officer card (shared by the map and the faction select).

Any screen that shows an officer draws his face with ``OfficerCard.face`` or his name with
``OfficerCard.name``; both become clickable and open the card: a painted portrait, who he
serves (officers may change sides), leadership, his squad, a short biography and the six
non-combat stats as a spider web.
"""

from __future__ import annotations

from typing import List, Optional, Tuple

import pygame

from .campaign import Campaign
from .faces import face, paint_web, web_points
from .factions import CITY, FACTION
from .hires import HIRES
from .officers import OFFICER, SQUAD_SLOTS, STAT_HELP, STATS, bio
from .render import INK, Renderer, _c
from .sim import H, W
from .units import TEAMS


class OfficerCard:
    def __init__(self, renderer: Renderer, camp: Campaign):
        from .mapview import shield_surface, wrap        # (mapview imports this module)
        self.r = renderer
        self.font = renderer.font
        self.camp = camp
        self.wrap = wrap
        self.shields = {k: shield_surface(f) for k, f in FACTION.items()}
        self.key: Optional[str] = None                   # officer whose card is open
        self.hits: List[Tuple[pygame.Rect, str]] = []    # clickable faces and names drawn this frame
        self._mouse = (0, 0)
        self.dim = pygame.Surface((W, H), pygame.SRCALPHA)
        self.dim.fill((24, 20, 37, 170))

    @property
    def open(self) -> bool:
        return self.key is not None

    def begin(self, mouse: Tuple[int, int]) -> None:
        """Start of a frame: forget last frame's clickable spots."""
        self._mouse = mouse
        self.hits = []
        HIRES.drop()                                     # a new frame: forget last frame's pictures

    def cover(self) -> None:
        """A window now covers whatever was drawn so far: its faces are neither sharp nor clickable."""
        HIRES.drop()
        self.hits = []

    def handle(self, ev, mouse: Tuple[int, int]) -> bool:
        """True if the event was the card's (an open card swallows everything)."""
        mx, my = mouse
        if self.key is not None:
            self._card_handle(ev, mx, my)
            return True
        if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
            for rect, key in self.hits:
                if rect.collidepoint(mx, my):
                    self.key = key
                    return True
        return False

    def draw(self, s: pygame.Surface) -> None:
        if self.key is None:
            return
        s.blit(self.dim, (0, 0))
        self.cover()
        self._card_draw(s, OFFICER[self.key])

    def face(self, s: pygame.Surface, rect: pygame.Rect, key: str, frame: Optional[str] = None,
             click: bool = True) -> None:
        """Painted portrait of an officer (sharp at any window size); clicking it opens his card."""
        f = FACTION[self.camp.allegiance[key]]
        rect = pygame.Rect(rect)
        hot = click and rect.collidepoint(self._mouse)
        edge = "#fee761" if hot else frame or f.color
        pygame.draw.rect(s, _c(edge), rect.inflate(2, 2), 1)
        if not HIRES.blit(s, rect, f"face:{key}", lambda w, h, k=key: face(k, w, h)):
            pygame.draw.rect(s, _c(f.dark), rect)                       # still painting: a silhouette
            pygame.draw.ellipse(s, _c(f.color), (rect.centerx - rect.w // 4, rect.y + rect.h // 5,
                                                 rect.w // 2, rect.h // 2))
        if click:
            self.hits.append((rect.inflate(2, 2), key))

    def name(self, s: pygame.Surface, key: str, x: int, y: int, color: str = "#fee761",
                     anchor: str = "topleft", scale: int = 1) -> pygame.Rect:
        """An officer's name that opens his card (white and underlined under the mouse)."""
        name = OFFICER[key].name
        r = self.font.render(name, color, scale).get_rect(**{anchor: (x, y)})
        hot = r.collidepoint(self._mouse)
        self.font.draw(s, name, x, y, "#ffffff" if hot else color, scale=scale, anchor=anchor)
        if hot:
            pygame.draw.line(s, _c("#ffffff"), (r.x + 1, r.bottom), (r.right - 2, r.bottom))
        self.hits.append((r, key))
        return r

    # --- officer card ------------------------------------------------------------------------------
    CARD = pygame.Rect(12, 19, W - 24, H - 46)
    RANKS = ("ГЛАВА ФРАКЦИИ", "ВЫСШИЙ ЧИН", "ОФИЦЕР", "МЛАДШИЙ ОФИЦЕР")

    def _card_buttons(self) -> List[Tuple[pygame.Rect, str]]:
        r = self.CARD
        return [(pygame.Rect(r.right - 16, r.y + 3, 12, 11), "close"),
                (pygame.Rect(r.right - 46, r.y + 3, 13, 11), "prev"),
                (pygame.Rect(r.right - 31, r.y + 3, 13, 11), "next")]

    def _card_cycle(self, d: int) -> None:
        offs = self.camp.officers_of(self.camp.allegiance[self.key])
        keys = [o.key for o in offs]
        if self.key in keys:
            self.key = keys[(keys.index(self.key) + d) % len(keys)]

    def _card_handle(self, ev, mx: int, my: int) -> None:
        if ev.type == pygame.KEYDOWN:
            if ev.key in (pygame.K_LEFT, pygame.K_RIGHT):
                self._card_cycle(1 if ev.key == pygame.K_RIGHT else -1)
            elif ev.key in (pygame.K_ESCAPE, pygame.K_RETURN, pygame.K_SPACE):
                self.key = None
        elif ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 3:
            self.key = None
        elif ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
            for rect, action in self._card_buttons():
                if rect.collidepoint(mx, my):
                    if action == "close":
                        self.key = None
                    else:
                        self._card_cycle(1 if action == "next" else -1)
                    return None
            if not self.CARD.collidepoint(mx, my):
                self.key = None
        elif ev.type == pygame.MOUSEWHEEL:
            self._card_cycle(-1 if ev.y > 0 else 1)
        return None

    def _web_axes(self) -> Tuple[int, int, int]:
        r = self.CARD
        return r.x + 362, r.y + 104, 36                   # centre x, y and radius of the stat web

    def _card_stat_at(self, mx: int, my: int) -> Optional[int]:
        cx, cy, rad = self._web_axes()
        for i, (x, y) in enumerate(web_points(cx, cy, rad + 14, [20] * len(STATS))):
            if abs(mx - x) < 30 and abs(my - y) < 8:
                return i
        return None

    def _card_draw(self, s: pygame.Surface, o) -> None:
        r = self.CARD
        font = self.font
        serves = FACTION[self.camp.allegiance[o.key]]
        home = FACTION[o.faction]
        p = self.camp.presence(o.key) if o.rank else 1.0
        trim = "#f2c84b" if p >= 0.6 else "#c0cbdc" if p >= 0.36 else "#8b9bb4"
        s.blit(self.r.panel(r.w, r.h, base="#181425", border=serves.color), r.topleft)
        pygame.draw.rect(s, _c(serves.dark), (r.x + 3, r.y + 3, r.w - 6, 13))
        font.draw(s, "КАРТОЧКА ОФИЦЕРА", r.x + 8, r.y + 6, serves.light)
        for rect, action in self._card_buttons():
            hot = rect.collidepoint(self._mouse)
            col = (162, 38, 51) if action == "close" else (58, 68, 102)
            pygame.draw.rect(s, (190, 70, 80) if hot and action == "close" else (90, 105, 136) if hot else col, rect)
            font.draw(s, {"close": "X", "prev": "<", "next": ">"}[action], rect.centerx + 1, rect.centery, "#ffffff",
                      anchor="center")
        offs = [x.key for x in self.camp.officers_of(serves.key)]
        if o.key in offs:
            font.draw(s, f"{offs.index(o.key) + 1} / {len(offs)}", r.right - 50, r.y + 6, "#8b9bb4", anchor="topright")
        # portrait in a frame whose metal tells the officer's calibre
        pr = pygame.Rect(r.x + 9, r.y + 22, 96, 116)
        pygame.draw.rect(s, _c(trim), pr.inflate(6, 6))
        pygame.draw.rect(s, INK, pr.inflate(6, 6), 1)
        pygame.draw.rect(s, INK, pr.inflate(2, 2), 1)
        self.face(s, pr, o.key, frame=trim, click=False)
        font.draw(s, self.RANKS[min(o.rank, 3)], pr.centerx, pr.bottom + 6, "#c0cbdc", anchor="midtop")
        verdict = ("ВЫДАЮЩИЙСЯ" if p >= 0.6 else "ДОСТОЙНЫЙ" if p >= 0.36 else "ЗАУРЯДНЫЙ")
        if o.female:
            verdict = verdict[:-2] + "АЯ"
        font.draw(s, verdict, pr.centerx, pr.bottom + 14, trim, anchor="midtop")
        loy = self.camp.loyalty.get(o.key, 100)
        font.draw(s, f"ВЕРНОСТЬ {loy}", pr.centerx, pr.bottom + 23, "#63c74d" if loy >= 60 else "#feae34"
                  if loy >= 35 else "#e43b44", anchor="midtop")
        realm = self.camp.realms.get(serves.key)
        if realm and o.key in realm.council:
            font.draw(s, "СИДИТ В СОВЕТЕ", pr.centerx, pr.bottom + 31, "#fee761", anchor="midtop")
        # who he is
        x = r.x + 118
        name_w = self.font.render(o.name, "#fee761").get_width()
        font.draw(s, o.name, x, r.y + 21, "#fee761", scale=2 if name_w * 2 <= 148 else 1)
        y = r.y + (38 if name_w * 2 <= 148 else 31)
        font.draw(s, o.title, x, y, serves.light)
        y += 11
        s.blit(self.shields[serves.key], (x, y - 1))
        font.draw(s, "СЛУЖИТ:", x + 18, y - 1, "#8b9bb4")
        font.draw(s, serves.name, x + 18, y + 7, "#ffffff")
        y += 16
        if serves.key != home.key:
            font.draw(s, f"ПЕРЕБЕЖЧИК, РОДОМ ИЗ: {home.short}", x, y, "#f6757a")
            y += 9
        font.draw(s, "ЛИДЕРСТВО", x, y, "#c0cbdc")
        font.draw(s, str(self.camp.leadership(o.key)), x + 62, y - 3, "#fee761", scale=2)
        from .growth import xp_needed
        lvl, xp = self.camp.level[o.key], int(self.camp.xp[o.key])
        need = xp_needed(lvl)
        font.draw(s, f"УР. {lvl}", x + 104, y - 1, "#ffffff")
        bar = pygame.Rect(x + 104, y + 6, 42, 3)
        pygame.draw.rect(s, (38, 43, 68), bar)
        pygame.draw.rect(s, _c("#41a6f6"), (bar.x, bar.y, int(bar.w * min(1, xp / need)), bar.h))
        if bar.inflate(4, 12).collidepoint(self._mouse):
            font.draw(s, f"ОПЫТ {xp}/{need}", x + 146, y - 9, "#41a6f6", anchor="topright")
        power = self.camp.power(o.key)
        squad = self.camp.squads[o.key]
        y += 11
        font.draw(s, f"ОТРЯД: {len(squad)} ИЗ {SQUAD_SLOTS}, МОЩЬ {power}", x, y, "#a7f070")
        y += 10
        city = self.camp.officer_city.get(o.key)
        if city:
            font.draw(s, f"НАХОДИТСЯ: {CITY[city].name}", x, y, "#c0cbdc")
            y += 11
        pygame.draw.line(s, _c("#3a4466"), (x, y), (x + 146, y))
        y += 5
        for line in self.wrap(bio(o), 148):
            font.draw(s, line, x, y, "#e6dfd0")
            y += 7
        # his squad, unit by unit
        y = r.bottom - 42
        font.draw(s, "ОТРЯД:", x - 110, y + 4, "#c0cbdc")
        for k in range(SQUAD_SLOTS):
            box = pygame.Rect(x - 110 + 32 + k * 23, y, 21, 15)
            pygame.draw.rect(s, (38, 43, 68), box)
            pygame.draw.rect(s, (90, 105, 136), box, 1)
            if k < len(squad):
                por = self.r.portrait(f"{squad[k].key}_{TEAMS[0].key}")
                s.blit(por, (box.x + 1, box.y + 1), area=pygame.Rect(0, 0, 19, 13))
        # the stat web
        cx, cy, rad = self._web_axes()
        pygame.draw.line(s, _c("#3a4466"), (r.x + 270, r.y + 22), (r.x + 270, r.bottom - 20))
        font.draw(s, "НЕБОЕВЫЕ НАВЫКИ", cx, r.y + 22, "#fee761", anchor="midtop")
        st = self.camp.ostats[o.key]
        font.draw(s, f"СУММА {sum(st)} ИЗ {20 * len(STATS)}", cx, r.y + 31, "#8b9bb4", anchor="midtop")
        web = pygame.Rect(cx - rad, cy - rad, rad * 2, rad * 2)
        HIRES.blit(s, web, f"web:{o.key}:{serves.key}:{','.join(map(str, st))}",
                   lambda w, h, st=list(st), a=serves.color, b=serves.light: paint_web(st, a, b, w, h))
        hot = self._card_stat_at(*self._mouse)
        for i, (lx, ly) in enumerate(web_points(cx, cy, rad + 10, [20] * len(STATS))):
            anchor = "midbottom" if ly < cy - rad * 0.9 else "midtop" if ly > cy + rad * 0.9 else \
                "midleft" if lx > cx else "midright"
            dy = {"midbottom": -6, "midtop": 0}.get(anchor, -4)
            col = "#ffffff" if hot == i else "#c0cbdc"
            font.draw(s, STATS[i], lx, ly + dy, col, anchor=anchor)
            v = st[i]
            base = o.stats[i]
            vcol = "#63c74d" if v >= 15 else "#fee761" if v >= 9 else "#e43b44"
            txt = str(v) if v == base else f"{v} ({'+' if v > base else ''}{v - base})"
            font.draw(s, txt, lx, ly + dy + 8, vcol if v == base else "#a7f070" if v > base else "#f6757a",
                      anchor=anchor)
        # the cards he brings into the council's deck
        from .cardui import CardArt
        from .cards import FACTION_CARD, PERSONAL
        if not hasattr(self, "art"):
            self.art = CardArt(self.r)
        mine = [FACTION_CARD[o.faction]] if o.rank == 0 and o.faction == serves.key else list(PERSONAL[o.key])
        mine += self.camp.extra.get(o.key, [])
        x1, y1 = r.x + 278, r.y + 168
        font.draw(s, "КАРТЫ В КОЛОДУ СОВЕТА:", x1, y1, "#fee761")
        y1 += 9
        hover = None
        for k in mine:
            chip = self.art.chip(k)
            s.blit(chip, (x1, y1))
            if pygame.Rect(x1, y1, chip.get_width(), 7).collidepoint(self._mouse):
                hover = k
            y1 += 8
        if hover:
            img = self.art.full(hover, o.name, serves.key)
            self.cover()
            s.blit(img, (r.x + 118, r.y + 40))
        tip = STAT_HELP[STATS[hot]] if hot is not None else "НАВЕДИ НА НАВЫК ИЛИ КАРТУ.  < > - ДРУГИЕ ОФИЦЕРЫ"
        font.draw(s, tip.upper() if hot is not None else tip, r.centerx, r.bottom - 11,
                  "#41a6f6" if hot is not None else "#5a6988", anchor="midtop")

