"""The goblin horde's own ways (pure Python, no pygame).

**The great building.** The goblins never build what people build. Once in a campaign, when the
horde has hoarded ``GREAT_COST`` gold, it raises ONE great building in a lair - and from then on
it plays in that manner (``manner``):

* ТОТЕМ ВОЙНЫ (боевой дух) - every goblin squad fights x``TOTEM_MULT`` (on the map and in real
  battles: goblins hit harder), so the horde storms more (its odds grow);
* ЯМА С ПЛЕННЫМИ (выкуп или жертва) - a part of the enemies who fall in a battle the goblins win,
  a captive from every goblin raid and night snatchers' catch (``SNATCH``) end up in the pit. Every goblin turn each captive is either
  ransomed (his realm pays ``RANSOM`` x his power in gold) or sacrificed (mad goblins and shamans
  of ``SACRIFICE`` x his power crawl out of the pit). The horde raids more;
* ЗАГОН ВАРГОВ (дешёвые всадники) - wolf riders are hired in every lair without a muster, at half
  price and half upkeep, and the pen breeds a free one now and then (``PEN_BREED``).

The great building stands until its lair falls (then it is burnt; the horde may raise it again,
in the same manner). The player is told at once: it is a big change on the map.

**Buying the horde off.** People pay the goblins to be left alone: ОТКУП ОТ ОРДЫ (a card of state
in every human deck) pays ``buy_off_price`` gold into the horde's treasury - and the horde neither
storms nor raids the payer's cities for ``BUY_OFF_TURNS`` of his turns (nor may he touch the
lairs). A realm the horde does not threaten keeps the silver it collected for the purpose.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import List, Optional, Tuple

from .factions import CITY, neighbors
from .units import ROSTER

GOBLIN = "goblin"
GREAT_COST = 540
SAVE_FROM = 4                 # the horde starts hoarding for the great building from this round
TOTEM_MULT = 1.3
PIT_SHARE, PIT_MAX = 0.6, 12
SNATCH = 0.4                  # per enemy city next to the pit's lairs, every goblin turn
RANSOM, SACRIFICE = 1.0, 1.3
PEN_PRICE, PEN_UPKEEP, PEN_BREED = 0.5, 0.5, 0.8
BUY_OFF_TURNS = 4
BUY_OFF_SILVER = 15           # gold per own city when there is nobody to pay


@dataclass(frozen=True)
class Great:
    key: str
    name: str
    manner: str
    text: str
    color: str


GREAT = {g.key: g for g in (
    Great("totem", "ТОТЕМ ВОЙНЫ", "БОЕВОЙ ДУХ", "Гоблины штурмуют и держат логова на 30% сильнее - и на карте, и "
          "в настоящих боях.", "#e43b44"),
    Great("pit", "ЯМА С ПЛЕННЫМИ", "ВЫКУП ИЛИ ЖЕРТВА", "Часть павших врагов в боях, выигранных гоблинами, "
          "пленник с каждого набега и улов ночных ловцов из соседних городов попадают в яму. Каждый ход пленников выкупают их державы (золото орде) "
          "или приносят в жертву (из ямы лезут безумные гоблины). Орда чаще ходит в набеги.", "#b07ad8"),
    Great("warg_pen", "ЗАГОН ВАРГОВ", "ДЕШЁВЫЕ ВСАДНИКИ", "Наездников на лютоволках нанимают в любом логове "
          "без сбора войск, за полцены и с половинным содержанием; загон сам выводит новых.", "#feae34"),
)}
ORDER = tuple(GREAT)


# --- state ------------------------------------------------------------------------------------------
def great(camp) -> Optional[Tuple[str, str]]:
    """(kind, lair) of the standing great building, or None."""
    g = camp.great.get(GOBLIN)
    if g and camp.owner.get(g[1]) == GOBLIN:
        return g
    return None


def has(camp, kind: str) -> bool:
    g = great(camp)
    return bool(g) and g[0] == kind


def great_in(camp, city: str) -> Optional[str]:
    g = great(camp)
    return g[0] if g and g[1] == city else None


def can_build(camp, kind: str, city: str) -> Tuple[bool, str]:
    if great(camp):
        return False, "ВЕЛИКАЯ ПОСТРОЙКА УЖЕ СТОИТ"
    if camp.manner.get(GOBLIN, kind) != kind:
        return False, "ОРДА УЖЕ ВЫБРАЛА СВОЙ ПУТЬ"
    if camp.owner.get(city) != GOBLIN:
        return False, "ЭТО НЕ ЛОГОВО ОРДЫ"
    if camp.gold[GOBLIN] < GREAT_COST:
        return False, "НЕ ХВАТАЕТ ЗОЛОТА"
    return True, ""


def build(camp, kind: str, city: str) -> bool:
    if not can_build(camp, kind, city)[0]:
        return False
    camp.gold[GOBLIN] -= GREAT_COST
    camp.great[GOBLIN] = (kind, city)
    again = GOBLIN in camp.manner
    camp.manner[GOBLIN] = kind
    camp.stats["great"][kind] += 1
    g = GREAT[kind]
    text = (f"Орда {'снова ' if again else ''}возвела в логове {CITY[city].name} {g.name} ({g.manner}). "
            f"{g.text}")
    camp.log_event(GOBLIN, f"ВЕЛИКАЯ ПОСТРОЙКА ОРДЫ: {g.name} в {CITY[city].name}")
    camp.world_events.append((camp.turn, f"great:{kind}", text))   # the player sees it as a big card
    return True


def on_city_lost(camp, city: str) -> None:
    """A lair falls: its great building is burnt (the pit's captives run home)."""
    g = camp.great.get(GOBLIN)
    if g and g[1] == city:
        del camp.great[GOBLIN]
        camp.pit.clear()
        camp.stats["great_lost"][g[0]] += 1
        camp.log_event(GOBLIN, f"{GREAT[g[0]].name} в {CITY[city].name} сожжён")


# --- effects ----------------------------------------------------------------------------------------
def side_mult(camp, faction: str) -> float:
    """The totem: goblin armies storm, and goblin lairs hold, x``TOTEM_MULT``."""
    return TOTEM_MULT if faction == GOBLIN and has(camp, "totem") else 1.0


def fury(camp, attacker: str, defender: str) -> Tuple[float, float]:
    """Damage multipliers of the two sides in a real battle."""
    if not has(camp, "totem"):
        return 1.0, 1.0
    return (TOTEM_MULT if attacker == GOBLIN else 1.0), (TOTEM_MULT if defender == GOBLIN else 1.0)


def pen_hire(camp, city: str, key: str) -> bool:
    """Wolf riders: in every lair, without a muster, while the pen stands."""
    return key == "wolf_rider" and camp.owner.get(city) == GOBLIN and has(camp, "warg_pen")


def hire_mult(camp, city: str, key: str) -> float:
    return PEN_PRICE if pen_hire(camp, city, key) else 1.0


def upkeep_mult(camp, faction: str, key: str) -> float:
    return PEN_UPKEEP if faction == GOBLIN and key == "wolf_rider" and has(camp, "warg_pen") else 1.0


def capture(camp, realm: str, power: int) -> None:
    if has(camp, "pit") and realm in camp.realms and realm != GOBLIN and len(camp.pit) < PIT_MAX:
        camp.pit.append((realm, int(power)))
        camp.stats["captives"][realm] += 1


def on_battle(camp, b, fallen_enemies: List[Tuple[str, int]]) -> None:
    """The goblins won a battle: some of the enemies who fell are dragged into the pit."""
    if not has(camp, "pit"):
        return
    for realm, power in fallen_enemies:
        if camp.rng.random() < PIT_SHARE:
            capture(camp, realm, power)


def on_raid(camp, f: str, city: str) -> None:
    if f == GOBLIN:
        capture(camp, camp.owner[city], 50 + 5 * camp.prosperity[city])


def turn(camp, faction: str) -> None:
    """Start of the horde's turn: the pit is emptied, the pen breeds."""
    if faction != GOBLIN:
        tick_buy_off(camp, faction)
        return
    g = great(camp)
    if not g:
        return
    kind, city = g
    if kind == "warg_pen" and camp.rng.random() < PEN_BREED:
        from .campaign_ai import _recruit_city          # the wolves run to where the riders are needed
        where = _recruit_city(camp, GOBLIN, camp.cities_of(GOBLIN))[1] or city
        camp.free[where].append(camp._new("wolf_rider"))
        camp.stats["bred"][GOBLIN] += 1
    if kind == "pit":                                  # night snatchers drag people off the border
        own = set(camp.cities_of(GOBLIN))
        for c in [c for c in camp.owner if camp.owner[c] != GOBLIN and not camp.at_peace(GOBLIN, camp.owner[c])
                  and any(n in own for n in neighbors(c))]:
            if camp.rng.random() < SNATCH:
                capture(camp, camp.owner[c], 40 + 5 * camp.prosperity[c])
    if kind == "pit" and camp.pit:
        ransom = sacrificed = 0
        for realm, power in camp.pit:
            alive = realm in camp.realms and camp.realms[realm].alive
            price = int(power * RANSOM)
            if alive and camp.gold[realm] >= price and _ransom_first(camp):
                camp.gold[realm] -= price
                camp.earn(GOBLIN, price, "ransom")
                ransom += price
                camp.log_event(realm, f"ВЫКУП: орда отпустила пленного за {price} золота")
            else:
                sacrificed += camp.recruit(city, int(power * SACRIFICE), ("mad_goblin", "goblin_shaman", "goblin"))
        camp.stats["ransom"][GOBLIN] += ransom
        camp.stats["sacrificed"][GOBLIN] += sacrificed
        camp.pit.clear()
        if ransom or sacrificed:
            camp.log_event(GOBLIN, f"ЯМА: выкуп {ransom} золота, жертвы дали воинов на {sacrificed} мощи")


def _ransom_first(camp) -> bool:
    """Gold while the horde is poor or cannot feed more warriors; blood when it can."""
    up = camp.upkeep(GOBLIN)
    return camp.gold[GOBLIN] < 2 * up + 100 or camp.expected_income(GOBLIN) < up * 1.2


# --- the computer: hoarding and choosing the manner ----------------------------------------------------
def saving(camp, faction: str) -> float:
    """Gold the horde keeps aside for its great building (hiring stops above the rest)."""
    if faction != GOBLIN or great(camp) or camp.turn < SAVE_FROM:
        return 0.0
    from . import reign
    share = 1.0 if reign.has(camp, GOBLIN, "hoarder") else 0.8
    return GREAT_COST * share


def choose(camp) -> str:
    """Which manner suits the ruling chieftain (his reign traits, with a touch of chance)."""
    if camp.manner.get(GOBLIN):
        return camp.manner[GOBLIN]
    if camp.force_great:
        return camp.force_great
    from . import reign
    t = reign.ruler_traits(camp, GOBLIN)
    r = random.Random(f"manner:{camp.seed}:{camp.leader.get(GOBLIN)}")
    score = {k: r.uniform(0, 2.0) for k in ORDER}
    for trait, kind in (("aggressive", "totem"), ("brave", "totem"), ("reckless", "totem"), ("warmonger", "totem"),
                        ("cruel", "pit"), ("greedy", "pit"), ("vulture", "pit"), ("miser", "pit"),
                        ("recruiter", "warg_pen"), ("conqueror", "warg_pen"), ("cautious", "warg_pen"),
                        ("hoarder", "warg_pen")):
        if trait in t:
            score[kind] += 0.5
    return max(score, key=score.get)


def ai_build(camp, faction: str) -> None:
    if faction != GOBLIN or great(camp) or camp.gold[GOBLIN] < GREAT_COST or camp.realms[GOBLIN].ap < 1:
        return
    lairs = camp.cities_of(GOBLIN)
    if not lairs:
        return
    from .campaign_ai import threat

    def safety(c):                  # deep in the horde's lands, away from the strongest armies
        return threat(camp, GOBLIN, c) / max(1.0, camp.defense_power(c)) - 0.2 * sum(
            1 for n in neighbors(c) if camp.owner[n] == GOBLIN)
    city = min(lairs, key=safety)
    if build(camp, choose(camp), city):
        camp.realms[GOBLIN].ap -= 1


def odds_bonus(camp, faction: str) -> float:
    """The totem makes the horde bolder - by its strength alone: the odds already count it (a bolder
    horde that also lowered its bar only bled itself white in the measurements)."""
    return 0.0


def raid_mult(camp, faction: str) -> float:
    return 1.6 if faction == GOBLIN and has(camp, "pit") else 1.0


# --- buying the horde off -----------------------------------------------------------------------------
def border(camp, faction: str) -> List[str]:
    """Own cities next to a goblin lair."""
    return [c for c in camp.cities_of(faction) if any(camp.owner[n] == GOBLIN for n in neighbors(c))]


def threatened(camp, faction: str) -> bool:
    return faction != GOBLIN and GOBLIN in camp.realms and camp.realms[GOBLIN].alive and bool(border(camp, faction))


def buy_off_price(camp, faction: str) -> int:
    return 60 + 30 * len(border(camp, faction))


def bought(camp, a: str, b: str) -> bool:
    """The horde has been paid off by the other side of the pair."""
    if GOBLIN not in (a, b):
        return False
    other = b if a == GOBLIN else a
    return camp.paid.get(other, 0) > 0


def tick_buy_off(camp, faction: str) -> None:
    if camp.paid.get(faction, 0) > 0:
        camp.paid[faction] -= 1
        if camp.paid[faction] <= 0:
            del camp.paid[faction]
            camp.log_event(faction, "Откуп кончился: орда снова смотрит на ваши города")


def can_buy_off(camp, faction: str) -> Tuple[bool, str]:
    if threatened(camp, faction) and camp.gold[faction] < buy_off_price(camp, faction):
        return False, f"НУЖНО {buy_off_price(camp, faction)} ЗОЛОТА"
    return True, ""


def buy_off(camp, faction: str, turns: int = BUY_OFF_TURNS, free: bool = False) -> str:
    if not threatened(camp, faction):
        if free:
            return "орды рядом нет"
        g = camp.earn(faction, BUY_OFF_SILVER * len(camp.cities_of(faction)), "tax")
        return f"орды рядом нет - собранное серебро осталось в казне: +{g} золота"
    price = 0 if free else buy_off_price(camp, faction)
    camp.gold[faction] -= price
    if price:
        camp.earn(GOBLIN, price, "tribute")
        camp.stats["bought_off"][faction] += 1
    camp.paid[faction] = max(camp.paid.get(faction, 0), turns)
    return f"мир с ордой на {turns} х." + (f" (заплачено {price} золота)" if price else "")
