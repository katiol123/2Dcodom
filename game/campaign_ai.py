"""Computer realms on the world map (pure Python, no pygame).

Every turn a computer realm
1. puts free troops into its officers' squads and hires when the treasury allows;
2. refills empty council seats;
3. plays cards greedily: each playable card gets its best targets and a value in
   gold-equivalents (``VALUE`` below); the best value per action point goes first, as long
   as it beats what an action point is worth (``AP_PRICE``).
The values are rough on purpose: they make the computer play sensibly, and the card
balance tool (``cardsim.py``) shows how often each card is played and what it brings.
"""

from __future__ import annotations

from typing import Callable, Dict, List, Optional, Sequence, Tuple

from .cardplay import MAX_GROUP, options
from .cards import CARDS, COUNCIL_SEATS, PERSONAL, council_totals, threshold_cards
from .factions import CITY, FACTION, neighbors
from .officers import OFFICER
from .units import ROSTER

AP_PRICE = 35                   # what one action point is worth, in gold
TIER_HINT = {"faction": 150, "unique": 130, "strong": 140, "moderate": 80, "basic": 60, "junk": 20, "curse": -60}
POWER_VALUE = 0.7               # gold-equivalent of one point of troop power
PROSPERITY_VALUE = 45           # gold-equivalent of +1 prosperity in an own city


# --- helpers ---------------------------------------------------------------------------------
def card_value(camp, f: str, inst) -> float:
    """Quick worth of a card in hand (for what to keep, or what a spy throws away)."""
    return TIER_HINT[inst.card.tier] - inst.card.cost * 10


def cards_to_keep(camp, f: str, n: int) -> list:
    hand = [c for c in camp.realms[f].hand if c.card.tier != "curse" and not c.card.unplayable]
    return sorted(hand, key=lambda c: -card_value(camp, f, c))[:n]


def frontier(camp, f: str) -> List[str]:
    """Own cities next to a hostile city."""
    return [c for c in camp.cities_of(f)
            if any(camp.owner[n] != f and not camp.at_peace(f, camp.owner[n]) for n in neighbors(c))]


def threat(camp, f: str, city: str) -> float:
    """Strongest hostile army standing next to the city."""
    best = 0.0
    for n in neighbors(city):
        other = camp.owner[n]
        if other != f and not camp.at_peace(f, other):
            best = max(best, sum(camp.power(o.key) for o in camp.officers_in(n)))
    return best


def _econ_factor(camp, f: str) -> float:
    """Troops are worth less (or nothing) when the realm cannot pay for more of them."""
    up = camp.upkeep(f)
    margin = camp.expected_income(f) - up
    if margin < 0.15 * up and camp.gold[f] < 4 * up:
        return -0.2
    base = 1.0 if margin > 0.25 * up else 0.5
    return base if camp.gold[f] > up else base * 0.5


def _recruit_city(camp, f: str, cities: Sequence[str]) -> Tuple[float, Optional[str]]:
    """Where new troops help most: a frontier city with officers who have room in their squads."""
    best, pick = -1.0, None
    front = set(frontier(camp, f))
    for c in cities:
        room = sum(max(0, o.leadership - camp.power(o.key)) for o in camp.officers_in(c))
        score = min(room, 300) / 300 + (0.6 if c in front else 0) + threat(camp, f, c) / 2000
        if score > best:
            best, pick = score, c
    return best, pick


def _city_worth(camp, city: str) -> float:
    return 300 + camp.prosperity[city] * 60 + (250 if CITY[city].kind == "capital" else 0)


