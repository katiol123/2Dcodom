import unittest

from game import buildings, population, reign
from game.campaign import Campaign
from game.cards import CARDS
from game.factions import CITY, FACTION, neighbors
from game.officers import OFFICER


class SicknessTest(unittest.TestCase):
    def setUp(self):
        self.c = Campaign("aldern", seed=6)
        self.c.no_events = True

    def test_sickness_card_redraws_and_sickens_a_city(self):
        c, r = self.c, self.c.realms["aldern"]
        n = len(r.hand)
        inst = next(x for x in r.all_cards() if x.key == "sickness")
        for pile in (r.draw, r.hand, r.discard):
            if inst in pile:
                pile.remove(inst)
        r.draw.append(inst)
        c._draw("aldern", 1)
        self.assertEqual(len(r.hand), n + 1)                     # a card in its place
        self.assertIn(inst, r.discard)                            # it stays in the deck
        self.assertNotIn(inst, r.hand)
        self.assertTrue(any(c.owner[x] == "aldern" for x in c.sick) or
                        c.stats["outbreaks_stopped"]["aldern"])

    def test_infirmaries_stack(self):
        c = self.c
        city = FACTION["aldern"].capital
        self.assertEqual(buildings.sickness_block(c, city), 0)
        c.buildings[city] = ["infirmary"]
        self.assertAlmostEqual(buildings.sickness_block(c, city), 0.5)
        near = next(n for n in neighbors(city) if c.owner[n] == "aldern")
        c.buildings[near] = ["infirmary"]
        self.assertAlmostEqual(buildings.sickness_block(c, city), 0.75)

    def test_the_sick_may_die_and_a_ruler_is_succeeded(self):
        c = self.c
        ruler = c.leader["sylvan"]
        city = c.officer_city[ruler]
        c.sick[city] = 2
        old = population.SICK_DEATH
        population.SICK_DEATH = 1.0
        try:
            population.turn(c, "sylvan")
        finally:
            population.SICK_DEATH = old
        self.assertIn(ruler, c.dead)
        self.assertNotEqual(c.leader["sylvan"], ruler)
        self.assertEqual(c.sick[city], 1)

    def test_plague_adds_sickness_cards(self):
        c = self.c
        before = sum(1 for x in c.realms["north"].all_cards() if x.key == "sickness")
        population.plague_cards(c)
        after = sum(1 for x in c.realms["north"].all_cards() if x.key == "sickness")
        self.assertEqual(after, before + population.PLAGUE_CARDS)


class NewcomerTest(unittest.TestCase):
    def test_talent_comes_of_age(self):
        c = Campaign("aldern", seed=6)
        city = FACTION["aldern"].capital
        n = len(c.officers_of("aldern"))
        o = population.come_of_age(c, "aldern", city)
        self.assertIn(o, OFFICER)
        self.assertEqual(len(c.officers_of("aldern")), n + 1)
        self.assertEqual(c.officer_city[o], city)
        self.assertTrue(c.personal(o))
        self.assertIn(reign.reign_of(o), reign.REIGNS)
        from game.officers import bio
        self.assertTrue(bio(OFFICER[o]))

    def test_talent_card(self):
        c = Campaign("aldern", seed=6)
        inst = c._inst("talent_search", "threshold")
        c.realms["aldern"].hand.append(inst)
        city = c.cities_of("aldern")[0]
        n = len(c.officers_of("aldern"))
        self.assertTrue(c.play("aldern", inst, [city])[0])
        self.assertEqual(len(c.officers_of("aldern")), n + 1)

    def test_world_does_not_empty(self):
        c = Campaign(None, seed=11)
        while c.turn <= 30:
            c.run_ai(stop_at_player=False, max_turns=1)
        self.assertGreater(sum(c.stats["newcomers"].values()), 0)
        for f in c.alive():
            if f != "goblin":
                self.assertGreaterEqual(len(c.officers_of(f)), 6, f)


