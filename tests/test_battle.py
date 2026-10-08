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
        self.assertEqual(len(ALL), 57)
        self.assertEqual(len(CLASSIC), 7)
        self.assertEqual({k for k, u in ROSTER.items() if u.ranged},
                         {"archer", "mage", "cleric", "crossbowman", "necromancer", "shaman", "goblin_shaman",
                          "ranger", "dryad", "druid", "banshee", "horse_archer", "ice_witch", "frost_giant",
                          "alchemist", "rune_priest", "slinger"})
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

    def test_spearman_counters_any_charge_in_reach(self):
        from game import ai
        w = headless_world([["spearman", "archer"], ["barbarian"]], 1)
        w.time = 1.0
        spear = next(u for u in w.units if u.key == "spearman")
        archer = next(u for u in w.units if u.key == "archer")
        barb = next(u for u in w.units if u.key == "barbarian")
        barb.x, barb.y = spear.x + 30, spear.y
        barb.target = archer
        self.assertFalse(ai._try_abilities(w, spear))   # not rushing: nothing to counter
        barb.status["charge"] = 1.0                # rushing past him at the archer: still caught
        self.assertTrue(ai._try_abilities(w, spear))
        spear.action = None
        spear.cd = 0.0
        barb.x = spear.x + 90                      # out of reach: no counter
        self.assertFalse(ai._try_abilities(w, spear))
        barb.x = spear.x + 30
        barb.target = spear
        barb.status["charge"] = 1.0
        x0, hp0 = barb.x, barb.hp
        self.assertTrue(ai._try_abilities(w, spear))   # the braced spear strikes at once
        self.assertFalse(barb.has("charge"))
        self.assertGreater(barb.x - x0, 15)        # knocked back
        self.assertTrue(barb.has("stun"))          # thrown off its feet
        self.assertIs(barb.target, spear)          # and turned on the spearman
        lo = ROSTER["spearman"].damage[0] * ai.COUNTER_BONUS * (1 - ROSTER["barbarian"].armor)
        self.assertGreaterEqual(hp0 - barb.hp, round(lo) - 1)
        x0 = barb.x
        ai._melee(w, spear, barb)                  # an ordinary thrust: no knockback
        self.assertAlmostEqual(barb.x, x0)

    def _pair(self, a, b):
        from game import ai
        w = headless_world([[a], [b]], 1)
        w.time = 1.0
        u, e = w.units
        e.x, e.y = u.x + 25, u.y
        u.target, e.target = e, u
        u.facing, e.facing = 1, -1
        return ai, w, u, e

    def test_every_counter_unit_meets_a_rush(self):
        for counter in ("spearman", "halberdier", "militia", "uhlan"):
            ai, w, u, e = self._pair(counter, "barbarian")
            e.status["charge"] = 1.0
            hp = e.hp
            self.assertTrue(ai._try_abilities(w, u), counter)
            self.assertFalse(e.has("charge"), counter)
            self.assertLess(e.hp, hp, counter)

    def test_uhlan_lance_breaks_a_rushing_rider(self):
        for rusher in ("lancer", "wolf", "barbarian"):
            ai, w, u, e = self._pair("uhlan", rusher)
            u.status["charge"] = 1.0                   # both in a rush; only the uhlan has the couched lance
            u.status["lancehit"] = 1.5
            e.status["charge"] = 1.0
            hp = e.hp
            self.assertTrue(ai._try_abilities(w, u), rusher)
            self.assertFalse(e.has("charge"))
            self.assertFalse(u.has("charge") or u.has("lancehit"))   # his own rush ends too, no double bonus
            hi = ROSTER["uhlan"].damage[1] * ai.COUNTER_BONUS * 1.6
            self.assertLessEqual(hp - e.hp, hi + 1)

    def test_two_uhlans_joust(self):
        self._joust("uhlan")

    def test_two_mounted_knights_joust(self):
        self._joust("lancer")

    def test_any_two_rushes_head_on_clash(self):
        from game import ai
        for a, b in (("barbarian", "wolf"), ("mamluk", "lancer"), ("wolf_rider", "valkyrie"), ("orc", "barbarian")):
            ai_, w, u, e = self._pair(a, b)
            for x in (u, e):
                x.status["charge"] = 1.0
                x.status["stunhit"] = 1.5
            hu, he = u.hp, e.hp
            self.assertTrue(ai._try_abilities(w, u), (a, b))
            self.assertFalse(u.has("charge") or e.has("charge"), (a, b))
            self.assertFalse(u.has("stunhit") or e.has("stunhit"), (a, b))
            self.assertLess(u.hp + e.hp, hu + he)          # both strike (a dodge may still save one)
            self.assertTrue(any(t.text == "СШИБКА!" for t in w.texts))

    def _joust(self, key):
        ai, w, a, b = self._pair(key, key)
        a.cd = b.cd = 0.0
        for x in (a, b):
            x.status["charge"] = 1.0
            x.status["lancehit"] = 1.5
        ha, hb = a.hp, b.hp
        self.assertTrue(ai._try_abilities(w, a))
        for x in (a, b):
            self.assertFalse(x.has("charge") or x.has("lancehit"))
            self.assertTrue(x.has("stun") and x.has("regroup"))
        self.assertLess(a.hp, ha)                      # both lances strike at once
        self.assertLess(b.hp, hb)
        self.assertTrue(any(t.text == "СШИБКА!" for t in w.texts))

    def test_foot_spears_beat_the_uhlan_rush(self):
        ai, w, u, e = self._pair("spearman", "uhlan")
        e.status["charge"] = 1.0
        e.status["lancehit"] = 1.5
        self.assertTrue(ai._try_abilities(w, u))
        self.assertFalse(e.has("charge"))
        self.assertTrue(e.has("stun"))

    def test_uhlan_rides_off_for_run_ups(self):
        w = headless_world([["uhlan"], ["knight"]], 2)
        charges = 0
        was = False
        while w.winner is None and w.time < 30:
            w.step(1 / 60)
            now = w.units[0].has("charge")
            charges += now and not was
            was = now
        self.assertGreaterEqual(charges, 4)            # a fresh run-up every few seconds

    def test_spears_shield_the_mage_from_wolves(self):
        """Two spearmen and a mage against two wolves rushing past at the mage: the spears must
        meet the rush (no misses) and the mage must have a real chance to live."""
        alive = misses = 0
        for seed in range(20):
            w = headless_world([["spearman", "spearman", "mage"], ["wolf", "wolf"]], seed)
            seen = set()
            mage = next(u for u in w.units if u.key == "mage")
            while w.winner is None and w.time < 120:
                w.step(1 / 60)
                for t in w.texts:
                    if id(t) not in seen:
                        seen.add(id(t))
                        misses += t.text == "МИМО"
            alive += mage.alive
        self.assertGreaterEqual(alive, 5)          # at least a quarter of the fights
        self.assertLess(misses, 20)

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
        for seed in range(30):
            w = run(headless_world([random_squad(rng), random_squad(rng)], seed))
            for u in w.units:
                if not u.summoned:
                    dealt[u.base_key] += u.dealt + u.healed
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


