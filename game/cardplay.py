"""What the cards do: target options (step by step) and effects (pure Python, no pygame).

A card lists its target steps in ``Card.targets``; ``options(camp, faction, card, chosen)``
returns the candidates for the next step given the ones already chosen. Multi-select steps
(``MULTI``) take a tuple of 1..3 officers. ``EFFECTS[key](camp, faction, targets)`` applies a
card and returns a short line for the chronicle.
"""

from __future__ import annotations

from typing import Callable, Dict, List

from .cards import CARDS
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
    """Other realms; the horde keeps its word to those who paid it off."""
    return [x for x in camp.alive() if x != f and not (f == "goblin" and camp.at_peace(f, x))]


def options(camp, f: str, key: str, chosen: list) -> list:
    out = _options(camp, f, key, chosen)
    spared = camp.vows.get(f)
    if spared and CARDS[key].kind == "military":         # ЛЕСНОЙ ЗАРОК: no war on the realm that sent it
        def free(x) -> bool:
            if not isinstance(x, str):
                return True
            side = camp.owner.get(x) or (x if x in camp.realms else camp.allegiance.get(x))
            return side not in spared
        out = [x for x in out if free(x)]
    return out


def _options(camp, f: str, key: str, chosen: list) -> list:
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
    if step == "tiltyard_city":                          # a free slot and the gold for the work
        from .buildings import BUILDINGS, can_build
        return [c for c in own if can_build(camp, f, c, "tiltyard", BUILDINGS["tiltyard"].cost)[0]]
    if step == "building":                               # what a master builder can put up (half price)
        from .buildings import BUILDINGS, ORDER, can_build
        return [k for k in ORDER if can_build(camp, f, chosen[0], k, BUILDINGS[k].cost // 2)[0]]
    if step == "enemy_town":                             # cities of men: lairs know no order
        return [c for c in camp.owner if camp.owner[c] not in (f, "goblin") and c in camp.law]
    if step == "enemy_lair":
        return [c for c in camp.owner if camp.owner[c] == "goblin" and _hostile(camp, f, c)
                and any(camp.owner[n] == f for n in neighbors(c))]
    if step == "enemy_built":
        return [c for c in camp.owner if camp.owner[c] != f and camp.buildings.get(c)
                and any(camp.owner[n] == f for n in neighbors(c))]
    if step == "hand_card":                              # a debt is repaid, never burnt away
        return [c.id for c in camp.realms[f].hand if c.key != "debt" and (c.key != "purge" or len(
            [x for x in camp.realms[f].hand if x.key == "purge"]) > 1)]
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


def completable(camp, f: str, key: str, chosen: list = None, width: int = 12) -> bool:
    """Can the card's target steps be filled all the way (not only the first one)? A picker must never
    open onto a dead end (a march with no own city next door, a builder with nothing affordable)."""
    chosen = list(chosen or [])
    steps = CARDS[key].targets
    if len(chosen) >= len(steps):
        return True
    opts = options(camp, f, key, chosen)
    multi = steps[len(chosen)] in MULTI
    for o in opts[:width]:
        if completable(camp, f, key, chosen + [(o,) if multi else o], width):
            return True
    return False


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
    """Change prosperity; growth stops at the city's room, but never takes away what is above it (a gold rush)."""
    p = camp.prosperity[city]
    cap = max(camp.max_prosperity(city), p) if d > 0 else 10
    camp.prosperity[city] = max(1, min(cap, p + d))


def _best(camp, f, city, stat) -> int:
    return max((camp.stat(o.key, stat) for o in camp.officers_in(city) if camp.allegiance[o.key] == f), default=0)


def _cut(camp, city, frac) -> int:
    """Every troop in the city (squads and garrison) - lose ``frac`` of the power."""
    troops = [(o.key, None, t) for o in camp.officers_in(city) for t in camp.squads[o.key]]
    troops += [(None, city, t) for t in camp.free[city]]
    before = sum(t.power for _, _, t in troops)
    camp._losses(troops, frac)
    return before


def _raid(camp, f, city) -> int:
    from .horde import on_raid
    from .order import RAID, hit
    on_raid(camp, f, city)
    hit(camp, city, RAID)
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
    from .buildings import count
    g = _gold(camp, f, int(camp.income_of(city, f) * (1.5 if count(camp, city, "market") else 1)), "tax")
    from .order import DEN_TAX, FENCE, haunted
    if city in camp.dens and haunted(camp, city):          # the den fences its take through the lairs
        camp.earn("goblin", int(g / (1 - DEN_TAX) * DEN_TAX * FENCE), "fence")
    if camp.taxed.get(city, -9) >= camp.turn - 1 and camp.realms[f].course != "economy":
        _prosper(camp, city, -1)
        from .order import OVERTAX, hit
        hit(camp, city, OVERTAX)
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
    return f"рука державы {FACTION[rival].short} раскрыта"


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
@effect("flea_market")
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
    from .buildings import RUIN_RAID, ruin
    ruin(camp, city, RUIN_RAID, "набег")
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
    return f"рука державы {FACTION[t[0]].short} раскрыта"


@effect("moon_rite")
def _moon(camp, f, t):
    camp.draw_cards(f, 2)
    return ""


@effect("dead_whisper")
def _whisper(camp, f, t):
    _reveal(camp, f, t[0])
    camp.draw_cards(f, 1)
    return f"рука державы {FACTION[t[0]].short} раскрыта"


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
    camp.add_curse(t[0], "fire", source=f)
    camp.change_relation(f, t[0], -4)
    return f"{FACTION[t[0]].short}: в колоде ПОЖАР"


@effect("agitators")
def _agitators(camp, f, t):
    camp.add_curse(t[0], "desertion", 2, source=f)
    camp.change_relation(f, t[0], -5)
    return f"{FACTION[t[0]].short}: 2 ДЕЗЕРТИРСТВА в колоде"


@effect("letters")
@effect("dirty_tricks")
def _letters(camp, f, t):
    camp.add_curse(t[0], "unrest", 2, source=f)
    camp.change_relation(f, t[0], -4)
    return f"{FACTION[t[0]].short}: 2 СМУТЫ в колоде"


@effect("green_vow")
def _green_vow(camp, f, t):
    got = camp.add_curse(t[0], "forest_vow", 1, source=f)
    camp.change_relation(f, t[0], -3)
    return f"{FACTION[t[0]].short}: ЛЕСНОЙ ЗАРОК в колоде" if got else "зарок перехвачен"


@effect("plague_cauldron")
def _cauldron(camp, f, t):
    camp.add_curse(t[0], "plague", 2, source=f)
    camp.change_relation(f, t[0], -8)
    return f"{FACTION[t[0]].short}: 2 ЧУМЫ в колоде"


@effect("mushroom_haze")
def _haze(camp, f, t):
    camp.add_curse(t[0], "haze", 2, source=f)
    return f"{FACTION[t[0]].short}: 2 ГАЛЛЮЦИНАЦИИ в колоде"


@effect("bribe")
def _bribe(camp, f, t):
    o = t[1]
    camp.change_relation(f, camp.allegiance[o], -6)
    if camp.loyalty[o] >= 90:                                    # the devoted send the bribe back
        camp.gold[f] += CARDS["bribe"].gold
        return f"{OFFICER[o].name} с презрением вернул{'а' if OFFICER[o].female else ''} золото"
    camp.change_loyalty(o, -30)
    if camp.loyalty[o] < 20 and not camp.is_leader(o):
        camp.defect(o, f)
        return f"{OFFICER[o].name} {'перешла' if OFFICER[o].female else 'перешёл'} на нашу сторону"
    return f"{OFFICER[o].name}: верность {camp.loyalty[o]}"


@effect("plot")
def _plot(camp, f, t):
    o = t[1]
    victim = camp.allegiance[o]
    intrigue = camp.totals(camp.realms[f].council)["ИНТРИГА"]
    chance = 0.35 + (60 - camp.loyalty[o]) / 100 + intrigue / 400 + (0.15 if camp.realms[f].course == "intrigue" else 0)
    if camp.is_leader(o):
        chance = 0.0
    if camp.loyalty[o] >= 90:
        chance -= 0.3                                            # the devoted are hard to turn
    chance = max(0.0, min(0.95, chance))
    camp.change_relation(f, victim, -15)
    if camp.rng.random() < chance:
        camp.defect(o, f)
        return f"{OFFICER[o].name} с отрядом {'перешла' if OFFICER[o].female else 'перешёл'} к нам"
    camp.change_loyalty(o, 10)
    return f"заговор против {OFFICER[o].name} раскрыт"


@effect("counterspy")
def _counterspy(camp, f, t):
    r = camp.realms[f]
    n = 0
    for pile in (r.draw, r.hand, r.discard):
        before = len(pile)
        pile[:] = [c for c in pile if c.card.tier != "curse" or c.key == "debt"]   # a debt is paid, not burnt
        n += before - len(pile)
    return f"сожжено проклятий: {n}"


@effect("peers_court")
def _peers(camp, f, t):
    r = camp.realms[f]
    for o in r.council:
        camp.change_loyalty(o, 15)
    r.hand[:] = [c for c in r.hand if c.card.tier != "curse" or c.key == "debt"]
    camp.draw_cards(f, 1)
    return "совет присягнул снова"


@effect("embassy")
def _embassy(camp, f, t):
    camp.change_relation(f, t[0], 15)
    return f"{FACTION[t[0]].short}: отношения {camp.relation(f, t[0])}"


@effect("trade_pact")
def _trade(camp, f, t):
    from .diplomacy import propose
    ok, msg = propose(camp, f, t[0], "trade", bonus=20, turns=8)
    return msg


@effect("truce")
def _truce(camp, f, t):
    from .diplomacy import propose
    ok, msg = propose(camp, f, t[0], "truce", bonus=20, turns=8)
    return msg


@effect("grand_embassy")
def _grand_embassy(camp, f, t):
    from .diplomacy import propose, status
    camp.change_relation(f, t[0], 15)                        # the gifts stay, whatever the answer
    kind = "alliance" if status(camp, f, t[0]) == "truce" else "truce"
    ok, msg = propose(camp, f, t[0], kind, bonus=35, turns=10)
    if ok and frozenset((f, t[0])) not in camp.trade:
        camp.trade[frozenset((f, t[0]))] = (10, 30)
        msg += ", ТОРГОВЛЯ 30 ЗОЛ."
    return msg


@effect("buyout")
def _buyout(camp, f, t):
    city = t[0]
    old = camp.owner[city]
    price = camp.prosperity[city] * 100
    camp.gold[f] -= price
    camp.earn(old, price, "sales")
    camp.free[city] = []
    camp.handover(city, f)
    camp.change_relation(f, old, -15)
    camp.check_fall(old, f)
    return f"{CITY[city].name} куплен у державы {FACTION[old].short} за {price} золота"


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
@effect("fat_year")
def _golden_age(camp, f, t):
    cities = camp.cities_of(f)
    for c in sorted(cities, key=lambda c: camp.prosperity[c])[:2]:
        _prosper(camp, c, 1)
    g = sum(camp.prosperity[c] * 6 for c in cities)
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
    advisers = [o for o in r.council if not camp.is_leader(o)]
    if not advisers:
        return "совет пуст"
    o = min(advisers, key=lambda x: camp.loyalty[x])
    camp.set_council(t[0], [x for x in r.council if x != o], quiet=True)   # the dismissal itself: -20
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
              and not camp.at_peace(f, x) and any(camp.owner[n] == x for c in own for n in neighbors(c))]
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
    return f"украдено {g} золота у державы {FACTION[t[0]].short}"


@effect("ancient_map")
def _ancient_map(camp, f, t):
    camp.move([t[0]], t[1], spend=False)
    return f"{OFFICER[t[0]].name} -> {CITY[t[1]].name}"


@effect("purge")
def _purge(camp, f, t):
    r = camp.realms[f]
    inst = next((c for c in r.hand if c.id == t[0]), None)
    if inst is None:
        return "нечего жечь"
    r.hand.remove(inst)                                          # gone for good
    camp.draw_cards(f, 1)
    return f"сожжена карта {inst.card.name}"


@effect("muster")
def _muster(camp, f, t):
    from .buildings import count
    n = camp.muster_turns(camp.realms[f].council) + count(camp, t[0], "barracks")
    camp.muster[t[0]] = max(camp.muster.get(t[0], 0), n)
    return f"{CITY[t[0]].name}: найм открыт" + (f" на {n} х." if n > 1 else " на этот ход")


@effect("talent_search")
def _talent_search(camp, f, t):
    from .buildings import count
    from .population import come_of_age
    city = t[0]
    got = [come_of_age(camp, f, city) for _ in range(1 + count(camp, city, "academy"))]
    got = [o for o in got if o]
    if not got:
        return "двор полон: новых людей не нашлось"
    return f"{CITY[city].name}: " + ", ".join(OFFICER[o].name for o in got)


@effect("master_builder")
def _master_builder(camp, f, t):
    from .buildings import BUILDINGS, build
    city, key = t
    camp.realms[f].ap += 1                                   # the card's own point pays for the work
    ok, msg = build(camp, f, city, key, BUILDINGS[key].cost // 2)
    return msg


@effect("tiltyard")
def _tiltyard(camp, f, t):
    from .buildings import build
    camp.realms[f].ap += 1                                   # the card's own point pays for the work
    ok, msg = build(camp, f, t[0], "tiltyard")
    return msg


@effect("physician")
def _physician(camp, f, t):
    city = t[0]
    camp.sick.pop(city, None)
    camp.immune[city] = 6
    for o in camp.officers_in(city):
        camp.change_loyalty(o.key, 5)
    return f"{CITY[city].name}: лекари на страже 6 ходов"


@effect("sappers")
def _sappers(camp, f, t):
    from .buildings import ruin
    city = t[0]
    lost = ruin(camp, city, 1.0, "сапёры")
    camp.change_relation(f, camp.owner[city], -6)
    from .buildings import BUILDINGS
    return f"{CITY[city].name}: разрушено - " + ", ".join(BUILDINGS[k].name for k in lost) if lost else "не вышло"


@effect("ford_hero")
def _ford_hero(camp, f, t):
    camp.buff(t[0], 1.35, 3)
    camp.loyalty[t[0]] = 100
    return OFFICER[t[0]].name


@effect("goblin_bane")
def _goblin_bane(camp, f, t):
    _gold(camp, f, 150, "trophies")
    return f"+150 золота, {CITY[t[0]].name}: новобранцы на {camp.recruit(t[0], 120)} мощи"


@effect("golden_governor")
def _golden_governor(camp, f, t):
    n = sum(1 for c in camp.cities_of(f) if camp.prosperity[c] >= 7)
    return f"+{_gold(camp, f, 50 * n, 'tax')} золота"


@effect("wall_first")
def _wall_first(camp, f, t):
    return camp.attack(f, t[1], t[0], mult=1.25)


@effect("unbroken")
def _unbroken(camp, f, t):
    camp.ready.add(t[0])
    camp.buff(t[0], 1.2, 2)
    return OFFICER[t[0]].name


@effect("peacemaker")
def _peacemaker(camp, f, t):
    if camp.relation(f, t[0]) < 20:
        return f"{FACTION[t[0]].short} не желают мира"
    camp.truce[frozenset((f, t[0]))] = 10
    camp.change_relation(f, t[0], 10)
    return f"мир с державой {FACTION[t[0]].short} на 10 ходов"


@effect("giant_slayer")
def _giant_slayer(camp, f, t):
    for o in camp.officers_of(f):
        camp.buff(o.key, 1.2, 3)
    return "все отряды воодушевлены"


@effect("war_legend")
def _war_legend(camp, f, t):
    return camp.attack(f, t[1], t[0], mult=1.4)


# --- the horde -------------------------------------------------------------------------------------
@effect("buy_off")
def _buy_off(camp, f, t):
    from .horde import buy_off
    return buy_off(camp, f)


@effect("goblin_tongue")
def _goblin_tongue(camp, f, t):
    from .horde import buy_off
    out = buy_off(camp, f, turns=4, free=True)
    got = camp.recruit(t[0], 100, ("goblin", "goblin_bomber"))
    return f"{out}; гоблины на {got} мощи пришли в городе {CITY[t[0]].name}"


def _scare(camp, f, x, amount) -> str:
    """A neighbour pays the horde, or a border city of his suffers."""
    if camp.gold[x] >= amount:
        camp.gold[x] -= amount
        _gold(camp, f, amount, "tribute")
        camp.log_event(x, f"Орда стрясла с нас {amount} золота")
        return f"{FACTION[x].short} платит {amount}"
    own = set(camp.cities_of(f))
    border = [c for c in camp.cities_of(x) if any(n in own for n in neighbors(c))]
    if border:
        c = max(border, key=lambda c: camp.prosperity[c])
        _prosper(camp, c, -1)
        return f"{CITY[c].name} разорён"
    return f"{FACTION[x].short}: взять нечего"


@effect("intimidate")
def _intimidate(camp, f, t):
    return _scare(camp, f, t[0], 60)


@effect("great_fear")
def _great_fear(camp, f, t):
    own = set(camp.cities_of(f))
    near = [x for x in camp.alive() if x != f and any(camp.owner[n] == x for c in own for n in neighbors(c))
            and not camp.at_peace(f, x)]
    return "; ".join(_scare(camp, f, x, 50) for x in near) or "соседей нет"


@effect("head_hunters")
def _head_hunters(camp, f, t):
    before = _cut(camp, t[0], 0.25)
    g = _gold(camp, f, 40, "raids")
    return f"{CITY[t[0]].name}: гоблины потеряли четверть ({before} мощи было), +{g} золота за головы"


@effect("city_watch")
def _city_watch(camp, f, t):
    from .order import MAX
    city = t[0]
    camp.law[city] = min(MAX, camp.law.get(city, 6) + 4)
    den = city in camp.dens
    camp.dens.discard(city)
    return f"{CITY[city].name}: порядок {camp.law[city]}" + ("; притон разогнан" if den else "")


@effect("thieves_guild")
def _thieves_guild(camp, f, t):
    from .order import SAFE, hit
    city = t[0]
    hit(camp, city, 4)
    camp.change_relation(f, camp.owner[city], -5)
    out = f"{CITY[city].name}: порядок {camp.law[city]}"
    if camp.law[city] < SAFE and city not in camp.dens:
        camp.dens.add(city)
        _prosper(camp, city, -1)
        out += "; завёлся воровской притон"
    return out


@effect("pride")
def _pride(camp, f, t):
    return "гордого советника выслушали - и только"


@effect("shiny_pile")
def _shiny_pile(camp, f, t):
    from .horde import great
    per = 20 if great(camp) else 30
    return f"+{_gold(camp, f, per * len(camp.cities_of(f)), 'tax')} золота в кучу"


EFFECTS = E


# --- curses going off when drawn -----------------------------------------------------------------
def _vice(camp, f: str, inst) -> None:
    """A councillor's vice goes off; the card goes back to the discard (it stays in the deck while
    he sits in the council, unless burnt by ЧИСТКА КАНЦЕЛЯРИИ)."""
    r = camp.realms[f]
    key = inst.key
    who = OFFICER[inst.origin].name if inst.origin in OFFICER else "советник"
    if key == "embezzle":
        loss = min(40, camp.gold[f] // 5)
        camp.gold[f] -= loss
        camp.log_event(f, f"КАЗНОКРАДСТВО: {who} украл{'а' if inst.origin in OFFICER and OFFICER[inst.origin].female else ''} {loss} золота")
    elif key == "rudeness":
        others = [x for x in camp.alive() if x not in (f, "goblin")]
        if others and f != "goblin":
            x = camp.rng.choice(others)
            camp.change_relation(f, x, -10)
            camp.log_event(f, f"ГРУБОСТЬ: {who} оскорбил посла, отношения с державой {FACTION[x].short} -10")
    elif key == "envy":
        others = [o for o in r.council if o != inst.origin and not camp.is_leader(o)]
        if others:
            o = camp.rng.choice(others)
            camp.change_loyalty(o, -10)
            camp.log_event(f, f"ЗАВИСТЬ: {who} интригует против {OFFICER[o].name}")
    elif key == "drink":
        r.ap_penalty += 1
        camp.log_event(f, f"ПЬЯНСТВО: {who} проспал совет, -1 ОД")
    elif key == "cowardice":
        if inst.origin in OFFICER:
            camp.buff(inst.origin, 0.85, 2)
        camp.log_event(f, f"ТРУСОСТЬ: отряд {who} пал духом")
    elif key == "blabber":
        others = [x for x in camp.alive() if x != f]
        if others:
            x = camp.rng.choice(others)
            camp.realms[x].revealed[f] = camp.turn
            camp.draw_cards(x, 1)
            camp.log_event(f, f"БОЛТЛИВОСТЬ: {who} выболтал тайны - {FACTION[x].short} всё знают")
    elif key == "gambling":
        if camp.rng.random() < 0.65:
            loss = min(50, camp.gold[f])
            camp.gold[f] -= loss
            camp.log_event(f, f"АЗАРТ: {who} проиграл {loss} золота казны")
        else:
            camp.gold[f] += 25
            camp.log_event(f, f"АЗАРТ: {who} выиграл 25 золота")
    elif key == "cruelty":
        city = camp.officer_city.get(inst.origin)
        if city and camp.owner[city] == f:
            _prosper(camp, city, -1)
            camp.log_event(f, f"ЖЕСТОКОСТЬ: {who} лютует в городе {CITY[city].name}, процветание -1")
    elif key == "pride":
        if inst.origin in OFFICER:
            camp.change_loyalty(inst.origin, -8)
        camp.log_event(f, f"ГОРДЫНЯ: {who} обижен на совет")
    r.discard.append(inst)


def on_draw(camp, f: str, inst) -> None:
    r = camp.realms[f]
    key = inst.key
    if inst.card.tier == "vice":
        _vice(camp, f, inst)
        return
    if key == "sickness":
        from .population import on_draw_sickness
        on_draw_sickness(camp, f, inst)
        return
    if key == "fire":
        loss = min(150, camp.gold[f] // 4)
        camp.gold[f] -= loss
        camp.log_event(f, f"ПОЖАР НА СКЛАДАХ: -{loss} золота")
    elif key == "plague":
        cities = camp.cities_of(f)
        if cities:
            c = camp.rng.choice(cities)
            _prosper(camp, c, -2)
            camp.log_event(f, f"ЧУМА в городе {CITY[c].name}: процветание -2")
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
    elif key == "forest_vow":
        if inst.by and inst.by != f:
            camp.vows.setdefault(f, set()).add(inst.by)
            camp.log_event(f, f"ЛЕСНОЙ ЗАРОК: в этот ход ни одной военной карты против {FACTION[inst.by].short}")
        camp._draw(f, 1)                                           # the vow burns, a card comes instead
        return
    elif key == "haze":
        others = [c for c in r.hand if c is not inst]
        if others:
            c = camp.rng.choice(others)
            r.hand.remove(c)
            r.discard.append(c)
            camp.log_event(f, f"ГАЛЛЮЦИНАЦИИ: сгорела карта {c.card.name}")
    # the curse is spent
