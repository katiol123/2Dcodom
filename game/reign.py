"""Reign types (pure Python, no pygame): how a ruler governs when the computer plays his realm.

Every officer has a reign type (``reign_of``) - a name such as ТИРАН made of three behaviour
traits (``TRAITS``, 37 of them, in 33 types; ``GOBLIN_ONLY`` types only for goblins, ``HUMAN_ONLY`` only for people). It only matters - and is only shown - while he rules a realm that
the computer plays: the player's own ruler governs as the player does, and officers who do not
rule keep their type hidden. A new ruler brings his own way of governing (succession.py).

The type follows the officer's skills (a schemer with high ИНТРИГА, a builder with high
УПРАВЛЕНИЕ, a warlord with high ВЕРБОВКА...) with a seeded touch of chance; the first rulers of the
realms have a type that suits their lore (``LEADER_REIGN``). Traits act through the helpers below,
used by campaign_ai.py, diplomacy.py, growth.py and campaign.py.
"""

from __future__ import annotations

import random
from functools import lru_cache
from typing import Dict, List, Optional, Tuple

from .officers import OFFICER

# key: (name, short description)
TRAITS: Dict[str, Tuple[str, str]] = {
    "aggressive": ("АГРЕССИВНЫЙ", "военные карты ценит на 30% выше"),
    "cautious": ("ОСТОРОЖНЫЙ", "штурмует только при шансе 65% и выше"),
    "reckless": ("БЕЗРАССУДНЫЙ", "идёт на штурм уже при шансе 45%"),
    "cruel": ("ЖЕСТОКИЙ", "пленных офицеров обычно казнит"),
    "merciful": ("МИЛОСЕРДНЫЙ", "пленных почти всегда отпускает домой (а держава отпущенного благодарна, +5)"),
    "greedy": ("АЛЧНЫЙ", "карты хозяйства ценит на 30% выше, тянется к курсу хозяйства"),
    "paranoid": ("ПОДОЗРИТЕЛЬНЫЙ", "защиту от интриг ценит вдвое"),
    "schemer": ("ИНТРИГАН", "карты интриги ценит на 40% выше, тянется к тайной политике"),
    "diplomat": ("ДИПЛОМАТ", "шлёт послов с миром и союзом даже ради малой выгоды"),
    "warmonger": ("ВОИНСТВЕННЫЙ", "мира не просит и неохотно его принимает (-15)"),
    "treacherous": ("ВЕРОЛОМНЫЙ", "рвёт перемирия и даже союзы, едва сосед становится лёгкой добычей: "
                                  "чем вернее штурм, тем скорее удар"),
    "builder": ("СТРОИТЕЛЬ", "процветание городов ценит на 40% выше, бережёт их от поборов"),
    "defender": ("ОБОРОНЕЦ", "карты обороны ценит на 40% выше, тянется к курсу обороны"),
    "conqueror": ("ЗАВОЕВАТЕЛЬ", "вражеские города ценит на 25% выше, тянется к курсу войны"),
    "miser": ("СКРЯГА", "держит в казне запас на 3 хода содержания, нанимает меньше"),
    "recruiter": ("ВЕРБОВЩИК", "найм и сбор войск ценит на 40% выше"),
    "trader": ("ТОРГОВЕЦ", "предлагает торговлю даже ради малой выгоды и охотнее её принимает (+10)"),
    "brave": ("ХРАБРЫЙ", "сам ведёт войска в бой уже при шансе 65%"),
    "careful_self": ("БЕРЕЖЁТ СЕБЯ", "не покидает своего города (в бой - лишь в безвыходном положении) и "
                                     "держит при себе сильнейших воинов как личную гвардию"),
    "nepotist": ("КУМОВСТВО", "в совет сажает самых верных, а не самых способных"),
    "meritocrat": ("МЕРИТОКРАТ", "в совет сажает самых способных и пересматривает его вдвое чаще"),
    "vengeful": ("МСТИТЕЛЬНЫЙ", "обидчика (штурмовавшего его города) бьёт и при меньших шансах, стягивает войска "
                               "к его границе и мира с ним не заключает"),
    "vulture": ("СТЕРВЯТНИК", "добивает ослабленных (смута, потерянные города): рвёт с ними перемирие и "
                             "штурмует их при меньших шансах"),
    "pious": ("НАБОЖНЫЙ", "подлых интриг избегает (-50%), охотно строит храмы"),
    "traditionalist": ("ТРАДИЦИОНАЛИСТ", "меняет курс державы лишь при большой выгоде"),
    "ambitious": ("ЧЕСТОЛЮБИВЫЙ", "союзов не ищет, метит в сильнейших (+30% к штурмам их городов)"),
    "isolationist": ("ЗАТВОРНИК", "карты дипломатии ценит вдвое ниже и почти не придерживает их в руке"),
    "courtly": ("ЛЮБИТЕЛЬ ЦЕРЕМОНИЙ", "карты дипломатии ценит на 40% выше и охотно придерживает до удобного часа"),
    "chancellor": ("КАНЦЛЕР", "карты совета ценит на 40% выше и придерживает их"),
    "rover": ("НЕУТОМИМЫЙ", "карты походов ценит на 50% выше: его войска не засиживаются на месте"),
    "attentive": ("ЧУТКИЙ", "охотнее разыгрывает карты советников, чья верность низка: так он их задабривает, "
                           "даже ценой менее выгодного хода"),
    "admirer": ("ПОЧИТАТЕЛЬ СИЛЫ", "гегемона не боится, а уважает: отношения с ним растут, его послов принимает "
                                  "охотно, нападать на него не рвётся"),
    "honorable": ("БЛАГОРОДНЫЙ", "карт интриги почти не разыгрывает: подлость ему претит (защита от интриг - "
                                "не в счёт)"),
    "fist": ("ЖЕЛЕЗНЫЙ КУЛАК", "стягивает отряды к самой опасной границе, оставляя в тылу лишь полгарнизона"),
    # the horde
    "hunter": ("ГРОЗА ГОБЛИНОВ", "логова штурмует охотнее (+50%), от орды не откупается"),
    "appeaser": ("ДАННИК ОРДЫ", "откуп от орды ценит вдвое: лучше платить, чем воевать с гоблинами"),
    "hoarder": ("ЖАДНЫЙ ДО БЛЕСТЯШЕК", "вождь орды: копит всё золото на великую постройку"),
}
GOBLIN_ONLY = {"warchief", "hoard_king"}          # reign types only goblins have
HUMAN_ONLY = {"slayer", "tributary", "hermit", "peacemaker", "usurper"}   # ... and only people (the horde has no envoys)

