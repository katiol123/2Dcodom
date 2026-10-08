"""What the cards do: target options (step by step) and effects (pure Python, no pygame).

A card lists its target steps in ``Card.targets``; ``options(camp, faction, card, chosen)``
returns the candidates for the next step given the ones already chosen. Multi-select steps
(``MULTI``) take a tuple of 1..3 officers. ``EFFECTS[key](camp, faction, targets)`` applies a
card and returns a short line for the chronicle.
"""

from __future__ import annotations

from typing import Callable, Dict, List

from .cards import CARDS, council_totals
from .factions import CITY, FACTION, neighbors
from .officers import OFFICER
from .units import ROSTER

MULTI = {"officers_here", "attackers", "attackers_far", "attackers_port"}
MAX_GROUP = 3


# --- targets ------------------------------------------------------------------------------------
def _own(camp, f) -> List[str]:
    return camp.cities_of(f)


def _ready_in(camp, f, city, troops=False) -> List[str]:
    return [o.key for o in camp.officers_in(city) if o.key in camp.ready and camp.allegiance[o.key] == f
            and (not troops or camp.squads[o.key])]


def _hostile(camp, f, city) -> bool:
    other = camp.owner[city]
    return other != f and not camp.at_peace(f, other)


def _rivals(camp, f) -> List[str]:
    return [x for x in camp.alive() if x != f]


def options(camp, f: str, key: str, chosen: list) -> list:
    card = CARDS[key]
    if len(chosen) >= len(card.targets):
        return []
    step = card.targets[len(chosen)]
    own = _own(camp, f)
    if step == "own_city":
        return own
    if step == "own_city_officers":
        return [c for c in own if _ready_in(camp, f, c)]
    if step == "officers_here":
        return _ready_in(camp, f, chosen[-1])
    if step == "own_city_pair":
        return [c for c in own if any(camp.owner[n] == f for n in neighbors(c))]
    if step == "own_city_pair2":
        return [n for n in neighbors(chosen[0]) if camp.owner[n] == f]
    if step == "dest_adj":
        return [n for n in neighbors(chosen[0]) if camp.owner[n] == f]
    if step == "dest_2":
        dist = camp.roads_within(chosen[0], 2, f)
        return [c for c, d in dist.items() if d > 0 and camp.owner[c] == f]
    if step == "dest_any":
        return [c for c in own if c != chosen[0]]
    if step == "dest_any_one":
        return [c for c in own if c != camp.officer_city[chosen[0]]]
    if step == "enemy_adj":
        return [c for c in camp.owner if _hostile(camp, f, c)
                and any(camp.owner[n] == f and _ready_in(camp, f, n, troops=True) for n in neighbors(c))]
    if step == "enemy_adj_any":
        return [c for c in camp.owner if _hostile(camp, f, c) and any(camp.owner[n] == f for n in neighbors(c))]
    if step == "enemy_reach":
        return [c for c in camp.owner if _hostile(camp, f, c) and _far_attackers(camp, f, c)]
    if step == "enemy_port":
        if not any(CITY[c].kind == "port" and _ready_in(camp, f, c, troops=True) for c in own):
            return []
        return [c for c in camp.owner if CITY[c].kind == "port" and _hostile(camp, f, c)]
    if step == "enemy_city":
        return [c for c in camp.owner if camp.owner[c] != f]
    if step == "enemy_city_officers":
        return [c for c in camp.owner if camp.owner[c] != f and camp.officers_in(c)]
    if step == "enemy_officer_there":
        return [o.key for o in camp.officers_in(chosen[0])]
    if step == "attackers":
        return [o for n in neighbors(chosen[0]) if camp.owner[n] == f for o in _ready_in(camp, f, n, troops=True)]
    if step == "attackers_far":
        return _far_attackers(camp, f, chosen[0])
    if step == "attackers_port":
        return [o for c in own if CITY[c].kind == "port" for o in _ready_in(camp, f, c, troops=True)]
    if step == "raider":
        return [o for n in neighbors(chosen[0]) if camp.owner[n] == f for o in _ready_in(camp, f, n, troops=True)]
    if step == "city_buyable":
        return [c for c in camp.owner if camp.owner[c] not in (f, "goblin") and not camp.officers_in(c)
                and (camp.at_peace(f, camp.owner[c]) or camp.relation(f, camp.owner[c]) >= 50)
                and any(camp.owner[n] == f for n in neighbors(c)) and camp.gold[f] >= camp.prosperity[c] * 100]
    if step == "rival":
        return _rivals(camp, f)
    if step == "rival_diplo":
        return [] if f == "goblin" else [x for x in _rivals(camp, f) if x != "goblin"]
    if step == "rival_neighbor":
        return [x for x in _rivals(camp, f)
                if any(camp.owner[n] == x for c in own for n in neighbors(c))]
    if step == "own_officer":
        return [o.key for o in camp.officers_of(f)]
    if step == "own_officer_ready":
        return [o.key for o in camp.officers_of(f) if o.key in camp.ready]
    if step == "own_officer_spent":
        return [o.key for o in camp.officers_of(f) if o.key not in camp.ready]
    raise KeyError(step)


