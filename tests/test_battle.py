import random
import unittest

from game.assets import SpriteFactory, plan_battle
from game.match import headless_world, random_squad
from game.units import ALL, CLASSIC, ROSTER, TEAMS, look_for


def run(w, limit=180.0):
    while w.winner is None and w.time < limit:
        w.step(1 / 60)
    return w


class RosterTest(unittest.TestCase):
    def test_roster(self):
        self.assertEqual(len(ALL), 17)
        self.assertEqual(len(CLASSIC), 7)
        self.assertEqual({k for k, u in ROSTER.items() if u.ranged},
                         {"archer", "mage", "cleric", "crossbowman", "necromancer", "shaman"})
        for u in ROSTER.values():
            self.assertTrue(u.strong and u.weak, u.key)

    def test_looks_vary_within_class_but_keep_identity(self):
        for key in ALL:
            looks = [look_for(key, TEAMS[0], s) for s in range(12)]
            self.assertGreater(len({repr(x) for x in looks}), 3, key)        # faces differ
            self.assertEqual(look_for(key, TEAMS[0], 5), look_for(key, TEAMS[0], 5))  # deterministic
            if hasattr(looks[0], "weapon"):
                if key != "skeleton":
                    self.assertEqual(len({x.weapon for x in looks}), 1, key)  # class weapon is fixed

    def test_plan_gives_every_unit_its_own_look(self):
        slots, summons, looks = plan_battle([["knight"] * 4, ["necromancer", "wolf"]], 3)
        self.assertEqual(len({s.look for s in slots if s.team == 0}), 4)
        self.assertIn(1, summons)
        self.assertEqual(len(looks), len({s.look for s in slots}) + 1)