# key: (name, traits)
REIGNS: Dict[str, Tuple[str, Tuple[str, str, str]]] = {
    "tyrant": ("ТИРАН", ("cruel", "aggressive", "paranoid")),
    "conqueror": ("ЗАВОЕВАТЕЛЬ", ("conqueror", "brave", "recruiter")),
    "sage": ("МУДРЕЦ", ("cautious", "builder", "diplomat")),
    "merchant": ("ТОРГОВЫЙ КНЯЗЬ", ("greedy", "trader", "miser")),
    "schemer": ("ИНТРИГАН", ("schemer", "treacherous", "vulture")),
    "noble": ("БЛАГОРОДНЫЙ ВОЖДЬ", ("honorable", "brave", "merciful")),
    "keeper": ("ХРАНИТЕЛЬ", ("defender", "traditionalist", "careful_self")),
    "reformer": ("РЕФОРМАТОР", ("attentive", "meritocrat", "builder")),
    "avenger": ("МСТИТЕЛЬ", ("vengeful", "reckless", "warmonger")),
    "patron": ("ПОКРОВИТЕЛЬ", ("merciful", "pious", "nepotist")),
    "despot": ("ВЛАСТОЛЮБЕЦ", ("ambitious", "vulture", "aggressive")),
    "strategist": ("СТРАТЕГ", ("vulture", "careful_self", "fist")),
    "warlord": ("ПОЛКОВОДЕЦ", ("aggressive", "brave", "fist")),
    "raider": ("ЗАХВАТЧИК", ("conqueror", "reckless", "fist")),
    "autocrat": ("ДЕСПОТ", ("cruel", "paranoid", "nepotist")),
    "envoy": ("КУПЕЦ-ДИПЛОМАТ", ("trader", "diplomat", "admirer")),
    "architect": ("ЗОДЧИЙ ДЕРЖАВЫ", ("builder", "defender", "miser")),
    "zealot": ("РЕВНИТЕЛЬ ВЕРЫ", ("pious", "vengeful", "aggressive")),
    "shadow": ("ТЕНЕВОЙ ПРАВИТЕЛЬ", ("schemer", "paranoid", "careful_self")),
    "crusader": ("КРЕСТОНОСЕЦ", ("honorable", "conqueror", "brave")),
    "miserly": ("СКУПОЙ ВЛАДЫКА", ("miser", "traditionalist", "cautious")),
    "upstart": ("ВЫСКОЧКА", ("ambitious", "reckless", "meritocrat")),
    "benefactor": ("ОТЕЦ НАРОДА", ("diplomat", "builder", "merciful")),
    "mercenary": ("НАЁМНЫЙ КНЯЗЬ", ("greedy", "treacherous", "admirer")),
    "hermit": ("ОТШЕЛЬНИК НА ТРОНЕ", ("isolationist", "defender", "miser")),
    "peacemaker": ("МИРОТВОРЕЦ", ("courtly", "diplomat", "merciful")),
    "chancellor": ("ВЕЛИКИЙ КАНЦЛЕР", ("chancellor", "attentive", "builder")),
    "nomad": ("КОЧЕВОЙ ВОЖДЬ", ("rover", "reckless", "recruiter")),
    "slayer": ("ИСТРЕБИТЕЛЬ ОРД", ("hunter", "brave", "conqueror")),
    "tributary": ("ОТКУПЩИК", ("appeaser", "cautious", "trader")),
    "usurper": ("КОВАРНЫЙ УЗУРПАТОР", ("treacherous", "ambitious", "aggressive")),
    "warchief": ("ВЕЛИКИЙ ВОЖАК", ("hoarder", "aggressive", "reckless")),
    "hoard_king": ("КОРОЛЬ КУЧИ", ("hoarder", "greedy", "cruel")),
}

