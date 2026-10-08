"""Reign types (pure Python, no pygame): how a ruler governs when the computer plays his realm.

Every officer has a reign type (``reign_of``) - a name such as ТИРАН made of three behaviour
traits (``TRAITS``, 30 of them). It only matters - and is only shown - while he rules a realm that
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
    "merciful": ("МИЛОСЕРДНЫЙ", "пленных отпускает домой, их держава за это благодарна (+5)"),
    "greedy": ("АЛЧНЫЙ", "карты хозяйства ценит на 30% выше, тянется к курсу хозяйства"),
    "generous": ("ЩЕДРЫЙ", "раз в 3 хода верность всех его офицеров +1"),
    "paranoid": ("ПОДОЗРИТЕЛЬНЫЙ", "защиту от интриг ценит вдвое; верность забытых советников падает вдвое быстрее"),
    "schemer": ("ИНТРИГАН", "карты интриги ценит на 40% выше, тянется к тайной политике"),
    "diplomat": ("ДИПЛОМАТ", "вдвое охотнее шлёт послов с миром и союзом"),
    "warmonger": ("ВОИНСТВЕННЫЙ", "мира не просит и неохотно его принимает (-15)"),
    "honorable": ("БЛАГОРОДНЫЙ", "никогда не нарушает договоров"),
    "treacherous": ("ВЕРОЛОМНЫЙ", "разрывает перемирия втрое охотнее"),
    "builder": ("СТРОИТЕЛЬ", "процветание городов ценит на 40% выше, бережёт их от поборов"),
    "defender": ("ОБОРОНЕЦ", "карты обороны ценит на 40% выше, тянется к курсу обороны"),
    "conqueror": ("ЗАВОЕВАТЕЛЬ", "вражеские города ценит на 25% выше, тянется к курсу войны"),
    "miser": ("СКРЯГА", "держит в казне запас на 3 хода содержания, нанимает меньше"),
    "recruiter": ("ВЕРБОВЩИК", "найм и сбор войск ценит на 40% выше"),
    "elitist": ("ЦЕНИТЕЛЬ ЛУЧШИХ", "нанимает только сильных воинов, ополченцев и псов не берёт"),
    "trader": ("ТОРГОВЕЦ", "вдвое охотнее предлагает торговлю и охотнее её принимает (+10)"),
    "brave": ("ХРАБРЫЙ", "сам ведёт войска в бой уже при шансе 65%"),
    "careful_self": ("БЕРЕЖЁТ СЕБЯ", "сам идёт в бой лишь при шансе 90% или в безвыходном положении"),
    "nepotist": ("КУМОВСТВО", "в совет сажает самых верных, а не самых способных"),
    "meritocrat": ("МЕРИТОКРАТ", "в совет сажает самых способных и пересматривает его вдвое чаще"),
    "vengeful": ("МСТИТЕЛЬНЫЙ", "того, кто штурмовал его города, бьёт в первую очередь (+50%)"),
    "vulture": ("СТЕРВЯТНИК", "бьёт ослабленных: державы в смуте и терявшие города (+40%)"),
    "pious": ("НАБОЖНЫЙ", "подлых интриг избегает (-50%), отношения с соседями медленно растут"),
    "traditionalist": ("ТРАДИЦИОНАЛИСТ", "меняет курс державы лишь при большой выгоде"),
    "reformer": ("РЕФОРМАТОР", "меняет курс, как только это выгоднее"),
    "ambitious": ("ЧЕСТОЛЮБИВЫЙ", "союзов не ищет, метит в сильнейших (+30% к штурмам их городов)"),
}

# key: (name, traits)
REIGNS: Dict[str, Tuple[str, Tuple[str, str, str]]] = {
    "tyrant": ("ТИРАН", ("cruel", "aggressive", "paranoid")),
    "conqueror": ("ЗАВОЕВАТЕЛЬ", ("conqueror", "brave", "recruiter")),
    "sage": ("МУДРЕЦ", ("cautious", "builder", "diplomat")),
    "merchant": ("ТОРГОВЫЙ КНЯЗЬ", ("greedy", "trader", "miser")),
    "schemer": ("ИНТРИГАН", ("schemer", "treacherous", "vulture")),
    "noble": ("БЛАГОРОДНЫЙ ВОЖДЬ", ("honorable", "brave", "merciful")),
    "keeper": ("ХРАНИТЕЛЬ", ("defender", "traditionalist", "careful_self")),
    "reformer": ("РЕФОРМАТОР", ("reformer", "meritocrat", "builder")),
    "avenger": ("МСТИТЕЛЬ", ("vengeful", "reckless", "warmonger")),
    "patron": ("ПОКРОВИТЕЛЬ", ("generous", "pious", "nepotist")),
    "despot": ("ВЛАСТОЛЮБЕЦ", ("ambitious", "elitist", "aggressive")),
    "strategist": ("СТРАТЕГ", ("vulture", "careful_self", "reformer")),
    "warlord": ("ПОЛКОВОДЕЦ", ("aggressive", "brave", "recruiter")),
    "raider": ("ЗАХВАТЧИК", ("conqueror", "reckless", "cruel")),
    "autocrat": ("ДЕСПОТ", ("cruel", "paranoid", "nepotist")),
    "envoy": ("КУПЕЦ-ДИПЛОМАТ", ("trader", "diplomat", "greedy")),
    "architect": ("ЗОДЧИЙ ДЕРЖАВЫ", ("builder", "defender", "miser")),
    "zealot": ("РЕВНИТЕЛЬ ВЕРЫ", ("pious", "honorable", "aggressive")),
    "shadow": ("ТЕНЕВОЙ ПРАВИТЕЛЬ", ("schemer", "paranoid", "careful_self")),
    "crusader": ("КРЕСТОНОСЕЦ", ("honorable", "conqueror", "brave")),
    "miserly": ("СКУПОЙ ВЛАДЫКА", ("miser", "traditionalist", "cautious")),
    "upstart": ("ВЫСКОЧКА", ("ambitious", "reckless", "meritocrat")),
    "benefactor": ("ОТЕЦ НАРОДА", ("generous", "builder", "merciful")),
    "mercenary": ("НАЁМНЫЙ КНЯЗЬ", ("greedy", "treacherous", "elitist")),
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
}
_VICE_LEAN = {"cruelty": "tyrant", "embezzle": "merchant", "greed": "merchant", "pride": "despot",
              "cowardice": "keeper", "blabber": "patron"}

# the first rulers: as the chronicles tell
LEADER_REIGN = {"aldern": "noble", "sylvan": "keeper", "ashen": "tyrant", "khanate": "conqueror",
                "sultanate": "sage", "north": "despot", "league": "merchant", "highland": "avenger",
                "goblin": "tyrant"}


@lru_cache(maxsize=None)
def reign_of(officer: str) -> str:
    o = OFFICER[officer]
    if o.rank == 0 and o.faction in LEADER_REIGN:
        return LEADER_REIGN[o.faction]
    r = random.Random(f"reign:{officer}")
    score = {k: sum(w * (o.stats[i] - 10) for i, w in enumerate(lean)) / 10 + r.uniform(0, 1.6)
             for k, lean in _LEAN.items()}
    from .cards import VICE_OF
    for v in VICE_OF.get(officer, ()):
        if v in _VICE_LEAN:
            score[_VICE_LEAN[v]] += 1.5
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
    if "paranoid" in t and card.key in GUARD_CARDS:
        m *= 2.0
    if "defender" in t and card.key in DEFENSE_CARDS:
        m *= 1.4
    if "recruiter" in t and card.kind == "recruit":
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
    """How sure the computer must be before it risks its ruler in a storm."""
    if has(camp, faction, "brave"):
        return 0.65
    if has(camp, faction, "careful_self"):
        return 0.9
    return 0.8


def worth_mult(camp, faction: str) -> float:
    return 1.25 if has(camp, faction, "conqueror") else 1.0


def hostility(camp, faction: str, target: str) -> float:
    t = ruler_traits(camp, faction)
    if not t or target in (faction, "goblin"):
        return 1.0
    m = 1.0
    if "vengeful" in t and camp.last_attack.get((target, faction), -99) >= camp.turn - 8:
        m *= 1.5
    if "vulture" in t:
        from .diplomacy import lost_lately
        if camp.realms[target].unrest or lost_lately(camp, target):
            m *= 1.4
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
    if has(camp, faction, "reformer"):
        return 0.2
    return 0.5


def reserve(camp, faction: str, base: float) -> float:
    return max(base, 3 * camp.upkeep(faction)) if has(camp, faction, "miser") else base


def hire_ok(camp, faction: str, key: str) -> bool:
    from .units import ROSTER
    return not has(camp, faction, "elitist") or ROSTER[key].tier in ("average", "above")


def prisoner_fate(camp, victor: str) -> Optional[str]:
    """What the victor's ruler does with a captured officer: 'execute', 'release' or None (as usual)."""
    t = ruler_traits(camp, victor)
    if "cruel" in t and camp.rng.random() < 0.7:
        return "execute"
    if "merciful" in t:
        return "release"
    return None
