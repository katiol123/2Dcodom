"""Order in the cities (pure Python, no pygame).

Every city of men has ПОРЯДОК, 0..10 (``camp.law``). Each own turn it drifts one step towards
what the city can keep (``target``):

* a governor (any officer standing there) +1, and +1 more if his РАЗВЕДКА is 14+ (informers, watch);
* a garrison: +1 with 300 power of troops in the city, +2 with 700;
* a temple +1, the capital +1;
* wealth draws thieves: -1 for every point of prosperity above 6;
* sickness -2, the realm's political instability -1;
* the horde's shadow (a passive trait of the goblins): a city next to a lair -``HORDE_FEAR`` unless its
  realm has bought the horde off; crime there serves the goblins - what smugglers carry off and a
  ``FENCE`` share of what a thieves' den skims from the tax go to the horde's treasury.

Battles in the city cost 2 order, raids 1, over-taxing 1; a taken city starts at ``TAKEN``.
Low order breeds crime (``CRIME`` chance per own turn below ``SAFE``): a thieves' den (prosperity -1,
and while it stands the tax there brings ``DEN_TAX`` less; it is cleared when order climbs back to
``CLEARED``), a riot of the mob (prosperity -1, the garrison loses a warrior) or smugglers (the treasury
loses gold). So rich cities left without governors and troops slide back by themselves.
Goblin lairs know no order.
"""

from __future__ import annotations

from typing import Optional

from .factions import CITY

START, MAX = 6, 10
TAKEN = 3
SAFE, CLEARED = 4, 6
CRIME = 0.15                  # per point of order below SAFE, per own turn
DEN_TAX = 0.3
BATTLE, RAID, OVERTAX = 2, 1, 1
HORDE_FEAR, FENCE = 2, 0.5


def applies(camp, city: str) -> bool:
    return camp.owner.get(city) != "goblin"


def target(camp, city: str) -> int:
    from .buildings import count
    t = 5
    offs = camp.officers_in(city)
    if offs:
        t += 1 + (1 if max(camp.stat(o.key, "РАЗВЕДКА") for o in offs) >= 14 else 0)
    troops = sum(camp.power(o.key) for o in offs) + sum(x.power for x in camp.free[city])
    t += (troops >= 300) + (troops >= 700)
    t += count(camp, city, "temple") + (1 if CITY[city].kind == "capital" else 0)
    t -= max(0, camp.prosperity[city] - 6)
    if city in camp.sick:
        t -= 2
    owner = camp.realms.get(camp.owner[city])
    if owner and owner.unrest:
        t -= 1
    if haunted(camp, city):
        t -= HORDE_FEAR
    return max(0, min(MAX, t))


def haunted(camp, city: str) -> bool:
    """A city of men in the horde's shadow: next to a lair of an unbought horde."""
    from .factions import neighbors
    owner = camp.owner[city]
    return owner != "goblin" and any(camp.owner[n] == "goblin" for n in neighbors(city)) \
        and not camp.at_peace("goblin", owner)


def hit(camp, city: str, d: int) -> None:
    if applies(camp, city):
        camp.law[city] = max(0, min(MAX, camp.law.get(city, START) - d))


def taken(camp, city: str) -> None:
    camp.law[city] = TAKEN
    camp.dens.discard(city)


def tax_mult(camp, city: str) -> float:
    return 1 - DEN_TAX if city in camp.dens else 1.0


def turn(camp, faction: str) -> None:
    """Start of a realm's turn: order drifts, crime strikes where it is low."""
    from .cardplay import _prosper
    for city in camp.cities_of(faction):
        if not applies(camp, city):
            continue
        o = camp.law.get(city, START)
        t = target(camp, city)
        o += (t > o) - (t < o)
        camp.law[city] = o
        if city in camp.dens and o >= CLEARED:
            camp.dens.discard(city)
            camp.log_event(faction, f"{CITY[city].name}: стража разогнала воровской притон")
        if o < SAFE and camp.rng.random() < CRIME * (SAFE - o):
            _crime(camp, faction, city, _prosper)


def _crime(camp, faction: str, city: str, prosper) -> Optional[str]:
    name = CITY[city].name
    kinds = ["riot", "smugglers"] + ([] if city in camp.dens else ["den", "den"])
    k = camp.rng.choice(kinds)
    camp.stats["crime"][k] += 1
    if k == "den":
        camp.dens.add(city)
        prosper(camp, city, -1)
        msg = f"{name}: завёлся ВОРОВСКОЙ ПРИТОН - процветание -1, подать там на 30% меньше"
    elif k == "riot":
        prosper(camp, city, -1)
        if camp.free[city]:
            camp.free[city].pop(camp.rng.randrange(len(camp.free[city])))
        msg = f"{name}: БУНТ ЧЕРНИ - процветание -1"
    else:
        loss = min(camp.gold[faction], 20 + 5 * camp.prosperity[city])
        camp.gold[faction] -= loss
        msg = f"{name}: КОНТРАБАНДИСТЫ увели {loss} золота мимо казны"
        if haunted(camp, city):
            camp.earn("goblin", loss, "fence")
            msg += " - прямиком в логово гоблинов"
    camp.log_event(faction, msg)
    return msg