class RealmUnitsTest(unittest.TestCase):
    def test_prices_follow_power_tiers(self):
        avg = lambda tier: sum(u.cost for u in ROSTER.values() if u.tier == tier) / max(
            1, sum(1 for u in ROSTER.values() if u.tier == tier))
        self.assertLess(avg("weak"), avg("below"))
        self.assertLess(avg("below"), avg("average"))
        self.assertLess(avg("average"), avg("above"))
        cheap = [k for k in ALL if ROSTER[k].cost <= 50]
        self.assertGreaterEqual(len(cheap), 5, cheap)
        for u in ROSTER.values():
            self.assertGreater(u.upkeep, 0)

    def test_cornered_shooter_fights_back(self):
        from game import ai
        from game.sim import FIELD
        w = headless_world([["shaman"], ["barbarian"]], 1)
        w.time = 1.0
        sh = next(u for u in w.units if u.key == "shaman")
        barb = next(u for u in w.units if u.key == "barbarian")
        sh.x, sh.y = FIELD[0], FIELD[1]            # in the corner
        barb.x, barb.y = sh.x + 12, sh.y + 2
        barb.target = sh
        sh.target = barb
        shots = 0
        for _ in range(240):
            barb.cd = 99.0                         # keep the barbarian from killing it
            w.step(1 / 60)
            shots += sh.action is not None and sh.action["kind"] == "shot"
        self.assertGreater(shots, 0)

    def test_harpoon_pulls_a_shooter(self):
        from game import ai
        w = headless_world([["harpooner"], ["archer", "knight"]], 1)
        w.time = 1.0
        h = next(u for u in w.units if u.key == "harpooner")
        a = next(u for u in w.units if u.key == "archer")
        a.x, a.y = h.x + 90, h.y
        h.facing = 1
        self.assertTrue(ai._try_abilities(w, h))
        ai.resolve_action(w, h, h.action)
        self.assertLess(abs(a.x - h.x), 20)
        self.assertTrue(a.has("stun") or a.dead)

    def test_druid_turns_into_a_bear_once(self):
        from game import ai
        w = headless_world([["druid"], ["knight"]], 1)
        w.time = 1.0
        d = w.units[0] if w.units[0].base_key == "druid" else w.units[1]
        d.hp = d.max_hp * 0.3
        ai.passives(w, d)
        self.assertEqual(d.key, "bear")
        self.assertEqual(d.base_key, "druid")
        self.assertGreater(d.hp / d.max_hp, 0.6)

    def test_valkyrie_brings_back_a_fallen_ally(self):
        from game import ai
        w = headless_world([["valkyrie", "archer"], ["knight"]], 1)
        w.time = 5.0
        v = next(u for u in w.units if u.key == "valkyrie")
        a = next(u for u in w.units if u.key == "archer")
        w.kill(a, None)
        w.time = 7.0
        a.x, a.y = v.x + 5, v.y
        self.assertTrue(ai._try_abilities(w, v))
        ai.resolve_action(w, v, v.action)
        self.assertTrue(a.alive)
        self.assertAlmostEqual(a.hp, a.max_hp * 0.4)
        self.assertIsNone(ai._valk_body(w, v))          # only once per battle

    def test_bomber_blast_ignores_shields(self):
        from game import ai
        w = headless_world([["goblin_bomber"], ["knight"]], 1)
        w.time = 1.0
        b = next(u for u in w.units if u.key == "goblin_bomber")
        k = next(u for u in w.units if u.key == "knight")
        k.x, k.y, k.facing = b.x + 8, b.y, -1
        hp = k.hp
        ai.explode(w, b, 1.0)
        self.assertTrue(b.dead)
        self.assertGreater(hp - k.hp, ROSTER["goblin_bomber"].damage[0] * 0.9)


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