# which skills make each reign likely (weights over STATS order: УПР, ВЕРБ, ЛОГ, РАЗВ, ДИП, ИНТР)
_LEAN: Dict[str, Tuple[float, ...]] = {
    "tyrant": (0, 0.5, 0, 0, -1, 1.2),
    "conqueror": (0, 1.2, 0.8, 0, -0.3, 0),
    "sage": (0.8, 0, 0, 0, 1.2, -0.3),
    "merchant": (1.3, -0.5, 0.3, 0, 0.4, 0),
    "schemer": (0, 0, 0, 0.8, 0, 1.4),
    "noble": (0, 0.3, 0.6, 0, 1.0, -1),
    "keeper": (0.3, 0, 1.0, 0.8, 0, 0),
    "reformer": (1.1, 0, 0, 0.7, 0, 0),
    "avenger": (0, 1.0, 0, 0, -1.2, 0.3),
    "patron": (0.4, 0, 0, 0, 1.0, 0),
    "despot": (0.3, 0.7, 0, 0, -0.4, 0.7),
    "strategist": (0, 0, 0.6, 1.2, 0, 0.3),
    "warlord": (0, 1.1, 0.6, 0.3, -0.3, 0),
    "raider": (0, 0.9, 0.5, 0, -0.8, 0.4),
    "autocrat": (0.4, 0, 0, 0, -0.8, 1.1),
    "envoy": (0.5, 0, 0, 0, 1.2, 0.3),
    "architect": (1.2, 0, 0.6, 0, 0, -0.3),
    "zealot": (0, 0.6, 0, 0, 0.5, -0.8),
    "shadow": (0, 0, 0, 0.8, -0.3, 1.2),
    "crusader": (0, 0.8, 0.5, 0, 0.4, -0.6),
    "miserly": (1.0, -0.6, 0.6, 0, 0, 0),
    "upstart": (0.3, 0.6, 0, 0, -0.3, 0.6),
    "benefactor": (0.8, 0, 0, 0, 0.8, -0.6),
    "mercenary": (0.4, 0.4, 0, 0, 0, 0.8),
    "usurper": (0, 0.5, 0, 0.4, -0.6, 1.0),
    "hermit": (0.7, 0, 0.7, 0.3, -1.7, 0),
    "peacemaker": (0, -0.3, 0, 0, 1.4, -0.6),
    "chancellor": (1.3, 0, 0, 0.7, 0.5, 0),
    "nomad": (0, 0.8, 1.0, 0, -0.3, 0),
    "slayer": (0, 0.8, 0.6, 0.4, -0.4, 0),
    "tributary": (0.6, 0, 0, 0, 0.8, 0),
    "warchief": (0, 1.0, 0.4, 0, 0, 0),
    "hoard_king": (0.8, 0, 0, 0, 0, 0.6),
}
_VICE_LEAN = {"cruelty": "tyrant", "embezzle": "merchant", "greed": "merchant", "pride": "despot",
              "cowardice": "keeper", "blabber": "patron"}

