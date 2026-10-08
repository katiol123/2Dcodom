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
from .cards import CARDS, COUNCIL_SEATS
from .factions import CITY, FACTION, neighbors
from .units import ROSTER

AP_PRICE = 35                   # what one action point is worth, in gold
TIER_HINT = {"faction": 150, "unique": 130, "strong": 140, "rare": 120, "moderate": 80, "basic": 60, "junk": 20, "curse": -60,
             "vice": -50, "feat": 170, "fate": -40}
POWER_VALUE = 0.7               # gold-equivalent of one point of troop power
PROSPERITY_VALUE = 45           # gold-equivalent of +1 prosperity in an own city


# --- helpers ---------------------------------------------------------------------------------
def card_value(camp, f: str, inst) -> float:
    """Quick worth of a card in hand (for what to keep, or what a spy throws away)."""
    return TIER_HINT[inst.card.tier] - inst.card.cost * 10


def cards_to_keep(camp, f: str, n: int) -> list:
    hand = [c for c in camp.realms[f].hand if c.card.tier not in ("curse", "vice") and not c.card.unplayable]
    if frontier(camp, f) and any(threat(camp, f, c) > 0 for c in frontier(camp, f)):
        # answers are worth keeping while enemies stand at the gates
        hand.sort(key=lambda c: -(card_value(camp, f, c) + (60 if c.card.reaction == "attacked" else 0)))
        return hand[:n]
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
        room = sum(max(0, camp.leadership(o.key) - camp.power(o.key)) for o in camp.officers_in(c))
        score = min(room, 300) / 300 + (0.6 if c in front else 0) + threat(camp, f, c) / 2000
        if score > best:
            best, pick = score, c
    return best, pick


def _city_worth(camp, city: str) -> float:
    return 300 + camp.prosperity[city] * 60 + (250 if CITY[city].kind == "capital" else 0)


LEADER_VALUE = 2500              # gold-equivalent of the ruler's life (what a succession costs)


def _odds(camp, f: str, group: Sequence[str], target: str, mult: float) -> Tuple[float, float, float]:
    a = camp.attack_power(f, group, target, mult)
    d = camp.defense_power(target)
    if (camp.owner[target], f) in camp.grudge:
        d *= 1.3
    if camp.owner[target] != "goblin" and camp.relation(f, camp.owner[target]) <= 14:
        d *= 1.15
    return camp.win_chance(a, d), a, d


def _desperate(camp, f: str, target: str) -> bool:
    """Stakes high enough to risk the ruler: the realm is down to its last cities, or the target is
    its own lost capital."""
    from .factions import FACTION
    return len(camp.cities_of(f)) <= 2 or (f in FACTION and target == FACTION[f].capital)


def _attack_plan(camp, f: str, key: str, mult: float = 1.0) -> Tuple[float, list]:
    from .diplomacy import enemy_of_alliance, hegemon
    from . import reign
    from .succession import BATTLE_DEATH_LOST, BATTLE_DEATH_WON
    best = (-1.0, [])
    h = hegemon(camp)
    foes = set(enemy_of_alliance(camp, f)) | ({h} if h and h != f else set())
    from .horde import odds_bonus
    need = reign.min_odds(camp, f) - odds_bonus(camp, f)
    ruler = camp.leader.get(f)
    for target in options(camp, f, key, []):
        cands = options(camp, f, key, [target])
        cands = sorted(cands, key=lambda o: -camp.power(o) * camp.officer_mult(o))[:MAX_GROUP]
        if not cands:
            continue
        p, a, d = _odds(camp, f, cands, target, mult)
        if ruler in cands and f != camp.player:
            # the ruler rides out only when the storm is safe enough - or when there is no other way
            # and losing the city weighs more than the risk of losing him
            others = [o for o in options(camp, f, key, [target]) if o != ruler]
            others = sorted(others, key=lambda o: -camp.power(o) * camp.officer_mult(o))[:MAX_GROUP]
            p2, a2, d2 = _odds(camp, f, others, target, mult) if others else (0.0, 0.0, d)
            if p < reign.leader_odds(camp, f):
                if p2 >= need:
                    cands, p, a, d = others, p2, a2, d2
                elif not (_desperate(camp, f, target) and p >= need):
                    continue
        if p < need:
            continue
        hostility = 1.0 + (40 - min(40, camp.relation(f, camp.owner[target]))) / 80
        if camp.realms[camp.owner[target]].course == "economy":
            hostility *= 1.4                     # a rich realm that does not arm itself is tempting prey
        if camp.owner[target] in foes:
            hostility *= 1.35                    # the alliance's common enemy / the hegemon
        if camp.realms[camp.owner[target]].unrest:
            hostility *= 1.25                    # a throne that shakes invites the sword
        hostility *= reign.hostility(camp, f, camp.owner[target])
        v = p * _city_worth(camp, target) * reign.worth_mult(camp, f) * hostility - (1 - p) * a * 0.5 \
            - p * 0.3 * min(a, d) * POWER_VALUE
        if ruler in cands:                       # the price of risking the ruler's life
            v -= LEADER_VALUE * ((1 - p) * BATTLE_DEATH_LOST + p * BATTLE_DEATH_WON)
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