def _far_attackers(camp, f, target) -> List[str]:
    out = []
    for n in neighbors(target):
        if camp.owner[n] != f:
            continue
        for c, d in camp.roads_within(n, 2, f).items():
            if camp.owner[c] == f:
                out.extend(o for o in _ready_in(camp, f, c, troops=True) if o not in out)
    return out


def valid(camp, f: str, key: str, targets: list) -> bool:
    card = CARDS[key]
    if len(targets) != len(card.targets):
        return False
    for i, step in enumerate(card.targets):
        opts = options(camp, f, key, targets[:i])
        t = targets[i]
        if step in MULTI:
            if not isinstance(t, (list, tuple)) or not 1 <= len(t) <= MAX_GROUP or len(set(t)) != len(t):
                return False
            if any(x not in opts for x in t):
                return False
        elif t not in opts:
            return False
    return True


# --- helpers ------------------------------------------------------------------------------------
def _gold(camp, f, n, why="cards") -> int:
    return camp.earn(f, int(n), why)


def _prosper(camp, city, d) -> None:
    camp.prosperity[city] = max(1, min(camp.max_prosperity(city), camp.prosperity[city] + d))


def _best(camp, f, city, stat) -> int:
    return max((o.stat(stat) for o in camp.officers_in(city) if camp.allegiance[o.key] == f), default=0)


def _cut(camp, city, frac) -> int:
    """Every troop in the city (squads and garrison) - lose ``frac`` of the power."""
    troops = [(o.key, None, t) for o in camp.officers_in(city) for t in camp.squads[o.key]]
    troops += [(None, city, t) for t in camp.free[city]]
    before = sum(t.power for _, _, t in troops)
    camp._losses(troops, frac)
    return before


def _raid(camp, f, city) -> int:
    g = _gold(camp, f, camp.prosperity[city] * 12, "raids")
    _prosper(camp, city, -1)
    camp.change_relation(f, camp.owner[city], -10)
    return g


def _undead(camp, city, budget) -> int:
    return camp.recruit(city, budget, ("skeleton", "zombie", "ghoul"))


def _hand_value(camp, rival, inst) -> float:
    from .campaign_ai import card_value
    return card_value(camp, rival, inst)


def _reveal(camp, f, rival) -> None:
    camp.realms[f].revealed[rival] = camp.turn


def _city_names(cities) -> str:
    return ", ".join(CITY[c].name for c in cities)


# --- effects ------------------------------------------------------------------------------------
E: Dict[str, Callable] = {}


def effect(key):
    def deco(fn):
        E[key] = fn
        return fn
    return deco


@effect("tax")
def _tax(camp, f, t):
    city = t[0]
    g = _gold(camp, f, camp.income_of(city, f), "tax")
    if camp.taxed.get(city, -9) >= camp.turn - 1:
        _prosper(camp, city, -1)
        note = " (поборы: процветание -1)"
    else:
        note = ""
    camp.taxed[city] = camp.turn
    return f"{CITY[city].name} +{g} золота{note}"


