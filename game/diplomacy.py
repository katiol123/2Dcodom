"""Diplomacy (pure Python, no pygame): treaties are proposed and answered, alliances fight
together, the strongest realm gathers a coalition against itself, and the relation value itself
has consequences.

**Treaties.** Every pair of realms is at war unless it holds a truce (``camp.truce``) or an
alliance (``camp.alliance``; allies are also at peace). A proposal (``propose``) costs an envoy -
one action point - and the other side weighs it (``evaluate``): relations, who is stronger, wars
on other fronts, cities it has just lost, a fresh grudge, broken treaties, fear of the strongest
realm (the *hegemon*), a common enemy, its course, the envoys' skill (council ДИПЛОМАТИЯ) and the
prey it sees in the proposer's cities. Every factor is returned with its weight, so the screen can
say *why* the answer was yes or no. Breaking a treaty (``declare_war``) is a betrayal remembered
by everybody.

**Alliances.** Allies send help: ``ally_help`` adds part of the power of allied officers standing
next to a stormed (or a defended) city. An alliance may name a common enemy (``target``); allied
computer realms prefer to strike it.

**Coalition.** The hegemon (``hegemon``: far ahead of the average realm) frightens everybody: each
round its relations sink, and realms that border it draw closer to each other.

**Relation tiers** (``tier``) - every band does something, see ``TIER_EFFECTS``.
"""

from __future__ import annotations

from typing import List, Optional, Tuple

from .factions import FACTION, neighbors, relation as base_relation

TRUCE_TURNS = 6
ALLIANCE_TURNS = 12
ENVOY_COST = 1                           # action points per proposal
HEGEMON_AT = 1.3                         # standing over the average that makes a realm the hegemon

# (upper bound, key, name, colour)
TIERS = ((14, "feud", "КРОВНАЯ ВРАЖДА", "#e43b44"), (34, "hostile", "ВРАЖДА", "#f77622"),
         (64, "neutral", "НЕЙТРАЛИТЕТ", "#c0cbdc"), (84, "friend", "ДРУЖБА", "#a7f070"),
         (100, "brother", "БРАТСТВО", "#63c74d"))
TIER_EFFECTS = {
    "feud": "Обе стороны бьются насмерть: +15% силы и в штурме, и в обороне друг против друга. Мир, союз "
            "и торговля невозможны. Пленные не присягают.",
    "hostile": "Ни торговли, ни союза. Пограничные с ними города (если нет мира) растут на ход дольше.",
    "neutral": "Обычные отношения: возможны мир и торговля.",
    "friend": "Дружеская торговля: золото каждый ход обеим сторонам. Союз возможен.",
    "brother": "Двойная дружеская торговля. Союзная помощь в боях сильнее (40% вместо 25%).",
}
KIND_NAMES = {"truce": "ПЕРЕМИРИЕ", "alliance": "СОЮЗ", "trade": "ТОРГОВЛЯ"}
HELP_SHARE, HELP_SHARE_BROTHER = 0.25, 0.4


def tier(v: int) -> Tuple[str, str, str]:
    for top, key, name, col in TIERS:
        if v <= top:
            return key, name, col
    return TIERS[-1][1:]


def _pair(a: str, b: str) -> frozenset:
    return frozenset((a, b))


def humans(camp) -> List[str]:
    return [f for f in camp.alive() if f != "goblin"]


# --- standing ------------------------------------------------------------------------------------
def standing(camp, f: str) -> float:
    """Cities and army against the average living realm (1.0 = average)."""
    alive = humans(camp)
    if f not in alive:
        return 0.0
    cities = sum(len(camp.cities_of(x)) for x in alive) / len(alive)
    army = sum(camp.army(x) for x in alive) / len(alive)
    return 0.75 * len(camp.cities_of(f)) / max(1.0, cities) + 0.25 * camp.army(f) / max(1.0, army)


def hegemon(camp) -> Optional[str]:
    """The realm far ahead of the others - everybody's worry."""
    alive = humans(camp)
    if len(alive) < 3:
        return None
    best = max(alive, key=lambda f: standing(camp, f))
    return best if standing(camp, best) >= HEGEMON_AT else None


def status(camp, a: str, b: str) -> str:
    if _pair(a, b) in camp.alliance:
        return "alliance"
    if camp.truce.get(_pair(a, b), 0) > 0:
        return "truce"
    return "war"


