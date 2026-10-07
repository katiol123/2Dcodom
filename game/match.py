"""Setting up a battle: plan the looks, make sure their sprites exist, build the World."""

from __future__ import annotations

import random
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from .assets import AnimInfo, Slot, SpriteFactory, anim_infos, ensure_unit_sheets, plan_battle
from .sim import World
from .units import ALL, CLASSIC, SQUAD_MAX, TEAMS


def new_battle(squads: Sequence[Sequence[str]], seed: int, factory: SpriteFactory,
               progress: Optional[Callable[[str, int, int], None]] = None) -> Tuple[World, Dict[str, dict]]:
    """Full battle with a unique seeded look for every unit."""
    slots, summons, looks = plan_battle(squads, seed)
    metas = factory.ensure(looks, progress)
    anims = {name: anim_infos(meta) for name, meta in metas.items()}
    return World(slots, anims, seed, summons), metas


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
    summons = {team: f"skeleton_{TEAMS[team].key}" for team, squad in enumerate(squads) if "necromancer" in squad}
    return World(slots, _CLASS_ANIMS, seed, summons)


def random_squad(rng: random.Random, size: int = SQUAD_MAX) -> List[str]:
    return [rng.choice(ALL) for _ in range(size)]
