"""Rulers die and are succeeded (pure Python, no pygame).

A ruler never changes sides. He can die: in a lost battle (``BATTLE_DEATH``), when his city falls
with no road to retreat on, when his realm falls, and - rarely - of age or illness (``AGE_DEATH``
each own turn). The heir is the council member with the most presence and loyalty.

**Cards.** The first ruler brings the faction card; a successor's own cards become the ruler's
cards (he keeps them while he reigns, his seat is the ruler's seat). The cards of the ruler who
just died stay in the deck as his **legacy** (``Realm.legacy``) - but only his: when the next
ruler dies, the older legacy is gone, the faction card included.

**The heir** cannot be named: the court weighs merit (``claim``, ``heir_score``). Merit grows
with every own turn in the council, every card of his that is played, every battle won (a lost one
costs a little) and every feat; presence, level and loyalty count too. So a ruler shapes the
succession only by whom he trusts with seats, cards and armies.

**Political instability** (``UNREST_TURNS`` own turns) follows every succession, so that losing a
ruler on purpose never pays: one action point less every turn, the course is locked, all officers
lose loyalty at once (those passed over for the throne more), two СМУТЫ go into the deck, a
disloyal officer may rise as a pretender and leave with his squad, and the neighbours smell
weakness (the computer storms an unstable realm more eagerly and trusts it less as an ally).
"""

from __future__ import annotations

from typing import List, Optional

from .cards import CARDS, FACTION_CARD
from .factions import CITY
from .officers import OFFICER

BATTLE_DEATH_LOST, BATTLE_DEATH_WON = 0.12, 0.02
AGE_DEATH = 0.008
UNREST_TURNS = 6
UNREST_LOYALTY, PASSED_OVER = 15, 8


def _g(o: str, male: str, female: str) -> str:
    return female if OFFICER[o].female else male


def leader_cards(camp, faction: str, leader: Optional[str] = None) -> List[str]:
    """The cards a ruler brings: the faction card (first ruler) and his own cards."""
    leader = leader or camp.leader.get(faction)
    if not leader:
        return []
    first = OFFICER[leader].rank == 0 and OFFICER[leader].faction == faction
    return ([FACTION_CARD[faction]] if first else []) + list(camp.personal(leader))


def heir_score(camp, o: str) -> float:
    """Standing at court: merit earned in this campaign plus presence, level and loyalty."""
    f = camp.allegiance.get(o)
    seat = 10 if f in camp.realms and o in camp.realms[f].council else 0
    return camp.claim.get(o, 0) + 40 * camp.presence(o) + 3 * camp.level.get(o, 1) + \
        camp.loyalty.get(o, 50) / 10 + seat


def contenders(camp, faction: str, dead: Optional[str] = None) -> List[str]:
    """Officers of the realm by their claim to the throne, the likely heir first."""
    ruler = dead or camp.leader.get(faction)
    pool = [o.key for o in camp.officers_of(faction) if o.key != ruler and o.key not in camp.dead]
    native = [o for o in pool if OFFICER[o].faction == faction]   # turncoats inherit only if no one else can
    return sorted(native or pool, key=lambda o: -heir_score(camp, o))


def heir_of(camp, faction: str, dead: str) -> Optional[str]:
    c = contenders(camp, faction, dead)
    return c[0] if c else None


def die(camp, officer: str, cause: str) -> None:
    """An officer dies. His squad stays in the city as a garrison; a ruler is succeeded."""
    if officer in camp.dead:
        return
    f = camp.allegiance[officer]
    was_leader = camp.leader.get(f) == officer
    camp.dead.add(officer)
    camp.stats["deaths"][f] += 1
    city = camp.officer_city.pop(officer, None)
    if city and camp.owner.get(city) == f:
        camp.free[city].extend(camp.squads[officer])
    camp.squads[officer] = []
    camp.ready.discard(officer)
    r = camp.realms.get(f)
    name = OFFICER[officer].name
    if was_leader:
        camp.log_event(f, f"СМЕРТЬ ПРАВИТЕЛЯ: {name} {cause}")
        if r and r.alive:
            succeed(camp, f, officer)
        return
    camp.log_event(f, f"{name} {cause}")
    if r and officer in r.council:
        camp.set_council(f, [o for o in r.council if o != officer], quiet=True)


