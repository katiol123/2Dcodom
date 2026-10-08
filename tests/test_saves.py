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


if __name__ == "__main__":
    unittest.main()
