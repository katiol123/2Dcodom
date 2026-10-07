"""Headless balance report.

    python -m game.balance 40            # classic squad mirror match
    python -m game.balance 200 random    # random 7-unit squads: per-class win rate & output

Win rate of a class = share of battles won by squads containing it (counted once
per unit, so duplicates weigh more).  Aim for every class within ~40-60%."""

from __future__ import annotations

import collections
import random
import sys

from .match import headless_world, random_squad
from .units import ALL, CLASSIC, ROSTER


def run(n: int, mode: str = "classic") -> None:
    rng = random.Random(1234)
    wins = collections.Counter()
    times = []
    dealt = collections.Counter()
    healed = collections.Counter()
    kills = collections.Counter()
    alive = collections.Counter()
    count = collections.Counter()
    won = collections.Counter()
    for seed in range(n):
        squads = [CLASSIC, CLASSIC] if mode == "classic" else [random_squad(rng), random_squad(rng)]
        w = headless_world(squads, seed)
        while w.winner is None and w.time < 180:
            w.step(1 / 60)
        wins[w.winner] += 1
        times.append(w.end_time if w.winner is not None else w.time)
        for u in w.units:
            if u.summoned:
                continue
            count[u.key] += 1
            dealt[u.key] += u.dealt
            healed[u.key] += u.healed
            kills[u.key] += u.kills
            alive[u.key] += u.alive
            won[u.key] += (w.winner == u.team)
    print(f"{n} battles ({mode}): blue {wins[0]} / red {wins[1]} / unfinished {wins[None]}, "
          f"length avg {sum(times) / n:.1f}s (min {min(times):.0f}, max {max(times):.0f})")
    print(f"{'unit':12} {'n':>4} {'win%':>5} {'dmg':>5} {'heal':>5} {'kills':>5} {'alive':>5}")
    for k in (CLASSIC if mode == "classic" else ALL):
        c = max(1, count[k])
        print(f"{ROSTER[k].name:12} {count[k]:4d} {won[k] / c:5.0%} {dealt[k] / c:5.0f} {healed[k] / c:5.0f} "
              f"{kills[k] / c:5.2f} {alive[k] / c:5.0%}")


if __name__ == "__main__":
    run(int(sys.argv[1]) if len(sys.argv) > 1 else 40, sys.argv[2] if len(sys.argv) > 2 else "classic")
