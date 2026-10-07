"""Unit roster: stats, roles, strengths/weaknesses and seeded, team-colored looks.

Damage model
------------
* physical damage is reduced by ``armor`` (fraction), magic by ``resist``;
  ``holy`` is magic that hits undead x1.5, ``blunt`` weapons ignore 30% of armor
  and crush skeletons x1.5;
* ``dodge`` - chance to avoid physical hits (melee and arrows);
* every unit has a niche and a counter (see ``strong`` / ``weak``).

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
    strong: str = ""
    weak: str = ""
    prefers: Dict[str, float] = field(default_factory=dict)   # AI target bonus by enemy type


ROSTER: Dict[str, UnitType] = {u.key: u for u in (
    # --- original seven ----------------------------------------------------------
    UnitType("knight", "РЫЦАРЬ", "ТАНК", hp=460, armor=0.45, resist=0.0, damage=(15, 21), damage_type="physical",
             attack_range=17, cooldown=1.25, speed=31, radius=8,
             strong="Щит блокирует стрелы и удары, защищает стрелков (провокация)",
             weak="Медленный, магия игнорирует броню",
             prefers={"rogue": 25, "barbarian": 10, "wolf": 15}),
    UnitType("barbarian", "ВАРВАР", "БОЕЦ", hp=350, armor=0.12, resist=0.15, damage=(24, 32),
             damage_type="physical", attack_range=17, cooldown=1.3, speed=44,
             strong="Рывок в бой, рассекающий удар, казнь раненых (x1.5 при <30% HP), ярость и вампиризм при <50% HP",
             weak="Почти без брони; рывок на копейщика - x1.6 урона по себе, первым попадает под фокус",
             prefers={"mage": 15, "archer": 15, "cleric": 15}),
    UnitType("mage", "МАГ", "АРТИЛЛЕРИЯ", hp=175, armor=0.0, resist=0.30, damage=(24, 30), damage_type="magic",
             attack_range=165, cooldown=2.8, speed=33, ranged=True, caster=True, lane="back",
             strong="Огненный шар по площади + горение, ледяная волна",
             weak="Хрупкий, медленно колдует - лёгкая цель для разбойника",
             prefers={"knight": 25, "orc": 25, "ogre": 25, "paladin": 15}),
    UnitType("spearman", "КОПЕЙЩИК", "АНТИКАВАЛЕРИЯ", hp=310, armor=0.25, resist=0.10, damage=(19, 25),
             damage_type="physical", attack_range=27, cooldown=1.15, speed=38,
             strong="Длинное копьё бьёт первым, x1.6 урона по разбойникам, волкам и врагам в рывке, отбрасывает",
             weak="Слаб против стрел и магии издалека",
             prefers={"rogue": 35, "barbarian": 30, "orc": 25, "wolf": 35, "ogre": 20}),
    UnitType("rogue", "РАЗБОЙНИК", "УБИЙЦА", hp=185, armor=0.10, resist=0.10, damage=(11, 15),
             damage_type="physical", attack_range=14, cooldown=0.7, speed=64, dodge=0.30, radius=6, lane="flank",
             strong="Обходит с фланга, шаг сквозь тень за спину стрелку, удар в спину x1.9 + кровотечение, уклонение, дымовая шашка",
             weak="Мелкие удары вязнут в броне рыцаря, боится копейщика",
             prefers={"mage": 130, "archer": 115, "cleric": 130, "necromancer": 120, "shaman": 115,
                      "crossbowman": 110}),
    UnitType("orc", "ОРК", "ГРОМИЛА", hp=380, armor=0.25, resist=0.0, damage=(23, 30), damage_type="physical",
             attack_range=17, cooldown=1.4, speed=37, radius=8,
             strong="Регенерация, боевой клич: рывок, оглушение, бонус урона союзникам",
             weak="Медленные удары, совсем нет защиты от магии",
             prefers={"barbarian": 20, "rogue": 20, "spearman": 15, "knight": -25}),
    UnitType("archer", "ЛУЧНИК", "СТРЕЛОК", hp=165, armor=0.10, resist=0.10, damage=(15, 19),
             damage_type="physical", attack_range=175, cooldown=1.25, speed=42, ranged=True, lane="back",
             strong="Дальний бой, отходит от ближников, крит в голову, залп из 3 стрел",
             weak="Беспомощен в ближнем бою, стрелы блокирует щит рыцаря",
             prefers={"mage": 40, "rogue": 25, "cleric": 40, "necromancer": 30}),
    # --- ten new ones ----------------------------------------------------------------
    UnitType("paladin", "ПАЛАДИН", "СВЯТОЙ ВОИН", hp=370, armor=0.30, resist=0.20, damage=(15, 21),
             damage_type="holy", attack_range=17, cooldown=1.3, speed=33, blunt=True, radius=8,
             strong="Аура лечит союзников рядом, святая булава x1.5 по нежити, божественный щит при <30% HP",
             weak="Невысокий урон, медленный; щит спасает лишь раз",
             prefers={"skeleton": 40, "necromancer": 50}),
    UnitType("cleric", "ЖРИЦА", "ЛЕКАРЬ", hp=150, armor=0.0, resist=0.25, damage=(9, 13), damage_type="holy",
             attack_range=150, cooldown=2.0, speed=36, ranged=True, caster=True, lane="back",
             strong="Лечит самого раненого союзника (35-45 HP), снимает горение и кровотечение; святая искра по врагам",
             weak="Хрупкая, сама почти не наносит урона - первая цель убийц",
             prefers={"skeleton": 30, "necromancer": 30}),
    UnitType("crossbowman", "АРБАЛЕТЧИК", "БРОНЕБОЙЩИК", hp=200, armor=0.20, resist=0.10, damage=(36, 46),
             damage_type="physical", attack_range=185, cooldown=2.4, speed=34, ranged=True, lane="back",
             strong="Болт пробивает 75% брони и щит рыцаря, огромный урон за выстрел",
             weak="Долгая перезарядка, не отступает - в ближнем бою проигрывает",
             prefers={"knight": 45, "paladin": 40, "ogre": 30, "orc": 25, "hammerer": 25}),
    UnitType("necromancer", "НЕКРОМАНТ", "ПРИЗЫВАТЕЛЬ", hp=160, armor=0.0, resist=0.35, damage=(14, 19),
             damage_type="magic", attack_range=150, cooldown=2.0, speed=32, ranged=True, caster=True, lane="back",
             strong="Поднимает павших (любой стороны) скелетами-слугами, теневой снаряд лечит его самого",
             weak="Хрупкий, без трупов слаб; святой урон и паладин - его гибель",
             prefers={"cleric": 30, "mage": 20}),
    UnitType("skeleton", "СКЕЛЕТ", "НЕЖИТЬ", hp=300, armor=0.20, resist=0.30, damage=(20, 26),
             damage_type="physical", attack_range=16, cooldown=0.95, speed=39, undead=True,
             strong="Не чувствует кровотечения, восстаёт после смерти (если добит не дробящим и не святым)",
             weak="Дробящее оружие и святой урон x1.5, хрупкий без воскрешения",
             prefers={"archer": 15, "mage": 15}),
    UnitType("monk", "МОНАХ", "МАСТЕР БОЯ", hp=230, armor=0.10, resist=0.20, damage=(9, 12), damage_type="physical",
             attack_range=13, cooldown=0.5, speed=52, dodge=0.35, blunt=True, radius=6, lane="flank",
             strong="Шквал ударов, каждый 4-й удар оглушает и отбрасывает, уклонение 35% (и от стрел)",
             weak="Удары слабые - броня рыцаря и паладина их режет; в долгой рубке уступает громилам",
             prefers={"mage": 40, "archer": 35, "crossbowman": 45, "cleric": 40, "shaman": 35}),
    UnitType("hammerer", "МОЛОТОБОЕЦ", "СОКРУШИТЕЛЬ", hp=340, armor=0.30, resist=0.10, damage=(30, 38),
             damage_type="physical", attack_range=18, cooldown=1.9, speed=32, blunt=True, radius=8,
             strong="Дробящий молот пробивает броню, каждый 3-й удар - сотрясение земли: урон и оглушение вокруг",
             weak="Очень медленные удары и шаг, его легко расстрелять",
             prefers={"knight": 30, "paladin": 30, "skeleton": 30, "ogre": 15}),
    UnitType("shaman", "ШАМАН", "ГРОЗОВИК", hp=165, armor=0.05, resist=0.30, damage=(17, 23), damage_type="magic",
             attack_range=150, cooldown=2.5, speed=36, ranged=True, caster=True, lane="back",
             strong="Цепная молния прыгает на 3 врагов, замедляет; лечащий дождь союзникам раз в 12 с",
             weak="Молния слабеет с каждым прыжком, хрупок",
             prefers={"rogue": 20, "wolf": 20, "monk": 20}),
    UnitType("wolf", "ВОЛК", "ХИЩНИК", hp=245, armor=0.10, resist=0.05, damage=(12, 17), damage_type="physical",
             attack_range=15, cooldown=0.6, speed=72, dodge=0.15, radius=7, lane="flank",
             strong="Самый быстрый, укус вызывает кровотечение, стая: +20% урона за каждого волка рядом, вой",
             weak="Лёгкая броня, в одиночку быстро гибнет; копейщик бьёт его x1.6",
             prefers={"archer": 40, "mage": 40, "cleric": 45, "crossbowman": 40, "shaman": 35, "necromancer": 35}),
    UnitType("ogre", "ОГР", "ВЕЛИКАН", hp=560, armor=0.15, resist=0.0, damage=(38, 50), damage_type="physical",
             attack_range=22, cooldown=2.2, speed=27, blunt=True, radius=11,
             strong="Огромный запас HP, дубина отбрасывает и оглушает мелких, бьёт по нескольким",
             weak="Медленный и большой - мишень для стрелков, арбалетов и магии",
             prefers={"knight": 15, "spearman": 15}),
)}

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
