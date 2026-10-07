"""Campaign data: eight playable human factions, the wild goblins, cities, roads and recruit pools.

Pure data (no pygame, no numpy) - the world map generator (worldgen.py), the map
screen (mapview.py) and tests all read it.  Coordinates are pixels on the
MAP_W x MAP_H world map; a city's (x, y) is the foot of its tower.

* :data:`FACTIONS` - the eight playable human realms; every pair has a relation
  1..100 with a reason (:func:`relation`).
* :data:`GOBLINS` - a non-playable faction holding cities all over the map.  No
  diplomacy with it: it is at war with everyone, and anyone may take its cities.
* Recruit pools belong to *cities*, not factions: whoever holds a city hires the
  units it offers.  Pools may name units that do not exist in battle yet
  (:data:`NEW_UNITS`) - they are designed and added later.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple

from .units import ROSTER

MAP_W, MAP_H = 1600, 1100


@dataclass(frozen=True)
class Faction:
    key: str
    name: str
    short: str                      # fits on the faction bar
    color: str                      # flag field
    light: str                      # highlights, text on dark panels
    dark: str                       # flag shadow / ribbon border
    metal: str                      # emblem on the flag and coat of arms
    emblem: str                     # key into EMBLEMS
    leader: str
    leader_title: str
    capital: str                    # city key
    lore: str
    mechanics: Tuple[Tuple[str, str], ...]   # proposed faction features (not active yet)
    culture: str                    # ground style of its lands on the map
    playable: bool = True


FACTIONS: Tuple[Faction, ...] = (
    Faction(
        "aldern", "КОРОЛЕВСТВО АЛЬДЕРН", "АЛЬДЕРН", "#2f5fbf", "#7fa8f0", "#1c3a7a", "#f2c84b", "crown",
        "ЭДРИК III", "МОЛОДОЙ КОРОЛЬ", "kronholm",
        "Старейшее королевство людей на равнинах у Зеркального озера. Рыцари Альдерна веками "
        "стерегли тракты, но после гибели старого короля знать грызётся за власть, и юный "
        "Эдрик III держит корону лишь верностью паладинов. С востока давит Каганат, с юго-запада "
        "ползёт Пепел - бывшее герцогство самого Альдерна.",
        (("КОРОЛЕВСКИЕ ТРАКТЫ", "по дорогам между своими городами отряды идут на 1 город дальше"),
         ("РЫЦАРСКАЯ ЧЕСТЬ", "рыцари и паладины +15% HP, защищая свои города"),
         ("НАЛОГИ", "+20% золота с городов, но после поражений растёт недовольство")),
        "plains",
    ),
    Faction(
        "sylvan", "ЛЕСНОЕ КНЯЖЕСТВО ВЕЛЬДМАР", "ВЕЛЬДМАР", "#1f8a5e", "#6fe0a8", "#0f5436", "#e8f2e0", "tree",
        "АЭЛИНА", "КНЯГИНЯ-ДРУИД", "sylvaen",
        "Потомки первых поселенцев, ушедших в Вечный лес и заключивших договор с его духами. "
        "Егеря Вельдмара бьют белку в глаз, а друиды говорят с деревьями. Корона Альдерна "
        "считает их мятежными вассалами, но в чащу за ними не суётся. С юга наступает мёртвая "
        "земля, и корни Древа-Матери чернеют.",
        (("ЛЕСНЫЕ ТРОПЫ", "между своими лесными городами можно ходить без дорог"),
         ("МЕТКОСТЬ ЕГЕРЕЙ", "лучники и егеря получают +15% дальности"),
         ("ЦЕЛИТЕЛЬНАЯ ЧАЩА", "в лесных городах раненые отряды лечатся вдвое быстрее")),
        "forest",
    ),
    Faction(
        "ashen", "ПЕПЕЛЬНОЕ ГЕРЦОГСТВО", "ПЕПЕЛ", "#6a3d8f", "#c49be8", "#3d1f57", "#e6dcc8", "skull",
        "ВЕЛГАРОТ", "ГЕРЦОГ-НЕКРОМАНТ", "morkhaar",
        "Чума выкосила богатейшее герцогство Альдерна за одно лето. Выжившие отреклись от "
        "короны и пошли за придворным магом Велгаротом, который поднял их мёртвых родных на "
        "защиту границ. Здесь живые пашут землю бок о бок с мертвецами, а соседи видят в "
        "них чудовищ.",
        (("ЖАТВА", "после любой битвы рядом часть павших встаёт скелетами в гарнизон"),
         ("МЁРТВЫЕ НЕ ПРОСЯТ ЖАЛОВАНЬЯ", "нежить не требует золота на содержание, только ману"),
         ("ЧУМНОЙ ТУМАН", "соседние вражеские города теряют 10% дохода")),
        "blight",
    ),
    Faction(
        "khanate", "КАГАНАТ ВОЛЧЬЕГО КЛЫКА", "КАГАНАТ", "#b0303a", "#f6757a", "#5e1418", "#1a1418", "fang",
        "ТОГРУЛ", "ВЕЛИКИЙ КАГАН", "karaordu",
        "Кочевые роды восточных степей веками резали друг друга, пока Тогрул не объединил их "
        "под знаменем Волчьего Клыка. Конные лучники Каганата не знают усталости, а в его "
        "войске служат даже огры с гор. Каган уже взял горную крепость Карак-Ор и смотрит на "
        "плодородные долины Альдерна.",
        (("НАБЕГ", "город можно разграбить ради золота, не захватывая его"),
         ("СТЕПНЫЕ КОНИ", "в степи отряды Каганата ходят на 1 город дальше"),
         ("ДАНЬ", "соседи с отношением ниже 30 платят Каганату за мир")),
        "steppe",
    ),
    Faction(
        "sultanate", "СУЛТАНАТ ЗАРХАД", "ЗАРХАД", "#d0682a", "#ffb07a", "#7a3410", "#f6e7b0", "crescent",
        "САЛАДИР", "СУЛТАН ПЕСКОВ", "zarkhad",
        "За Гнилой топью лежат пески и оазисы Зархада. Султан Саладир правит из сада-дворца "
        "над подземной рекой, его мамлюки и боевые слоны славятся на всё побережье, а маги "
        "огня учатся у самого солнца. Султанат сказочно богат, но отрезан от мира болотами, "
        "кишащими гоблинами.",
        (("ОАЗИСЫ", "в пустынных городах отряды восстанавливаются вдвое быстрее"),
         ("КАРАВАНЫ", "+5% золота за каждую фракцию, с которой нет войны"),
         ("ЗНОЙ", "чужие отряды в пустыне теряют 5% HP каждый ход")),
        "desert",
    ),
    Faction(
        "north", "ЯРЛСТВА СЕВЕРА", "СЕВЕР", "#5fb7d9", "#bfeaff", "#2c6f8c", "#f4f8fc", "helm",
        "ХАЛЬВДАН", "ЯРЛ СЕДАЯ ГРИВА", "hjoldgard",
        "За снежными перевалами живут ярлы - мореходы, охотники и сказители. С каждым годом "
        "зимы всё длиннее, и драккары всё чаще уходят на юг за зерном. Старый Хальвдан хочет "
        "мира и торговли, но молодые хускарлы жаждут саг о великих набегах.",
        (("ЗИМНИЙ ПОХОД", "зимой отряды Севера не слабеют, а враги идут медленнее"),
         ("САГИ", "бойцы, убившие многих врагов, быстрее растут в уровне"),
         ("ДРАККАРЫ", "из портов Севера можно напасть на любой прибрежный город")),
        "tundra",
    ),
    Faction(
        "league", "ЗОЛОТАЯ ЛИГА", "ЛИГА", "#e0b22c", "#ffe08a", "#8a6410", "#7a1f2b", "scales",
        "ОКТАВИЯ ВАЛЬМАРРИ", "ДОЖ ЛИГИ", "valmarra",
        "Портовые города юга сто лет назад выкупили свободу у короны Альдерна - золотом, а не "
        "кровью. С тех пор Лигой правят торговые дома, а воюют за неё наёмники. Дож Октавия "
        "продаёт оружие всем сторонам и следит, чтобы ни одна из них не стала слишком сильной.",
        (("НАЁМНИКИ", "отряд из пула соседнего чужого города можно нанять за двойную цену"),
         ("ТОРГОВЫЕ ДОГОВОРЫ", "+10% золота за каждую фракцию с отношением выше 60"),
         ("ПОДКУП", "за золото можно переманить вражеский гарнизон")),
        "coast",
    ),
    Faction(
        "highland", "ГОРНОЕ КОРОЛЕВСТВО ДУРГХЕЙМ", "ДУРГХЕЙМ", "#6b6f7f", "#c0c6d8", "#33363f", "#f08a2c", "hammer",
        "БРУНИ ЖЕЛЕЗНОБОРОД", "ТАН ГОРЦЕВ", "durgheim",
        "Горцы северо-востока живут в крепостях, высеченных в скалах, и куют лучшую сталь "
        "мира. Их тан ничего не забывает: падение Карак-Ора записано в Книге Обид кровью. "
        "Снизу шахты подтачивают гоблины, с юга давит Каганат, но горы стоят три тысячи лет - "
        "и простоят ещё столько же.",
        (("КАМЕННЫЕ СТЕНЫ", "гарнизоны горных городов получают +20% брони"),
         ("ШАХТЫ", "горные города дают двойной доход"),
         ("КНИГА ОБИД", "+10% урона против фракции, напавшей на горцев первой")),
        "mountain",
    ),
)

# The non-playable faction: no diplomacy, always at war with everyone.
GOBLINS = Faction(
    "goblin", "ГОБЛИНСКИЕ ПЛЕМЕНА", "ГОБЛИНЫ", "#8fa830", "#d4ea6b", "#4f5e14", "#5a2e1e", "mushroom",
    "БУГОР", "ТРОЛЛЬ-МУСОРЩИК", "rotheap",
    "Дикие племена гоблинов засели в топях, руинах и пещерах по всему материку. Они грабят "
    "всех подряд, тащат в норы любой хлам и плодятся быстрее, чем их успевают выбивать. "
    "Договориться с ними невозможно - их города можно только отбить.",
    (("НЕ ВЕДУТ ПЕРЕГОВОРОВ", "вечная война со всеми, дипломатия невозможна"),
     ("ПЛОДЯТСЯ", "каждый ход в гоблинских городах прибавляется трусливый гоблин"),
     ("НАБЕГИ", "разросшиеся гарнизоны нападают на ближайший слабый город"),
     ("ЛОГОВО ТРОЛЛЯ", "Гнилую Кучу охраняет босс - тролль Бугор")),
    "swamp", playable=False,
)
ALL_FACTIONS: Tuple[Faction, ...] = FACTIONS + (GOBLINS,)
FACTION: Dict[str, Faction] = {f.key: f for f in ALL_FACTIONS}

# 9x9 emblems ('#' = metal; drawn on the flags and the coats of arms)
EMBLEMS: Dict[str, Tuple[str, ...]] = {
    "crown": (".........", "#...#...#", "#..###..#", "##.###.##", "#########",
              "#.##.##.#", "#########", ".........", "........."),
    "tree": ("...###...", "..#####..", ".#######.", "#########", ".#######.",
             "..#.#.#..", "....#....", "....#....", "...###..."),
    "skull": ("..#####..", ".#######.", "#########", "##..#..##", "##..#..##",
              ".###.###.", "..#####..", "..#.#.#..", "........."),
    "fang": ("#.......#", "##.....##", "##.....##", ".##...##.", ".##...##.",
             "..#####..", "..#####..", "...###...", "........."),
    "crescent": ("...###...", "..##.....", ".##......", ".##....#.", ".##...###",
                 ".##....#.", ".##......", "..##.....", "...###..."),
    "mushroom": ("...###...", ".#######.", "##.###.##", "#########", ".#######.",
                 "...###...", "...###...", "..#####..", "........."),
    "helm": ("#.......#", "#.......#", "##.###.##", ".#######.", ".#######.",
             ".##.#.##.", ".##.#.##.", ".##...##.", "........."),
    "scales": ("....#....", "#########", "#...#...#", "#...#...#", "##..#..##",
               "###.#.###", "....#....", "..#####..", "........."),
    "hammer": ("#########", "#########", "#########", "....#....", "....#....",
               "....#....", "....#....", "...###...", "........."),
}


# --- relations ------------------------------------------------------------------------------
# 1..100: ~50 neutral, >80 allies (or about to be), <20 at war (or about to be).
_REL = {
    ("aldern", "sylvan"): (42, "Вельдмар когда-то был вассалом короны. Альдерн требует налогов, "
                               "лес молчит и не платит."),
    ("aldern", "ashen"): (8, "Пепельное герцогство - мятежная земля Альдерна. Корона не признаёт "
                             "Велгарота, война идёт десятилетиями."),
    ("aldern", "khanate"): (18, "Конница Каганата жжёт восточные деревни, Альдерн держит против "
                                "неё форты. Большая война вот-вот начнётся."),
    ("aldern", "sultanate"): (58, "Далёкий, но щедрый партнёр: пряности и шёлк в обмен на зерно "
                                  "с полей Хартвела."),
    ("aldern", "north"): (40, "Северяне грабят северные пашни, но и торгуют мехами. Ярл ищет "
                              "мира, его хускарлы - нет."),
    ("aldern", "league"): (60, "Лига - бывшие вассалы короны. Торгуют охотно, но вечно спорят "
                               "о пошлинах и старых долгах."),
    ("aldern", "highland"): (84, "Древний союз: горцы куют рыцарям доспехи, король платит "
                                 "серебром и помогает против Каганата."),
    ("sylvan", "ashen"): (5, "Мёртвая земля отравляет корни Вечного леса. Для Вельдмара это "
                             "священная война."),
    ("sylvan", "khanate"): (35, "Кочевники выжигают восточные рощи под пастбища. Лес помнит "
                                "каждое сожжённое дерево."),
    ("sylvan", "sultanate"): (50, "Почти не встречались. Купцы султана скупают редкие лесные "
                                  "травы, и только."),
    ("sylvan", "north"): (66, "Северяне, как и лесной народ, чтут духов зверей. Охотничье "
                              "братство и торговля мехами."),
    ("sylvan", "league"): (44, "Лига скупает лесную древесину у контрабандистов. Выгодно, "
                               "но Вельдмар недоволен."),
    ("sylvan", "highland"): (36, "Старая обида: горцы срубили священные дубы для крепей своих "
                                 "шахт и не извинились."),
    ("ashen", "khanate"): (38, "Шаманы Каганата боятся мёртвых, но у обоих один враг - Альдерн. "
                               "Настороженное молчание."),
    ("ashen", "sultanate"): (26, "Жрецы солнца прокляли Велгарота. Торговля запрещена, но войны "
                                 "пока нет - их разделяет море."),
    ("ashen", "north"): (14, "Ярлы сжигают своих мёртвых, чтобы те не встали. Некромантия для "
                             "них худшее из зол."),
    ("ashen", "league"): (45, "Купцы Лиги тайно покупают у Пепла редкие реагенты, поэтому "
                              "худой мир."),
    ("ashen", "highland"): (20, "Горцы чтят предков, и поднимать мёртвых для них кощунство. "
                                "Близки к войне."),
    ("khanate", "sultanate"): (24, "Каганат грабит караваны Зархада на степных трактах. Султан "
                                   "платит дань, но копит обиду."),
    ("khanate", "north"): (48, "Обе стороны уважают силу, но спорят за пастбища у северных "
                               "отрогов. Пока нейтралитет."),
    ("khanate", "league"): (52, "Лига продаёт Каганату оружие, Каганат грабит её караваны. "
                                "Хрупкое равновесие."),
    ("khanate", "highland"): (6, "Каганат взял горную крепость Карак-Ор. Тан Бруни поклялся "
                                 "вернуть её - война идёт сейчас."),
    ("sultanate", "north"): (50, "Слишком далеко для вражды. Северный янтарь и меха ценятся "
                                 "при дворе султана."),
    ("sultanate", "league"): (28, "Соперники за морскую торговлю. У южного берега идёт война "
                                  "пошлин и каперов."),
    ("sultanate", "highland"): (64, "Горная сталь в обмен на пряности и золото. Караваны идут "
                                    "в обход степи."),
    ("north", "league"): (56, "Меха и китовый жир идут в порты Лиги. Иногда северяне грабят "
                              "её склады, и цены растут."),
    ("north", "highland"): (66, "Соседи по горам: железо в обмен на меха и общая неприязнь "
                                "к Каганату."),
    ("league", "highland"): (81, "Горная сталь уходит за море через порты Лиги. Торговый "
                                 "союз, выгодный обоим."),
}


def relation(a: str, b: str) -> Tuple[int, str]:
    """(value 1..100, reason) between two playable factions; symmetric.
    The goblins are at war with everyone (value 0)."""
    if a == b:
        return 100, ""
    if "goblin" in (a, b):
        return 0, "Гоблины не ведут переговоров - только война."
    return _REL[(a, b)] if (a, b) in _REL else _REL[(b, a)]


def relation_status(v: int) -> Tuple[str, str]:
    """Label and color for a relation value."""
    if v <= 0:
        return "ВЕЧНАЯ ВОЙНА", "#e43b44"
    if v >= 80:
        return "СОЮЗ", "#63c74d"
    if v >= 60:
        return "ДРУЖБА", "#a7f070"
    if v > 40:
        return "НЕЙТРАЛИТЕТ", "#c0cbdc"
    if v >= 20:
        return "НАПРЯЖЕНИЕ", "#feae34"
    return "ВОЙНА", "#e43b44"


# --- units that do not exist yet ---------------------------------------------------------------
# key: (name, role, idea) - designed and added to the battle roster at the next stage
NEW_UNITS: Dict[str, Tuple[str, str, str]] = {
    "griffon_knight": ("ГРИФОНИЙ РЫЦАРЬ", "ЛЕТУН", "перелетает строй и пикирует на стрелков"),
    "lancer": ("КОННЫЙ РЫЦАРЬ", "КАВАЛЕРИЯ", "таранный удар копьём с разгона"),
    "ranger": ("ЛЕСНОЙ ЕГЕРЬ", "СТРЕЛОК", "меткие выстрелы, прячется в зарослях"),
    "dryad": ("ДРИАДА", "ЦЕЛИТЕЛЬ", "дух рощи: лечит союзников, опутывает врагов корнями"),
    "treant": ("ДРЕВЕНЬ", "ВЕЛИКАН", "огромный ходячий дуб, боится огня"),
    "druid": ("ДРУИД", "ОБОРОТЕНЬ", "превращается в медведя"),
    "bladedancer": ("ТАНЦУЮЩИЙ С КЛИНКАМИ", "ДУЭЛЯНТ", "вихрь двух мечей, высокое уклонение"),
    "death_knight": ("РЫЦАРЬ СМЕРТИ", "ТАНК", "павший рыцарь, пьёт жизнь ударами"),
    "wraith": ("ПРИЗРАК", "УБИЙЦА", "проходит сквозь строй, оружие почти не ранит его"),
    "banshee": ("БАНШИ", "КРИКУН", "вопль пугает и замедляет врагов"),
    "ghoul": ("ГУЛЬ", "ПАДАЛЬЩИК", "пожирает трупы и лечится"),
    "vampire": ("ВАМПИР", "ДВОРЯНИН", "вампиризм, рассыпается стаей мышей"),
    "horse_archer": ("КОННЫЙ ЛУЧНИК", "КАВАЛЕРИЯ", "стреляет на скаку и не даёт себя догнать"),
    "war_drummer": ("БОЕВОЙ БАРАБАНЩИК", "ПОДДЕРЖКА", "ритм барабана ускоряет союзников"),
    "mamluk": ("МАМЛЮК", "КАВАЛЕРИЯ", "тяжёлый всадник с саблей и щитом"),
    "war_elephant": ("БОЕВОЙ СЛОН", "КОЛОСС", "топчет строй, на спине - лучник"),
    "fire_dervish": ("ОГНЕННЫЙ ДЕРВИШ", "МАГ", "огненный вихрь вокруг себя"),
    "assassin": ("АССАСИН", "УБИЙЦА", "яд и удар из тени по командирам"),
    "valkyrie": ("ВАЛЬКИРИЯ", "ЛЕТУНЬЯ", "уносит павших союзников обратно в бой"),
    "ice_witch": ("ЛЕДЯНАЯ ВЕДЬМА", "КОЛДУНЬЯ", "замораживает врагов на месте"),
    "frost_giant": ("ЛЕДЯНОЙ ВЕЛИКАН", "ВЕЛИКАН", "швыряет глыбы льда"),
    "halberdier": ("АЛЕБАРДЩИК", "СТРАЖ", "держит строй, бьёт сквозь щиты"),
    "duelist": ("ДУЭЛЯНТ", "ФЕХТОВАЛЬЩИК", "парирует удары и отвечает выпадом"),
    "alchemist": ("АЛХИМИК", "БОМБИСТ", "кидает склянки с огнём и кислотой"),
    "shieldbearer": ("ГОРНЫЙ ЩИТОНОСЕЦ", "ТАНК", "стена щитов, почти неуязвим спереди"),
    "rune_priest": ("РУННЫЙ ЖРЕЦ", "ПОДДЕРЖКА", "руны дают союзникам броню"),
    "iron_golem": ("ЖЕЛЕЗНЫЙ ГОЛЕМ", "КОЛОСС", "медленный, стрелы его почти не берут"),
    "goblin_bomber": ("ГОБЛИН-ПОДРЫВНИК", "СМЕРТНИК", "бежит в толпу врагов и взрывается"),
    "bog_spider": ("БОЛОТНЫЙ ПАУК", "ЛОВЕЦ", "плюёт паутиной, ядовитый укус"),
}


def unit_name(key: str) -> str:
    return ROSTER[key].name if key in ROSTER else NEW_UNITS[key][0]


def unit_role(key: str) -> str:
    return ROSTER[key].role if key in ROSTER else NEW_UNITS[key][1]


def unit_exists(key: str) -> bool:
    return key in ROSTER


# --- cities ----------------------------------------------------------------------------------
@dataclass(frozen=True)
class City:
    key: str
    name: str
    faction: str
    x: int
    y: int
    kind: str                     # capital | castle | fort | town | port | lair
    pool: Tuple[str, ...]         # units this city lets its owner hire (3..6)
    desc: str


KIND_NAMES = {"capital": "СТОЛИЦА", "castle": "КРЕПОСТЬ", "fort": "ФОРТ", "town": "ГОРОД", "port": "ПОРТ",
              "lair": "ЛОГОВО"}

CITIES: Tuple[City, ...] = (
    # --- Ярлства Севера: тундра и фьорды
    City("skalvik", "СКАЛЬВИК", "north", 300, 95, "port",
         ("barbarian", "archer", "valkyrie", "ice_witch"), "Фьорд, где строят драккары для набегов"),
    City("hjoldgard", "ХЬЁЛЬДГАРД", "north", 540, 110, "capital",
         ("barbarian", "wolf", "shaman", "valkyrie", "frost_giant"), "Медовый зал ярла, высеченный в чёрной скале"),
    City("wolfdale", "ВОЛЧЬЯ ПАДЬ", "north", 730, 175, "town",
         ("wolf", "barbarian", "shaman", "frost_giant"), "Долина, где приручают лютых волков"),
    City("snowbarrow", "СНЕЖНЫЙ КУРГАН", "north", 190, 210, "fort",
         ("barbarian", "shaman", "skeleton"), "Древние курганы, мёртвые здесь неспокойны"),
    City("whitehorn", "БЕЛЫЙ РОГ", "north", 900, 95, "town",
         ("barbarian", "wolf", "hammerer", "valkyrie"), "Торговый пост у горных перевалов"),
    # --- Дургхейм: горы на северо-востоке
    City("durgheim", "ДУРГХЕЙМ", "highland", 1350, 170, "capital",
         ("hammerer", "crossbowman", "shieldbearer", "rune_priest", "iron_golem"), "Трон в скале и Великая Кузня"),
    City("ironmaw", "ЖЕЛЕЗНАЯ ПАСТЬ", "highland", 1170, 110, "castle",
         ("hammerer", "shieldbearer", "crossbowman"), "Шахтёрская крепость у богатейшей жилы"),
    City("deepforge", "ГЛУБИННЫЙ ГОРН", "highland", 1530, 280, "town",
         ("hammerer", "iron_golem", "rune_priest", "crossbowman"), "Кузни, где в лаве куют големов"),
    City("stoneward", "КАМЕННЫЙ СТРАЖ", "highland", 1220, 330, "fort",
         ("shieldbearer", "crossbowman", "hammerer", "spearman"), "Застава над перевалом в долины Альдерна"),
    City("silvervein", "СЕРЕБРЯНАЯ ЖИЛА", "highland", 1040, 250, "town",
         ("hammerer", "crossbowman", "rune_priest"), "Здешнее серебро идёт в королевскую монету"),
    # --- Королевство Альдерн: равнины в центре
    City("kronholm", "КРОНХОЛЬМ", "aldern", 780, 430, "capital",
         ("knight", "paladin", "cleric", "spearman", "archer", "griffon_knight"), "Белый замок у Зеркального озера"),
    City("st_alarius", "СВЯТОЙ АЛАРИЙ", "aldern", 590, 350, "town",
         ("monk", "cleric", "paladin", "spearman"), "Монастырь, где воспитывают паладинов"),
    City("ashford", "ЭШФОРД", "aldern", 960, 420, "castle",
         ("knight", "spearman", "crossbowman", "lancer"), "Восточная твердыня против Каганата"),
    City("hartwell", "ХАРТВЕЛ", "aldern", 620, 580, "town",
         ("spearman", "archer", "knight", "lancer"), "Житница королевства: поля и мельницы"),
    City("lumen", "ЛЮМЕН", "aldern", 920, 660, "town",
         ("mage", "cleric", "monk", "knight"), "Академия магов под покровительством короны"),
    City("northford", "СЕВЕРНЫЙ БРОД", "aldern", 730, 290, "fort",
         ("spearman", "archer", "barbarian", "knight"), "Застава против набегов северян"),
    City("westwatch", "ЗАПАДНАЯ ЗАСТАВА", "aldern", 470, 470, "fort",
         ("archer", "spearman", "ranger", "paladin"), "Пограничный форт у опушки Вечного леса"),
    # --- Вельдмар: Вечный лес на западе
    City("sylvaen", "СИЛЬВАЭН", "sylvan", 240, 450, "capital",
         ("ranger", "dryad", "treant", "druid", "bladedancer", "archer"), "Город в кроне Древа-Матери"),
    City("moonglade", "ЛУННАЯ ПОЛЯНА", "sylvan", 340, 310, "town",
         ("archer", "ranger", "druid"), "Поляна, где друиды читают звёзды"),
    City("worldroots", "КОРНИ МИРА", "sylvan", 140, 610, "town",
         ("treant", "dryad", "druid", "wolf"), "Священная роща древнейших деревьев"),
    City("stillwater", "ТИХАЯ ЗАВОДЬ", "sylvan", 350, 640, "town",
         ("archer", "ranger", "rogue", "bladedancer"), "Речная пристань контрабандистов"),
    City("silverbrook", "СЕРЕБРЯНЫЙ РУЧЕЙ", "sylvan", 110, 330, "fort",
         ("bladedancer", "archer", "monk"), "Застава танцующих с клинками"),
    # --- Пепельное герцогство: мёртвые земли на юго-западе
    City("morkhaar", "МОР-КХААР", "ashen", 240, 900, "capital",
         ("necromancer", "skeleton", "death_knight", "wraith", "banshee"), "Чёрная цитадель Велгарота"),
    City("plagueford", "ЧУМНОЙ БРОД", "ashen", 430, 790, "fort",
         ("skeleton", "ghoul", "necromancer", "spearman"), "Брод, где тонули армии живых"),
    City("kingbarrow", "КУРГАН КОРОЛЕЙ", "ashen", 110, 790, "town",
         ("skeleton", "death_knight", "wraith"), "Гробницы древних королей Альдерна"),
    City("ashharbor", "ПЕПЕЛЬНАЯ ГАВАНЬ", "ashen", 360, 1005, "port",
         ("skeleton", "ghoul", "vampire", "rogue"), "Порт кораблей-призраков"),
    City("greymonastery", "СЕРЫЙ МОНАСТЫРЬ", "ashen", 520, 915, "town",
         ("ghoul", "banshee", "necromancer", "vampire", "monk"), "Обитель, где монахи служат смерти"),
    # --- Золотая лига: южное побережье
    City("valmarra", "ВАЛЬМАРРА", "league", 790, 935, "capital",
         ("crossbowman", "rogue", "halberdier", "duelist", "alchemist", "mage"), "Мраморный порт, сердце Лиги"),
    City("corvina", "КОРВИНА", "league", 640, 985, "port",
         ("rogue", "crossbowman", "duelist", "archer"), "Город тайных аукционов"),
    City("aurelia", "АУРЕЛИЯ", "league", 980, 860, "town",
         ("halberdier", "crossbowman", "monk", "alchemist"), "Монетный двор Лиги под охраной монахов"),
    City("saltcape", "СОЛЁНЫЙ МЫС", "league", 1050, 990, "fort",
         ("halberdier", "archer", "rogue"), "Форт против гоблинских пиратов"),
    City("tremont", "ТРЕМОНТ", "league", 710, 780, "town",
         ("spearman", "halberdier", "crossbowman", "knight"), "Ярмарочный перекрёсток южных трактов"),
    # --- Каганат: степи на востоке
    City("karak_or", "КАРАК-ОР", "khanate", 1450, 440, "castle",
         ("barbarian", "ogre", "hammerer", "crossbowman", "horse_archer"), "Отнятая у горцев крепость"),
    City("karaordu", "КАРА-ОРДУ", "khanate", 1380, 640, "capital",
         ("horse_archer", "barbarian", "wolf", "shaman", "war_drummer", "ogre"), "Шатёр кагана среди тысячи костров"),
    City("bloodford", "КРОВАВЫЙ БРОД", "khanate", 1180, 560, "fort",
         ("horse_archer", "wolf", "barbarian"), "Брод, за который бьются каждое лето"),
    City("skullmound", "КУРГАН ПРЕДКОВ", "khanate", 1250, 760, "town",
         ("shaman", "war_drummer", "horse_archer", "archer"), "Святилище степных шаманов"),
    City("steppecamp", "СТЕПНОЙ СТАН", "khanate", 1080, 690, "town",
         ("horse_archer", "wolf", "spearman", "orc"), "Кочевой лагерь; здесь нанимают орков-наёмников"),
    # --- Султанат Зархад: пустыня на юго-востоке
    City("zarkhad", "ЗАРХАД", "sultanate", 1400, 950, "capital",
         ("mamluk", "war_elephant", "fire_dervish", "assassin", "mage", "spearman"), "Сад-дворец над подземной рекой"),
    City("bahri", "ПОРТ БАХРИ", "sultanate", 1290, 1050, "port",
         ("archer", "assassin", "rogue", "spearman"), "Гавань пряностей и шёлка"),
    City("safir", "ОАЗИС САФИР", "sultanate", 1510, 860, "town",
         ("monk", "cleric", "mamluk", "fire_dervish"), "Пальмы, святилище и колодцы"),
    City("redsands", "КРАСНЫЕ БАРХАНЫ", "sultanate", 1310, 850, "fort",
         ("mamluk", "archer", "spearman", "war_elephant"), "Форт на краю степи и песков"),
    City("minaret", "МЕДНЫЙ МИНАРЕТ", "sultanate", 1540, 1030, "town",
         ("mage", "fire_dervish", "cleric"), "Башня магов огня"),
    # --- гоблины (неигровая фракция): топи, руины и пещеры по всей карте
    City("rotheap", "ГНИЛАЯ КУЧА", "goblin", 1170, 915, "lair",
         ("goblin", "mad_goblin", "goblin_shaman", "goblin_bomber", "troll"), "Гора мусора, где спит тролль Бугор"),
    City("pirateshoal", "ПИРАТСКАЯ ОТМЕЛЬ", "goblin", 1170, 1040, "lair",
         ("goblin", "goblin_bomber", "rogue"), "Гнездо пиратов на гнилых плотах"),
    City("shroomhole", "ГРИБНАЯ НОРА", "goblin", 480, 660, "lair",
         ("goblin", "goblin_shaman", "bog_spider"), "Пещеры, где растят безумные грибы"),
    City("rustdump", "РЖАВАЯ СВАЛКА", "goblin", 1070, 535, "lair",
         ("goblin", "mad_goblin", "goblin_bomber", "ogre"), "Свалка доспехов со старого поля битвы"),
    City("caves", "ГОБЛИНСКИЕ ПЕЩЕРЫ", "goblin", 1035, 125, "lair",
         ("goblin", "mad_goblin", "wolf_rider"), "Норы, прогрызенные в горных шахтах"),
    City("stinkbog", "ВОНЮЧАЯ ТОПЬ", "goblin", 600, 840, "lair",
         ("goblin", "bog_spider", "goblin_shaman"), "Топь, где водятся болотные пауки"),
    City("redrock", "КРАСНАЯ СКАЛА", "goblin", 1530, 740, "lair",
         ("goblin", "wolf_rider", "mad_goblin", "ogre"), "Логово наездников на лютоволках"),
)
CITY: Dict[str, City] = {c.key: c for c in CITIES}

# Roads (undirected).  Checked by tests: none crosses the sea or the lake.
ROADS: Tuple[Tuple[str, str], ...] = (
    ("skalvik", "hjoldgard"), ("skalvik", "snowbarrow"), ("hjoldgard", "wolfdale"), ("wolfdale", "whitehorn"),
    ("wolfdale", "northford"), ("snowbarrow", "moonglade"), ("snowbarrow", "silverbrook"), ("whitehorn", "caves"),
    ("durgheim", "ironmaw"), ("durgheim", "deepforge"), ("durgheim", "stoneward"), ("ironmaw", "caves"),
    ("deepforge", "karak_or"), ("stoneward", "silvervein"), ("stoneward", "bloodford"), ("silvervein", "ashford"),
    ("silvervein", "caves"), ("kronholm", "st_alarius"), ("kronholm", "ashford"), ("kronholm", "hartwell"),
    ("kronholm", "northford"), ("st_alarius", "northford"), ("st_alarius", "westwatch"), ("ashford", "lumen"),
    ("ashford", "rustdump"), ("hartwell", "westwatch"), ("hartwell", "tremont"), ("hartwell", "shroomhole"),
    ("lumen", "aurelia"), ("lumen", "steppecamp"), ("westwatch", "sylvaen"), ("sylvaen", "moonglade"),
    ("sylvaen", "worldroots"), ("sylvaen", "stillwater"), ("sylvaen", "silverbrook"), ("worldroots", "stillwater"),
    ("worldroots", "kingbarrow"), ("stillwater", "plagueford"), ("stillwater", "shroomhole"),
    ("morkhaar", "plagueford"), ("morkhaar", "kingbarrow"), ("morkhaar", "ashharbor"),
    ("plagueford", "greymonastery"), ("plagueford", "shroomhole"), ("ashharbor", "greymonastery"),
    ("greymonastery", "corvina"), ("greymonastery", "stinkbog"), ("valmarra", "corvina"), ("valmarra", "aurelia"),
    ("valmarra", "tremont"), ("aurelia", "saltcape"), ("aurelia", "rotheap"), ("saltcape", "rotheap"),
    ("saltcape", "pirateshoal"), ("tremont", "stinkbog"), ("karak_or", "karaordu"), ("karaordu", "bloodford"),
    ("karaordu", "skullmound"), ("karaordu", "redrock"), ("bloodford", "steppecamp"), ("bloodford", "rustdump"),
    ("skullmound", "steppecamp"), ("skullmound", "redsands"), ("steppecamp", "rustdump"), ("zarkhad", "bahri"),
    ("zarkhad", "safir"), ("zarkhad", "redsands"), ("zarkhad", "minaret"), ("bahri", "pirateshoal"),
    ("safir", "minaret"), ("safir", "redrock"), ("redsands", "rotheap"), ("rotheap", "pirateshoal"),
    ("shroomhole", "stinkbog"),
)


def neighbors(key: str) -> List[str]:
    return [b if a == key else a for a, b in ROADS if key in (a, b)]


def cities_of(faction: str) -> List[City]:
    return [c for c in CITIES if c.faction == faction]