class BuildingTest(unittest.TestCase):
    def setUp(self):
        self.c = Campaign("aldern", seed=6)
        self.city = FACTION["aldern"].capital

    def test_build_costs_gold_and_a_point(self):
        c, city = self.c, self.city
        gold, ap = c.gold["aldern"], c.realms["aldern"].ap
        ok, _ = buildings.build(c, "aldern", city, "market")
        self.assertTrue(ok)
        self.assertEqual(c.gold["aldern"], gold - buildings.BUILDINGS["market"].cost)
        self.assertEqual(c.realms["aldern"].ap, ap - 1)
        self.assertFalse(buildings.can_build(c, "aldern", city, "market")[0])     # one of each
        c.gold["aldern"] = 9999
        for k in ("walls", "tower"):
            buildings.build(c, "aldern", city, k)
        self.assertFalse(buildings.can_build(c, "aldern", city, "temple")[0])     # capital: 3 slots

    def test_effects(self):
        c, city = self.c, self.city
        d = c.defense_power(city)
        c.buildings[city] = ["walls"]
        self.assertAlmostEqual(c.defense_power(city), d * 1.25, delta=1)
        c.buildings[city] = ["tower"]
        self.assertAlmostEqual(c.defense_power(city), d + buildings.TOWER_DEFENSE * 1.0 *
                               (c.defense_power(city) - d) / buildings.TOWER_DEFENSE, delta=1)
        self.assertGreater(c.defense_power(city), d)
        key = CITY[city].pool[0]
        price = c.hire_price(city, key)
        c.buildings[city] = ["barracks"]
        self.assertLess(c.hire_price(city, key), price)
        c.buildings[city] = ["market"]
        gold = c.gold["aldern"]
        inst = c._inst("tax", "base")
        c.realms["aldern"].hand.append(inst)
        income = c.income_of(city, "aldern")
        c.play("aldern", inst, [city])
        self.assertEqual(c.gold["aldern"] - gold, int(income * 1.5))

    def test_capture_may_ruin_buildings(self):
        c, city = self.c, self.city
        c.buildings[city] = ["market", "walls", "tower"]
        c.rng.random = lambda: 0.0                          # everything that can burn, burns
        buildings.ruin(c, city, buildings.RUIN_CAPTURE, "город взят", all_of_them=True)
        self.assertEqual(c.buildings[city], [])

    def test_sappers(self):
        c = self.c
        enemy = next(n for x in c.cities_of("aldern") for n in neighbors(x) if c.owner[n] != "aldern")
        c.buildings[enemy] = ["walls"]
        inst = c._inst("sappers", "aldern:1")
        c.realms["aldern"].hand.append(inst)
        self.assertTrue(c.play("aldern", inst, [enemy])[0])
        self.assertEqual(c.buildings[enemy], [])

    def test_tower_shoots_in_a_real_battle(self):
        from game.campaign import Battle
        from game.match import headless_campaign_world
        c = self.c
        city = c.cities_of("sylvan")[0]
        c.buildings[city] = ["tower"]
        att = [o.key for o in c.officers_of("aldern")[:2]]
        b = Battle("aldern", "sylvan", city, att, [o.key for o in c.officers_in(city)], seed=3)
        c._forces(b)
        self.assertEqual(b.towers, 1)
        w = headless_campaign_world(b)
        self.assertEqual(len(w.towers), 1)
        while w.winner is None and w.time < 60:
            w.step(1 / 60)
        self.assertGreater(w.towers[0].dealt, 0)

    def test_new_personal_cards_handed_out(self):
        from game.cards import PERSONAL
        for k in ("master_builder", "physician", "sappers"):
            self.assertGreaterEqual(sum(1 for v in PERSONAL.values() if k in v), 3, k)
            self.assertIn(k, CARDS)

    def test_twenty_four_reigns(self):
        self.assertEqual(len(reign.REIGNS), 24)
        used = {t for _, tr in reign.REIGNS.values() for t in tr}
        self.assertEqual(used, set(reign.TRAITS))


if __name__ == "__main__":
    unittest.main()
