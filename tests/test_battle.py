import unittest

from game.assets import anim_infos, ensure_unit_sheets
from game.sim import World
from game.units import ORDER, ROSTER


class BattleTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        metas = ensure_unit_sheets()            # cached after the first run
        cls.anims = {k: anim_infos(m) for k, m in metas.items()}

    def run_battle(self, seed, limit=180.0):
        w = World(self.anims, seed)
        while w.winner is None and w.time < limit:
            w.step(1 / 60)
        return w

    def test_roster(self):
        self.assertEqual(sorted(ORDER), sorted(ROSTER))
        self.assertEqual(len(ORDER), 7)
        self.assertEqual({k for k, u in ROSTER.items() if u.ranged}, {"archer", "mage"})
        for u in ROSTER.values():
            self.assertTrue(u.strong and u.weak, u.key)

    def test_battle_ends_with_winner(self):
        for seed in (1, 2, 3):
            w = self.run_battle(seed)
            self.assertIsNotNone(w.winner, f"seed {seed} did not finish")
            self.assertEqual(w.alive_count(1 - w.winner), 0)
            self.assertGreater(w.alive_count(w.winner), 0)
            self.assertTrue(15 < w.end_time < 120, w.end_time)

    def test_deterministic(self):
        a, b = self.run_battle(5), self.run_battle(5)
        self.assertEqual(a.winner, b.winner)
        self.assertAlmostEqual(a.end_time, b.end_time)
        self.assertEqual([round(u.hp) for u in a.units], [round(u.hp) for u in b.units])

    def test_every_unit_contributes(self):
        dealt = {k: 0.0 for k in ORDER}
        for seed in range(6):
            for u in self.run_battle(seed).units:
                dealt[u.key] += u.dealt
        for k, v in dealt.items():
            self.assertGreater(v, 150, k)

    def test_damage_model(self):
        w = World(self.anims, 1)
        knight = next(u for u in w.units if u.key == "knight" and u.team == 0)
        mage = next(u for u in w.units if u.key == "mage" and u.team == 1)
        hp = knight.hp
        w.deal(mage, knight, 100, "magic")            # magic ignores the knight's armor
        self.assertEqual(hp - knight.hp, 100)
        orc = next(u for u in w.units if u.key == "orc" and u.team == 0)
        hp = orc.hp
        w.deal(None, orc, 100, "physical")
        self.assertEqual(hp - orc.hp, round(100 * (1 - ROSTER["orc"].armor)))

    def test_projectiles_and_abilities_happen(self):
        seen = set()
        for seed in range(4):
            w = World(self.anims, seed)
            while w.winner is None and w.time < 120:
                w.step(1 / 60)
                seen.update(p.kind for p in w.projectiles)
                seen.update(t.text for t in w.texts if not t.text.strip("+0123456789 ").isdigit())
        for key in ("arrow", "fireball", "ВААГХ!", "ТЕНЬ!"):
            self.assertIn(key, seen)


if __name__ == "__main__":
    unittest.main()