# the first rulers: as the chronicles tell
LEADER_REIGN = {"aldern": "noble", "sylvan": "keeper", "ashen": "tyrant", "khanate": "conqueror",
                "sultanate": "sage", "north": "despot", "league": "merchant", "highland": "avenger",
                "goblin": "tyrant"}


MIN_HOLDERS = 2                # every reign type belongs to at least this many officers of the starting cast


def _scores(officer: str) -> Dict[str, float]:
    o = OFFICER[officer]
    r = random.Random(f"reign:{officer}")
    goblin = o.faction == "goblin"
    score = {k: sum(w * (o.stats[i] - 10) for i, w in enumerate(lean)) / 10 + r.uniform(0, 1.6)
             + (1.0 if goblin and k in GOBLIN_ONLY else 0)
             for k, lean in _LEAN.items() if k not in (HUMAN_ONLY if goblin else GOBLIN_ONLY)}
    from .cards import VICE_OF
    for v in VICE_OF.get(officer, ()):
        if v in _VICE_LEAN:
            score[_VICE_LEAN[v]] += 1.5
    return score


@lru_cache(maxsize=1)
def _cast() -> Dict[str, str]:
    """Reign types of the starting cast: each officer's best fit, then the rare types are handed to the
    officers they suit nearly as well, so that every type is met in play (``MIN_HOLDERS``)."""
    from .officers import OFFICERS
    offs = [o.key for lst in OFFICERS.values() for o in lst]
    fixed = {k for k in offs if OFFICER[k].rank == 0 and OFFICER[k].faction in LEADER_REIGN}
    scores = {k: _scores(k) for k in offs if k not in fixed}
    out = {k: LEADER_REIGN[OFFICER[k].faction] for k in fixed}
    out.update({k: max(sc, key=sc.get) for k, sc in scores.items()})
    for kind in REIGNS:
        while sum(1 for v in out.values() if v == kind) < MIN_HOLDERS:
            count = {t: sum(1 for v in out.values() if v == t) for t in REIGNS}
            cands = [k for k, sc in scores.items() if kind in sc and out[k] != kind and count[out[k]] > MIN_HOLDERS]
            if not cands:
                break
            k = min(cands, key=lambda k: (scores[k][out[k]] - scores[k][kind], k))
            out[k] = kind
    return out


@lru_cache(maxsize=None)
def reign_of(officer: str) -> str:
    o = OFFICER[officer]
    if o.rank == 0 and o.faction in LEADER_REIGN:
        return LEADER_REIGN[o.faction]
    cast = _cast()
    if officer in cast:
        return cast[officer]
    score = _scores(officer)                      # a newcomer: his own best fit
    return max(score, key=score.get)


def describe(officer: str) -> Tuple[str, List[Tuple[str, str]]]:
    name, traits = REIGNS[reign_of(officer)]
    return name, [TRAITS[t] for t in traits]


def ruler_traits(camp, faction: str) -> Tuple[str, ...]:
    """Traits of the realm's ruler - only for realms the computer plays."""
    if faction == camp.player:
        return ()
    ruler = camp.leader.get(faction) if hasattr(camp, "leader") else None
    return REIGNS[reign_of(ruler)][1] if ruler else ()


