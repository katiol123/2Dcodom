import unittest

from game.campaign import Battle, Campaign, HARDY, TRADE_SKIM, WRATH_DPS
from game.cardplay import EFFECTS, options
from game.cards import CARDS, PERSONAL
from game.factions import CITY, FACTIONS
from game.match import headless_campaign_world
from game.officers import OFFICER


class PassivesTest(unittest.TestCase):
    def test_each_realm_names_its_card_and_one_passive(self):
        for f in FACTIONS:
            self.assertEqual(len(f.mechanics), 2, f.key)

    def test_highlanders_are_hardy(self):
        c = Campaign(None, seed=3)
        city = c.cities_of("aldern")[0]
        att = [o.key for o in c.officers_of(HARDY) if c.squads[o.key]][:2]
        b = Battle(HARDY, "aldern", city, att, [o.key for o in c.officers_in(city)])
        c._forces(b)
        w = headless_campaign_world(b)
        for u in w.units:
            if u.team == 0:
                self.assertAlmostEqual(u.armor_bonus, 0.15)
                self.assertAlmostEqual(u.max_hp, u.type.hp * 1.15)
            else:
                self.assertEqual(u.armor_bonus, 0.0)

    def test_the_forest_roots_its_stormers(self):
        c = Campaign(None, seed=3)
        city = next(x for x in c.cities_of("sylvan") if CITY[x].faction == "sylvan")
        att = [o.key for o in c.officers_of("ashen") if c.squads[o.key]][:4]   # a storm that lasts
        b = Battle("ashen", "sylvan", city, att, [o.key for o in c.officers_in(city)])
        c._forces(b)
        self.assertEqual(b.wrath, (1, WRATH_DPS * c.prosperity[city]))
        w = headless_campaign_world(b)
        rooted = set()
        while w.winner is None and w.time < 30:
            w.step(1 / 60)
            rooted |= {u.id for u in w.units if u.team == 0 and u.has("wrath")}
        self.assertGreaterEqual(len(rooted), 2)                 # every 7 seconds a stormer is held

    def test_zarkhad_skims_its_partners_other_trade(self):
        c = Campaign(None, seed=3)
        c.trade[frozenset(("sultanate", "league"))] = (10, 20)
        c.trade[frozenset(("league", "north"))] = (10, 20)
        z, n = c.gold["sultanate"], c.gold["north"]
        c.current = c.order.index("north")
        c.end_turn()
        cut = int(round(20 * TRADE_SKIM))
        self.assertEqual(c.stats["gold"]["skim"], cut)
        self.assertGreaterEqual(c.gold["sultanate"], z + cut - 1)   # (no upkeep is paid on north's turn)

    def test_league_redeals_and_buys_off_curses(self):
        c = Campaign("league", seed=3)
        r = c.realms["league"]
        c.gold["league"] = 500
        n0 = len(r.hand)
        self.assertTrue(c.redeal("league"))
        self.assertEqual(c.gold["league"], 400)
        self.assertFalse(c.can_redeal("league")[0])            # once a turn
        self.assertEqual(len(r.hand), n0)                      # as many new cards (a thin deck may bring some back)
        r.hand.append(c._inst("unrest", "curse"))
        n = len(r.hand)
        self.assertEqual(c.burn_curse("league"), CARDS["unrest"].name)
        self.assertEqual(c.gold["league"], 350)
        self.assertFalse(any(x.key == "unrest" for x in r.hand + r.draw + r.discard))
        self.assertEqual(len(r.hand), n)                       # a card in its place
        self.assertFalse(c.can_redeal("aldern")[0])

    def test_green_vow_binds_war_cards_for_a_turn(self):
        holder = next(o for o, cards in PERSONAL.items() if "green_vow" in cards)
        self.assertEqual(OFFICER[holder].faction, "sylvan")
        c = Campaign(None, seed=3)
        c.intercepts = lambda council: False
        c.realms["ashen"].course = "balance"
        EFFECTS["green_vow"](c, "sylvan", ["ashen"])
        r = c.realms["ashen"]
        vow = next(x for x in r.draw if x.key == "forest_vow")
        r.draw.remove(vow)
        r.draw.append(vow)                                      # drawn next
        c.draw_cards("ashen", 1)
        self.assertIn("sylvan", c.vows["ashen"])
        self.assertFalse(any(x.key == "forest_vow" for x in r.hand + r.draw + r.discard))   # it burnt
        targets = options(c, "ashen", "assault", [])
        self.assertFalse(any(c.owner[t] == "sylvan" for t in targets))
        c.current = c.order.index("ashen")
        c.end_turn()
        self.assertNotIn("ashen", c.vows)


