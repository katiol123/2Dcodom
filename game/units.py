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

from pixelforge.units.creatures import QuadSpec, SpiderSpec
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
    short: str = ""           # card label when the name is too long
    dodge_magic: bool = False # dodge also works against spells
    shield: Tuple[float, ...] = ()   # (block chance vs missiles, vs melee, melee damage kept) - from the front only
    goblin: bool = False      # goblin kin (crowd bonus, mad goblin aura)
    boss: bool = False        # deliberately overpowered; left out of random squads and the balance target
    hidden: bool = False      # not selectable (e.g. the druid's bear form)
    tier: str = "average"     # intended power: weak | below | average | above | boss (see TIERS)
    cost: int = 0             # hire price in gold (0 = from the tier, see price())
    upkeep: int = 0           # gold per turn
    incorporeal: bool = False # walks through other units (no collisions)
    missile_mult: float = 1.0 # damage taken from arrows, bolts and thrown rocks
    physical_mult: float = 1.0
    magic_mult: float = 1.0   # damage taken from magic and holy attacks
    fire_mult: float = 1.0    # damage taken from fire (fireballs, burning, fire flasks, fire dervish)
    immune: Tuple[str, ...] = ()   # statuses that never stick (stun, slow, root, fear, bleed, poison, burn)
    prefers: Dict[str, float] = field(default_factory=dict)   # AI target bonus by enemy type
    perks: Tuple[Tuple[str, str], ...] = ()      # (name, description): strengths
    flaws: Tuple[Tuple[str, str], ...] = ()      # weaknesses
    behavior: Tuple[Tuple[str, str], ...] = ()   # how the AI plays this unit