def _attack_plan(camp, f: str, key: str, mult: float = 1.0) -> Tuple[float, list]:
    best = (-1.0, [])
    for target in options(camp, f, key, []):
        cands = options(camp, f, key, [target])
        cands = sorted(cands, key=lambda o: -camp.power(o) * camp.officer_mult(o))[:MAX_GROUP]
        if not cands:
            continue
        a = camp.attack_power(f, cands, target, mult)
        d = camp.defense_power(target)
        if (camp.owner[target], f) in camp.grudge:
            d *= 1.3
        p = camp.win_chance(a, d)
        if p < 0.55:
            continue
        hostility = 1.0 + (40 - min(40, camp.relation(f, camp.owner[target]))) / 80
        if camp.realms[camp.owner[target]].course == "economy":
            hostility *= 1.4                     # a rich realm that does not arm itself is tempting prey
        v = p * _city_worth(camp, target) * hostility - (1 - p) * a * 0.5 - p * 0.3 * min(a, d) * POWER_VALUE
        if v > best[0]:
            best = (v, [target, tuple(cands)])
    return best


def _move_plan(camp, f: str, key: str) -> Tuple[float, list]:
    """Bring interior officers towards the front."""
    front = frontier(camp, f)
    if not front:
        return -1.0, []
    best = (-1.0, [])
    for src in options(camp, f, key, []):
        here = sorted(options(camp, f, key, [src]), key=lambda o: -camp.power(o))
        movers = [o for o in here if camp.power(o) > 0][:MAX_GROUP]
        if not movers:
            continue
        for dest in options(camp, f, key, [src, tuple(movers)]):
            if dest not in front:
                continue
            if src in front and threat(camp, f, dest) <= threat(camp, f, src):
                continue
            power = sum(camp.power(o) for o in movers)
            v = 25 + 0.06 * power + threat(camp, f, dest) / 40
            if v > best[0]:
                best = (v, [src, tuple(movers), dest])
    return best


def _rival_threat(camp, f: str, rival: str) -> float:
    """How much of the rival's army stands next to our cities."""
    total = 0.0
    own = set(camp.cities_of(f))
    for c in camp.cities_of(rival):
        if any(n in own for n in neighbors(c)):
            total += sum(camp.power(o.key) for o in camp.officers_in(c))
    return total


def _best_rival(camp, f: str, key: str, score: Callable[[str], float]) -> Tuple[float, list]:
    best = (-1.0, [])
    for r in options(camp, f, key, []):
        v = score(r)
        if v > best[0]:
            best = (v, [r])
    return best


def _best_city(camp, f: str, key: str, score: Callable[[str], float]) -> Tuple[float, list]:
    best = (-1.0, [])
    for c in options(camp, f, key, []):
        v = score(c)
        if v > best[0]:
            best = (v, [c])
    return best


def _best_officer(camp, f: str, key: str, score: Callable[[str], float]) -> Tuple[float, list]:
    return _best_city(camp, f, key, score)


def _enemy_officer(camp, f: str, key: str, score: Callable[[str], float]) -> Tuple[float, list]:
    best = (-1.0, [])
    for c in options(camp, f, key, []):
        if camp.owner[c] == "goblin" and key != "plot":
            pass
        for o in options(camp, f, key, [c]):
            v = score(o)
            if v > best[0]:
                best = (v, [c, o])
    return best


def _frontline_officer(camp, f: str) -> float:
    front = set(frontier(camp, f))
    return max((camp.power(o.key) for o in camp.officers_of(f) if camp.officer_city[o.key] in front), default=0)


def _hand_has_more(camp, f: str, exclude) -> bool:
    return any(c is not exclude and not c.card.unplayable and c.card.cost > 0 for c in camp.realms[f].hand)