class CityFeatsTest(unittest.TestCase):
    def test_cities_with_features(self):
        from game.buildings import slots
        from game.factions import CITY_FEATS
        from game.units import ROSTER
        self.assertEqual(len(CITY_FEATS), 7)
        self.assertEqual(sum(1 for k, _, _ in CITY_FEATS.values() if k == "slot"), 2)
        self.assertEqual(slots("valmarra"), 4)
        self.assertEqual(slots("ashford"), 2)
        c = Campaign(None, seed=3)
        key = c._pool("steppecamp")[0]
        self.assertEqual(c.hire_price("steppecamp", key), int(round(ROSTER[key].cost * 0.8)))
        from game.population import outbreak
        outbreak(c, "sylvan", "worldroots")
        self.assertNotIn("worldroots", c.sick)
        hall = [o for o in c.officers_of("north") if not c.is_leader(o.key)][:1]
        if hall:
            c.officer_city[hall[0].key] = "hjoldgard"
            c.loyalty[hall[0].key] = 40
            c._city_feats("north")
            self.assertEqual(c.loyalty[hall[0].key], 42)
            c.loyalty[hall[0].key] = 70
            c._city_feats("north")
            self.assertEqual(c.loyalty[hall[0].key], 70)       # the loyal need no mead

    def test_tombs_raise_skeletons_for_the_defenders(self):
        c = Campaign(None, seed=3)
        att = [o.key for o in c.officers_of("sylvan") if c.squads[o.key]][:3]
        b = Battle("sylvan", c.owner["kingbarrow"], "kingbarrow", att, [o.key for o in c.officers_in("kingbarrow")])
        c._forces(b)
        self.assertTrue(b.tombs)
        w = headless_campaign_world(b)
        while w.time < 21 and w.winner is None:
            w.step(1 / 60)
        risen = [u for u in w.units if u.team == 1 and u.key == "skeleton" and not u.tag]
        self.assertGreaterEqual(len(risen), 2 if w.winner is None else 1)

