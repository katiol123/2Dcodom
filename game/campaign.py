"""Campaign state and its turn engine (pure Python, no pygame).

* every realm has a treasury (``gold``) and a council (the leader + 4 advisers);
* units are **troops**: hired in a city they stand there unassigned until an officer in the
  same city takes them into his squad (max 7, total power within his leadership);
* every city has a **prosperity** (1..10): what an economy card played there brings in;
* a turn: the realm gets 5 action points (ОД) and plays cards from its hand; at the end it pays
  its troops, discards the hand (a competent council keeps some cards) and draws a new one.
  Hands are drawn at the *end* of a turn, so rivals can spy on them and spoil them in between.

Cards are in ``cards.py`` (data) and ``cardplay.py`` (effects); the computer players in
``campaign_ai.py``. Battles over cities are resolved here (``attack``) from squad power.
"""

from __future__ import annotations

import itertools
import random
from collections import Counter
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from .cards import (AP, AP_BONUS, BASE_SET, CARDS, COUNCIL_SEATS, FACTION_CARD, PERSONAL, hand_size, reserve,
                    strife, threshold_cards)
from .factions import ALL_FACTIONS, CITIES, CITY, FACTION, PROSPERITY, City, neighbors, relation
from .officers import OFFICER, OFFICERS, SQUAD_SLOTS, Officer
from .units import ROSTER

START_GOLD = {"league": 700, "sultanate": 650, "goblin": 250}
DEFAULT_GOLD = 450
START_SQUAD = (0.25, 0.4)       # starting squads: this share of the officer's leadership
TAX = 20                        # gold per point of prosperity for a tax card
GUARD = {"capital": 260, "castle": 220, "fort": 170, "town": 110, "port": 120, "lair": 140}
WALLS = {"capital": 1.25, "castle": 1.3, "fort": 1.2, "town": 1.0, "port": 1.05, "lair": 1.1}
BATTLE_K = 2.5                  # how decisive a power advantage is
MAX_PROSPERITY = 10
PROSPERITY_ROOM = 3             # a city can grow this far above its starting prosperity
GROWTH_TURNS = 4                # an untaxed city grows +1 prosperity after this many turns


@dataclass
class Troop:
    id: int
    key: str

    @property
    def power(self) -> int:
        return ROSTER[self.key].cost


@dataclass
class CardInst:
    id: int
    key: str
    origin: str = "base"        # base | faction | threshold | curse | officer key (personal card)
    left: int = 0               # curses: turns until they vanish (0 = stays)

    @property
    def card(self):
        return CARDS[self.key]


@dataclass
class Realm:
    key: str
    council: List[str]
    draw: List[CardInst] = field(default_factory=list)
    hand: List[CardInst] = field(default_factory=list)
    discard: List[CardInst] = field(default_factory=list)
    ap: int = 0
    ap_penalty: int = 0         # taken off the next turn's action points
    keep: List[int] = field(default_factory=list)       # card ids the player marked to keep
    alive: bool = True
    revealed: Dict[str, int] = field(default_factory=dict)   # rival -> turn their hand was seen

    def all_cards(self) -> List[CardInst]:
        return self.draw + self.hand + self.discard


def _pair(a: str, b: str) -> frozenset:
    return frozenset((a, b))


