"""Unit roster: stats, roles, strengths/weaknesses and team-colored looks.

Damage model
------------
* physical damage is reduced by ``armor`` (fraction), magic by ``resist``;
* ``dodge`` - chance to avoid physical hits (melee and arrows);
* every unit has a niche and a counter (see ``strong`` / ``weak``).

Speeds are px/s on a 480x270 battlefield, ranges in px, cooldowns in seconds.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Dict, Tuple

from pixelforge.units.humanoid import HumanoidSpec


@dataclass(frozen=True)
class UnitType:
    key: str
    name: str                 # Russian display name
    role: str                 # tank | bruiser | caster | lancer | assassin | brute | marksman
    hp: int
    armor: float              # physical damage reduction 0..1
    resist: float             # magic damage reduction 0..1
    damage: Tuple[int, int]
    damage_type: str          # physical | magic
    attack_range: float
    cooldown: float
    speed: float
    dodge: float = 0.0
    ranged: bool = False
    radius: float = 7.0       # body size for collisions
    strong: str = ""
    weak: str = ""
    # target preferences: enemy type key -> score bonus (AI)
    prefers: Dict[str, float] = field(default_factory=dict)


ROSTER: Dict[str, UnitType] = {u.key: u for u in (
    UnitType("knight", "РЫЦАРЬ", "tank", hp=460, armor=0.45, resist=0.0, damage=(15, 21), damage_type="physical",
             attack_range=17, cooldown=1.25, speed=31, radius=8,
             strong="Щит блокирует стрелы и удары, защищает стрелков (провокация)",
             weak="Медленный, магия игнорирует броню",
             prefers={"rogue": 25, "barbarian": 10}),
    UnitType("barbarian", "ВАРВАР", "bruiser", hp=380, armor=0.12, resist=0.15, damage=(27, 36),
             damage_type="physical", attack_range=17, cooldown=1.3, speed=44,
             strong="Рывок в бой, рассекающий удар, казнь раненых (x1.5 при <30% HP), ярость и вампиризм при <50% HP",
             weak="Почти без брони; рывок на копейщика - x1.6 урона по себе, первым попадает под фокус",
             prefers={"mage": 15, "archer": 15}),
    UnitType("mage", "МАГ", "caster", hp=175, armor=0.0, resist=0.30, damage=(24, 30), damage_type="magic",
             attack_range=165, cooldown=2.8, speed=33, ranged=True,
             strong="Огненный шар по площади + горение, ледяная волна",
             weak="Хрупкий, медленно колдует - лёгкая цель для разбойника",
             prefers={"knight": 25, "orc": 25}),
    UnitType("spearman", "КОПЕЙЩИК", "lancer", hp=290, armor=0.25, resist=0.10, damage=(18, 24),
             damage_type="physical", attack_range=27, cooldown=1.15, speed=38,
             strong="Длинное копьё бьёт первым, x1.6 урона по разбойникам и по врагам в рывке, отбрасывает",
             weak="Слаб против стрел и магии издалека",
             prefers={"rogue": 35, "barbarian": 30, "orc": 25}),
    UnitType("rogue", "РАЗБОЙНИК", "assassin", hp=185, armor=0.10, resist=0.10, damage=(12, 16),
             damage_type="physical", attack_range=14, cooldown=0.7, speed=64, dodge=0.30, radius=6,
             strong="Обходит с фланга, шаг сквозь тень за спину стрелку, удар в спину x1.9 + кровотечение, уклонение, дымовая шашка",
             weak="Мелкие удары вязнут в броне рыцаря, боится копейщика",
             prefers={"mage": 130, "archer": 115}),
    UnitType("orc", "ОРК", "brute", hp=400, armor=0.25, resist=0.0, damage=(25, 32), damage_type="physical",
             attack_range=17, cooldown=1.4, speed=37, radius=8,
             strong="Регенерация, боевой клич: рывок, оглушение, бонус урона союзникам",
             weak="Медленные удары, совсем нет защиты от магии",
             prefers={"barbarian": 20, "rogue": 20, "spearman": 15, "knight": -25}),
    UnitType("archer", "ЛУЧНИК", "marksman", hp=165, armor=0.10, resist=0.10, damage=(11, 15),
             damage_type="physical", attack_range=175, cooldown=1.35, speed=42, ranged=True,
             strong="Дальний бой, отходит от ближников, крит в голову, залп из 3 стрел",
             weak="Беспомощен в ближнем бою, стрелы блокирует щит рыцаря",
             prefers={"mage": 40, "rogue": 25}),
)}

ORDER = ["knight", "barbarian", "spearman", "orc", "rogue", "archer", "mage"]


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


def spec_for(key: str, team: Team) -> HumanoidSpec:
    """Look of a unit type in a team's colors (cloth/cape/shield take the team color)."""
    c, a = team.color, team.accent
    specs = {
        "knight": HumanoidSpec(top="#8b9bb4", top_shiny=True, bottom="#5a6988", boots="#3a4466",
                               helmet="#c0cbdc", hair=None, weapon="sword", shield=a, cape=c, belt="#733e39"),
        "barbarian": HumanoidSpec(skin="#d77643", top=c, sleeves="#d77643", bottom="#733e39", boots="#3e2731",
                                  hair="#feae34" if team.key == "blue" else "#e43b44", hair_style="long",
                                  beard="#feae34" if team.key == "blue" else "#e43b44",
                                  helmet="#8b9bb4", helmet_style="horned", weapon="axe", build="stocky"),
        "mage": HumanoidSpec(top=c, robe=True, sleeves=c, bottom=c, boots="#3e2731", helmet=c, helmet_style="hood",
                             beard="#c0cbdc", hair="#c0cbdc", weapon="staff",
                             magic="#fee761" if team.key == "red" else "#2ce8f5", belt="#feae34", build="slim"),
        "spearman": HumanoidSpec(skin="#c28569", top=c, bottom="#5a6988", boots="#733e39", hair="#3e2731",
                                 helmet="#b86f50", weapon="spear", shield=a),
        "rogue": HumanoidSpec(top="#262b44", sleeves="#262b44", bottom="#3a4466", boots="#181425",
                              hair="#fee761" if team.key == "blue" else "#ead4aa", hair_style="spiky",
                              weapon="dagger", cape=c, build="slim", belt="#733e39"),
        "orc": HumanoidSpec(skin="#63c74d", eye="#e43b44", top=c, sleeves="#63c74d", bottom="#3e2731",
                            boots="#181425", hair="#181425", hair_style="spiky", weapon="axe",
                            weapon_color="#8b9bb4", build="stocky"),
        "archer": HumanoidSpec(top=c, sleeves=c, bottom="#733e39", boots="#3e2731", hair="#feae34",
                               helmet=a, helmet_style="hood", weapon="bow", handle_color="#b86f50",
                               cape=c, belt="#733e39", build="slim"),
    }
    return replace(specs[key], name=f"{key}_{team.key}")
