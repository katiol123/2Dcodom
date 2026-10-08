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
from .factions import ALL_FACTIONS, FACTION
from .officers import OFFICER


def one_game(args) -> Dict:
    seed, rounds, fixed = args[:3]
    force = args[3] if len(args) > 3 else None          # (event key or "", round) for events mode
    c = Campaign(None, seed=seed)
    if force is not None:
        c.no_events = True
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
    snap = None
    while c.turn <= rounds:
        if force is not None and c.turn >= force[1] and snap is None:
            snap = {f: (len(c.cities_of(f)), c.army(f), c.gold[f]) for f in c.order}
            if force[0]:
                from .events import fire
                fire(c, force[0])
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
    from .diplomacy import standing
    return {
        "snap": snap, "standing": {f: standing(c, f) for f in c.order},
        "army_end": {f: c.army(f) for f in c.order},
        "diplomacy": c.stats["diplomacy"], "hegemon": c.stats["hegemon"], "events": c.stats["events"],
        "alliances": len(c.alliance), "growth": growth, "levels": c.stats["levels"], "declines": c.stats["declines"],
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
    dip, heg, ev = Counter(), Counter(), Counter()
    for r in results:
        dip.update(r["diplomacy"])
        heg.update(r["hegemon"])
        ev.update(r["events"])
    out.append("ДИПЛОМАТИЯ за кампанию: " + ", ".join(f"{k} {v / n:.1f}" for k, v in sorted(dip.items()))
               + f"; союзов в конце {sum(r['alliances'] for r in results) / n:.1f}")
    out.append("ГЕГЕМОН (ходов): " + ", ".join(f"{FACTION[k].short} {v / n:.1f}" for k, v in heg.most_common()))
    out.append(f"СОБЫТИЯ МИРА: {sum(ev.values()) / n:.2f} за кампанию: " +
               ", ".join(f"{k} {v / n:.2f}" for k, v in ev.most_common()))
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


def events_impact(games: int = 40, at: int = 15, after: int = 12) -> str:
    """Every event forced at round ``at`` against the same seeds without it: how the realms differ
    ``after`` rounds later (cities, army, standing)."""
    from .events import EVENTS
    keys = [""] + [e.key for e in EVENTS]
    jobs = [(seed, at + after, "", (k, at)) for k in keys for seed in range(1, games + 1)]
    with Pool() as pool:
        res = pool.map(one_game, jobs)
    by = {k: res[i * games:(i + 1) * games] for i, k in enumerate(keys)}
    base = by[""]
    out = [f"влияние событий: {games} кампаний, событие на ходу {at}, сравнение через {after} ходов", "",
           f"{'СОБЫТИЕ':16s} {'ГОР.МАКС.СДВИГ':>14s} {'АРМИЯ ВСЕГО':>11s} {'ЛИДЕР ГОР.':>10s} {'СЛАБЫЕ ГОР.':>11s} "
           f"{'РАЗБРОС':>8s} {'ПАЛО':>5s}"]

    def summary(rows):
        cities = {f: sum(r["cities"][f] for r in rows) / len(rows) for f in rows[0]["cities"]}
        army = sum(sum(r["army_end"].values()) for r in rows) / len(rows)
        lead = weak = 0.0
        spread = 0.0
        for r in rows:                                   # the realms that led / trailed at the event
            order = sorted((f for f in r["snap"] if f != "goblin"), key=lambda f: -r["snap"][f][0])
            lead += sum(r["cities"][f] for f in order[:2]) / 2
            weak += sum(r["cities"][f] for f in order[-3:]) / 3
            vals = [r["cities"][f] for f in order]
            m = sum(vals) / len(vals)
            spread += (sum((v - m) ** 2 for v in vals) / len(vals)) ** 0.5
        dead = sum(1 for r in rows for f, a in r["alive"].items() if not a and f != "goblin")
        return cities, army, lead / len(rows), weak / len(rows), spread / len(rows), dead / len(rows)

    c0, a0, l0, w0, s0, d0 = summary(base)
    out.append(f"{'(без события)':16s} {'':>14s} {a0:11.0f} {l0:10.2f} {w0:11.2f} {s0:8.2f} {d0:5.2f}")
    for k in keys[1:]:
        c1, a1, l1, w1, s1, d1 = summary(by[k])
        shift = max(c1, key=lambda f: abs(c1[f] - c0[f]))
        out.append(f"{k:16s} {FACTION[shift].short[:8]:>8s} {c1[shift] - c0[shift]:+5.2f} {a1 / a0 - 1:+11.0%} "
                   f"{l1 - l0:+10.2f} {w1 - w0:+11.2f} {s1 - s0:+8.2f} {d1 - d0:+5.2f}")
    return "\n".join(out)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "events":
        print(events_impact(int(sys.argv[2]) if len(sys.argv) > 2 else 40))
        sys.exit()
    games = int(sys.argv[1]) if len(sys.argv) > 1 else 40
    rounds = int(sys.argv[2]) if len(sys.argv) > 2 else 40
    fixed = sys.argv[3] if len(sys.argv) > 3 else ""     # e.g. "war": every realm stays on that course
    print(run(games, rounds, fixed=fixed))
