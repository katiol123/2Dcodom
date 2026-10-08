import unittest
import unittest.mock

from game import order
from game.campaign import Battle, Campaign
from game.campaign_ai import arrives
from game.cards import THRESHOLDS
from game.officers import STATS


def _set_council_stat(c, f, stat, total):
    i = STATS.index(stat)
    council = c.realms[f].council
    for o in council:
        c.ostats[o][i] = total // len(council)


class ScarTest(unittest.TestCase):
    def setUp(self):
        self.c = Campaign("aldern", seed=4)

    def test_logistics_lowers_the_chance(self):
        c = self.c
        _set_council_stat(c, "aldern", "ЛОГИСТИКА", 40)
        low = c.scar_chance("aldern")
        _set_council_stat(c, "aldern", "ЛОГИСТИКА", 80)
        high = c.scar_chance("aldern")
        self.assertAlmostEqual(low, 1.0)
        self.assertAlmostEqual(high, 0.5)

    def test_battle_scars_the_holder_after_the_battle(self):
        c = self.c
        city = c.cities_of("goblin")[0]
        attackers = [o.key for o in c.officers_of("aldern")[:3]]
        seen = []
        real = c.scar_chance
        c.scar_chance = lambda owner: seen.append(owner) or real(owner)
        c.attack("aldern", attackers, city)
        self.assertEqual(seen, [c.owner[city]])              # whoever holds the city after the battle

    def test_two_battles_ravage_a_city(self):
        c = self.c
        city = c.cities_of("north")[0]
        p = c.prosperity[city]
        with unittest.mock.patch.object(c, "scar_chance", lambda owner: 1.0):
            c._scar(city, "north")
            c._scar(city, "north")
        self.assertEqual(c.prosperity[city], max(1, p - 2))
        self.assertTrue(c.ravaged.get(city))
        before = c.prosperity[city]
        c.untaxed[city] = 99
        c.current = c.order.index("north")
        c.end_turn()
        self.assertEqual(c.prosperity[city], before)            # a ravaged city does not grow


class OrderTest(unittest.TestCase):
    def setUp(self):
        self.c = Campaign("aldern", seed=5)

    def test_rich_ungoverned_city_slides_into_crime(self):
        c = self.c
        city = next(x for x in c.cities_of("aldern") if c.officers_in(x))
        for o in c.officers_in(city):
            c.officer_city[o.key] = c.cities_of("aldern")[0] if city != c.cities_of("aldern")[0] else \
                c.cities_of("aldern")[1]
        c.free[city] = []
        c.prosperity[city] = 10
        self.assertLess(order.target(c, city), order.SAFE)
        c.law[city] = 0
        c.rng.seed(2)
        for _ in range(12):
            c.law[city] = 0
            order.turn(c, "aldern")
        self.assertGreater(sum(c.stats["crime"].values()), 0)
        self.assertLess(c.prosperity[city], 10)

    def test_den_skims_tax_and_is_cleared(self):
        c = self.c
        city = c.cities_of("aldern")[0]
        g = c.income_of(city, "aldern")
        c.dens.add(city)
        self.assertEqual(c.income_of(city, "aldern"), int(g * (1 - order.DEN_TAX)))
        c.law[city] = order.CLEARED
        with unittest.mock.patch("game.order.target", lambda camp, x: order.MAX):
            order.turn(c, "aldern")
        self.assertNotIn(city, c.dens)

    def test_battles_raids_and_capture_shake_order(self):
        c = self.c
        city = c.cities_of("north")[0]
        c.law[city] = 6
        c._scar(city, "north")
        self.assertEqual(c.law[city], 6 - order.BATTLE)
        c._take("aldern", city, [])
        self.assertEqual(c.law[city], order.TAKEN)
        lair = c.cities_of("goblin")[0]
        order.hit(c, lair, 3)
        self.assertNotIn(lair, c.law)                            # lairs know no order


class OrderCardsTest(unittest.TestCase):
    def test_watch_and_guild(self):
        from game.cardplay import EFFECTS, options
        from game.cards import PERSONAL
        self.assertEqual(sum(1 for c in PERSONAL.values() if "city_watch" in c), 4)
        self.assertEqual(sum(1 for c in PERSONAL.values() if "thieves_guild" in c), 4)
        c = Campaign("aldern", seed=7)
        town = c.cities_of("north")[0]
        self.assertIn(town, options(c, "aldern", "thieves_guild", []))
        self.assertFalse(set(c.cities_of("goblin")) & set(options(c, "aldern", "thieves_guild", [])))
        c.law[town] = 6
        p = c.prosperity[town]
        EFFECTS["thieves_guild"](c, "aldern", [town])
        self.assertEqual(c.law[town], 2)
        self.assertIn(town, c.dens)
        self.assertEqual(c.prosperity[town], max(1, p - 1))
        own = c.cities_of("aldern")[0]
        c.law[own] = 2
        c.dens.add(own)
        EFFECTS["city_watch"](c, "aldern", [own])
        self.assertEqual(c.law[own], 6)
        self.assertNotIn(own, c.dens)


class IntrigueTargetTest(unittest.TestCase):
    def test_watchful_rivals_are_worse_targets(self):
        c = Campaign(None, seed=6)
        self.assertEqual(arrives(c, "aldern", "north"), 1.0 if not c.intercepts(c.realms["north"].council) else 0.65)
        _set_council_stat(c, "north", "РАЗВЕДКА", THRESHOLDS[0] + 5)
        self.assertAlmostEqual(arrives(c, "aldern", "north"), 0.65)
        c.realms["north"].course = "intrigue"
        self.assertAlmostEqual(arrives(c, "aldern", "north"), 0.5)
        inst = c._inst("intercept", "base")
        c.realms["north"].hand.append(inst)
        self.assertAlmostEqual(arrives(c, "aldern", "north"), 0.5)   # not seen: we cannot know
        c.realms["aldern"].revealed["north"] = c.turn
        self.assertEqual(arrives(c, "aldern", "north"), 0.0)



class CardFaceTest(unittest.TestCase):
    def test_every_card_text_fits_its_face(self):
        import os
        os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
        from game.cardui import CARD_W
        from game.cards import CARDS
        from game.mapview import wrap
        for k, c in CARDS.items():
            self.assertLessEqual(len(wrap(c.text, CARD_W - 9)), 8, k)

    def test_plural(self):
        from game.mapview import plural
        self.assertEqual([plural(n, "ЛОГОВО", "ЛОГОВА", "ЛОГОВ") for n in (1, 2, 5, 11, 21, 22)],
                         ["ЛОГОВО", "ЛОГОВА", "ЛОГОВ", "ЛОГОВ", "ЛОГОВО", "ЛОГОВА"])


if __name__ == "__main__":
    unittest.main()
