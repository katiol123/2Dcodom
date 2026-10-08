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


def campaign_squads(b) -> Tuple[List[List[str]], List[List[int]]]:
    """Unit keys and troop ids of both sides of a campaign storm (strongest first, capped); the
    defenders get their town militia (walls and townsfolk) on top."""
    att = sorted(b.att, key=lambda ot: -ot[1].power)[:FIELD_CAP]
    deff = sorted(b.deff, key=lambda ot: -ot[1].power)[:FIELD_CAP]
    keys = [[t.key for _, t in att], [t.key for _, t in deff]]
    tags = [[t.id for _, t in att], [t.id for _, t in deff]]
    for _ in range(min(b.militia, FIELD_CAP + 4 - len(deff))):
        keys[1].append("militia")
        tags[1].append(0)
    if not keys[1]:
        keys[1], tags[1] = ["militia"], [0]
    return keys, tags


def campaign_battle(b, factory: SpriteFactory, progress=None) -> Tuple[World, Dict[str, dict]]:
    """A real battle for a campaign storm: attackers on the left, defenders on the right."""
    keys, tags = campaign_squads(b)
    slots, summons, looks = plan_battle(keys, b.seed % 100000)
    tagged = []
    per_team = {0: iter(tags[0]), 1: iter(tags[1])}
    for s in slots:
        tagged.append(Slot(s.team, s.key, s.look, next(per_team[s.team])))
    metas = factory.ensure(looks, progress)
    anims = {name: anim_infos(meta) for name, meta in metas.items()}
    return World(tagged, anims, b.seed % 100000, summons), metas


def headless_campaign_world(b) -> World:
    """A campaign storm fought headless (seed-0 sprite timings): tests and quick checks."""
    if not _CLASS_ANIMS:
        _CLASS_ANIMS.update({k: anim_infos(m) for k, m in ensure_unit_sheets().items()})
    keys, tags = campaign_squads(b)
    slots = [Slot(team, key, f"{key}_{TEAMS[team].key}", tag) for team in (0, 1)
             for key, tag in zip(keys[team], tags[team])]
    from .assets import SUMMONS
    summons = {(team, k): f"{k}_{TEAMS[team].key}" for team in (0, 1)
               for owner in keys[team] for k in SUMMONS.get(owner, ())}
    return World(slots, _CLASS_ANIMS, b.seed % 100000, summons)


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