@effect("march")
def _march(camp, f, t):
    camp.move(t[1], t[2])
    return f"{len(t[1])} офиц. -> {CITY[t[2]].name}"


@effect("forced_march")
def _forced(camp, f, t):
    return _march(camp, f, t)


@effect("mother_tree")
def _mother_tree(camp, f, t):
    camp.move(t[1], t[2], spend=False)
    _fortify(camp, t[2], 1.3, 2)
    return f"{len(t[1])} офиц. тайными тропами -> {CITY[t[2]].name}"


@effect("assault")
def _assault(camp, f, t):
    return camp.attack(f, t[1], t[0])


@effect("blitz")
def _blitz(camp, f, t):
    return camp.attack(f, t[1], t[0], mult=1.15)


@effect("longships")
def _longships(camp, f, t):
    return camp.attack(f, t[1], t[0])


@effect("levy")
def _levy(camp, f, t):
    p = camp.recruit(t[0], 60 + 10 * _best(camp, f, t[0], "ВЕРБОВКА"))
    return f"{CITY[t[0]].name}: новобранцы на {p} мощи"


@effect("feast")
def _feast(camp, f, t):
    for o in camp.officers_in(t[0]):
        camp.change_loyalty(o.key, 12)
    return CITY[t[0]].name


@effect("hunt")
def _hunt(camp, f, t):
    return f"+{_gold(camp, f, 30)} золота"


@effect("omen")
def _omen(camp, f, t):
    r = camp.realms[f]
    top = r.draw[-3:]
    free = [c for c in top if c.card.cost == 0 and not c.card.unplayable and not c.card.on_draw]
    if free:
        r.draw.remove(free[-1])
        r.hand.append(free[-1])
        return f"в руку: {free[-1].card.name}"
    return "знаки неясны"


@effect("tourney")
def _tourney(camp, f, t):
    for o in camp.realms[f].council:
        camp.change_loyalty(o, 8)
    _prosper(camp, FACTION[f].capital, 1) if camp.owner[FACTION[f].capital] == f else None
    return "совет доволен"


@effect("denounce")
def _denounce(camp, f, t):
    rival = t[0]
    _reveal(camp, f, rival)
    if any(c.card.tier == "curse" for c in camp.realms[rival].hand):
        camp.gold[rival] = max(0, camp.gold[rival] - 20)
        return f"{FACTION[rival].short}: найдено проклятие, -20 золота"
    return f"рука {FACTION[rival].short} раскрыта"


@effect("parade")
def _parade(camp, f, t):
    cap = FACTION[f].capital
    for o in camp.officers_in(cap) if camp.owner[cap] == f else []:
        camp.change_loyalty(o.key, 10)
        camp.buff(o.key, 1.1, 2)
    return "парад в столице"


@effect("guard")
def _guard(camp, f, t):
    for _ in range(2):
        camp.free[t[0]].append(camp._new("militia"))
    return CITY[t[0]].name


@effect("old_debt")
def _old_debt(camp, f, t):
    camp.change_relation(f, t[0], -8)
    return f"+{_gold(camp, f, 45)} золота"


@effect("pilgrimage")
def _pilgrimage(camp, f, t):
    camp.loyalty[t[0]] = 100
    camp.ready.add(t[0])
    return OFFICER[t[0]].name


@effect("fair")
def _fair(camp, f, t):
    g = _gold(camp, f, camp.prosperity[t[0]] * 10, "trade")
    _prosper(camp, t[0], 1)
    return f"{CITY[t[0]].name} +{g} золота"


@effect("caravan")
def _caravan(camp, f, t):
    g = _gold(camp, f, (camp.prosperity[t[0]] + camp.prosperity[t[1]]) * 9, "trade")
    return f"{CITY[t[0]].name} - {CITY[t[1]].name}: +{g} золота"


@effect("tithe")
def _tithe(camp, f, t):
    g = _gold(camp, f, sum(camp.prosperity[c] * 6 for c in camp.cities_of(f)), "tax")
    return f"+{g} золота"


