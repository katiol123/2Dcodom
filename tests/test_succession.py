import unittest

from game import succession
from game.campaign import Campaign
from game.cards import CARDS, FACTION_CARD
from game.officers import OFFICERS


class SuccessionTest(unittest.TestCase):
    def setUp(self):
        self.c = Campaign("aldern", seed=5)
        self.c.no_events = True

    def keys(self, f, origin):
        return [x.key for x in self.c.realms[f].all_cards() if x.origin == origin]

    def test_ruler_never_changes_sides(self):
        c = self.c
        ruler = c.leader["sylvan"]
        c.defect(ruler, "aldern")
        self.assertEqual(c.allegiance[ruler], "sylvan")
        c.change_loyalty(ruler, -90)
        self.assertEqual(c.loyalty[ruler], 100)

    def test_death_heir_legacy_and_unrest(self):
        c, f = self.c, "sylvan"
        r = c.realms[f]
        first = c.leader[f]
        self.assertEqual(self.keys(f, "faction"), [FACTION_CARD[f]])
        loyal = {o.key: c.loyalty[o.key] for o in c.officers_of(f)}
        expected = succession.contenders(c, f)[0]
        succession.die(c, first, "пала в бою")
        heir = c.leader[f]
        self.assertEqual(heir, expected)
        self.assertEqual(r.council.count(heir), 1)                       # moved to the ruler's seat
        self.assertEqual(c.loyalty[heir], 100)
        self.assertFalse(c.devoted(heir))                                # no bonus for a ruler's loyalty
        self.assertNotEqual(heir, first)
        self.assertIn(first, c.dead)
        self.assertNotIn(first, [o.key for o in c.officers_of(f)])
        self.assertEqual(r.council[0], heir)
        self.assertEqual(self.keys(f, "faction"), [])                    # the faction card lives on as legacy
        self.assertEqual(self.keys(f, "legacy"), [FACTION_CARD[f]])
        self.assertEqual(sorted(self.keys(f, heir)), sorted(c.personal(heir)))   # his own cards: the ruler's
        self.assertEqual(r.unrest, succession.UNREST_TURNS)
        self.assertTrue(all(c.loyalty[o] < loyal[o] for o in loyal if o not in (heir, first) and loyal[o] > 0))
        self.assertTrue(any(x.key == "unrest" for x in r.all_cards()))
        self.assertTrue(c.can_set_council(f, r.council)[0])
        self.assertFalse(c.can_set_council(f, r.council[1:])[0])          # the new ruler keeps his seat
        # the next death: only the latest ruler's legacy stays
        succession.die(c, heir, "скончался")
        third = c.leader[f]
        self.assertNotIn(FACTION_CARD[f], [x.key for x in r.all_cards()])
        self.assertEqual(sorted(self.keys(f, "legacy")),
                         sorted(k for k in c.personal(heir) if CARDS[k].tier != "vice"))
        self.assertNotEqual(third, heir)

    def test_merit_decides_the_heir(self):
        c, f = self.c, "aldern"
        outsider = [o.key for o in c.officers_of(f) if o.key not in c.realms[f].council][-1]
        self.assertNotEqual(succession.contenders(c, f)[0], outsider)
        c.claim[outsider] = 500                                          # years of service and victories
        self.assertEqual(succession.contenders(c, f)[0], outsider)
        succession.die(c, c.leader[f], "пал в бою")
        self.assertEqual(c.leader[f], outsider)
        self.assertEqual(c.realms[f].council[0], outsider)
        self.assertTrue(set(c.personal(outsider)) <= {x.key for x in c.realms[f].all_cards()})

    def test_unrest_costs_action_points(self):
        c, f = self.c, "aldern"
        succession.die(c, c.leader[f], "пал в бою")
        r = c.realms[f]
        r.ap = 5
        succession.turn(c, f)
        self.assertEqual(r.ap, 4)
        self.assertEqual(r.unrest, succession.UNREST_TURNS - 1)
        self.assertGreater(r.course_cd, 0)                              # the course is locked

    def test_rulers_die_in_campaigns(self):
        c = Campaign(None, seed=9)
        while c.turn <= 30:
            c.run_ai(stop_at_player=False, max_turns=1)
        for f, r in c.realms.items():
            lead = c.leader.get(f)
            if r.alive and lead:
                self.assertIn(lead, r.council)
                self.assertNotIn(lead, c.dead)
                self.assertEqual(c.allegiance[lead], f)
        self.assertEqual(OFFICERS["aldern"][0].rank, 0)


if __name__ == "__main__":
    unittest.main()
