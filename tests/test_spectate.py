import os
import unittest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

from game.campaign import Campaign
from game.diplomacy import propose
from game.factions import CITY, FACTION


class SpectateTest(unittest.TestCase):
    def test_every_card_and_embassy_reaches_the_show_hook(self):
        c = Campaign(None, seed=3)
        shown = []
        c.show_hook = lambda camp, what: shown.append(what)
        c.run_ai(stop_at_player=False, max_turns=1)
        cards = [w for w in shown if w["what"] == "card"]
        envoys = [w for w in shown if w["what"] == "diplo"] + [w["envoys"] for w in cards if w["envoys"]]
        self.assertEqual(len(cards), sum(c.stats["played"].values()))
        self.assertTrue(cards and all(w["faction"] in FACTION and "msg" in w for w in cards))
        self.assertTrue(envoys)
        for e in envoys:
            self.assertIn(e["to"], FACTION)
            self.assertIsInstance(e["yes"], bool)
        self.assertIsNone(c._envoys)
        self.assertFalse(c._playing)

    def test_envoys_of_a_card_ride_with_it(self):
        c = Campaign(None, seed=3)
        shown = []
        c.show_hook = lambda camp, what: shown.append(what)
        c._playing = True                              # as inside Campaign.play
        propose(c, "aldern", "sylvan", "truce", bonus=999)
        self.assertEqual(shown, [])                    # kept for the card's own show
        self.assertEqual(c._envoys["treaty"], "truce")
        c._playing, c._envoys = False, None
        propose(c, "league", "ashen", "trade", bonus=999)
        self.assertEqual(shown[-1]["what"], "diplo")  # on its own

    def test_what_a_card_was_played_on(self):
        from game.spectate import target_of
        city = next(iter(CITY))
        self.assertEqual(target_of("tax", [city]), ("city", city))
        self.assertEqual(target_of("march", [city, ["aldern:1"], "kronholm"]), ("city", "kronholm"))
        self.assertEqual(target_of("embassy", ["sylvan"]), ("realm", "sylvan"))
        self.assertEqual(target_of("ford_hero", ["aldern:2"]), ("officer", "aldern:2"))
        self.assertEqual(target_of("golden_age", []), ("self", None))

    def test_the_spectator_watches_a_round(self):
        import pygame
        from game.assets import ensure_unit_sheets
        from game.mapview import WorldMapScreen
        from game.render import Renderer
        from game.sim import H, W
        pygame.init()
        pygame.display.set_mode((W, H))
        m = WorldMapScreen(Renderer(ensure_unit_sheets()), campaign=Campaign(None, seed=3))
        m.runner.watch_ai = "calc"
        s = pygame.Surface((W, H))
        m.table.next_round()
        shows, frames = set(), 0
        while m.runner.busy() and frames < 40000:
            m.update(0.1, (5, 5))
            m.draw(s)
            frames += 1
            if m.show is not None:
                shows.add(id(m.show))
                if len(shows) == 2:                    # a click moves on
                    m.handle(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=(5, 5)), (5, 5))
                if len(shows) == 3:                    # Esc: the rest goes by unseen
                    m.handle(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE), (5, 5))
        self.assertFalse(m.runner.busy())
        self.assertEqual(len(shows), 3)
        self.assertFalse(m.runner.show_plays)

    def test_every_new_ruler_is_announced_goblins_too(self):
        from game.succession import die
        c = Campaign("aldern", seed=3)
        shown = []
        c.show_hook = lambda camp, what: shown.append(what)
        for f in ("goblin", "aldern"):
            old = c.leader[f]
            die(c, old, "пал в бою")
            rec = c.successions[-1]
            self.assertEqual((rec["faction"], rec["old"], rec["new"]), (f, old, c.leader[f]))
            self.assertEqual(shown[-1]["what"], "ruler")
        self.assertEqual([r["idx"] for r in c.successions], [0, 1])

    def test_the_player_sees_the_new_ruler_card(self):
        import pygame
        from game.assets import ensure_unit_sheets
        from game.mapview import WorldMapScreen
        from game.render import Renderer
        from game.sim import H, W
        from game.succession import die
        pygame.init()
        pygame.display.set_mode((W, H))
        c = Campaign("aldern", seed=3)
        m = WorldMapScreen(Renderer(ensure_unit_sheets()), campaign=c)
        die(c, c.leader["goblin"], "пал в бою")
        m.update(0.05, (5, 5))
        m.draw(pygame.Surface((W, H)))
        self.assertEqual(m.ruler_show["faction"], "goblin")
        m.handle(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=(5, 5)), (5, 5))
        self.assertIsNone(m.ruler_show)


if __name__ == "__main__":
    unittest.main()
