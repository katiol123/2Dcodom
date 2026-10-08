import unittest

from game import ai
from game.match import headless_world


class FormationTest(unittest.TestCase):
    def test_who_keeps_the_line(self):
        w = headless_world([["knight", "assassin", "archer", "cleric", "troll"], ["spearman"]], 1)
        by = {u.key: u for u in w.units if u.team == 0}
        self.assertTrue(ai.in_line(by["knight"]))
        for k in ("assassin", "archer", "cleric", "troll"):
            self.assertFalse(ai.in_line(by[k]), k)
        self.assertIsNotNone(by["knight"].row)

    def test_soldiers_march_in_line_and_fight_from_their_side(self):
        w = headless_world([["knight", "spearman", "barbarian", "halberdier"] * 2,
                            ["knight", "spearman", "barbarian", "halberdier"] * 2], 3)
        line = [u for u in w.units if ai.in_line(u)]
        while w.time < 1.0:
            w.step(1 / 60)
        far = [u for u in line if u.alive and u.target and abs(u.target.x - u.x) > ai.LINE_CLOSE[1]]
        for u in far:                                   # still marching: they keep to their rows
            self.assertLess(abs(u.y - u.row), 12, u.key)
        while w.time < 6.0 and w.winner is None:
            w.step(1 / 60)
        for u in line:
            if u.alive and u.target and ai.in_melee_range(u, u.target):
                behind = (u.x - u.target.x) * (1 if u.team == 0 else -1)
                self.assertLess(behind, 8, u.key)       # no wrapping round to the enemy's back


if __name__ == "__main__":
    unittest.main()
