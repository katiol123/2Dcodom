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
        self.assertEqual(len(ALL), 22)
        self.assertEqual(len(CLASSIC), 7)
        self.assertEqual({k for k, u in ROSTER.items() if u.ranged},
                         {"archer", "mage", "cleric", "crossbowman", "necromancer", "shaman", "goblin_shaman"})
        for u in ROSTER.values():
            self.assertTrue(u.perks and u.behavior, u.key)
            for name, desc in u.perks + u.flaws + u.behavior:
                self.assertEqual(name, name.upper(), u.key)
                self.assertTrue(desc and " - " not in desc, (u.key, name))

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
        self.assertIn((1, "skeleton"), summons)
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

    def test_skeleton_death_grip(self):
        from game import ai
        w = headless_world([["skeleton"], ["archer", "mage"]], 1)
        sk = w.units[0]
        archer = next(u for u in w.units if u.key == "archer")
        mage = next(u for u in w.units if u.key == "mage")
        sk.target = archer
        mage.x, mage.y = sk.x + 5, sk.y               # a juicier target right next to it
        self.assertIs(ai.pick_target(w, sk), archer)

    def test_wolves_hunt_the_same_prey(self):
        from game import ai
        w = headless_world([["wolf", "wolf"], ["knight", "archer", "mage"]], 2)
        w1, w2 = w.units[0], w.units[1]
        mage = next(u for u in w.units if u.key == "mage")
        w1.target = mage
        self.assertIs(ai.pick_target(w, w2), mage)

    def test_monk_intercepts_divers(self):
        from game import ai
        w = headless_world([["monk", "archer"], ["rogue", "cleric"]], 2)
        monk, archer = w.units[0], w.units[1]
        rogue = next(u for u in w.units if u.key == "rogue")
        rogue.target = archer
        self.assertIs(ai.pick_target(w, monk), rogue)

    def test_necromancer_walks_to_corpses(self):
        w = headless_world([["necromancer"], ["knight", "archer"]], 3)
        necro = w.units[0]
        archer = next(u for u in w.units if u.key == "archer")
        w.time = 5.0
        archer.x, archer.y = necro.x + 200, necro.y
        w.kill(archer, None)
        w.time = 7.0
        x0 = necro.x
        from game import ai
        for _ in range(30):
            ai.think(w, necro, 1 / 60)
            w._separate(1 / 60)
        self.assertGreater(necro.x, x0 + 2)            # heading for the body

    def test_every_class_contributes(self):
        dealt = {k: 0.0 for k in ALL}
        rng = random.Random(3)
        for seed in range(10):
            w = run(headless_world([random_squad(rng), random_squad(rng)], seed))
            for u in w.units:
                if not u.summoned:
                    dealt[u.key] += u.dealt + u.healed
        for k in ALL:
            if not ROSTER[k].boss:                     # bosses are never in random squads
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


class GoblinTest(unittest.TestCase):
    def test_goblin_panics_once_unless_mad_goblin_is_near(self):
        from game import ai
        w = headless_world([["goblin"], ["knight"]], 1)
        g = next(u for u in w.units if u.key == "goblin")
        g.hp = g.max_hp * 0.2
        ai.passives(w, g)
        self.assertTrue(g.has("panic"))
        g.status.clear()
        ai.passives(w, g)
        self.assertFalse(g.has("panic"))            # only once per battle
        w = headless_world([["goblin", "mad_goblin"], ["knight"]], 1)
        g = next(u for u in w.units if u.key == "goblin")
        mad = next(u for u in w.units if u.key == "mad_goblin")
        mad.x, mad.y = g.x + 10, g.y
        g.hp = g.max_hp * 0.2
        ai.passives(w, g)
        self.assertFalse(g.has("panic"))

    def test_troll_nest_kick_and_stupor(self):
        from game import ai
        w = headless_world([["troll"], ["knight"]], 1)
        w.time = 1.0
        troll = next(u for u in w.units if u.key == "troll")
        ai.passives(w, troll)
        troll.abil["nest"] = 0
        ai.passives(w, troll)
        gobs = [u for u in w.units if u.key == "goblin"]
        self.assertEqual(len(gobs), 4)
        self.assertEqual(troll.abil["nest"], ai.NEST_EVERY)
        self.assertEqual(ai.NEST_EVERY, 24.0)
        kicked = 0
        for _ in range(40):                           # each goblin is checked exactly once
            for g in gobs:
                g.hop, g.rising = 0.0, 0.0
                if g.alive:
                    g.x, g.y = troll.x + 5, troll.y
            ai.passives(w, troll)
        self.assertTrue(all(g.kick_checked for g in gobs))
        kicked = sum(g.kicked for g in gobs)
        self.assertLessEqual(kicked, 4)
        stupors = 0
        for _ in range(200):
            troll.status.pop("stupor", None)
            troll.abil["dumb"] = 0
            ai.passives(w, troll)
            stupors += troll.has("stupor")
        self.assertTrue(20 < stupors < 70, stupors)   # ~20 %

    def test_kick_sends_goblin_flying_and_kills_it(self):
        w = headless_world([["troll", "goblin"], ["knight"]], 1)
        w.time = 1.0
        troll = next(u for u in w.units if u.key == "troll")
        g = next(u for u in w.units if u.key == "goblin")
        x0 = g.x
        w.kick(troll, g)
        self.assertTrue(g.dead and g.kicked)
        for _ in range(60):
            w.step(1 / 60)
        self.assertGreater(abs(g.x - x0), 60)

    def test_wolf_rider_dodges_magic_and_rider_may_survive(self):
        w = headless_world([["wolf_rider"], ["mage"]], 1)
        w.time = 1.0
        rider = next(u for u in w.units if u.key == "wolf_rider")
        mage = next(u for u in w.units if u.key == "mage")
        misses = 0
        for _ in range(300):
            rider.hp = rider.max_hp
            misses += w.deal(mage, rider, 10, "magic") == 0
        self.assertTrue(60 < misses < 120, misses)    # ~30 %
        survived = 0
        for seed in range(40):
            w = headless_world([["wolf_rider", "knight"], ["mage"]], seed)
            w.time = 1.0
            w.kill(next(u for u in w.units if u.key == "wolf_rider"), None)
            gob = [u for u in w.units if u.key == "goblin"]
            if gob:
                survived += 1
                self.assertEqual(gob[0].hp, ROSTER["goblin"].hp * 0.5)
        self.assertTrue(4 < survived < 22, survived)

    def test_mad_goblin_blocks_from_the_front_only(self):
        w = headless_world([["mad_goblin"], ["archer", "knight"]], 1)
        w.time = 1.0
        mad = next(u for u in w.units if u.key == "mad_goblin")
        knight = next(u for u in w.units if u.key == "knight")
        mad.facing = 1
        knight.x, knight.y = mad.x + 15, mad.y
        blocked = 0
        for _ in range(300):
            mad.hp = mad.max_hp
            blocked += w.deal(knight, mad, 10, "physical") == 0
        self.assertTrue(30 < blocked < 95, blocked)   # ~20 %
        knight.x = mad.x - 15                          # from behind: never blocked
        for _ in range(100):
            mad.hp = mad.max_hp
            self.assertGreater(w.deal(knight, mad, 10, "physical"), 0)


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
