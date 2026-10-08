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

from . import cards as _cards
from . import reign
from .cards import AP, AP_BONUS, CARDS, COURSES, COUNCIL_SEATS, FACTION_CARD, PERSONAL
from .factions import ALL_FACTIONS, CITIES, CITY, FACTION, PROSPERITY, City, neighbors, relation
from .officers import OFFICER, OFFICERS, SQUAD_SLOTS, STATS, Officer
from .units import ROSTER

LOOT_PER_PROSPERITY = 25        # the North's ДОБЫЧА: gold for every point of a stormed city's prosperity
START_GOLD = {"league": 700, "sultanate": 650, "goblin": 250}
DEFAULT_GOLD = 450
START_SQUAD = (0.25, 0.4)       # starting squads: this share of the officer's leadership
TAX = 20                        # gold per point of prosperity for a tax card
GUARD = {"capital": 260, "castle": 220, "fort": 170, "town": 110, "port": 120, "lair": 140}
WALLS = {"capital": 1.25, "castle": 1.3, "fort": 1.2, "town": 1.0, "port": 1.05, "lair": 1.1}
BATTLE_K = 2.5                  # how decisive a power advantage is
MAX_PROSPERITY = 10
PROSPERITY_ROOM = 2             # a city can grow this far above its starting prosperity
GROWTH_TURNS = 4                # an untaxed city grows +1 prosperity after this many turns
# battles scar a city: -1 prosperity with this chance - less when the owner's council is good at ЛОГИСТИКА
# (carts, evacuation, the wounded taken care of): SCAR_MAX at a council total of 40 or less, SCAR_MIN at 80+
SCAR_MAX, SCAR_MIN = 1.0, 0.5
RAVAGE_BATTLES, RAVAGE_WINDOW, RAVAGE_TURNS = 2, 5, 4    # 2 battles in 5 rounds: no growth for 4 own turns


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
    course: str = "balance"     # see cards.COURSES
    course_cd: int = 0          # own turns before the course may change again
    storms: int = 0             # storms since the last war fatigue
    revealed: Dict[str, int] = field(default_factory=dict)   # rival -> turn their hand was seen
    legacy: List[str] = field(default_factory=list)  # cards left by the ruler who died last
    unrest: int = 0             # own turns of political instability left (succession.py)

    def all_cards(self) -> List[CardInst]:
        return self.draw + self.hand + self.discard


@dataclass
class Battle:
    """One storm: who, where, with what - and, once fought, who won and who fell."""
    attacker: str
    defender: str
    city: str
    officers: List[str]
    defenders: List[str]
    mult: float = 1.0
    seed: int = 0
    def_mult: float = 1.0
    withdrawn: bool = False
    att: List[Tuple[str, "Troop"]] = field(default_factory=list)
    deff: List[Tuple[Optional[str], "Troop"]] = field(default_factory=list)
    militia: int = 0
    aux: Tuple[List[str], List[str]] = field(default_factory=lambda: ([], []))   # allied detachments
    towers: int = 0             # archer towers of the stormed city (buildings.py)
    fury: Tuple[float, float] = (1.0, 1.0)    # damage multipliers of the sides (the horde's totem)
    helpers: Tuple[List[str], List[str]] = field(default_factory=lambda: ([], []))
    a: float = 0.0
    d: float = 0.0
    p: float = 0.0
    att_won: Optional[bool] = None
    fallen: set = field(default_factory=set)              # troop ids


def _pair(a: str, b: str) -> frozenset:
    return frozenset((a, b))


