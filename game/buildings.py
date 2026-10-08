"""City buildings (pure Python, no pygame).

A city has building slots (``slots``: capital 3, lair 1, others 2), at most one building of each
kind. Building costs gold and one action point (``build``); a master builder's card builds for
half price. Buildings can be lost: a raid on the city may burn one, a storm that fails may still
wreck one, and when the city is taken each building may be destroyed (``RUIN_*``).

The buildings and where they act:

* ЛАЗАРЕТ   - stops a sickness outbreak (population.py) in its city and the realm's neighbouring
  cities with 50% chance; several stack (75%, 87%...);
* РЫНОК     - ПОДАТЬ played on this city brings +50% (cardplay.py);
* БАШНЯ     - in a real battle for the city a tower shoots at the stormers like a strong archer
  (sim.py); in a worked-out battle it adds to the defence;
* КАЗАРМЫ   - hiring here is 20% cheaper and a muster lasts a turn longer;
* СТЕНЫ     - defence of the city x1.25;
* ХРАМ      - officers standing here gain loyalty every turn and catch sickness half as often;
* АКАДЕМИЯ  - officers standing here learn twice as fast in garrison; young talents prefer to
  come of age here and come more often.

РИСТАЛИЩЕ is built only by its card (rare, cards.py): the realm's cavalry (``MOUNT_OF``) is hired
there on any turn, without a muster, 15% cheaper; the city's defence x1.1.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple

from .factions import CITY, neighbors


@dataclass(frozen=True)
class Building:
    key: str
    name: str
    cost: int
    text: str


BUILDINGS = {b.key: b for b in (
    Building("infirmary", "ЛАЗАРЕТ", 150, "Останавливает болезнь в этом и соседних своих городах с шансом 50% "
                                          "(два лазарета рядом - 75%, три - 87%)."),
    Building("market", "РЫНОК", 200, "ПОДАТЬ, собранная в этом городе, приносит на 50% больше."),
    Building("tower", "БАШНЯ", 220, "В бою за город стреляет по штурмующим как усиленный лучник; в расчётном бою "
                                    "+110 к обороне."),
    Building("barracks", "КАЗАРМЫ", 180, "Найм здесь на 20% дешевле, СБОР ВОЙСК длится на ход дольше."),
    Building("walls", "СТЕНЫ", 260, "Оборона города x1.25."),
    Building("temple", "ХРАМ", 160, "Верность офицеров в городе +1 каждый ход, болезнь здесь вдвое менее смертельна."),
    Building("academy", "АКАДЕМИЯ", 200, "Офицеры в городе учатся в гарнизоне вдвое быстрее; молодые таланты "
                                         "появляются здесь и вдвое чаще."),
)}
BUILDINGS["tiltyard"] = Building("tiltyard", "РИСТАЛИЩЕ", 140, "Конница державы нанимается здесь в любой ход, "
                                  "без СБОРА ВОЙСК, на 15% дешевле; оборона города x1.1.")
ORDER = tuple(k for k in BUILDINGS if k != "tiltyard")   # what СТРОЙКА and the master builder can put up
MOUNT_OF = {"aldern": "lancer", "league": "uhlan", "khanate": "horse_archer", "sultanate": "mamluk"}
TILTYARD_PRICE, TILTYARD_DEFENSE = 0.85, 1.1
TOWER_DEFENSE = 110
RUIN_RAID, RUIN_FAILED_STORM, RUIN_CAPTURE = 0.5, 0.2, 0.4


def slots(city: str) -> int:
    kind = CITY[city].kind
    return 3 if kind == "capital" else 1 if kind == "lair" else 2


def count(camp, city: str, key: str) -> int:
    return 1 if key in camp.buildings.get(city, ()) else 0


MASONS = {"highland": 0.7}       # МАСТЕРА КАМНЯ: the highlanders build for less


def price_for(faction: str, cost: int) -> int:
    """What a building (or half of it, for a card) costs this faction."""
    return int(round(cost * MASONS.get(faction, 1.0)))


def can_build(camp, faction: str, city: str, key: str, price: int = None) -> Tuple[bool, str]:
    if camp.owner.get(city) != faction:
        return False, "ЭТО НЕ ВАШ ГОРОД"
    have = camp.buildings.get(city, [])
    if key in have:
        return False, "УЖЕ ПОСТРОЕНО"
    if len(have) >= slots(city):
        return False, "НЕТ МЕСТА ДЛЯ СТРОЙКИ"
    price = price_for(faction, BUILDINGS[key].cost if price is None else price)
    if camp.gold[faction] < price:
        return False, "НЕ ХВАТАЕТ ЗОЛОТА"
    return True, ""


def build(camp, faction: str, city: str, key: str, price: int = None, ap: int = 1) -> Tuple[bool, str]:
    base = BUILDINGS[key].cost if price is None else price
    price = price_for(faction, base)
    ok, why = can_build(camp, faction, city, key, base)
    if not ok:
        return False, why
    r = camp.realms[faction]
    if r.ap < ap:
        return False, "НЕТ ОЧКОВ ДЕЙСТВИЙ"
    r.ap -= ap
    camp.gold[faction] -= price
    camp.buildings.setdefault(city, []).append(key)
    camp.stats["built"][key] += 1
    msg = f"{CITY[city].name}: построено - {BUILDINGS[key].name}"
    camp.log_event(faction, msg)
    return True, msg


def ruin(camp, city: str, chance: float, why: str, all_of_them: bool = False) -> List[str]:
    """Each building (or one at random) may be destroyed."""
    have = camp.buildings.get(city, [])
    if not have:
        return []
    picks = list(have) if all_of_them else [camp.rng.choice(have)]
    lost = [k for k in picks if camp.rng.random() < chance]
    for k in lost:
        have.remove(k)
        camp.stats["ruined"][k] += 1
    if lost:
        camp.log_event(camp.owner[city], f"{CITY[city].name}: {why} - разрушено: "
                                         + ", ".join(BUILDINGS[k].name for k in lost))
    return lost


def sickness_block(camp, city: str) -> float:
    """Chance that the realm's infirmaries in and around the city stop an outbreak."""
    f = camp.owner[city]
    n = count(camp, city, "infirmary") + sum(count(camp, c, "infirmary") for c in neighbors(city)
                                              if camp.owner[c] == f)
    return 1 - 0.5 ** n if n else 0.0


