import os
import unittest
from collections import Counter

from game.campaign import Campaign
from game.cardplay import EFFECTS, MULTI, options
from game.cards import (AP, BASE_SET, CARDS, COUNCIL_SEATS, FACTION_CARD, PERSONAL, THRESHOLD_CARDS, THRESHOLDS,
                        UNIQUE_HOLDER, UNIQUES, competence, council_totals, deck_for, hand_size, reserve,
                        threshold_cards)
from game.factions import ALL_FACTIONS, CITY, PROSPERITY, neighbors
from game.officers import OFFICER, OFFICERS, STATS


class CardDataTest(unittest.TestCase):
    def test_catalogue(self):
        for key, c in CARDS.items():
            self.assertTrue(c.name and c.text, key)
            self.assertTrue(0 <= c.cost <= 3, key)
            if not c.unplayable and not (c.on_draw and c.tier == "curse" and key != "debt"):
                self.assertIn(key, EFFECTS, key)
            self.assertFalse(" - " in c.name, key)
        tiers = Counter(c.tier for c in CARDS.values())
        for t in ("basic", "junk", "moderate", "strong", "unique", "faction", "curse"):
            self.assertGreater(tiers[t], 0, t)
        self.assertEqual(set(PROSPERITY), set(CITY))
        self.assertTrue(all(1 <= v <= 10 for v in PROSPERITY.values()))

    def test_faction_and_threshold_cards(self):
        self.assertEqual(set(FACTION_CARD), {f.key for f in ALL_FACTIONS})
        self.assertEqual(len(set(FACTION_CARD.values())), len(FACTION_CARD))          # one of a kind each
        self.assertTrue(all(CARDS[k].tier == "faction" for k in FACTION_CARD.values()))
        self.assertEqual(set(THRESHOLD_CARDS), set(STATS))
        mids = [m for m, _ in THRESHOLD_CARDS.values()]
        tops = [t for _, t in THRESHOLD_CARDS.values()]
        self.assertTrue(all(CARDS[k].tier == "moderate" for k in mids))
        self.assertTrue(all(CARDS[k].tier == "strong" for k in tops))

    def test_deck_is_base_faction_council_thresholds(self):
        for f, offs in OFFICERS.items():
            council = [o.key for o in offs[:COUNCIL_SEATS]]
            deck = deck_for(f, council)
            expect = list(BASE_SET) + [FACTION_CARD[f]] + [k for o in council for k in PERSONAL[o]] + \
                threshold_cards(council)
            self.assertEqual(sorted(deck), sorted(expect))
            self.assertEqual(PERSONAL[offs[0].key], ())                 # the leader brings the faction card

    def test_thresholds_give_up_to_twelve_cards(self):
        totals = council_totals([o.key for o in OFFICERS["aldern"][:5]])
        n = sum((totals[s] >= THRESHOLDS[0]) + (totals[s] >= THRESHOLDS[1]) for s in STATS)
        self.assertEqual(n, competence([o.key for o in OFFICERS["aldern"][:5]]))
        self.assertLessEqual(THRESHOLDS[1], 20 * COUNCIL_SEATS)        # a council of 20s clears all 12
        self.assertEqual(sum(1 for s in STATS for _ in range(2)), 12)

    def test_uniques_and_dilemmas(self):
        from game.faces import presence
        held = Counter(k for cards in PERSONAL.values() for k in cards if CARDS[k].tier == "unique")
        uniques = [k for k, c in CARDS.items() if c.tier == "unique"]
        for k in uniques:
            self.assertEqual(held[k], 1, k)                              # exactly one copy in the world
            self.assertIn(k, PERSONAL[UNIQUE_HOLDER[k]])
        for f, cards in UNIQUES.items():
            offs = OFFICERS[f]
            median = sorted(presence(o) for o in offs[1:])[len(offs) // 2]
            weak = [UNIQUE_HOLDER[k] for k in cards if presence(OFFICER[UNIQUE_HOLDER[k]]) < median]
            self.assertGreaterEqual(len(weak), 2, f)                     # weak officers with unique cards
            best = sorted(offs[1:], key=presence, reverse=True)[:3]
            self.assertTrue(any(all(CARDS[k].tier in ("junk", "basic") for k in PERSONAL[o.key]) for o in best), f)


class CampaignCardsTest(unittest.TestCase):
    def setUp(self):
        self.c = Campaign("aldern", seed=3)

    def test_turn_start(self):
        c = self.c
        self.assertEqual(c.whose_turn(), "aldern")
        self.assertEqual(c.realms["aldern"].ap, AP)
        self.assertEqual(c.ap_max("khanate"), AP + 1)                   # the Horde's passive
        for f, r in c.realms.items():
            self.assertEqual(len(r.hand), hand_size(r.council), f)
            self.assertIn(OFFICERS[f][0].key, r.council)
            self.assertEqual(len(r.council), COUNCIL_SEATS)
            keys = Counter(x.key for x in r.all_cards())
            self.assertEqual(keys[FACTION_CARD[f]], 1)

    def _give(self, f, key):
        inst = self.c._inst(key, "base")
        self.c.realms[f].hand.append(inst)
        return inst

    def test_tax_and_overtaxing(self):
        c = self.c
        inst = self._give("aldern", "tax")
        gold = c.gold["aldern"]
        income = c.income_of("kronholm", "aldern")
        ok, _ = c.play("aldern", inst, ["kronholm"])
        self.assertTrue(ok)
        self.assertEqual(c.gold["aldern"], gold + income)
        self.assertEqual(c.realms["aldern"].ap, AP - 1)
        p = c.prosperity["kronholm"]
        c.turn += 1                                                     # the next turn, same city
        c.play("aldern", self._give("aldern", "tax"), ["kronholm"])
        self.assertEqual(c.prosperity["kronholm"], p - 1)
        self.assertFalse(c.play("aldern", self._give("aldern", "tax"), ["valmarra"])[0])   # not our city

    def test_ap_and_gold_limits(self):
        c = self.c
        c.realms["aldern"].ap = 1
        self.assertEqual(c.can_play("aldern", self._give("aldern", "assault"))[1], "НЕ ХВАТАЕТ ОД")
        c.realms["aldern"].ap = 5
        c.gold["aldern"] = 10
        self.assertEqual(c.can_play("aldern", self._give("aldern", "build"))[1], "НЕ ХВАТАЕТ ЗОЛОТА")

    def test_every_card_has_working_targets(self):
        c = self.c
        for key, card in CARDS.items():
            chosen = []
            for step in card.targets:
                opts = options(c, "aldern", key, chosen)
                if not opts:
                    break
                chosen.append(tuple(opts[:1]) if step in MULTI else opts[0])

    def test_curses(self):
        c = self.c
        c.realms["sylvan"].council = [OFFICERS["sylvan"][0].key]          # no spy-catchers
        n = len(c.realms["sylvan"].draw)
        self.assertTrue(c.play("aldern", self._give("aldern", "letters"), ["sylvan"])[0])
        self.assertEqual(len(c.realms["sylvan"].draw), n + 2)
        unrest = [x for x in c.realms["sylvan"].draw if x.key == "unrest"]
        self.assertTrue(all(CARDS[x.key].unplayable for x in unrest))
        for _ in range(3):                                              # they fade after 3 of its turns
            c._start_turn("sylvan")
        self.assertFalse(any(x.key == "unrest" for x in c.realms["sylvan"].all_cards()))
        # a fire goes off when drawn
        c.gold["sylvan"] = 400
        c.realms["sylvan"].draw.append(c._inst("fire", "curse"))
        c._draw("sylvan", 1)
        self.assertEqual(c.gold["sylvan"], 300)
        self.assertFalse(any(x.key == "fire" for x in c.realms["sylvan"].all_cards()))

    def test_council_change_rebuilds_deck(self):
        c = self.c
        r = c.realms["aldern"]
        gone = r.council[1]
        others = [o.key for o in c.officers_of("aldern") if o.key not in r.council]
        new = others[0]
        loy = c.loyalty[gone]
        self.assertFalse(c.set_council("aldern", r.council[1:]))           # the leader always sits
        self.assertTrue(c.set_council("aldern", [r.council[0], new] + r.council[2:]))
        origins = Counter(x.origin for x in r.all_cards())
        self.assertNotIn(gone, origins)
        self.assertEqual(origins[new], len(PERSONAL[new]))
        want = Counter(threshold_cards(r.council))
        have = Counter(x.key for x in r.all_cards() if x.origin == "threshold")
        self.assertEqual(want, have)
        self.assertLess(c.loyalty[gone], loy)

    def test_hand_reserve(self):
        c = self.c
        r = c.realms["aldern"]
        n = reserve(r.council)
        keep = [x.id for x in r.hand[:n]]
        r.keep = list(keep)
        c.end_turn()
        self.assertTrue(all(any(x.id == k for x in r.hand) for k in keep))
        self.assertEqual(c.whose_turn(), c.order[1])

    def test_storm(self):
        c = self.c
        target = "shroomhole"                                           # a goblin lair next to Hartwell
        self.assertIn("hartwell", neighbors(target))
        offs = [o.key for o in c.officers_in("hartwell")]
        for o in offs:
            c.squads[o] = [c._new("knight") for _ in range(6)]
            c.ready.add(o)
        inst = self._give("aldern", "assault")
        chosen = [target, tuple(offs[:3])]
        c.rng.seed(1)
        ok, msg = c.play("aldern", inst, chosen)
        self.assertTrue(ok, msg)
        self.assertEqual(c.owner[target], "aldern", msg)
        self.assertTrue(all(c.officer_city[o] == target for o in offs[:3]))
        self.assertTrue(all(o not in c.ready for o in offs[:3]))        # they acted this turn

    def test_ai_campaign_runs_and_stays_consistent(self):
        for seed in (1, 2):
            c = Campaign(None, seed=seed)
            c.run_ai(stop_at_player=False, max_turns=15)
            ids = Counter()
            for f, r in c.realms.items():
                self.assertGreaterEqual(c.gold[f], 0)
                ids.update(x.id for x in r.all_cards())
                if r.alive:
                    for o in c.officers_of(f):
                        self.assertEqual(c.owner[c.officer_city[o.key]], f, o.key)
            self.assertEqual(max(ids.values()), 1)                      # no card in two places
            self.assertGreater(sum(c.stats["played"].values()), 200)
        a, b = Campaign(None, seed=5), Campaign(None, seed=5)
        a.run_ai(stop_at_player=False, max_turns=6)
        b.run_ai(stop_at_player=False, max_turns=6)
        self.assertEqual(a.log, b.log)                                  # deterministic


class CardScreenTest(unittest.TestCase):
    def test_play_card_council_and_end_turn(self):
        os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
        os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
        import pygame
        from game.assets import ensure_unit_sheets
        from game.hires import HIRES
        from game.mapview import WorldMapScreen
        from game.render import Renderer
        from game.sim import H, W
        pygame.init()
        pygame.display.set_mode((W, H))
        HIRES.sync = True
        m = WorldMapScreen(Renderer(ensure_unit_sheets()), campaign=Campaign("aldern"))
        surf = pygame.Surface((W, H))

        def frame(pos):
            m.update(0.05, pos)
            m.draw(surf)

        def click(pos, button=1):
            frame(pos)
            m.handle(pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=pos, button=button), pos)
            frame(pos)
            m.handle(pygame.event.Event(pygame.MOUSEBUTTONUP, pos=pos, button=button), pos)

        hand = m.camp.realms["aldern"].hand
        hand.append(m.camp._inst("tax", "base"))
        i = len(hand) - 1
        frame((0, 0))
        r = m.table.hand_rects()[i]
        frame((r.right - 4, r.y + 5))                                   # hover raises the card
        r = m.table.hand_rects()[i]
        click((r.right - 4, r.y + 30))
        self.assertIsNotNone(m.table.play)
        c = CITY["kronholm"]
        m.cam = [c.x - W / 2, c.y - H / 2]
        m._clamp()
        sx, sy = m._to_screen(c.x, c.y)
        gold = m.camp.gold["aldern"]
        click((sx, sy - 4))
        self.assertIsNone(m.table.play)
        self.assertGreater(m.camp.gold["aldern"], gold)
        # council: free a seat with its X, then fill it from the list
        b = next(b for b in m.buttons if b.action == "council")
        click(b.rect.center)
        self.assertTrue(m.table.council_open)
        seat = m.table._seat_rect(4)
        before = list(m.camp.realms["aldern"].council)
        click((seat.right - 6, seat.y + 6))
        self.assertEqual(len(m.camp.realms["aldern"].council), COUNCIL_SEATS - 1)
        click(m.table._cand_rect(0).center)
        self.assertEqual(len(m.camp.realms["aldern"].council), COUNCIL_SEATS)
        self.assertNotEqual(m.camp.realms["aldern"].council, before)
        m.table.council_tab = "deck"
        frame(m.table._cand_rect(0).center)
        m.handle(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE), (0, 0))
        self.assertFalse(m.table.council_open)
        # end of turn: the others play, the chronicle opens, our turn again
        click(m.table.end_rect().center)
        self.assertTrue(m.table.chronicle_open)
        self.assertEqual(m.camp.whose_turn(), "aldern")
        self.assertEqual(m.camp.turn, 2)
        frame((0, 0))
        m.handle(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE), (0, 0))
        self.assertFalse(m.table.chronicle_open)
        # spectator: the button plays a round
        s = WorldMapScreen(Renderer(ensure_unit_sheets()), campaign=Campaign(None))
        s.update(0.05, (0, 0))
        s.draw(surf)
        pos = s.table.end_rect().center
        s.handle(pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=pos, button=1), pos)
        self.assertEqual(s.camp.turn, 2)


if __name__ == "__main__":
    unittest.main()