@effect("edict")
def _edict(camp, f, t):
    g = _gold(camp, f, sum(camp.prosperity[c] * 6 for c in camp.cities_of(f)), "tax")
    return f"+{g} золота со всего королевства"


@effect("build")
def _build(camp, f, t):
    _prosper(camp, t[0], 2)
    return f"{CITY[t[0]].name}: процветание {camp.prosperity[t[0]]}"


@effect("reform")
def _reform(camp, f, t):
    return _build(camp, f, t)


@effect("charter")
def _charter(camp, f, t):
    _prosper(camp, t[0], 3)
    return f"{CITY[t[0]].name}: процветание {camp.prosperity[t[0]]}"


@effect("loan")
def _loan(camp, f, t):
    camp.add_curse(f, "debt")
    return f"+{_gold(camp, f, 220, 'loans')} золота в долг"


@effect("debt")
def _debt(camp, f, t):
    return "долг выплачен"


@effect("militia_call")
def _militia(camp, f, t):
    p = camp.recruit(t[0], 100, sorted(camp._pool(t[0]), key=lambda k: ROSTER[k].cost)[:2])
    camp.defense[t[0]] = [max(1.25, camp.defense.get(t[0], [1, 0])[0]), 2]
    return f"{CITY[t[0]].name}: ополчение на {p} мощи"


@effect("volunteers")
def _volunteers(camp, f, t):
    p = camp.recruit(t[0], camp.prosperity[t[0]] * 25)
    return f"{CITY[t[0]].name}: добровольцы на {p} мощи"


@effect("recruiters")
def _recruiters(camp, f, t):
    p = camp.recruit(t[0], 140)
    return f"{CITY[t[0]].name}: новобранцы на {p} мощи"


@effect("conscription")
def _conscription(camp, f, t):
    total = sum(camp.recruit(c, 40 + 15 * camp.prosperity[c]) for c in camp.cities_of(f))
    return f"под знамёна встали воины на {total} мощи"


def _fortify(camp, city, mult, turns):
    cur = camp.defense.get(city)
    if not cur or cur[0] <= mult:
        camp.defense[city] = [mult, turns]


@effect("fortify")
def _fortify_card(camp, f, t):
    _fortify(camp, t[0], 1.4, 3)
    return CITY[t[0]].name


@effect("thicket_spirits")
def _spirits(camp, f, t):
    _fortify(camp, t[0], 1.8, 4)
    return CITY[t[0]].name


@effect("rune_gates")
def _rune_gates(camp, f, t):
    _fortify(camp, t[0], 2.0, 5)
    return CITY[t[0]].name


@effect("raid")
def _raid_card(camp, f, t):
    city, o = t[0], t[1]
    g = _raid(camp, f, city)
    camp.ready.discard(o)
    if camp.defense_power(city) > camp.power(o) * 1.5:          # the garrison bites back
        camp._losses([(o, None, x) for x in camp.squads[o]], 0.12)
    return f"{CITY[city].name} разграблен, +{g} золота"


@effect("wolf_hunt")
def _wolf_hunt(camp, f, t):
    o = t[0]
    here = camp.officer_city[o]
    targets = sorted((n for n in neighbors(here) if _hostile(camp, f, n)),
                     key=lambda c: -camp.prosperity[c])[:2]
    g = sum(_raid(camp, f, c) for c in targets)
    return f"разграблены: {_city_names(targets) or 'никто'}, +{g} золота"


@effect("great_raid")
def _great_raid(camp, f, t):
    own = set(camp.cities_of(f))
    targets = [c for c in camp.owner if _hostile(camp, f, c) and any(n in own for n in neighbors(c))]
    g = 0
    for c in targets:
        g += _gold(camp, f, camp.prosperity[c] * 8, "raids")
        _prosper(camp, c, -1)
        camp.change_relation(f, camp.owner[c], -8)
    return f"разграблено городов: {len(targets)}, +{g} золота"


@effect("siege")
def _siege(camp, f, t):
    camp.siege[t[0]] = [f, 3]
    camp.change_relation(f, camp.owner[t[0]], -6)
    return f"{CITY[t[0]].name} в осаде"


