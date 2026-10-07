"""Unit roster: stats, roles, strengths/weaknesses and seeded, team-colored looks.

Damage model
------------
* physical damage is reduced by ``armor`` (fraction), magic by ``resist``;
  ``holy`` is magic that hits undead x1.5, ``blunt`` weapons ignore 30% of armor
  and crush skeletons x1.5;
* ``dodge`` - chance to avoid physical hits (melee and arrows);
* every unit has a niche and a counter (see ``TRAITS``: perks, flaws, behavior).

Speeds are px/s on a 480x270 battlefield, ranges in px, cooldowns in seconds.

Looks
-----
:func:`look_for` builds the sprite spec for one unit from a seed.  What makes
a class recognisable (weapon, armor type, helmet shape, robe, team colors) is
fixed; faces, skin, hair, beards, builds and shades vary.  Same seed -> same look.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field, replace
from typing import Dict, List, Tuple, Union

from pixelforge.units.creatures import QuadSpec
from pixelforge.units.humanoid import HumanoidSpec


@dataclass(frozen=True)
class UnitType:
    key: str
    name: str                 # Russian display name
    role: str
    hp: int
    armor: float              # physical damage reduction 0..1
    resist: float             # magic damage reduction 0..1
    damage: Tuple[int, int]
    damage_type: str          # physical | magic | holy
    attack_range: float
    cooldown: float
    speed: float
    dodge: float = 0.0
    ranged: bool = False
    caster: bool = False      # uses the "cast" animation for its attack
    blunt: bool = False
    undead: bool = False
    radius: float = 7.0       # body size for collisions
    lane: str = "front"       # front | flank | back  (starting position)
    prefers: Dict[str, float] = field(default_factory=dict)   # AI target bonus by enemy type
    perks: Tuple[Tuple[str, str], ...] = ()      # (name, description): strengths
    flaws: Tuple[Tuple[str, str], ...] = ()      # weaknesses
    behavior: Tuple[Tuple[str, str], ...] = ()   # how the AI plays this unit


ROSTER: Dict[str, UnitType] = {u.key: u for u in (
    # --- original seven ----------------------------------------------------------
    UnitType("knight", "РЫЦАРЬ", "ТАНК", hp=460, armor=0.45, resist=0.0, damage=(15, 21), damage_type="physical",
             attack_range=17, cooldown=1.25, speed=31, radius=8,
             prefers={"rogue": 25, "barbarian": 10, "wolf": 15}),
    UnitType("barbarian", "ВАРВАР", "БОЕЦ", hp=350, armor=0.12, resist=0.15, damage=(24, 32),
             damage_type="physical", attack_range=17, cooldown=1.3, speed=44,
             prefers={"mage": 15, "archer": 15, "cleric": 15}),
    UnitType("mage", "МАГ", "АРТИЛЛЕРИЯ", hp=175, armor=0.0, resist=0.30, damage=(24, 30), damage_type="magic",
             attack_range=165, cooldown=2.8, speed=33, ranged=True, caster=True, lane="back",
             prefers={"knight": 25, "orc": 25, "ogre": 25, "paladin": 15}),
    UnitType("spearman", "КОПЕЙЩИК", "АНТИКАВАЛЕРИЯ", hp=330, armor=0.28, resist=0.10, damage=(21, 27),
             damage_type="physical", attack_range=27, cooldown=1.15, speed=38,
             prefers={"barbarian": 30, "orc": 25, "wolf": 15, "ogre": 20}),
    UnitType("rogue", "РАЗБОЙНИК", "УБИЙЦА", hp=185, armor=0.10, resist=0.10, damage=(11, 15),
             damage_type="physical", attack_range=14, cooldown=0.7, speed=64, dodge=0.30, radius=6, lane="flank",
             prefers={"mage": 130, "archer": 115, "cleric": 130, "necromancer": 120, "shaman": 115,
                      "crossbowman": 110}),
    UnitType("orc", "ОРК", "ГРОМИЛА", hp=380, armor=0.25, resist=0.0, damage=(23, 30), damage_type="physical",
             attack_range=17, cooldown=1.4, speed=37, radius=8,
             prefers={"barbarian": 20, "rogue": 20, "spearman": 15, "knight": -25}),
    UnitType("archer", "ЛУЧНИК", "СТРЕЛОК", hp=165, armor=0.10, resist=0.10, damage=(15, 19),
             damage_type="physical", attack_range=175, cooldown=1.25, speed=42, ranged=True, lane="back",
             prefers={"mage": 40, "rogue": 25, "cleric": 40, "necromancer": 30}),
    # --- ten new ones ----------------------------------------------------------------
    UnitType("paladin", "ПАЛАДИН", "СВЯТОЙ ВОИН", hp=370, armor=0.30, resist=0.20, damage=(15, 21),
             damage_type="holy", attack_range=17, cooldown=1.3, speed=33, radius=8,
             prefers={"skeleton": 40, "necromancer": 50}),
    UnitType("cleric", "ЖРИЦА", "ЛЕКАРЬ", hp=150, armor=0.0, resist=0.25, damage=(9, 13), damage_type="holy",
             attack_range=150, cooldown=2.0, speed=36, ranged=True, caster=True, lane="back",
             prefers={"skeleton": 30, "necromancer": 30}),
    UnitType("crossbowman", "АРБАЛЕТЧИК", "БРОНЕБОЙЩИК", hp=200, armor=0.20, resist=0.10, damage=(36, 46),
             damage_type="physical", attack_range=185, cooldown=2.4, speed=34, ranged=True, lane="back",
             prefers={"knight": 45, "paladin": 40, "ogre": 30, "orc": 25, "hammerer": 25}),
    UnitType("necromancer", "НЕКРОМАНТ", "ПРИЗЫВАТЕЛЬ", hp=160, armor=0.0, resist=0.35, damage=(14, 19),
             damage_type="magic", attack_range=150, cooldown=2.0, speed=32, ranged=True, caster=True, lane="back",
             prefers={"cleric": 30, "mage": 20}),
    UnitType("skeleton", "СКЕЛЕТ", "НЕЖИТЬ", hp=300, armor=0.20, resist=0.30, damage=(20, 26),
             damage_type="physical", attack_range=16, cooldown=0.95, speed=39, undead=True,
             prefers={"archer": 15, "mage": 15}),
    UnitType("monk", "МОНАХ", "МАСТЕР БОЯ", hp=230, armor=0.10, resist=0.20, damage=(9, 12), damage_type="physical",
             attack_range=13, cooldown=0.5, speed=52, dodge=0.35, blunt=True, radius=6, lane="flank",
             prefers={"mage": 40, "archer": 35, "crossbowman": 45, "cleric": 40, "shaman": 35}),
    UnitType("hammerer", "МОЛОТОБОЕЦ", "СОКРУШИТЕЛЬ", hp=340, armor=0.30, resist=0.10, damage=(30, 38),
             damage_type="physical", attack_range=18, cooldown=1.9, speed=32, blunt=True, radius=8,
             prefers={"knight": 30, "paladin": 30, "skeleton": 30, "ogre": 15}),
    UnitType("shaman", "ШАМАН", "ГРОЗОВИК", hp=165, armor=0.05, resist=0.30, damage=(17, 23), damage_type="magic",
             attack_range=150, cooldown=2.5, speed=36, ranged=True, caster=True, lane="back",
             prefers={"rogue": 20, "wolf": 20, "monk": 20}),
    UnitType("wolf", "ВОЛК", "ХИЩНИК", hp=245, armor=0.10, resist=0.05, damage=(12, 17), damage_type="physical",
             attack_range=15, cooldown=0.6, speed=72, dodge=0.15, radius=7, lane="flank",
             prefers={"archer": 40, "mage": 40, "cleric": 45, "crossbowman": 40, "shaman": 35, "necromancer": 35}),
    UnitType("ogre", "ОГР", "ВЕЛИКАН", hp=560, armor=0.15, resist=0.0, damage=(38, 50), damage_type="physical",
             attack_range=22, cooldown=2.2, speed=27, blunt=True, radius=11,
             prefers={"knight": 15, "spearman": 15}),
)}

# --- descriptions: perks (green), flaws (red), behavior (blue) --------------------------
# Every line is one independent trait: "NAME", "short description".  Keep them in
# sync with the mechanics in sim.py / ai.py.

TRAITS: Dict[str, Dict[str, Tuple[Tuple[str, str], ...]]] = {
    "knight": dict(
        perks=(("ЩИТ", "блокирует 60% стрел и 30% ударов спереди"),
               ("ТЯЖЁЛАЯ БРОНЯ", "поглощает 45% физического урона"),
               ("ПРОВОКАЦИЯ", "заставляет врага, прорвавшегося к стрелкам, биться с ним 3.5 с (раз в 9 с)")),
        flaws=(("МЕДЛИТЕЛЬНОСТЬ", "один из самых медленных бойцов"),
               ("УЯЗВИМ К МАГИИ", "броня не спасает от заклинаний"),
               ("ОТКРЫТАЯ СПИНА", "щит не защищает сзади и от арбалетных болтов")),
        behavior=(("ТЕЛОХРАНИТЕЛЬ", "первым делом атакует тех, кто напал на своих стрелков"),)),
    "barbarian": dict(
        perks=(("РЫВОК", "бросается к врагу с ускорением x1.9 (раз в 10 с)"),
               ("РАССЕЧЕНИЕ", "60% урона задевает врагов рядом с целью"),
               ("КАЗНЬ", "x1.5 урона по врагам с HP ниже 30%"),
               ("ЯРОСТЬ", "при HP ниже 50% бьёт в 1.7 раза чаще"),
               ("ВАМПИРИЗМ", "в ярости лечится на 25% нанесённого урона")),
        flaws=(("ЛЁГКАЯ БРОНЯ", "всего 12% защиты, первым попадает под удар"),),
        behavior=(("ПАЛАЧ", "охотится на самых раненых врагов"),)),
    "mage": dict(
        perks=(("ОГНЕННЫЙ ШАР", "взрыв бьёт всех врагов в радиусе"),
               ("ПОДЖОГ", "взрыв поджигает: 6 урона в секунду 3 с"),
               ("ЛЕДЯНАЯ ВОЛНА", "отталкивает и замедляет на 50% подошедших вплотную (раз в 9 с)")),
        flaws=(("ХРУПКОСТЬ", "175 HP и никакой брони"),
               ("ДОЛГИЙ КАСТ", "колдует раз в 2.8 с")),
        behavior=(("АРТИЛЛЕРИСТ", "бьёт туда, где врагов больше всего"),
                  ("ОСТОРОЖНОСТЬ", "держит дистанцию и отступает от ближников"))),
    "spearman": dict(
        perks=(("ДЛИННОЕ КОПЬЁ", "самый длинный удар в ближнем бою, бьёт первым"),
               ("КОНТРУДАР", "встречает врага, бегущего на него рывком: +100% урона и отбрасывает"),
               ("СЛОМАННЫЙ РЫВОК", "контрудар обрывает рывок врага и его оглушающий удар")),
        flaws=(("НЕПОВОРОТЛИВОСТЬ", "не успевает догнать стрелков и магов"),),
        behavior=(("ЛОВЕЦ РЫВКОВ", "в первую очередь целится во врагов в рывке"),)),
    "rogue": dict(
        perks=(("ШАГ СКВОЗЬ ТЕНЬ", "телепорт за спину стрелку или магу (раз в 12 с)"),
               ("УДАР В СПИНУ", "x1.9 урона, если враг смотрит не на него"),
               ("КРОВОТЕЧЕНИЕ", "удар в спину отнимает ещё 6 HP в секунду 3 с"),
               ("УКЛОНЕНИЕ", "30% шанс увернуться от удара или стрелы"),
               ("ДЫМОВАЯ ШАШКА", "при HP ниже 35% исчезает и отступает (раз за бой)")),
        flaws=(("СЛАБЫЕ УДАРЫ", "броня сильно режет его урон"),
               ("ЛЁГКАЯ БРОНЯ", "долго не живёт под ударами")),
        behavior=(("ОБХОД С ФЛАНГА", "бежит по краю поля и ищет стрелков и магов"),)),
    "orc": dict(
        perks=(("РЕГЕНЕРАЦИЯ", "4 HP в секунду, 8 если давно не получал урон"),
               ("БОЕВОЙ КЛИЧ", "рывок к врагу, первый удар оглушает на 1.1 с (раз в 16 с)"),
               ("ВООДУШЕВЛЕНИЕ", "клич даёт союзникам рядом +20% урона на 6 с")),
        flaws=(("МЕДЛЕННЫЕ УДАРЫ", "бьёт раз в 1.4 с"),
               ("БЕЗ МАГИЧЕСКОЙ ЗАЩИТЫ", "заклинания проходят полностью")),
        behavior=(("ВЫЗОВ СИЛЬНЕЙШЕМУ", "ищет драки с самым крепким бойцом ближнего боя"),)),
    "archer": dict(
        perks=(("ДАЛЬНИЙ БОЙ", "стреляет почти через всё поле"),
               ("ВЫСТРЕЛ В ГОЛОВУ", "20% шанс двойного урона"),
               ("ЗАЛП", "3 стрелы по разным целям (раз в 9 с)")),
        flaws=(("ХРУПКОСТЬ", "165 HP и лёгкая броня"),
               ("ЩИТ ПРОТИВ СТРЕЛ", "рыцарь ловит щитом большинство стрел"),
               ("НАВЕСНАЯ СТРЕЛЬБА", "по быстрой цели стрела может промахнуться")),
        behavior=(("КАЙТ", "держит дистанцию, отходит от ближников и стреляет на отходе"),)),
    "paladin": dict(
        perks=(("АУРА ИСЦЕЛЕНИЯ", "союзники рядом восстанавливают 1.6 HP в секунду"),
               ("СВЯТАЯ БУЛАВА", "святой урон, x1.5 по нежити"),
               ("БОЖЕСТВЕННЫЙ ЩИТ", "смертельный удар делает его неуязвимым на 3 с (раз за бой)")),
        flaws=(("НЕВЫСОКИЙ УРОН", "15-21 за удар"),
               ("МЕДЛИТЕЛЬНОСТЬ", "медленно добирается до врага")),
        behavior=(("КРЕСТОНОСЕЦ", "в первую очередь идёт на нежить и некромантов"),)),
    "cleric": dict(
        perks=(("ИСЦЕЛЕНИЕ", "лечит самого раненого союзника на 35-45 HP"),
               ("ОЧИЩЕНИЕ", "лечение снимает горение и кровотечение"),
               ("СВЯТАЯ ИСКРА", "если лечить некого, бьёт врагов (нежить x1.5)")),
        flaws=(("ХРУПКОСТЬ", "150 HP и никакой брони"),
               ("ПОЧТИ БЕЗ УРОНА", "сама почти не убивает")),
        behavior=(("СИДЕЛКА", "держится возле раненых союзников"),
                  ("ОСТОРОЖНОСТЬ", "отступает от ближников"))),
    "crossbowman": dict(
        perks=(("БРОНЕБОЙНЫЙ БОЛТ", "игнорирует 75% брони"),
               ("СКВОЗЬ ЩИТ", "болт не блокируется щитом рыцаря"),
               ("ТЯЖЁЛЫЙ ВЫСТРЕЛ", "36-46 урона и отталкивает цель")),
        flaws=(("ДОЛГАЯ ПЕРЕЗАРЯДКА", "один выстрел в 2.4 с"),
               ("ПЛОХ ВБЛИЗИ", "в ближнем бою проигрывает почти всем")),
        behavior=(("ОХОТНИК ЗА БРОНЁЙ", "выбирает самых бронированных врагов"),
                  ("СТОИТ НАСМЕРТЬ", "никогда не отступает"))),
    "necromancer": dict(
        perks=(("ПОДНЯТЬ МЁРТВЫХ", "превращает труп любой стороны в скелета-слугу (до 2, раз в 6 с)"),
               ("ПОХИЩЕНИЕ ЖИЗНИ", "теневой снаряд лечит его на 50% урона")),
        flaws=(("ХРУПКОСТЬ", "160 HP и никакой брони"),
               ("СЛАБЫЙ БЕЗ МЁРТВЫХ", "пока нет трупов, урон невелик")),
        behavior=(("СТЕРВЯТНИК", "подбирается к свежим трупам, чтобы поднять их"),)),
    "skeleton": dict(
        perks=(("ВОССТАНИЕ", "через 2.5 с после смерти встаёт с 70% HP (раз за бой)"),
               ("БЕСКРОВНЫЙ", "не бывает кровотечения")),
        flaws=(("ХРУПКИЕ КОСТИ", "дробящее оружие x1.5 и не даёт восстать"),
               ("НЕЧИСТЬ", "святой урон x1.5 и не даёт восстать")),
        behavior=(("МЁРТВАЯ ХВАТКА", "не меняет цель, пока она жива"),)),
    "monk": dict(
        perks=(("ШКВАЛ УДАРОВ", "бьёт дважды в секунду"),
               ("КОМБО", "каждый 4-й удар оглушает на 0.7 с и отбрасывает"),
               ("УКЛОНЕНИЕ", "35% шанс увернуться, в том числе от стрел"),
               ("ДРОБЯЩИЕ КУЛАКИ", "игнорируют 30% брони, нежить x1.5")),
        flaws=(("СЛАБЫЕ УДАРЫ", "9-12 урона за удар"),
               ("ЛЁГКАЯ БРОНЯ", "проигрывает затяжную рубку громилам")),
        behavior=(("ПЕРЕХВАТЧИК", "ловит врагов, напавших на своих стрелков, иначе охотится на чужих"),)),
    "hammerer": dict(
        perks=(("ДРОБЯЩИЙ МОЛОТ", "игнорирует 30% брони, нежить x1.5"),
               ("СОТРЯСЕНИЕ", "каждый 3-й удар оглушает всех врагов вокруг и ранит их")),
        flaws=(("МЕДЛЕННЫЕ УДАРЫ", "бьёт раз в 1.9 с"),
               ("МЕДЛИТЕЛЬНОСТЬ", "его легко расстрелять на подходе")),
        behavior=(("В САМУЮ ГУЩУ", "идёт туда, где врагов больше всего"),)),
    "shaman": dict(
        perks=(("ЦЕПНАЯ МОЛНИЯ", "бьёт цель и перескакивает ещё на 2 врагов"),
               ("ЗАМЕДЛЕНИЕ", "молния замедляет на 50% на 1.5 с"),
               ("ЦЕЛЕБНЫЙ ДОЖДЬ", "лечит союзников вокруг на 25 HP (раз в 12 с)")),
        flaws=(("ХРУПКОСТЬ", "165 HP и почти без брони"),
               ("ЗАТУХАНИЕ", "каждый прыжок молнии слабее на 30%")),
        behavior=(("ГРОЗОВИК", "целится в скопления врагов"),
                  ("ОСТОРОЖНОСТЬ", "отступает от ближников"))),
    "wolf": dict(
        perks=(("СКОРОСТЬ", "самый быстрый боец на поле"),
               ("УКУС", "вызывает кровотечение: 6 HP в секунду 2.5 с"),
               ("СТАЯ", "+20% урона за каждого волка рядом"),
               ("ВОЙ", "первый вой даёт рывок всем волкам рядом (раз за бой)"),
               ("УКЛОНЕНИЕ", "15% шанс увернуться")),
        flaws=(("ЛЁГКАЯ БРОНЯ", "в одиночку быстро гибнет"),),
        behavior=(("ОХОТА СТАЕЙ", "бросается на ту же добычу, что и другие волки"),
                  ("ОБХОД С ФЛАНГА", "бежит по краю поля к стрелкам и магам"))),
    "ogre": dict(
        perks=(("ВЕЛИКАН", "560 HP, больше всех на поле"),
               ("РАЗМАХ ДУБИНЫ", "50% урона задевает врагов рядом с целью"),
               ("СОКРУШАЮЩИЙ УДАР", "отбрасывает, мелких врагов оглушает на 0.5 с"),
               ("ДРОБЯЩАЯ ДУБИНА", "игнорирует 30% брони, нежить x1.5")),
        flaws=(("МЕДЛИТЕЛЬНОСТЬ", "самый медленный боец"),
               ("МЕДЛЕННЫЕ УДАРЫ", "бьёт раз в 2.2 с"),
               ("БОЛЬШАЯ МИШЕНЬ", "без магической защиты, удобная цель стрелкам")),
        behavior=(("ДАВКА", "идёт туда, где врагов больше всего, чтобы задеть многих"),)),
}

ROSTER = {k: replace(u, **TRAITS[k]) for k, u in ROSTER.items()}

# the original line-up (used as the default squad)
CLASSIC = ["knight", "barbarian", "spearman", "orc", "rogue", "archer", "mage"]
ALL = list(ROSTER)
ORDER = CLASSIC  # backwards compatible name
SQUAD_MAX = 7


@dataclass(frozen=True)
class Team:
    key: str
    name: str
    color: str        # main cloth color
    accent: str       # secondary / cape
    light: str        # UI highlight
    dark: str


TEAMS = (
    Team("blue", "ЛАЗУРНЫЕ", "#124e89", "#0099db", "#2ce8f5", "#193c3e"),
    Team("red", "БАГРОВЫЕ", "#a22633", "#e43b44", "#f6757a", "#3e2731"),
)

# --- looks --------------------------------------------------------------------------------

SKINS = ["#e8b796", "#c28569", "#b86f50", "#733e39", "#ead4aa", "#d77643"]
HAIRS = ["#3e2731", "#733e39", "#feae34", "#181425", "#e43b44", "#c0cbdc", "#ead4aa", "#b86f50"]
GREYS = ["#ffffff", "#c0cbdc", "#8b9bb4"]
STEEL = ["#c0cbdc", "#8b9bb4", "#ead4aa"]

Look = Union[HumanoidSpec, QuadSpec]


def _human(r: random.Random, sleeves_from: str = "", **kw) -> HumanoidSpec:
    """Random face/hair/build; ``kw`` pins the class-defining parts.
    ``sleeves_from="skin"|"top"`` makes the sleeves match the (possibly random) skin or top."""
    hair_style = r.choice(["short", "short", "long", "spiky"])
    base = dict(skin=r.choice(SKINS), hair=r.choice(HAIRS), hair_style=hair_style,
                beard=r.choice(HAIRS) if r.random() < 0.3 else None,
                build=r.choice(["normal", "normal", "stocky", "slim"]))
    base.update(kw)
    if sleeves_from:
        base["sleeves"] = base[sleeves_from]
    return HumanoidSpec(**base)


def look_for(key: str, team: Team, seed: int) -> Look:
    """Seeded appearance of one unit of class ``key`` in ``team``'s colors."""
    r = random.Random(f"{key}:{team.key}:{seed}")
    c, a = team.color, team.accent
    if key == "knight":
        return _human(r, top=r.choice(["#8b9bb4", "#c0cbdc"]), top_shiny=True,
                      bottom=r.choice(["#5a6988", "#3a4466"]), boots="#3a4466", helmet=r.choice(STEEL),
                      hair=None, weapon="sword", shield=a, cape=c, belt=r.choice(["#733e39", "#3e2731"]),
                      build=r.choice(["normal", "stocky"]))
    if key == "barbarian":
        hair = r.choice(["#feae34", "#e43b44", "#733e39", "#ead4aa", "#3e2731"])
        return _human(r, skin=r.choice(["#d77643", "#c28569", "#e8b796", "#b86f50"]), top=c,
                      bottom=r.choice(["#733e39", "#3e2731"]), boots="#3e2731",
                      hair=hair, hair_style=r.choice(["long", "spiky"]),
                      beard=hair if r.random() < 0.75 else None,
                      helmet=r.choice(["#8b9bb4", "#c0cbdc"]) if r.random() < 0.75 else None,
                      helmet_style="horned", weapon="axe", build="stocky", sleeves_from="skin")
    if key == "mage":
        return _human(r, top=c, robe=True, sleeves=c, bottom=c, boots="#3e2731", helmet=c,
                      helmet_style="hood", beard=r.choice(GREYS + [None]), hair=r.choice(GREYS),
                      weapon="staff", magic="#fee761" if team.key == "red" else "#2ce8f5",
                      belt=r.choice(["#feae34", "#ead4aa"]), build="slim")
    if key == "spearman":
        return _human(r, top=c, bottom=r.choice(["#5a6988", "#733e39"]), boots=r.choice(["#733e39", "#3e2731"]),
                      helmet=r.choice(["#b86f50", "#8b9bb4", "#733e39"]), weapon="spear",
                      shield=a if r.random() < 0.6 else None)
    if key == "rogue":
        return _human(r, top=r.choice(["#262b44", "#3a4466", "#3e2731"]),
                      bottom="#3a4466", boots="#181425", hair_style=r.choice(["spiky", "short", "long"]),
                      weapon="dagger", cape=c, build="slim", belt="#733e39", beard=None, sleeves_from="top")
    if key == "orc":
        skin = r.choice(["#63c74d", "#3e8948", "#8bae4d", "#5a9e5a"])
        return _human(r, skin=skin, eye=r.choice(["#e43b44", "#fee761"]), top=c, sleeves=skin,
                      bottom="#3e2731", boots="#181425", hair="#181425", hair_style=r.choice(["spiky", "long", "none"]),
                      beard=None, helmet="#8b9bb4" if r.random() < 0.3 else None, helmet_style="horned",
                      weapon="axe", weapon_color="#8b9bb4", build="stocky")
    if key == "archer":
        return _human(r, top=c, sleeves=c, bottom=r.choice(["#733e39", "#5a6988"]), boots="#3e2731",
                      helmet=r.choice([a, c]), helmet_style="hood", weapon="bow", handle_color="#b86f50",
                      cape=c if r.random() < 0.7 else None, belt="#733e39", build=r.choice(["slim", "normal"]))
    if key == "paladin":
        return _human(r, top=r.choice(["#ead4aa", "#c0cbdc"]), top_shiny=True, bottom="#8b9bb4",
                      boots="#5a6988", helmet=r.choice(["#feae34", "#ead4aa"]), hair=None, weapon="mace",
                      weapon_color="#fee761", shield=a, cape=c, belt="#feae34")
    if key == "cleric":
        return _human(r, top=r.choice(["#ffffff", "#ead4aa", "#c0cbdc"]), robe=True,
                      bottom="#ffffff", boots="#b86f50", helmet=c, helmet_style="hood",
                      hair_style="long", beard=None, weapon="staff", magic="#fee761", handle_color="#ead4aa",
                      belt=c, build="slim", sleeves_from="top")
    if key == "crossbowman":
        return _human(r, top=c, bottom=r.choice(["#5a6988", "#3a4466"]), boots="#3e2731",
                      helmet=r.choice(["#8b9bb4", "#c0cbdc"]), weapon="crossbow", handle_color="#733e39",
                      weapon_color="#8b9bb4", belt="#733e39")
    if key == "necromancer":
        return _human(r, skin=r.choice(["#c0cbdc", "#8b9bb4", "#e8b796"]), top=r.choice(["#262b44", "#181425", "#3e2731"]),
                      robe=True, bottom="#181425", boots="#181425", helmet=c, helmet_style="hood",
                      beard=r.choice([None, "#c0cbdc", "#181425"]), eye=r.choice(["#63c74d", "#e43b44"]),
                      weapon="staff", magic="#63c74d", handle_color="#3e2731", belt=c, build="slim", sleeves_from="top")
    if key == "skeleton":
        bone = r.choice(["#ead4aa", "#c0cbdc", "#e4a672"])
        return HumanoidSpec(skin=bone, eye=r.choice(["#e43b44", "#2ce8f5", "#63c74d"]), hair=None,
                            top=bone, sleeves=bone, bottom=bone, boots=bone, belt=c,
                            cape=c if r.random() < 0.5 else None,
                            helmet=r.choice(["#8b9bb4", "#5a6988"]) if r.random() < 0.4 else None,
                            weapon=r.choice(["sword", "axe"]), weapon_color=r.choice(["#8b9bb4", "#b86f50"]),
                            shield=a if r.random() < 0.4 else None, build="slim")
    if key == "monk":
        return _human(r, hair=None if r.random() < 0.6 else r.choice(HAIRS), hair_style="short",
                      top=r.choice(["#feae34", "#f77622", "#e4a672"]), bottom=c,
                      boots="#733e39", belt=c, weapon=None, build=r.choice(["normal", "slim"]), sleeves_from="skin")
    if key == "hammerer":
        hair = r.choice(["#b86f50", "#e43b44", "#3e2731", "#c0cbdc", "#feae34"])
        return _human(r, hair=hair, beard=hair, top=c, bottom="#733e39", boots="#3e2731",
                      helmet=r.choice(["#8b9bb4", "#b86f50"]) if r.random() < 0.6 else None,
                      weapon="hammer", weapon_color=r.choice(["#8b9bb4", "#c0cbdc"]), build="stocky", belt="#733e39")
    if key == "shaman":
        return _human(r, skin=r.choice(SKINS + ["#63c74d"]), top=c, bottom=r.choice(["#733e39", "#3e2731"]),
                      boots="#733e39", hair_style=r.choice(["long", "spiky"]), weapon="staff", magic="#73eff7",
                      handle_color="#b86f50", cape=r.choice([None, "#733e39"]), belt="#feae34")
    if key == "ogre":
        skin = r.choice(["#8b9bb4", "#5a6988", "#8bae4d", "#c28569"])
        return HumanoidSpec(size=44, skin=skin, eye=r.choice(["#e43b44", "#fee761"]), hair=None,
                            beard=r.choice([None, "#3e2731"]), top=c, sleeves=skin, bottom="#733e39",
                            boots="#3e2731", belt="#3e2731", weapon="mace", weapon_color="#733e39",
                            handle_color="#3e2731", build="stocky")
    if key == "wolf":
        fur = r.choice(["#8b9bb4", "#5a6988", "#733e39", "#c0cbdc", "#3a4466"])
        return QuadSpec(fur=fur, belly=r.choice(["#c0cbdc", "#ead4aa", "#8b9bb4"]),
                        eye=r.choice(["#fee761", "#e43b44"]), collar=c,
                        body_len=r.choice([10.0, 11.0, 12.0]), tail="bushy")
    raise KeyError(key)


def spec_for(key: str, team: Team, seed: int = 0) -> Look:
    """Kept for compatibility: the seed-0 look."""
    return look_for(key, team, seed)
