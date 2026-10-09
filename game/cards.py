"""Action cards: the catalogue, officers' personal cards and how a realm's deck is built.

Everything a realm does on the world map is a card played for action points (ОД):
collecting taxes, marching, storming cities, hiring for free, diplomacy, intrigue.

A realm's deck (see ``deck_for``) is made of
* the six cards of state, set by the realm's **course** (``COURSES``): balance = three taxes, a march,
  an assault and a muster (СБОР ВОЙСК: hiring in a city is open only while a muster lasts, longer
  with a council strong in ВЕРБОВКА); war = three assaults; economy = taxes and a fair; and so on. The course can be
  changed during the campaign, then it is locked for a while (``course_cooldown``: the better the
  council governs, the sooner it may change course again); every course but balance has a price;
* ONE faction card (it belongs to the leader, who always sits in the council);
* the personal cards of the officers sitting in the council (``personal``);
* threshold cards: for each of the six stats, the council's total over ``THRESHOLDS[0]``
  adds a moderate card and over ``THRESHOLDS[1]`` a strong one (12 at most).
Rivals can slip curses into it (``CURSES``): dead cards that clog the hand for a few
turns, or cards that go off with a bad effect the moment they are drawn.

This module is data only; what the cards do lives in ``cardplay.py``.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

from .officers import OFFICER, OFFICERS, STATS, Officer

TIERS = ("basic", "junk", "moderate", "strong", "rare", "unique", "faction", "curse", "vice", "feat", "fate")
TIER_NAMES = {"basic": "ОСНОВА", "junk": "ПУСТЯК", "moderate": "ДЕЛЬНАЯ", "strong": "СИЛЬНАЯ", "rare": "РЕДКАЯ",
              "unique": "ЕДИНСТВЕННАЯ", "faction": "ФРАКЦИОННАЯ", "curse": "ПРОКЛЯТИЕ", "vice": "ПОРОК",
              "feat": "ПОДВИГ", "fate": "НАПАСТЬ"}
KIND_NAMES = {"economy": "ХОЗЯЙСТВО", "military": "ВОЙНА", "intrigue": "ИНТРИГА", "diplomacy": "ДИПЛОМАТИЯ",
              "council": "СОВЕТ", "recruit": "НАБОР", "curse": "БЕДА", "vice": "ПОРОК"}

AP = 5                          # action points per turn
AP_BONUS = {"khanate": 1}       # the Horde: one more action every turn
HAND = 5                        # cards drawn at the end of every turn
COUNCIL_SEATS = 5               # the leader + four advisers
THRESHOLDS = (62, 80)           # council total of one stat: +1 moderate card, +1 strong card


@dataclass(frozen=True)
class Card:
    key: str
    name: str
    cost: int                   # action points
    tier: str
    kind: str
    text: str
    targets: Tuple[str, ...] = ()
    gold: int = 0               # gold paid on top of the action points
    exhaust: bool = False       # burns after play (leaves the deck for good)
    unplayable: bool = False    # a dead card in hand
    on_draw: bool = False       # goes off the moment it is drawn
    expires: int = 0            # curses: vanish after this many of the owner's turns
    reaction: str = ""          # answer cards: "attacked" / "cursed" - they go off in a rival's turn


def _c(key, name, cost, tier, kind, text, targets=(), **kw) -> Card:
    return Card(key, name, cost, tier, kind, text, tuple(targets), **kw)


_CARDS: List[Card] = [
    # --- the state's own cards: in every deck --------------------------------------------------
    _c("tax", "ПОДАТЬ", 1, "basic", "economy",
       "Собрать налог в своём городе: процветание x20 золота. Два хода подряд в одном городе - процветание -1.",
       ("own_city",)),
    _c("march", "ПОХОД", 1, "basic", "military",
       "До 3 офицеров с отрядами идут в соседний свой город.", ("own_city_officers", "officers_here", "dest_adj")),
    _c("assault", "ШТУРМ", 2, "basic", "military",
       "До 3 офицеров из соседних городов штурмуют вражеский город. Победа - город ваш.",
       ("enemy_adj", "attackers")),
    _c("levy", "НАБОР", 1, "basic", "recruit",
       "Бесплатные новобранцы в своём городе на 60 мощи + 10 за вербовку лучшего офицера там.", ("own_city",)),

    _c("buy_off", "ОТКУП ОТ ОРДЫ", 1, "basic", "diplomacy", "Орде 60 золота + 30 за каждый свой город у логов: 4 хода "
       "мир с гоблинами. Если орды рядом нет: +15 золота за каждый свой город."),
    _c("muster", "СБОР ВОЙСК", 1, "basic", "recruit", "Открыть найм в своём городе на этот ход. Вербовка "
       "совета 62+: ещё на 1 ход, 80+: ещё на 2.", ("own_city",)),

    # --- junk: a little use in a special case, or too dear -------------------------------------
    _c("feast", "ПИР", 1, "junk", "council", "Офицеры в своём городе: верность +12.", ("own_city_officers",)),
    _c("hunt", "ОХОТА", 1, "junk", "economy", "Дичь на стол и шкуры на рынок: +30 золота."),
    _c("omen", "ГАДАНИЕ", 0, "junk", "council", "Посмотреть 3 верхние карты колоды. Одну из них взять в руку, "
       "если она стоит 0 ОД.", ()),
    _c("tourney", "ТУРНИР", 2, "junk", "council", "Весь совет: верность +8. Столица: процветание +1."),
    _c("denounce", "ДОНОС", 1, "junk", "intrigue", "Узнать руку соперника. Если в ней есть проклятие - его "
       "владелец теряет 20 золота.", ("rival",)),
    _c("parade", "ПАРАД", 2, "junk", "council", "Офицеры в столице: верность +10, их отряды +10% силы на 2 хода."),
    _c("guard", "ЛИЧНАЯ ГВАРДИЯ", 1, "junk", "recruit", "Два ополченца в своём городе.", ("own_city",)),
    _c("old_debt", "СТАРЫЙ ДОЛГ", 1, "junk", "economy", "Стрясти должок: +45 золота, но отношения с "
       "соперником -8.", ("rival_diplo",)),
    _c("pilgrimage", "ПАЛОМНИЧЕСТВО", 2, "junk", "council", "Свой офицер: верность 100, и он готов действовать "
       "снова.", ("own_officer",)),

    # --- moderate ---------------------------------------------------------------------------------
    _c("fair", "ЯРМАРКА", 1, "moderate", "economy", "Свой город: процветание x10 золота и процветание +1. "
       "Не считается налогом.", ("own_city",)),
    _c("caravan", "КАРАВАН", 1, "moderate", "economy", "Два соседних своих города торгуют: (сумма их "
       "процветания) x9 золота.", ("own_city_pair", "own_city_pair2")),
    _c("tithe", "ДЕСЯТИНА", 2, "moderate", "economy", "Каждый свой город: процветание x6 золота. Без "
       "штрафа за поборы."),
    _c("build", "СТРОЙКА", 1, "moderate", "economy", "Заплатить 80 золота: процветание своего города +2.",
       ("own_city",), gold=80),
    _c("loan", "ЗАЙМ", 0, "moderate", "economy", "+220 золота сразу. В колоду ложится ДОЛГ: при каждом "
       "вытягивании - проценты 40.", ()),
    _c("militia_call", "ОПОЛЧЕНИЕ", 1, "moderate", "recruit", "Свой город: дешёвые бойцы на 100 мощи и "
       "оборона x1.25 на 2 хода.", ("own_city",)),
    _c("volunteers", "ДОБРОВОЛЬЦЫ", 1, "moderate", "recruit", "Свой город: новобранцы на процветание x25 мощи.",
       ("own_city",)),
    _c("fortify", "УКРЕПЛЕНИЯ", 1, "moderate", "military", "Свой город: оборона x1.4 на 3 хода.", ("own_city",)),
    _c("raid", "НАБЕГ", 1, "moderate", "military", "Офицер грабит соседний вражеский город: процветание x12 "
       "золота, процветание там -1. Город не берётся.", ("enemy_adj", "raider")),
    _c("siege", "ОСАДА", 1, "moderate", "military", "Соседний вражеский город в осаде 3 хода: оборона x0.75, "
       "каждый ход процветание -1.", ("enemy_adj",)),
    _c("supplies", "ПРОВИАНТ", 0, "moderate", "military", "Свой офицер снова готов идти или штурмовать.",
       ("own_officer_spent",)),
    _c("morale", "БОЕВОЙ ДУХ", 1, "moderate", "military", "Отряд своего офицера +25% силы на 2 хода.",
       ("own_officer",)),
    _c("patrol", "ДОЗОР", 0, "moderate", "council", "Вытянуть 1 карту."),
    _c("sabotage", "ДИВЕРСИЯ", 1, "moderate", "intrigue", "Вражеский город: процветание -2, гарнизон теряет "
       "одного воина.", ("enemy_city",)),
    _c("arson", "ПОДЖОГ", 1, "moderate", "intrigue", "Подбросить сопернику ПОЖАР: вытянув его, он потеряет "
       "четверть казны.", ("rival",)),
    _c("bribe", "ПОДКУП", 1, "moderate", "intrigue", "100 золота: верность вражеского офицера -30. Ниже 20 - "
       "он переходит к вам с отрядом.", ("enemy_city_officers", "enemy_officer_there"), gold=100),
    _c("agitators", "ПОДСТРЕКАТЕЛИ", 1, "moderate", "intrigue", "В колоду соперника ложатся 2 "
       "ДЕЗЕРТИРСТВА: вытянув, он теряет воина из лучшего отряда.", ("rival",)),
    _c("counterspy", "КОНТРРАЗВЕДКА", 1, "moderate", "intrigue", "Сжечь все проклятия в руке и в колоде."),
    _c("embassy", "ПОСОЛЬСТВО", 1, "moderate", "diplomacy", "Отношения с соперником +15.", ("rival_diplo",)),
    _c("trade_pact", "ТОРГОВЫЙ ДОГОВОР", 1, "moderate", "diplomacy", "Предложить торговлю с весомыми дарами "
       "(+20 к согласию): 8 ходов оба получают золото.", ("rival_diplo",)),
    _c("buyout", "ВЫКУП ЗЕМЛИ", 2, "moderate", "diplomacy", "Купить соседний город державы, с которой мир "
       "или отношения 50+, если там нет офицеров: процветание x100 золота.", ("city_buyable",)),
    _c("mobilize", "МОБИЛИЗАЦИЯ", 0, "moderate", "council", "+2 ОД в этот ход. В колоду ложится УСТАЛОСТЬ "
       "на 3 хода.", ()),

    # --- answers: they wait in hand and go off in a rival's turn ----------------------------------
    _c("ambush", "ЗАСАДА", 0, "moderate", "military", "ОТВЕТ: когда штурмуют ваш город, нападающие теряют "
       "15% войск ещё до боя.", reaction="attacked"),
    _c("sortie", "ВЫЛАЗКА", 0, "moderate", "military", "ОТВЕТ: когда штурмуют ваш город, его защита в этом "
       "бою x1.3.", reaction="attacked"),
    _c("reinforce", "ПОДКРЕПЛЕНИЕ", 0, "moderate", "military", "ОТВЕТ: когда штурмуют ваш город, сильнейший "
       "офицер из соседнего своего города приходит на помощь.", reaction="attacked"),
    _c("withdraw", "ОТХОД", 0, "junk", "military", "ОТВЕТ: когда штурмуют ваш город, войска уходят в соседний "
       "свой город целыми. Город сдан без боя.", reaction="attacked"),
    _c("intercept", "ПЕРЕХВАТ ГОНЦА", 0, "moderate", "intrigue", "ОТВЕТ: когда соперник подбрасывает вам "
       "проклятия, они не доходят до колоды.", reaction="cursed"),

    # --- threshold cards: moderate (first threshold) -------------------------------------------
    _c("reform", "РЕФОРМА", 1, "moderate", "economy", "Свой город: процветание +2.", ("own_city",)),
    _c("talent_search", "ПОИСК ТАЛАНТОВ", 1, "moderate", "recruit", "В свой город прибывает молодой офицер: "
       "слабый, но учится быстро. Если город с академией - прибывают двое.", ("own_city",)),
    _c("master_builder", "МАСТЕР-ЗОДЧИЙ", 1, "moderate", "economy", "Построить в своём городе любое здание "
       "за полцены.", ("own_city", "building")),
    _c("physician", "ЛЕКАРЬ", 1, "moderate", "council", "Вылечить болезнь в своём городе; 6 ходов болезнь его "
       "не берёт, верность офицеров там +5.", ("own_city",)),
    _c("sappers", "САПЁРЫ", 1, "moderate", "intrigue", "Разрушить здание в соседнем вражеском городе.",
       ("enemy_built",)),
    _c("sickness", "БОЛЕЗНЬ В ГОРОДЕ", 0, "fate", "curse", "Вытянув - возьмите другую карту. В своём городе болезнь на "
       "3 хода: офицеры там могут умереть. Лазареты её останавливают.",
       unplayable=True, on_draw=True),
    _c("forced_march", "ФОРСИРОВАННЫЙ МАРШ", 1, "moderate", "military", "До 3 офицеров идут на 2 дороги "
       "по своим землям.", ("own_city_officers", "officers_here", "dest_2")),
    _c("scouts", "ЛАЗУТЧИКИ", 1, "moderate", "council", "Вытянуть 2 карты и узнать руку соперника.",
       ("rival",)),
    _c("truce", "ПЕРЕМИРИЕ", 1, "moderate", "diplomacy", "Предложить мир с грамотами (+20 к согласию): "
       "8 ходов никто ни на кого не нападает.", ("rival_diplo",)),
    _c("letters", "ПОДМЕТНЫЕ ПИСЬМА", 1, "moderate", "intrigue", "В колоду соперника ложатся 2 СМУТЫ: "
       "мёртвые карты на 3 хода.", ("rival",)),

    # --- the horde's own versions of cards that do not suit goblins (``GOBLIN_SWAP``) -------------
    _c("intimidate", "ЗАПУГИВАНИЕ", 1, "moderate", "intrigue", "Соседняя держава платит орде 60 золота, а нет "
       "золота - её приграничный город теряет 1 процветания.", ("rival_neighbor",)),
    _c("great_fear", "ВЕЛИКИЙ СТРАХ", 2, "strong", "intrigue", "Каждая соседняя держава платит орде 50 золота, "
       "а нет золота - её приграничный город теряет 1 процветания."),
    _c("dirty_tricks", "ПАКОСТИ", 1, "moderate", "intrigue", "Гоблины гадят сопернику: в его колоду ложатся "
       "2 СМУТЫ - мёртвые карты на 3 хода.", ("rival",)),
    _c("flea_market", "БАРАХОЛКА", 1, "moderate", "economy", "Своё логово: процветание x10 золота за краденое "
       "и процветание +1.", ("own_city",)),
    _c("fat_year", "ЖИРНЫЙ ГОД", 2, "strong", "economy", "Два беднейших своих логова: процветание +1. Каждое "
       "логово: процветание x6 золота."),

    # --- threshold cards: strong (second threshold) ---------------------------------------------
    _c("purge", "ЧИСТКА КАНЦЕЛЯРИИ", 1, "strong", "council", "Сжечь навсегда одну карту из руки (хоть "
       "проклятие) и вытянуть новую.", ("hand_card",)),
    _c("golden_age", "ЗОЛОТОЙ ВЕК", 2, "strong", "economy", "Два беднейших своих города: процветание +1. "
       "Каждый свой город: процветание x6 золота."),
    _c("conscription", "ВСЕОБЩИЙ ПРИЗЫВ", 2, "strong", "recruit", "Каждый свой город: новобранцы на "
       "40 + процветание x15 мощи."),
    _c("blitz", "МОЛНИЕНОСНЫЙ ПОХОД", 2, "strong", "military", "Штурм силами из городов в 3 дорогах от цели, "
       "+15% силы.", ("enemy_reach", "attackers_far")),
    _c("all_seeing", "ВСЕВИДЯЩЕЕ ОКО", 1, "strong", "intrigue", "Увидеть руку соперника и сбросить из неё "
       "2 лучшие карты.", ("rival",)),
    _c("grand_embassy", "ВЕЛИКОЕ ПОСОЛЬСТВО", 2, "strong", "diplomacy", "Отношения +15 в любом случае. Предложить "
       "мир (а при мире - союз) с +35 к согласию на 10 ходов; при согласии ещё и торговля по 30 золота.",
       ("rival_diplo",)),
    _c("plot", "ЗАГОВОР", 2, "strong", "intrigue", "Вражеский офицер может перейти к вам с отрядом. "
       "Шанс выше, если он неверен, а у совета высокая интрига.", ("enemy_city_officers", "enemy_officer_there")),

    # --- faction cards (one per realm, the leader's) ----------------------------------------------
    _c("edict", "КОРОЛЕВСКИЙ ЭДИКТ", 1, "faction", "economy", "Каждый свой город: процветание x6 "
       "золота. Без штрафа за поборы."),
    _c("mother_tree", "ТРОПЫ ДРЕВА-МАТЕРИ", 0, "faction", "military", "До 3 офицеров переходят из своего "
       "города в любой свой без дорог и остаются готовы. Там оборона x1.3 на 2 хода.",
       ("own_city_officers", "officers_here", "dest_any")),
    _c("harvest", "ЖАТВА", 1, "faction", "recruit", "Мёртвые встают: в каждом своём городе нежить на 40 "
       "мощи, в столице - на 90."),
    _c("great_raid", "ВЕЛИКИЙ НАБЕГ", 2, "faction", "military", "Все вражеские города у ваших границ "
       "разграблены: процветание x8 золота с каждого, процветание там -1."),
    _c("desert_caravans", "КАРАВАНЫ ПУСТЫНИ", 1, "faction", "economy", "+45 золота за каждую державу, с "
       "которой мир или отношения 40+. Порт: процветание +1."),
    _c("longships", "ДРАККАРЫ", 2, "faction", "military", "До 3 офицеров из своих портов "
       "штурмуют любой вражеский порт по морю, без дорог.", ("enemy_port", "attackers_port")),
    _c("golden_contract", "ЗОЛОТОЙ КОНТРАКТ", 1, "faction", "recruit", "Нанять в свой город до 3 воинов "
       "из пула ЛЮБОГО города мира за 1.25 цены.", ("own_city",)),
    _c("book_of_grudges", "КНИГА ОБИД", 1, "faction", "military", "Соперник вписан в Книгу: 6 ходов ваши "
       "отряды против него +30% силы. Верность совета +10.", ("rival",)),
    _c("brood", "ВЫВОДОК", 1, "faction", "recruit", "В каждом логове вылупляются гоблины на 110 мощи."),

    # --- unique personal cards: one copy in the whole world --------------------------------------
    _c("charter", "ГРАМОТА О ВОЛЬНОСТЯХ", 1, "unique", "economy", "Свой город: процветание +3. Сгорает.",
       ("own_city",), exhaust=True),
    _c("tiltyard", "РИСТАЛИЩЕ", 1, "rare", "recruit", "Ристалище в своём городе за 140 золота: "
       "конница державы нанимается там в любой ход без СБОРА ВОЙСК и на 15% дешевле, оборона x1.1.",
       ("tiltyard_city",)),
    _c("griffon_order", "ОРДЕН ГРИФОНА", 1, "unique", "military", "Свой офицер: +40% силы на 3 хода, и он "
       "снова готов.", ("own_officer",)),
    _c("peers_court", "СУД ПЭРОВ", 1, "faction", "council", "Совет: верность +15. Сжечь проклятия в руке, "
       "вытянуть 1 карту."),
    _c("forest_wrath", "ГНЕВ ЛЕСА", 2, "unique", "military", "Соседний вражеский город: все войска там "
       "теряют 30%.", ("enemy_adj_any",)),
    _c("thicket_spirits", "ДУХИ ЧАЩИ", 1, "unique", "military", "Свой город: оборона x1.8 на 4 хода.",
       ("own_city",)),
    _c("moon_rite", "ЛУННЫЙ ОБРЯД", 0, "unique", "council", "Вытянуть 2 карты."),
    _c("plague_cauldron", "ЧУМНОЙ КОТЁЛ", 2, "unique", "intrigue", "В колоду соперника ложатся 2 ЧУМЫ: "
       "вытянутая чума снижает процветание его города на 2.", ("rival",)),
    _c("raise_dead", "ПОДНЯТЬ ПАВШИХ", 1, "unique", "recruit", "Свой город: нежить на 220 мощи.",
       ("own_city",)),
    _c("dead_whisper", "ШЁПОТ МЁРТВЫХ", 0, "unique", "intrigue", "Узнать руку соперника и вытянуть 1 карту.",
       ("rival",)),
    _c("wolf_hunt", "ВОЛЧЬЯ ОХОТА", 1, "unique", "military", "Офицер грабит до 2 соседних вражеских городов "
       "(процветание x12 с каждого) и остаётся готов.", ("own_officer_ready",)),
    _c("tribute", "ДАНЬ", 1, "unique", "economy", "Каждый сосед с отношениями ниже 30 (кроме тех, с кем мир) "
       "платит вам 50 золота."),
    _c("feigned_retreat", "ЛОЖНОЕ ОТСТУПЛЕНИЕ", 1, "unique", "military", "Свой офицер: +60% силы на 2 хода.",
       ("own_officer",)),
    _c("fire_rain", "ОГНЕННЫЙ ДОЖДЬ", 2, "unique", "military", "Соседний вражеский город: все войска там "
       "теряют 35%.", ("enemy_adj_any",)),
    _c("harem_intrigue", "ГАРЕМНЫЕ ИНТРИГИ", 1, "unique", "intrigue", "Из совета соперника изгнан самый "
       "неверный советник (верность -20). Его карты уходят из колоды.", ("rival",)),
    _c("genie_lamp", "ЛАМПА ДЖИННА", 0, "unique", "council", "+2 ОД и 1 карта. Сгорает.", exhaust=True),
    _c("winter_storm", "ЗИМНЯЯ БУРЯ", 2, "unique", "military", "Все офицеры соперника скованы льдом: в "
       "его следующий ход они не ходят и не штурмуют.", ("rival",)),
    _c("hero_saga", "САГА О ГЕРОЕ", 1, "unique", "military", "Свой офицер: +50% силы на 4 хода, верность 100.",
       ("own_officer",)),
    _c("mead_feast", "МЕДОВЫЙ ПИР", 1, "unique", "council", "Офицеры в своём городе: верность +20, отряды "
       "+15% силы на 2 хода.", ("own_city_officers",)),
    _c("bill", "ВЕКСЕЛЬ БАНКА", 0, "unique", "economy", "+300 золота. Сгорает.", exhaust=True),
    _c("mercenary_company", "НАЁМНАЯ РОТА", 1, "unique", "recruit", "150 золота: наёмники на 350 мощи в "
       "свой город.", ("own_city",), gold=150),
    _c("secret_auction", "ТАЙНЫЙ АУКЦИОН", 1, "unique", "intrigue", "Забрать случайную карту из руки "
       "соперника себе в руку.", ("rival",)),
    _c("rune_gates", "РУННЫЕ ВРАТА", 1, "unique", "military", "Свой город: оборона x2 на 5 ходов.",
       ("own_city",)),
    _c("deep_vein", "ГЛУБИННАЯ ЖИЛА", 1, "unique", "economy", "+35 золота за каждый свой город."),
    _c("forge_golem", "ГОЛЕМ ИЗ ГОРНА", 2, "unique", "recruit", "Свой город: железный голем и жрец рун.",
       ("own_city",)),
    _c("mushroom_haze", "ГРИБНОЙ ДУРМАН", 1, "unique", "intrigue", "В колоду соперника ложатся 2 "
       "ГАЛЛЮЦИНАЦИИ: вытянутая выбивает из руки другую карту.", ("rival",)),
    _c("troll_wakes", "ТРОЛЛЬ ПРОСНУЛСЯ", 2, "unique", "recruit", "Свой город: тролль. Сгорает.",
       ("own_city",), exhaust=True),
    _c("thievery", "ВОРОВСТВО", 1, "unique", "economy", "Украсть до 80 золота у соседней державы.",
       ("rival_neighbor",)),
    _c("dragon_gold", "ЗОЛОТО ДРАКОНА", 0, "unique", "economy", "+400 золота. Сгорает.", exhaust=True),
    _c("city_watch", "ГОРОДСКАЯ СТРАЖА", 1, "moderate", "council", "Свой город: порядок +4, воровской притон "
       "разогнан.", ("own_city",)),
    _c("thieves_guild", "ВОРОВСКАЯ ГИЛЬДИЯ", 1, "moderate", "intrigue", "Вражеский город: порядок -4; если он "
       "упал ниже 4 - там заводится воровской притон (процветание -1, подать на 30% меньше).", ("enemy_town",)),
    _c("head_hunters", "ОХОТНИКИ ЗА ГОЛОВАМИ", 1, "moderate", "military", "Соседнее гоблинское логово: "
       "войска там теряют 25%, за головы +40 золота.", ("enemy_lair",)),
    _c("goblin_tongue", "ГОБЛИНСКИЙ ТОЛМАЧ", 1, "moderate", "diplomacy", "Уговорить вожака без золота: 4 хода "
       "орда не трогает вас (а вы её), и ватага гоблинов на 100 мощи переходит к вам в свой город.",
       ("own_city",)),
    _c("shiny_pile", "КУЧА БЛЕСТЯШЕК", 1, "moderate", "economy", "+20 золота за каждое своё логово; пока "
       "великой постройки орды нет - +30."),
    _c("ancient_map", "ДРЕВНЯЯ КАРТА", 1, "unique", "military", "Свой офицер переходит в любой свой город "
       "и остаётся готов.", ("own_officer_ready", "dest_any_one")),

    # --- feats: one of each per campaign, earned by an officer's deed (``FEATS``) -----------------
    _c("ford_hero", "ГЕРОЙ БРОДА", 1, "feat", "military", "Подвиг: удержал город вопреки силе врага. "
       "Свой офицер: +35% силы на 3 хода, верность 100.", ("own_officer",)),
    _c("goblin_bane", "ГРОЗА ГОБЛИНОВ", 1, "feat", "recruit", "Подвиг: взял 2 логова. Трофеи: +150 "
       "золота и новобранцы на 120 мощи в своём городе.", ("own_city",)),
    _c("golden_governor", "ЗОЛОТОЙ НАМЕСТНИК", 1, "feat", "economy", "Подвиг: 4 города державы расцвели до предела. "
       "+50 золота за каждый свой город с процветанием 7+."),
    _c("wall_first", "ПЕРВЫЙ НА СТЕНЕ", 2, "feat", "military", "Подвиг: взял чужую столицу вопреки силе. Штурм соседнего "
       "города с +25% силы.", ("enemy_adj", "attackers")),
    _c("unbroken", "НЕСОКРУШИМЫЙ", 0, "feat", "military", "Подвиг: 8 побед подряд. Свой офицер снова "
       "готов, его отряд +20% силы на 2 хода.", ("own_officer",)),
    _c("peacemaker", "МИРОТВОРЕЦ", 1, "feat", "diplomacy", "Подвиг: 7 договоров о мире и союзе сразу. Мир "
       "на 10 ходов с державой при отношениях 20+.", ("rival_diplo",)),
    _c("giant_slayer", "ПОБЕДИТЕЛЬ ГИГАНТОВ", 2, "feat", "military", "Подвиг: победил втрое сильнейшего "
       "врага. Все ваши отряды +20% силы на 3 хода."),
    _c("war_legend", "ЛЕГЕНДА ВОЙНЫ", 2, "feat", "military", "Подвиг: дорос до 10 уровня. Штурм из городов "
       "в 3 дорогах от цели, +40% силы.", ("enemy_reach", "attackers_far")),

    # --- vices: a councillor's flaws come into the deck with him ---------------------------------
    _c("sloth", "ЛЕНЬ", 0, "vice", "vice", "Порок советника: мёртвая карта. Ничего не делает, только "
       "занимает место в руке.", unplayable=True),
    _c("embezzle", "КАЗНОКРАДСТВО", 0, "vice", "vice", "Порок советника: вытянув, держава теряет 40 золота "
       "(до пятой части казны).", unplayable=True, on_draw=True),
    _c("rudeness", "ГРУБОСТЬ", 0, "vice", "vice", "Порок советника: вытянув, отношения со случайной "
       "державой -10.", unplayable=True, on_draw=True),
    _c("envy", "ЗАВИСТЬ", 0, "vice", "vice", "Порок советника: вытянув, верность другого случайного "
       "советника -10.", unplayable=True, on_draw=True),
    _c("drink", "ПЬЯНСТВО", 0, "vice", "vice", "Порок советника: вытянув, в следующий ход на 1 ОД меньше.",
       unplayable=True, on_draw=True),
    _c("cowardice", "ТРУСОСТЬ", 0, "vice", "vice", "Порок советника: вытянув, его отряд на 2 хода слабее "
       "на 15%.", unplayable=True, on_draw=True),
    _c("blabber", "БОЛТЛИВОСТЬ", 0, "vice", "vice", "Порок советника: вытянув, он выбалтывает тайны - "
       "случайный соперник видит вашу руку и тянет карту.", unplayable=True, on_draw=True),
    _c("gambling", "АЗАРТ", 0, "vice", "vice", "Порок советника: вытянув, он играет на казённые: "
       "чаще проигрывает 50 золота, реже выигрывает 25.", unplayable=True, on_draw=True),
    _c("cruelty", "ЖЕСТОКОСТЬ", 0, "vice", "vice", "Порок советника: вытянув, в его городе процветание -1.",
       unplayable=True, on_draw=True),
    _c("pride", "ГОРДЫНЯ", 1, "vice", "vice", "Порок советника: выслушать его стоит 1 ОД и ничего не даёт. "
       "Осталась в руке к концу хода - он обижен, что его не слушают: верность -8."),

    # --- curses -----------------------------------------------------------------------------------
    _c("unrest", "СМУТА", 0, "curse", "curse", "Мёртвая карта. Исчезнет через 3 хода.", unplayable=True,
       expires=3),
    _c("fire", "ПОЖАР", 0, "curse", "curse", "Вытянув - потерять четверть казны (до 150).", on_draw=True),
    _c("plague", "ЧУМА", 0, "curse", "curse", "Вытянув - процветание случайного своего города -2. Может "
       "перекинуться в колоду снова.", on_draw=True),
    _c("desertion", "ДЕЗЕРТИРСТВО", 0, "curse", "curse", "Вытянув - самый сильный отряд теряет воина.",
       on_draw=True),
    _c("strife", "РАСПРИ В СОВЕТЕ", 0, "curse", "curse", "Слабый совет спорит. Мёртвая карта на 2 хода.",
       unplayable=True, expires=2),
    _c("fatigue", "УСТАЛОСТЬ", 0, "curse", "curse", "Мёртвая карта на 3 хода.", unplayable=True, expires=3),
    _c("war_fatigue", "ВОЕННАЯ УСТАЛОСТЬ", 0, "curse", "curse", "Цена военного курса: каждый штурм. "
       "Мёртвая карта на 4 хода.", unplayable=True, expires=4),
    _c("debt", "ДОЛГ", 0, "curse", "curse", "Вытянув - проценты 40 золота. Сыграть: вернуть 220 золота, "
       "и долг сгорает.", gold=220, on_draw=True, exhaust=True),
    _c("haze", "ГАЛЛЮЦИНАЦИИ", 0, "curse", "curse", "Вытянув - случайная другая карта уходит из руки в сброс.",
       on_draw=True),
]

CARDS: Dict[str, Card] = {c.key: c for c in _CARDS}

BASE_SET: Tuple[str, ...] = ("tax", "tax", "tax", "march", "assault")


@dataclass(frozen=True)
class Course:
    key: str
    name: str
    base: Tuple[str, ...]       # the six cards of state on this course
    plus: str
    minus: str


COURSES: Dict[str, Course] = {c.key: c for c in (
    Course("balance", "РАВНОВЕСИЕ", BASE_SET + ("muster",), "Всего понемногу.", "Без штрафа."),
    Course("war", "ВОЙНА", ("assault", "assault", "assault", "march", "tax", "muster"),
           "Штурм приходит в руку почти каждый ход.",
           "ВОЕННАЯ УСТАЛОСТЬ: каждый штурм кладёт в колоду мёртвую карту. Свои города сами не растут."),
    Course("economy", "ХОЗЯЙСТВО", ("tax", "tax", "tax", "fair", "golden_age", "muster"),
           "Поборы не снижают процветание, города растут каждые 3 хода, Золотой век в основе.",
           "ЛАКОМАЯ ДОБЫЧА: соседи охотнее нападают на богатую державу. Ни штурма, ни похода в основе."),
    Course("defense", "ОБОРОНА", ("tax", "tax", "fortify", "sortie", "march", "muster"),
           "Оборона всех своих городов x1.25, укрепления и вылазка в основе.",
           "Штурма в основе нет: расширяться можно лишь картами советников."),
    Course("intrigue", "ТАЙНАЯ ПОЛИТИКА", ("tax", "tax", "letters", "bribe", "assault", "muster"),
           "Половина чужих проклятий перехвачена, заговоры удаются чаще.",
           "ПАРАНОЙЯ: верность всех своих офицеров падает на 1 каждый ход."),
)}
COURSE_BASE_CD, COURSE_MIN_CD = 10, 3

# cards that do not suit the horde (it has no diplomacy, writes no letters, holds no fairs) and what
# goblins get in their place
GOBLIN_SWAP: Dict[str, str] = {"truce": "intimidate", "grand_embassy": "great_fear", "letters": "dirty_tricks",
                               "fair": "flea_market", "golden_age": "fat_year"}


def localize(faction: Optional[str], key: str) -> str:
    return GOBLIN_SWAP.get(key, key) if faction == "goblin" else key


def course_base(faction: Optional[str], course: str) -> Tuple[str, ...]:
    """The cards of state of a course for this realm: goblins get their own versions; every human
    realm buys the horde off with one card instead of a tax (instead of an assault on the war course)."""
    base = [localize(faction, k) for k in COURSES[course].base]
    if faction and faction != "goblin":
        drop = "tax" if base.count("tax") >= 2 else "assault"
        base[len(base) - 1 - base[::-1].index(drop)] = "buy_off"
    return tuple(base)


def course_cooldown(council: List[str], stats: Stats = None) -> int:
    """Turns before the course may change again: 10, one less for every 6 points of the council's
    УПРАВЛЕНИЕ above 40, never under 3."""
    gov = council_totals(council, stats)["УПРАВЛЕНИЕ"]
    return max(COURSE_MIN_CD, COURSE_BASE_CD - max(0, gov - 40) // 6)

FACTION_CARD: Dict[str, str] = {
    "aldern": "edict", "sylvan": "mother_tree", "ashen": "harvest", "khanate": "great_raid",
    "sultanate": "desert_caravans", "north": "longships", "league": "golden_contract",
    "highland": "book_of_grudges", "goblin": "brood",
}

# stat -> (card for the first threshold, card for the second)
THRESHOLD_CARDS: Dict[str, Tuple[str, str]] = {
    "УПРАВЛЕНИЕ": ("reform", "purge"),
    "ВЕРБОВКА": ("talent_search", "conscription"),
    "ЛОГИСТИКА": ("forced_march", "blitz"),
    "РАЗВЕДКА": ("scouts", "all_seeing"),
    "ДИПЛОМАТИЯ": ("truce", "grand_embassy"),
    "ИНТРИГА": ("letters", "plot"),
}

# deeds that earn a feat card (one of each per campaign); checked in campaign.py
FEATS: Dict[str, str] = {
    "ford_hero": "удержать город, когда шанс устоять был не выше 15%",
    "goblin_bane": "участвовать во взятии 2 гоблинских логов",
    "golden_governor": "быть лучшим управленцем в городах державы, когда 4 из них расцвели до предела",
    "wall_first": "взять штурмом столицу державы, когда шанс был меньше половины",
    "unbroken": "выиграть 8 боёв подряд",
    "peacemaker": "сидеть в совете, когда у державы 7 договоров о мире и союзе сразу (лучший дипломат совета)",
    "giant_slayer": "победить, когда сила врага была втрое больше",
    "war_legend": "дорасти до 10 уровня",
}

# the realm's own cards in every deck, whoever rules and sits in the council (the faction's passive)
PASSIVE_CARDS: Dict[str, Tuple[str, ...]] = {"aldern": ("peers_court",)}

# the faction's unique cards; each goes to one officer (``_holders`` picks who)
UNIQUES: Dict[str, Tuple[str, ...]] = {
    "aldern": ("charter", "griffon_order", "peers_court"),
    "sylvan": ("forest_wrath", "thicket_spirits", "moon_rite"),
    "ashen": ("plague_cauldron", "raise_dead", "dead_whisper"),
    "khanate": ("wolf_hunt", "tribute", "feigned_retreat"),
    "sultanate": ("fire_rain", "harem_intrigue", "genie_lamp"),
    "north": ("winter_storm", "hero_saga", "mead_feast"),
    "league": ("bill", "mercenary_company", "secret_auction"),
    "highland": ("rune_gates", "deep_vein", "forge_golem"),
    "goblin": ("mushroom_haze", "troll_wakes", "thievery"),
}
WANDERING_UNIQUES = {"dragon_gold": "highland", "ancient_map": "sylvan"}   # treasures found far from home

# personal card pools by the officer's strongest stat
_POOLS: Dict[str, Dict[str, Tuple[str, ...]]] = {
    "УПРАВЛЕНИЕ": {"basic": ("tax",), "moderate": ("fair", "caravan", "tithe", "build", "loan"),
                   "junk": ("hunt", "tourney", "parade")},
    "ВЕРБОВКА": {"basic": ("levy",), "moderate": ("militia_call", "volunteers", "mobilize", "sortie"),
                 "junk": ("guard", "feast")},
    "ЛОГИСТИКА": {"basic": ("march", "assault"), "moderate": ("supplies", "siege", "raid", "fortify", "reinforce"),
                  "junk": ("pilgrimage", "hunt", "withdraw")},
    "РАЗВЕДКА": {"basic": ("assault",), "moderate": ("patrol", "sabotage", "raid", "morale", "counterspy", "ambush",
                                                  "intercept"),
                 "junk": ("omen", "denounce")},
    "ДИПЛОМАТИЯ": {"basic": ("tax",), "moderate": ("embassy", "trade_pact", "fair", "buyout"),
                   "junk": ("old_debt", "feast")},
    "ИНТРИГА": {"basic": ("levy",), "moderate": ("bribe", "arson", "counterspy", "agitators"),
                "junk": ("denounce", "omen")},
}


def _holders() -> Dict[str, str]:
    """card -> officer. Mostly the faction's *weakest* officers hold its unique cards (so taking
    one into the council costs competence); one goes to a middling officer."""
    from .faces import presence
    out: Dict[str, str] = {}
    for fk, cards in UNIQUES.items():
        offs = sorted(OFFICERS[fk][1:], key=presence)
        picks = [offs[0], offs[1], offs[len(offs) // 2]]
        for card, o in zip(cards, picks):
            out[card] = o.key
    for card, fk in WANDERING_UNIQUES.items():
        taken = set(out.values())
        offs = [o for o in sorted(OFFICERS[fk][1:], key=presence) if o.key not in taken]
        out[card] = offs[2].key
    return out


def _empty_heads() -> set:
    """Two of each faction's most able officers who bring nothing but trifles to the table."""
    from .faces import presence
    out = set()
    for fk, offs in OFFICERS.items():
        best = sorted(offs[1:], key=presence, reverse=True)
        out.update(o.key for o in best[:2])
    return out


