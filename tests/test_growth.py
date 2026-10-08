import unittest

from game import growth
from game.campaign import Battle, Campaign
from game.cards import CARDS, FEATS, THRESHOLDS, muster_turns
from game.faces import presence
from game.factions import CITY, FACTION
from game.officers import OFFICER, OFFICERS, STATS


class GrowthTest(unittest.TestCase):
    def setUp(self):
        self.c = Campaign("aldern", seed=3)

    def _weak_and_strong(self, f="aldern"):
        offs = sorted((o for o in OFFICERS[f] if o.rank), key=presence)
        return offs[0].key, offs[-1].key

    def test_weak_officers_learn_faster(self):
        weak, strong = self._weak_and_strong()
        self.assertGreater(growth.learn_rate(self.c, weak), 3 * growth.learn_rate(self.c, strong))
        for o in (weak, strong):
            growth.gain_xp(self.c, o, 400)
        self.assertGreater(self.c.level[weak], self.c.level[strong])
        self.assertGreater(sum(self.c.ostats[weak]) + self.c.olead[weak] / 20,
                           sum(OFFICER[weak].stats) + OFFICER[weak].leadership / 20)

    def test_level_up_raises_a_stat_or_leadership(self):
        o = self._weak_and_strong()[0]
        before, lvl = (sum(self.c.ostats[o]), self.c.olead[o]), self.c.level[o]
        growth.level_up(self.c, o)
        after = sum(self.c.ostats[o]), self.c.olead[o]
        self.assertEqual(self.c.level[o], lvl + 1)
        self.assertTrue(after[0] == before[0] + 1 or after[1] == before[1] + growth.LEAD_STEP)
        self.assertTrue(all(v <= 20 for v in self.c.ostats[o]))

    def test_degrade_and_council_sees_current_stats(self):
        r = self.c.realms["aldern"]
        o = r.council[1]
        totals = self.c.totals(r.council)
        growth.degrade(self.c, o, "тяжело ранен")
        self.assertEqual(sum(self.c.totals(r.council).values()), sum(totals.values()) - 1)
        self.assertEqual(sum(self.c.ostats[o]), sum(OFFICER[o].stats) - 1)

    def test_feat_once_per_campaign(self):
        self.assertEqual(set(FEATS), {k for k, c in CARDS.items() if c.tier == "feat"})
        r = self.c.realms["aldern"]
        o = r.council[1]
        growth.award(self.c, o, "ford_hero")
        growth.award(self.c, r.council[2], "ford_hero")            # a second hero gets nothing
        self.assertEqual(self.c.feats["ford_hero"], o)
        self.assertIn("ford_hero", self.c.personal(o))
        self.assertNotIn("ford_hero", self.c.personal(r.council[2]))
        self.assertEqual(sum(1 for x in r.all_cards() if x.key == "ford_hero"), 1)

    def test_ford_hero_for_holding_against_the_odds(self):
        c = self.c
        city = FACTION["sylvan"].capital
        d = c.officers_in(city)[0].key
        b = Battle("aldern", "sylvan", city, [c.officers_of("aldern")[1].key], [d], a=300, d=100, p=0.9,
                   att_won=False)
        growth.on_battle(c, b)
        self.assertEqual(c.feats.get("ford_hero"), d)

    def test_used_cards_raise_loyalty_ignored_lower_it(self):
        c = self.c
        r = c.realms["aldern"]
        o = r.council[1]
        c.loyalty[o] = 50
        inst = c._inst(c.personal(o)[0], o) if c.personal(o) else c._inst("tax", o)
        growth.on_card_used(c, "aldern", inst)
        self.assertEqual(c.loyalty[o], 52)
        c.last_used[o] = c.turn - 10                                   # ignored for ten turns
        growth.turn(c, "aldern")
        self.assertLess(c.loyalty[o], 52)

    def test_disloyal_officer_leaves_for_the_best_neighbour(self):
        c = self.c
        o = c.officers_of("aldern")[3].key
        new = growth.desert(c, o)
        self.assertIsNotNone(new)
        self.assertNotIn(new, ("aldern", "goblin"))
        self.assertEqual(c.allegiance[o], new)
        self.assertEqual(c.stats["deserted_officers"]["aldern"], 1)

    def test_devoted_adviser_cards_cost_less(self):
        c = self.c
        r = c.realms["aldern"]
        o = next(x for x in r.council[1:] if any(CARDS[k].cost for k in c.personal(x)))
        k = next(k for k in c.personal(o) if CARDS[k].cost)
        inst = c._inst(k, o)
        c.loyalty[o] = 99
        self.assertEqual(c.card_cost("aldern", inst), CARDS[k].cost)
        c.loyalty[o] = 100
        self.assertTrue(c.devoted(o))
        self.assertEqual(c.card_cost("aldern", inst), CARDS[k].cost - 1)

    def test_lost_capital_shakes_loyalty(self):
        c = self.c
        o = c.officers_of("sylvan")[2].key
        before = c.loyalty[o]
        growth.on_city_lost(c, "sylvan", FACTION["sylvan"].capital)
        self.assertEqual(c.loyalty[o], max(0, before - 8))

    def test_muster_opens_hiring_longer_with_recruiters(self):
        c = self.c
        weak = [o.key for o in OFFICERS["aldern"][:1]]
        self.assertEqual(muster_turns(weak), 1)
        strong = {o: [20] * len(STATS) for o in ("a", "b", "c", "d", "e")}
        self.assertEqual(muster_turns(list(strong), strong), 3)
        self.assertLessEqual(THRESHOLDS[1], 100)
        city = "kronholm"
        key = CITY[city].pool[0]
        self.assertFalse(c.can_hire(city, key)[0])
        inst = c._inst("muster", "base")
        c.realms["aldern"].hand.append(inst)
        self.assertTrue(c.play("aldern", inst, [city])[0])
        self.assertTrue(c.can_hire(city, key)[0])
        for _ in range(3):                                              # it closes again
            c._start_turn("aldern")
        self.assertFalse(c.can_hire(city, key)[0])


if __name__ == "__main__":
    unittest.main()