class BattleTest(unittest.TestCase):
    def test_classic_battle_ends(self):
        for seed in (1, 2):
            w = run(headless_world([CLASSIC, CLASSIC], seed))
            self.assertIsNotNone(w.winner)
            self.assertEqual(w.standing(1 - w.winner), 0)
            self.assertTrue(15 < w.end_time < 120, w.end_time)

    def test_random_squads_and_uneven_sizes(self):
        rng = random.Random(9)
        for seed in range(4):
            squads = [random_squad(rng, rng.randint(1, 7)), random_squad(rng, rng.randint(1, 7))]
            w = run(headless_world(squads, seed), limit=240)
            self.assertIsNotNone(w.winner, squads)

    def test_deterministic(self):
        sq = [["paladin", "wolf", "shaman"], ["ogre", "necromancer", "cleric"]]
        a, b = run(headless_world(sq, 5)), run(headless_world(sq, 5))
        self.assertEqual(a.winner, b.winner)
        self.assertAlmostEqual(a.end_time, b.end_time)

    def test_damage_model(self):
        w = headless_world([["knight", "skeleton"], ["mage", "hammerer", "paladin"]], 1)
        knight, skel = w.units[0], next(u for u in w.units if u.key == "skeleton")
        mage = next(u for u in w.units if u.key == "mage")
        hammer = next(u for u in w.units if u.key == "hammerer")
        hp = knight.hp
        w.deal(mage, knight, 100, "magic")                  # magic ignores armor
        self.assertEqual(hp - knight.hp, 100)
        hp = skel.hp
        w.deal(hammer, skel, 100, "physical")               # blunt: x1.5 vs undead, ignores 30% armor
        self.assertEqual(hp - skel.hp, round(100 * 1.5 * (1 - ROSTER["skeleton"].armor * 0.7)))

    def test_skeleton_revives_unless_smashed(self):
        w = headless_world([["skeleton", "skeleton"], ["rogue", "hammerer"]], 1)
        w.time = 1.0
        s1, s2 = w.units[0], w.units[1]
        rogue = next(u for u in w.units if u.key == "rogue")
        hammer = next(u for u in w.units if u.key == "hammerer")
        w.deal(rogue, s1, 10_000, "magic")
        w.deal(hammer, s2, 10_000, "physical")
        self.assertIsNotNone(s1.revive_at)
        self.assertIsNone(s2.revive_at)
        for _ in range(200):
            w.step(1 / 60)
        self.assertTrue(s1.alive)
        self.assertTrue(s2.dead)

    def test_paladin_divine_shield_once(self):
        w = headless_world([["paladin"], ["ogre"]], 1)
        pal = w.units[0]
        w.deal(None, pal, 10_000, "magic")
        self.assertTrue(pal.alive and pal.has("divine"))
        pal.status.clear()
        w.deal(None, pal, 10_000, "magic")
        self.assertTrue(pal.dead)

    def test_spearman_counters_only_a_charge_at_him(self):
        from game import ai
        w = headless_world([["spearman", "archer"], ["barbarian"]], 1)
        w.time = 1.0
        spear, archer = w.units[0], w.units[1]
        barb = next(u for u in w.units if u.key == "barbarian")
        barb.x, barb.y = spear.x + 30, spear.y
        barb.status["charge"] = 1.0
        barb.target = archer                       # rushing past him at someone else: no brace
        self.assertFalse(ai._try_abilities(w, spear))
        barb.target = spear                        # rushing at him: brace and counter
        self.assertTrue(ai._try_abilities(w, spear))
        self.assertTrue(spear.action["counter"])
        x0, hp0 = barb.x, barb.hp
        ai._melee(w, spear, barb, counter=True)
        self.assertFalse(barb.has("charge"))
        self.assertGreater(barb.x - x0, 15)        # knocked back
        lo = ROSTER["spearman"].damage[0] * ai.COUNTER_BONUS * (1 - ROSTER["barbarian"].armor)
        self.assertGreaterEqual(hp0 - barb.hp, round(lo) - 1)
        x0 = barb.x
        ai._melee(w, spear, barb)                  # an ordinary thrust: no knockback
        self.assertAlmostEqual(barb.x, x0)

    def test_rush_is_not_spammed_after_a_counter(self):
        for enemy in ("barbarian", "orc", "wolf"):
            w = headless_world([["spearman"], [enemy]], 3)
            seen, counters = set(), 0
            while w.time < 9 and w.winner is None:
                w.step(1 / 60)
                for t in w.texts:
                    if id(t) not in seen:
                        seen.add(id(t))
                        counters += t.text.startswith("КОНТРУДАР")
            self.assertEqual(counters, 1, enemy)

    def test_every_class_contributes(self):
        dealt = {k: 0.0 for k in ALL}
        rng = random.Random(3)
        for seed in range(10):
            w = run(headless_world([random_squad(rng), random_squad(rng)], seed))
            for u in w.units:
                if not u.summoned:
                    dealt[u.key] += u.dealt + u.healed
        for k in ALL:
            self.assertGreater(dealt[k], 0, k)

    def test_abilities_happen(self):
        seen = set()
        squads = [["necromancer", "orc", "rogue", "shaman", "cleric", "hammerer", "monk"],
                  ["mage", "archer", "wolf", "wolf", "knight", "paladin", "skeleton"]]
        for seed in range(3):
            w = headless_world(squads, seed)
            while w.winner is None and w.time < 120:
                w.step(1 / 60)
                seen.update(p.kind for p in w.projectiles)
                seen.update(t.text for t in w.texts)
                if w.bolts:
                    seen.add("lightning")
                if any(u.summoned for u in w.units):
                    seen.add("summon")
        for key in ("arrow", "fireball", "dark", "lightning", "summon", "ВААГХ!", "ТЕНЬ!", "АУУУ!"):
            self.assertIn(key, seen)


class FactoryTest(unittest.TestCase):
    def test_parallel_build_and_cache(self):
        slots, summons, looks = plan_battle([["monk", "ogre"], ["wolf", "crossbowman"]], 424242)
        f = SpriteFactory(workers=2)
        try:
            metas = f.ensure(looks)
        finally:
            f.close()
        self.assertEqual(set(metas), set(looks))
        for m in metas.values():
            self.assertIn("attack", m["animations"])


if __name__ == "__main__":
    unittest.main()