def _personal() -> Dict[str, Tuple[str, ...]]:
    holders = _holders()
    by_officer: Dict[str, List[str]] = {}
    for card, o in holders.items():
        by_officer.setdefault(o, []).append(card)
    empty = _empty_heads()
    used: Dict[str, int] = {}
    out: Dict[str, Tuple[str, ...]] = {}
    for o in OFFICER.values():
        if o.rank == 0:
            out[o.key] = ()                      # the leader brings the faction card
            continue
        r = random.Random(f"cards:{o.key}")
        cards = list(by_officer.get(o.key, ()))
        n = 2 if o.rank <= 2 else 1 + (r.random() < 0.5)
        while len(cards) < n:
            weights = [o.stats[i] ** 2 for i in range(len(STATS))]
            stat = r.choices(STATS, weights)[0]
            pool = _POOLS[stat]
            if o.key in empty or by_officer.get(o.key):
                tier = r.choice(("junk", "junk", "basic"))
            else:
                tier = r.choices(("basic", "moderate", "junk"), (0.3, 0.55, 0.15))[0]
            least = min(used.get(k, 0) for k in pool[tier])       # spread cards over the officers
            pick = r.choice([k for k in pool[tier] if used.get(k, 0) == least])
            used[pick] = used.get(pick, 0) + 1
            cards.append(pick)
        out[o.key] = tuple(cards) + VICE_OF.get(o.key, ())
    return out