def _peaceful(camp, f: str, key: str, realm: Optional[str]) -> bool:
    """A hostile act aimed at a realm we are at peace with: the computer does not do that."""
    return key in HOSTILE and realm is not None and realm != f and camp.at_peace(f, realm)


def _best_rival(camp, f: str, key: str, score: Callable[[str], float]) -> Tuple[float, list]:
    best = (-1.0, [])
    for r in options(camp, f, key, []):
        if _peaceful(camp, f, key, r):
            continue
        v = score(r)
        if v > best[0]:
            best = (v, [r])
    return best


def _best_city(camp, f: str, key: str, score: Callable[[str], float]) -> Tuple[float, list]:
    best = (-1.0, [])
    for c in options(camp, f, key, []):
        if c in CITY and _peaceful(camp, f, key, camp.owner[c]):
            continue
        v = score(c)
        if v > best[0]:
            best = (v, [c])
    return best


def _best_officer(camp, f: str, key: str, score: Callable[[str], float]) -> Tuple[float, list]:
    return _best_city(camp, f, key, score)


def _enemy_officer(camp, f: str, key: str, score: Callable[[str], float]) -> Tuple[float, list]:
    best = (-1.0, [])
    for c in options(camp, f, key, []):
        if _peaceful(camp, f, key, camp.owner[c]):
            continue
        for o in options(camp, f, key, [c]):
            v = score(o)
            if v > best[0]:
                best = (v, [c, o])
    return best


def _goblin_target(camp, f: str) -> bool:
    """Our best storm would hit a goblin lair (buying the horde off would forbid it)."""
    v, plan = _attack_plan(camp, f, "assault")
    return bool(plan) and camp.owner[plan[0]] == "goblin"


def arrives(camp, f: str, rival: str) -> float:
    """Chance that a curse we slip into the rival's deck gets there: a council with a good eye for
    spies (РАЗВЕДКА 62+) catches a third, a realm on the course of secret policy half; a ПЕРЕХВАТ
    ГОНЦА in his hand stops it all - but we know of it only if we have seen his hand this round."""
    r = camp.realms[rival]
    caught = max(0.35 if camp.intercepts(r.council) else 0.0, 0.5 if r.course == "intrigue" else 0.0)
    if camp.realms[f].revealed.get(rival, -99) >= camp.turn and any(c.card.reaction == "cursed" for c in r.hand):
        return 0.0
    return 1.0 - caught


def _frontline_officer(camp, f: str) -> float:
    front = set(frontier(camp, f))
    return max((camp.power(o.key) for o in camp.officers_of(f) if camp.officer_city[o.key] in front), default=0)


def _hand_has_more(camp, f: str, exclude) -> bool:
    return any(c is not exclude and not c.card.unplayable and c.card.cost > 0 for c in camp.realms[f].hand)


