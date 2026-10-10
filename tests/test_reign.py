import unittest

from game import reign
from game.campaign import Campaign
from game.campaign_ai import _attack_plan
from game.factions import neighbors
from game.officers import OFFICER


class ReignTest(unittest.TestCase):
    def test_thirty_three_traits_all_used(self):
        self.assertEqual(len(reign.TRAITS), 37)
        used = {t for _, traits in reign.REIGNS.values() for t in traits}
        self.assertEqual(used, set(reign.TRAITS))
        for name, desc in reign.TRAITS.values():
            self.assertTrue(name and desc)
        for o in OFFICER:
            self.assertIn(reign.reign_of(o), reign.REIGNS)

    def test_every_reign_type_is_met(self):
        from collections import Counter
        from game.officers import OFFICERS
        n = Counter(reign.reign_of(o.key) for offs in OFFICERS.values() for o in offs)
        for kind in reign.REIGNS:
            self.assertGreaterEqual(n[kind], reign.MIN_HOLDERS, kind)

    def test_shown_only_for_computer_rulers(self):
        c = Campaign("aldern", seed=1)
        c.seat_councils()
        self.assertFalse(reign.shown(c, c.leader["aldern"]))             # the player rules himself
        self.assertTrue(reign.shown(c, c.leader["ashen"]))
        adviser = c.realms["ashen"].council[1]
        self.assertFalse(reign.shown(c, adviser))                        # hidden until he rules
        self.assertEqual(reign.ruler_traits(c, "aldern"), ())
        self.assertIn("cruel", reign.ruler_traits(c, "ashen"))           # the necromancer duke: a tyrant

    def test_traits_change_decisions(self):
        c = Campaign(None, seed=1)
        from game.cards import CARDS
        self.assertGreater(reign.card_mult(c, "khanate", CARDS["assault"]), 0)
        self.assertEqual(reign.min_odds(c, "sultanate"), 0.65)           # a sage: cautious
        self.assertEqual(reign.min_odds(c, "highland"), 0.45)            # an avenger: reckless
        self.assertGreater(reign.leader_odds(c, "sylvan"), 1.0)         # a keeper never rides out herself
        self.assertEqual(reign.leader_odds(c, "aldern"), 0.65)           # a noble rides in front
        self.assertGreater(reign.card_mult(c, "ashen", CARDS["assault"]), 1.0)   # aggressive
        self.assertGreater(reign.course_bias(c, "league").get("economy", 0), 0)

    def _lone_ruler(self, f):
        """The ruler alone next to an enemy city: no one else could storm it."""
        c = Campaign(None, seed=2)
        c.no_events = True
        ruler = c.leader[f]
        home = next(x for x in c.cities_of(f) if any(c.owner[n] != f for n in neighbors(x)))
        c.officer_city[ruler] = home
        target = next(n for n in neighbors(home) if c.owner[n] != f)
        for o in c.officers_of(f):
            if o.key != ruler:
                c.officer_city[o.key] = next(x for x in c.cities_of(f) if x != home) \
                    if len(c.cities_of(f)) > 1 else home
                c.ready.discard(o.key)
        c.ready.add(ruler)
        return c, ruler, target

    def test_ai_spares_its_ruler(self):
        c, ruler, target = self._lone_ruler("sylvan")             # a keeper: never, unless desperate
        c.win_chance = lambda a, d: 0.85
        v, plan = _attack_plan(c, "sylvan", "assault")
        self.assertFalse(plan and ruler in plan[1])
        c.win_chance = lambda a, d: 0.99
        v, plan = _attack_plan(c, "sylvan", "assault")
        self.assertFalse(plan and ruler in plan[1])               # not even at 99%: she stays home
        c, ruler, target = self._lone_ruler("aldern")             # a brave noble: from 65%
        c.win_chance = lambda a, d: 0.7
        v, plan = _attack_plan(c, "aldern", "assault")
        self.assertTrue(plan and ruler in plan[1])

    def test_desperate_ruler_fights(self):
        c, ruler, target = self._lone_ruler("sylvan")
        for city in c.cities_of("sylvan")[2:]:                   # down to the last two cities
            c.owner[city] = "ashen"
        c.win_chance = lambda a, d: 0.6
        v, plan = _attack_plan(c, "sylvan", "assault")
        self.assertTrue(plan and ruler in plan[1])

    def test_tyrant_executes_prisoners(self):
        c = Campaign(None, seed=4)
        fates = [reign.prisoner_fate(c, "ashen") for _ in range(200)]
        self.assertGreater(fates.count("execute"), 100)
        self.assertEqual(reign.prisoner_fate(c, "aldern"), "release")   # merciful noble

    def test_new_and_sharpened_traits(self):
        from game.campaign_ai import best_play, staff
        from game.diplomacy import betrayal, envoy_ease, evaluate, hegemon
        c = Campaign(None, seed=1)
        c.seat_councils()
        orig = reign.ruler_traits
        try:
            reign.ruler_traits = lambda camp, f: ("vengeful",) if f == "khanate" else ()
            c.last_attack[("sultanate", "khanate")] = c.turn
            self.assertTrue(reign.offender(c, "khanate", "sultanate"))
            self.assertGreater(reign.odds_relief(c, "khanate", "sultanate"), 0)
            self.assertIn("ИХ ПРАВИТЕЛЬ ЖАЖДЕТ МЕСТИ", [t for t, _ in evaluate(c, "sultanate", "khanate", "truce")[1]])
            reign.ruler_traits = lambda camp, f: ("diplomat", "trader") if f == "khanate" else ()
            self.assertLess(envoy_ease(c, "khanate", "truce"), 1)
            self.assertLess(envoy_ease(c, "khanate", "trade"), 1)
            reign.ruler_traits = lambda camp, f: ("careful_self",) if f == "khanate" else ()
            ruler = c.leader["khanate"]
            self.assertTrue(reign.homebody(c, "khanate", ruler))
            city = c.officer_city[ruler]
            c.squads[ruler] = []
            c.free[city] = [c._new("knight"), c._new("militia")]
            staff(c, city)
            self.assertIn("knight", [t.key for t in c.squads[ruler]])      # the best man guards the ruler
            reign.ruler_traits = lambda camp, f: ("honorable",) if f == "khanate" else ()
            from game.cards import CARDS
            spy = next(k for k, cd in CARDS.items() if cd.kind == "intrigue" and k not in reign.GUARD_CARDS)
            self.assertLess(reign.card_mult(c, "khanate", CARDS[spy]), 0.2)
            reign.ruler_traits = lambda camp, f: ("attentive",) if f == "khanate" else ()
            adviser = c.realms["khanate"].council[1] if len(c.realms["khanate"].council) > 1 else None
            c.loyalty[adviser] = 20
            inst = c._inst(c.personal(adviser)[0], adviser)
            self.assertGreater(reign.coaxing(c, "khanate", inst), 1.5)   # a sulking adviser's card first
            reign.ruler_traits = lambda camp, f: ("admirer",) if f == "khanate" else ()
            h = hegemon(c)
            if h and h != "khanate":
                self.assertTrue(reign.admires(c, "khanate", h))
                self.assertLess(reign.hostility(c, "khanate", h), 1.0)
        finally:
            reign.ruler_traits = orig


if __name__ == "__main__":
    unittest.main()