def defense_mult(camp, city: str) -> float:
    return (1.25 if count(camp, city, "walls") else 1.0) * (TILTYARD_DEFENSE if count(camp, city, "tiltyard") else 1.0)


def tiltyard_mount(camp, city: str):
    """The cavalry a tiltyard in the city offers its owner (None: no tiltyard, or a realm without horse)."""
    return MOUNT_OF.get(camp.owner.get(city)) if count(camp, city, "tiltyard") else None


def defense_bonus(camp, city: str) -> float:
    return TOWER_DEFENSE if count(camp, city, "tower") else 0.0


def hire_price(camp, city: str, cost: int, key: str = "") -> int:
    if key and key == tiltyard_mount(camp, city):
        cost = cost * TILTYARD_PRICE
    return int(round(cost * 0.8)) if count(camp, city, "barracks") else int(round(cost))


# --- the computer builds ---------------------------------------------------------------------------
def ai_build(camp, faction: str, reserve: float) -> None:
    """With spare gold and an action point left, the computer puts up the most useful building."""
    r = camp.realms[faction]
    if r.ap < 1 or faction == "goblin":
        return
    from . import reign
    margin = 60 if reign.has(camp, faction, "builder") else 160
    best = None
    for city in camp.cities_of(faction):
        have = camp.buildings.get(city, [])
        if len(have) >= slots(city):
            continue
        front = any(camp.owner[n] not in (faction,) and not camp.at_peace(faction, camp.owner[n])
                    for n in neighbors(city))
        for key in ORDER:
            b = BUILDINGS[key]
            cost = price_for(faction, b.cost)
            if key in have or camp.gold[faction] < cost + reserve + margin:
                continue
            v = _ai_value(camp, faction, city, key, front)
            if v > 0 and (best is None or v / cost > best[0]):
                best = (v / cost, city, key)
    if best and best[0] > 0.9:
        build(camp, faction, best[1], best[2])


def _ai_value(camp, faction: str, city: str, key: str, front: bool) -> float:
    pros = camp.prosperity[city]
    officers = len(camp.officers_in(city))
    if key == "market":
        return pros * 25 + (60 if CITY[city].kind == "capital" else 0)
    if key == "walls":
        return 300 if front else 40
    if key == "tower":
        return 260 if front else 30
    if key == "barracks":
        return 230 if front else 90
    if key == "infirmary":
        sick = sum(1 for c in camp.sick if camp.owner[c] == faction)
        return 120 + 80 * sick + 20 * officers
    if key == "temple":
        return 40 * officers
    if key == "academy":
        return 50 * officers + (120 if CITY[city].kind == "capital" else 0)
    return 0
