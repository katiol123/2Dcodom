"""Setting up a battle: plan the looks, make sure their sprites exist, build the World."""

from __future__ import annotations

import random
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from .assets import AnimInfo, Slot, SpriteFactory, anim_infos, ensure_unit_sheets, plan_battle
from .sim import World
from .units import ALL, CLASSIC, ROSTER, SQUAD_MAX, TEAMS


def new_battle(squads: Sequence[Sequence[str]], seed: int, factory: SpriteFactory,
               progress: Optional[Callable[[str, int, int], None]] = None) -> Tuple[World, Dict[str, dict]]:
    """Full battle with a unique seeded look for every unit."""
    slots, summons, looks = plan_battle(squads, seed)
    metas = factory.ensure(looks, progress)
    anims = {name: anim_infos(meta) for name, meta in metas.items()}
    return World(slots, anims, seed, summons), metas


FIELD_CAP = 18                  # units per side on the field in a campaign storm


MAX_BANDS = 3                   # squads a side fights in, each in its own (invisible) strip of the field
                                # (the allies' detachments come on top as a strip of their own)


def campaign_squads(b) -> Tuple[List[List[str]], List[List[int]], List[List[int]]]:
    """Unit keys, troop ids and squad bands of both sides of a campaign storm (strongest first, capped);
    the defenders get their town militia (walls and townsfolk) on top. A band is one officer's squad
    (the garrison and the town militia are one more, the allies' detachments another); a side keeps at
    most ``MAX_BANDS`` of them, the smallest ones merged into the rest."""
    att = sorted(b.att, key=lambda ot: -ot[1].power)[:FIELD_CAP]
    deff = sorted(b.deff, key=lambda ot: -ot[1].power)[:FIELD_CAP]
    keys = [[t.key for _, t in att], [t.key for _, t in deff]]
    tags = [[t.id for _, t in att], [t.id for _, t in deff]]
    owners = [[o or "garrison" for o, _ in att], [o or "garrison" for o, _ in deff]]
    for side, aux in enumerate(getattr(b, "aux", ([], []))):   # allies' detachments (not at risk)
        for k in aux[:max(0, FIELD_CAP + 2 - len(keys[side]))]:
            keys[side].append(k)
            tags[side].append(0)
            owners[side].append("allies")
    for _ in range(min(b.militia, FIELD_CAP + 4 - len(deff))):
        keys[1].append("militia")
        tags[1].append(0)
        owners[1].append("garrison")
    if not keys[1]:
        keys[1], tags[1], owners[1] = ["militia"], [0], ["garrison"]
    return keys, tags, [_bands(side) for side in owners]


ALLIES = "allies"


def _bands(owners: List[str]) -> List[int]:
    """Squad -> band number (0..MAX_BANDS-1), the biggest squads first; the rest join the smallest bands."""
    sizes: Dict[str, int] = {}
    for o in owners:
        sizes[o] = sizes.get(o, 0) + 1
    allied = sizes.pop("allies", 0)
    order = sorted(sizes, key=lambda o: (-sizes[o], o))
    band = {o: i for i, o in enumerate(order[:MAX_BANDS])}
    load = [sizes[o] for o in order[:MAX_BANDS]]
    for o in order[MAX_BANDS:]:
        i = min(range(len(load)), key=lambda j: load[j])
        band[o] = i
        load[i] += sizes[o]
    if allied:
        band["allies"] = len(load)                   # the allies hold a strip of their own (the 4th at most)
    return [band[o] for o in owners]