VICES: Tuple[str, ...] = ("sloth", "embezzle", "rudeness", "envy", "drink", "cowardice", "blabber", "gambling",
                          "cruelty", "pride")


def _vices() -> Dict[str, Tuple[str, ...]]:
    """Some officers bring a vice into the council's deck - the able ones a little more often, so
    a strong adviser can come with a flaw. Every vice belongs to at least three officers."""
    from .faces import presence
    r = random.Random("vices")
    offs = sorted((o for o in OFFICER.values() if o.rank > 0), key=lambda o: o.key)
    score = {o.key: r.random() + 0.6 * presence(o) for o in offs}
    keys = sorted(score, key=score.get, reverse=True)[:3 * len(VICES)]
    r.shuffle(keys)
    return {k: (VICES[i % len(VICES)],) for i, k in enumerate(keys)}


VICE_OF: Dict[str, Tuple[str, ...]] = _vices()

# how a vice shows in the officer's biography ("{м|ж}" forms)
VICE_TRAIT: Dict[str, str] = {
    "sloth": "Порок: ленив{|а}, любое дело откладывает на завтра.",
    "embezzle": "Порок: нечист{|а} на руку, казна при {нём|ней} худеет.",
    "rudeness": "Порок: груб{|а} с послами, и соседи это запоминают.",
    "envy": "Порок: завистлив{|а} и плетёт козни против других советников.",
    "drink": "Порок: пьёт, и наутро совет ждёт {его|её} до полудня.",
    "cowardice": "Порок: трус{|иха}, и солдаты это чувствуют.",
    "blabber": "Порок: болтун{|ья}, тайны совета знает вся округа.",
    "gambling": "Порок: игрок, ставит на кон казённое золото.",
    "cruelty": "Порок: жесток{|а}, и горожане бегут от {него|неё}.",
    "pride": "Порок: горд{|а} и обидчив{|а}, когда {его|её} не слушают.",
}