class RearTest(unittest.TestCase):
    def test_rear_chances(self):
        from game import reign
        from game.campaign_ai import rear_chance
        c = Campaign(None, seed=3)
        offs = [o.key for o in c.officers_of("aldern") if not c.is_leader(o.key)]
        a, b = offs[0], offs[1]
        city = c.cities_of("aldern")[0]
        c.squads[a], c.squads[b] = [], list(c.squads[b]) or [c._new("knight")] * 5
        c.ostats[a][0] = c.ostats[b][0] = 15
        self.assertGreater(rear_chance(c, "aldern", a, "tax", city), rear_chance(c, "aldern", b, "tax", city))
        c.ostats[b] = list(c.ostats[b]); c.ostats[b][0] = 20
        c.squads[b] = []
        self.assertGreater(rear_chance(c, "aldern", b, "tax", city), rear_chance(c, "aldern", a, "tax", city))
        c.loyalty[a], c.loyalty[b] = 30, 80
        self.assertGreater(rear_chance(c, "aldern", a, "morale", city), rear_chance(c, "aldern", b, "morale", city))
        p = rear_chance(c, "aldern", a, "order", city)
        orig = reign.has
        reign.has = lambda camp, f, t: t == "fist" or orig(camp, f, t)
        try:
            self.assertAlmostEqual(rear_chance(c, "aldern", a, "order", city), p / 2)
        finally:
            reign.has = orig

    def test_tax_shown_is_tax_paid(self):
        from game.buildings import BUILDINGS
        c = Campaign("aldern", seed=3)
        city = c.cities_of("aldern")[0]
        c.buildings[city] = ["market"]
        shown = c.tax_yield(city, "aldern")
        g = c.gold["aldern"]
        EFFECTS["tax"](c, "aldern", [city])
        self.assertEqual(c.gold["aldern"] - g, shown)

    def test_squads_fight_in_separate_strips_and_are_named(self):
        from game.match import squad_names
        from game.sim import FIELD, TALL_TOP
        c = Campaign(None, seed=3)
        f = next(f for f in ("north", "aldern", "highland") if len([o for o in c.officers_of(f) if c.squads[o.key]]) >= 3)
        att = [o.key for o in c.officers_of(f) if c.squads[o.key]][:3]
        tgt = next(x for x in c.owner if c.owner[x] not in (f, "goblin") and c.officers_in(x))
        b = Battle(f, c.owner[tgt], tgt, att, [o.key for o in c.officers_in(tgt)])
        c._forces(b)
        w = headless_campaign_world(b)
        self.assertEqual(w.y0, TALL_TOP)                          # a taller field for strips
        strips = sorted({u.strip for u in w.units if u.team == 0})
        self.assertEqual(len(strips), 3)
        for (a0, a1), (b0, b1) in zip(strips, strips[1:]):
            self.assertGreaterEqual(b0 - a1, 20)                  # bare ground between the squads
        names = squad_names(b)[0]
        self.assertEqual(sorted(names), [0, 1, 2])
        self.assertTrue(all(OFFICER[o].name in " ".join(names.values()) for o in att))
        self.assertTrue(all(u.band in names for u in w.units if u.team == 0))
        quick = headless_campaign_world(Battle(f, c.owner[tgt], tgt, att[:1], []))
        self.assertEqual(quick.y0, FIELD[1])                     # one squad a side: the usual field

    def test_ai_gives_strong_men_to_great_captains(self):
        from game.campaign_ai import staff, _hire_pick
        c = Campaign(None, seed=3)
        city = c.cities_of("aldern")[0]
        offs = c.officers_in(city)
        big, small = offs[0].key, offs[1].key
        for o in offs:
            c.squads[o.key] = []
        c.olead[big], c.olead[small] = 900, 300
        for o in offs[2:]:
            c.officer_city[o.key] = c.cities_of("aldern")[1]
        c.free[city] = [c._new("militia") for _ in range(3)] + [c._new("paladin"), c._new("uhlan")]
        staff(c, city)
        self.assertEqual({t.key for t in c.squads[big]}, {"paladin", "uhlan"})   # the strong to the great
        self.assertTrue(all(t.key == "militia" for t in c.squads[small]))
        # a full squad of cheap men trades its weakest for a strong recruit standing in the city
        c.officer_city[small] = c.cities_of("aldern")[1]           # (no one else here to lead him)
        c.squads[big] = [c._new("militia") for _ in range(7)]
        c.free[city] = [c._new("paladin")]
        staff(c, city)
        self.assertIn("paladin", [t.key for t in c.squads[big]])
        self.assertEqual(len(c.squads[big]), 7)
        # hiring: worth per place, not the cheapest crowd
        c.squads[big] = [c._new("paladin") for _ in range(5)]
        self.assertEqual(_hire_pick(c, "aldern", big, city, ["militia", "knight"], False), "knight")
        self.assertIsNone(_hire_pick(c, "aldern", big, city, ["militia"], False))   # save for a worthy one
        self.assertEqual(_hire_pick(c, "aldern", big, city, ["militia"], True), "militia")   # unless in danger


if __name__ == "__main__":
    unittest.main()