@effect("supplies")
def _supplies(camp, f, t):
    camp.ready.add(t[0])
    return OFFICER[t[0]].name


@effect("morale")
def _morale(camp, f, t):
    camp.buff(t[0], 1.25, 2)
    return OFFICER[t[0]].name


@effect("griffon_order")
def _griffon(camp, f, t):
    camp.buff(t[0], 1.4, 3)
    camp.ready.add(t[0])
    return OFFICER[t[0]].name


@effect("feigned_retreat")
def _feigned(camp, f, t):
    camp.buff(t[0], 1.6, 2)
    return OFFICER[t[0]].name


@effect("hero_saga")
def _saga(camp, f, t):
    camp.buff(t[0], 1.5, 4)
    camp.loyalty[t[0]] = 100
    return f"сага о {OFFICER[t[0]].name}"


@effect("mead_feast")
def _mead(camp, f, t):
    for o in camp.officers_in(t[0]):
        camp.change_loyalty(o.key, 20)
        camp.buff(o.key, 1.15, 2)
    return CITY[t[0]].name


@effect("patrol")
def _patrol(camp, f, t):
    camp.draw_cards(f, 1)
    return ""


@effect("scouts")
def _scouts(camp, f, t):
    _reveal(camp, f, t[0])
    camp.draw_cards(f, 2)
    return f"рука {FACTION[t[0]].short} раскрыта"


@effect("moon_rite")
def _moon(camp, f, t):
    camp.draw_cards(f, 2)
    return ""


@effect("dead_whisper")
def _whisper(camp, f, t):
    _reveal(camp, f, t[0])
    camp.draw_cards(f, 1)
    return f"рука {FACTION[t[0]].short} раскрыта"


@effect("sabotage")
def _sabotage(camp, f, t):
    city = t[0]
    _prosper(camp, city, -2)
    victims = camp.free[city] or [x for o in camp.officers_in(city) for x in camp.squads[o.key]]
    if victims:
        v = camp.rng.choice(victims)
        for lst in [camp.free[city]] + [camp.squads[o.key] for o in camp.officers_in(city)]:
            if v in lst:
                lst.remove(v)
    camp.change_relation(f, camp.owner[city], -6)
    return CITY[city].name


@effect("arson")
def _arson(camp, f, t):
    camp.add_curse(t[0], "fire")
    camp.change_relation(f, t[0], -4)
    return f"{FACTION[t[0]].short}: в колоде ПОЖАР"


@effect("agitators")
def _agitators(camp, f, t):
    camp.add_curse(t[0], "desertion", 2)
    camp.change_relation(f, t[0], -5)
    return f"{FACTION[t[0]].short}: 2 ДЕЗЕРТИРСТВА в колоде"


@effect("letters")
def _letters(camp, f, t):
    camp.add_curse(t[0], "unrest", 2)
    camp.change_relation(f, t[0], -4)
    return f"{FACTION[t[0]].short}: 2 СМУТЫ в колоде"


@effect("plague_cauldron")
def _cauldron(camp, f, t):
    camp.add_curse(t[0], "plague", 2)
    camp.change_relation(f, t[0], -8)
    return f"{FACTION[t[0]].short}: 2 ЧУМЫ в колоде"


@effect("mushroom_haze")
def _haze(camp, f, t):
    camp.add_curse(t[0], "haze", 2)
    return f"{FACTION[t[0]].short}: 2 ГАЛЛЮЦИНАЦИИ в колоде"


@effect("bribe")
def _bribe(camp, f, t):
    o = t[1]
    camp.change_loyalty(o, -30)
    camp.change_relation(f, camp.allegiance[o], -6)
    if camp.loyalty[o] < 20 and OFFICER[o].rank > 0:
        camp.defect(o, f)
        return f"{OFFICER[o].name} перешёл{'а' if OFFICER[o].female else ''} на нашу сторону"
    return f"{OFFICER[o].name}: верность {camp.loyalty[o]}"