def allies(camp, f: str) -> List[str]:
    return [x for k in camp.alliance for x in k if f in k and x != f and x in camp.alive()]


def borders(camp, a: str, b: str) -> bool:
    mine = set(camp.cities_of(a))
    return any(camp.owner[n] == b for c in mine for n in neighbors(c))


def lost_lately(camp, f: str, turns: int = 6) -> int:
    return sum(1 for t, old, _, _ in camp.losses if old == f and t >= camp.turn - turns)


def attacked_lately(camp, a: str, b: str, turns: int = 3) -> bool:
    """Did ``a`` storm ``b`` in the last turns?"""
    return camp.last_attack.get((a, b), -99) >= camp.turn - turns


def hostile_fronts(camp, f: str, besides: str) -> int:
    """Other realms at war with ``f`` along its borders (goblins count)."""
    return sum(1 for x in camp.alive() if x not in (f, besides) and status(camp, f, x) == "war"
               and borders(camp, f, x))


def prey(camp, f: str, other: str) -> float:
    """Best odds ``f`` has of storming one of ``other``'s cities right now."""
    best = 0.0
    for c in camp.cities_of(other):
        mine = [o.key for n in neighbors(c) if camp.owner[n] == f for o in camp.officers_in(n)
                if camp.allegiance[o.key] == f]
        if mine:
            best = max(best, camp.win_chance(camp.attack_power(f, mine, c), camp.defense_power(c)))
    return best


# --- feasibility and evaluation ------------------------------------------------------------------
def can_propose(camp, frm: str, to: str, kind: str) -> Tuple[bool, str]:
    if "goblin" in (frm, to) or frm == to:
        return False, "С ГОБЛИНАМИ НЕ ДОГОВОРИТЬСЯ"
    if to not in camp.alive():
        return False, "ЭТОЙ ДЕРЖАВЫ БОЛЬШЕ НЕТ"
    t = tier(camp.relation(frm, to))[0]
    st = status(camp, frm, to)
    if t == "feud":
        return False, "КРОВНАЯ ВРАЖДА: ПОСЛОВ НЕ ПРИМУТ"
    if kind == "truce" and st != "war":
        return False, "МИР УЖЕ ЕСТЬ"
    if kind == "alliance":
        if st == "alliance":
            return False, "СОЮЗ УЖЕ ЕСТЬ"
        if t == "hostile":
            return False, "ПРИ ВРАЖДЕ СОЮЗ НЕВОЗМОЖЕН"
    if kind == "trade":
        if _pair(frm, to) in camp.trade:
            return False, "ТОРГОВЛЯ УЖЕ ИДЁТ"
        if t == "hostile":
            return False, "ПРИ ВРАЖДЕ ТОРГОВЛЯ НЕВОЗМОЖНА"
    if camp.proposals.get((frm, to)) == camp.turn:
        return False, "ПОСЛЫ УЖЕ БЫЛИ У НИХ В ЭТОМ ХОДУ"
    return True, ""


