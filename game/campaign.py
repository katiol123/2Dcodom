"""Campaign state and the rules of hiring and forming squads (pure Python, no pygame).

* every faction has a treasury (``gold``);
* units are **troops**: hired in a city (from that city's recruit pool) they stand
  there unassigned until an officer in the same city takes them into his squad;
* an officer's squad holds up to 7 troops whose total power (sum of hire prices)
  must not exceed the officer's leadership.

Turns, movement, income and battles over cities come later; they will build on
this state.
"""

from __future__ import annotations

import itertools
import random
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from .factions import CITIES, CITY, FACTION, City
from .officers import OFFICER, OFFICERS, SQUAD_SLOTS, Officer
from .units import ROSTER

START_GOLD = {"league": 900, "sultanate": 800, "goblin": 300}
DEFAULT_GOLD = 600


@dataclass
class Troop:
    id: int
    key: str

    @property
    def power(self) -> int:
        return ROSTER[self.key].cost


class Campaign:
    def __init__(self, player: Optional[str] = None, seed: int = 1):
        """``player`` is the faction the human plays, or None for a spectator."""
        self.player = player
        self.rng = random.Random(seed)
        self._ids = itertools.count(1)
        self.owner: Dict[str, str] = {c.key: c.faction for c in CITIES}
        self.gold: Dict[str, int] = {f: START_GOLD.get(f, DEFAULT_GOLD) for f in OFFICERS}
        self.officer_city: Dict[str, str] = {}
        self.allegiance: Dict[str, str] = {o.key: o.faction for o in OFFICER.values()}   # officers may defect
        self.squads: Dict[str, List[Troop]] = {o: [] for o in OFFICER}
        self.free: Dict[str, List[Troop]] = {c.key: [] for c in CITIES}
        self._deploy()

    # --- setup ------------------------------------------------------------------------------
    def _deploy(self) -> None:
        """Officers spread over their realm (every city gets at least one), each with a starting
        squad of about half his leadership, plus a few unassigned recruits in every city."""
        for faction, officers in OFFICERS.items():
            cities = [c for c in CITIES if c.faction == faction]
            cap = FACTION[faction].capital
            cities.sort(key=lambda c: c.key != cap)
            order = [cities[0].key] + [c.key for c in cities[1:]] + [cities[0].key]
            for i, off in enumerate(officers):
                city = order[i] if i < len(order) else self.rng.choice([c.key for c in cities])
                self.officer_city[off.key] = city
                self._starting_squad(off, CITY[city])
            for c in cities:
                cheap = sorted(c.pool, key=lambda k: ROSTER[k].cost)[:2]
                for _ in range(2 if c.key == cap else 1):
                    self.free[c.key].append(self._new(self.rng.choice(cheap)))

    def _starting_squad(self, off: Officer, city: City) -> None:
        target = off.leadership * self.rng.uniform(0.4, 0.6)
        squad = self.squads[off.key]
        for _ in range(4):
            room = off.leadership - self.power(off.key)
            cands = [k for k in city.pool if ROSTER[k].cost <= room and not ROSTER[k].boss]
            if not cands or self.power(off.key) >= target:
                break
            squad.append(self._new(self.rng.choice(cands)))

    def _new(self, key: str) -> Troop:
        return Troop(next(self._ids), key)

    # --- queries ----------------------------------------------------------------------------
    def officers_in(self, city: str) -> List[Officer]:
        return sorted((OFFICER[k] for k, c in self.officer_city.items()
                       if c == city and self.allegiance[k] == self.owner[city]),
                      key=lambda o: (o.rank, -o.leadership))

    def power(self, officer: str) -> int:
        return sum(t.power for t in self.squads[officer])

    def upkeep(self, faction: str) -> int:
        """Gold per turn for every troop of the faction (in squads and unassigned)."""
        total = sum(ROSTER[t.key].upkeep for o, sq in self.squads.items() if self.allegiance[o] == faction
                    for t in sq)
        total += sum(ROSTER[t.key].upkeep for c, lst in self.free.items() if self.owner[c] == faction for t in lst)
        return total

    def officers_of(self, faction: str) -> List[Officer]:
        """Everyone serving the faction now (defectors included), leader first."""
        return sorted((OFFICER[k] for k, f in self.allegiance.items() if f == faction),
                      key=lambda o: (o.faction != faction, o.rank, -o.leadership))

    def defect(self, officer: str, faction: str) -> None:
        """The officer changes sides together with his squad (treason, bribery, capture...)."""
        self.allegiance[officer] = faction

    def controls(self, city: str) -> bool:
        """The human player may manage this city."""
        return self.player is not None and self.owner[city] == self.player

    # --- hiring ----------------------------------------------------------------------------
    def can_hire(self, city: str, key: str) -> Tuple[bool, str]:
        faction = self.owner[city]
        if key not in CITY[city].pool:
            return False, "ЭТИХ ВОИНОВ ЗДЕСЬ НЕ НАНЯТЬ"
        if ROSTER[key].cost > self.gold[faction]:
            return False, "НЕ ХВАТАЕТ ЗОЛОТА"
        return True, ""

    def hire(self, city: str, key: str) -> Optional[Troop]:
        ok, _ = self.can_hire(city, key)
        if not ok:
            return None
        self.gold[self.owner[city]] -= ROSTER[key].cost
        t = self._new(key)
        self.free[city].append(t)          # the recruits stand in the city from the moment they are hired
        return t

    # --- squads ----------------------------------------------------------------------------
    def can_assign(self, officer: str, troop_id: int) -> Tuple[bool, str]:
        city = self.officer_city[officer]
        troop = next((t for t in self.free[city] if t.id == troop_id), None)
        if troop is None:
            return False, "ОТРЯД НЕ В ЭТОМ ГОРОДЕ"
        if len(self.squads[officer]) >= SQUAD_SLOTS:
            return False, "ВСЕ 7 МЕСТ ЗАНЯТЫ"
        if self.power(officer) + troop.power > OFFICER[officer].leadership:
            return False, "НЕ ХВАТАЕТ ЛИДЕРСТВА"
        return True, ""

    def assign(self, officer: str, troop_id: int) -> bool:
        ok, _ = self.can_assign(officer, troop_id)
        if not ok:
            return False
        city = self.officer_city[officer]
        troop = next(t for t in self.free[city] if t.id == troop_id)
        self.free[city].remove(troop)
        self.squads[officer].append(troop)
        return True

    def unassign(self, officer: str, troop_id: int) -> bool:
        troop = next((t for t in self.squads[officer] if t.id == troop_id), None)
        if troop is None:
            return False
        self.squads[officer].remove(troop)
        self.free[self.officer_city[officer]].append(troop)
        return True