@effect("plot")
def _plot(camp, f, t):
    o = t[1]
    victim = camp.allegiance[o]
    intrigue = council_totals(camp.realms[f].council)["ИНТРИГА"]
    chance = 0.35 + (60 - camp.loyalty[o]) / 100 + intrigue / 400
    if OFFICER[o].rank == 0 and OFFICER[o].faction == victim:
        chance = 0.0
    chance = max(0.0, min(0.95, chance))
    camp.change_relation(f, victim, -15)
    if camp.rng.random() < chance:
        camp.defect(o, f)
        return f"{OFFICER[o].name} с отрядом перешёл{'а' if OFFICER[o].female else ''} к нам"
    camp.change_loyalty(o, 10)
    return f"заговор против {OFFICER[o].name} раскрыт"


@effect("counterspy")
def _counterspy(camp, f, t):
    r = camp.realms[f]
    n = 0
    for pile in (r.draw, r.hand, r.discard):
        before = len(pile)
        pile[:] = [c for c in pile if c.card.tier != "curse"]
        n += before - len(pile)
    return f"сожжено проклятий: {n}"


@effect("peers_court")
def _peers(camp, f, t):
    r = camp.realms[f]
    for o in r.council:
        camp.change_loyalty(o, 15)
    r.hand[:] = [c for c in r.hand if c.card.tier != "curse"]
    camp.draw_cards(f, 1)
    return "совет присягнул снова"


@effect("embassy")
def _embassy(camp, f, t):
    camp.change_relation(f, t[0], 15)
    return f"{FACTION[t[0]].short}: отношения {camp.relation(f, t[0])}"


@effect("trade_pact")
def _trade(camp, f, t):
    if camp.relation(f, t[0]) < 50:
        camp.change_relation(f, t[0], 5)
        return f"{FACTION[t[0]].short} отказались торговать"
    camp.trade[frozenset((f, t[0]))] = (6, 25)
    camp.change_relation(f, t[0], 5)
    return f"торговля с {FACTION[t[0]].short} на 6 ходов"


@effect("truce")
def _truce(camp, f, t):
    if camp.relation(f, t[0]) < 30:
        camp.change_relation(f, t[0], 5)
        return f"{FACTION[t[0]].short} отвергли перемирие"
    camp.truce[frozenset((f, t[0]))] = 4
    return f"перемирие с {FACTION[t[0]].short} на 4 хода"


@effect("grand_embassy")
def _grand_embassy(camp, f, t):
    if camp.relation(f, t[0]) < 40:
        camp.change_relation(f, t[0], 12)
        return f"{FACTION[t[0]].short} приняли дары, но мира не будет"
    camp.truce[frozenset((f, t[0]))] = 8
    camp.trade[frozenset((f, t[0]))] = (8, 30)
    camp.change_relation(f, t[0], 15)
    return f"мир и торговля с {FACTION[t[0]].short} на 8 ходов"


@effect("buyout")
def _buyout(camp, f, t):
    city = t[0]
    old = camp.owner[city]
    price = camp.prosperity[city] * 100
    camp.gold[f] -= price
    camp.earn(old, price, "sales")
    camp.free[city] = []
    camp.owner[city] = f
    camp.siege.pop(city, None)
    camp.defense.pop(city, None)
    camp.change_relation(f, old, -15)
    camp.check_fall(old, f)
    return f"{CITY[city].name} куплен у {FACTION[old].short} за {price} золота"


@effect("mobilize")
def _mobilize(camp, f, t):
    camp.realms[f].ap += 2
    camp.add_curse(f, "fatigue")
    return "+2 ОД"


@effect("genie_lamp")
def _lamp(camp, f, t):
    camp.realms[f].ap += 2
    camp.draw_cards(f, 1)
    return "+2 ОД"


@effect("golden_age")
def _golden_age(camp, f, t):
    g = 0
    for c in camp.cities_of(f):
        _prosper(camp, c, 1)
        g += camp.prosperity[c] * 6
    return f"+{_gold(camp, f, g, 'tax')} золота, процветание растёт"