def evaluate(camp, frm: str, to: str, kind: str, bonus: int = 0) -> Tuple[int, List[Tuple[str, int]]]:
    """How ``to`` weighs ``frm``'s proposal: (score, [(reason, weight)]); yes when score >= 0."""
    rel = camp.relation(frm, to)
    why: List[Tuple[str, int]] = []

    def add(text: str, v: float) -> None:
        v = int(round(v))
        if v:
            why.append((text, v))

    base = {"truce": 45, "alliance": 62, "trade": 45}[kind]
    add("ОТНОШЕНИЯ", (rel - base) * (0.8 if kind == "truce" else 1.0))
    ours, theirs = camp.army(frm) + 1, camp.army(to) + 1
    ratio = ours / theirs
    h = hegemon(camp)
    if kind == "truce":
        if ratio > 1:
            add("ВЫ СИЛЬНЕЕ - ИМ НУЖЕН МИР", min(30, (ratio - 1) * 25))
        else:
            add("ОНИ СИЛЬНЕЕ И НЕ БОЯТСЯ", -min(25, (1 / ratio - 1) * 20))
        add("ВОЮЮТ НА ДРУГИХ ФРОНТАХ", 8 * hostile_fronts(camp, to, frm))
        add("НЕДАВНО ТЕРЯЛИ ГОРОДА", 8 * min(3, lost_lately(camp, to)))
        if not borders(camp, frm, to):
            add("МЕЖДУ ВАМИ НЕТ ГРАНИЦЫ", 10)
        if prey(camp, to, frm) >= 0.7:
            add("ВИДЯТ ЛЁГКУЮ ДОБЫЧУ В ВАШИХ ГОРОДАХ", -20)
        course = camp.realms[to].course
        if course in ("war", "intrigue"):
            add("ИХ КУРС: " + ("ВОЙНА" if course == "war" else "ИНТРИГИ"), -15 if course == "war" else -5)
        elif course in ("economy", "defense"):
            add("ИХ КУРС МИРНЫЙ", 8)
    if kind == "alliance":
        if h and h not in (frm, to) and (borders(camp, to, h) or borders(camp, frm, h)):
            add(f"ОБЩИЙ ВРАГ: {FACTION[h].short}", 25)
        common = [x for x in humans(camp) if x not in (frm, to) and status(camp, frm, x) == "war"
                  and status(camp, to, x) == "war" and borders(camp, frm, x) and borders(camp, to, x)]
        add("ОБЩИЕ СОСЕДИ-ВРАГИ", 6 * min(3, len(common)))
        if ratio > 1.3:
            add("СИЛЬНЫЙ СОЮЗНИК", 10)
        elif ratio < 0.5:
            add("СЛИШКОМ СЛАБЫЙ СОЮЗНИК", -10)
        n = len(allies(camp, to))
        if n >= 2:
            add("У НИХ УЖЕ ХВАТАЕТ СОЮЗНИКОВ", -15 * (n - 1))
    if kind == "trade":
        if camp.realms[to].course == "economy":
            add("ИХ КУРС: ХОЗЯЙСТВО", 12)
        if camp.gold[to] < camp.upkeep(to) * 2:
            add("ИМ НУЖНО ЗОЛОТО", 10)
    if attacked_lately(camp, frm, to):
        add("СВЕЖА ОБИДА: ВЫ ИХ ШТУРМОВАЛИ", -25)
    if camp.betrayals[frm]:
        add("ВЫ НАРУШАЛИ ДОГОВОРЫ", -15 * min(3, camp.betrayals[frm]))
    if h == frm and kind != "trade":
        add("БОЯТСЯ ВАШЕГО ВОЗВЫШЕНИЯ", -25 if kind == "alliance" else -15)
    if h == to and kind == "truce":
        add("ОНИ ВЕРШАТ СУДЬБЫ МИРА", -10)
    if camp.realms[frm].unrest:
        add("ВАШ ТРОН ШАТАЕТСЯ", -15 if kind == "alliance" else -5)
    from . import reign
    if kind == "truce" and reign.has(camp, to, "warmonger"):
        add("ИХ ПРАВИТЕЛЬ ВОИНСТВЕН", -15)
    if kind == "trade" and reign.has(camp, to, "trader"):
        add("ИХ ПРАВИТЕЛЬ - ТОРГОВЕЦ", 10)
    if kind == "alliance" and reign.has(camp, to, "ambitious"):
        add("ИХ ПРАВИТЕЛЬ НЕ ДЕЛИТ СЛАВУ", -20)
    dip = camp.totals(camp.realms[frm].council)["ДИПЛОМАТИЯ"]
    add("ИСКУССТВО ВАШИХ ПОСЛОВ", (dip - 50) / 4)
    intr = camp.totals(camp.realms[to].council)["ИНТРИГА"]
    if intr > 60:
        add("ИХ СОВЕТ ПОДОЗРИТЕЛЕН", -(intr - 60) / 4)
    if bonus:
        add("ДАРЫ И ГРАМОТЫ", bonus)
    return sum(v for _, v in why), why