class Campaign:
    def __init__(self, player: Optional[str] = None, seed: int = 1):
        """``player`` is the faction the human plays, or None for a spectator."""
        self.player = player
        self.seed = seed
        self.rng = random.Random(seed)
        self._ids = itertools.count(1)
        self._cids = itertools.count(1)
        self.owner: Dict[str, str] = {c.key: c.faction for c in CITIES}
        self.gold: Dict[str, int] = {f: START_GOLD.get(f, DEFAULT_GOLD) for f in OFFICERS}
        self.officer_city: Dict[str, str] = {}
        self.allegiance: Dict[str, str] = {o.key: o.faction for o in OFFICER.values()}   # officers may defect
        self.squads: Dict[str, List[Troop]] = {o: [] for o in OFFICER}
        self.free: Dict[str, List[Troop]] = {c.key: [] for c in CITIES}
        self.prosperity: Dict[str, int] = dict(PROSPERITY)
        self.taxed: Dict[str, int] = {}                       # city -> turn it was last taxed
        self.untaxed: Dict[str, int] = {c.key: 0 for c in CITIES}
        self.loyalty: Dict[str, int] = {}
        self.rel: Dict[frozenset, int] = {}
        self.truce: Dict[frozenset, int] = {}                 # pair -> turns left
        self.trade: Dict[frozenset, Tuple[int, int]] = {}     # pair -> (turns left, gold each)
        self.buffs: Dict[str, List[List[float]]] = {}         # officer -> [[mult, turns]]
        self.frozen: Dict[str, int] = {}                      # faction -> its next turns frozen
        self.defense: Dict[str, List[float]] = {}             # city -> [mult, turns]
        self.siege: Dict[str, List] = {}                      # city -> [by faction, turns]
        self.grudge: Dict[Tuple[str, str], int] = {}          # (faction, rival) -> turns
        self.ready: set = set()                               # officers who may still move/attack
        self.log: List[Tuple[int, str, str]] = []
        self.stats: Dict[str, Counter] = {"played": Counter(), "drawn": Counter(), "gold": Counter(),
                                          "captured": Counter(), "battles": Counter(), "earned": Counter(),
                                          "paid": Counter()}
        self.earned: Dict[str, int] = {}                      # gold earned this turn
        self.income: Dict[str, List[int]] = {}                # gold earned in the last turns
        self.turn = 1
        self.order: List[str] = [f.key for f in ALL_FACTIONS]
        if player in self.order:                              # the player moves first
            self.order.remove(player)
            self.order.insert(0, player)
        self.current = 0
        self._deploy()
        self.realms: Dict[str, Realm] = {}
        for f in ALL_FACTIONS:
            offs = OFFICERS[f.key]
            self.realms[f.key] = Realm(f.key, [offs[0].key])
            from .campaign_ai import choose_council
            self.realms[f.key].council = choose_council(self, f.key)
            for o in self.realms[f.key].council:
                self.loyalty[o] = min(100, self.loyalty[o] + 10)
            self._build_deck(f.key)
            self._draw(f.key, hand_size(self.realms[f.key].council))
        for a, b in itertools.combinations([f.key for f in ALL_FACTIONS], 2):
            self.rel[_pair(a, b)] = relation(a, b)[0]
        self._start_turn(self.order[0])

    # --- setup ------------------------------------------------------------------------------
    def _deploy(self) -> None:
        """Officers spread over their realm (every city gets at least one), each with a modest
        starting squad, plus a few unassigned recruits in every city."""
        for faction, officers in OFFICERS.items():
            cities = [c for c in CITIES if c.faction == faction]
            cap = FACTION[faction].capital
            cities.sort(key=lambda c: c.key != cap)
            order = [cities[0].key] + [c.key for c in cities[1:]] + [cities[0].key]
            for i, off in enumerate(officers):
                city = order[i] if i < len(order) else self.rng.choice([c.key for c in cities])
                self.officer_city[off.key] = city
                self._starting_squad(off, CITY[city])
                self.loyalty[off.key] = 100 if off.rank == 0 else self.rng.randint(45, 85) + (3 - off.rank) * 4
            for c in cities:
                cheap = sorted(self._pool(c.key), key=lambda k: ROSTER[k].cost)[:2]
                for _ in range(2 if c.key == cap else 1):
                    self.free[c.key].append(self._new(self.rng.choice(cheap)))

    def _pool(self, city: str) -> List[str]:
        return [k for k in CITY[city].pool if k in ROSTER]

    def _starting_squad(self, off: Officer, city: City) -> None:
        target = off.leadership * self.rng.uniform(*START_SQUAD)
        squad = self.squads[off.key]
        for _ in range(4):
            room = off.leadership - self.power(off.key)
            cands = [k for k in self._pool(city.key) if ROSTER[k].cost <= room and not ROSTER[k].boss]
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

    def troop_upkeep(self, faction: str, key: str) -> float:
        u = ROSTER[key].upkeep
        if faction == "ashen" and ROSTER[key].undead:
            return u * 0.4                                # the dead ask for little pay, only for bones
        return u

    def upkeep(self, faction: str) -> int:
        """Gold per turn for every troop of the faction (in squads and unassigned)."""
        total = sum(self.troop_upkeep(faction, t.key) for o, sq in self.squads.items()
                    if self.allegiance[o] == faction for t in sq)
        total += sum(self.troop_upkeep(faction, t.key) for c, lst in self.free.items()
                     if self.owner[c] == faction for t in lst)
        return int(total)

    def officers_of(self, faction: str) -> List[Officer]:
        """Everyone serving the faction now (defectors included), leader first."""
        return sorted((OFFICER[k] for k, f in self.allegiance.items() if f == faction),
                      key=lambda o: (o.faction != faction, o.rank, -o.leadership))

    def cities_of(self, faction: str) -> List[str]:
        return [c for c, f in self.owner.items() if f == faction]

    def controls(self, city: str) -> bool:
        """The human player may manage this city."""
        return self.player is not None and self.owner[city] == self.player

    def alive(self) -> List[str]:
        return [f for f in self.order if self.realms[f].alive]

    def whose_turn(self) -> str:
        return self.order[self.current]

    def relation(self, a: str, b: str) -> int:
        if a == b:
            return 100
        if "goblin" in (a, b):
            return 0
        return self.rel[_pair(a, b)]

    def change_relation(self, a: str, b: str, d: int) -> None:
        if a != b and "goblin" not in (a, b):
            k = _pair(a, b)
            self.rel[k] = max(1, min(100, self.rel[k] + d))

    def at_peace(self, a: str, b: str) -> bool:
        return self.truce.get(_pair(a, b), 0) > 0

    def max_prosperity(self, city: str) -> int:
        return min(MAX_PROSPERITY, PROSPERITY[city] + PROSPERITY_ROOM)

    def income_of(self, city: str, faction: str) -> int:
        """What a tax card brings in this city now."""
        best = max((o.stat("УПРАВЛЕНИЕ") for o in self.officers_in(city) if self.allegiance[o.key] == faction),
                   default=0)
        return self.prosperity[city] * TAX + 2 * best

    def army(self, faction: str) -> int:
        return sum(self.power(o.key) for o in self.officers_of(faction)) + \
            sum(t.power for c in self.cities_of(faction) for t in self.free[c])

    def earn(self, faction: str, n: int, why: str = "cards") -> int:
        self.gold[faction] += n
        self.earned[faction] = self.earned.get(faction, 0) + n
        self.stats["gold"][why] += n
        self.stats["earned"][faction] += n
        return n

    def expected_income(self, faction: str) -> float:
        """Average gold earned per turn lately (what the realm can afford to pay its troops)."""
        h = self.income.get(faction)
        return sum(h) / len(h) if h else 250.0

    def log_event(self, faction: str, text: str) -> None:
        self.log.append((self.turn, faction, text))

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

    def recruit(self, city: str, budget: int, pool: Optional[Sequence[str]] = None) -> int:
        """Free troops worth about ``budget`` power from the city's pool (cheap ones first)."""
        keys = [k for k in (pool or self._pool(city)) if k in ROSTER and not ROSTER[k].boss]
        if not keys:
            return 0
        got = 0
        while True:
            cands = [k for k in keys if ROSTER[k].cost <= budget - got]
            if not cands:
                if got == 0:                     # a budget below the cheapest unit still buys one
                    cands = [min(keys, key=lambda k: ROSTER[k].cost)]
                else:
                    break
            k = self.rng.choice(cands)
            self.free[city].append(self._new(k))
            got += ROSTER[k].cost
            if got >= budget:
                break
        return got

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

    # --- officers: loyalty, defection, moves ------------------------------------------------
    def change_loyalty(self, officer: str, d: int) -> None:
        if OFFICER[officer].rank == 0 and self.allegiance[officer] == OFFICER[officer].faction:
            return                                       # a leader never wavers
        self.loyalty[officer] = max(0, min(100, self.loyalty[officer] + d))

    def nearest_city(self, start: str, faction: str) -> Optional[str]:
        """Closest city of the faction by roads (any owner on the way)."""
        seen, front = {start}, [start]
        while front:
            for c in front:
                if self.owner[c] == faction:
                    return c
            nxt = []
            for c in front:
                for n in neighbors(c):
                    if n not in seen:
                        seen.add(n)
                        nxt.append(n)
            front = nxt
        return None

    def defect(self, officer: str, faction: str) -> None:
        """The officer changes sides together with his squad (treason, bribery, capture...)."""
        old = self.allegiance[officer]
        if old == faction:
            return
        if old in self.realms and officer in self.realms[old].council:
            members = [o for o in self.realms[old].council if o != officer]
            self.set_council(old, members, quiet=True)
        self.allegiance[officer] = faction
        self.loyalty[officer] = 60
        self.ready.discard(officer)
        city = self.officer_city.get(officer)
        if city is None or self.owner[city] != faction:
            dest = self.nearest_city(city or FACTION[faction].capital, faction)
            if dest:
                self.officer_city[officer] = dest

    def move(self, officers: Sequence[str], dest: str, spend: bool = True) -> None:
        for o in officers:
            self.officer_city[o] = dest
            if spend:
                self.ready.discard(o)

    def officer_mult(self, officer: str) -> float:
        m = 1.0
        for mult, _ in self.buffs.get(officer, []):
            m *= mult
        return m

    def buff(self, officer: str, mult: float, turns: int) -> None:
        self.buffs.setdefault(officer, []).append([mult, turns])

    def roads_within(self, start: str, steps: int, faction: str) -> Dict[str, int]:
        """Cities reachable in up to ``steps`` roads, passing only through the faction's cities."""
        dist = {start: 0}
        front = [start]
        for d in range(1, steps + 1):
            nxt = []
            for c in front:
                if c != start and self.owner[c] != faction:
                    continue
                for n in neighbors(c):
                    if n not in dist:
                        dist[n] = d
                        nxt.append(n)
            front = nxt
        return dist

    # --- council and deck -------------------------------------------------------------------
    def _inst(self, key: str, origin: str) -> CardInst:
        return CardInst(next(self._cids), key, origin, CARDS[key].expires)

    def _build_deck(self, faction: str) -> None:
        r = self.realms[faction]
        r.draw = [self._inst(k, "base") for k in BASE_SET]
        r.draw.append(self._inst(FACTION_CARD[faction], "faction"))
        for o in r.council:
            r.draw.extend(self._inst(k, o) for k in PERSONAL[o])
        r.draw.extend(self._inst(k, "threshold") for k in threshold_cards(r.council))
        self.rng.shuffle(r.draw)

    def council_options(self, faction: str) -> List[Officer]:
        return [o for o in self.officers_of(faction)]

    def can_set_council(self, faction: str, members: Sequence[str]) -> Tuple[bool, str]:
        leader = OFFICERS[faction][0].key
        if leader not in members:
            return False, "ГЛАВА ФРАКЦИИ ВСЕГДА В СОВЕТЕ"
        if len(members) > COUNCIL_SEATS or len(set(members)) != len(members):
            return False, f"В СОВЕТЕ {COUNCIL_SEATS} МЕСТ"
        if any(self.allegiance[o] != faction for o in members):
            return False, "ЧУЖОЙ ОФИЦЕР"
        return True, ""

    def set_council(self, faction: str, members: Sequence[str], quiet: bool = False) -> bool:
        """Change the council: the dismissed take their cards with them (and a grudge), the new
        members shuffle theirs into the deck; threshold cards follow the new totals."""
        members = list(members)
        if not quiet and not self.can_set_council(faction, members)[0]:
            return False
        r = self.realms[faction]
        old = list(r.council)
        gone = [o for o in old if o not in members]
        new = [o for o in members if o not in old]
        piles = (r.draw, r.hand, r.discard)
        for pile in piles:
            pile[:] = [c for c in pile if c.origin not in gone]
        for o in new:
            for k in PERSONAL[o]:
                r.draw.insert(self.rng.randrange(len(r.draw) + 1), self._inst(k, o))
        r.council = members
        want = Counter(threshold_cards(members))
        have = Counter(c.key for pile in piles for c in pile if c.origin == "threshold")
        for k in have:
            extra = have[k] - want.get(k, 0)
            for pile in piles:
                while extra > 0 and any(c.key == k and c.origin == "threshold" for c in pile):
                    pile.remove(next(c for c in pile if c.key == k and c.origin == "threshold"))
                    extra -= 1
        for k in want:
            for _ in range(want[k] - have.get(k, 0)):
                r.draw.insert(self.rng.randrange(len(r.draw) + 1), self._inst(k, "threshold"))
        for o in gone:
            if self.allegiance.get(o) == faction:
                self.change_loyalty(o, -15)
        for o in new:
            self.change_loyalty(o, 10)
        return True

    def add_curse(self, faction: str, key: str, n: int = 1, source: str = "") -> int:
        """Slip curses into a realm's draw pile; a watchful council catches some. Returns how many got in."""
        from .cards import intercepts
        r = self.realms[faction]
        got = 0
        for _ in range(n):
            if key not in ("debt", "fatigue", "strife") and intercepts(r.council) and self.rng.random() < 0.35:
                self.log_event(faction, f"Разведка перехватила {CARDS[key].name}")
                continue
            r.draw.insert(self.rng.randrange(len(r.draw) + 1), self._inst(key, "curse"))
            got += 1
        return got

    def _draw(self, faction: str, n: int) -> List[CardInst]:
        r = self.realms[faction]
        got = []
        for _ in range(n):
            if not r.draw:
                if not r.discard:
                    break
                r.draw = r.discard
                r.discard = []
                self.rng.shuffle(r.draw)
            c = r.draw.pop()
            self.stats["drawn"][c.key] += 1
            if c.card.on_draw:
                from .cardplay import on_draw
                on_draw(self, faction, c)
            else:
                r.hand.append(c)
                got.append(c)
        return got

    def draw_cards(self, faction: str, n: int) -> List[CardInst]:
        return self._draw(faction, n)

    def discard_card(self, faction: str, inst: CardInst, burn: bool = False) -> None:
        r = self.realms[faction]
        if inst in r.hand:
            r.hand.remove(inst)
        if not burn:
            r.discard.append(inst)

    # --- turns ------------------------------------------------------------------------------
    def ap_max(self, faction: str) -> int:
        return AP + AP_BONUS.get(faction, 0)

    def _start_turn(self, faction: str) -> None:
        r = self.realms[faction]
        r.ap = max(0, self.ap_max(faction) - r.ap_penalty)
        r.ap_penalty = 0
        frozen = self.frozen.pop(faction, 0)
        self.ready = set() if frozen else {o.key for o in self.officers_of(faction)}
        if frozen:
            self.log_event(faction, "Войска скованы льдом и не выходят из городов")
        for pile in (r.draw, r.hand, r.discard):              # curses fade
            for c in list(pile):
                if c.left:
                    c.left -= 1
                    if c.left <= 0:
                        pile.remove(c)
        for o in [o.key for o in self.officers_of(faction)]:
            lst = self.buffs.get(o)
            if lst:
                for b in lst:
                    b[1] -= 1
                self.buffs[o] = [b for b in lst if b[1] > 0]
        for city in self.cities_of(faction):
            d = self.defense.get(city)
            if d:
                d[1] -= 1
                if d[1] <= 0:
                    del self.defense[city]
        for k in [k for k in self.grudge if k[0] == faction]:
            self.grudge[k] -= 1
            if self.grudge[k] <= 0:
                del self.grudge[k]
        if strife(r.council) and self.turn % 3 == 0:
            self.add_curse(faction, "strife")
            self.log_event(faction, "Совет погряз в распрях")

    def end_turn(self) -> None:
        """Finish the current realm's turn and start the next one's."""
        f = self.whose_turn()
        r = self.realms[f]
        # sieges bleed the besieged cities of this realm
        for city in self.cities_of(f):
            s = self.siege.get(city)
            if s:
                self.prosperity[city] = max(1, self.prosperity[city] - 1)
                s[1] -= 1
                if s[1] <= 0 or self.owner[city] == s[0]:
                    del self.siege[city]
        # untaxed cities grow
        for city in self.cities_of(f):
            if self.taxed.get(city) == self.turn:
                self.untaxed[city] = 0
            else:
                self.untaxed[city] += 1
                if self.untaxed[city] >= GROWTH_TURNS:
                    self.untaxed[city] = 0
                    self.prosperity[city] = min(self.max_prosperity(city), self.prosperity[city] + 1)
        # treaties
        for k in list(self.truce):
            if f in k:
                self.truce[k] -= 0.5                         # both sides tick: a truce of N lasts N rounds
                if self.truce[k] <= 0:
                    del self.truce[k]
        for k, (turns, g) in list(self.trade.items()):
            if f in k:
                self.earn(f, g, "trade")
                if turns - 0.5 <= 0:
                    del self.trade[k]
                else:
                    self.trade[k] = (turns - 0.5, g)
        # pay the troops
        up = self.upkeep(f)
        self.gold[f] -= up
        self.stats["paid"][f] += up
        hist = self.income.setdefault(f, [])
        hist.append(self.earned.pop(f, 0))
        del hist[:-4]
        if self.gold[f] < 0:
            self._desert(f)
            self.gold[f] = 0
        # hand: keep what the council allows, draw the rest
        keep_n = reserve(r.council)
        if f == self.player:
            kept = [c for c in r.hand if c.id in r.keep][:keep_n]
        else:
            from .campaign_ai import cards_to_keep
            kept = cards_to_keep(self, f, keep_n)
        for c in list(r.hand):
            if c not in kept:
                r.hand.remove(c)
                r.discard.append(c)
        r.keep = []
        self._draw(f, max(0, hand_size(r.council) - len(r.hand)))
        self._next()

    def _desert(self, f: str) -> None:
        """Unpaid troops walk away until the upkeep fits the empty treasury."""
        troops = [(None, c, t) for c in self.cities_of(f) for t in self.free[c]]
        troops += [(o.key, None, t) for o in self.officers_of(f) for t in self.squads[o.key]]
        self.rng.shuffle(troops)
        lost = 0
        debt = -self.gold[f]
        for o, c, t in troops:
            if lost >= debt:
                break
            (self.squads[o] if o else self.free[c]).remove(t)
            lost += ROSTER[t.key].upkeep * 3
        self.log_event(f, "Казна пуста: часть войск разбежалась")

    def _next(self) -> None:
        n = len(self.order)
        for _ in range(n):
            self.current = (self.current + 1) % n
            if self.current == 0:
                self.turn += 1
            if self.realms[self.whose_turn()].alive:
                break
        self._start_turn(self.whose_turn())

    def run_ai(self, stop_at_player: bool = True, max_turns: int = 1000) -> None:
        """Let the computer realms play until it is the player's turn (or the round limit)."""
        from .campaign_ai import play_turn
        steps = 0
        while steps < max_turns * len(self.order):
            f = self.whose_turn()
            if stop_at_player and f == self.player:
                return
            play_turn(self, f)
            self.end_turn()
            steps += 1

    # --- playing cards ------------------------------------------------------------------------
    def can_play(self, faction: str, inst: CardInst) -> Tuple[bool, str]:
        r = self.realms[faction]
        card = inst.card
        if inst not in r.hand:
            return False, "КАРТЫ НЕТ В РУКЕ"
        if self.whose_turn() != faction:
            return False, "СЕЙЧАС НЕ ВАШ ХОД"
        if card.unplayable:
            return False, "ЭТУ КАРТУ НЕЛЬЗЯ СЫГРАТЬ"
        if card.cost > r.ap:
            return False, "НЕ ХВАТАЕТ ОД"
        if card.gold > self.gold[faction]:
            return False, "НЕ ХВАТАЕТ ЗОЛОТА"
        if card.targets and not self.options(faction, card.key, []):
            return False, "НЕТ ПОДХОДЯЩЕЙ ЦЕЛИ"
        return True, ""

    def options(self, faction: str, card_key: str, chosen: Sequence) -> list:
        from .cardplay import options
        return options(self, faction, card_key, list(chosen))

    def play(self, faction: str, inst: CardInst, targets: Sequence = ()) -> Tuple[bool, str]:
        from .cardplay import EFFECTS, valid
        ok, why = self.can_play(faction, inst)
        if not ok:
            return False, why
        card = inst.card
        targets = list(targets)
        if not valid(self, faction, card.key, targets):
            return False, "НЕВЕРНАЯ ЦЕЛЬ"
        r = self.realms[faction]
        r.ap -= card.cost
        self.gold[faction] -= card.gold
        r.hand.remove(inst)
        msg = EFFECTS[card.key](self, faction, targets)
        if card.exhaust:
            pass                                              # burnt: gone for good
        else:
            r.discard.append(inst)
        self.stats["played"][card.key] += 1
        self.log_event(faction, f"{card.name}: {msg}" if msg else card.name)
        return True, msg

    # --- war --------------------------------------------------------------------------------
    def defense_power(self, city: str) -> float:
        owner = self.owner[city]
        troops = sum(self.power(o.key) * self.officer_mult(o.key) for o in self.officers_in(city))
        troops += sum(t.power for t in self.free[city])
        d = (troops + GUARD[CITY[city].kind] + 12 * self.prosperity[city]) * WALLS[CITY[city].kind]
        if city in self.defense:
            d *= self.defense[city][0]
        if city in self.siege and self.siege[city][0] != owner:
            d *= 0.75
        if owner == "sylvan" and CITY[city].faction == "sylvan":
            d *= 1.2                                      # the forest hides its own
        return d

    def attack_power(self, faction: str, officers: Sequence[str], city: str, mult: float = 1.0) -> float:
        a = sum(self.power(o) * self.officer_mult(o) for o in officers) * mult
        if (faction, self.owner[city]) in self.grudge:
            a *= 1.3
        return a

    def win_chance(self, a: float, d: float) -> float:
        if a <= 0:
            return 0.0
        return a ** BATTLE_K / (a ** BATTLE_K + d ** BATTLE_K)

    def _losses(self, troops: List[Tuple[Optional[str], Optional[str], Troop]], frac: float) -> None:
        total = sum(t.power for _, _, t in troops)
        goal = total * frac
        self.rng.shuffle(troops)
        lost = 0
        for o, c, t in troops:
            if lost >= goal:
                break
            (self.squads[o] if o else self.free[c]).remove(t)
            lost += t.power

    def attack(self, faction: str, officers: Sequence[str], city: str, mult: float = 1.0) -> str:
        """Storm a city. Returns the chronicle line."""
        defender = self.owner[city]
        a = self.attack_power(faction, officers, city, mult)
        d = self.defense_power(city)
        if (defender, faction) in self.grudge:
            d *= 1.3
        p = self.win_chance(a, d)
        win = self.rng.random() < p
        for o in officers:
            self.ready.discard(o)
        defenders = [o.key for o in self.officers_in(city)]
        att_troops = [(o, None, t) for o in officers for t in self.squads[o]]
        def_troops = [(o, None, t) for o in defenders for t in self.squads[o]] + \
                     [(None, city, t) for t in self.free[city]]
        ratio = min(a, d) / max(a, d, 1)
        w_loss = max(0.05, min(0.85, 0.6 * ratio ** 1.3 * self.rng.uniform(0.7, 1.3)))
        l_loss = self.rng.uniform(0.6, 0.95)
        self.stats["battles"][faction] += 1
        self.change_relation(faction, defender, -20 if win else -12)
        for f in self.alive():
            if f not in (faction, defender):
                self.change_relation(faction, f, -2)
        name = CITY[city].name
        if not win:
            self._losses(att_troops, l_loss * 0.7)               # the stormers fall back home
            self._losses(def_troops, w_loss)
            for o in officers:
                self.change_loyalty(o, -5)
            return f"штурм {name} отбит ({int(a)} против {int(d)})"
        self._losses(att_troops, w_loss)
        self._losses(def_troops, l_loss)
        self.free[city] = []                                     # the garrison is gone
        self._take(faction, city, defenders)
        self.move(officers, city)
        for o in officers:
            self.change_loyalty(o, 3)
        return f"{name} взят ({int(a)} против {int(d)})"

    def _take(self, faction: str, city: str, defenders: Sequence[str]) -> None:
        old = self.owner[city]
        self.owner[city] = faction
        self.prosperity[city] = max(1, self.prosperity[city] - 1)
        self.siege.pop(city, None)
        self.defense.pop(city, None)
        self.stats["captured"][faction] += 1
        for o in defenders:                                      # retreat, or fall into captivity
            back = [n for n in neighbors(city) if self.owner[n] == old]
            if back:
                self.officer_city[o] = self.rng.choice(back)
                self.change_loyalty(o, -5)
                continue
            leader = OFFICER[o].rank == 0 and OFFICER[o].faction == old
            if not leader and (self.rng.random() < (100 - self.loyalty[o]) / 100 + 0.15
                               or not self.cities_of(old)):
                self.squads[o] = []
                self.defect(o, faction)
                self.officer_city[o] = city
                self.log_event(faction, f"{OFFICER[o].name} попал{'а' if OFFICER[o].female else ''} в плен "
                                        f"и присягнул{'а' if OFFICER[o].female else ''} победителю")
            else:
                self.squads[o] = []
                home = self.nearest_city(city, old)
                if home:
                    self.officer_city[o] = home
                else:
                    self.defect(o, faction)
                    self.officer_city[o] = city
        self.check_fall(old, faction)

    def check_fall(self, old: str, faction: str) -> None:
        """A realm without cities falls; its officers go over to the conqueror."""
        if not self.cities_of(old) and old in self.realms and self.realms[old].alive:
            self.realms[old].alive = False
            for o in [x.key for x in self.officers_of(old)]:
                self.squads[o] = []
                self.defect(o, faction)
            self.log_event(faction, f"{FACTION[old].name} пала")