class Campaign:
    HOOKS = ("battle_hook", "answer_hook", "diplo_hook")
    _SHAPE: Tuple[str, ...] = ()            # attribute names of a fresh campaign (filled on first init)

    def __getstate__(self):
        """Saved games (saves.py): hooks belong to the screen, id counters become plain numbers."""
        st = dict(self.__dict__)
        for h in self.HOOKS:
            st[h] = None
        for k in ("_ids", "_cids"):
            n = next(st[k])                                # peeks one id: harmless, ids only need to be new
            st[k] = n
            setattr(self, k, itertools.count(n))
        return st

    def __setstate__(self, st):
        for k in ("_ids", "_cids"):
            st[k] = itertools.count(st[k])
        self.__dict__.update(st)
        self._upgrade()

    def _upgrade(self) -> None:
        """A save from an older build: state added since comes from a fresh campaign with the same seed,
        cards removed since leave the piles."""
        fresh = None
        if not Campaign._SHAPE:                           # nothing to compare with yet in this process
            Campaign(None)
        if any(k not in self.__dict__ for k in Campaign._SHAPE):
            fresh = Campaign(self.player, self.seed)
            for k, v in fresh.__dict__.items():
                self.__dict__.setdefault(k, v)
        for f, r in self.realms.items():
            for name, field_ in Realm.__dataclass_fields__.items():
                if name not in r.__dict__:
                    fresh = fresh or Campaign(self.player, self.seed)
                    r.__dict__[name] = getattr(fresh.realms[f], name)
            for pile in (r.draw, r.hand, r.discard):
                pile[:] = [c for c in pile if c.key in CARDS]
            r.legacy = [k for k in r.legacy if k in CARDS]

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
        base = [o for lst in OFFICERS.values() for o in lst]     # newcomers join later (enlist)
        self.allegiance: Dict[str, str] = {o.key: o.faction for o in base}   # officers may defect
        self.squads: Dict[str, List[Troop]] = {o.key: [] for o in base}
        self.free: Dict[str, List[Troop]] = {c.key: [] for c in CITIES}
        self.prosperity: Dict[str, int] = dict(PROSPERITY)
        self.taxed: Dict[str, int] = {}                       # city -> turn it was last taxed
        self.untaxed: Dict[str, int] = {c.key: 0 for c in CITIES}
        self.loyalty: Dict[str, int] = {}
        # officers change during the campaign (growth.py): stats, leadership, experience, feats
        self.ostats: Dict[str, List[int]] = {o.key: list(o.stats) for o in base}
        self.olead: Dict[str, int] = {o.key: o.leadership for o in base}
        self.xp: Dict[str, float] = {o.key: 0.0 for o in base}
        self.level: Dict[str, int] = {o.key: 1 for o in base}
        self.idle: Dict[str, int] = {}                        # own turns without experience
        self.last_used: Dict[str, int] = {}                   # turn an adviser's card was last played
        self.streak: Dict[str, int] = {}                      # battles won in a row
        self.lairs: Dict[str, int] = {}                       # goblin lairs taken
        self.feats: Dict[str, str] = {}                       # feat card -> officer who earned it
        self.extra: Dict[str, List[str]] = {}                 # officer -> cards earned in play
        self.muster: Dict[str, int] = {}                      # city -> own turns its recruiting stays open
        self.leader: Dict[str, Optional[str]] = {f: offs[0].key for f, offs in OFFICERS.items()}
        self.dead: set = set()                                # officers who died (succession.py)
        self.claim: Dict[str, float] = {}                     # merit at court: who would inherit the throne
        self.sick: Dict[str, int] = {}                        # city -> own turns of sickness left
        self.immune: Dict[str, int] = {}                      # city -> turns a physician keeps it healthy
        self.buildings: Dict[str, List[str]] = {}             # city -> building keys (buildings.py)
        self.newcomers: Dict[str, int] = {}                   # faction -> young talents so far
        self.great: Dict[str, Tuple[str, str]] = {}           # the horde's great building: (kind, lair) (horde.py)
        self.manner: Dict[str, str] = {}                      # the horde's chosen way (kept after a loss)
        self.force_great: Optional[str] = None                # tests/cardsim: force the horde's choice
        self.pit: List[Tuple[str, int]] = []                  # captives in the pit: (their realm, power)
        self.paid: Dict[str, int] = {}                        # realm -> own turns the horde stays bought off
        self.fought: Dict[str, List[int]] = {}                # city -> rounds of the battles fought there lately
        self.ravaged: Dict[str, int] = {}                     # city -> own turns it cannot grow
        self.law: Dict[str, int] = {c.key: 6 for c in CITIES if c.faction != "goblin"}   # ПОРЯДОК (order.py)
        self.dens: set = set()                                # cities with a thieves' den
        self.burnt: set = set()                               # (officer, card) burnt after play: never comes back
        self.rel: Dict[frozenset, int] = {}
        self.truce: Dict[frozenset, int] = {}                 # pair -> turns left
        self.alliance: Dict[frozenset, List] = {}             # pair -> [turns left, common enemy]
        self.betrayals: Counter = Counter()                   # broken treaties, by realm
        self.last_attack: Dict[Tuple[str, str], int] = {}     # (attacker, victim) -> turn
        self.losses: List[Tuple[int, str, str, str]] = []     # (turn, old owner, new owner, city)
        self.proposals: Dict[Tuple[str, str], int] = {}       # (from, to) -> turn of the last envoys
        self.attacks: List[Tuple[int, str, Optional[str], str, bool]] = []   # turn, by, from, city, won
        self.world_events: List[Tuple[int, str, str]] = []  # (turn, event, what happened)
        self.active: Dict[str, int] = {}                      # running world events -> rounds left
        self.last_event = -99
        self.no_events = False                                # tests switch the world's whims off
        self.diplo_hook = None      # (camp, from, to, kind, reasons) -> the player's yes/no
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
                                          "paid": Counter(), "courses": Counter(), "levels": Counter(),
                                          "declines": Counter(), "feats": Counter(),
                                          "deserted_officers": Counter(), "reshuffles": Counter(),
                                          "diplomacy": Counter(), "hegemon": Counter(), "events": Counter(),
                                          "deaths": Counter(), "successions": Counter(),
                                          "unrest_turns": Counter(), "outbreaks": Counter(),
                                          "outbreaks_stopped": Counter(), "sick_deaths": Counter(),
                                          "newcomers": Counter(), "built": Counter(), "ruined": Counter(),
                                          "great": Counter(), "great_lost": Counter(), "captives": Counter(),
                                          "ransom": Counter(), "sacrificed": Counter(), "bred": Counter(),
                                          "bought_off": Counter(), "scarred": Counter(), "crime": Counter(),
                                          "ravaged": Counter()}
        self.earned: Dict[str, int] = {}                      # gold earned this turn
        self.income: Dict[str, List[int]] = {}                # gold earned in the last turns
        self.battle_hook = None     # (camp, Battle) -> True if the battle was fought for real
        self.answer_hook = None     # (camp, Battle, cards) -> card the player answers with, or None
        self.turn = 1
        self.order: List[str] = [f.key for f in ALL_FACTIONS]
        if player in self.order:                              # the player moves first
            self.order.remove(player)
            self.order.insert(0, player)
        self.current = 0
        self._deploy()
        for a, b in itertools.combinations([f.key for f in ALL_FACTIONS], 2):
            self.rel[_pair(a, b)] = relation(a, b)[0]
        self.realms: Dict[str, Realm] = {}
        for f in ALL_FACTIONS:
            offs = OFFICERS[f.key]
            self.realms[f.key] = Realm(f.key, [offs[0].key])      # the council starts empty: only the ruler
            self._build_deck(f.key)
            self._draw(f.key, self.hand_size(self.realms[f.key].council))
        self._start_turn(self.order[0])
        Campaign._SHAPE = tuple(self.__dict__)

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

    def enlist(self, off: Officer, city: str) -> None:
        """A new officer joins the faction owning ``city`` (a young talent, population.py)."""
        k = off.key
        faction = self.owner[city]
        self.dead.discard(k)
        self.allegiance[k] = faction
        self.officer_city[k] = city
        self.squads[k] = []
        self.loyalty[k] = self.rng.randint(55, 80)
        self.ostats[k] = list(off.stats)
        self.olead[k] = off.leadership
        self.xp[k] = 0.0
        self.level[k] = 1
        self.extra[k] = _cards.newcomer_cards(off)
        self._starting_squad(off, CITY[city])

    def _new(self, key: str) -> Troop:
        return Troop(next(self._ids), key)

    # --- officers as they are now ----------------------------------------------------------
    def stat(self, officer: str, name: str) -> int:
        return self.ostats[officer][STATS.index(name)]

    def leadership(self, officer: str) -> int:
        return self.olead[officer]

    def presence(self, officer: str) -> float:
        lead = (self.olead[officer] - 200) / 600
        st = self.ostats[officer]
        return max(0.0, min(1.0, 0.5 * lead + 0.5 * (sum(st) / len(st) - 6) / 10))

    def personal(self, officer: str) -> List[str]:
        """The officer's cards - minus those he already burnt (a bill cashed once is gone for good, even if
        he leaves the council and comes back)."""
        return [k for k in list(PERSONAL.get(officer, ())) + self.extra.get(officer, [])
                if (officer, k) not in self.burnt]

    def totals(self, council) -> Dict[str, int]:
        return _cards.council_totals(list(council), self.ostats)

    def thresholds(self, council, faction: Optional[str] = None) -> List[str]:
        council = list(council)
        if faction is None and council:
            faction = self.allegiance.get(council[0])
        return _cards.threshold_cards(council, self.ostats, faction)

    def competence(self, council) -> int:
        return _cards.competence(list(council), self.ostats)

    def hand_size(self, council) -> int:
        return _cards.hand_size(list(council), self.ostats)

    def reserve(self, council) -> int:
        return _cards.reserve(list(council), self.ostats)

    def strife(self, council) -> bool:
        return _cards.strife(list(council), self.ostats)

    def intercepts(self, council) -> bool:
        return _cards.intercepts(list(council), self.ostats)

    def course_cooldown(self, council) -> int:
        return _cards.course_cooldown(list(council), self.ostats)

    def muster_turns(self, council) -> int:
        return _cards.muster_turns(list(council), self.ostats)

    def card_cost(self, faction: str, inst) -> int:
        """A devoted adviser (loyalty 100) makes his own cards cost 1 action point less."""
        o = inst.origin
        cost = inst.card.cost
        if o in OFFICER and self.devoted(o) and o in self.realms[faction].council:
            cost = max(0, cost - 1)
        return cost

    def devoted(self, officer: str) -> bool:
        return self.loyalty.get(officer, 0) >= 100 and not self.is_leader(officer)

    def is_leader(self, officer: str) -> bool:
        """The ruler of the realm the officer serves (rulers change: succession.py)."""
        return self.leader.get(self.allegiance.get(officer)) == officer

    def refresh_council_of(self, officer: str) -> None:
        """An adviser's stats changed: the council's threshold cards follow."""
        f = self.allegiance.get(officer)
        r = self.realms.get(f) if hasattr(self, "realms") else None
        if r and officer in r.council:
            self._sync_thresholds(f)

    # --- queries ----------------------------------------------------------------------------
    def officers_in(self, city: str) -> List[Officer]:
        return sorted((OFFICER[k] for k, c in self.officer_city.items()
                       if c == city and self.allegiance[k] == self.owner[city] and k not in self.dead),
                      key=lambda o: (not self.is_leader(o.key), o.rank, -self.olead[o.key]))

    def power(self, officer: str) -> int:
        return sum(t.power for t in self.squads[officer])

    def troop_upkeep(self, faction: str, key: str) -> float:
        from .horde import upkeep_mult
        u = ROSTER[key].upkeep * upkeep_mult(self, faction, key)
        if "frost" in self.active and faction not in ("north", "highland"):
            u *= 1.3
        if faction == "ashen" and ROSTER[key].undead:
            return u * 0.3                                # the dead ask for little pay, only for bones
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
        return sorted((OFFICER[k] for k, f in self.allegiance.items() if f == faction and k not in self.dead),
                      key=lambda o: (self.leader.get(faction) != o.key, o.faction != faction, o.rank,
                                     -self.olead[o.key]))

    def cities_of(self, faction: str) -> List[str]:
        return [c for c, f in self.owner.items() if f == faction]

    def controls(self, city: str) -> bool:
        """The human player may manage this city."""
        return self.player is not None and self.owner[city] == self.player

    def alive(self) -> List[str]:
        return [f for f in self.order if f in self.realms and self.realms[f].alive]

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
        from .horde import bought
        return self.truce.get(_pair(a, b), 0) > 0 or _pair(a, b) in self.alliance or bought(self, a, b)

    def max_prosperity(self, city: str) -> int:
        return min(MAX_PROSPERITY, PROSPERITY[city] + PROSPERITY_ROOM)

    def income_of(self, city: str, faction: str) -> int:
        """What a tax card brings in this city now."""
        best = max((self.stat(o.key, "УПРАВЛЕНИЕ") for o in self.officers_in(city) if self.allegiance[o.key] == faction),
                   default=0)
        from .order import tax_mult
        g = int((self.prosperity[city] * TAX + 2 * best) * tax_mult(self, city))   # a thieves' den skims it
        return g * 2 // 5 if "drought" in self.active else g

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
        from .horde import pen_hire
        from .buildings import tiltyard_mount
        pen = pen_hire(self, city, key) or key == tiltyard_mount(self, city)    # open on any turn
        if key not in CITY[city].pool and not pen:
            return False, "ЭТИХ ВОИНОВ ЗДЕСЬ НЕ НАНЯТЬ"
        if self.muster.get(city, 0) <= 0 and not pen:
            return False, "НАЙМ ЗАКРЫТ: НУЖНА КАРТА СБОР ВОЙСК"
        if self.hire_price(city, key) > self.gold[faction]:
            return False, "НЕ ХВАТАЕТ ЗОЛОТА"
        return True, ""

    def hire_price(self, city: str, key: str) -> int:
        from .buildings import hire_price
        from .horde import hire_mult
        return hire_price(self, city, int(round(ROSTER[key].cost * hire_mult(self, city, key))), key)

    def hire_pool(self, city: str) -> List[str]:
        """Who can be hired in the city: its pool and the cavalry of a tiltyard."""
        from .buildings import tiltyard_mount
        mount = tiltyard_mount(self, city)
        return list(CITY[city].pool) + ([mount] if mount and mount not in CITY[city].pool else [])

    def hire(self, city: str, key: str) -> Optional[Troop]:
        ok, _ = self.can_hire(city, key)
        if not ok:
            return None
        self.gold[self.owner[city]] -= self.hire_price(city, key)
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
        if self.power(officer) + troop.power > self.olead[officer]:
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
        if self.is_leader(officer):
            return                                       # a ruler never wavers
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
        if old == faction or self.is_leader(officer) or officer in self.dead:
            return                                       # a ruler never changes sides
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
        if self.loyalty.get(officer, 60) < 30:
            m *= 0.9                                      # fights half-heartedly
        elif self.devoted(officer):
            m *= 1.15                                     # would die for his lord
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
        r.draw = [self._inst(k, "base") for k in _cards.course_base(faction, r.course)]
        lead = self.leader.get(faction)
        if lead and OFFICER[lead].rank == 0 and OFFICER[lead].faction == faction:
            r.draw.append(self._inst(FACTION_CARD[faction], "faction"))
        r.draw.extend(self._inst(k, "legacy") for k in r.legacy)
        r.draw.append(self._inst("sickness", "fate"))
        r.draw.extend(self._inst(k, "passive") for k in _cards.PASSIVE_CARDS.get(faction, ()))
        for o in r.council:
            r.draw.extend(self._inst(k, o) for k in self.personal(o))
        r.draw.extend(self._inst(k, "threshold") for k in self.thresholds(r.council, faction))
        self.rng.shuffle(r.draw)

    def council_options(self, faction: str) -> List[Officer]:
        return [o for o in self.officers_of(faction)]

    def can_set_council(self, faction: str, members: Sequence[str]) -> Tuple[bool, str]:
        leader = self.leader.get(faction)
        if leader and leader not in members:
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
            for k in self.personal(o):
                r.draw.insert(self.rng.randrange(len(r.draw) + 1), self._inst(k, o))
            self.last_used[o] = self.turn
        r.council = members
        self._sync_thresholds(faction)
        for o in gone:
            if self.allegiance.get(o) == faction:
                self.change_loyalty(o, -20)
        for o in new:
            self.change_loyalty(o, 8)
        return True

    def can_change_course(self, faction: str, course: str) -> Tuple[bool, str]:
        r = self.realms[faction]
        if course not in COURSES:
            return False, "НЕТ ТАКОГО КУРСА"
        if course == r.course:
            return False, "ЭТО И ЕСТЬ НЫНЕШНИЙ КУРС"
        if self.whose_turn() != faction:
            return False, "КУРС МЕНЯЮТ В СВОЙ ХОД"
        if r.course_cd > 0:
            return False, f"СМЕНИТЬ КУРС МОЖНО ЧЕРЕЗ {r.course_cd} Х."
        return True, ""

    def change_course(self, faction: str, course: str) -> bool:
        """The cards of state are swapped for the new course's (wherever they are, the hand too);
        then the course is locked for ``course_cooldown`` turns."""
        if not self.can_change_course(faction, course)[0]:
            return False
        r = self.realms[faction]
        for pile in (r.draw, r.hand, r.discard):
            pile[:] = [c for c in pile if c.origin != "base"]
        for k in _cards.course_base(faction, course):
            r.draw.insert(self.rng.randrange(len(r.draw) + 1), self._inst(k, "base"))
        r.course = course
        r.course_cd = self.course_cooldown(r.council)
        r.storms = 0
        self.log_event(faction, f"Новый курс державы: {COURSES[course].name}")
        return True

    def _sync_thresholds(self, faction: str) -> None:
        """Threshold cards follow the council's current totals (wherever the cards are)."""
        r = self.realms[faction]
        piles = (r.draw, r.hand, r.discard)
        want = Counter(self.thresholds(r.council, faction))
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

    def add_curse(self, faction: str, key: str, n: int = 1, source: str = "") -> int:
        """Slip curses into a realm's draw pile; a watchful council catches some of those a rival sends
        (``source``) - the realm's own troubles cannot be intercepted. Returns how many got in."""
        r = self.realms[faction]
        got = 0
        hostile = bool(source) and source != faction and key not in ("debt", "fatigue", "strife", "war_fatigue")
        if hostile:
            stop = self.answers(faction, "cursed")
            if stop:                                          # the courier never arrives
                r.hand.remove(stop[0])
                r.discard.append(stop[0])
                self.stats["played"]["intercept"] += 1
                self.log_event(faction, f"ПЕРЕХВАТ ГОНЦА: {CARDS[key].name} не дошла")
                return 0
        for _ in range(n):
            catch = max(0.35 if self.intercepts(r.council) else 0.0, 0.5 if r.course == "intrigue" else 0.0)
            if hostile and self.rng.random() < catch:
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
        self.settle_officers(faction)
        from .succession import ensure_ruler
        ensure_ruler(self, faction)
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
        self.stats["courses"][f"{faction}:{r.course}"] += 1
        if r.course_cd > 0:
            r.course_cd -= 1
        for city in [c for c in self.muster if self.owner[c] == faction]:
            self.muster[city] -= 1
            if self.muster[city] <= 0:
                del self.muster[city]
        from . import growth
        growth.turn(self, faction)
        from . import population, succession
        succession.turn(self, faction)
        population.turn(self, faction)
        from . import horde, order
        horde.turn(self, faction)
        order.turn(self, faction)
        from .buildings import count
        for city in self.cities_of(faction):
            if count(self, city, "temple"):
                for o in self.officers_in(city):
                    self.change_loyalty(o.key, 1)
            if city in self.immune:
                self.immune[city] -= 1
                if self.immune[city] <= 0:
                    del self.immune[city]
            if city in self.ravaged:
                self.ravaged[city] -= 1
                if self.ravaged[city] <= 0:
                    del self.ravaged[city]
        if r.course == "intrigue":                            # paranoia: nobody trusts anybody
            for o in self.officers_of(faction):
                self.change_loyalty(o.key, -1)
        if self.strife(r.council) and self.turn % 3 == 0:
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
            if self.taxed.get(city) == self.turn or r.course == "war" or "frost" in self.active \
                    or self.ravaged.get(city):
                self.untaxed[city] = 0
            else:
                self.untaxed[city] += 1
                need = GROWTH_TURNS - 1 if r.course == "economy" else GROWTH_TURNS
                from .diplomacy import growth_blocked
                if growth_blocked(self, city):
                    need += 1                                 # a restless border
                if self.prosperity[city] >= PROSPERITY[city]:
                    need *= 3                                 # above its old self a city grows only slowly
                if self.untaxed[city] >= need:
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
        # a proud adviser nobody listened to this turn takes offence
        for c in r.hand:
            if c.key == "pride" and c.origin in OFFICER:
                self.change_loyalty(c.origin, -8)
                self.log_event(f, f"ГОРДЫНЯ: {OFFICER[c.origin].name} обижен{'а' if OFFICER[c.origin].female else ''}, "
                                  f"что {'её' if OFFICER[c.origin].female else 'его'} не выслушали: верность -8")
        # hand: keep what the council allows, draw the rest
        keep_n = self.reserve(r.council)
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
        self._draw(f, max(0, self.hand_size(r.council) - len(r.hand)))
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
        from . import growth
        growth.on_unpaid(self, f)

    def _next(self) -> None:
        n = len(self.order)
        for _ in range(n):
            self.current = (self.current + 1) % n
            if self.current == 0:
                self.turn += 1
                from . import diplomacy, events
                diplomacy.round_tick(self)
                events.round_tick(self)
            if self.realms[self.whose_turn()].alive:
                break
        self._start_turn(self.whose_turn())

    def run_ai(self, stop_at_player: bool = True, max_turns: int = 1000) -> None:
        """Let the computer realms play until it is the player's turn (or the round limit)."""
        from .campaign_ai import play_turn
        if stop_at_player and self.player and not self.realms[self.player].alive:
            max_turns = min(max_turns, 1)                     # the player's realm fell: one round at a time
        steps = 0
        while steps < max_turns * len(self.order):
            f = self.whose_turn()
            if stop_at_player and f == self.player:
                return
            play_turn(self, f)
            self.end_turn()
            steps += 1
            if stop_at_player and self.player and not self.realms[self.player].alive:
                max_turns = min(max_turns, 1)             # the player's realm fell meanwhile: one round, no more

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
        if card.reaction:
            return False, "ЭТО ОТВЕТ: СРАБОТАЕТ В ЧУЖОЙ ХОД"
        if self.card_cost(faction, inst) > r.ap:
            return False, "НЕ ХВАТАЕТ ОД"
        if card.gold > self.gold[faction]:
            return False, "НЕ ХВАТАЕТ ЗОЛОТА"
        from .cardplay import completable
        if card.targets and not completable(self, faction, card.key):
            return False, "НЕТ ПОДХОДЯЩЕЙ ЦЕЛИ"
        if card.key == "buy_off":
            from .horde import can_buy_off
            return can_buy_off(self, faction)
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
        r.ap -= self.card_cost(faction, inst)
        self.gold[faction] -= card.gold
        r.hand.remove(inst)
        msg = EFFECTS[card.key](self, faction, targets)
        if card.exhaust:                                      # burnt: gone for good
            if inst.origin in OFFICER:
                self.burnt.add((inst.origin, card.key))
        else:
            r.discard.append(inst)
        self.stats["played"][card.key] += 1
        from . import growth
        growth.on_card_used(self, faction, inst)
        self.log_event(faction, f"{card.name}: {msg}" if msg else card.name)
        return True, msg

    # --- war --------------------------------------------------------------------------------
    def defense_power(self, city: str) -> float:
        owner = self.owner[city]
        troops = sum(self.power(o.key) * self.officer_mult(o.key) for o in self.officers_in(city))
        troops += sum(t.power for t in self.free[city])
        from .buildings import defense_bonus, defense_mult
        d = (troops + GUARD[CITY[city].kind] + 12 * self.prosperity[city] + defense_bonus(self, city)) \
            * WALLS[CITY[city].kind] * defense_mult(self, city)
        if city in self.defense:
            d *= self.defense[city][0]
        if city in self.siege and self.siege[city][0] != owner:
            d *= 0.75
        if owner in self.realms and self.realms[owner].course == "defense":
            d *= 1.25
        if owner == "sylvan" and CITY[city].faction == "sylvan":
            d *= 1.2                                      # the forest hides its own
        from .horde import side_mult
        return d * side_mult(self, owner)

    def attack_power(self, faction: str, officers: Sequence[str], city: str, mult: float = 1.0) -> float:
        from .horde import side_mult
        a = sum(self.power(o) * self.officer_mult(o) for o in officers) * mult * side_mult(self, faction)
        if (faction, self.owner[city]) in self.grudge:
            a *= 1.3
        if self.owner[city] != "goblin" and self.relation(faction, self.owner[city]) <= 14:
            a *= 1.15                                         # blood feud
        return a

    def win_chance(self, a: float, d: float) -> float:
        if a <= 0:
            return 0.0
        return a ** BATTLE_K / (a ** BATTLE_K + d ** BATTLE_K)

    def attack(self, faction: str, officers: Sequence[str], city: str, mult: float = 1.0) -> str:
        """Storm a city. The defender may answer with a card from his hand; then the battle is fought
        for real (``battle_hook``, when the player is involved or wants to watch) or worked out from
        the forces. Returns the chronicle line."""
        defender = self.owner[city]
        for o in officers:
            self.ready.discard(o)
        b = Battle(faction, defender, city, list(officers), [o.key for o in self.officers_in(city)],
                   mult=mult, seed=self.rng.randrange(1 << 30))
        self.last_attack[(faction, defender)] = self.turn
        src = self.officer_city.get(officers[0]) if officers else None
        self.attacks.append((self.turn, faction, src, city, False))
        answer = self._answer(b)
        if b.withdrawn:
            return self._withdraw(b, answer)
        self._forces(b)
        if not (self.battle_hook and self.battle_hook(self, b)):
            self._formula(b)
        line = self._settle(b, answer)
        self._scar(city, self.owner[city])             # whoever holds the city after the battle answers for it
        return line

    def _forces(self, b: "Battle") -> None:
        city = b.city
        from .buildings import count
        b.towers = count(self, city, "tower")
        b.att = [(o, t) for o in b.officers for t in self.squads[o]]
        b.deff = [(o, t) for o in b.defenders for t in self.squads[o]] + [(None, t) for t in self.free[city]]
        b.a = self.attack_power(b.attacker, b.officers, city, b.mult)
        b.d = self.defense_power(city) * b.def_mult
        if (b.defender, b.attacker) in self.grudge:
            b.d *= 1.3
        if "goblin" not in (b.attacker, b.defender) and self.relation(b.attacker, b.defender) <= 14:
            b.d *= 1.15                                       # blood feud: they fight to the last
        b.fury = self._battle_fury(b)
        from .diplomacy import ally_help
        for side, (me, enemy) in enumerate(((b.attacker, b.defender), (b.defender, b.attacker))):
            if enemy == "goblin" and me == "goblin":
                continue
            power, who = ally_help(self, me, city, enemy)
            if power <= 0:
                continue
            b.helpers[side].extend(who)
            if side == 0:
                b.a += power
            else:
                b.d += power
            pool = sorted((t for a in who for o in self.officers_of(a) for n in neighbors(city)
                           if self.officer_city.get(o.key) == n for t in self.squads[o.key]),
                          key=lambda t: -t.power)
            got = 0
            for t in pool:                                # the detachment that actually marches
                if got >= power:
                    break
                b.aux[side].append(t.key)
                got += t.power
        b.p = self.win_chance(b.a, b.d)
        troops = sum(t.power for _, t in b.deff)
        b.militia = max(0, min(8, int((b.d - troops) / ROSTER["militia"].cost)))   # walls and townsfolk

    def _battle_fury(self, b: "Battle") -> Tuple[float, float]:
        """Damage multipliers of both sides in a real battle: everything the odds count beyond the bare
        troops (officers' buffs and spirit, the storm card, grudges, feuds, defence cards and course, the
        totem). Walls and townsfolk come as militia and towers instead."""
        raw_a = sum(t.power for _, t in b.att)
        fa = b.a / raw_a if raw_a else 1.0
        owner = b.defender
        own = sum(self.power(o) for o in b.defenders)
        base = own + sum(t.power for t in self.free[b.city])
        spirit = (sum(self.power(o) * self.officer_mult(o) for o in b.defenders)
                  + sum(t.power for t in self.free[b.city])) / base if base else 1.0   # only townsfolk: plain spirit
        fd = spirit * b.def_mult
        if b.city in self.defense:
            fd *= self.defense[b.city][0]
        if b.city in self.siege and self.siege[b.city][0] != owner:
            fd *= 0.75
        if owner in self.realms and self.realms[owner].course == "defense":
            fd *= 1.25
        if owner == "sylvan" and CITY[b.city].faction == "sylvan":
            fd *= 1.2
        from .horde import side_mult
        fd *= side_mult(self, owner)
        if (b.defender, b.attacker) in self.grudge:
            fd *= 1.3
        if "goblin" not in (b.attacker, b.defender) and self.relation(b.attacker, b.defender) <= 14:
            fd *= 1.15
        clamp = lambda v: max(0.6, min(2.5, v))
        return clamp(fa), clamp(fd)

    def _formula(self, b: "Battle") -> None:
        b.att_won = self.rng.random() < b.p
        ratio = min(b.a, b.d) / max(b.a, b.d, 1)
        w_loss = max(0.05, min(0.85, 0.6 * ratio ** 1.3 * self.rng.uniform(0.7, 1.3)))
        l_loss = self.rng.uniform(0.6, 0.95)
        att_loss, def_loss = (w_loss, l_loss) if b.att_won else (l_loss * 0.7, w_loss)
        b.fallen = self._pick(b.att, att_loss) | self._pick(b.deff, def_loss)

    def _pick(self, troops, frac: float) -> set:
        order = list(troops)
        self.rng.shuffle(order)
        goal, lost, out = sum(t.power for _, t in order) * frac, 0, set()
        for _, t in order:
            if lost >= goal:
                break
            out.add(t.id)
            lost += t.power
        return out

    def fate_odds(self, officer: Optional[str], won: bool, ratio: float) -> float:
        """Chance that a fallen warrior lives: the winners' wounded are nursed back (better under an
        officer with good ЛОГИСТИКА); the losers' wounded may slip away to a neighbouring own city
        (also ЛОГИСТИКА, and harder the more crushing the defeat)."""
        log = self.stat(officer, "ЛОГИСТИКА") if officer else 8
        if won:
            return min(0.6, 0.2 + 0.015 * log)
        return min(0.5, (0.1 + 0.015 * log) * (0.5 + 0.5 * ratio))

    def scar_chance(self, owner: str) -> float:
        """Chance that a battle in a city costs it 1 prosperity - checked against the council ЛОГИСТИКА of
        the side that holds the city after the battle."""
        r = self.realms.get(owner)
        log = self.totals(r.council)["ЛОГИСТИКА"] if r and r.council else 0
        return SCAR_MAX - (SCAR_MAX - SCAR_MIN) * max(0.0, min(1.0, (log - 40) / 40))

    def _scar(self, city: str, owner: str) -> None:
        """Every battle may scar the city; three in a few rounds leave it ravaged."""
        recent = [t for t in self.fought.get(city, []) if t > self.turn - RAVAGE_WINDOW] + [self.turn]
        self.fought[city] = recent
        from .order import BATTLE, hit
        hit(self, city, BATTLE)
        if self.rng.random() < self.scar_chance(owner):
            self.prosperity[city] = max(1, self.prosperity[city] - 1)
            self.stats["scarred"][owner] += 1
        if len(recent) >= RAVAGE_BATTLES and not self.ravaged.get(city):
            self.ravaged[city] = RAVAGE_TURNS
            self.stats["ravaged"][owner] += 1
            self.log_event(owner, f"{CITY[city].name} РАЗОРЁН боями: {RAVAGE_TURNS} х. не растёт")

    def _settle(self, b: "Battle", answer: str) -> str:
        city, name = b.city, CITY[b.city].name
        faction, defender = b.attacker, b.defender
        self.stats["battles"][faction] += 1
        r = self.realms.get(faction)
        if r and r.course == "war":                           # war fatigue: every storm
            self.add_curse(faction, "war_fatigue")
            self.log_event(faction, "ВОЕННАЯ УСТАЛОСТЬ")
        won = bool(b.att_won)
        if self.attacks and self.attacks[-1][3] == city:
            t, by, src, c, _ = self.attacks[-1]
            self.attacks[-1] = (t, by, src, c, won)
        for a in b.helpers[0]:
            self.change_relation(a, defender, -4)
            self.change_relation(a, faction, 2)
        if b.helpers[0] or b.helpers[1]:
            names = ", ".join(FACTION[x].short for x in b.helpers[0] + b.helpers[1])
            answer += f"; союзники в бою: {names}"
        self.change_relation(faction, defender, -20 if won else -12)
        for f in self.alive():
            if f not in (faction, defender):
                self.change_relation(faction, f, -2)
        ratio = min(b.a, b.d) / max(b.a, b.d, 1)
        dead = wounded = fled = 0
        refuge = [n for n in neighbors(city) if self.owner[n] == defender]
        escapees: List[Tuple[Optional[str], Troop]] = []
        gob_won = (faction if won else defender) == "goblin"
        loser = defender if won else faction
        pit = [(loser, t.power) for _, t in (b.deff if won else b.att) if t.id in b.fallen] if gob_won else []
        for side, troops in (("att", b.att), ("def", b.deff)):
            side_won = won if side == "att" else not won
            for o, t in troops:
                if t.id not in b.fallen:
                    continue
                if self.rng.random() < self.fate_odds(o or (b.defenders[0] if b.defenders else None), side_won, ratio):
                    if side_won or side == "att":
                        wounded += 1                         # healed in the ranks (stormers are home)
                        continue
                    if refuge:
                        escapees.append((o, t))
                        fled += 1
                        self._remove(o, city, t)
                        continue
                self._remove(o, city, t)
                dead += 1
        tail = f"; павших {dead}, раненых {wounded}" + (f", бежали {fled}" if fled else "") + answer
        if pit:
            from .horde import on_battle as pit_battle
            pit_battle(self, b, pit)
        from . import growth
        if not won:
            from .buildings import RUIN_FAILED_STORM, ruin
            ruin(self, city, RUIN_FAILED_STORM, "штурм отбит, но город пострадал")
            for o in b.officers:
                self.change_loyalty(o, -5)
            growth.on_battle(self, b)
            from .succession import on_battle
            on_battle(self, b)
            return f"штурм {name} отбит ({int(b.a)} против {int(b.d)}){tail}"
        for t in list(self.free[city]):                       # the rest of the garrison runs if it can
            self.free[city].remove(t)
            if refuge:
                escapees.append((None, t))
        self._take(faction, city, b.defenders)
        for o, t in escapees:
            if o and self.allegiance.get(o) == defender and self.officer_city.get(o) in refuge:
                self.squads[o].append(t)
            elif refuge:
                self.free[self.rng.choice(refuge)].append(t)
        self.move(b.officers, city)
        for o in b.officers:
            self.change_loyalty(o, 3)
        growth.on_battle(self, b)
        from .succession import on_battle
        on_battle(self, b)
        return f"{name} взят ({int(b.a)} против {int(b.d)}){tail}"

    def _remove(self, officer: Optional[str], city: str, t: Troop) -> None:
        for lst in ((self.squads[officer],) if officer else ()) + (self.free[city],):
            if t in lst:
                lst.remove(t)
                return

    # --- answers ----------------------------------------------------------------------------
    def answers(self, faction: str, trigger: str) -> List[CardInst]:
        return [c for c in self.realms[faction].hand if c.card.reaction == trigger] if faction in self.realms else []

    def _answer(self, b: "Battle") -> str:
        """The defender may play one answer card from his hand."""
        cards = self.answers(b.defender, "attacked")
        if not any(self.owner[n] == b.defender for n in neighbors(b.city)):
            cards = [c for c in cards if c.key != "withdraw"]      # nowhere to withdraw to: no such answer
        if not cards:
            return ""
        if b.defender == self.player and self.answer_hook:
            pick = self.answer_hook(self, b, cards)
        elif b.defender == self.player:
            pick = None
        else:
            from .campaign_ai import choose_answer
            pick = choose_answer(self, b, cards)
        if pick is None:
            return ""
        r = self.realms[b.defender]
        r.hand.remove(pick)
        r.discard.append(pick)
        self.stats["played"][pick.key] += 1
        k = pick.key
        if k == "ambush":
            for o in b.officers:
                losses = self._pick([(o, t) for t in self.squads[o]], 0.15)
                self.squads[o] = [t for t in self.squads[o] if t.id not in losses]
        elif k == "sortie":
            b.def_mult *= 1.3
        elif k == "reinforce":
            cands = [o for n in neighbors(b.city) if self.owner[n] == b.defender for o in self.officers_in(n)]
            if cands:
                o = max(cands, key=lambda x: self.power(x.key)).key
                self.officer_city[o] = b.city
                b.defenders.append(o)
        elif k == "withdraw":
            b.withdrawn = True
        return f"; ответ: {pick.card.name}"

    def _withdraw(self, b: "Battle", answer: str) -> str:
        if self.attacks and self.attacks[-1][3] == b.city:   # the city changed hands: the storm succeeded
            t, by, src, c, _ = self.attacks[-1]
            self.attacks[-1] = (t, by, src, c, True)
        self.stats["battles"][b.attacker] += 1
        r = self.realms.get(b.attacker)
        if r and r.course == "war":
            self.add_curse(b.attacker, "war_fatigue")
        refuge = [n for n in neighbors(b.city) if self.owner[n] == b.defender]
        dest = max(refuge, key=lambda c: self.defense_power(c)) if refuge else None
        if dest:
            for o in b.defenders:
                self.officer_city[o] = dest
            self.free[dest].extend(self.free[b.city])
        self.free[b.city] = []
        self._take(b.attacker, b.city, [] if dest else b.defenders)
        self.move(b.officers, b.city)
        return f"{CITY[b.city].name} сдан без боя{answer}"

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

    def _take(self, faction: str, city: str, defenders: Sequence[str]) -> None:
        old = self.owner[city]
        from . import growth
        if old in self.realms:
            growth.on_city_lost(self, old, city)
        growth.on_city_won(self, faction)
        from .buildings import RUIN_CAPTURE, ruin
        ruin(self, city, 1.0 if faction == "goblin" else RUIN_CAPTURE,     # goblins keep nothing people built
             "город взят штурмом", all_of_them=True)
        if faction == "north":                                   # ДОБЫЧА: the longships carry the city's wealth home
            self.earn(faction, LOOT_PER_PROSPERITY * self.prosperity[city], "loot")
        self.handover(city, faction)
        self.prosperity[city] = max(1, self.prosperity[city] - 1)
        self.stats["captured"][faction] += 1
        for o in defenders:                                      # retreat, or fall into captivity
            back = [n for n in neighbors(city) if self.owner[n] == old]
            if back:
                self.officer_city[o] = self.rng.choice(back)
                self.change_loyalty(o, -5)
                continue
            if self.is_leader(o):                          # a ruler is never taken: he flees far or dies
                home = self.nearest_city(city, old)
                if home and home != city and self.rng.random() < 0.5:
                    self.officer_city[o] = home
                    self.squads[o] = []
                    continue
                from .succession import die
                die(self, o, "погиб" + ("ла" if OFFICER[o].female else "") + f" при падении {CITY[city].name}")
                continue
            leader = False
            fate = reign.prisoner_fate(self, faction) if self.cities_of(old) else None
            if fate == "execute":
                from .succession import die
                self.change_relation(faction, old, -10)
                die(self, o, "казнен" + ("а" if OFFICER[o].female else "") + f" по приказу державы {FACTION[faction].short}")
                continue
            if fate == "release":
                self.squads[o] = []
                home = self.nearest_city(city, old)
                if home:
                    self.officer_city[o] = home
                    self.change_relation(faction, old, 5)
                    self.log_event(faction, f"{OFFICER[o].name} отпущен" + ("а" if OFFICER[o].female else "")
                                   + " домой из милости")
                    continue
            feud = old != "goblin" and self.relation(old, faction) <= 14      # blood feud: no oaths
            if not leader and not feud and (self.rng.random() < (100 - self.loyalty[o]) / 100 + 0.15
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

    def seat_councils(self) -> None:
        """Fill every council as the computer would (the campaign itself starts with empty seats)."""
        from .campaign_ai import choose_council
        for f, r in self.realms.items():
            if r.alive:
                self.set_council(f, choose_council(self, f), quiet=True)

    def handover(self, city: str, faction: str) -> None:
        """The city changes hands (storm, event, purchase): what belonged to the old owner's rule goes."""
        old = self.owner[city]
        if old == faction:
            return
        if old == "goblin":
            from .horde import on_city_lost
            on_city_lost(self, city)
        self.owner[city] = faction
        from .order import taken
        taken(self, city)
        if faction == "goblin":
            self.law.pop(city, None)                         # lairs know no order
        for d in (self.sick, self.siege, self.defense, self.muster, self.taxed, self.ravaged):
            d.pop(city, None)
        self.losses.append((self.turn, old, faction, city))

    def settle_officers(self, faction: str) -> None:
        """No officer is left standing in a city his realm does not hold (events, falls, revolts)."""
        for o in self.officers_of(faction):
            city = self.officer_city.get(o.key)
            if city is None or self.owner.get(city) != faction:
                dest = self.nearest_city(city or FACTION[faction].capital, faction) if self.cities_of(faction) else None
                if dest:
                    self.officer_city[o.key] = dest

    def check_fall(self, old: str, faction: str) -> None:
        """A realm without cities falls; its officers go over to the conqueror."""
        if not self.cities_of(old) and old in self.realms and self.realms[old].alive:
            self.realms[old].alive = False
            for d in (self.truce, self.alliance, self.trade):     # treaties die with the realm
                for k in [k for k in d if old in k]:
                    del d[k]
            self.paid.pop(old, None)
            ruler = self.leader.get(old)
            for o in [x.key for x in self.officers_of(old)]:
                self.squads[o] = []
                if o == ruler:
                    self.dead.add(o)                     # the last ruler does not survive his realm
                    self.officer_city.pop(o, None)
                    continue
                self.defect(o, faction)
            self.log_event(faction, f"{FACTION[old].name} пала")