# --- card values: (value in gold, targets) ----------------------------------------------------
def _v(camp, f, inst) -> Tuple[float, list]:
    k = inst.key
    gold = camp.gold[f]
    econ = _econ_factor(camp, f)
    if k == "tax":
        def s(c):
            over = camp.taxed.get(c, -9) >= camp.turn - 1 and camp.realms[f].course != "economy"
            return camp.income_of(c, f) - (PROSPERITY_VALUE * 1.3 if over else 0)
        return _best_city(camp, f, k, s)
    if k == "fair":
        return _best_city(camp, f, k, lambda c: camp.prosperity[c] * 10 + (PROSPERITY_VALUE
                                                                            if camp.prosperity[c] < 10 else 0))
    if k == "caravan":
        best = (-1.0, [])
        for a in options(camp, f, k, []):
            for b in options(camp, f, k, [a]):
                v = (camp.prosperity[a] + camp.prosperity[b]) * 9
                if v > best[0]:
                    best = (v, [a, b])
        return best
    if k in ("tithe", "edict"):
        m = 6
        return sum(camp.prosperity[c] * m for c in camp.cities_of(f)), []
    if k == "golden_age":
        return sum((camp.prosperity[c] + 1) * 6 + PROSPERITY_VALUE for c in camp.cities_of(f)), []
    if k in ("build", "reform", "charter"):
        n = {"build": 2, "reform": 2, "charter": 3}[k]
        cost = 80 if k == "build" else 0
        if k == "build" and gold < 80 + camp.upkeep(f):
            return -1, []
        return _best_city(camp, f, k, lambda c: min(n, 10 - camp.prosperity[c]) * PROSPERITY_VALUE - cost
                          + (10 if c in frontier(camp, f) else 20))
    if k == "loan":
        return (90 if gold < camp.upkeep(f) * 1.5 else -1), []
    if k == "debt":
        return (90 if gold > 220 + camp.upkeep(f) * 2 else -1), []
    if k in ("hunt", "bill", "dragon_gold"):
        return {"hunt": 30, "bill": 300, "dragon_gold": 400}[k], []
    if k == "old_debt":
        return _best_rival(camp, f, k, lambda r: 45 - (8 if camp.relation(f, r) > 40 else 0))
    if k == "deep_vein":
        return 35 * len(camp.cities_of(f)), []
    if k == "thievery":
        return _best_rival(camp, f, k, lambda r: min(80, camp.gold[r]))
    if k == "tribute":
        own = set(camp.cities_of(f))
        payers = [x for x in camp.alive() if x not in (f, "goblin") and camp.relation(f, x) < 30
                  and any(camp.owner[n] == x for c in own for n in neighbors(c))]
        return sum(min(50, camp.gold[x]) for x in payers), []
    if k == "desert_caravans":
        friends = [x for x in camp.alive() if x not in (f, "goblin")
                   and (camp.at_peace(f, x) or camp.relation(f, x) >= 40)]
        return 45 * len(friends) + 20, []
    # --- recruiting
    budgets = {"levy": 90, "guard": 90, "militia_call": 130, "recruiters": 140, "raise_dead": 220,
               "mercenary_company": 350, "forge_golem": 270, "troll_wakes": 400}
    if k in budgets:
        if k == "mercenary_company" and gold < 150 + camp.upkeep(f):
            return -1, []
        score, city = _recruit_city(camp, f, options(camp, f, k, []))
        if city is None:
            return -1, []
        cost = 150 if k == "mercenary_company" else 0
        return budgets[k] * POWER_VALUE * econ * (0.7 + 0.3 * min(score, 1.5)) - cost, [city]
    if k == "volunteers":
        score, city = _recruit_city(camp, f, options(camp, f, k, []))
        return (camp.prosperity[city] * 25 * POWER_VALUE * econ if city else -1), ([city] if city else [])
    if k == "conscription":
        return sum(40 + 15 * camp.prosperity[c] for c in camp.cities_of(f)) * POWER_VALUE * econ, []
    if k == "harvest":
        return (len(camp.cities_of(f)) * 40 + 50) * POWER_VALUE * econ, []
    if k == "brood":
        return len(camp.cities_of(f)) * 110 * POWER_VALUE * econ, []
    if k == "golden_contract":
        if gold < 400:
            return -1, []
        score, city = _recruit_city(camp, f, options(camp, f, k, []))
        return (220 * econ if city else -1), [city]
    # --- war
    if k == "assault":
        return _attack_plan(camp, f, k)
    if k == "blitz":
        return _attack_plan(camp, f, k, 1.15)
    if k == "longships":
        return _attack_plan(camp, f, k)
    if k in ("march", "forced_march", "mother_tree"):
        return _move_plan(camp, f, k)
    if k == "ancient_map":
        front = frontier(camp, f)
        best = (-1.0, [])
        for o in options(camp, f, k, []):
            if camp.officer_city[o] in front or not camp.squads[o]:
                continue
            for c in options(camp, f, k, [o]):
                if c in front:
                    v = 30 + 0.06 * camp.power(o) + threat(camp, f, c) / 40
                    if v > best[0]:
                        best = (v, [o, c])
        return best
    if k == "raid":
        best = (-1.0, [])
        for c in options(camp, f, k, []):
            for o in options(camp, f, k, [c]):
                risk = 20 if camp.defense_power(c) > camp.power(o) * 1.5 else 0
                v = camp.prosperity[c] * 12 + 25 - risk
                if v > best[0]:
                    best = (v, [c, o])
        return best
    if k == "wolf_hunt":
        def s(o):
            here = camp.officer_city[o]
            t = sorted((camp.prosperity[n] for n in neighbors(here)
                        if camp.owner[n] != f and not camp.at_peace(f, camp.owner[n])), reverse=True)[:2]
            return sum(p * 12 + 25 for p in t) if camp.squads[o] else -1
        return _best_officer(camp, f, k, s)
    if k == "great_raid":
        own = set(camp.cities_of(f))
        t = [c for c in camp.owner if camp.owner[c] != f and not camp.at_peace(f, camp.owner[c])
             and any(n in own for n in neighbors(c))]
        return sum(camp.prosperity[c] * 8 + 20 for c in t), []
    if k == "siege":
        return _best_city(camp, f, k, lambda c: 50 + camp.prosperity[c] * 8
                          + (60 if camp.defense_power(c) > _frontline_officer(camp, f) else 0))
    if k in ("fortify", "thicket_spirits", "rune_gates"):
        m = {"fortify": 1.4, "thicket_spirits": 1.8, "rune_gates": 2.0}[k]

        def s(c):
            t = threat(camp, f, c)
            d = camp.defense_power(c)
            if t <= 0:
                return -1
            return min(250, t * 0.25 * (m - 1) / 0.4) * (1.5 if t > d * 0.8 else 0.5) * (2 if c == FACTION[f].capital
                                                                                       else 1)
        return _best_city(camp, f, k, s)
    if k == "supplies":
        def s(o):
            return 40 + camp.power(o) * 0.05 if camp.squads[o] and camp.officer_city[o] in frontier(camp, f) else -1
        return _best_officer(camp, f, k, s)
    if k in ("morale", "griffon_order", "feigned_retreat", "hero_saga"):
        m = {"morale": 0.25, "griffon_order": 0.4, "feigned_retreat": 0.6, "hero_saga": 0.5}[k]
        front = set(frontier(camp, f))

        def s(o):
            if camp.officer_city[o] not in front:
                return -1
            return camp.power(o) * m * 0.35 + (25 if k == "griffon_order" and o not in camp.ready else 0)
        return _best_officer(camp, f, k, s)
    if k in ("forest_wrath", "fire_rain"):
        frac = 0.3 if k == "forest_wrath" else 0.35

        def s(c):
            troops = sum(camp.power(o.key) for o in camp.officers_in(c)) + sum(t.power for t in camp.free[c])
            return troops * frac * POWER_VALUE
        return _best_city(camp, f, k, s)
    # --- council and cards
    if k == "patrol":
        return 55, []
    if k == "moon_rite":
        return 110, []
    if k == "scouts":
        return _best_rival(camp, f, k, lambda r: 100 + (5 if r != "goblin" else 0))
    if k == "dead_whisper":
        return _best_rival(camp, f, k, lambda r: 55)
    if k == "omen":
        return 8, []
    if k == "denounce":
        return _best_rival(camp, f, k, lambda r: 20 if any(c.card.tier == "curse" for c in camp.realms[r].hand)
                           else 3)
    if k in ("feast", "mead_feast"):
        def s(c):
            low = sum(max(0, 70 - camp.loyalty[o.key]) for o in camp.officers_in(c))
            return low * 0.6 + (camp.power(max(camp.officers_in(c), key=lambda o: camp.power(o.key)).key) * 0.15
                                * 0.35 if k == "mead_feast" and c in frontier(camp, f) else 0)
        return _best_city(camp, f, k, s)
    if k == "tourney":
        return sum(max(0, 70 - camp.loyalty[o]) for o in camp.realms[f].council) * 0.4 + 15, []
    if k == "parade":
        return 25, []
    if k == "pilgrimage":
        return _best_officer(camp, f, k, lambda o: max(0, 70 - camp.loyalty[o]) * 0.8)
    if k == "peers_court":
        curses = sum(1 for c in camp.realms[f].hand if c.card.tier == "curse")
        return 70 + 40 * curses, []
    if k == "counterspy":
        return sum(55 for c in camp.realms[f].all_cards() if c.card.tier == "curse"), []
    if k == "mobilize":
        return (90 if _hand_has_more(camp, f, inst) else -1), []
    if k == "genie_lamp":
        return 130, []
    # --- intrigue against rivals
    def hostile(r):
        return 1.0 + (50 - min(50, camp.relation(f, r))) / 50 + _rival_threat(camp, f, r) / 1500
    if k == "arson":
        return _best_rival(camp, f, k, lambda r: min(150, camp.gold[r] // 4) * 0.7 * hostile(r))
    if k == "agitators":
        return _best_rival(camp, f, k, lambda r: 55 * hostile(r))
    if k == "letters":
        return _best_rival(camp, f, k, lambda r: 45 * hostile(r))
    if k == "plague_cauldron":
        return _best_rival(camp, f, k, lambda r: 90 * hostile(r))
    if k == "mushroom_haze":
        return _best_rival(camp, f, k, lambda r: 60 * hostile(r))
    if k == "all_seeing":
        return _best_rival(camp, f, k, lambda r: sum(sorted((card_value(camp, r, c) for c in camp.realms[r].hand),
                                                            reverse=True)[:2]) * 0.6 * hostile(r))
    if k == "secret_auction":
        return _best_rival(camp, f, k, lambda r: 70 if camp.realms[r].hand else -1)
    if k == "harem_intrigue":
        return _best_rival(camp, f, k, lambda r: 70 * hostile(r) if len(camp.realms[r].council) > 1 else -1)
    if k == "winter_storm":
        return _best_rival(camp, f, k, lambda r: 30 + _rival_threat(camp, f, r) * 0.12)
    if k == "sabotage":
        return _best_city(camp, f, k, lambda c: (2 * PROSPERITY_VALUE * 0.6 + 40) * hostile(camp.owner[c])
                          * (1 if camp.prosperity[c] > 2 else 0.4))
    if k == "bribe":
        if gold < 100 + camp.upkeep(f):
            return -1, []
        return _enemy_officer(camp, f, k, lambda o: (camp.power(o) * POWER_VALUE + 120 - 100)
                              if camp.loyalty[o] - 30 < 20 and OFFICER[o].rank > 0 else -1)
    if k == "plot":
        intrigue = council_totals(camp.realms[f].council)["ИНТРИГА"]

        def s(o):
            if OFFICER[o].rank == 0 and OFFICER[o].faction == camp.allegiance[o]:
                return -1
            ch = max(0, min(0.95, 0.35 + (60 - camp.loyalty[o]) / 100 + intrigue / 400
                            + (0.15 if camp.realms[f].course == "intrigue" else 0)))
            return ch * (camp.power(o) * POWER_VALUE + 150)
        return _enemy_officer(camp, f, k, s)
    if k == "book_of_grudges":
        return _best_rival(camp, f, k, lambda r: (_rival_threat(camp, f, r) * 0.1 + 60)
                           if camp.relation(f, r) < 30 and (f, r) not in camp.grudge else -1)
    # --- diplomacy
    if k == "buyout":
        return _best_city(camp, f, k, lambda c: _city_worth(camp, c) - camp.prosperity[c] * 100
                          if camp.gold[f] - camp.prosperity[c] * 100 > camp.upkeep(f) * 2 else -1)
    if k == "embassy":
        return _best_rival(camp, f, k, lambda r: (60 if _rival_threat(camp, f, r) > camp.army(f) * 0.3 else 15)
                           if camp.relation(f, r) < 70 else -1)
    if k == "trade_pact":
        return _best_rival(camp, f, k, lambda r: 150 if camp.relation(f, r) >= 50
                           and frozenset((f, r)) not in camp.trade else -1)
    if k in ("truce", "grand_embassy"):
        need = 30 if k == "truce" else 40

        def s(r):
            if camp.relation(f, r) < need or camp.at_peace(f, r):
                return -1
            danger = _rival_threat(camp, f, r)
            our = sum(camp.defense_power(c) for c in frontier(camp, f)) or 1
            v = 30 + min(250, danger / our * 120)
            return v + (300 if k == "grand_embassy" else 0)
        return _best_rival(camp, f, k, s)
    return -1, []


VALUE = _v


# --- turn ----------------------------------------------------------------------------------------
def manage(camp, f: str) -> None:
    """Fill squads with the free troops in their city, hire with spare gold."""
    for c in camp.cities_of(f):
        offs = sorted(camp.officers_in(c), key=lambda o: -o.leadership)
        for t in sorted(camp.free[c], key=lambda t: -t.power):
            for o in offs:
                if camp.assign(o.key, t.id):
                    break
    up = camp.upkeep(f)
    reserve = 80 + 2 * up
    margin = camp.expected_income(f) - up
    if margin < 0:
        reserve = 4 * up                                # cannot afford a bigger army
    front = frontier(camp, f) or camp.cities_of(f)
    for c in sorted(front, key=lambda c: -threat(camp, f, c)):
        for o in camp.officers_in(c):
            while camp.gold[f] > reserve:
                room = o.leadership - camp.power(o.key)
                cands = [k for k in camp._pool(c) if ROSTER[k].cost <= room and ROSTER[k].cost <= camp.gold[f] - reserve
                         and not ROSTER[k].boss and camp.troop_upkeep(f, k) <= max(0, margin - 0.1 * up)]
                if not cands or len(camp.squads[o.key]) >= 7:
                    break
                k = max(cands, key=lambda k: ROSTER[k].cost)
                t = camp.hire(c, k)
                camp.assign(o.key, t.id)
                margin -= camp.troop_upkeep(f, k)


COUNCIL_HINT = {"basic": 55, "junk": 15, "moderate": 80, "strong": 140, "unique": 150, "faction": 0}


def council_score(members: Sequence[str], taste: Optional[Dict[str, float]] = None) -> float:
    """What a council brings: its personal cards, its threshold cards and its competence.
    ``taste`` makes every computer ruler value things a bit differently (uniques, thresholds)."""
    from .cards import hand_size, reserve, strife
    taste = taste or {}
    v = sum(COUNCIL_HINT[CARDS[k].tier] * taste.get(CARDS[k].tier, 1.0) for o in members for k in PERSONAL[o])
    v += sum(COUNCIL_HINT[CARDS[k].tier] * taste.get("threshold", 1.0) for k in threshold_cards(list(members)))
    v += 70 * (hand_size(list(members)) - 5) + 45 * reserve(list(members)) - (90 if strife(list(members)) else 0)
    return v


def choose_council(camp, f: str) -> List[str]:
    """Leader + four advisers, improved seat by seat while any swap helps."""
    from .faces import presence
    from .officers import OFFICERS
    leader = OFFICERS[f][0].key
    cands = [o.key for o in camp.officers_of(f) if o.key != leader]
    members = [leader] + sorted(cands, key=lambda k: -presence(OFFICER[k]))[:COUNCIL_SEATS - 1]
    import random as _r
    rr = _r.Random(f"taste:{camp.seed}:{f}")
    taste = {"unique": rr.uniform(0.6, 1.8), "threshold": rr.uniform(0.8, 1.2), "moderate": rr.uniform(0.8, 1.2)}
    best = council_score(members, taste)
    for _ in range(6):
        improved = False
        for i in range(1, len(members)):
            for c in cands:
                if c in members:
                    continue
                trial = members[:i] + [c] + members[i + 1:]
                v = council_score(trial, taste)
                if v > best + 1:
                    members, best, improved = trial, v, True
        if not improved:
            break
    return members


def fill_council(camp, f: str) -> None:
    r = camp.realms[f]
    if len(r.council) >= COUNCIL_SEATS:
        return
    camp.set_council(f, choose_council(camp, f), quiet=True)


def best_play(camp, f: str, ap_price: float = AP_PRICE) -> Optional[Tuple[float, object, list]]:
    r = camp.realms[f]
    best = None
    for inst in list(r.hand):
        if not camp.can_play(f, inst)[0]:
            continue
        v, targets = VALUE(camp, f, inst)
        if v is None or v <= 0:
            continue
        cost = inst.card.cost
        net = v - cost * ap_price
        if net <= 0:
            continue
        score = net / (cost + 0.5)
        if best is None or score > best[0]:
            best = (score, inst, targets)
    return best


# realms' leanings when they pick a course
COURSE_TASTE = {"khanate": {"war": 0.5}, "north": {"war": 0.3}, "league": {"intrigue": 0.3, "economy": 0.3},
                "sultanate": {"economy": 0.3}, "highland": {"defense": 0.3}, "ashen": {"intrigue": 0.3},
                "goblin": {"war": 0.4}, "sylvan": {"defense": 0.2}}


def course_scores(camp, f: str) -> Dict[str, float]:
    """How much each course suits the realm right now."""
    up = camp.upkeep(f)
    income = camp.expected_income(f)
    poor = income < up * 1.1 or camp.gold[f] < up
    v, _ = _attack_plan(camp, f, "assault")
    targets = sum(1 for c in options(camp, f, "assault", []))
    danger = max((threat(camp, f, c) / max(1.0, camp.defense_power(c)) for c in frontier(camp, f)), default=0)
    intrigue = council_totals(camp.realms[f].council)["ИНТРИГА"]
    s = {"balance": 1.8,
         "war": (1.2 + min(1.5, v / 300) + 0.1 * min(targets, 4)) * (0.5 if poor else 1.0),
         "economy": 2.6 if poor else 1.1,
         "defense": 1.0 + 1.6 * max(0.0, min(1.5, danger) - 0.6),
         "intrigue": 1.0 + (0.6 if intrigue >= 62 else 0) + (0.3 if v <= 0 else 0)}
    for k, d in COURSE_TASTE.get(f, {}).items():
        s[k] += d
    return s


def pick_course(camp, f: str) -> None:
    r = camp.realms[f]
    if r.course_cd > 0:
        return
    s = course_scores(camp, f)
    best = max(s, key=s.get)
    if best != r.course and s[best] > s[r.course] + 0.5:          # only for a clear reason
        camp.change_course(f, best)


def play_turn(camp, f: str) -> None:
    if not camp.realms[f].alive:
        return
    manage(camp, f)
    pick_course(camp, f)
    fill_council(camp, f)
    for _ in range(20):
        pick = best_play(camp, f)
        if pick is None:                 # nothing worth a full action left: spend what remains
            pick = best_play(camp, f, ap_price=0)
        if pick is None:
            break
        _, inst, targets = pick
        ok, _ = camp.play(f, inst, targets)
        if not ok:                       # a stale plan: drop the card from consideration this turn
            break
    manage(camp, f)
