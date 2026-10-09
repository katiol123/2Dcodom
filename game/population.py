"""Sickness, deaths and newcomers: the world's people change (pure Python, no pygame).

**Sickness.** Every realm's deck holds one БОЛЕЗНЬ В ГОРОДЕ (``SICKNESS``). When it is drawn it is
not kept: it goes back to the discard pile, a card is drawn in its place, and sickness breaks out
in a random own city for ``SICK_TURNS`` own turns - unless the infirmaries nearby stop it
(buildings.py). While a city is sick, every officer standing there may die at the start of each
own turn (``SICK_DEATH``, one death a turn at most; a ruler too - and then a successor takes the throne). The world event
ЧУМА НА МАТЕРИКЕ shuffles two more sickness cards into every deck for a while.

**Newcomers.** So that the world does not empty, young talents come of age: the council card
ПОИСК ТАЛАНТОВ (first ВЕРБОВКА threshold) brings one into a chosen city, and a realm with fewer
officers than it started with finds one by itself now and then (``INFLUX``; an academy helps).
Their names come from a prepared pool (``officers.newcomer``); they start weak but learn fast.
"""

from __future__ import annotations

from typing import Optional

from .factions import CITY
from .officers import OFFICER, OFFICERS, newcomer

SICKNESS = "sickness"
SICK_TURNS = 3
SICK_DEATH = 0.04              # per officer standing in a sick city, at the start of each own turn
INFLUX = 0.12                  # per own turn, when the realm has fewer officers than at the start
MAX_OFFICERS = 24
PLAGUE_CARDS, PLAGUE_LEFT = 2, 10


def _g(o: str, male: str, female: str) -> str:
    return female if OFFICER[o].female else male


# --- sickness --------------------------------------------------------------------------------------
def outbreak(camp, faction: str, city: Optional[str] = None) -> str:
    """Sickness breaks out in a city of the realm (a random one by default)."""
    from .buildings import sickness_block
    cities = camp.cities_of(faction)
    if not cities:
        return ""
    from .factions import city_feat
    if city is None:                                     # crowded cities fall sick more often
        city = camp.rng.choices(cities, [1 + 2 * len(camp.officers_in(c)) for c in cities])[0]
    if city_feat(city) == "grove":                       # СВЯЩЕННАЯ РОЩА: the sickness finds no hold
        camp.stats["outbreaks_stopped"][faction] += 1
        msg = f"БОЛЕЗНЬ обошла священную рощу: {CITY[city].name}"
        camp.log_event(faction, msg)
        return msg
    camp.stats["outbreaks"][faction] += 1
    block = 1.0 if city in camp.immune else sickness_block(camp, city)
    if block and camp.rng.random() < block:
        camp.stats["outbreaks_stopped"][faction] += 1
        msg = f"БОЛЕЗНЬ в городе {CITY[city].name} остановлена лазаретом"
    else:
        camp.sick[city] = SICK_TURNS
        msg = f"БОЛЕЗНЬ В ГОРОДЕ {CITY[city].name}: офицеры там в опасности {SICK_TURNS} х."
    camp.log_event(faction, msg)
    return msg


def on_draw_sickness(camp, faction: str, inst) -> None:
    r = camp.realms[faction]
    outbreak(camp, faction)
    if inst.left == 0 or inst.left > 1:                  # back to the discard (plague copies fade)
        r.discard.append(inst)
    camp._draw(faction, 1)                               # a card in its place


def plague_cards(camp) -> None:
    """The world plague: two more sickness cards in every deck, for a while."""
    for f, r in camp.realms.items():
        if r.alive:
            for _ in range(PLAGUE_CARDS):
                inst = camp._inst(SICKNESS, "plague")
                inst.left = PLAGUE_LEFT
                r.draw.insert(camp.rng.randrange(len(r.draw) + 1), inst)


def turn(camp, faction: str) -> None:
    """Start of a realm's own turn: the sick may die, sickness fades, talents come of age."""
    from .succession import die
    for city in [c for c in list(camp.sick) if camp.owner[c] == faction]:
        for o in [x.key for x in camp.officers_in(city)]:
            if camp.rng.random() < SICK_DEATH * _temple_care(camp, city):
                camp.stats["sick_deaths"][faction] += 1
                die(camp, o, _g(o, "умер", "умерла") + f" от болезни в городе {CITY[city].name}")
                break                                     # one death a turn at most: a sickness, not a massacre
        camp.sick[city] -= 1
        if camp.sick[city] <= 0:
            del camp.sick[city]
    start = len(OFFICERS.get(faction, ()))
    officers = len(camp.officers_of(faction))
    if faction in camp.realms and camp.realms[faction].alive and officers < start:
        from .buildings import count
        academies = sum(count(camp, c, "academy") for c in camp.cities_of(faction))
        short = start - officers                          # the emptier the court, the faster it fills
        if camp.rng.random() < INFLUX * (1 + academies) * (1 + short / 4):
            come_of_age(camp, faction)


def _temple_care(camp, city: str) -> float:
    from .buildings import count
    return 0.5 if count(camp, city, "temple") else 1.0


# --- newcomers -------------------------------------------------------------------------------------
def come_of_age(camp, faction: str, city: Optional[str] = None) -> Optional[str]:
    """A young talent joins the realm (in ``city``, or where an academy stands, or anywhere)."""
    cities = camp.cities_of(faction)
    if not cities or len(camp.officers_of(faction)) >= MAX_OFFICERS:
        return None
    if city is None:
        from .buildings import count
        schools = [c for c in cities if count(camp, c, "academy")]
        city = camp.rng.choice(schools or cities)
    n = camp.newcomers.get(faction, 0)
    camp.newcomers[faction] = n + 1
    o = newcomer(faction, n)
    camp.enlist(o, city)
    camp.stats["newcomers"][faction] += 1
    camp.log_event(faction, f"НОВЫЙ ОФИЦЕР: {o.name} ({o.title}) {_g(o.key, 'прибыл', 'прибыла')} в "
                            f"{CITY[city].name}")
    return o.key
