import unittest
import unittest.mock

from game import horde, reign
from game.campaign import Campaign
from game.cards import CARDS, GOBLIN_SWAP, course_base, deck_for, threshold_cards
from game.factions import neighbors
from game.officers import OFFICER, OFFICERS


def _turn_of(c, f):
    c.current = c.order.index(f)
    c._start_turn(f)


class HordeTest(unittest.TestCase):
    def setUp(self):
        self.c = Campaign("aldern", seed=3)
        self.c.no_events = True

    def _great(self, kind):
        c = self.c
        lair = c.cities_of("goblin")[0]
        c.gold["goblin"] = horde.GREAT_COST + 50
        self.assertTrue(horde.build(c, kind, lair))
        return lair

    def test_great_building_costs_gold_and_tells_the_player(self):
        c = self.c
        lair = c.cities_of("goblin")[0]
        self.assertFalse(horde.can_build(c, "totem", lair)[0])          # the horde is poor at first
        self._great("totem")
        self.assertEqual(c.gold["goblin"], 50)
        self.assertEqual(horde.great(c), ("totem", lair))
        self.assertEqual(c.world_events[-1][1], "great:totem")          # shown as a big card
        c.gold["goblin"] = 5000
        self.assertFalse(horde.can_build(c, "pit", lair)[0])            # one at a time

    def test_lost_with_its_lair_and_only_the_same_again(self):
        c = self.c
        lair = self._great("pit")
        c.pit.append(("aldern", 100))
        c._take("aldern", lair, [])
        self.assertIsNone(horde.great(c))
        self.assertEqual(c.pit, [])                                       # the captives ran home
        other = c.cities_of("goblin")[0]
        c.gold["goblin"] = 5000
        self.assertFalse(horde.can_build(c, "totem", other)[0])          # the horde keeps its manner
        self.assertTrue(horde.can_build(c, "pit", other)[0])

    def test_totem_makes_goblins_fight_harder(self):
        c = self.c
        lair = c.cities_of("goblin")[1]
        before = c.defense_power(lair)
        self._great("totem")
        self.assertAlmostEqual(c.defense_power(lair), before * horde.TOTEM_MULT)
        self.assertEqual(horde.fury(c, "goblin", "aldern"), (horde.TOTEM_MULT, 1.0))

    def test_totem_in_a_real_battle(self):
        from game.match import headless_campaign_world
        self._great("totem")
        c = self.c
        lair = c.cities_of("goblin")[0]
        from game.campaign import Battle
        b = Battle("goblin", "aldern", lair, [], [])
        c._forces(b)
        self.assertEqual(b.fury[0], horde.TOTEM_MULT)
        world = headless_campaign_world(b)
        self.assertEqual(world.fury, b.fury)

    @unittest.mock.patch("game.horde.SNATCH", 0.0)
    def test_pit_ransom_or_sacrifice(self):
        c = self.c
        lair = self._great("pit")
        c.pit.append(("aldern", 100))
        c.gold["goblin"] = 0                                              # poor: takes the ransom
        gold = c.gold["aldern"]
        horde.turn(c, "goblin")
        self.assertEqual(c.gold["aldern"], gold - int(100 * horde.RANSOM))
        self.assertEqual(c.pit, [])
        c.pit.append(("aldern", 100))
        c.gold["goblin"] = 5000                                           # rich: blood instead
        c.income["goblin"] = [2000] * 4
        free = sum(t.power for t in c.free[lair])
        horde.turn(c, "goblin")
        self.assertGreater(sum(t.power for t in c.free[lair]), free)

    def test_night_snatchers(self):
        c = self.c
        self._great("pit")
        with unittest.mock.patch("game.horde.SNATCH", 1.0):
            c.gold["goblin"] = 0
            horde.turn(c, "goblin")
        self.assertGreater(c.stats["captives"].total(), 0)

    def test_pit_fills_after_won_battles_and_raids(self):
        c = self.c
        self._great("pit")
        c.rng.seed(1)
        horde.on_battle(c, None, [("aldern", 100)] * 20)
        self.assertTrue(0 < len(c.pit) <= horde.PIT_MAX)
        n = len(c.pit)
        horde.on_raid(c, "goblin", c.cities_of("aldern")[0])
        self.assertEqual(len(c.pit), min(horde.PIT_MAX, n + 1))

    def test_warg_pen_hires_cheap_riders_anywhere(self):
        c = self.c
        lair = next(x for x in c.cities_of("goblin") if "wolf_rider" not in __import__("game.factions").factions.CITY[x].pool)
        self.assertFalse(c.can_hire(lair, "wolf_rider")[0])
        self._great("warg_pen")
        c.gold["goblin"] = 1000
        self.assertTrue(c.can_hire(lair, "wolf_rider")[0])                # no muster needed
        self.assertEqual(c.hire_price(lair, "wolf_rider"), round(145 * horde.PEN_PRICE))
        self.assertAlmostEqual(c.troop_upkeep("goblin", "wolf_rider"),
                               __import__("game.units").units.ROSTER["wolf_rider"].upkeep * horde.PEN_UPKEEP)

    def test_buy_off_keeps_the_horde_away(self):
        c = self.c
        self.assertTrue(horde.threatened(c, "aldern"))
        border = horde.border(c, "aldern")[0]
        lair = next(n for n in neighbors(border) if c.owner[n] == "goblin")
        self.assertFalse(c.at_peace("goblin", "aldern"))
        price = horde.buy_off_price(c, "aldern")
        g, gg = c.gold["aldern"], c.gold["goblin"]
        horde.buy_off(c, "aldern")
        self.assertEqual(c.gold["aldern"], g - price)
        self.assertEqual(c.gold["goblin"], gg + price)                    # the horde grows rich on it
        self.assertTrue(c.at_peace("goblin", "aldern"))
        from game.cardplay import options
        self.assertNotIn(border, options(c, "goblin", "assault", []))
        self.assertNotIn(lair, options(c, "aldern", "assault", []))       # and the payer leaves it alone
        for _ in range(horde.BUY_OFF_TURNS):
            horde.tick_buy_off(c, "aldern")
        self.assertFalse(c.at_peace("goblin", "aldern"))

    def test_buy_off_without_a_horde_keeps_the_silver(self):
        c = self.c
        c.realms["goblin"].alive = False
        g = c.gold["aldern"]
        horde.buy_off(c, "aldern")
        self.assertEqual(c.gold["aldern"], g + horde.BUY_OFF_SILVER * len(c.cities_of("aldern")))

    def test_buy_off_replaces_a_card_of_state(self):
        self.assertEqual(course_base("aldern", "balance").count("buy_off"), 1)
        self.assertEqual(course_base("aldern", "balance").count("tax"), 2)
        self.assertEqual(course_base("aldern", "war").count("assault"), 2)
        self.assertEqual(course_base("aldern", "war").count("tax"), 1)
        self.assertNotIn("buy_off", course_base("goblin", "balance"))
        for f in OFFICERS:
            self.assertEqual(len(course_base(f, "economy")), 6)

    def test_goblins_get_cards_that_suit_them(self):
        self.assertIn("flea_market", course_base("goblin", "economy"))
        self.assertIn("dirty_tricks", course_base("goblin", "intrigue"))
        strong = [o.key for o in OFFICERS["aldern"]][:1] * 5
        stats = {strong[0]: [20] * 6}
        self.assertIn("truce", threshold_cards(strong, stats, "aldern"))
        cards = threshold_cards(strong, stats, "goblin")
        self.assertIn("intimidate", cards)
        self.assertIn("great_fear", cards)
        self.assertFalse(set(GOBLIN_SWAP) & set(cards))
        council = [o.key for o in OFFICERS["goblin"][:5]]
        self.assertFalse(set(GOBLIN_SWAP) & set(deck_for("goblin", council, "intrigue")))
        for k in GOBLIN_SWAP.values():
            self.assertEqual(CARDS[k].tier, CARDS[next(a for a, b in GOBLIN_SWAP.items() if b == k)].tier)

    def test_intimidate_takes_gold_or_ruins(self):
        c = self.c
        _turn_of(c, "goblin")
        c.gold["aldern"] = 100
        from game.cardplay import EFFECTS
        EFFECTS["intimidate"](c, "goblin", ["aldern"])
        self.assertEqual(c.gold["aldern"], 40)
        c.gold["aldern"] = 0
        before = sum(c.prosperity[x] for x in c.cities_of("aldern"))
        EFFECTS["intimidate"](c, "goblin", ["aldern"])
        self.assertEqual(sum(c.prosperity[x] for x in c.cities_of("aldern")), before - 1)

    def test_goblin_personal_cards(self):
        from game.cards import PERSONAL
        holders = {k: [o for o, cards in PERSONAL.items() if k in cards]
                   for k in ("head_hunters", "goblin_tongue", "shiny_pile")}
        self.assertEqual(len(holders["head_hunters"]), 4)
        self.assertEqual(len(holders["goblin_tongue"]), 3)
        self.assertEqual({OFFICER[o].faction for o in holders["shiny_pile"]}, {"goblin"})
        c = self.c
        from game.cardplay import EFFECTS
        g = c.gold["goblin"]
        EFFECTS["shiny_pile"](c, "goblin", [])
        self.assertEqual(c.gold["goblin"], g + 30 * len(c.cities_of("goblin")))
        city = c.cities_of("aldern")[0]
        EFFECTS["goblin_tongue"](c, "aldern", [city])
        self.assertTrue(c.at_peace("aldern", "goblin"))
        self.assertTrue(any(t.key.startswith("goblin") for t in c.free[city]))

    def test_goblin_reign_traits(self):
        goblin = {reign.reign_of(o.key) for o in OFFICERS["goblin"]}
        people = {reign.reign_of(o) for o in OFFICER if OFFICER[o].faction != "goblin"}
        self.assertFalse(goblin & reign.HUMAN_ONLY)
        self.assertFalse(people & reign.GOBLIN_ONLY)
        self.assertTrue(goblin & reign.GOBLIN_ONLY)
        self.assertTrue(people & reign.HUMAN_ONLY)

    def test_horde_hoards_and_builds(self):
        c = Campaign(None, seed=2)
        c.turn = 10
        self.assertEqual(horde.saving(c, "goblin"), horde.GREAT_COST * 0.8)
        self.assertEqual(horde.saving(c, "aldern"), 0)
        c.force_great = "warg_pen"
        c.gold["goblin"] = horde.GREAT_COST
        _turn_of(c, "goblin")
        horde.ai_build(c, "goblin")
        self.assertEqual(horde.great(c)[0], "warg_pen")
        self.assertEqual(horde.saving(c, "goblin"), 0)


if __name__ == "__main__":
    unittest.main()
