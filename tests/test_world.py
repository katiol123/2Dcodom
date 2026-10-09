import unittest

from game import diplomacy as dip
from game import events
from game.campaign import Campaign
from game.factions import neighbors


def _pair(a, b):
    return frozenset((a, b))


class DiplomacyTest(unittest.TestCase):
    def setUp(self):
        self.c = Campaign("aldern", seed=2)
        self.c.no_events = True

    def test_tiers_cover_every_value(self):
        names = [dip.tier(v)[0] for v in range(1, 101)]
        self.assertEqual(names[0], "feud")
        self.assertEqual(names[-1], "brother")
        self.assertEqual(len(set(names)), 5)
        self.assertEqual(set(dip.TIER_EFFECTS), set(names))

    def test_evaluate_gives_reasons_and_relations_matter(self):
        c = self.c
        c.rel[_pair("aldern", "league")] = 80
        good, why = dip.evaluate(c, "aldern", "league", "truce")
        self.assertTrue(why and all(isinstance(v, int) for _, v in why))
        self.assertEqual(good, sum(v for _, v in why))
        c.rel[_pair("aldern", "league")] = 20
        bad, _ = dip.evaluate(c, "aldern", "league", "truce")
        self.assertGreater(good, bad)
        c.betrayals["aldern"] = 2                                    # broken treaties are remembered
        worse, why = dip.evaluate(c, "aldern", "league", "truce")
        self.assertLess(worse, bad)
        self.assertIn("ВЫ НАРУШАЛИ ДОГОВОРЫ", [t for t, _ in why])

    def test_feud_closes_the_door(self):
        c = self.c
        c.rel[_pair("aldern", "ashen")] = 5
        for kind in ("truce", "alliance", "trade"):
            self.assertFalse(dip.can_propose(c, "aldern", "ashen", kind)[0])
        self.assertFalse(dip.can_propose(c, "aldern", "goblin", "truce")[0])

    def test_truce_alliance_and_betrayal(self):
        c = self.c
        c.rel[_pair("aldern", "highland")] = 95
        ok, msg = dip.propose(c, "aldern", "highland", "truce", bonus=100)
        self.assertTrue(ok, msg)
        self.assertTrue(c.at_peace("aldern", "highland"))
        self.assertFalse(dip.can_propose(c, "aldern", "highland", "truce")[0])   # once a turn, and already
        c.turn += 1
        ok, msg = dip.propose(c, "aldern", "highland", "alliance", bonus=100)
        self.assertTrue(ok, msg)
        self.assertEqual(dip.status(c, "aldern", "highland"), "alliance")
        self.assertIn("highland", dip.allies(c, "aldern"))
        before = c.relation("aldern", "highland")
        dip.declare_war(c, "aldern", "highland")
        self.assertEqual(dip.status(c, "aldern", "highland"), "war")
        self.assertEqual(c.betrayals["aldern"], 1)
        self.assertLessEqual(c.relation("aldern", "highland"), before - 25)

    def test_player_answers_proposals(self):
        c = self.c
        c.rel[_pair("aldern", "league")] = 90
        asked = []
        c.diplo_hook = lambda camp, frm, to, kind, reasons: asked.append(kind) or False
        ok, _ = dip.propose(c, "league", "aldern", "truce", bonus=100)
        self.assertFalse(ok)                                         # the player said no
        self.assertEqual(asked, ["truce"])
        self.assertFalse(c.at_peace("aldern", "league"))

    def test_allies_help_in_storms(self):
        c = self.c
        target, enemy, ally = next((x, c.owner[x], c.owner[n]) for x in c.owner for n in neighbors(x)
                                   if c.owner[x] not in ("aldern", "goblin")
                                   and c.owner[n] not in ("aldern", "goblin", c.owner[x])
                                   and c.officers_in(n))
        self.assertEqual(dip.ally_help(c, "aldern", target, enemy)[0], 0)
        c.alliance[_pair("aldern", ally)] = [10, None]
        power, who = dip.ally_help(c, "aldern", target, enemy)
        self.assertGreater(power, 0)
        self.assertEqual(who, [ally])

    def test_feud_fights_harder_both_ways(self):
        c = self.c
        city = c.cities_of("ashen")[0]
        offs = [o.key for o in c.officers_of("aldern")[:2]]
        c.rel[_pair("aldern", "ashen")] = 50
        a = c.attack_power("aldern", offs, city)
        c.rel[_pair("aldern", "ashen")] = 5
        self.assertAlmostEqual(c.attack_power("aldern", offs, city), a * 1.15)

    def test_friends_trade_and_hegemon_is_feared(self):
        c = self.c
        c.rel[_pair("aldern", "highland")] = 90
        c.truce[_pair("aldern", "highland")] = 5
        gold = c.gold["aldern"]
        dip.round_tick(c)
        self.assertGreater(c.gold["aldern"], gold)                   # brotherhood: trade every round
        for city in c.cities_of("sylvan") + c.cities_of("league"):    # make the North huge
            c.owner[city] = "north"
        self.assertEqual(dip.hegemon(c), "north")
        rel = c.relation("north", "aldern")
        dip.round_tick(c)
        self.assertLess(c.relation("north", "aldern"), rel + 1)

    def test_hostile_border_grows_slower(self):
        c = self.c
        city = next(x for x in c.cities_of("aldern")
                    if any(c.owner[n] not in ("aldern", "goblin") for n in neighbors(x)))
        other = next(c.owner[n] for n in neighbors(city) if c.owner[n] not in ("aldern", "goblin"))
        c.rel[_pair("aldern", other)] = 20
        self.assertTrue(dip.growth_blocked(c, city))
        c.truce[_pair("aldern", other)] = 3
        self.assertFalse(dip.growth_blocked(c, city))

    def test_ai_campaign_with_diplomacy_runs(self):
        c = Campaign(None, seed=7)
        while c.turn <= 14:
            c.run_ai(stop_at_player=False, max_turns=1)
        self.assertTrue(sum(c.stats["diplomacy"].values()) > 0)
        for p in c.alliance:
            self.assertNotIn("goblin", p)