@effect("all_seeing")
def _all_seeing(camp, f, t):
    rival = t[0]
    _reveal(camp, f, rival)
    hand = camp.realms[rival].hand
    best = sorted(hand, key=lambda c: -_hand_value(camp, rival, c))[:2]
    for c in best:
        camp.discard_card(rival, c)
    return f"{FACTION[rival].short} лишились: " + ", ".join(c.card.name for c in best) if best else "пусто"


@effect("secret_auction")
def _auction(camp, f, t):
    hand = [c for c in camp.realms[t[0]].hand if c.card.tier != "curse"]
    if not hand:
        return "торги сорвались"
    c = camp.rng.choice(hand)
    camp.realms[t[0]].hand.remove(c)
    c.origin = "stolen"
    camp.realms[f].hand.append(c)
    return f"куплена карта {c.card.name}"


@effect("harem_intrigue")
def _harem(camp, f, t):
    r = camp.realms[t[0]]
    advisers = [o for o in r.council if OFFICER[o].rank > 0 or OFFICER[o].faction != t[0]]
    if not advisers:
        return "совет пуст"
    o = min(advisers, key=lambda x: camp.loyalty[x])
    camp.set_council(t[0], [x for x in r.council if x != o], quiet=True)
    camp.change_loyalty(o, -5)
    return f"{OFFICER[o].name} изгнан из совета {FACTION[t[0]].short}"


@effect("winter_storm")
def _storm(camp, f, t):
    camp.frozen[t[0]] = 1
    camp.change_relation(f, t[0], -8)
    return f"{FACTION[t[0]].short} скованы льдом"


@effect("forest_wrath")
def _forest_wrath(camp, f, t):
    before = _cut(camp, t[0], 0.3)
    camp.change_relation(f, camp.owner[t[0]], -10)
    return f"{CITY[t[0]].name}: войска поредели ({before})"


@effect("fire_rain")
def _fire_rain(camp, f, t):
    before = _cut(camp, t[0], 0.35)
    camp.change_relation(f, camp.owner[t[0]], -10)
    return f"{CITY[t[0]].name} в огне ({before})"


@effect("harvest")
def _harvest(camp, f, t):
    cap = FACTION[f].capital
    total = sum(_undead(camp, c, 90 if c == cap else 40) for c in camp.cities_of(f))
    return f"встала нежить на {total} мощи"


@effect("raise_dead")
def _raise(camp, f, t):
    return f"{CITY[t[0]].name}: нежить на {_undead(camp, t[0], 220)} мощи"


@effect("desert_caravans")
def _desert_caravans(camp, f, t):
    friends = [x for x in camp.alive() if x not in (f, "goblin")
               and (camp.at_peace(f, x) or camp.relation(f, x) >= 40)]
    g = _gold(camp, f, 45 * len(friends), "trade")
    ports = [c for c in camp.cities_of(f) if CITY[c].kind == "port"]
    if ports:
        _prosper(camp, ports[0], 1)
    return f"+{g} золота от {len(friends)} держав"


@effect("golden_contract")
def _contract(camp, f, t):
    city = t[0]
    pool = sorted({k for c in CITY.values() for k in c.pool if k in ROSTER and not ROSTER[k].boss},
                  key=lambda k: -ROSTER[k].cost)
    bought = []
    for k in pool:
        price = int(ROSTER[k].cost * 1.25)
        if len(bought) < 3 and camp.gold[f] - price >= 150:
            camp.gold[f] -= price
            camp.free[city].append(camp._new(k))
            bought.append(k)
    return f"{CITY[city].name}: нанято {len(bought)}" + (f" ({', '.join(ROSTER[k].name for k in bought)})"
                                                          if bought else "")


@effect("book_of_grudges")
def _grudges(camp, f, t):
    camp.grudge[(f, t[0])] = 6
    camp.change_relation(f, t[0], -40)
    for o in camp.realms[f].council:
        camp.change_loyalty(o, 10)
    return f"{FACTION[t[0]].short} вписаны в Книгу Обид"


