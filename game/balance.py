"""Headless balance report.

    python -m game.balance 40            # classic squad mirror match
    python -m game.balance 300 random    # random 7-unit squads: per-class win rate & output

Win rate of a class = share of battles won by squads containing it (counted once
per unit, so duplicates weigh more).  Battles run in parallel worker processes."""

from __future__ import annotations

import collections
import concurrent.futures as cf
import os
import random
import sys

from .match import headless_world, random_squad
from .units import ALL, CLASSIC, ROSTER


def _battle(args):
    seed, squads = args
    w = headless_world(squads, seed)
    while w.winner is None and w.time < 180:
        w.step(1 / 60)
    units = [(u.key, u.dealt, u.healed, u.kills, u.alive, w.winner == u.team) for u in w.units if not u.summoned]
    return w.winner, (w.end_time if w.winner is not None else w.time), units


def run(n: int, mode: str = "classic") -> None:
    rng = random.Random(1234)
    jobs = [(seed, [CLASSIC, CLASSIC] if mode == "classic" else [random_squad(rng), random_squad(rng)])
            for seed in range(n)]
    with cf.ProcessPoolExecutor(max_workers=min(4, os.cpu_count() or 1)) as pool:
        results = list(pool.map(_battle, jobs, chunksize=4))
    wins = collections.Counter()
    times = []
    stat = collections.defaultdict(lambda: [0, 0.0, 0.0, 0, 0, 0])   # n, dealt, healed, kills, alive, won
    for winner, t, units in results:
        wins[winner] += 1
        times.append(t)
        for key, dealt, healed, kills, alive, won in units:
            st = stat[key]
            st[0] += 1
            st[1] += dealt
            st[2] += healed
            st[3] += kills
            st[4] += alive
            st[5] += won
    print(f"{n} battles ({mode}): blue {wins[0]} / red {wins[1]} / unfinished {wins[None]}, "
          f"length avg {sum(times) / n:.1f}s (min {min(times):.0f}, max {max(times):.0f})")
    print(f"{'unit':20} {'n':>4} {'win%':>5} {'dmg':>5} {'heal':>5} {'kills':>5} {'alive':>5}")
    for k in (CLASSIC if mode == "classic" else [k for k in ALL if not ROSTER[k].boss]):
        c, dealt, healed, kills, alive, won = stat[k]
        c = max(1, c)
        print(f"{ROSTER[k].name:20} {c:4d} {won / c:5.0%} {dealt / c:5.0f} {healed / c:5.0f} "
              f"{kills / c:5.2f} {alive / c:5.0%}")


if __name__ == "__main__":
    run(int(sys.argv[1]) if len(sys.argv) > 1 else 40, sys.argv[2] if len(sys.argv) > 2 else "classic")