def has(camp, faction: str, trait: str) -> bool:
    return trait in ruler_traits(camp, faction)


def shown(camp, officer: str) -> bool:
    """The reign type is shown only for a ruler the computer plays."""
    f = camp.allegiance.get(officer)
    return camp.is_leader(officer) and f != camp.player and officer not in camp.dead


# --- effects ---------------------------------------------------------------------------------------
DEFENSE_CARDS = {"fortify", "sortie", "militia_call", "thicket_spirits", "rune_gates"}
GUARD_CARDS = {"counterspy", "intercept", "purge", "peers_court", "denounce"}
ENVOY_CARDS = {"embassy", "trade_pact", "truce", "grand_embassy", "buyout", "peacemaker"}   # (not the horde's buy-off)
MARCH_CARDS = {"march", "forced_march", "mother_tree", "blitz", "longships", "ancient_map"}


def card_mult(camp, faction: str, card) -> float:
    t = ruler_traits(camp, faction)
    if not t:
        return 1.0
    m = 1.0
    if "aggressive" in t and card.kind == "military" and card.key not in DEFENSE_CARDS:
        m *= 1.3
    if "greedy" in t and card.kind == "economy":
        m *= 1.3
    if "schemer" in t and card.kind == "intrigue":
        m *= 1.4
    if "pious" in t and card.kind == "intrigue" and card.key not in GUARD_CARDS:
        m *= 0.5
    if "honorable" in t and card.kind == "intrigue" and card.key not in GUARD_CARDS:
        m *= 0.1
    if "paranoid" in t and card.key in GUARD_CARDS:
        m *= 2.0
    if "defender" in t and card.key in DEFENSE_CARDS:
        m *= 1.4
    if "recruiter" in t and card.kind == "recruit":
        m *= 1.4
    if "isolationist" in t and card.key in ENVOY_CARDS:
        m *= 0.5
    if "courtly" in t and card.key in ENVOY_CARDS:
        m *= 1.4
    if "chancellor" in t and card.kind == "council":
        m *= 1.4
    if "rover" in t and card.key in MARCH_CARDS:
        m *= 1.5
    return m


def keep_mult(camp, faction: str, card) -> float:
    """How eagerly the ruler keeps a card in hand for the next turn."""
    t = ruler_traits(camp, faction)
    m = 1.0
    if card.key in ENVOY_CARDS:
        m *= (0.2 if "isolationist" in t else 1.0) * (1.6 if "courtly" in t else 1.0)
    if "chancellor" in t and card.kind == "council":
        m *= 1.4
    return m


def prosperity_value(camp, faction: str, base: float) -> float:
    return base * (1.4 if has(camp, faction, "builder") else 1.0)


def min_odds(camp, faction: str) -> float:
    if has(camp, faction, "cautious"):
        return 0.65
    if has(camp, faction, "reckless"):
        return 0.45
    return 0.55


def leader_odds(camp, faction: str) -> float:
    """How sure the computer must be before it risks its ruler in a storm (БЕРЕЖЁТ СЕБЯ: never, unless
    desperate)."""
    if has(camp, faction, "brave"):
        return 0.65
    if has(camp, faction, "careful_self"):
        return 1.01
    return 0.8


def homebody(camp, faction: str, officer: str) -> bool:
    """БЕРЕЖЁТ СЕБЯ: the ruler stays in his city (no marches, no posts away)."""
    return camp.leader.get(faction) == officer and has(camp, faction, "careful_self")


def offender(camp, faction: str, other: str) -> bool:
    """МСТИТЕЛЬНЫЙ: ``other`` has stormed this ruler's cities lately."""
    return has(camp, faction, "vengeful") and camp.last_attack.get((other, faction), -99) >= camp.turn - 8


def weakened(camp, other: str) -> bool:
    """A realm in unrest or that has lost cities lately (СТЕРВЯТНИК's prey)."""
    from .diplomacy import lost_lately
    return bool(camp.realms[other].unrest) or lost_lately(camp, other) > 0