class EventsTest(unittest.TestCase):
    def test_every_event_fires_and_changes_the_world(self):
        for e in events.EVENTS:
            c = Campaign(None, seed=3)
            for _ in range(10):
                c.run_ai(stop_at_player=False, max_turns=1)
            before = (dict(c.owner), dict(c.prosperity), {f: c.gold[f] for f in c.order}, dict(c.rel),
                      dict(c.loyalty), {k: len(v) for k, v in c.free.items()}, dict(c.active))
            line = events.fire(c, e.key)
            after = (dict(c.owner), dict(c.prosperity), {f: c.gold[f] for f in c.order}, dict(c.rel),
                     dict(c.loyalty), {k: len(v) for k, v in c.free.items()}, dict(c.active))
            self.assertNotEqual(before, after, e.key)
            self.assertIn(e.name, line)
            self.assertEqual(c.world_events[-1][1], e.key)

    def test_timed_events_change_the_rules(self):
        c = Campaign(None, seed=3)
        city = c.cities_of("aldern")[0]
        up, inc = c.upkeep("aldern"), c.income_of(city, "aldern")
        events.fire(c, "frost")
        self.assertGreater(len(c.frost_wide), len(c.owner) / 2)                   # more than half the world
        self.assertGreater(c.upkeep("aldern"), up)
        self.assertEqual(c.upkeep("north"), Campaign(None, seed=3).upkeep("north"))   # used to the cold
        c.active = {"drought": 2}
        self.assertEqual(c.income_of(city, "aldern"), inc * 2 // 5)
        for _ in range(4):
            events.round_tick(c)
        self.assertNotIn("drought", c.active)                        # it passes

    def test_events_are_rare(self):
        c = Campaign(None, seed=1)
        fired = 0
        for t in range(1, 41):
            c.turn = t
            n = len(c.world_events)
            events.round_tick(c)
            fired += len(c.world_events) - n
        self.assertLessEqual(fired, 5)
        self.assertTrue(all(t >= events.FIRST_ROUND for t, _, _ in c.world_events))
        turns = [t for t, _, _ in c.world_events]
        self.assertTrue(all(b - a >= events.GAP for a, b in zip(turns, turns[1:])))


class FrostTest(unittest.TestCase):
    def test_the_frozen_north(self):
        from game.campaign import Battle, FROST_PACE, FROST_UPKEEP
        from game.campaign_ai import frost_reluctance
        from game.factions import CITY, FROST_CITIES
        from game.match import headless_campaign_world
        c = Campaign(None, seed=3)
        self.assertTrue(set(c.cities_of("north")) <= FROST_CITIES)
        self.assertTrue(any(CITY[x].faction not in ("north", "goblin") for x in FROST_CITIES))   # others freeze too
        frozen = next(x for x in FROST_CITIES if c.owner[x] == "aldern")
        warm = next(x for x in c.cities_of("aldern") if x not in FROST_CITIES)
        self.assertAlmostEqual(c.troop_upkeep("aldern", "knight", frozen),
                               c.troop_upkeep("aldern", "knight", warm) * FROST_UPKEEP)
        self.assertEqual(c.troop_upkeep("north", "knight", frozen), c.troop_upkeep("north", "knight", warm))
        att = [o.key for o in c.officers_of("north") if c.squads[o.key]][:2]
        b = Battle("north", "aldern", frozen, att, [o.key for o in c.officers_in(frozen)])
        c._forces(b)
        self.assertTrue(b.frost)
        self.assertEqual(b.chill, (1.0, FROST_PACE))                    # only the southerners shiver
        w = headless_campaign_world(b)
        knights = [u for u in w.units if u.team == 1]
        self.assertTrue(knights and all(u.chill == FROST_PACE for u in knights))
        u = knights[0]
        self.assertAlmostEqual(u.speed(), u.type.speed * FROST_PACE)
        self.assertAlmostEqual(u.cooldown(), u.type.cooldown / FROST_PACE)
        north_city = c.cities_of("north")[0]
        c.gold["aldern"] = 0
        self.assertLess(frost_reluctance(c, "aldern", north_city), 0.85)  # a poor realm keeps away
        self.assertEqual(frost_reluctance(c, "north", frozen), 1.0)


if __name__ == "__main__":
    unittest.main()
