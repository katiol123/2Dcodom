import tempfile
import unittest
import unittest.mock
from pathlib import Path

from game import saves
from game.campaign import Campaign
from game.officers import FIRST_NEWCOMER, OFFICER


class SaveTest(unittest.TestCase):
    def test_round_trip_keeps_playing(self):
        with tempfile.TemporaryDirectory() as d, \
                unittest.mock.patch("game.saves.path", lambda: Path(d) / "campaign.sav"):
            self.assertIsNone(saves.load())
            c = Campaign("aldern", seed=3)
            c.battle_hook = lambda camp, b: False             # the screen's hooks are not saved
            for _ in range(5):
                c.end_turn()
                c.run_ai()
            self.assertTrue(saves.save(c))
            fresh = [k for k in c.ostats if int(k.split(":")[1]) >= FIRST_NEWCOMER]
            self.assertTrue(fresh)
            for k in fresh:
                del OFFICER[k]                                # as after a restart of the game
            back = saves.load()
            self.assertIsNotNone(back)
            self.assertIsNone(back.battle_hook)
            self.assertEqual((back.turn, back.gold, back.owner), (c.turn, c.gold, c.owner))
            for k in fresh:
                self.assertIn(k, OFFICER)
            ids = {t.id for ts in back.free.values() for t in ts}
            self.assertNotIn(back._new("militia").id, ids)  # new troops get new ids
            back.end_turn()
            back.run_ai()
            self.assertEqual(back.turn, c.turn + 1)


class TitleTest(unittest.TestCase):
    def test_new_over_a_save_asks_first(self):
        from test_campaign import _pygame_ui
        pygame, renderer = _pygame_ui()
        from game.sim import H, W
        from game.title import TitleScreen
        c = Campaign("aldern", seed=3)
        with unittest.mock.patch("game.saves.load", lambda: c):
            t = TitleScreen(renderer)
        surf = pygame.Surface((W, H))
        key = lambda k: t.handle(pygame.event.Event(pygame.KEYDOWN, key=k), (0, 0))

        def frames(n=10):
            for _ in range(n):
                t.update(0.05, (0, 0))
                t.draw(surf)
        self.assertEqual(t.focus, 1)                                    # ПРОДОЛЖИТЬ first
        key(pygame.K_UP)
        key(pygame.K_RETURN)                                            # НАЧАТЬ over the save
        frames()
        self.assertTrue(t.confirm)
        self.assertIsNone(t.result)
        key(pygame.K_ESCAPE)                                            # НЕТ
        frames()
        self.assertFalse(t.confirm)
        key(pygame.K_RETURN)
        frames()
        key(pygame.K_RETURN)                                            # ДА
        frames()
        self.assertEqual(t.result, "new")


if __name__ == "__main__":
    unittest.main()
