"""The diplomacy window: the relation matrix of all realms and, for the player, envoys to one realm
at a time - propose a truce, an alliance or trade (1 action point each), or break a treaty.
Before sending, the window shows how the other side will weigh the proposal (``diplomacy.evaluate``).
"""

from __future__ import annotations

from typing import List, Optional, Tuple

import pygame

from pixelforge.text import text_width

from . import diplomacy as dip
from .factions import ALL_FACTIONS, FACTION, relation as lore
from .render import _c
from .sim import H, W

ACTIONS = (("truce", "МИР"), ("alliance", "СОЮЗ"), ("trade", "ТОРГОВЛЯ"), ("war", "РАЗОРВАТЬ"))


def live_reason(camp, a: str, b: str) -> str:
    """Why two realms stand where they stand now: storms, treaties and betrayals of this campaign."""
    out = []
    for x, y in ((a, b), (b, a)):
        t = camp.last_attack.get((x, y))
        if t is not None:
            out.append(f"штурм {FACTION[x].short} -> {FACTION[y].short} на ходу {t}")
    st = dip.status(camp, a, b)
    if st != "war":
        out.append({"truce": "между ними мир", "alliance": "они в союзе"}[st])
    if frozenset((a, b)) in camp.trade:
        out.append("торгуют")
    if not out:
        out.append("в этой кампании они ещё не сталкивались")
    return "СЕЙЧАС: " + "; ".join(out) + "."