# the same reasons told to the side that receives the envoys
_TURN = {"ВЫ СИЛЬНЕЕ - ИМ НУЖЕН МИР": "ОНИ СИЛЬНЕЕ - ВАМ НУЖЕН МИР",
         "ОНИ СИЛЬНЕЕ И НЕ БОЯТСЯ": "ВЫ СИЛЬНЕЕ, МОЖНО НЕ БОЯТЬСЯ",
         "ВОЮЮТ НА ДРУГИХ ФРОНТАХ": "ВЫ ВОЮЕТЕ НА ДРУГИХ ФРОНТАХ",
         "НЕДАВНО ТЕРЯЛИ ГОРОДА": "ВЫ НЕДАВНО ТЕРЯЛИ ГОРОДА",
         "ВИДЯТ ЛЁГКУЮ ДОБЫЧУ В ВАШИХ ГОРОДАХ": "ИХ ГОРОДА - ЛЁГКАЯ ДОБЫЧА ДЛЯ ВАС",
         "ИХ КУРС МИРНЫЙ": "ВАШ КУРС МИРНЫЙ", "У НИХ УЖЕ ХВАТАЕТ СОЮЗНИКОВ": "У ВАС УЖЕ ХВАТАЕТ СОЮЗНИКОВ",
         "ИМ НУЖНО ЗОЛОТО": "ВАМ НУЖНО ЗОЛОТО", "СВЕЖА ОБИДА: ВЫ ИХ ШТУРМОВАЛИ": "СВЕЖА ОБИДА: ОНИ ВАС ШТУРМОВАЛИ",
         "ВЫ НАРУШАЛИ ДОГОВОРЫ": "ОНИ НАРУШАЛИ ДОГОВОРЫ", "БОЯТСЯ ВАШЕГО ВОЗВЫШЕНИЯ": "ИХ ВОЗВЫШЕНИЕ ПУГАЕТ",
         "ОНИ ВЕРШАТ СУДЬБЫ МИРА": "ВЫ ВЕРШИТЕ СУДЬБЫ МИРА", "ИСКУССТВО ВАШИХ ПОСЛОВ": "ИСКУССТВО ИХ ПОСЛОВ",
         "ИХ СОВЕТ ПОДОЗРИТЕЛЕН": "ВАШ СОВЕТ ПОДОЗРИТЕЛЕН", "ВАШ ТРОН ШАТАЕТСЯ": "ИХ ТРОН ШАТАЕТСЯ"}


def for_recipient(reasons: List[Tuple[str, int]]) -> List[Tuple[str, int]]:
    """``evaluate`` speaks to the proposer; this is how the receiving side's advisers put it."""
    return [(_TURN.get(t, t.replace("ИХ КУРС", "ВАШ КУРС")), v) for t, v in reasons]


def mood(score: int) -> Tuple[str, str]:
    if score >= 15:
        return "СКЛОННЫ СОГЛАСИТЬСЯ", "#63c74d"
    if score >= 0:
        return "КОЛЕБЛЮТСЯ, НО СКОРЕЕ ДА", "#a7f070"
    if score >= -15:
        return "КОЛЕБЛЮТСЯ, СКОРЕЕ НЕТ", "#feae34"
    return "ПРОТИВ", "#e43b44"


# --- acting --------------------------------------------------------------------------------------
def trade_gold(camp, a: str, b: str) -> int:
    return 10 + 2 * min(len(camp.cities_of(a)), len(camp.cities_of(b)))


def propose(camp, frm: str, to: str, kind: str, bonus: int = 0, turns: Optional[int] = None,
            target: Optional[str] = None) -> Tuple[bool, str]:
    """Send envoys. The player answers proposals made to him (``camp.diplo_hook``)."""
    ok, why = can_propose(camp, frm, to, kind)
    if not ok:
        return False, why
    camp.proposals[(frm, to)] = camp.turn
    score, reasons = evaluate(camp, frm, to, kind, bonus)
    yes = score >= 0
    if to == camp.player and camp.diplo_hook is not None:
        answer = camp.diplo_hook(camp, frm, to, kind, reasons)
        if answer is not None:                           # None: nobody to ask, decide as the AI would
            yes = bool(answer)
    name = KIND_NAMES[kind]
    camp.stats["diplomacy"][f"{kind}:{'yes' if yes else 'no'}"] += 1
    if not yes:
        camp.change_relation(frm, to, -2)
        top = min(reasons, key=lambda r: r[1])[0] if reasons else ""
        msg = f"{FACTION[to].short} ОТВЕРГЛИ {name}" + (f" ({top})" if top and to != camp.player else "")
        camp.log_event(frm, msg)
        if to != frm:
            camp.log_event(to, f"Отвергли {name} от державы {FACTION[frm].short}")
        return False, msg
    p = _pair(frm, to)
    if kind == "truce":
        camp.truce[p] = turns or TRUCE_TURNS
        msg = f"{name} С {FACTION[to].short} НА {camp.truce[p]} Х."
    elif kind == "alliance":
        camp.truce.pop(p, None)
        h = hegemon(camp)
        camp.alliance[p] = [turns or ALLIANCE_TURNS, target or (h if h not in (frm, to) else None)]
        enemy = camp.alliance[p][1]
        msg = f"{name} С {FACTION[to].short} НА {camp.alliance[p][0]} Х." + \
              (f", ОБЩИЙ ВРАГ: {FACTION[enemy].short}" if enemy else "")
    else:
        g = trade_gold(camp, frm, to)
        camp.trade[p] = (turns or 8, g)
        msg = f"{name} С {FACTION[to].short}: +{g} ЗОЛОТА ЗА ХОД"
    camp.change_relation(frm, to, 4)
    camp.log_event(frm, msg)
    camp.log_event(to, f"{name} с державой {FACTION[frm].short} заключён")
    return True, msg