@effect("brood")
def _brood(camp, f, t):
    total = sum(camp.recruit(c, 110, ("goblin", "mad_goblin", "goblin_bomber")) for c in camp.cities_of(f))
    return f"вылупились гоблины на {total} мощи"


@effect("tribute")
def _tribute(camp, f, t):
    own = set(camp.cities_of(f))
    payers = [x for x in camp.alive() if x not in (f, "goblin") and camp.relation(f, x) < 30
              and any(camp.owner[n] == x for c in own for n in neighbors(c))]
    g = 0
    for x in payers:
        pay = min(50, camp.gold[x])
        camp.gold[x] -= pay
        g += pay
        camp.change_relation(f, x, -5)
    _gold(camp, f, g, "tribute")
    return f"дань с {len(payers)} соседей: +{g} золота"


@effect("bill")
def _bill(camp, f, t):
    return f"+{_gold(camp, f, 300)} золота"


@effect("dragon_gold")
def _dragon(camp, f, t):
    return f"+{_gold(camp, f, 400)} золота"


@effect("mercenary_company")
def _company(camp, f, t):
    pool = [k for k in ("crossbowman", "halberdier", "duelist", "rogue", "spearman", "archer") if k in ROSTER]
    return f"{CITY[t[0]].name}: наёмники на {camp.recruit(t[0], 350, pool)} мощи"


@effect("deep_vein")
def _vein(camp, f, t):
    return f"+{_gold(camp, f, 35 * len(camp.cities_of(f)))} золота"


@effect("forge_golem")
def _golem(camp, f, t):
    for k in ("iron_golem", "rune_priest"):
        camp.free[t[0]].append(camp._new(k))
    return CITY[t[0]].name


@effect("troll_wakes")
def _troll(camp, f, t):
    camp.free[t[0]].append(camp._new("troll"))
    return f"{CITY[t[0]].name}: тролль"


@effect("thievery")
def _thievery(camp, f, t):
    g = min(80, camp.gold[t[0]])
    camp.gold[t[0]] -= g
    _gold(camp, f, g, "theft")
    camp.change_relation(f, t[0], -6)
    return f"украдено {g} золота у {FACTION[t[0]].short}"


@effect("ancient_map")
def _ancient_map(camp, f, t):
    camp.move([t[0]], t[1], spend=False)
    return f"{OFFICER[t[0]].name} -> {CITY[t[1]].name}"


EFFECTS = E


# --- curses going off when drawn -----------------------------------------------------------------
def on_draw(camp, f: str, inst) -> None:
    r = camp.realms[f]
    key = inst.key
    if key == "fire":
        loss = min(150, camp.gold[f] // 4)
        camp.gold[f] -= loss
        camp.log_event(f, f"ПОЖАР НА СКЛАДАХ: -{loss} золота")
    elif key == "plague":
        cities = camp.cities_of(f)
        if cities:
            c = camp.rng.choice(cities)
            _prosper(camp, c, -2)
            camp.log_event(f, f"ЧУМА в {CITY[c].name}: процветание -2")
        if camp.rng.random() < 0.35 and sum(1 for c in r.all_cards() if c.key == "plague") < 3:
            r.discard.append(camp._inst("plague", "curse"))       # it spreads
    elif key == "desertion":
        squads = [o.key for o in camp.officers_of(f) if camp.squads[o.key]]
        if squads:
            o = max(squads, key=camp.power)
            camp.squads[o].pop(camp.rng.randrange(len(camp.squads[o])))
            camp.log_event(f, f"ДЕЗЕРТИРСТВО в отряде {OFFICER[o].name}")
    elif key == "debt":
        pay = min(40, camp.gold[f])
        camp.gold[f] -= pay
        camp.log_event(f, f"ДОЛГ: проценты {pay} золота")
        r.hand.append(inst)                                        # stays until repaid
        return
    elif key == "haze":
        others = [c for c in r.hand if c is not inst]
        if others:
            c = camp.rng.choice(others)
            r.hand.remove(c)
            r.discard.append(c)
            camp.log_event(f, f"ГАЛЛЮЦИНАЦИИ: сгорела карта {c.card.name}")
    # the curse is spent