PERSONAL: Dict[str, Tuple[str, ...]] = _personal()
UNIQUE_HOLDER: Dict[str, str] = _holders()
# СУД ПЭРОВ became Aldern's passive (PASSIVE_CARDS): its old holder brings the РИСТАЛИЩЕ instead
for _o, _cards in list(PERSONAL.items()):
    if "peers_court" in _cards:
        PERSONAL[_o] = tuple("tiltyard" if k == "peers_court" else k for k in _cards)
UNIQUE_HOLDER = {("tiltyard" if k == "peers_court" else k): o for k, o in UNIQUE_HOLDER.items()}
UNIQUES["aldern"] = tuple("tiltyard" if k == "peers_court" else k for k in UNIQUES["aldern"])


# the new trades go to a few officers each, the best at them in some realms
_TRADES = {"master_builder": ("УПРАВЛЕНИЕ", ("highland", "sultanate", "aldern", "league")),
           "physician": ("ЛОГИСТИКА", ("sylvan", "sultanate", "north", "aldern")),
           "sappers": ("РАЗВЕДКА", ("khanate", "north", "highland", "league"))}


_TRADES.update({"head_hunters": ("РАЗВЕДКА", ("aldern", "league", "highland", "khanate")),
                "goblin_tongue": ("ДИПЛОМАТИЯ", ("sultanate", "ashen", "north")),
                "shiny_pile": ("УПРАВЛЕНИЕ", ("goblin", "goblin")),
                "city_watch": ("РАЗВЕДКА", ("aldern", "highland", "north", "sultanate")),
                "thieves_guild": ("ИНТРИГА", ("league", "ashen", "khanate", "sylvan")),
                "tiltyard": ("УПРАВЛЕНИЕ", ("aldern", "khanate", "sultanate", "league"))})