def declare_war(camp, frm: str, to: str) -> str:
    """Break a truce or an alliance: a betrayal everybody remembers."""
    p = _pair(frm, to)
    had = status(camp, frm, to)
    camp.truce.pop(p, None)
    camp.alliance.pop(p, None)
    camp.trade.pop(p, None)
    if had == "war":
        return ""
    camp.betrayals[frm] += 1
    camp.stats["diplomacy"]["betrayal"] += 1
    camp.change_relation(frm, to, -25)
    for x in humans(camp):
        if x not in (frm, to):
            camp.change_relation(frm, x, -6)
    for a in allies(camp, to):                  # the victim's allies take its side
        if a != frm:
            camp.change_relation(frm, a, -8)
            camp.alliance[_pair(a, to)][1] = frm
    msg = f"ВЕРОЛОМСТВО: {FACTION[frm].short} РАЗОРВАЛИ " + ("СОЮЗ" if had == "alliance" else "МИР") + \
          f" С {FACTION[to].short}"
    camp.log_event(frm, msg)
    camp.log_event(to, msg)
    return msg


def ally_help(camp, f: str, city: str, enemy: str) -> Tuple[float, List[str]]:
    """Allies of ``f`` hostile to ``enemy`` send part of their officers' power from next to ``city``."""
    total, who = 0.0, []
    for a in allies(camp, f):
        if a == enemy or status(camp, a, enemy) != "war":
            continue
        share = HELP_SHARE_BROTHER if tier(camp.relation(f, a))[0] == "brother" else HELP_SHARE
        here = [o.key for n in neighbors(city) for o in camp.officers_in(n)
                if camp.allegiance[o.key] == a and camp.owner[n] == a]
        power = sum(camp.power(o) for o in here) * share
        if power > 0:
            total += power
            who.append(a)
    return total, who


def growth_blocked(camp, city: str) -> bool:
    """A border city facing a hostile realm (without peace) grows a turn slower."""
    f = camp.owner[city]
    for n in neighbors(city):
        x = camp.owner[n]
        if x not in (f, "goblin") and status(camp, f, x) == "war" and \
                tier(camp.relation(f, x))[0] in ("feud", "hostile"):
            return True
    return False


def round_tick(camp) -> None:
    """Once a round: treaties age, friends trade, relations drift, the hegemon is feared."""
    alive = humans(camp)
    for p in list(camp.alliance):
        camp.alliance[p][0] -= 1
        if camp.alliance[p][0] <= 0:
            del camp.alliance[p]
            a, b = sorted(p)
            camp.truce[p] = 2                       # parting friends keep the peace a little longer
            for f in (a, b):
                camp.log_event(f, f"Союз {FACTION[a].short} и {FACTION[b].short} истёк")
        elif all(x in alive for x in p):
            a, b = tuple(p)
            camp.change_relation(a, b, 2)
    for i, a in enumerate(alive):
        for b in alive[i + 1:]:
            p = _pair(a, b)
            t = tier(camp.relation(a, b))[0]
            if t in ("friend", "brother") and status(camp, a, b) != "war":
                g = 4 + min(len(camp.cities_of(a)), len(camp.cities_of(b)))
                g *= 2 if t == "brother" else 1
                camp.earn(a, g, "friendship")
                camp.earn(b, g, "friendship")
            if p in camp.trade:
                camp.change_relation(a, b, 1)
            # relations drift back towards the old memories when nothing happens
            if camp.turn % 3 == 0 and not attacked_lately(camp, a, b, 4) and not attacked_lately(camp, b, a, 4):
                base = base_relation(a, b)[0]
                v = camp.relation(a, b)
                if v != base:
                    camp.change_relation(a, b, 1 if v < base else -1)
    h = hegemon(camp)
    if h:
        camp.stats["hegemon"][h] += 1
        near = [x for x in alive if x != h and borders(camp, x, h)]
        for x in alive:
            if x != h:
                camp.change_relation(h, x, -1)              # fear of the strongest
        for i, a in enumerate(near):
            for b in near[i + 1:]:
                if camp.turn % 2 == 0:
                    camp.change_relation(a, b, 1)           # the threatened draw together
    if camp.turn % 15 == 0:
        for f in list(camp.betrayals):
            camp.betrayals[f] = max(0, camp.betrayals[f] - 1)