def odds_relief(camp, faction: str, target_owner: str) -> float:
    """How much lower storm odds will do: МСТИТЕЛЬНЫЙ against his offender, СТЕРВЯТНИК against the weak."""
    if target_owner in (faction, "goblin") or target_owner not in camp.realms:
        return 0.0
    d = 0.0
    if offender(camp, faction, target_owner):
        d += 0.15
    if has(camp, faction, "vulture") and weakened(camp, target_owner):
        d += 0.08
    return d


def admires(camp, faction: str, other: str) -> bool:
    """ПОЧИТАТЕЛЬ СИЛЫ: ``other`` is the hegemon and this ruler looks up to it."""
    from .diplomacy import hegemon
    return has(camp, faction, "admirer") and other == hegemon(camp)


COAX_BELOW = 75                 # ЧУТКИЙ: advisers below this loyalty are coaxed with their own cards


def coaxing(camp, faction: str, inst) -> float:
    """ЧУТКИЙ: a card brought by an adviser of low loyalty is worth more to play (it mends him, +2)."""
    o = inst.origin
    if not has(camp, faction, "attentive") or o not in camp.loyalty or o not in camp.realms[faction].council:
        return 1.0
    return 1.0 + max(0, COAX_BELOW - camp.loyalty[o]) / 25


def coax_bonus(camp, faction: str, inst) -> float:
    """... and even a card of little use is played for the adviser's sake (value in gold)."""
    m = coaxing(camp, faction, inst)
    return (m - 1.0) * 40


def worth_mult(camp, faction: str) -> float:
    return 1.25 if has(camp, faction, "conqueror") else 1.0


def hostility(camp, faction: str, target: str) -> float:
    t = ruler_traits(camp, faction)
    if t and target == "goblin" and "hunter" in t:
        return 1.5
    if not t or target in (faction, "goblin"):
        return 1.0
    m = 1.0
    if "vengeful" in t and camp.last_attack.get((target, faction), -99) >= camp.turn - 8:
        m *= 2.0
    if "vulture" in t:
        from .diplomacy import lost_lately
        if camp.realms[target].unrest or lost_lately(camp, target):
            m *= 1.4
    if "admirer" in t:
        from .diplomacy import hegemon
        if target == hegemon(camp):
            m *= 0.5                                # the strongest is looked up to, not attacked
    if "ambitious" in t:
        from .diplomacy import humans, standing
        rivals = [x for x in humans(camp) if x != faction]
        if rivals and target == max(rivals, key=lambda x: standing(camp, x)):
            m *= 1.3
    return m


def course_bias(camp, faction: str) -> Dict[str, float]:
    t = ruler_traits(camp, faction)
    b: Dict[str, float] = {}
    for trait, course, d in (("greedy", "economy", 0.3), ("builder", "economy", 0.3), ("defender", "defense", 0.6),
                             ("conqueror", "war", 0.6), ("aggressive", "war", 0.3), ("schemer", "intrigue", 0.5)):
        if trait in t:
            b[course] = b.get(course, 0) + d
    return b


def course_margin(camp, faction: str) -> float:
    if has(camp, faction, "traditionalist"):
        return 1.2
    return 0.5


def reserve(camp, faction: str, base: float) -> float:
    return max(base, 3 * camp.upkeep(faction)) if has(camp, faction, "miser") else base


def hire_ok(camp, faction: str, key: str) -> bool:
    return True


RELEASE, RELEASE_MERCIFUL, EXECUTE_CRUEL = 0.2, 0.9, 0.7


def prisoner_fate(camp, victor: str) -> Optional[str]:
    """What the victor's ruler does with a captured officer: 'execute', 'release' (his realm is grateful,
    +5, whoever lets him go) or None (he swears to the victor or slips home). Any computer ruler sometimes
    lets a prisoner go; МИЛОСЕРДНЫЙ nearly always, ЖЕСТОКИЙ usually executes."""
    if victor == camp.player or victor == "goblin":
        return None
    t = ruler_traits(camp, victor)
    if "cruel" in t and camp.rng.random() < EXECUTE_CRUEL:
        return "execute"
    if camp.rng.random() < (RELEASE_MERCIFUL if "merciful" in t else RELEASE):
        return "release"
    return None