def succeed(camp, faction: str, dead: str) -> Optional[str]:
    r = camp.realms[faction]
    heir = heir_of(camp, faction, dead)
    legacy = [k for k in leader_cards(camp, faction, dead) if CARDS[k].tier != "vice"]
    for pile in (r.draw, r.hand, r.discard):              # the dead ruler's cards and the old legacy go
        pile[:] = [c for c in pile if c.origin not in ("faction", "legacy", dead)]
    r.legacy = legacy
    for k in legacy:
        r.draw.insert(camp.rng.randrange(len(r.draw) + 1), camp._inst(k, "legacy"))
    camp.leader[faction] = heir
    camp.stats["successions"][faction] += 1
    council = [o for o in r.council if o != dead]
    if heir is not None and heir not in council:          # the heir takes the ruler's seat with his cards
        for k in camp.personal(heir):
            r.draw.insert(camp.rng.randrange(len(r.draw) + 1), camp._inst(k, heir))
    r.council = ([heir] if heir else []) + [o for o in council if o != heir]
    camp._sync_thresholds(faction)
    if heir is None:
        return None
    camp.loyalty[heir] = 100
    # political instability
    r.unrest = UNREST_TURNS
    r.course_cd = max(r.course_cd, UNREST_TURNS)
    passed = {o for o in council if o != heir}
    for o in camp.officers_of(faction):
        if o.key != heir:
            camp.change_loyalty(o.key, -(UNREST_LOYALTY + (PASSED_OVER if o.key in passed else 0)))
    camp.add_curse(faction, "unrest", 2)
    camp.log_event(faction, f"НОВЫЙ ПРАВИТЕЛЬ: {OFFICER[heir].name}. ПОЛИТИЧЕСКАЯ НЕСТАБИЛЬНОСТЬ на "
                            f"{UNREST_TURNS} х. Наследие: " + (", ".join(CARDS[k].name for k in legacy) or "нет"))
    return heir


def ensure_ruler(camp, faction: str) -> None:
    """A living realm always has a living ruler (a realm revived by an event crowns its best claimant);
    the dead and the departed leave the council."""
    r = camp.realms.get(faction)
    if not r or not r.alive:
        return
    council = [o for o in r.council if o not in camp.dead and camp.allegiance.get(o) == faction]
    if council != r.council:
        r.council = council
        camp._sync_thresholds(faction)
    ruler = camp.leader.get(faction)
    if ruler and ruler not in camp.dead and camp.allegiance.get(ruler) == faction:
        return
    heir = heir_of(camp, faction, ruler or "")
    if heir is None and camp.cities_of(faction):         # a court with nobody left: a young claimant rises
        from .population import come_of_age
        heir = come_of_age(camp, faction)
    if heir is None:
        return
    for pile in (r.draw, r.hand, r.discard):              # the old court's cards left with it
        pile[:] = [c for c in pile if c.origin not in OFFICER or c.origin in r.council and c.origin not in camp.dead]
    camp.leader[faction] = heir
    camp.loyalty[heir] = 100
    if heir not in r.council:
        for k in camp.personal(heir):
            r.draw.insert(camp.rng.randrange(len(r.draw) + 1), camp._inst(k, heir))
    r.council = [heir] + [o for o in r.council if o != heir]
    camp._sync_thresholds(faction)
    camp.log_event(faction, f"НОВЫЙ ПРАВИТЕЛЬ: {OFFICER[heir].name} поднял{_g(heir, '', 'а')} павшее знамя")


def turn(camp, faction: str) -> None:
    """Start of a realm's own turn: old age, and the troubles of an unstable realm."""
    r = camp.realms[faction]
    leader = camp.leader.get(faction)
    if leader and camp.turn > 5 and faction != "goblin" and camp.rng.random() < AGE_DEATH:
        die(camp, leader, _g(leader, "скончался от болезни", "скончалась от болезни"))
    for o in r.council:                                   # a seat in the council is a claim at court
        if o != leader:
            camp.claim[o] = camp.claim.get(o, 0) + 3
    if r.unrest > 0:
        r.unrest -= 1
        r.ap = max(0, r.ap - 1)
        camp.stats["unrest_turns"][faction] += 1
        if faction != "goblin" and camp.rng.random() < 0.25:     # a pretender rises
            rivals = [o.key for o in camp.officers_of(faction) if o.key != camp.leader.get(faction)
                      and camp.loyalty.get(o.key, 60) < 45]
            if rivals:
                from .growth import desert
                o = min(rivals, key=lambda x: camp.loyalty[x])
                camp.log_event(faction, f"ПРЕТЕНДЕНТ: {OFFICER[o].name} не признал{_g(o, '', 'а')} "
                                        f"нового правителя")
                desert(camp, o)
        if r.unrest == 0:
            camp.log_event(faction, "Нестабильность улеглась: власть нового правителя признана")


def on_battle(camp, b) -> None:
    """A ruler in a battle may fall: often on the losing side, rarely among the winners."""
    won = bool(b.att_won)
    for officers, side_won in ((b.officers, won), (b.defenders, not won)):
        for o in officers:
            f = camp.allegiance.get(o)
            if camp.leader.get(f) != o or o in camp.dead:
                continue
            p = BATTLE_DEATH_WON if side_won else BATTLE_DEATH_LOST
            if camp.rng.random() < p:
                die(camp, o, _g(o, "пал в бою", "пала в бою") + f" ({CITY[b.city].name})")
