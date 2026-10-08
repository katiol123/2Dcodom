"""Card balance: whole campaigns played by the computer, with statistics.

    python -m game.cardsim [games] [rounds]

Every realm is played by the AI for ``rounds`` rounds, ``games`` times with different seeds.
The report shows, per realm: cities held at the end, how often it was wiped out, income and
army; per card: how often it is played when drawn (a card that is drawn and never played is
dead weight, a card played every time is a must-have), and the economy as a whole.
"""

from __future__ import annotations

import sys
from collections import Counter, defaultdict
from multiprocessing import Pool
from typing import Dict

from .campaign import Campaign
from .cards import CARDS, TIER_NAMES
from .factions import ALL_FACTIONS


def one_game(args) -> Dict:
    seed, rounds = args
    c = Campaign(None, seed=seed)
    curve = defaultdict(list)
    deserted = Counter()
    while c.turn <= rounds:
        c.run_ai(stop_at_player=False, max_turns=1)
        for f in c.order:
            curve[f].append(len(c.cities_of(f)))
    for t, f, text in c.log:
        if text.startswith("Казна пуста"):
            deserted[f] += 1
    battles = sum(1 for t, f, text in c.log if text.startswith(("ШТУРМ", "МОЛНИЕНОСНЫЙ", "ДРАККАРЫ")))
    wins = sum(1 for t, f, text in c.log if text.startswith(("ШТУРМ", "МОЛНИЕНОСНЫЙ", "ДРАККАРЫ"))
               and "взят" in text)
    return {
        "cities": {f: len(c.cities_of(f)) for f in c.order},
        "alive": {f: c.realms[f].alive for f in c.order},
        "army": {f: c.army(f) for f in c.order},
        "gold": {f: c.gold[f] for f in c.order},
        "prosperity": {f: (sum(c.prosperity[x] for x in c.cities_of(f)) / max(1, len(c.cities_of(f))))
                       for f in c.order},
        "played": c.stats["played"], "drawn": c.stats["drawn"], "income": c.stats["gold"],
        "deserted": deserted, "earned": c.stats["earned"], "paid": c.stats["paid"], "battles": battles, "wins": wins, "mid": {f: v[len(v) // 2] for f, v in curve.items()},
    }


def run(games: int = 40, rounds: int = 40, procs: int = 0) -> str:
    args = [(seed, rounds) for seed in range(1, games + 1)]
    if procs == 1:
        results = [one_game(a) for a in args]
    else:
        with Pool(procs or None) as pool:
            results = pool.map(one_game, args)
    out = [f"{games} кампаний по {rounds} ходов", ""]
    out.append(f"{'ДЕРЖАВА':12s} {'ГОР.СЕРЕД':>9s} {'ГОР.КОНЕЦ':>9s} {'ПАЛА':>5s} {'АРМИЯ':>6s} {'ЗОЛОТО':>6s} "
               f"{'ПРОЦВ':>5s} {'БЕГСТВО':>7s} {'ДОХОД/ХОД':>9s} {'ЖАЛОВ/ХОД':>9s}")
    for fac in ALL_FACTIONS:
        f = fac.key
        n = len(results)
        mid = sum(r["mid"][f] for r in results) / n
        end = sum(r["cities"][f] for r in results) / n
        dead = sum(1 for r in results if not r["alive"][f]) / n
        army = sum(r["army"][f] for r in results) / n
        gold = sum(r["gold"][f] for r in results) / n
        pros = sum(r["prosperity"][f] for r in results) / n
        des = sum(r["deserted"][f] for r in results) / n
        inc = sum(r["earned"][f] for r in results) / n / rounds
        paid = sum(r["paid"][f] for r in results) / n / rounds
        out.append(f"{fac.short:12s} {mid:9.1f} {end:9.1f} {dead:5.0%} {army:6.0f} {gold:6.0f} {pros:5.1f} {des:7.1f}"
                   f" {inc:9.0f} {paid:9.0f}")
    played, drawn, income = Counter(), Counter(), Counter()
    for r in results:
        played.update(r["played"])
        drawn.update(r["drawn"])
        income.update(r["income"])
    battles = sum(r["battles"] for r in results)
    wins = sum(r["wins"] for r in results)
    out += ["", f"штурмов за кампанию: {battles / len(results):.1f}, удачных {wins / max(1, battles):.0%}",
            "доход за кампанию (все державы): " + ", ".join(f"{k} {v / len(results):.0f}"
                                                         for k, v in income.most_common()), ""]
    out.append(f"{'КАРТА':24s} {'УРОВЕНЬ':12s} {'ВЫТЯН':>6s} {'СЫГР':>6s} {'ДОЛЯ':>5s}")
    for key, card in sorted(CARDS.items(), key=lambda kv: (kv[1].tier, -played[kv[0]])):
        d = drawn[key] / len(results)
        p = played[key] / len(results)
        if d == 0 and p == 0:
            out.append(f"{card.name:24s} {TIER_NAMES[card.tier]:12s} {'-':>6s}")
            continue
        out.append(f"{card.name:24s} {TIER_NAMES[card.tier]:12s} {d:6.1f} {p:6.1f} {p / max(d, 0.01):5.0%}")
    return "\n".join(out)


if __name__ == "__main__":
    games = int(sys.argv[1]) if len(sys.argv) > 1 else 40
    rounds = int(sys.argv[2]) if len(sys.argv) > 2 else 40
    print(run(games, rounds))