def enemy_of_alliance(camp, f: str) -> List[str]:
    """Realms named as the common enemy in ``f``'s alliances."""
    return [v[1] for k, v in camp.alliance.items() if f in k and v[1]]


# --- the computer's diplomacy --------------------------------------------------------------------
def ai_wishes(camp, f: str) -> List[Tuple[float, str, str]]:
    """(desire, kind, partner) the computer realm ``f`` would like, with the odds folded in."""
    out = []
    alive = humans(camp)
    h = hegemon(camp)
    my_army = camp.army(f) + 1
    for r in alive:
        if r == f:
            continue
        st = status(camp, f, r)
        if st == "war" and can_propose(camp, f, r, "truce")[0] and borders(camp, f, r):
            danger = camp.army(r) / my_army
            want = 60 * (danger - 0.8) + 25 * lost_lately(camp, f) + 12 * hostile_fronts(camp, f, r)
            if h and h not in (f, r) and borders(camp, f, h):
                want += 25                             # save the strength for the hegemon
            if camp.realms[f].course in ("economy", "defense"):
                want += 10
            want -= 120 * prey(camp, f, r)             # don't make peace with easy prey
            if r == h:
                want -= 30
            if want > 0:
                out.append((want, "truce", r))
        if st != "alliance" and can_propose(camp, f, r, "alliance")[0] and not allies(camp, f):
            want = 0.0
            if h and h not in (f, r) and (borders(camp, f, h) or borders(camp, r, h)):
                want += 90
            want += 6 * sum(1 for x in alive if x not in (f, r) and borders(camp, f, x) and borders(camp, r, x))
            if want > 60:
                out.append((want, "alliance", r))
        trades = sum(1 for k in camp.trade if f in k)
        if trades < 2 and can_propose(camp, f, r, "trade")[0] and camp.relation(f, r) >= 50:
            out.append((trade_gold(camp, f, r) * 3, "trade", r))
    from . import reign
    t = reign.ruler_traits(camp, f)
    mult = {"truce": (2.0 if "diplomat" in t else 1.0) * (0.0 if "warmonger" in t else 1.0),
            "alliance": (2.0 if "diplomat" in t else 1.0) * (0.0 if "ambitious" in t else 1.0),
            "trade": 2.0 if "trader" in t else 1.0}
    out = [(w * mult[k], k, r) for w, k, r in out if w * mult[k] > 0]
    scored = []
    for want, kind, r in out:
        score, _ = evaluate(camp, f, r, kind)
        if r == camp.player:
            score -= 5                                 # the human is unpredictable
        if score >= 0:
            scored.append((want, kind, r))
    return sorted(scored, reverse=True)


def ai_turn(camp, f: str, ap_price: float) -> None:
    """At most one proposal a turn (it costs an envoy); rarely, a treacherous strike."""
    if f == "goblin" or f not in humans(camp):
        return
    r = camp.realms[f]
    wishes = ai_wishes(camp, f)
    if wishes and r.ap >= ENVOY_COST and wishes[0][0] > ap_price * ENVOY_COST * 1.2:
        _, kind, other = wishes[0]
        r.ap -= ENVOY_COST
        propose(camp, f, other, kind)
    # treachery: a truce partner who has become easy prey (never an ally)
    from . import reign
    if reign.has(camp, f, "honorable"):
        return
    sly = reign.has(camp, f, "treacherous")
    for other in humans(camp):
        if other != f and status(camp, f, other) == "truce" and camp.relation(f, other) < (60 if sly else 45) \
                and camp.betrayals[f] < (4 if sly else 2) and prey(camp, f, other) >= 0.8:
            if camp.rng.random() < (0.45 if sly else 0.15):
                declare_war(camp, f, other)
                break