def _horde_danger(camp, f: str) -> float:
    """What the horde's armies at our border may cost us while it is not bought off."""
    from .horde import border
    danger = 0.0
    for c in border(camp, f):
        g = max((sum(camp.power(o.key) * camp.officer_mult(o.key) for o in camp.officers_in(n))
                 for n in neighbors(c) if camp.owner[n] == "goblin"), default=0.0)
        danger += camp.win_chance(g, camp.defense_power(c)) * _city_worth(camp, c) * 0.5
    return danger


# the horde's versions of cards are valued as the originals
ALIAS = {"dirty_tricks": "letters", "flea_market": "fair", "fat_year": "golden_age"}


# --- card values: (value in gold, targets) ----------------------------------------------------
def _v(camp, f, inst) -> Tuple[float, list]:
    k = ALIAS.get(inst.key, inst.key)
    gold = camp.gold[f]
    econ = _econ_factor(camp, f)
    from . import reign
    PV = reign.prosperity_value(camp, f, PROSPERITY_VALUE)      # a builder values growth more
    if k == "tax":
        def s(c):
            over = camp.taxed.get(c, -9) >= camp.turn - 1 and camp.realms[f].course != "economy"
            return camp.income_of(c, f) - (PV * 1.3 if over else 0)
        return _best_city(camp, f, k, s)
    if k == "fair":
        return _best_city(camp, f, k, lambda c: camp.prosperity[c] * 10 + (PV
                                                                            if camp.prosperity[c] < camp.max_prosperity(c)
                                                                            else 0))
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
        poor = sorted(camp.cities_of(f), key=lambda c: camp.prosperity[c])[:2]
        return sum(camp.prosperity[c] * 6 for c in camp.cities_of(f)) + sum(
            PV + 6 for c in poor if camp.prosperity[c] < camp.max_prosperity(c)), []
    if k in ("build", "reform", "charter"):
        n = {"build": 2, "reform": 2, "charter": 3}[k]
        cost = 80 if k == "build" else 0
        if k == "build" and gold < 80 + camp.upkeep(f):
            return -1, []
        def room(c):                         # a city at its room gains nothing: no card wasted on it
            r = min(n, camp.max_prosperity(c) - camp.prosperity[c])
            return r * PV - cost + (10 if c in frontier(camp, f) else 20) if r > 0 else -1
        return _best_city(camp, f, k, room)
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
                  and not camp.at_peace(f, x) and any(camp.owner[n] == x for c in own for n in neighbors(c))]
        return sum(min(50, camp.gold[x]) for x in payers), []
    if k in ("buy_off", "goblin_tongue"):
        from .horde import BUY_OFF_SILVER, buy_off_price, threatened
        if not threatened(camp, f):
            if k == "goblin_tongue":
                score, city = _recruit_city(camp, f, camp.cities_of(f))
                return 100 * POWER_VALUE * econ, [city]
            return BUY_OFF_SILVER * len(camp.cities_of(f)), []
        if camp.paid.get(f, 0) > 1 or reign.has(camp, f, "hunter"):
            return -1, []
        v = _horde_danger(camp, f) * (2.0 if reign.has(camp, f, "appeaser") else 1.0)
        v -= max(0.0, _attack_plan(camp, f, "assault")[0]) * 0.6 if _goblin_target(camp, f) else 0
        if k == "goblin_tongue":
            score, city = _recruit_city(camp, f, camp.cities_of(f))
            return v + 100 * POWER_VALUE * econ, [city]
        price = buy_off_price(camp, f)
        if gold - price < camp.upkeep(f):
            return -1, []
        return v - price, []
    if k == "head_hunters":
        def s(c):
            troops = sum(camp.power(o.key) for o in camp.officers_in(c)) + sum(t.power for t in camp.free[c])
            return (troops * 0.25 * POWER_VALUE + 40) * (1.5 if reign.has(camp, f, "hunter") else 1.0)
        return _best_city(camp, f, k, s)
    if k == "city_watch":
        from .order import CLEARED, DEN_TAX

        def s(c):
            law = camp.law.get(c, 6)
            den = DEN_TAX * camp.income_of(c, f) * 4 if c in camp.dens else 0
            return max(0, CLEARED + 1 - law) * 22 + den if law < CLEARED or den else -1
        return _best_city(camp, f, k, s)
    if k == "thieves_guild":
        from .order import SAFE

        def s(c):
            r = camp.owner[c]
            after = camp.law.get(c, 6) - 4
            hurt = (PROSPERITY_VALUE * 0.6 + camp.prosperity[c] * 6) if after < SAFE and c not in camp.dens else 0
            return (max(0, SAFE - after) * 15 + hurt) * (1.0 + (50 - min(50, camp.relation(f, r))) / 50)
        return _best_city(camp, f, k, s)
    if k == "shiny_pile":
        from .horde import great
        return (20 if great(camp) else 30) * len(camp.cities_of(f)), []
    if k == "intimidate":
        return _best_rival(camp, f, k, lambda r: 60 if camp.gold[r] >= 60 else PROSPERITY_VALUE * 0.5)
    if k == "great_fear":
        own = set(camp.cities_of(f))
        near = [x for x in camp.alive() if x != f and not camp.at_peace(f, x)
                and any(camp.owner[n] == x for c in own for n in neighbors(c))]
        return sum(50 if camp.gold[x] >= 50 else PROSPERITY_VALUE * 0.5 for x in near), []
    if k == "desert_caravans":
        friends = [x for x in camp.alive() if x not in (f, "goblin")
                   and (camp.at_peace(f, x) or camp.relation(f, x) >= 40)]
        return 45 * len(friends) + 20, []
    # --- recruiting
    budgets = {"levy": 90, "guard": 90, "militia_call": 130, "raise_dead": 220,
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
        from .horde import raid_mult
        best = (-1.0, [])
        for c in options(camp, f, k, []):
            for o in options(camp, f, k, [c]):
                risk = 20 if camp.defense_power(c) > camp.power(o) * 1.5 else 0
                v = (camp.prosperity[c] * 12 + 25) * raid_mult(camp, f) - risk
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
    if k == "purge":
        hand = [c for c in camp.realms[f].hand if c is not inst]
        if not hand:
            return -1, []
        worst = min(hand, key=lambda c: card_value(camp, f, c))
        v = -card_value(camp, f, worst)                           # burning a curse is worth a lot
        return (max(v, 0) + 45 if card_value(camp, f, worst) < 40 else -1), [worst.id]
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
        return sum(55 for c in camp.realms[f].all_cards() if c.card.tier == "curse" and c.key != "debt"), []
    if k == "pride":                       # listening to the proud adviser saves his loyalty (-8 if he waits)
        loyal = camp.loyalty.get(inst.origin, 60)
        return 24 + (45 if loyal < 45 else 0), []
    if k == "mobilize":
        return (90 if _hand_has_more(camp, f, inst) else -1), []
    if k == "genie_lamp":
        return 130, []
    # --- intrigue against rivals: the worse we stand with them, the more it is worth - and a curse
    # is worth only as much as the chance it gets through their watch (``arrives``)
    def hostile(r):
        return 1.0 + (50 - min(50, camp.relation(f, r))) / 50 + _rival_threat(camp, f, r) / 1500
    if k == "arson":
        return _best_rival(camp, f, k, lambda r: min(150, camp.gold[r] // 4) * 0.7 * hostile(r) * arrives(camp, f, r))
    if k == "agitators":
        return _best_rival(camp, f, k, lambda r: 55 * hostile(r) * arrives(camp, f, r))
    if k == "letters":
        return _best_rival(camp, f, k, lambda r: 45 * hostile(r) * arrives(camp, f, r))
    if k == "plague_cauldron":
        return _best_rival(camp, f, k, lambda r: 90 * hostile(r) * arrives(camp, f, r))
    if k == "mushroom_haze":
        return _best_rival(camp, f, k, lambda r: 60 * hostile(r) * arrives(camp, f, r))
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
                              if camp.loyalty[o] - 30 < 20 and not camp.is_leader(o) else -1)
    if k == "plot":
        intrigue = camp.totals(camp.realms[f].council)["ИНТРИГА"]

        def s(o):
            if camp.is_leader(o):
                return -1
            ch = max(0, min(0.95, 0.35 + (60 - camp.loyalty[o]) / 100 + intrigue / 400
                            + (0.15 if camp.realms[f].course == "intrigue" else 0)))
            return ch * (camp.power(o) * POWER_VALUE + 150)
        return _enemy_officer(camp, f, k, s)
    if k == "book_of_grudges":
        return _best_rival(camp, f, k, lambda r: (_rival_threat(camp, f, r) * 0.1 + 60)
                           if camp.relation(f, r) < 30 and (f, r) not in camp.grudge else -1)
    # --- diplomacy
    if k == "muster":
        up = camp.upkeep(f)
        spare = camp.gold[f] - (80 + 2 * up)
        if spare < 60 or camp.expected_income(f) < up * 1.1:
            return -1, []
        score, city = _recruit_city(camp, f, [c for c in options(camp, f, k, []) if camp.muster.get(c, 0) <= 0])
        if city is None:
            return -1, []
        room = sum(max(0, camp.leadership(o.key) - camp.power(o.key)) for o in camp.officers_in(city))
        return min(spare, room, 400) * 0.45 * camp.muster_turns(camp.realms[f].council) ** 0.5, [city]
    if k in ("ford_hero", "unbroken"):
        front = set(frontier(camp, f))
        return _best_officer(camp, f, k, lambda o: (camp.power(o) * 0.35 * 0.4 + 30)
                             if camp.officer_city[o] in front and camp.squads[o] else -1)
    if k == "talent_search":
        n = len(camp.officers_of(f))
        from .population import MAX_OFFICERS
        if n >= MAX_OFFICERS:
            return -1, []
        cities = camp.cities_of(f)
        from .buildings import count
        city = max(cities, key=lambda c: (count(camp, c, "academy"), c == FACTION[f].capital if f in FACTION else 0))
        return 60 + max(0, 14 - n) * 25, [city]
    if k == "tiltyard":
        from .buildings import BUILDINGS, MOUNT_OF
        cities = options(camp, f, "tiltyard", [])
        if not cities or camp.gold[f] - BUILDINGS["tiltyard"].cost < camp.upkeep(f) * 2 or f not in MOUNT_OF:
            return -1, []
        best = max(cities, key=lambda c: (threat(camp, f, c), len(camp.officers_in(c))))
        return 120 + 30 * len(camp.officers_in(best)), [best]
    if k == "master_builder":
        from .buildings import BUILDINGS, ORDER, _ai_value, can_build
        best = (-1.0, [])
        for c in camp.cities_of(f):
            front = any(camp.owner[n] != f and not camp.at_peace(f, camp.owner[n]) for n in neighbors(c))
            for b in ORDER:
                if can_build(camp, f, c, b, BUILDINGS[b].cost // 2)[0] and \
                        camp.gold[f] - BUILDINGS[b].cost // 2 > camp.upkeep(f) * 2:
                    v = _ai_value(camp, f, c, b, front) * 0.6
                    if v > best[0]:
                        best = (v, [c, b])
        return best
    if k == "physician":
        sick = [c for c in camp.cities_of(f) if c in camp.sick]
        if sick:
            c = max(sick, key=lambda c: len(camp.officers_in(c)) + (5 if camp.leader.get(f) in
                                                                  [o.key for o in camp.officers_in(c)] else 0))
            return 80 + 60 * len(camp.officers_in(c)), [c]
        return -1, []
    if k == "sappers":
        from .buildings import BUILDINGS
        opts = options(camp, f, k, [])
        if not opts:
            return -1, []
        c = max(opts, key=lambda c: sum(BUILDINGS[b].cost for b in camp.buildings[c]))
        return 0.5 * max(BUILDINGS[b].cost for b in camp.buildings[c]), [c]
    if k == "goblin_bane":
        score, city = _recruit_city(camp, f, options(camp, f, k, []))
        return (150 + 120 * POWER_VALUE * max(econ, 0.2)), [city]
    if k == "golden_governor":
        return 50 * sum(1 for c in camp.cities_of(f) if camp.prosperity[c] >= 7), []
    if k == "wall_first":
        return _attack_plan(camp, f, k, 1.25)
    if k == "war_legend":
        return _attack_plan(camp, f, k, 1.4)
    if k == "giant_slayer":
        return (camp.army(f) * 0.2 * 0.25 if frontier(camp, f) else -1), []
    if k == "peacemaker":
        return _best_rival(camp, f, k, lambda r: 30 + min(250, _rival_threat(camp, f, r) * 0.2)
                           if camp.relation(f, r) >= 20 and not camp.at_peace(f, r) else -1)
    if k == "buyout":
        return _best_city(camp, f, k, lambda c: _city_worth(camp, c) - camp.prosperity[c] * 100
                          if camp.gold[f] - camp.prosperity[c] * 100 > camp.upkeep(f) * 2 else -1)
    if k == "embassy":
        return _best_rival(camp, f, k, lambda r: (60 if _rival_threat(camp, f, r) > camp.army(f) * 0.3 else 15)
                           if camp.relation(f, r) < 70 else -1)
    from .diplomacy import can_propose, evaluate
    if k == "trade_pact":
        from .diplomacy import trade_gold
        return _best_rival(camp, f, k, lambda r: trade_gold(camp, f, r) * 8
                           if can_propose(camp, f, r, "trade")[0] and evaluate(camp, f, r, "trade", 20)[0] >= 0
                           else -1)
    if k in ("truce", "grand_embassy"):
        from .diplomacy import status
        bonus = 20 if k == "truce" else 35

        def s(r):
            kind = "alliance" if k == "grand_embassy" and status(camp, f, r) == "truce" else "truce"
            if not can_propose(camp, f, r, kind)[0] or evaluate(camp, f, r, kind, bonus)[0] < 0:
                return 40 if k == "grand_embassy" and camp.relation(f, r) < 60 else -1
            if kind == "alliance":
                return 250
            danger = _rival_threat(camp, f, r)
            our = sum(camp.defense_power(c) for c in frontier(camp, f)) or 1
            v = 30 + min(250, danger / our * 120)
            return v + (240 if k == "grand_embassy" else 0)
        return _best_rival(camp, f, k, s)
    return -1, []


VALUE = _v


def choose_answer(camp, b, cards):
    """Which answer a computer defender plays when its city is stormed (or None)."""
    a = camp.attack_power(b.attacker, b.officers, b.city, b.mult)
    d = camp.defense_power(b.city)
    p_def = 1 - camp.win_chance(a, d)
    keys = {c.key: c for c in cards}
    refuge = [n for n in neighbors(b.city) if camp.owner[n] == b.defender]
    if p_def < 0.2 and "withdraw" in keys and refuge:
        return keys["withdraw"]
    if p_def > 0.85:
        return None
    gains = {}
    if "sortie" in keys:
        gains["sortie"] = 1 - camp.win_chance(a, d * 1.3)
    if "ambush" in keys:
        gains["ambush"] = 1 - camp.win_chance(a * 0.85, d)
    if "reinforce" in keys:
        extra = max((camp.power(o.key) for n in refuge for o in camp.officers_in(n)), default=0)
        gains["reinforce"] = 1 - camp.win_chance(a, d + extra * 1.1)
    if not gains:
        return None
    best = max(gains, key=gains.get)
    return keys[best] if gains[best] > p_def + 0.05 else None


# --- turn ----------------------------------------------------------------------------------------
def manage(camp, f: str) -> None:
    """Fill squads with the free troops in their city, hire with spare gold."""
    for c in camp.cities_of(f):
        offs = sorted(camp.officers_in(c), key=lambda o: -camp.leadership(o.key))
        for t in sorted(camp.free[c], key=lambda t: -t.power):
            for o in offs:
                if camp.assign(o.key, t.id):
                    break
    up = camp.upkeep(f)
    reserve = 80 + 2 * up
    margin = camp.expected_income(f) - up
    if margin < 0:
        reserve = 4 * up                                # cannot afford a bigger army
    from . import reign
    from .horde import pen_hire, saving
    reserve = reign.reserve(camp, f, reserve) + saving(camp, f)          # the horde hoards for its great building
    from .buildings import tiltyard_mount
    pen = [c for c in camp.cities_of(f) if pen_hire(camp, c, "wolf_rider")]
    yard = {c: tiltyard_mount(camp, c) for c in camp.cities_of(f) if tiltyard_mount(camp, c)}
    front = [c for c in camp.cities_of(f) if camp.muster.get(c, 0) > 0 or c in pen or c in yard]   # open only there
    for c in sorted(front, key=lambda c: -threat(camp, f, c)):
        pool = (camp._pool(c) if camp.muster.get(c, 0) > 0 else []) + (["wolf_rider"] if c in pen else []) + \
            ([yard[c]] if c in yard and (camp.muster.get(c, 0) <= 0 or yard[c] not in camp._pool(c)) else [])
        for o in camp.officers_in(c):
            while camp.gold[f] > reserve:
                room = camp.leadership(o.key) - camp.power(o.key)
                cands = [k for k in pool if ROSTER[k].cost <= room and camp.hire_price(c, k) <= camp.gold[f] - reserve
                         and not ROSTER[k].boss and camp.troop_upkeep(f, k) <= max(0, margin - 0.1 * up)
                         and reign.hire_ok(camp, f, k)]
                if not cands or len(camp.squads[o.key]) >= 7:
                    break
                k = max(cands, key=lambda k: ROSTER[k].cost / camp.hire_price(c, k) + ROSTER[k].cost / 1000)
                t = camp.hire(c, k)
                if t is None:
                    break
                camp.assign(o.key, t.id)
                margin -= camp.troop_upkeep(f, k)


COUNCIL_HINT = {"basic": 55, "junk": 15, "moderate": 80, "strong": 140, "rare": 110, "unique": 150, "faction": 0, "vice": -60, "feat": 170, "fate": 0}


def council_score(camp, members: Sequence[str], taste: Optional[Dict[str, float]] = None) -> float:
    """What a council brings: its personal cards, its threshold cards and its competence.
    ``taste`` makes every computer ruler value things a bit differently (uniques, thresholds)."""
    taste = taste or {}
    m = list(members)
    v = sum(COUNCIL_HINT[CARDS[k].tier] * taste.get(CARDS[k].tier, 1.0) for o in m for k in camp.personal(o))
    v += sum(COUNCIL_HINT[CARDS[k].tier] * taste.get("threshold", 1.0) for k in camp.thresholds(m))
    v += 70 * (camp.hand_size(m) - 5) + 45 * camp.reserve(m) - (90 if camp.strife(m) else 0)
    v -= sum(max(0, 35 - camp.loyalty.get(o, 60)) * 2 for o in m)     # grumblers are a liability
    v += sum(2 * sum(camp.ostats[o]) + 25 * camp.level.get(o, 0) for o in m[1:])  # skill and renown
    from . import reign
    f = camp.allegiance.get(m[0]) if m else None
    if f and reign.has(camp, f, "nepotist"):
        v += sum(4 * camp.loyalty.get(o, 50) for o in m[1:])          # the faithful first
    if f and reign.has(camp, f, "meritocrat"):
        v += sum(3 * sum(camp.ostats[o]) for o in m[1:])              # the able first
    return v


def choose_council(camp, f: str) -> List[str]:
    """Leader + four advisers, improved seat by seat while any swap helps."""
    leader = camp.leader.get(f)
    cands = [o.key for o in camp.officers_of(f) if o.key != leader]
    head = [leader] if leader else []
    members = head + sorted(cands, key=lambda k: -camp.presence(k))[:COUNCIL_SEATS - len(head)]
    import random as _r
    rr = _r.Random(f"taste:{camp.seed}:{f}")
    taste = {"unique": rr.uniform(0.6, 1.8), "threshold": rr.uniform(0.8, 1.2), "moderate": rr.uniform(0.8, 1.2)}
    best = council_score(camp, members, taste)
    for _ in range(6):
        improved = False
        for i in range(len(head), len(members)):
            for c in cands:
                if c in members:
                    continue
                trial = members[:i] + [c] + members[i + 1:]
                v = council_score(camp, trial, taste)
                if v > best + 1:
                    members, best, improved = trial, v, True
        if not improved:
            break
    return members


def fill_council(camp, f: str) -> None:
    """Fill empty seats; every few turns look again - a risen officer may deserve a seat."""
    r = camp.realms[f]
    if len(r.council) < COUNCIL_SEATS:
        camp.set_council(f, choose_council(camp, f), quiet=True)
        return
    from . import reign
    every = 3 if reign.has(camp, f, "meritocrat") else 6
    if camp.turn % every == (camp.order.index(f) if f in camp.order else 0) % every:
        new = choose_council(camp, f)
        if set(new) != set(r.council) and council_score(camp, new) > council_score(camp, r.council) + 80:
            camp.set_council(f, new, quiet=True)
            camp.stats["reshuffles"][f] += 1


# hostile acts: the computer does not spend them on realms it is at peace with (allies least of all)
HOSTILE = {"arson", "agitators", "letters", "dirty_tricks", "plague_cauldron", "mushroom_haze", "all_seeing",
           "secret_auction", "harem_intrigue", "winter_storm", "sabotage", "bribe", "plot", "sappers",
           "thieves_guild", "thievery", "intimidate", "denounce", "old_debt"}


def _victim(camp, targets) -> Optional[str]:
    from .officers import OFFICER as _O
    for t in targets[:2]:
        if isinstance(t, str):
            if t in camp.realms:
                return t
            if t in CITY:
                return camp.owner[t]
            if t in _O:
                return camp.allegiance.get(t)
    return None


def peace_mult(camp, f: str, key: str, targets) -> float:
    if key not in HOSTILE:
        return 1.0
    v = _victim(camp, targets)
    if v is None or v == f or not camp.at_peace(f, v):
        return 1.0
    from .diplomacy import status
    return 0.05 if status(camp, f, v) == "alliance" else 0.1


def best_play(camp, f: str, ap_price: float = AP_PRICE) -> Optional[Tuple[float, object, list]]:
    from . import reign
    r = camp.realms[f]
    best = None
    for inst in list(r.hand):
        if not camp.can_play(f, inst)[0]:
            continue
        v, targets = VALUE(camp, f, inst)
        if v is None or v <= 0:
            continue
        if peace_mult(camp, f, inst.key, targets) < 1:
            continue                                     # no hostile acts against friends, not even with spare points
        v *= reign.card_mult(camp, f, inst.card)
        cost = camp.card_cost(f, inst)
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
    intrigue = camp.totals(camp.realms[f].council)["ИНТРИГА"]
    s = {"balance": 1.8,
         "war": (1.2 + min(1.5, v / 300) + 0.1 * min(targets, 4)) * (0.5 if poor else 1.0),
         "economy": 2.6 if poor else 1.1,
         "defense": 1.0 + 1.6 * max(0.0, min(1.5, danger) - 0.6),
         "intrigue": 1.0 + (0.6 if intrigue >= 62 else 0) + (0.3 if v <= 0 else 0)}
    for k, d in COURSE_TASTE.get(f, {}).items():
        s[k] += d
    from . import reign
    for k, d in reign.course_bias(camp, f).items():
        s[k] += d
    return s


def pick_course(camp, f: str) -> None:
    r = camp.realms[f]
    if r.course_cd > 0:
        return
    s = course_scores(camp, f)
    best = max(s, key=s.get)
    from . import reign
    if best != r.course and s[best] > s[r.course] + reign.course_margin(camp, f):   # only for a clear reason
        camp.change_course(f, best)


def play_turn(camp, f: str) -> None:
    if not camp.realms[f].alive:
        return
    manage(camp, f)
    from . import horde
    horde.ai_build(camp, f)                  # the horde's great building, once it has hoarded enough
    pick_course(camp, f)
    fill_council(camp, f)
    from .diplomacy import ai_turn
    ai_turn(camp, f, AP_PRICE)
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
    from .buildings import ai_build
    ai_build(camp, f, 80 + 2 * camp.upkeep(f))                 # spare gold and a spare point: build
    manage(camp, f)