def _give_trades() -> None:
    empty = _empty_heads()                       # the able "trifle bringers" stay so (the council's dilemma)
    for card, (stat, realms) in _TRADES.items():
        i = STATS.index(stat)
        for f in realms:
            offs = [o for o in OFFICER.values() if o.faction == f and o.rank > 0 and card not in PERSONAL[o.key]
                    and o.key not in empty]
            best = max(offs, key=lambda o: (o.stats[i], o.key))
            PERSONAL[best.key] = PERSONAL[best.key] + (card,)


_give_trades()


def newcomer_cards(officer: Officer) -> List[str]:
    """A young talent brings one plain card of his best skill."""
    best = STATS[max(range(len(STATS)), key=lambda i: officer.stats[i])]
    pool = _POOLS[best]["basic"] or _POOLS[best]["junk"]
    return [random.Random(f"newcomer-card:{officer.key}").choice(pool)]


def personal(officer: str) -> Tuple[str, ...]:
    return PERSONAL.get(officer, ())


Stats = Optional[Dict[str, Sequence[int]]]      # officer -> current stats (a campaign changes them)


def council_totals(council: List[str], stats: Stats = None) -> Dict[str, int]:
    get = (lambda o: stats[o]) if stats is not None else (lambda o: OFFICER[o].stats)
    return {st: sum(get(o)[i] for o in council) for i, st in enumerate(STATS)}


