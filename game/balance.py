"""Headless balance report: ``python -m game.balance [battles]``.

Runs many seeded battles without graphics and prints win rates, fight
length and per-unit damage / kills / survival - use it after changing stats."""

from __future__ import annotations

import collections
import sys

from .assets import anim_infos, ensure_unit_sheets
from .sim import World
from .units import ORDER, ROSTER


def main(n: int = 40) -> None:
    anims = {k: anim_infos(m) for k, m in ensure_unit_sheets().items()}
    wins = collections.Counter()
    times = []
    dealt = collections.Counter()
    kills = collections.Counter()
    alive = collections.Counter()
    for seed in range(n):
        w = World(anims, seed)
        while w.winner is None and w.time < 180:
            w.step(1 / 60)
        wins[w.winner] += 1
        times.append(w.end_time)
        for u in w.units:
            dealt[u.key] += u.dealt
            kills[u.key] += u.kills
            alive[u.key] += u.alive
    print(f"{n} battles: blue {wins[0]} / red {wins[1]} / draw {wins[None]}, "
          f"length avg {sum(times) / n:.1f}s (min {min(times):.0f}, max {max(times):.0f})")
    print(f"{'unit':10} {'dmg/battle':>10} {'kills':>6} {'survived':>9}")
    for k in ORDER:
        print(f"{ROSTER[k].name:10} {dealt[k] / n / 2:10.0f} {kills[k] / n / 2:6.2f} {alive[k] / n / 2:9.0%}")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 40)
