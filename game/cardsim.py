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
from .officers import OFFICER


def one_game(args) -> Dict:
    seed, rounds, fixed = args
    c = Campaign(None, seed=seed)
    if fixed:                                    # every realm locked on one course (to compare courses)
        import game.campaign_ai as ai
        ai.pick_course = lambda camp, f: None
        for f in c.order:
            c.current = c.order.index(f)
            c.realms[f].course_cd = 0
            c.change_course(f, fixed) if fixed != "balance" else None
        c.current = 0
        c.log = []
    curve = defaultdict(list)
    deserted = Counter()
    first_council = {o for f in c.order for o in c.realms[f].council}
    ever_council = set(first_council)
    while c.turn <= rounds:
        c.run_ai(stop_at_player=False, max_turns=1)
        for f in c.order:
            curve[f].append(len(c.cities_of(f)))
            ever_council.update(c.realms[f].council)
    for t, f, text in c.log:
        if text.startswith("Казна пуста"):
            deserted[f] += 1
    battles = sum(1 for t, f, text in c.log if text.startswith(("ШТУРМ", "МОЛНИЕНОСНЫЙ", "ДРАККАРЫ")))
    wins = sum(1 for t, f, text in c.log if text.startswith(("ШТУРМ", "МОЛНИЕНОСНЫЙ", "ДРАККАРЫ"))
               and "взят" in text)
    # how officers changed, by their starting calibre (quintiles of presence among non-leaders)
    from .faces import presence
    offs = sorted((o for o in OFFICER.values() if o.rank), key=presence)
    growth = []
    for i, o in enumerate(offs):
        q = i * 5 // len(offs)
        delta = sum(c.ostats[o.key]) - sum(o.stats)
        growth.append((q, delta, c.level[o.key], c.olead[o.key] - o.leadership,
                       o.key in ever_council and o.key not in first_council))
    return {
        "growth": growth, "levels": c.stats["levels"], "declines": c.stats["declines"],
        "feats": c.stats["feats"], "turncoats": c.stats["deserted_officers"], "reshuffles": c.stats["reshuffles"],
        "cities": {f: len(c.cities_of(f)) for f in c.order},
        "alive": {f: c.realms[f].alive for f in c.order},
        "army": {f: c.army(f) for f in c.order},
        "gold": {f: c.gold[f] for f in c.order},
        "prosperity": {f: (sum(c.prosperity[x] for x in c.cities_of(f)) / max(1, len(c.cities_of(f))))
                       for f in c.order},
        "played": c.stats["played"], "drawn": c.stats["drawn"], "income": c.stats["gold"],
        "deserted": deserted, "earned": c.stats["earned"], "paid": c.stats["paid"], "courses": c.stats["courses"], "battles": battles, "wins": wins, "mid": {f: v[len(v) // 2] for f, v in curve.items()},
    }


def run(games: int = 40, rounds: int = 40, procs: int = 0, fixed: str = "") -> str:
    args = [(seed, rounds, fixed) for seed in range(1, games + 1)]
    if procs == 1:
        results = [one_game(a) for a in args]
    else:
        with Pool(procs or None) as pool:
            results = pool.map(one_game, args)
    out = [f"{games} кампаний по {rounds} ходов" + (f", все на курсе {fixed}" if fixed else ""), ""]
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
    courses = Counter()
    for r in results:
        courses.update(r["courses"])
    out += ["", "КУРСЫ (доля ходов): " + ", ".join(
        f"{fac.short} " + "/".join(f"{k[:3]} {courses[f'{fac.key}:{k}'] / max(1, sum(v for kk, v in courses.items() if kk.startswith(fac.key + ':'))):.0%}"
                                  for k in ("balance", "war", "economy", "defense", "intrigue")
                                  if courses[f"{fac.key}:{k}"]) for fac in ALL_FACTIONS)]
    n = len(results)
    out += ["", "ОФИЦЕРЫ ЗА КАМПАНИЮ: уровней " + ", ".join(
        f"{fac.short} {sum(r['levels'][fac.key] for r in results) / n:.0f}" for fac in ALL_FACTIONS),
        "  падений навыка " + ", ".join(f"{fac.short} {sum(r['declines'][fac.key] for r in results) / n:.1f}"
                                        for fac in ALL_FACTIONS),
        "  измен (ушли сами) " + ", ".join(f"{fac.short} {sum(r['turncoats'][fac.key] for r in results) / n:.2f}"
                                          for fac in ALL_FACTIONS),
        "  перестановок совета " + ", ".join(f"{fac.short} {sum(r['reshuffles'][fac.key] for r in results) / n:.1f}"
                                            for fac in ALL_FACTIONS)]
    out.append(f"{'КАЛИБР (квинтиль)':18s} {'НАВЫКИ +-':>9s} {'УРОВЕНЬ':>7s} {'ЛИДЕРСТВО':>9s} {'УПАЛИ':>6s} "
               f"{'ВЫРОСЛИ 5+':>10s} {'ВОШЛИ В СОВЕТ':>13s}")
    for q, label in enumerate(("слабейшие", "слабые", "средние", "сильные", "сильнейшие")):
        rows = [g for r in results for g in r["growth"] if g[0] == q]
        k = max(1, len(rows))
        out.append(f"{label:18s} {sum(g[1] for g in rows) / k:+9.2f} {sum(g[2] for g in rows) / k:7.2f} "
                   f"{sum(g[3] for g in rows) / k:+9.1f} {sum(g[1] < 0 for g in rows) / k:6.1%} "
                   f"{sum(g[1] >= 5 for g in rows) / k:10.1%} {sum(g[4] for g in rows) / k:13.1%}")
    feats = Counter()
    for r in results:
        feats.update(r["feats"])
    out.append("ПОДВИГИ (доля кампаний): " + ", ".join(f"{CARDS[k].name} {feats[k] / n:.0%}" for k in
                                                       [k for k, c in CARDS.items() if c.tier == "feat"]))
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
    fixed = sys.argv[3] if len(sys.argv) > 3 else ""     # e.g. "war": every realm stays on that course
    print(run(games, rounds, fixed=fixed))