ROSTER: Dict[str, UnitType] = {u.key: u for u in (
    # --- original seven ----------------------------------------------------------
    UnitType("knight", "РЫЦАРЬ", "ТАНК", hp=430, armor=0.45, resist=0.0, damage=(15, 21), damage_type="physical",
             attack_range=17, cooldown=1.25, speed=31, radius=8, shield=(0.6, 0.3, 0.3),
             prefers={"rogue": 25, "barbarian": 10, "wolf": 15}),
    UnitType("barbarian", "ВАРВАР", "БОЕЦ", hp=310, armor=0.12, resist=0.15, damage=(22, 28),
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
    UnitType("orc", "ОРК", "ГРОМИЛА", hp=345, armor=0.25, resist=0.0, damage=(20, 27), damage_type="physical",
             attack_range=17, cooldown=1.4, speed=37, radius=8,
             prefers={"barbarian": 20, "rogue": 20, "spearman": 15, "knight": -25}),
    UnitType("archer", "ЛУЧНИК", "СТРЕЛОК", hp=165, armor=0.10, resist=0.10, damage=(17, 21),
             damage_type="physical", attack_range=175, cooldown=1.25, speed=42, ranged=True, lane="back",
             prefers={"mage": 40, "rogue": 25, "cleric": 40, "necromancer": 30}),
    # --- ten new ones ----------------------------------------------------------------
    UnitType("paladin", "ПАЛАДИН", "СВЯТОЙ ВОИН", hp=345, armor=0.30, resist=0.20, damage=(14, 20),
             damage_type="holy", attack_range=17, cooldown=1.3, speed=33, radius=8,
             prefers={"skeleton": 40, "necromancer": 50}),
    UnitType("cleric", "ЖРИЦА", "ЛЕКАРЬ", hp=150, armor=0.0, resist=0.25, damage=(9, 13), damage_type="holy",
             attack_range=150, cooldown=2.0, speed=36, ranged=True, caster=True, lane="back",
             prefers={"skeleton": 30, "necromancer": 30}),
    UnitType("crossbowman", "АРБАЛЕТЧИК", "БРОНЕБОЙЩИК", hp=215, armor=0.20, resist=0.10, damage=(36, 46),
             damage_type="physical", attack_range=185, cooldown=2.4, speed=34, ranged=True, lane="back",
             prefers={"knight": 45, "paladin": 40, "ogre": 30, "orc": 25, "hammerer": 25}),
    UnitType("necromancer", "НЕКРОМАНТ", "ПРИЗЫВАТЕЛЬ", hp=150, armor=0.0, resist=0.35, damage=(13, 17),
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
    UnitType("ogre", "ОГР", "ВЕЛИКАН", hp=510, armor=0.15, resist=0.0, damage=(38, 50), damage_type="physical",
             attack_range=22, cooldown=2.2, speed=27, blunt=True, radius=11,
             prefers={"knight": 15, "spearman": 15}, tier="above"),
    # --- goblin tribe -----------------------------------------------------------------
    UnitType("goblin", "ГОБЛИН", "ТРУС", hp=225, armor=0.05, resist=0.05, damage=(10, 14), damage_type="physical",
             attack_range=13, cooldown=0.7, speed=52, dodge=0.15, radius=5, goblin=True,
             prefers={"archer": 15, "mage": 15, "cleric": 15}, tier="below"),
    UnitType("wolf_rider", "ГОБЛИН НА ЛЮТОВОЛКЕ", "НАЛЁТЧИК", hp=280, armor=0.15, resist=0.15, damage=(18, 23),
             damage_type="physical", attack_range=17, cooldown=0.9, speed=70, dodge=0.30, dodge_magic=True,
             radius=8, lane="flank", short="НАЕЗДНИК", goblin=True,
             prefers={"archer": 60, "mage": 60, "cleric": 60, "crossbowman": 55, "shaman": 50, "necromancer": 50,
                      "goblin_shaman": 50}, tier="above"),
    UnitType("mad_goblin", "БЕЗУМНЫЙ ГОБЛИН", "БЕРСЕРК", hp=290, armor=0.20, resist=0.10, damage=(24, 31),
             damage_type="physical", attack_range=17, cooldown=1.3, speed=44, radius=6, short="БЕЗУМЕЦ",
             shield=(0.4, 0.2, 0.0), goblin=True,
             prefers={"spearman": 10, "barbarian": 10}),
    UnitType("goblin_shaman", "ГОБЛИН-ШАМАН", "ПОДСТРЕКАТЕЛЬ", hp=180, armor=0.0, resist=0.20, damage=(12, 16),
             damage_type="magic", attack_range=140, cooldown=1.8, speed=40, ranged=True, caster=True, lane="back",
             radius=5, short="Г.ШАМАН", goblin=True,
             prefers={"rogue": 15, "wolf": 15}),
    UnitType("goblin_bomber", "ГОБЛИН-ПОДРЫВНИК", "СМЕРТНИК", hp=150, armor=0.0, resist=0.0, damage=(220, 260),
             damage_type="physical", attack_range=12, cooldown=1.0, speed=66, radius=5, lane="flank",
             short="ПОДРЫВНИК", goblin=True, tier='weak'),
    UnitType("bog_spider", "БОЛОТНЫЙ ПАУК", "ЛОВЕЦ", hp=270, armor=0.15, resist=0.10, damage=(13, 17),
             damage_type="physical", attack_range=15, cooldown=0.85, speed=54, radius=8, short="ПАУК",
             prefers={"rogue": 20, "wolf": 20, "wolf_rider": 25, "lancer": 25, "mamluk": 25}, tier='average'),
    # --- Королевство Альдерн --------------------------------------------------------------
    UnitType("griffon_knight", "ГРИФОНИЙ РЫЦАРЬ", "ЛЕТУН", hp=400, armor=0.30, resist=0.10, damage=(21, 27),
             damage_type="physical", attack_range=18, cooldown=1.25, speed=56, radius=9, lane="flank",
             short="ГРИФОН", missile_mult=1.3,
             prefers={"archer": 50, "mage": 50, "cleric": 50, "crossbowman": 45, "ranger": 45, "ice_witch": 45,
                      "shaman": 40, "alchemist": 40}, tier="above"),
    UnitType("lancer", "КОННЫЙ РЫЦАРЬ", "КАВАЛЕРИЯ", hp=430, armor=0.35, resist=0.05, damage=(24, 30),
             damage_type="physical", attack_range=18, cooldown=1.4, speed=60, radius=10, short="ВСАДНИК",
             prefers={"archer": 20, "mage": 20, "crossbowman": 20}, tier="above"),
    UnitType("uhlan", "УЛАН", "КОПЕЙНАЯ КАВАЛЕРИЯ", hp=400, armor=0.30, resist=0.10, damage=(22, 28),
             damage_type="physical", attack_range=24, cooldown=1.3, speed=64, radius=10, short="УЛАН",
             prefers={"archer": 20, "mage": 20, "crossbowman": 20, "wolf": 20, "barbarian": 15, "wolf_rider": 20},
             tier="above"),
    # --- Вельдмар ----------------------------------------------------------------------------
    UnitType("ranger", "ЛЕСНОЙ ЕГЕРЬ", "СТРЕЛОК", hp=165, armor=0.10, resist=0.15, damage=(23, 29),
             damage_type="physical", attack_range=190, cooldown=1.5, speed=46, ranged=True, lane="back",
             short="ЕГЕРЬ", prefers={"mage": 50, "cleric": 55, "shaman": 45, "necromancer": 45, "dryad": 45}),
    UnitType("dryad", "ДРИАДА", "ЦЕЛИТЕЛЬ", hp=170, armor=0.05, resist=0.25, damage=(10, 14), damage_type="magic",
             attack_range=150, cooldown=2.0, speed=40, ranged=True, caster=True, lane="back", fire_mult=1.5),
    UnitType("treant", "ДРЕВЕНЬ", "ВЕЛИКАН", hp=600, armor=0.30, resist=0.15, damage=(28, 36),
             damage_type="physical", attack_range=22, cooldown=2.2, speed=23, blunt=True, radius=12,
             missile_mult=0.5, fire_mult=1.5, tier="above"),
    UnitType("druid", "ДРУИД", "ОБОРОТЕНЬ", hp=220, armor=0.05, resist=0.25, damage=(14, 18), damage_type="magic",
             attack_range=140, cooldown=2.0, speed=38, ranged=True, caster=True, lane="back"),
    UnitType("bear", "МЕДВЕДЬ", "ОБЛИК ДРУИДА", hp=480, armor=0.20, resist=0.15, damage=(24, 30),
             damage_type="physical", attack_range=16, cooldown=1.1, speed=48, radius=9, hidden=True),
    UnitType("bladedancer", "ТАНЦУЮЩИЙ С КЛИНКАМИ", "ДУЭЛЯНТ", hp=240, armor=0.10, resist=0.15, damage=(13, 17),
             damage_type="physical", attack_range=15, cooldown=0.8, speed=56, dodge=0.35, radius=6, lane="flank",
             short="КЛИНКИ", prefers={"rogue": 40, "wolf": 30, "assassin": 40, "monk": 30}),
    # --- Пепельное герцогство ----------------------------------------------------------------
    UnitType("death_knight", "РЫЦАРЬ СМЕРТИ", "ТАНК", hp=430, armor=0.40, resist=0.30, damage=(19, 25),
             damage_type="physical", attack_range=17, cooldown=1.4, speed=30, undead=True, radius=8,
             short="Р.СМЕРТИ", prefers={"paladin": 50, "cleric": 50, "monk": 35}, tier="above"),
    UnitType("wraith", "ПРИЗРАК", "УБИЙЦА", hp=240, armor=0.0, resist=0.0, damage=(15, 19), damage_type="magic",
             attack_range=15, cooldown=1.0, speed=50, undead=True, radius=6, lane="flank", incorporeal=True,
             physical_mult=0.5, magic_mult=1.3, immune=("bleed", "poison"),
             prefers={"archer": 60, "mage": 55, "cleric": 60, "crossbowman": 55, "ranger": 55, "shaman": 50}),
    UnitType("banshee", "БАНШИ", "КРИКУН", hp=185, armor=0.0, resist=0.30, damage=(17, 21), damage_type="magic",
             attack_range=140, cooldown=2.0, speed=40, ranged=True, caster=True, lane="back", undead=True,
             immune=("bleed", "poison")),
    UnitType("ghoul", "ГУЛЬ", "ПАДАЛЬЩИК", hp=290, armor=0.10, resist=0.15, damage=(14, 19),
             damage_type="physical", attack_range=13, cooldown=0.8, speed=50, undead=True, radius=6,
             immune=("bleed", "poison")),
    UnitType("vampire", "ВАМПИР", "ДВОРЯНИН", hp=285, armor=0.15, resist=0.25, damage=(18, 24),
             damage_type="physical", attack_range=16, cooldown=1.0, speed=48, undead=True, radius=6, lane="flank",
             immune=("bleed", "poison"),
             prefers={"cleric": 45, "mage": 40, "dryad": 40, "shaman": 35, "necromancer": 30}),
    # --- Каганат -------------------------------------------------------------------------------
    UnitType("horse_archer", "КОННЫЙ ЛУЧНИК", "КАВАЛЕРИЯ", hp=280, armor=0.10, resist=0.10, damage=(16, 20),
             damage_type="physical", attack_range=150, cooldown=1.2, speed=64, ranged=True, radius=9, lane="flank",
             short="К.ЛУЧНИК", prefers={"mage": 30, "cleric": 30, "archer": 15}),
    UnitType("war_drummer", "БОЕВОЙ БАРАБАНЩИК", "ПОДДЕРЖКА", hp=230, armor=0.10, resist=0.10, damage=(9, 12),
             damage_type="physical", attack_range=14, cooldown=1.0, speed=40, lane="back", short="БАРАБАН", tier="below"),
    # --- Зархад --------------------------------------------------------------------------------
    UnitType("mamluk", "МАМЛЮК", "КАВАЛЕРИЯ", hp=430, armor=0.30, resist=0.10, damage=(22, 28),
             damage_type="physical", attack_range=19, cooldown=1.2, speed=60, radius=10,
             prefers={"archer": 15, "mage": 15}, tier="above"),
    UnitType("war_elephant", "БОЕВОЙ СЛОН", "КОЛОСС", hp=500, armor=0.30, resist=0.10, damage=(26, 34),
             damage_type="physical", attack_range=26, cooldown=2.4, speed=25, blunt=True, radius=15,
             short="СЛОН", immune=("stun",), tier="above"),
    UnitType("fire_dervish", "ОГНЕННЫЙ ДЕРВИШ", "МАГ ВИХРЯ", hp=260, armor=0.05, resist=0.30, damage=(13, 17),
             damage_type="magic", attack_range=17, cooldown=1.1, speed=50, radius=6, short="ДЕРВИШ",
             immune=("burn",)),
    UnitType("assassin", "АССАСИН", "УБИЙЦА", hp=190, armor=0.10, resist=0.15, damage=(12, 16),
             damage_type="physical", attack_range=14, cooldown=0.75, speed=62, dodge=0.25, radius=6, lane="flank"),
    # --- Север -----------------------------------------------------------------------------------
    UnitType("valkyrie", "ВАЛЬКИРИЯ", "ЛЕТУНЬЯ", hp=340, armor=0.25, resist=0.20, damage=(20, 25),
             damage_type="physical", attack_range=22, cooldown=1.15, speed=50, radius=7, lane="flank", tier="above"),
    UnitType("ice_witch", "ЛЕДЯНАЯ ВЕДЬМА", "КОЛДУНЬЯ", hp=185, armor=0.0, resist=0.30, damage=(18, 23),
             damage_type="magic", attack_range=155, cooldown=2.0, speed=36, ranged=True, caster=True, lane="back",
             short="ВЕДЬМА", fire_mult=1.5, prefers={"barbarian": 20, "orc": 20, "ogre": 20, "lancer": 25}),
    UnitType("frost_giant", "ЛЕДЯНОЙ ВЕЛИКАН", "ВЕЛИКАН", hp=720, armor=0.20, resist=0.20, damage=(36, 44),
             damage_type="physical", attack_range=125, cooldown=2.2, speed=24, ranged=True, caster=True, radius=12,
             short="Л.ВЕЛИКАН", immune=("slow", "root", "freeze", "burn"), tier="above"),
    # --- Лига ------------------------------------------------------------------------------------
    UnitType("halberdier", "АЛЕБАРДЩИК", "СТРАЖ", hp=340, armor=0.30, resist=0.10, damage=(22, 28),
             damage_type="physical", attack_range=26, cooldown=1.4, speed=34, radius=8, short="АЛЕБАРДА",
             prefers={"knight": 25, "paladin": 20, "shieldbearer": 25, "lancer": 25, "mamluk": 25}),
    UnitType("duelist", "ДУЭЛЯНТ", "ФЕХТОВАЛЬЩИК", hp=250, armor=0.15, resist=0.15, damage=(16, 21),
             damage_type="physical", attack_range=18, cooldown=0.9, speed=50, radius=6),
    UnitType("alchemist", "АЛХИМИК", "БОМБИСТ", hp=175, armor=0.05, resist=0.15, damage=(18, 22), damage_type="magic",
             attack_range=130, cooldown=2.2, speed=38, ranged=True, caster=True, lane="back"),
    # --- Дургхейм --------------------------------------------------------------------------------
    UnitType("shieldbearer", "ГОРНЫЙ ЩИТОНОСЕЦ", "ТАНК", hp=450, armor=0.40, resist=0.10, damage=(14, 18),
             damage_type="physical", attack_range=15, cooldown=1.3, speed=28, radius=8, short="ЩИТОНОСЕЦ",
             shield=(0.8, 0.5, 0.25)),
    UnitType("rune_priest", "РУННЫЙ ЖРЕЦ", "ПОДДЕРЖКА", hp=195, armor=0.15, resist=0.30, damage=(11, 15),
             damage_type="magic", attack_range=140, cooldown=2.0, speed=32, ranged=True, caster=True, lane="back",
             short="Р.ЖРЕЦ"),
    UnitType("iron_golem", "ЖЕЛЕЗНЫЙ ГОЛЕМ", "КОЛОСС", hp=560, armor=0.50, resist=0.0, damage=(26, 34),
             damage_type="physical", attack_range=18, cooldown=2.0, speed=22, blunt=True, radius=11, short="ГОЛЕМ",
             missile_mult=0.25, magic_mult=1.3, immune=("bleed", "poison", "stun", "fear"), tier="above"),
    # --- дешёвые отряды (их нанимают, когда не хватает золота) и гарпунщик ------------------------
    UnitType("militia", "ОПОЛЧЕНЕЦ", "ПИКИНЁР", hp=200, armor=0.10, resist=0.05, damage=(12, 16),
             damage_type="physical", attack_range=25, cooldown=1.3, speed=38, tier="weak",
             prefers={"barbarian": 20, "wolf": 15, "lancer": 25, "mamluk": 25, "wolf_rider": 20}),
    UnitType("slinger", "ПРАЩНИК", "МЕТАТЕЛЬ", hp=140, armor=0.05, resist=0.05, damage=(9, 12),
             damage_type="physical", attack_range=150, cooldown=1.4, speed=44, ranged=True, lane="back",
             tier="weak", prefers={"mage": 20, "cleric": 20}),
    UnitType("zombie", "ЗОМБИ", "МЕРТВЕЦ", hp=260, armor=0.0, resist=0.10, damage=(10, 14),
             damage_type="physical", attack_range=13, cooldown=1.2, speed=22, undead=True, tier="weak",
             immune=("bleed", "poison", "fear")),
    UnitType("war_dog", "БОЕВОЙ ПЁС", "ГОНЧАЯ", hp=150, armor=0.05, resist=0.05, damage=(9, 13),
             damage_type="physical", attack_range=14, cooldown=0.7, speed=70, dodge=0.10, radius=6, lane="flank",
             short="ПЁС", tier="weak",
             prefers={"archer": 35, "mage": 35, "cleric": 40, "crossbowman": 35, "slinger": 35}),
    UnitType("harpooner", "ГАРПУНЩИК", "ЛОВЕЦ", hp=330, armor=0.15, resist=0.10, damage=(19, 24),
             damage_type="physical", attack_range=22, cooldown=1.2, speed=42, short="ГАРПУН",
             prefers={"archer": 35, "mage": 35, "cleric": 35, "crossbowman": 35, "ranger": 35, "slinger": 25,
                      "ice_witch": 35, "shaman": 30, "alchemist": 30}),
    UnitType("troll", "ТРОЛЛЬ-МУСОРЩИК", "БОСС", hp=950, armor=0.45, resist=0.10, damage=(52, 66),
             damage_type="physical", attack_range=24, cooldown=2.8, speed=22, blunt=True, radius=12, short="ТРОЛЛЬ", boss=True, tier="boss"),
)}

# --- descriptions: perks (green), flaws (red), behavior (blue) --------------------------
# Every line is one independent trait: "NAME", "short description".  Keep them in
# sync with the mechanics in sim.py / ai.py.  Plain stats (HP, armor, speed, damage,
# range, cooldown, dodge) are shown separately and are NOT traits.

TRAITS: Dict[str, Dict[str, Tuple[Tuple[str, str], ...]]] = {
    "knight": dict(
        perks=(("ЩИТ", "блокирует 60% стрел и 30% ударов спереди"),
               ("ПРОВОКАЦИЯ", "заставляет врага, прорвавшегося к стрелкам, биться с ним 3.5 с (раз в 9 с)")),
        flaws=(("ОТКРЫТАЯ СПИНА", "щит не защищает сзади и от арбалетных болтов"),),
        behavior=(("ТЕЛОХРАНИТЕЛЬ", "первым делом атакует тех, кто напал на своих стрелков"),)),
    "barbarian": dict(
        perks=(("РЫВОК", "бросается к врагу с ускорением x1.9 (раз в 10 с)"),
               ("РАССЕЧЕНИЕ", "50% урона задевает врагов рядом с целью"),
               ("КАЗНЬ", "x1.4 урона по врагам с HP ниже 30%"),
               ("ЯРОСТЬ", "при HP ниже 50% бьёт в 1.7 раза чаще"),
               ("ВАМПИРИЗМ", "в ярости лечится на 25% нанесённого урона")),
        behavior=(("ПАЛАЧ", "охотится на самых раненых врагов"),)),
    "mage": dict(
        perks=(("ОГНЕННЫЙ ШАР", "взрыв бьёт всех врагов в радиусе"),
               ("ПОДЖОГ", "взрыв поджигает: 6 урона в секунду 3 с"),
               ("ЛЕДЯНАЯ ВОЛНА", "отталкивает и замедляет на 50% подошедших вплотную (раз в 9 с)")),
        behavior=(("АРТИЛЛЕРИСТ", "бьёт туда, где врагов больше всего"),
                  ("ОСТОРОЖНОСТЬ", "держит дистанцию и отступает от ближников"))),
    "spearman": dict(
        perks=(("КОНТРУДАР", "встречает копьём любого врага в рывке, до которого дотянется: +100% урона и "
                             "отбрасывает"),
               ("СЛОМАННЫЙ РЫВОК", "контрудар обрывает рывок врага и его оглушающий удар")),
        behavior=(("ЛОВЕЦ РЫВКОВ", "в первую очередь целится во врагов в рывке"),)),
    "rogue": dict(
        perks=(("ШАГ СКВОЗЬ ТЕНЬ", "телепорт за спину стрелку или магу (раз в 12 с)"),
               ("УДАР В СПИНУ", "x1.9 урона, если враг смотрит не на него"),
               ("КРОВОТЕЧЕНИЕ", "удар в спину отнимает ещё 6 HP в секунду 3 с"),
               ("ДЫМОВАЯ ШАШКА", "при HP ниже 35% исчезает в дыму (раз за бой)")),
        behavior=(("ОБХОД С ФЛАНГА", "бежит по краю поля и ищет стрелков и магов"),)),
    "orc": dict(
        perks=(("РЕГЕНЕРАЦИЯ", "4 HP в секунду, 8 если давно не получал урон"),
               ("БОЕВОЙ КЛИЧ", "рывок к врагу, первый удар оглушает на 1.1 с (раз в 16 с)"),
               ("ВООДУШЕВЛЕНИЕ", "клич даёт союзникам рядом +20% урона на 6 с")),
        behavior=(("ВЫЗОВ СИЛЬНЕЙШЕМУ", "ищет драки с самым крепким бойцом ближнего боя"),)),
    "archer": dict(
        perks=(("ВЫСТРЕЛ В ГОЛОВУ", "20% шанс двойного урона"),
               ("ЗАЛП", "3 стрелы по разным целям (раз в 9 с)")),
        flaws=(("ЩИТ ПРОТИВ СТРЕЛ", "рыцарь ловит щитом большинство стрел"),
               ("НАВЕСНАЯ СТРЕЛЬБА", "по быстрой цели стрела может промахнуться")),
        behavior=(("КАЙТ", "держит дистанцию, отходит от ближников и стреляет на отходе"),)),
    "paladin": dict(
        perks=(("АУРА ИСЦЕЛЕНИЯ", "союзники рядом восстанавливают 1.6 HP в секунду"),
               ("СВЯТАЯ БУЛАВА", "урон святой, по нежити x1.5"),
               ("БОЖЕСТВЕННЫЙ ЩИТ", "смертельный удар делает его неуязвимым на 3 с (раз за бой)")),
        behavior=(("КРЕСТОНОСЕЦ", "в первую очередь идёт на нежить и некромантов"),)),
    "cleric": dict(
        perks=(("ИСЦЕЛЕНИЕ", "лечит самого раненого союзника на 35-45 HP"),
               ("ОЧИЩЕНИЕ", "лечение снимает горение и кровотечение"),
               ("СВЯТАЯ ИСКРА", "если лечить некого, бьёт врагов (нежить x1.5)")),
        behavior=(("СИДЕЛКА", "держится возле раненых союзников"),
                  ("ОСТОРОЖНОСТЬ", "отступает от ближников"))),
    "crossbowman": dict(
        perks=(("БРОНЕБОЙНЫЙ БОЛТ", "игнорирует 75% брони"),
               ("СКВОЗЬ ЩИТ", "болт не блокируется щитом рыцаря"),
               ("ОТБРАСЫВАНИЕ", "болт отталкивает цель")),
        behavior=(("ОХОТНИК ЗА БРОНЁЙ", "выбирает самых бронированных врагов"),
                  ("СТОИТ НАСМЕРТЬ", "никогда не отступает"))),
    "necromancer": dict(
        perks=(("ПОДНЯТЬ МЁРТВЫХ", "превращает труп любой стороны в скелета-слугу (до 2, раз в 8 с)"),
               ("ПОХИЩЕНИЕ ЖИЗНИ", "теневой снаряд лечит его на 50% урона")),
        behavior=(("СТЕРВЯТНИК", "подбирается к свежим трупам, чтобы поднять их"),)),
    "skeleton": dict(
        perks=(("ВОССТАНИЕ", "через 2.5 с после смерти встаёт с 70% HP (раз за бой)"),
               ("БЕСКРОВНЫЙ", "не бывает кровотечения")),
        flaws=(("ХРУПКИЕ КОСТИ", "дробящее оружие x1.5 и не даёт восстать"),
               ("НЕЧИСТЬ", "святой урон x1.5 и не даёт восстать")),
        behavior=(("МЁРТВАЯ ХВАТКА", "не меняет цель, пока она жива"),)),
    "monk": dict(
        perks=(("КОМБО", "каждый 4-й удар оглушает на 0.7 с и отбрасывает"),
               ("ДРОБЯЩИЕ КУЛАКИ", "игнорируют 30% брони, нежить x1.5")),
        behavior=(("ПЕРЕХВАТЧИК", "ловит врагов, напавших на своих стрелков, иначе охотится на чужих"),)),
    "hammerer": dict(
        perks=(("ДРОБЯЩИЙ МОЛОТ", "игнорирует 30% брони, нежить x1.5"),
               ("СОТРЯСЕНИЕ", "каждый 3-й удар оглушает всех врагов вокруг и ранит их")),
        behavior=(("В САМУЮ ГУЩУ", "идёт туда, где врагов больше всего"),)),
    "shaman": dict(
        perks=(("ЦЕПНАЯ МОЛНИЯ", "бьёт цель и перескакивает ещё на 2 врагов"),
               ("ЗАМЕДЛЕНИЕ", "молния замедляет на 50% на 1.5 с"),
               ("ЦЕЛЕБНЫЙ ДОЖДЬ", "лечит союзников вокруг на 25 HP (раз в 12 с)")),
        flaws=(("ЗАТУХАНИЕ", "каждый прыжок молнии слабее на 30%"),),
        behavior=(("ГРОЗОВИК", "целится в скопления врагов"),
                  ("ОСТОРОЖНОСТЬ", "отступает от ближников"))),
    "wolf": dict(
        perks=(("УКУС", "вызывает кровотечение: 6 HP в секунду 2.5 с"),
               ("СТАЯ", "+20% урона за каждого волка рядом"),
               ("ВОЙ", "первый вой даёт рывок всем волкам рядом (раз за бой)")),
        behavior=(("ОХОТА СТАЕЙ", "бросается на ту же добычу, что и другие волки"),
                  ("ОБХОД С ФЛАНГА", "бежит по краю поля к стрелкам и магам"))),
    "ogre": dict(
        perks=(("РАЗМАХ ДУБИНЫ", "50% урона задевает врагов рядом с целью"),
               ("СОКРУШАЮЩИЙ УДАР", "отбрасывает, мелких врагов оглушает на 0.5 с"),
               ("ДРОБЯЩАЯ ДУБИНА", "игнорирует 30% брони, нежить x1.5")),
        behavior=(("ДАВКА", "идёт туда, где врагов больше всего, чтобы задеть многих"),)),
    "goblin": dict(
        perks=(("ОТРАВЛЕННЫЙ НОЖ", "удар отравляет: 4 HP в секунду 4 с"),
               ("УДАР ИСПОДТИШКА", "+50% урона, если враг бьётся с кем-то другим"),
               ("ГОБЛИНСКАЯ ТОЛПА", "+10% урона за каждого гоблина рядом (до +30%)")),
        behavior=(("ТРУСЛИВЫЙ", "при HP ниже 30% убегает с поля боя на 8 с (раз за бой)"),)),
    "wolf_rider": dict(
        perks=(("РЫВОК", "лютоволк бросается к врагу с ускорением x1.9 (раз в 9 с)"),
               ("УВОРОТ ОТ МАГИИ", "уклонение работает и против заклинаний"),
               ("НАЕЗДНИК УЦЕЛЕЛ", "при гибели с шансом 30% гоблин спрыгивает живым (50% HP)")),
        behavior=(("НАЛЁТЧИК", "обходит по краю поля и бьёт по стрелкам и магам"),)),
    "mad_goblin": dict(
        perks=(("АУРА БЕЗУМИЯ", "гоблины-союзники рядом не трусят"),
               ("БЛОК ТОПОРОМ", "отбивает 40% стрел и 20% ударов спереди"),
               ("РЖАВОЕ ЛЕЗВИЕ", "удар вызывает кровотечение: 6 HP в секунду 3 с")),
        flaws=(("ОТКРЫТАЯ СПИНА", "топор не защищает сзади и от арбалетных болтов"),),
        behavior=(("ВОЖАК", "бросается на тех, кто бьёт его гоблинов"),)),
    "goblin_shaman": dict(
        perks=(("ГРИБНОЕ БЕШЕНСТВО", "до 2 союзников впадают в ярость на 5 с: бьют в 1.7 раза чаще, на 20% "
                                    "сильнее и быстрее бегают (раз в 4 с)"),
               ("ЯДОВИТЫЕ СПОРЫ", "снаряд отравляет: 4 HP в секунду 3 с")),
        behavior=(("ПОДСТРЕКАТЕЛЬ", "бешенство достаётся тем, кто уже в гуще боя"),
                  ("ОСТОРОЖНОСТЬ", "отступает от ближников"))),
    "militia": dict(
        perks=(("ПИКА", "встречает пикой любого врага в рывке, до которого дотянется: +100% урона и отбрасывает"),),
        flaws=(("ДРОГНУЛ", "при HP ниже 25% бежит к своим 3 с (раз за бой)"),),
        behavior=(("ЛОВЕЦ РЫВКОВ", "в первую очередь целится во врагов в рывке"),)),
    "slinger": dict(
        perks=(("ТЯЖЁЛЫЙ КАМЕНЬ", "15% шанс оглушить цель на 0.5 с"),),
        behavior=(("ОСТОРОЖНОСТЬ", "держит дистанцию и отступает от ближников"),)),
    "zombie": dict(
        perks=(("ГНИЛОЙ УКУС", "удар отравляет: 4 HP в секунду 3 с"),
               ("БЕССТРАШНЫЙ", "не бывает страха, кровотечения и яда")),
        flaws=(("НЕЧИСТЬ", "святой урон и дробящее оружие x1.5"),),
        behavior=(("БРЕДЁТ", "идёт на ближайшего врага"),)),
    "war_dog": dict(
        perks=(("ХВАТКА", "укус замедляет на 50% на 1 с"),),
        behavior=(("ГОНЧАЯ", "бежит по краю поля к стрелкам и магам"),)),
    "harpooner": dict(
        perks=(("ГАРПУН", "притягивает к себе стрелка или мага с 40-120 px: 70% урона и оглушение 0.6 с "
                          "(раз в 8 с)"),),
        behavior=(("ЛОВЕЦ СТРЕЛКОВ", "охотится за стрелками и магами"),)),
    "goblin_bomber": dict(
        perks=(("БАБАХ!", "добежав до врагов, взрывается: огненный урон по всем вокруг, мимо брони и щитов"),
               ("ДЕТОНАЦИЯ", "убитый, всё равно взрывается с половиной силы")),
        flaws=(("СМЕРТНИК", "гибнет при взрыве"),
               ("ЗАДЕВАЕТ СВОИХ", "союзники рядом получают треть урона взрыва")),
        behavior=(("ВЫЖИДАЕТ", "ждёт, пока завяжется бой, и бежит в самую гущу раненых врагов"),)),
    "bog_spider": dict(
        perks=(("ПАУТИНА", "плюёт паутиной: цель не может двигаться 2.5 с (раз в 7 с)"),
               ("ЯДОВИТЫЙ УКУС", "укус отравляет: 4 HP в секунду 4 с")),
        behavior=(("ЛОВЕЦ", "паутиной в первую очередь ловит ныряльщиков и всадников"),)),
    "griffon_knight": dict(
        perks=(("ПИКИРОВАНИЕ", "перелетает к стрелку или магу и бьёт сверху: x2 урона и оглушение 0.8 с "
                               "(раз в 9 с)"),),
        flaws=(("МИШЕНЬ В НЕБЕ", "стрелы и болты наносят ему +30% урона"),),
        behavior=(("ОХОТНИК НА СТРЕЛКОВ", "выбирает стрелков и магов"),)),
    "lancer": dict(
        perks=(("ТАРАННЫЙ УДАР", "разгон к врагу: конь сшибает, первый удар мечом x2.5 и отбрасывает "
                                 "(раз в 7 с)"),),
        flaws=(("БЕЗ РАЗГОНА", "обычные удары на 15% слабее"),
               ("КОПЬЯ", "копейщики и алебардщики встречают разгон контрударом")),
        behavior=(("НАСКОК", "после таранного удара отъезжает для нового разгона"),)),
    "uhlan": dict(
        perks=(("НАСКОК С ПИКОЙ", "разгон к врагу: первый удар x2 и отбрасывает; перезарядка всего 4 с"),
               ("КОНТРУДАР", "встречает пикой любого врага в рывке, до которого дотянется: +100% урона, "
                             "рывок сломан, враг сбит с ног")),
        flaws=(("КОПЬЯ", "копейщики и алебардщики встречают его разгон контрударом"),),
        behavior=(("РАЗБЕГ", "когда разгон готов, выходит из ближнего боя и отъезжает, чтобы снова ударить "
                             "с разбега"),)),
    "ranger": dict(
        perks=(("МАСКИРОВКА", "невидим для врагов, пока не выстрелит; снова скрывается через 5 с без урона"),
               ("ВЫСТРЕЛ ИЗ ЗАСАДЫ", "выстрел из маскировки наносит двойной урон")),
        behavior=(("СНАЙПЕР", "выбирает лекарей и магов"),
                  ("ОСТОРОЖНОСТЬ", "отступает от ближников"))),
    "dryad": dict(
        perks=(("ЖИВИЦА", "лечит самого раненого союзника на 25-32 HP"),
               ("ОПУТЫВАНИЕ", "корни держат на месте ближника у союзников 2.5 с (раз в 8 с)")),
        flaws=(("ГОРЮЧАЯ", "огонь наносит ей x1.5 урона"),),
        behavior=(("СИДЕЛКА", "держится возле раненых союзников"),
                  ("ОСТОРОЖНОСТЬ", "отступает от ближников"))),
    "treant": dict(
        perks=(("КОРНИ", "каждый 3-й удар опутывает всех врагов вокруг на 1.5 с"),
               ("КОРА", "стрелы и болты наносят ему 50% урона"),
               ("ТЯЖЁЛЫЕ ВЕТВИ", "дробящий удар: игнорирует 30% брони, нежить x1.5")),
        flaws=(("ГОРЮЧИЙ", "огонь наносит ему x1.5 урона"),),
        behavior=(("ЗАСЛОН", "атакует тех, кто напал на своих стрелков"),)),
    "druid": dict(
        perks=(("ОБОРОТЕНЬ", "при HP ниже 50% превращается в медведя (раз за бой)"),
               ("ЗВЕРИНАЯ СИЛА", "превращение восстанавливает 40% здоровья")),
        behavior=(("ОСТОРОЖНОСТЬ", "в облике человека держится позади"),)),
    "bear": dict(
        perks=(("МЕДВЕЖЬЯ ЛАПА", "удар вызывает кровотечение: 6 HP в секунду 3 с"),),
        behavior=(("ЗВЕРЬ", "бросается на ближайшего врага"),)),
    "bladedancer": dict(
        perks=(("ВИХРЬ КЛИНКОВ", "каждый 3-й удар задевает всех врагов вокруг (70% урона)"),
               ("ТАНЕЦ", "после уклонения бьёт без перезарядки")),
        behavior=(("ПЕРЕХВАТЧИК", "ловит врагов, напавших на своих стрелков"),)),
    "death_knight": dict(
        perks=(("ПОХИЩЕНИЕ ЖИЗНИ", "лечится на 30% нанесённого урона"),
               ("ЛЕДЯНОЙ КЛИНОК", "удар замедляет на 50% на 1.5 с"),
               ("МЁРТВАЯ ПЛОТЬ", "не бывает кровотечения и яда")),
        flaws=(("НЕЧИСТЬ", "святой урон и дробящее оружие x1.5"),),
        behavior=(("ОХОТНИК НА СВЯТЫХ", "первым делом идёт на паладинов, жриц и монахов"),)),
    "wraith": dict(
        perks=(("БЕСПЛОТНЫЙ", "физический урон по нему вдвое меньше"),
               ("СКВОЗЬ СТРОЙ", "проходит сквозь бойцов"),
               ("ЛЕДЯНОЕ КАСАНИЕ", "удары магические и не смотрят на броню")),
        flaws=(("НЕЧИСТЬ", "святой урон и дробящее оружие x1.5"),
               ("УЯЗВИМ К МАГИИ", "магия наносит ему +30% урона")),
        behavior=(("НАЛЁТ", "пролетает сквозь строй к стрелкам и магам"),)),
    "banshee": dict(
        perks=(("ВОПЛЬ", "враги вокруг в ужасе бегут 1.5 с и замедлены (раз в 9 с)"),
               ("МЁРТВАЯ ПЛОТЬ", "не бывает кровотечения и яда")),
        flaws=(("НЕЧИСТЬ", "святой урон и дробящее оружие x1.5"),),
        behavior=(("ОСТОРОЖНОСТЬ", "держит дистанцию; вопит, когда враги подошли"),)),
    "ghoul": dict(
        perks=(("ПОЖИРАТЕЛЬ", "раненый, съедает труп рядом: +70 HP (раз в 6 с)"),
               ("ГНИЛЫЕ КОГТИ", "удар отравляет: 4 HP в секунду 4 с"),
               ("МЁРТВАЯ ПЛОТЬ", "не бывает кровотечения и яда")),
        flaws=(("НЕЧИСТЬ", "святой урон и дробящее оружие x1.5"),),
        behavior=(("ПАДАЛЬЩИК", "охотится на самых раненых"),)),
    "vampire": dict(
        perks=(("ВАМПИРИЗМ", "лечится на 40% нанесённого урона"),
               ("СТАЯ МЫШЕЙ", "при HP ниже 30% рассыпается мышами: 2 с неуязвим, улетает и лечится на 25% "
                              "(раз за бой)")),
        flaws=(("НЕЧИСТЬ", "святой урон и дробящее оружие x1.5"),),
        behavior=(("ЖАЖДА", "ищет лекарей и магов"),)),
    "horse_archer": dict(
        perks=(("СТРЕЛЬБА НА СКАКУ", "стреляет, не останавливаясь, даже на отходе"),),
        behavior=(("КРУЖИТ", "держит дистанцию и уходит от ближников"),)),
    "war_drummer": dict(
        perks=(("БОЕВОЙ РИТМ", "союзники рядом бьют и бегают на 15% быстрее"),
               ("ГРОМ БАРАБАНА", "союзники рядом получают +20% урона на 5 с (раз в 12 с)")),
        flaws=(("ПРИМЕТНЫЙ", "вражеские стрелки и убийцы выбирают его в первую очередь"),),
        behavior=(("ПОЗАДИ СТРОЯ", "держится за спинами своих бойцов"),)),
    "mamluk": dict(
        perks=(("НАТИСК", "разгон к врагу, первый удар оглушает на 0.8 с (раз в 9 с)"),
               ("САБЛЯ", "удар вызывает кровотечение: 6 HP в секунду 2 с")),
        flaws=(("КОПЬЯ", "копейщики и алебардщики встречают натиск контрударом"),),
        behavior=(("УДАР ВО ФЛАНГ", "бьёт врагов, которые уже дерутся с его союзниками"),)),
    "war_elephant": dict(
        perks=(("РАСТАПТЫВАНИЕ", "сбивает врагов на пути: 8 урона и отбрасывает"),
               ("ЛУЧНИК В БАШЕНКЕ", "стрелок на спине стреляет каждые 2.5 с"),
               ("ГРОМАДА", "не бывает оглушён")),
        flaws=(("БЕШЕНСТВО", "при HP ниже 25% 4 с несётся вслепую и топчет и своих (раз за бой)"),),
        behavior=(("ТАРАН", "идёт туда, где врагов больше всего"),)),
    "fire_dervish": dict(
        perks=(("ОГНЕННЫЙ ВИХРЬ", "каждый удар бьёт всех врагов вокруг и поджигает на 2 с"),
               ("ОГНЕУПОРНЫЙ", "не горит")),
        flaws=(("ГОЛОВОКРУЖЕНИЕ", "после каждого 4-го вихря стоит в ступоре 1 с"),),
        behavior=(("В САМУЮ ГУЩУ", "идёт туда, где врагов больше всего"),)),
    "assassin": dict(
        perks=(("ЯДОВИТЫЕ КЛИНКИ", "удар отравляет: 4 HP в секунду 5 с"),
               ("ПРЫЖОК ИЗ ТЕНИ", "телепорт за спину цели (раз в 14 с)"),
               ("ДОБИТЬ ОТРАВЛЕННОГО", "x1.6 урона по отравленным")),
        behavior=(("ОХОТА ЗА ГОЛОВОЙ", "выбирает врага, нанёсшего больше всего урона"),)),
    "valkyrie": dict(
        perks=(("ИЗ ВАЛЬХАЛЛЫ", "поднимает павшего союзника с 40% HP (раз за бой)"),
               ("НЕБЕСНЫЙ РЫВОК", "бросается к врагу с ускорением x1.9 (раз в 10 с)")),
        behavior=(("ХРАНИТЕЛЬНИЦА", "спешит к телу павшего союзника"),)),
    "ice_witch": dict(
        perks=(("ЛЕДЯНАЯ СТРЕЛА", "снаряд замедляет на 50% на 2 с"),
               ("ЛЕДЯНАЯ ГРОБНИЦА", "замораживает самого опасного врага рядом на 2 с (раз в 10 с)")),
        flaws=(("ТАЕТ", "огонь наносит ей x1.5 урона"),),
        behavior=(("ОСТОРОЖНОСТЬ", "держит дистанцию и отступает от ближников"),)),
    "frost_giant": dict(
        perks=(("ГЛЫБА ЛЬДА", "бьёт по площади и замедляет на 2 с"),
               ("ЛЕДЯНАЯ ШКУРА", "не замедляется, не горит, не опутывается и не замерзает")),
        flaws=(("СЛЕПАЯ ЗОНА", "вплотную не бросает, а бьёт кулаком вдвое слабее"),),
        behavior=(("ОСАДНЫЙ", "кидает глыбы туда, где врагов больше всего"),)),
    "halberdier": dict(
        perks=(("КРЮК", "каждый 3-й удар сбивает с ног: оглушение 0.6 с"),
               ("СКВОЗЬ ЩИТ", "удары не блокируются щитами"),
               ("КОНТРУДАР", "встречает алебардой любого врага в рывке, до которого дотянется: +100% урона")),
        behavior=(("СТРАЖ СТРЕЛКОВ", "атакует тех, кто напал на своих стрелков"),)),
    "duelist": dict(
        perks=(("ПАРИРОВАНИЕ", "30% шанс отбить удар ближнего боя спереди и ответить ударом"),
               ("ВЫПАД", "первый удар по новой цели x1.6")),
        behavior=(("ВЫЗОВ", "ищет самого опасного бойца ближнего боя"),)),
    "alchemist": dict(
        perks=(("ОГНЕННАЯ СМЕСЬ", "склянка взрывается: урон и поджог всем вокруг"),
               ("КИСЛОТА", "каждая 2-я склянка разъедает броню: вдвое меньше на 5 с")),
        flaws=(("НЕСТАБИЛЬНЫЕ СКЛЯНКИ", "8% шанс, что склянка взорвётся в руках"),),
        behavior=(("ОСТОРОЖНОСТЬ", "держит дистанцию и отступает от ближников"),
                  ("ПРОТИВ БРОНИ", "выбирает самых бронированных врагов"))),
    "shieldbearer": dict(
        perks=(("СТЕНА ЩИТОВ", "блокирует 80% стрел и 50% ударов спереди"),
               ("ПРИКРЫТИЕ", "свои стрелки рядом получают на 30% меньше урона от стрел и болтов")),
        flaws=(("ОТКРЫТАЯ СПИНА", "щит не защищает сзади и от арбалетных болтов"),),
        behavior=(("СТЕНА", "встаёт между своими стрелками и врагом"),)),
    "rune_priest": dict(
        perks=(("РУНА КАМНЯ", "2 союзника под атакой получают на 35% меньше урона 6 с (раз в 7 с)"),
               ("РУНА ГРОМА", "взрыв под толпой врагов: 20 урона и оглушение 0.6 с (раз в 12 с)")),
        behavior=(("ОСТОРОЖНОСТЬ", "держит дистанцию и отступает от ближников"),)),
    "iron_golem": dict(
        perks=(("ЖЕЛЕЗНОЕ ТЕЛО", "стрелы и болты наносят ему 25% урона"),
               ("БЕЗДУШНЫЙ", "не бывает кровотечения, яда, оглушения и страха"),
               ("ЖЕЛЕЗНЫЕ КУЛАКИ", "дробящий удар: игнорирует 30% брони, нежить x1.5")),
        flaws=(("ПРОВОДНИК", "магия наносит ему +30% урона"),),
        behavior=(("НАПРОЛОМ", "идёт на ближайшего врага"),)),
    "troll": dict(
        perks=(("ГНЕЗДО ГОБЛИНОВ", "каждые 24 с из него выпрыгивают 4 трусливых гоблина"),
               ("ПИНОК", "трусливый гоблин, задевший тролля, с шансом 25% улетает от пинка и гибнет"),
               ("ДУБИНА", "дробящая: игнорирует 30% брони, нежить x1.5")),
        flaws=(("ТУПОГОЛОВЫЙ", "раз в 6 с с шансом 20% впадает в ступор на 5 с"),),
        behavior=(("НАПРОЛОМ", "идёт на ближайшего врага, не выбирая"),)),
}

ROSTER = {k: replace(u, **TRAITS[k]) for k, u in ROSTER.items()}

# --- hire price and upkeep (gold per turn) ---------------------------------------------------
# Set from measured strength: a 2000-battle random-squad run (python -m game.balance 2000 random)
# gives each class a win rate w; price ~ 90 * e^(4.2 * (w - 0.5)), upkeep ~ price / 11.
# Weak cheap units (militia, slinger, zombie, war dog, goblins) cost 40-55 - what a realm hires
# when its treasury is low.  Re-derive after big balance changes.
PRICES: Dict[str, Tuple[int, int]] = {
    "knight": (100, 9), "barbarian": (110, 10), "mage": (120, 11), "spearman": (85, 8), "rogue": (105, 10),
    "orc": (120, 11), "archer": (80, 7), "paladin": (125, 11), "cleric": (115, 10), "crossbowman": (105, 10),
    "necromancer": (125, 11), "skeleton": (90, 8), "monk": (90, 8), "hammerer": (100, 9), "shaman": (95, 9),
    "wolf": (80, 7), "ogre": (150, 14), "goblin": (55, 5), "wolf_rider": (145, 13), "mad_goblin": (105, 10),
    "goblin_shaman": (110, 10), "goblin_bomber": (40, 4), "bog_spider": (75, 7), "griffon_knight": (120, 11),
    "lancer": (120, 11), "uhlan": (165, 15), "ranger": (70, 6), "dryad": (105, 10), "treant": (150, 14), "druid": (85, 8),
    "bladedancer": (65, 6), "death_knight": (130, 12), "wraith": (75, 7), "banshee": (60, 5), "ghoul": (80, 7),
    "vampire": (115, 10), "horse_archer": (75, 7), "war_drummer": (75, 7), "mamluk": (125, 11),
    "war_elephant": (145, 13), "fire_dervish": (75, 7), "assassin": (75, 7), "valkyrie": (100, 9),
    "ice_witch": (80, 7), "frost_giant": (100, 9), "halberdier": (85, 8), "duelist": (85, 8), "alchemist": (70, 6),
    "shieldbearer": (70, 6), "rune_priest": (125, 11), "iron_golem": (145, 13), "militia": (45, 4),
    "slinger": (50, 5), "zombie": (40, 4), "war_dog": (45, 4), "harpooner": (80, 7), "troll": (400, 35),
}
TIER_NAMES = {"weak": "СЛАБЫЙ", "below": "НИЖЕ СРЕДНЕГО", "average": "СРЕДНИЙ", "above": "ВЫШЕ СРЕДНЕГО", "boss": "БОСС"}
ROSTER = {k: replace(u, cost=PRICES.get(k, (90, 8))[0], upkeep=PRICES.get(k, (90, 8))[1]) for k, u in ROSTER.items()}

# the original line-up (used as the default squad)
CLASSIC = ["knight", "barbarian", "spearman", "orc", "rogue", "archer", "mage"]
ALL = [k for k, u in ROSTER.items() if not u.hidden]
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
GOBLIN_SKINS = ["#63c74d", "#3e8948", "#8bae4d", "#a2b84d"]

Look = Union[HumanoidSpec, QuadSpec, SpiderSpec]


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
    if key in ("goblin", "mad_goblin", "goblin_shaman"):
        skin = r.choice(GOBLIN_SKINS)
        common = dict(size=24, skin=skin, eye=r.choice(["#fee761", "#e43b44", "#ffffff"]), goblin=True,
                      bottom=r.choice(["#733e39", "#3e2731", "#5a6988"]), boots=r.choice(["#3e2731", "#181425"]),
                      belt=r.choice(["#733e39", "#3e2731"]), beard=None)
        if key == "goblin":
            return HumanoidSpec(**common, hair=r.choice([None, None, "#181425", "#733e39"]), hair_style="spiky",
                                top=c, sleeves=skin, weapon="dagger", weapon_color=r.choice(["#8b9bb4", "#b86f50"]),
                                helmet=r.choice([None, None, "#b86f50", "#8b9bb4"]), build=r.choice(["slim", "normal"]))
        if key == "mad_goblin":
            return HumanoidSpec(**common, hair=r.choice(["#181425", "#e43b44", "#feae34"]), hair_style="spiky",
                                top=c, sleeves=skin, weapon="greataxe", weapon_color=r.choice(["#b86f50", "#be4a2f"]),
                                handle_color="#3e2731", build="stocky")
        return HumanoidSpec(**common, hair=None, top=r.choice(["#68386c", "#3e2731", "#265c42"]), robe=True,
                            sleeves=skin, helmet=c, helmet_style="hood", weapon="mushroom",
                            magic=r.choice(["#e43b44", "#b55088", "#f77622"]), handle_color="#ead4aa", build="slim")
    # --- Альдерн / Вельдмар -----------------------------------------------------------
    if key == "ranger":
        return _human(r, top=r.choice(["#265c42", "#3e8948"]), sleeves=c, bottom="#733e39", boots="#3e2731",
                      helmet=r.choice(["#265c42", "#3e2731"]), helmet_style="hood", weapon="bow",
                      handle_color="#733e39", cape=c, belt="#733e39", build="slim")
    if key == "dryad":
        leaf = r.choice(["#63c74d", "#a7f070", "#3e8948"])
        bark = r.choice(["#8bae4d", "#a2b84d", "#c2d68f"])
        return HumanoidSpec(skin=bark, eye=r.choice(["#fee761", "#ffffff"]), hair=leaf, hair_style="long",
                            beard=None, top=leaf, robe=True, sleeves=bark, bottom=leaf, boots=bark, belt=c,
                            weapon=None, magic="#a7f070", build="slim")
    if key == "treant":
        bark = r.choice(["#733e39", "#8a5a3a", "#5d4a3a"])
        return HumanoidSpec(size=46, skin=bark, eye=r.choice(["#fee761", "#a7f070"]),
                            hair=r.choice(["#3e8948", "#63c74d", "#265c42"]), hair_style="leaves",
                            beard=None, top=bark, sleeves=bark, bottom=bark, boots=bark,
                            belt=c, weapon=None, build="stocky", lean=6)
    if key == "druid":
        return _human(r, top=r.choice(["#3e8948", "#733e39", "#265c42"]), robe=True, bottom="#3e2731",
                      boots="#733e39", hair=r.choice(GREYS + ["#733e39"]), hair_style="long",
                      beard=r.choice(GREYS + ["#733e39"]), helmet=None, weapon="staff", magic="#a7f070",
                      handle_color="#733e39", belt=c, cape=c, sleeves_from="top")
    if key == "bladedancer":
        return _human(r, top=c, bottom=r.choice(["#3a4466", "#733e39"]), boots="#3e2731",
                      hair_style=r.choice(["long", "spiky"]), weapon="sword", offhand="sword",
                      belt=a, build="slim", beard=None, sleeves_from="skin")
    if key == "griffon_knight":
        return QuadSpec(kind="griffon", fur=r.choice(["#e4a672", "#b86f50", "#feae34"]),
                        belly=r.choice(["#ead4aa", "#ffffff"]), eye="#181425", nose="#feae34",
                        wings=r.choice(["#ffffff", "#c0cbdc", "#e4a672"]), head_color="#ffffff",
                        body_len=13, body_w=7, leg_len=5, tail="thin", size=(64, 52),
                        rider="human", rider_skin=r.choice(SKINS), rider_top="#c0cbdc", rider_helmet="#c0cbdc",
                        rider_weapon="lance", rider_cloth=c, rider_eye="#181425", rider_blade="#c0cbdc")
    if key == "uhlan":
        return QuadSpec(kind="horse", fur=r.choice(["#ead4aa", "#c0cbdc", "#b86f50", "#733e39"]),
                        belly=r.choice(["#ffffff", "#ead4aa"]), eye="#181425", mane=r.choice(["#ffffff", "#3e2731"]),
                        collar=c, body_len=14, body_w=6, leg_len=8, tail="long", size=(60, 52),
                        rider="human", rider_skin=r.choice(SKINS), rider_top=c, rider_helmet="#feae34",
                        rider_weapon="lance", rider_cloth=a, rider_eye="#181425")
    if key == "lancer":
        return QuadSpec(kind="horse", fur=r.choice(["#733e39", "#3e2731", "#ead4aa", "#8b9bb4", "#b86f50"]),
                        belly=r.choice(["#ead4aa", "#c0cbdc"]), eye="#181425", mane=r.choice(["#181425", "#ead4aa"]),
                        collar=c, body_len=14, body_w=7, leg_len=7, tail="long", size=(60, 52),
                        rider="human", rider_skin=r.choice(SKINS), rider_top="#8b9bb4", rider_helmet="#c0cbdc",
                        rider_weapon="sword", rider_cloth=c, rider_shield=a, rider_eye="#181425",
                        rider_blade="#c0cbdc")
    # --- Пепельное герцогство --------------------------------------------------------
    if key == "death_knight":
        return HumanoidSpec(skin=r.choice(["#8b9bb4", "#c0cbdc"]), eye=r.choice(["#2ce8f5", "#63c74d"]), hair=None,
                            top=r.choice(["#3a4466", "#262b44"]), top_shiny=True, bottom="#262b44", boots="#181425",
                            helmet=r.choice(["#262b44", "#3a4466"]), helmet_style="horned", weapon="sword",
                            weapon_color=r.choice(["#73eff7", "#a7f070"]), shield="#262b44", cape=c,
                            belt="#181425", build="stocky")
    if key == "wraith":
        cloth = r.choice(["#3a4466", "#262b44", "#5a6988"])
        return HumanoidSpec(skin=r.choice(["#c0cbdc", "#8b9bb4"]), eye=r.choice(["#2ce8f5", "#ffffff"]), hair=None,
                            top=cloth, robe=True, ghost=True, sleeves=cloth, bottom=cloth, boots=cloth, belt=c,
                            helmet=cloth, helmet_style="hood", weapon="scythe", weapon_color="#c0cbdc",
                            handle_color="#3e2731", build="slim")
    if key == "banshee":
        cloth = r.choice(["#c0cbdc", "#8b9bb4", "#ead4aa"])
        return HumanoidSpec(skin=r.choice(["#c0cbdc", "#a4dddb"]), eye=r.choice(["#ffffff", "#2ce8f5"]),
                            hair=r.choice(["#ffffff", "#c0cbdc"]), hair_style="long", top=cloth, robe=True,
                            ghost=True, sleeves=cloth, bottom=cloth, boots=cloth, belt=c, weapon=None,
                            magic="#73eff7", build="slim")
    if key == "ghoul":
        skin = r.choice(["#8b9bb4", "#8bae4d", "#a2a8a0"])
        return HumanoidSpec(skin=skin, eye=r.choice(["#e43b44", "#fee761"]), hair=r.choice([None, "#3e2731"]),
                            hair_style="long", top=r.choice(["#3e2731", "#5a6988"]), sleeves=skin,
                            bottom=r.choice(["#3e2731", "#733e39"]), boots=skin, belt=c, weapon=None,
                            claws=True, lean=18, build="slim")
    if key == "vampire":
        return HumanoidSpec(skin=r.choice(["#c0cbdc", "#ead4aa"]), eye="#e43b44", hair=r.choice(["#181425", "#ffffff"]),
                            hair_style=r.choice(["short", "long"]), top=r.choice(["#181425", "#3e2731"]),
                            sleeves="#181425", bottom="#181425", boots="#181425", belt="#a22633", cape=c,
                            weapon="rapier", weapon_color="#c0cbdc", build="slim")
    # --- Каганат ------------------------------------------------------------------------
    if key == "horse_archer":
        return QuadSpec(kind="horse", fur=r.choice(["#b86f50", "#733e39", "#ead4aa", "#3e2731"]),
                        belly=r.choice(["#ead4aa", "#e4a672"]), eye="#181425", mane="#181425", collar=c,
                        body_len=13, body_w=6, leg_len=7, tail="long", size=(58, 50),
                        rider="human", rider_skin=r.choice(SKINS), rider_top=c, rider_helmet=r.choice(["#733e39", "#8b9bb4"]),
                        rider_weapon="bow", rider_cloth=c, rider_eye="#181425")
    if key == "war_drummer":
        return _human(r, top=c, bottom="#733e39", boots="#3e2731", helmet=r.choice(["#733e39", "#3e2731"]),
                      hair_style="long", weapon="sticks", drum=r.choice(["#b86f50", "#a22633", "#733e39"]),
                      belt="#733e39", build="stocky", sleeves_from="skin")
    # --- Зархад ----------------------------------------------------------------------------
    if key == "mamluk":
        return QuadSpec(kind="horse", fur=r.choice(["#ffffff", "#3e2731", "#c0cbdc", "#b86f50"]),
                        belly=r.choice(["#ead4aa", "#c0cbdc"]), eye="#181425", mane=r.choice(["#181425", "#ead4aa"]),
                        collar=c, body_len=14, body_w=7, leg_len=7, tail="long", size=(60, 52),
                        rider="human", rider_skin=r.choice(["#c28569", "#b86f50", "#733e39"]), rider_top="#8b9bb4",
                        rider_helmet="#ffffff", rider_turban=True, rider_weapon="saber", rider_cloth=c,
                        rider_shield=a, rider_eye="#181425")
    if key == "war_elephant":
        return QuadSpec(kind="elephant", fur=r.choice(["#8b9bb4", "#5a6988", "#a2a8a0"]), belly="#5a6988",
                        eye="#181425", tusks="#ead4aa", collar=c, body_len=24, body_w=18, leg_len=9,
                        tail="thin", ears="round", size=(88, 72),
                        rider="human", rider_skin=r.choice(["#c28569", "#b86f50", "#733e39"]), rider_top=c,
                        rider_helmet="#ffffff", rider_turban=True, rider_weapon="bow", rider_cloth=a)
    if key == "fire_dervish":
        return _human(r, skin=r.choice(["#c28569", "#b86f50", "#733e39"]), top=r.choice(["#ffffff", "#ead4aa"]),
                      robe=True, bottom=c, boots="#733e39", helmet=r.choice(["#ffffff", "#f77622"]), helmet_style="turban",
                      hair=None, weapon="saber", offhand="saber", weapon_color="#feae34", magic="#f77622",
                      belt=c, build="slim", sleeves_from="skin")
    if key == "assassin":
        return _human(r, top=r.choice(["#262b44", "#3e2731"]), bottom="#262b44", boots="#181425",
                      helmet=r.choice(["#262b44", "#ffffff", c]), helmet_style="hood", weapon="dagger",
                      offhand="dagger", weapon_color="#a7f070", cape=c, belt="#733e39", beard=None,
                      build="slim", sleeves_from="top")
    # --- Север -----------------------------------------------------------------------------
    if key == "valkyrie":
        return _human(r, skin=r.choice(["#e8b796", "#ead4aa"]), hair=r.choice(["#feae34", "#ead4aa", "#ffffff"]),
                      hair_style="long", beard=None, top="#c0cbdc", top_shiny=True, bottom=c, boots="#733e39",
                      helmet="#c0cbdc", helmet_style="winged", weapon="spear", shield=a, wings="#ffffff",
                      belt="#feae34", build="slim")
    if key == "ice_witch":
        return _human(r, skin=r.choice(["#ead4aa", "#c0cbdc"]), hair=r.choice(["#ffffff", "#c0cbdc", "#73eff7"]),
                      hair_style="long", beard=None, top=r.choice(["#41a6f6", "#73eff7", "#c0cbdc"]), robe=True,
                      bottom="#41a6f6", boots="#3a4466", weapon="staff", magic="#c0f8ff", handle_color="#c0cbdc",
                      belt=c, cape=c, build="slim", sleeves_from="top")
    if key == "frost_giant":
        skin = r.choice(["#a4c8e8", "#8fb8de", "#c0d8f0"])
        hair = r.choice(["#ffffff", "#c0cbdc"])
        return HumanoidSpec(size=48, skin=skin, eye=r.choice(["#2ce8f5", "#ffffff"]), hair=hair, hair_style="long",
                            beard=hair, top=c, sleeves=skin, bottom="#5a6988", boots="#c0cbdc", belt="#3e2731",
                            helmet=r.choice([None, "#8b9bb4"]), helmet_style="horned", weapon=None,
                            magic="#c0f8ff", build="stocky")
    # --- Лига --------------------------------------------------------------------------------
    if key == "halberdier":
        return _human(r, top=c, bottom=r.choice(["#ead4aa", "#5a6988"]), boots="#3e2731",
                      helmet=r.choice(["#8b9bb4", "#c0cbdc"]), weapon="halberd", belt="#733e39",
                      build=r.choice(["normal", "stocky"]))
    if key == "duelist":
        return _human(r, top=c, bottom="#3e2731", boots="#181425", helmet=r.choice([a, "#262b44"]),
                      helmet_style="plume", weapon="rapier", offhand="dagger", cape=a, belt="#feae34",
                      build="slim", sleeves_from="top")
    if key == "alchemist":
        return _human(r, top="#733e39", sleeves=c, bottom="#3a4466", boots="#3e2731", helmet="#733e39",
                      weapon="flask", magic=r.choice(["#a7f070", "#f77622", "#b55088"]), belt=c,
                      build=r.choice(["slim", "normal"]))
    # --- Дургхейм --------------------------------------------------------------------------
    if key == "shieldbearer":
        hair = r.choice(["#b86f50", "#3e2731", "#c0cbdc", "#feae34"])
        return _human(r, hair=hair, beard=hair, top="#8b9bb4", top_shiny=True, bottom="#733e39", boots="#3e2731",
                      helmet=r.choice(["#8b9bb4", "#c0cbdc"]), weapon="axe", shield=c, big_shield=True,
                      belt="#733e39", build="stocky")
    if key == "rune_priest":
        hair = r.choice(["#ffffff", "#c0cbdc", "#8b9bb4"])
        return _human(r, hair=hair, beard=hair, top=r.choice(["#3a4466", "#5a6988"]), robe=True, bottom=c,
                      boots="#3e2731", weapon="staff", magic="#2ce8f5", handle_color="#5a6988", belt=c,
                      build="stocky", sleeves_from="top")
    if key == "iron_golem":
        return HumanoidSpec(size=44, skin="#8b9bb4", eye=r.choice(["#2ce8f5", "#feae34"]), hair=None,
                            top=r.choice(["#5a6988", "#8b9bb4"]), top_shiny=True, sleeves="#8b9bb4",
                            bottom="#5a6988", boots="#3a4466", belt=c, weapon=None, build="stocky")
    # --- гоблины -------------------------------------------------------------------------------
    if key == "goblin_bomber":
        skin = r.choice(GOBLIN_SKINS)
        return HumanoidSpec(size=24, skin=skin, eye=r.choice(["#fee761", "#e43b44"]), goblin=True, top=c,
                            sleeves=skin, bottom=r.choice(["#733e39", "#3e2731"]), boots="#3e2731", belt="#733e39",
                            hair=None, beard=None, helmet=r.choice(["#733e39", "#5a6988"]), weapon="bomb",
                            build="slim")
    if key == "bog_spider":
        return SpiderSpec(body=r.choice(["#5a6988", "#3e8948", "#733e39", "#68386c"]), mark=c,
                          legs=r.choice(["#3e2731", "#262b44"]), eye=r.choice(["#e43b44", "#fee761", "#a7f070"]))
    if key == "bear":
        return QuadSpec(kind="bear", fur=r.choice(["#733e39", "#3e2731", "#b86f50"]), belly="#b86f50",
                        eye="#181425", collar=c, body_len=13, body_w=9, leg_len=5, tail="none", ears="round",
                        size=(56, 44))
    # --- дешёвые отряды и гарпунщик ---------------------------------------------------
    if key == "militia":
        return _human(r, top=r.choice(["#ead4aa", "#b86f50", "#8b9bb4"]), sleeves=c, bottom="#733e39",
                      boots="#3e2731", helmet=r.choice([None, "#733e39", "#8b9bb4"]), weapon="spear",
                      weapon_color="#8b9bb4", belt=c, build=r.choice(["slim", "normal"]))
    if key == "slinger":
        return _human(r, top=r.choice(["#ead4aa", "#e4a672"]), sleeves=c, bottom=c, boots="#733e39",
                      helmet=c, helmet_style="hood", weapon="sling", belt="#733e39", build="slim")
    if key == "zombie":
        skin = r.choice(["#8bae4d", "#a2a8a0", "#8b9bb4"])
        return HumanoidSpec(skin=skin, eye=r.choice(["#fee761", "#ffffff"]), hair=r.choice([None, "#3e2731", "#5a6988"]),
                            hair_style="long", top=r.choice(["#5a6988", "#733e39", "#3e2731"]), sleeves=skin,
                            bottom=r.choice(["#3a4466", "#3e2731"]), boots=skin, belt=c, weapon=None, lean=10,
                            build=r.choice(["normal", "slim"]))
    if key == "war_dog":
        return QuadSpec(fur=r.choice(["#b86f50", "#733e39", "#3e2731", "#c28569"]), belly="#ead4aa", eye="#181425",
                        collar=c, body_len=9, body_w=6, leg_len=4.5, tail="thin", ears="round", size=(44, 32))
    if key == "harpooner":
        hair = r.choice(["#feae34", "#ead4aa", "#733e39", "#c0cbdc"])
        return _human(r, hair=hair, beard=hair if r.random() < 0.7 else None, top=r.choice(["#733e39", "#5a6988"]),
                      sleeves=c, bottom="#3e2731", boots="#733e39", helmet=r.choice([None, "#8b9bb4"]),
                      weapon="harpoon", cape=c, belt="#733e39", build="stocky")
    if key == "troll":
        skin = r.choice(["#5a9e8a", "#8b9bb4", "#6b8e5a", "#7a8a9e"])
        return HumanoidSpec(size=48, skin=skin, eye=r.choice(["#fee761", "#e43b44"]), hair=None,
                            beard=r.choice([None, None, "#3e2731"]), top=c, sleeves=skin, bottom="#733e39",
                            boots=skin, belt="#3e2731", weapon="club", handle_color=r.choice(["#733e39", "#b86f50"]),
                            build="stocky", tusks="#ead4aa", passengers=r.choice(GOBLIN_SKINS))
    if key == "wolf_rider":
        fur = r.choice(["#3a4466", "#262b44", "#5a6988", "#3e2731"])
        return QuadSpec(fur=fur, belly=r.choice(["#8b9bb4", "#5a6988"]), eye=r.choice(["#e43b44", "#fee761"]),
                        collar=c, body_len=13, body_w=7, leg_len=5.5, size=(56, 42), tail="bushy",
                        rider_skin=r.choice(GOBLIN_SKINS), rider_top=c, rider_eye=r.choice(["#fee761", "#e43b44"]),
                        rider_blade=r.choice(["#c0cbdc", "#b86f50"]))
    if key == "wolf":
        fur = r.choice(["#8b9bb4", "#5a6988", "#733e39", "#c0cbdc", "#3a4466"])
        return QuadSpec(fur=fur, belly=r.choice(["#c0cbdc", "#ead4aa", "#8b9bb4"]),
                        eye=r.choice(["#fee761", "#e43b44"]), collar=c,
                        body_len=r.choice([10.0, 11.0, 12.0]), tail="bushy")
    raise KeyError(key)


def spec_for(key: str, team: Team, seed: int = 0) -> Look:
    """Kept for compatibility: the seed-0 look."""
    return look_for(key, team, seed)
