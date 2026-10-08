"""Officers grow, fall and change their minds (pure Python, no pygame).

**Experience.** An officer earns experience in battle, when one of his cards is played and for
every turn in the council. Weak officers learn faster (``learn_rate``), so a nobody can climb
into the council over a campaign. Each level gives +1 to a stat (his best one or a random one)
or +20 leadership.

**Decline.** A heavy defeat may cost a stat point (a wound), and a celebrated officer who has
done nothing for a while may grow complacent and lose one. So the mighty can fall, too.

**Feats.** Rare deeds (``cards.FEATS``) earn a feat card - one of each per campaign - that
joins the officer's personal cards.

**Loyalty.** It rises when an adviser's cards are played and falls when he is ignored, when
the realm loses cities (the leader's authority suffers) or cannot pay its troops. Below 35 a
councillor grumbles (dead cards in the deck), below 30 he fights half-heartedly, below 20 he
may leave for the neighbour he likes best. At 100 (rare and fragile) he is devoted: his cards
cost 1 action point less and his squad fights 15% harder; at 90+ no bribe sways him.
"""

from __future__ import annotations

from typing import List, Optional

from . import reign
from .cards import CARDS
from .faces import presence
from .factions import CITY, FACTION, neighbors
from .officers import OFFICER, STATS

XP_WIN, XP_LOSS, XP_CARD, XP_SEAT, XP_DRILL = 25, 10, 8, 2, 5
LEAD_STEP, LEAD_MAX = 20, 900


def _g(o: str, male: str, female: str) -> str:
    return female if OFFICER[o].female else male


def xp_needed(level: int) -> int:
    return 60 + 10 * level


def learn_rate(camp, o: str) -> float:
    """Raw talents learn fast, famous captains slowly. Talent is judged by where he started, so a
    nobody keeps climbing even after he has made his name."""
    return 0.2 + 4 * (1 - presence(OFFICER[o])) ** 4


def gain_xp(camp, o: str, amount: float, deed: bool = True) -> None:
    """``deed``: earned by doing something (resets idleness), not by drilling in garrison."""
    if o not in camp.xp:
        return
    camp.xp[o] += amount * learn_rate(camp, o)
    if deed:
        camp.idle[o] = 0
    while camp.xp[o] >= xp_needed(camp.level[o]):
        camp.xp[o] -= xp_needed(camp.level[o])
        level_up(camp, o)


def level_up(camp, o: str) -> None:
    camp.level[o] += 1
    camp.stats["levels"][camp.allegiance[o]] += 1
    st = camp.ostats[o]
    name = OFFICER[o].name
    if camp.rng.random() < 0.2 and camp.olead[o] < LEAD_MAX:
        camp.olead[o] = min(LEAD_MAX, camp.olead[o] + LEAD_STEP)
        camp.log_event(camp.allegiance[o], f"{name}: уровень {camp.level[o]}, лидерство {camp.olead[o]}")
    else:
        room = [i for i in range(len(STATS)) if st[i] < 20]
        if room:
            if camp.rng.random() < 0.5:                       # sharpen his strength...
                i = max(room, key=lambda k: st[k])
            else:                                             # ...or learn something new
                i = camp.rng.choice(room)
            st[i] += 1
            camp.log_event(camp.allegiance[o], f"{name}: уровень {camp.level[o]}, {STATS[i]} {st[i]}")
    if camp.level[o] >= 10:
        award(camp, o, "war_legend")
    camp.refresh_council_of(o)


def degrade(camp, o: str, why: str) -> None:
    st = camp.ostats[o]
    cands = [i for i in range(len(STATS)) if st[i] > 2]
    if not cands:
        return
    i = max(cands, key=lambda k: st[k] + camp.rng.random() * 6)  # the proud lose what they shine in
    st[i] -= 1
    camp.stats["declines"][camp.allegiance[o]] += 1
    camp.log_event(camp.allegiance[o], f"{OFFICER[o].name}: {why}, {STATS[i]} {st[i]}")
    camp.refresh_council_of(o)


def award(camp, o: str, feat: str) -> None:
    """One of each feat per campaign: the deed earns the officer a feat card."""
    if feat in camp.feats or o not in camp.xp:
        return
    camp.feats[feat] = o
    camp.extra.setdefault(o, []).append(feat)
    camp.claim[o] = camp.claim.get(o, 0) + 15
    camp.stats["feats"][feat] += 1
    f = camp.allegiance[o]
    camp.log_event(f, f"ПОДВИГ: {OFFICER[o].name} - {CARDS[feat].name}")
    r = camp.realms.get(f)
    if r and o in r.council:
        r.draw.insert(camp.rng.randrange(len(r.draw) + 1), camp._inst(feat, o))
    camp.change_loyalty(o, 15)


# --- events --------------------------------------------------------------------------------------
def on_card_used(camp, f: str, inst) -> None:
    o = inst.origin
    if o in OFFICER and camp.allegiance.get(o) == f:
        camp.last_used[o] = camp.turn
        camp.claim[o] = camp.claim.get(o, 0) + 1
        gain_xp(camp, o, XP_CARD)
        camp.change_loyalty(o, 2)


