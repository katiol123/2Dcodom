"""Events of the world (pure Python, no pygame): rare upheavals that hit every realm at once.

About twice a campaign (``CHANCE`` a round, never in the first rounds, at least ``GAP`` rounds
apart) one of ``EVENTS`` happens. Most of them hurt the strong more than the weak or hand the weak
a chance (a revolt in conquered lands, a call against the strongest, free companies for the poor),
some simply shake everybody (plague, frost, drought), and the goblin horde brings the goblins back
when the realms of men have nearly wiped them out. ``python -m game.cardsim events`` measures how
much each event shifts the balance.

The screen shows a new event as a big card (``camp.world_events``); events with a duration are
listed in ``camp.active`` (key -> rounds left) and change rules in campaign.py: upkeep (frost),
growth (frost), tax income (drought).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Tuple

from .factions import CITIES, CITY, FACTION, neighbors
from .units import ROSTER

CHANCE = 0.09            # per round
FIRST_ROUND = 6
GAP = 8                   # rounds between two events at least


@dataclass
class Event:
    key: str
    name: str
    text: str
    run: Callable[["object"], Tuple[str, Optional[str]]]   # -> (what happened, realm hit hardest)
    can: Callable[["object"], bool] = lambda camp: True
    color: str = "#c9a24a"


def _humans(camp) -> List[str]:
    return [f for f in camp.alive() if f != "goblin"]


def _by_standing(camp) -> List[str]:
    from .diplomacy import standing
    return sorted(_humans(camp), key=lambda f: -standing(camp, f))


def _around(city: str, steps: int) -> Dict[str, int]:
    dist, front = {city: 0}, [city]
    for d in range(1, steps + 1):
        front = [n for c in front for n in neighbors(c) if n not in dist]
        for n in front:
            dist.setdefault(n, d)
    return dist


def _cull(camp, city: str, frac: float) -> int:
    """Remove a share of the troops in a city (garrison and the squads standing there)."""
    lost = 0
    lists = [camp.free[city]] + [camp.squads[o.key] for o in camp.officers_in(city)]
    for lst in lists:
        n = min(len(lst), int(len(lst) * frac + camp.rng.random()))
        camp.rng.shuffle(lst)
        del lst[:n]
        lost += n
    return lost


# --- the events ----------------------------------------------------------------------------------
def _plague(camp):
    from .population import plague_cards
    plague_cards(camp)                                     # two more sickness cards in every deck
    rich = sorted(camp.owner, key=lambda c: -camp.prosperity[c] + camp.rng.random() * 3)
    origin = rich[0]
    reach = _around(origin, 2)
    hit: Dict[str, int] = {}
    for city, d in reach.items():
        camp.prosperity[city] = max(1, camp.prosperity[city] - (4 if d == 0 else 3 if d == 1 else 2))
        owner = camp.owner[city]
        if owner != "ashen":                                   # the dead fear no plague
            _cull(camp, city, 0.6 if d == 0 else 0.4 if d == 1 else 0.25)
        hit[owner] = hit.get(owner, 0) + 1
    worst = max(hit, key=hit.get)
    return (f"мор вспыхнул в городе {CITY[origin].name} и прошёл по {len(reach)} городам: процветание упало, "
            f"гарнизоны поредели (нежить Пепла не болеет)", worst)


def _goblin_horde(camp):
    g = camp.realms["goblin"]
    revived = not g.alive
    g.alive = True
    lairs = [c.key for c in CITIES if c.faction == "goblin"]
    lost = sorted((c for c in lairs if camp.owner[c] != "goblin"), key=camp.defense_power)
    taken = []
    for city in lost[:3]:
        old = camp.owner[city]
        garrison = camp.officers_in(city)
        camp.free[city] = []
        camp.owner[city] = "goblin"
        for o in garrison:                                     # the garrison's officers flee
            home = camp.nearest_city(city, old)
            if home:
                camp.officer_city[o.key] = home
        camp.losses.append((camp.turn, old, "goblin", city))
        camp.siege.pop(city, None)
        taken.append(city)
        camp.check_fall(old, "goblin")
    for city in camp.cities_of("goblin"):
        camp.recruit(city, 160 if city in taken else 90)
    # goblin-born officers who serve men half-heartedly hear the drums
    back = 0
    for o, f in list(camp.allegiance.items()):
        from .officers import OFFICER
        if OFFICER[o].faction == "goblin" and f != "goblin" and camp.loyalty.get(o, 60) < 70 \
                and camp.cities_of("goblin"):
            camp.defect(o, "goblin")
            camp.officer_city[o] = camp.rng.choice(camp.cities_of("goblin"))
            back += 1
    worst = camp.losses[-1][1] if taken else None
    return ((f"гоблины {'восстали из пепла и ' if revived else ''}отбили {len(taken)} логова, "
             f"во всех логовах новые орды" + (f", к ним вернулись {back} вождей" if back else "")), worst)


def _frost(camp):
    camp.active["frost"] = 3
    return ("на 3 хода: содержание войск +30% (кроме Севера и Дургхейма), города не растут", None)


def _fair(camp):
    league = "league"
    guests = [f for f in _humans(camp) if f != league and (camp.at_peace(f, league) or
                                                            camp.relation(f, league) >= 50)]
    camp.earn(league, 350, "event")
    for f in guests:
        camp.earn(f, 150, "event")
        camp.change_relation(f, league, 8)
    names = ", ".join(FACTION[f].short for f in guests) or "никто"
    return f"Лига +350 золота; гости ярмарки (мир или отношения 50+) по +150: {names}", league


def _gold_rush(camp):
    weak = list(reversed(_by_standing(camp)))[:3]
    f = camp.rng.choice(weak)
    city = max(camp.cities_of(f), key=lambda c: camp.rng.random())
    camp.prosperity[city] = 10
    camp.earn(f, 600, "event")
    camp.recruit(city, 220)                                   # the miners take up arms
    for n in {camp.owner[x] for x in neighbors(city)} - {f, "goblin"}:
        camp.change_relation(f, n, -6)                        # the neighbours grow envious
    return (f"жила в городе {CITY[city].name}: процветание 10, казна державы {FACTION[f].short} +600, рудокопы взялись "
            f"за оружие; соседи завидуют"), f


def _revolt(camp):
    f = _by_standing(camp)[0]
    conquered = [c for c in camp.cities_of(f) if CITY[c].faction != f]
    conquered.sort(key=camp.defense_power)
    done = []
    for city in conquered[:3]:
        home = CITY[city].faction
        to = home if home in camp.realms and (camp.realms[home].alive or home != "goblin") else None
        if to is None or to == "goblin":
            continue
        for o in camp.officers_in(city):
            dest = camp.nearest_city(city, f)
            if dest and dest != city:
                camp.officer_city[o.key] = dest
        camp.free[city] = []
        revived = not camp.realms[to].alive
        camp.realms[to].alive = True
        camp.owner[city] = to
        camp.losses.append((camp.turn, f, to, city))
        camp.recruit(city, 140)
        done.append(f"{CITY[city].name} -> {FACTION[to].short}" + (" (держава возродилась)" if revived else ""))
    if not done:                                              # no foreign lands: the peasants burn and run
        for city in sorted(camp.cities_of(f), key=lambda c: camp.prosperity[c])[:3]:
            camp.prosperity[city] = max(1, camp.prosperity[city] - 2)
            _cull(camp, city, 0.3)
        return f"бунт в землях державы {FACTION[f].short}: три города разорены, гарнизоны разбежались", f
    return f"покорённые земли державы {FACTION[f].short} восстали: " + ", ".join(done), f


def _omen(camp):
    top = _by_standing(camp)[:2]
    for o, f in camp.allegiance.items():
        if f in camp.realms and f != "goblin":
            camp.change_loyalty(o, -15 if f in top else -6)
    for f in top:
        camp.add_curse(f, "unrest", 2)
    return ("комета над миром: верность офицеров падает, сильнейшие ("
            + ", ".join(FACTION[f].short for f in top) + ") ропщут: 2 СМУТЫ в колоду"), top[0]


def _prophet(camp):
    f = _by_standing(camp)[0]
    others = [x for x in _humans(camp) if x != f]
    for x in others:
        camp.change_relation(f, x, -25)
        if camp.at_peace(f, x):                               # the prophet releases them from their oaths
            camp.truce.pop(frozenset((f, x)), None)
            camp.alliance.pop(frozenset((f, x)), None)
    for i, a in enumerate(others):
        for b in others[i + 1:]:
            camp.change_relation(a, b, 10)
    return (f"пророк зовёт все державы против державы {FACTION[f].short}: клятвы им расторгнуты, отношения с ними -25, "
            f"между прочими +10"), f


def _free_companies(camp):
    order = list(reversed(_by_standing(camp)))
    got = []
    for i, f in enumerate(order):
        budget = 520 if i < 3 else 220 if i < 5 else 0
        if not budget or not camp.cities_of(f):
            continue
        city = FACTION[f].capital if camp.owner.get(FACTION[f].capital) == f else camp.cities_of(f)[0]
        pool = [k for c in CITY.values() for k in c.pool if k in ROSTER and not ROSTER[k].boss]
        camp.recruit(city, budget, sorted(set(pool)))
        got.append(f"{FACTION[f].short} {budget}")
    return "вольные роты нанимаются к тем, кто платит щедрее слабого: " + ", ".join(got), order[0]


def _drought(camp):
    camp.active["drought"] = 4
    return "на 4 хода подати приносят лишь 40% золота", None


EVENTS: List[Event] = [
    Event("plague", "ЧУМА НА МАТЕРИКЕ", "Мор идёт от богатейшего города на 2 дороги вокруг: процветание "
          "-4/-3/-2, гарнизоны теряют до 60% воинов (нежить Пепла не болеет); в каждую колоду ложатся ещё 2 "
          "БОЛЕЗНИ В ГОРОДЕ на 10 ходов.", _plague, color="#7a9e48"),
    Event("goblin_horde", "НАШЕСТВИЕ ГОБЛИНОВ", "Гоблины отбивают до 3 слабейших своих логов, во всех "
          "логовах новые орды; гоблинские вожди на службе людей могут вернуться к своим.", _goblin_horde,
          can=lambda camp: camp.turn >= 10 and len(camp.cities_of("goblin")) <= 4, color="#63c74d"),
    Event("frost", "ВЕЛИКАЯ СТУЖА", "3 хода: содержание войск +30% (Север и Дургхейм привычны к холоду), "
          "города не растут.", _frost, color="#9bd3f0"),
    Event("fair", "ЯРМАРКА В ЛИГЕ", "Лига +350 золота, каждый гость (мир с Лигой или отношения 50+) "
          "+150 золота и отношения +8.", _fair, can=lambda camp: "league" in _humans(camp), color="#feae34"),
    Event("gold_rush", "ЗОЛОТАЯ ЖИЛА", "В городе одной из трёх слабейших держав нашли золото: процветание "
          "10, +600 в казну и ополчение рудокопов; соседи завидуют (отношения -6).", _gold_rush, color="#fee761"),
    Event("revolt", "КРЕСТЬЯНСКАЯ ВОЙНА", "У сильнейшей державы 3 покорённых города возвращаются прежним "
          "хозяевам (павшие державы возрождаются). Нет покорённых - три города разорены.", _revolt,
          color="#e43b44"),
    Event("omen", "ХВОСТАТАЯ ЗВЕЗДА", "Дурное знамение: верность всех офицеров -6, у двух сильнейших "
          "держав -15 и по 2 СМУТЫ в колоду.", _omen, color="#b07ad8"),
    Event("prophet", "ВОЗЗВАНИЕ ПРОРОКА", "Все против сильнейшей державы: её договоры расторгнуты, отношения "
          "со всеми -25, между прочими +10. Рождается коалиция.", _prophet, color="#ffffff"),
    Event("free_companies", "ВОЛЬНЫЕ РОТЫ", "Наёмники идут к слабым: три слабейшие державы получают "
          "отряды на 520 мощи в столице, следующие две - на 220.", _free_companies, color="#c28a2e"),
    Event("drought", "ВЕЛИКАЯ ЗАСУХА", "4 хода подати приносят лишь 40% золота. Большие армии "
          "начнут разбегаться.", _drought, color="#d08a4a"),
]
EVENT = {e.key: e for e in EVENTS}


def fire(camp, key: str) -> str:
    e = EVENT[key]
    text, worst = e.run(camp)
    camp.world_events.append((camp.turn, key, text))
    camp.last_event = camp.turn
    camp.stats["events"][key] += 1
    line = f"СОБЫТИЕ: {e.name} - {text}"
    for f in _humans(camp) if worst is None else [worst]:
        camp.log_event(f, line)
    return line


def round_tick(camp) -> None:
    """Start of a round: running events age, and maybe a new one breaks out."""
    for k in list(camp.active):
        camp.active[k] -= 1
        if camp.active[k] <= 0:
            del camp.active[k]
    if camp.no_events or camp.turn < FIRST_ROUND or camp.turn - camp.last_event < GAP:
        return
    if camp.rng.random() >= CHANCE:
        return
    pool = [e for e in EVENTS if e.can(camp) and not any(k == e.key for _, k, _ in camp.world_events[-2:])]
    if pool:
        fire(camp, camp.rng.choice(pool).key)