def campaign_battle(b, factory: SpriteFactory, progress=None) -> Tuple[World, Dict[str, dict]]:
    """A real battle for a campaign storm: attackers on the left, defenders on the right."""
    keys, tags, bands = campaign_squads(b)
    tombs = getattr(b, "tombs", False)
    slots, summons, looks = plan_battle(keys, b.seed % 100000, {1: ["skeleton"]} if tombs else None)
    tagged = []
    per_team = {0: iter(zip(tags[0], bands[0])), 1: iter(zip(tags[1], bands[1]))}
    for s in slots:
        tag, band = next(per_team[s.team])
        tagged.append(Slot(s.team, s.key, s.look, tag, band))
    metas = factory.ensure(looks, progress)
    anims = {name: anim_infos(meta) for name, meta in metas.items()}
    world = World(tagged, anims, b.seed % 100000, summons, towers=[1] * getattr(b, "towers", 0),
                  fury=getattr(b, "fury", (1.0, 1.0)), chill=getattr(b, "chill", (1.0, 1.0)),
                  frost=getattr(b, "frost", False), hardy=getattr(b, "hardy", (False, False)),
                  wrath=getattr(b, "wrath", None), tombs=1 if tombs else None)
    from .factions import FACTION
    world.names = (FACTION[b.attacker].short, FACTION[b.defender].short)   # the realms, not the colours
    return world, metas


def headless_campaign_world(b) -> World:
    """A campaign storm fought headless (seed-0 sprite timings): tests and quick checks."""
    if not _CLASS_ANIMS:
        _CLASS_ANIMS.update({k: anim_infos(m) for k, m in ensure_unit_sheets().items()})
    keys, tags, bands = campaign_squads(b)
    slots = [Slot(team, key, f"{key}_{TEAMS[team].key}", tag, band) for team in (0, 1)
             for key, tag, band in zip(keys[team], tags[team], bands[team])]
    from .assets import SUMMONS
    summons = {(team, k): f"{k}_{TEAMS[team].key}" for team in (0, 1)
               for owner in keys[team] for k in SUMMONS.get(owner, ())}
    tombs = getattr(b, "tombs", False)
    if tombs:
        summons[(1, "skeleton")] = f"skeleton_{TEAMS[1].key}"
    return World(slots, _CLASS_ANIMS, b.seed % 100000, summons, towers=[1] * getattr(b, "towers", 0),
                 fury=getattr(b, "fury", (1.0, 1.0)), chill=getattr(b, "chill", (1.0, 1.0)),
                 frost=getattr(b, "frost", False), hardy=getattr(b, "hardy", (False, False)),
                 wrath=getattr(b, "wrath", None), tombs=1 if tombs else None)


def battle_outcome(world: World, b, rng: random.Random) -> None:
    """Write the result of a fought campaign battle into ``b`` (who won, which troops fell).
    Troops that did not fit on the field share their side's fate: the losers' mostly fall."""
    b.att_won = world.winner == 0
    fielded = {u.tag for u in world.units if u.tag}
    b.fallen = {u.tag for u in world.units if u.tag and not u.alive}
    for side, troops in ((0, b.att), (1, b.deff)):
        lost = (world.winner != side)
        for _, t in troops:
            if t.id not in fielded and lost and rng.random() < 0.75:
                b.fallen.add(t.id)


def prefetch(squads: Sequence[Sequence[str]], seed: int, factory: SpriteFactory) -> None:
    """Start drawing the sprites of a future battle in the background."""
    factory.prefetch(plan_battle(squads, seed)[2])


_CLASS_ANIMS: Dict[str, Dict[str, AnimInfo]] = {}


def headless_world(squads: Sequence[Sequence[str]], seed: int) -> World:
    """Same rules, but every unit of a class shares the seed-0 sprite timings
    (looks do not change animation timing) - fast for tests and balance runs."""
    if not _CLASS_ANIMS:
        _CLASS_ANIMS.update({k: anim_infos(m) for k, m in ensure_unit_sheets().items()})
    slots = [Slot(team, key, f"{key}_{TEAMS[team].key}") for team, squad in enumerate(squads) for key in squad]
    from .assets import SUMMONS
    summons = {(team, k): f"{k}_{TEAMS[team].key}" for team, squad in enumerate(squads)
               for owner in squad for k in SUMMONS.get(owner, ())}
    return World(slots, _CLASS_ANIMS, seed, summons)


def random_squad(rng: random.Random, size: int = SQUAD_MAX) -> List[str]:
    """Random line-up of regular classes (bosses are only picked by hand)."""
    pool = [k for k in ALL if not ROSTER[k].boss]
    return [rng.choice(pool) for _ in range(size)]