def on_battle(camp, b) -> None:
    """Experience, streaks, wounds and feats after a storm."""
    won = bool(b.att_won)
    ratio = min(b.a, b.d) / max(b.a, b.d, 1)
    sides = ((b.officers, won, b.a, b.d), (b.defenders, not won, b.d, b.a))
    for officers, side_won, mine, theirs in sides:
        for o in officers:
            if o not in camp.xp:
                continue
            gain_xp(camp, o, XP_WIN if side_won else XP_LOSS)
            camp.claim[o] = camp.claim.get(o, 0) + (4 if side_won else -1)
            if side_won:
                camp.streak[o] = camp.streak.get(o, 0) + 1
                if camp.streak[o] >= 8:
                    award(camp, o, "unbroken")
                if mine * 3 <= theirs:
                    award(camp, o, "giant_slayer")
            else:
                camp.streak[o] = 0
                if ratio < 0.6 and camp.rng.random() < 0.2:
                    degrade(camp, o, _g(o, "тяжело ранен", "тяжело ранена"))
    if won:
        city = b.city
        if city == FACTION[b.defender].capital and b.p < 0.5:  # the enemy's seat, against the odds
            lead = max(b.officers, key=camp.power, default=None)
            if lead:
                award(camp, lead, "wall_first")
        if CITY[city].faction == "goblin" and b.defender == "goblin":
            for o in b.officers:
                camp.lairs[o] = camp.lairs.get(o, 0) + 1
                if camp.lairs[o] >= 2:
                    award(camp, o, "goblin_bane")
    elif b.p >= 0.85 and b.defenders:                       # held against the odds
        hero = max(b.defenders, key=camp.power)
        award(camp, hero, "ford_hero")


def on_city_lost(camp, faction: str, city: str) -> None:
    """A lost city shakes the leader's authority: all his officers waver."""
    hit = 8 if city == FACTION[faction].capital else 2
    for o in camp.officers_of(faction):
        camp.change_loyalty(o.key, -hit)


def on_city_won(camp, faction: str) -> None:
    for o in camp.officers_of(faction):
        camp.change_loyalty(o.key, 1)


def on_unpaid(camp, faction: str) -> None:
    for o in camp.officers_of(faction):
        camp.change_loyalty(o.key, -1)


def turn(camp, faction: str) -> None:
    """Start of a realm's turn: seats, grudges, defections, complacency, feats of peace."""
    r = camp.realms[faction]
    for o in list(r.council):
        if camp.is_leader(o):
            continue
        gain_xp(camp, o, XP_SEAT)
        if camp.turn - camp.last_used.get(o, camp.turn) >= 5:
            camp.change_loyalty(o, -2 if reign.has(camp, faction, "paranoid") else -1)   # nobody listens
        if camp.loyalty[o] < 35 and camp.rng.random() < 0.15:
            camp.add_curse(faction, "unrest")
            camp.log_event(faction, f"{OFFICER[o].name} ропщет в совете")
    if reign.has(camp, faction, "generous") and camp.turn % 3 == 0:
        for x in camp.officers_of(faction):
            camp.change_loyalty(x.key, 1)
    if reign.has(camp, faction, "pious") and camp.turn % 4 == 0:
        from .diplomacy import borders, humans
        for x in humans(camp):
            if x != faction and borders(camp, faction, x):
                camp.change_relation(faction, x, 1)
    for o in [x.key for x in camp.officers_of(faction)]:
        camp.idle[o] = camp.idle.get(o, 0) + 1
        from .buildings import count
        school = count(camp, camp.officer_city[o], "academy") if o in camp.officer_city else 0
        gain_xp(camp, o, XP_DRILL * (2 if school else 1), deed=False)   # drill and garrison duty
        if camp.presence(o) > 0.6 and camp.idle[o] > 4 and camp.rng.random() < 0.015:
            degrade(camp, o, "почивает на лаврах")
        if camp.loyalty[o] < 20 and not camp.is_leader(o) \
                and camp.rng.random() < 0.2:
            desert(camp, o)
    # feats of peace and plenty
    truces = sum(1 for k, v in camp.truce.items() if faction in k and v > 0) + \
        sum(1 for k in camp.alliance if faction in k)
    if truces >= 7 and r.council:
        diplomat = max(r.council, key=lambda o: camp.stat(o, "ДИПЛОМАТИЯ"))
        award(camp, diplomat, "peacemaker")
    rich = [c for c in camp.cities_of(faction) if camp.prosperity[c] >= camp.max_prosperity(c)]
    if len(rich) >= 4:                                         # four cities grown as far as they can
        here = [o.key for c in rich for o in camp.officers_in(c)]
        if here:
            award(camp, max(here, key=lambda o: camp.stat(o, "УПРАВЛЕНИЕ")), "golden_governor")


def desert(camp, o: str) -> Optional[str]:
    """A disloyal officer leaves, squad and all, for the neighbour his realm gets on with best."""
    old = camp.allegiance[o]
    city = camp.officer_city.get(o)
    near: List[str] = []
    if city:
        near = [camp.owner[n] for n in neighbors(city) if camp.owner[n] not in (old, "goblin")]
    if not near:
        near = [f for f in camp.alive() if f not in (old, "goblin")]
    if not near:
        return None
    new = max(sorted(set(near)), key=lambda f: camp.relation(old, f) + camp.rng.random())  # sorted: same seed, same world
    camp.defect(o, new)
    camp.loyalty[o] = 55
    camp.stats["deserted_officers"][old] += 1
    camp.log_event(old, f"ИЗМЕНА: {OFFICER[o].name} {_g(o, 'ушёл', 'ушла')} к {FACTION[new].short}")
    return new