def threshold_cards(council: List[str], stats: Stats = None, faction: Optional[str] = None) -> List[str]:
    out = []
    totals = council_totals(council, stats)
    for st in STATS:
        mid, top = THRESHOLD_CARDS[st]
        if totals[st] >= THRESHOLDS[0]:
            out.append(localize(faction, mid))
        if totals[st] >= THRESHOLDS[1]:
            out.append(localize(faction, top))
    return out


def competence(council: List[str], stats: Stats = None) -> int:
    """How many thresholds the council clears (0..12)."""
    return len(threshold_cards(council, stats))


def hand_size(council: List[str], stats: Stats = None) -> int:
    return HAND + (1 if competence(council, stats) >= 6 else 0)


def reserve(council: List[str], stats: Stats = None) -> int:
    """Cards the realm may keep in hand from one turn to the next."""
    c = competence(council, stats)
    return 2 if c >= 8 else 1 if c >= 3 else 0


def intercepts(council: List[str], stats: Stats = None) -> bool:
    """A council with a good eye for spies (first РАЗВЕДКА threshold) catches a third of the
    curses rivals slip into its deck."""
    return council_totals(council, stats)["РАЗВЕДКА"] >= THRESHOLDS[0]


def strife(council: List[str], stats: Stats = None) -> bool:
    """A weak council quarrels: every third turn a dead card lands in its own deck."""
    return competence(council, stats) <= 1


def muster_turns(council: List[str], stats: Stats = None) -> int:
    """How long СБОР ВОЙСК keeps a city's recruiting open: this turn, +1 with the council's
    ВЕРБОВКА at the first threshold, +2 at the second."""
    v = council_totals(council, stats)["ВЕРБОВКА"]
    return 1 + (v >= THRESHOLDS[0]) + (v >= THRESHOLDS[1])


def deck_for(faction: str, council: List[str], course: str = "balance") -> List[str]:
    """Card keys of the realm's deck (curses come on top of this during play)."""
    cards = list(course_base(faction, course)) + [FACTION_CARD[faction], "sickness"] + \
        list(PASSIVE_CARDS.get(faction, ()))
    for o in council:
        cards.extend(PERSONAL.get(o, ()))
    cards.extend(threshold_cards(council, faction=faction))
    return cards


def best_council(faction_officers: List[Officer], leader: Officer) -> List[str]:
    """A default council: the leader and the four most able officers."""
    from .faces import presence
    rest = sorted((o for o in faction_officers if o.key != leader.key), key=presence, reverse=True)
    return [leader.key] + [o.key for o in rest[:COUNCIL_SEATS - 1]]