class DiploWindow:
    CELL_W, CELL_H = 26, 15

    def __init__(self, ms):
        self.ms = ms
        self.font = ms.font
        self.sel: Optional[str] = None
        self.hover_cell: Optional[Tuple[str, str]] = None
        self.hover_action: Optional[str] = None
        self.result: Tuple[str, str] = ("", "#ffffff")

    @property
    def camp(self):
        return self.ms.camp

    def rect(self) -> pygame.Rect:
        from .mapview import BOTTOM, TOP
        return pygame.Rect(12, TOP + 3, W - 24, H - TOP - BOTTOM - 6)

    def _origin(self) -> Tuple[int, int]:
        r = self.rect()
        return r.x + 46, r.y + 34

    def _cell(self, mx: int, my: int) -> Optional[Tuple[str, str]]:
        x0, y0 = self._origin()
        i, j = (mx - x0) // self.CELL_W, (my - y0) // self.CELL_H
        n = len(ALL_FACTIONS)
        if mx >= x0 and my >= y0 and i < n and j < n and i != j:
            return ALL_FACTIONS[j].key, ALL_FACTIONS[i].key
        return None

    def _panel_x(self) -> int:
        x0, _ = self._origin()
        return x0 + len(ALL_FACTIONS) * self.CELL_W + 12

    def _action_rects(self) -> List[Tuple[pygame.Rect, str]]:
        r = self.rect()
        x = self._panel_x()
        w = r.right - x - 8
        return [(pygame.Rect(x + (k % 2) * (w // 2 + 2), r.y + 104 + (k // 2) * 15, w // 2 - 2, 13), key)
                for k, (key, _) in enumerate(ACTIONS)]

    def open(self) -> None:
        p = self.camp.player
        if self.sel is None and p:
            others = [f for f in dip.humans(self.camp) if f != p]
            near = [f for f in others if dip.borders(self.camp, p, f)]
            self.sel = (near or others or [None])[0]
        self.result = ("", "#ffffff")

    # --- input -------------------------------------------------------------------------------------
    def update(self, mouse) -> None:
        mx, my = mouse
        self.hover_cell = self._cell(mx, my)
        self.hover_action = next((k for rect, k in self._action_rects() if rect.collidepoint(mx, my)), None)

    def handle(self, ev, mx: int, my: int) -> bool:
        """True while the window stays open."""
        if ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE or \
                ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 3:
            return False
        if ev.type != pygame.MOUSEBUTTONDOWN or ev.button != 1:
            return True
        r = self.rect()
        if not r.collidepoint(mx, my) or pygame.Rect(r.right - 16, r.y + 3, 12, 11).collidepoint(mx, my):
            return False
        cell = self._cell(mx, my)
        p = self.camp.player
        if cell:
            a, b = cell
            pick = b if a == p else a if b == p else b
            if pick != "goblin":
                self.sel = pick
            return True
        x0, y0 = self._origin()
        for j, f in enumerate(ALL_FACTIONS):                  # the shields on the left select too
            if pygame.Rect(x0 - 40, y0 + j * self.CELL_H, 38, self.CELL_H).collidepoint(mx, my) \
                    and f.key not in ("goblin", p):
                self.sel = f.key
                return True
        for rect, key in self._action_rects():
            if rect.collidepoint(mx, my):
                self._act(key)
                return True
        return True

    def _act(self, key: str) -> None:
        camp, p, other = self.camp, self.camp.player, self.sel
        if not p or not other:
            return
        if camp.whose_turn() != p:
            self.result = ("СЕЙЧАС НЕ ВАШ ХОД", "#e43b44")
            return
        if key == "war":
            if dip.status(camp, p, other) == "war":
                self.result = ("С НИМИ И ТАК ВОЙНА", "#e43b44")
                return
            self.result = (dip.declare_war(camp, p, other), "#e43b44")
            return
        ok, why = dip.can_propose(camp, p, other, key)
        if not ok:
            self.result = (why, "#e43b44")
            return
        r = camp.realms[p]
        if r.ap < dip.ENVOY_COST:
            self.result = ("НЕТ ОЧКОВ ДЕЙСТВИЙ НА ПОСОЛЬСТВО", "#e43b44")
            return
        r.ap -= dip.ENVOY_COST
        ok, msg = dip.propose(camp, p, other, key)
        self.result = (msg, "#63c74d" if ok else "#f6757a")

    # --- drawing -----------------------------------------------------------------------------------
    def draw(self, s: pygame.Surface) -> None:
        from .mapview import wrap
        camp, font = self.camp, self.font
        r = self.rect()
        s.blit(self.ms.r.panel(r.w, r.h, base="#181425", border="#c9a24a"), r.topleft)
        cr = pygame.Rect(r.right - 16, r.y + 3, 12, 11)
        pygame.draw.rect(s, (162, 38, 51), cr)
        font.draw(s, "X", cr.centerx + 1, cr.centery, "#ffffff", anchor="center")
        font.draw(s, "ДИПЛОМАТИЯ", r.centerx, r.y + 4, "#fee761", anchor="midtop")
        h = dip.hegemon(camp)
        x0, y0 = self._origin()
        cw, ch = self.CELL_W, self.CELL_H
        p = camp.player
        for i, f in enumerate(ALL_FACTIONS):
            s.blit(self.ms.shields[f.key], (x0 + i * cw + (cw - 15) // 2, y0 - 18))
            s.blit(self.ms.shields[f.key], (x0 - 18, y0 + i * ch))
            col = "#fee761" if f.key == self.sel else f.light
            font.draw(s, f.short[:5], x0 - 20, y0 + i * ch + 4, col, anchor="topright")
            if f.key == h:
                font.draw(s, "!", x0 + i * cw + cw // 2 + 8, y0 - 18, "#e43b44")
        for j, a in enumerate(ALL_FACTIONS):
            for i, b in enumerate(ALL_FACTIONS):
                cell = pygame.Rect(x0 + i * cw, y0 + j * ch, cw - 1, ch - 1)
                if a.key == b.key:
                    pygame.draw.rect(s, (30, 34, 54), cell)
                    continue
                hot = self.hover_cell in ((a.key, b.key), (b.key, a.key))
                mine = p in (a.key, b.key) and self.sel in (a.key, b.key)
                pygame.draw.rect(s, (58, 68, 102) if hot else (48, 56, 86) if mine else (38, 43, 68), cell)
                if "goblin" in (a.key, b.key):
                    font.draw(s, "X", cell.centerx, cell.centery - 1, "#e43b44", anchor="center")
                    continue
                v = camp.relation(a.key, b.key)
                _, _, col = dip.tier(v)
                pygame.draw.rect(s, _c(col), (cell.x, cell.bottom - 2, cell.w, 2))
                font.draw(s, str(v), cell.centerx, cell.centery - 1, col, anchor="center")
                st = dip.status(camp, a.key, b.key)
                if st != "war":
                    mark = pygame.Rect(cell.x + 1, cell.y + 1, 3, 3)
                    pygame.draw.rect(s, _c("#63c74d" if st == "alliance" else "#ffffff"), mark)
        # legend / hovered cell
        y = y0 + len(ALL_FACTIONS) * ch + 4
        if self.hover_cell and "goblin" not in self.hover_cell:
            a, b = self.hover_cell
            v = camp.relation(a, b)
            key, name, col = dip.tier(v)
            st = {"war": "ВОЙНА", "truce": "МИР", "alliance": "СОЮЗ"}[dip.status(camp, a, b)]
            font.draw(s, f"{FACTION[a].short} - {FACTION[b].short}: {v} {name}, {st}", r.x + 8, y, col)
            yy = y + 8
            for line in wrap(live_reason(camp, a, b), x0 + len(ALL_FACTIONS) * cw - r.x - 8)[:3]:
                font.draw(s, line, r.x + 8, yy, "#c0cbdc")      # what this campaign did to them, not old lore
                yy += 7
            for line in wrap(dip.TIER_EFFECTS[key], x0 + len(ALL_FACTIONS) * cw - r.x - 8)[:3]:
                font.draw(s, line, r.x + 8, yy, "#8b9bb4")
                yy += 7
        else:
            x = r.x + 8
            limit = self._panel_x() - 10                       # never across the divider: wrap the legend
            for top, key, name, col in dip.TIERS:
                lo = {"feud": 1, "hostile": 15, "neutral": 35, "friend": 65, "brother": 85}[key]
                item = f"{lo}+ {name}"
                if x + text_width(item) > limit:
                    x, y = r.x + 8, y + 8
                x = font.draw(s, item, x, y, col).right + 6
            for line in wrap("БЕЛЫЙ УГОЛОК - МИР, ЗЕЛЁНЫЙ - СОЮЗ, ! - ГЕГЕМОН (ЕГО БОЯТСЯ ВСЕ). НАВЕДИ НА КЛЕТКУ - "
                             "ЧТО МЕЖДУ НИМИ БЫЛО И ЧТО ДАЮТ ОТНОШЕНИЯ; КЛИК - ВЫБРАТЬ ДЕРЖАВУ", limit - r.x - 8):
                y += 8
                font.draw(s, line, r.x + 8, y, "#5a6988")
        self._panel(s)

    def _panel(self, s: pygame.Surface) -> None:
        from .mapview import wrap
        camp, font = self.camp, self.font
        r = self.rect()
        x = self._panel_x()
        w = r.right - x - 8
        pygame.draw.line(s, _c("#3a4466"), (x - 6, r.y + 16), (x - 6, r.bottom - 6))
        other, p = self.sel, camp.player
        if not other:
            font.draw(s, "ВЫБЕРИТЕ ДЕРЖАВУ", x, r.y + 18, "#8b9bb4")
            return
        f = FACTION[other]
        s.blit(self.ms.shields[other], (x, r.y + 16))
        font.draw(s, f.short, x + 18, r.y + 17, f.light)
        alive = other in camp.alive()
        tags = []
        if not alive:
            tags.append("РАЗГРОМ")
        if other == dip.hegemon(camp):
            tags.append("ГЕГЕМОН")
        tags.append(f"ГОРОДОВ {len(camp.cities_of(other))}, АРМИЯ {camp.army(other)}")
        font.draw(s, ", ".join(tags), x + 18, r.y + 25, "#8b9bb4")
        from . import reign
        ruler = camp.leader.get(other)
        if ruler and reign.shown(camp, ruler):          # how their ruler governs, with the traits on hover
            name, traits = reign.describe(ruler)
            label = f"ПРАВЛЕНИЕ: {name}"
            rect = font.draw(s, label, r.right - 8, r.y + 17, "#feae34", anchor="topright")
            if rect.collidepoint(self.ms._mouse):
                tip = pygame.Rect(rect.right - 200, rect.bottom + 2, 200, 4 + 16 * len(traits))
                pygame.draw.rect(s, (24, 20, 37), tip)
                pygame.draw.rect(s, _c("#feae34"), tip, 1)
                for i, (tn, td) in enumerate(traits):
                    font.draw(s, tn, tip.x + 4, tip.y + 3 + i * 16, "#fee761")
                    font.draw(s, td[:48], tip.x + 4, tip.y + 10 + i * 16, "#c0cbdc")
        if not p:
            return
        v = camp.relation(p, other)
        key, name, col = dip.tier(v)
        st = dip.status(camp, p, other)
        pair = frozenset((p, other))
        if st == "alliance":
            turns, enemy = camp.alliance[pair]
            stxt = f"СОЮЗ ЕЩЁ {turns} Х." + (f", ОБЩИЙ ВРАГ: {FACTION[enemy].short}" if enemy else "")
        elif st == "truce":
            stxt = f"МИР ЕЩЁ {int(camp.truce[pair] + 0.5)} Х."
        else:
            stxt = "ВОЙНА"
        if pair in camp.trade:
            stxt += f", ТОРГОВЛЯ +{camp.trade[pair][1]}"
        font.draw(s, f"ОТНОШЕНИЯ {v}: {name}", x, r.y + 36, col)
        lines = wrap(stxt, w)[:2]
        for i, line in enumerate(lines):
            font.draw(s, line, x, r.y + 44 + i * 7, "#ffffff")
        y = r.y + 46 + 7 * len(lines)
        for line in wrap(dip.TIER_EFFECTS[key], w)[:4 - (len(lines) - 1)]:
            font.draw(s, line, x, y, "#8b9bb4")
            y += 7
        if camp.betrayals[p]:
            font.draw(s, f"ВАШИХ ВЕРОЛОМСТВ ПОМНЯТ: {camp.betrayals[p]}", x, r.y + 88, "#f6757a")
        my_turn = camp.whose_turn() == p
        font.draw(s, f"ПРЕДЛОЖИТЬ ИМ ({dip.ENVOY_COST} ОД, У ВАС {camp.realms[p].ap}):", x, r.y + 95,
                  "#41a6f6" if my_turn else "#5a6988")
        for rect, k in self._action_rects():
            label = dict(ACTIONS)[k]
            ok = alive and my_turn and (dip.can_propose(camp, p, other, k)[0] if k != "war" else st != "war")
            hot = rect.collidepoint(self.ms._mouse)
            base = ("#a22633" if k == "war" else "#3e8948") if ok else "#3a4466"
            s.blit(self.ms.r.panel(rect.w, rect.h, base="#5a6988" if hot and ok else base,
                                   border="#c0cbdc" if ok else "#5a6988"), rect.topleft)
            font.draw(s, label, rect.centerx, rect.centery, "#ffffff" if ok else "#5a6988", anchor="center")
        # how they would weigh the hovered proposal
        y = r.y + 136
        k = self.hover_action
        if k and k != "war" and alive:
            ok, why = dip.can_propose(camp, p, other, k)
            if not ok:
                font.draw(s, why, x, y, "#f6757a")
            else:
                score, reasons = dip.evaluate(camp, p, other, k)
                label, mcol = dip.mood(score)
                font.draw(s, f"ОНИ: {label}", x, y, mcol)
                y += 9
                for text, val in sorted(reasons, key=lambda t: -abs(t[1]))[:8]:
                    font.draw(s, f"{val:+d}", x + 14, y, "#63c74d" if val > 0 else "#e43b44", anchor="topright")
                    font.draw(s, text, x + 18, y, "#c0cbdc")
                    y += 7
        elif k == "war":
            for line in wrap("Разрыв договора - вероломство: отношения с ними -25, со всеми прочими -6, их "
                             "союзники встанут на их сторону, а ваши послы долго будут встречать недоверие.", w):
                font.draw(s, line, x, y, "#f6757a")
                y += 7
        else:
            text, col = self.result
            for line in wrap(text, w)[:4]:
                font.draw(s, line, x, y, col)
                y += 7
            font.draw(s, "НАВЕДИ НА КНОПКУ: ИХ ДОВОДЫ", x, r.bottom - 10, "#5a6988")
