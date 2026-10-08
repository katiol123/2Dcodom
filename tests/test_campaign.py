import itertools
import math
import os
import unittest

from game.factions import (ALL_FACTIONS, CITIES, CITY, EMBLEMS, FACTION, FACTIONS, GOBLINS, NEW_UNITS, ROADS,
                           cities_of, neighbors, relation, relation_status)
from game.units import ROSTER


class FactionDataTest(unittest.TestCase):
    def test_eight_playable_factions_and_wild_goblins(self):
        self.assertEqual(len(FACTIONS), 8)
        self.assertTrue(all(f.playable for f in FACTIONS))
        self.assertFalse(GOBLINS.playable)
        for f in ALL_FACTIONS:
            self.assertIn(f.emblem, EMBLEMS)
            self.assertEqual(CITY[f.capital].faction, f.key, f.key)
            self.assertGreaterEqual(len(cities_of(f.key)), 3, f.key)
            self.assertTrue(f.lore and f.leader and len(f.mechanics) >= 3, f.key)
        for em in EMBLEMS.values():
            self.assertEqual((len(em), {len(r) for r in em}), (9, {9}))

    def test_relations(self):
        for a, b in itertools.combinations([f.key for f in FACTIONS], 2):
            v, why = relation(a, b)
            self.assertTrue(1 <= v <= 100 and why, (a, b))
            self.assertEqual(relation(b, a), (v, why))
        values = [relation(a.key, b.key)[0] for a, b in itertools.combinations(FACTIONS, 2)]
        self.assertTrue(any(v >= 80 for v in values) and any(v < 20 for v in values))
        for f in FACTIONS:                                   # no diplomacy with goblins
            self.assertEqual(relation(f.key, "goblin")[0], 0)
            self.assertEqual(relation_status(0)[0], "ВЕЧНАЯ ВОЙНА")

    def test_cities_and_pools(self):
        self.assertEqual(len({c.key for c in CITIES}), len(CITIES))
        for c in CITIES:
            self.assertIn(c.faction, FACTION)
            self.assertTrue(3 <= len(c.pool) <= 6, c.key)
            self.assertEqual(len(set(c.pool)), len(c.pool), c.key)
            for u in c.pool:
                self.assertTrue(u in ROSTER or u in NEW_UNITS, (c.key, u))
        for a, b in itertools.combinations(CITIES, 2):     # room for sprites and name ribbons
            self.assertGreater(math.hypot(a.x - b.x, a.y - b.y), 60, (a.key, b.key))
        self.assertGreaterEqual(len(cities_of("goblin")), 5)
        used = {u for c in CITIES for u in c.pool}
        self.assertFalse(set(NEW_UNITS) - used)            # every planned unit is hired somewhere

    def test_roads_connect_everything(self):
        self.assertEqual(len({frozenset(r) for r in ROADS}), len(ROADS))
        for a, b in ROADS:
            self.assertIn(a, CITY)
            self.assertIn(b, CITY)
        for c in CITIES:
            self.assertGreaterEqual(len(neighbors(c.key)), 2, c.key)
        seen, stack = {CITIES[0].key}, [CITIES[0].key]
        while stack:
            for n in neighbors(stack.pop()):
                if n not in seen:
                    seen.add(n)
                    stack.append(n)
        self.assertEqual(seen, set(CITY))


class OfficersTest(unittest.TestCase):
    def test_named_officers_with_leadership_and_six_stats(self):
        from game.officers import OFFICERS, STATS, bio
        self.assertEqual(set(OFFICERS), {f.key for f in ALL_FACTIONS})
        keys = set()
        for fk, offs in OFFICERS.items():
            self.assertTrue(12 <= len(offs) <= 22, fk)
            self.assertEqual(offs[0].rank, 0)
            self.assertEqual(offs[0].name, FACTION[fk].leader)
            self.assertEqual(len({o.name for o in offs}), len(offs), fk)
            for o in offs:
                keys.add(o.key)
                self.assertEqual(len(o.stats), len(STATS))
                self.assertTrue(all(1 <= v <= 20 for v in o.stats), o.key)
                self.assertTrue(200 <= o.leadership <= 800, o.key)
                b = bio(o)
                self.assertTrue(80 < len(b) < 330, o.key)
                self.assertFalse(set("{}|") & set(b), o.key)       # gendered forms all resolved
            # leadership follows rank: the leader leads the biggest squad
            self.assertEqual(max(offs, key=lambda o: o.leadership).rank, 0)
        self.assertEqual(len(keys), sum(len(v) for v in OFFICERS.values()))

    def test_faces_are_deterministic_and_follow_presence(self):
        from game.faces import paint_face, paint_web, presence
        from game.officers import OFFICER, OFFICERS
        a = paint_face("aldern:3", 30, 36)
        self.assertEqual(a.size, (30, 36))
        self.assertEqual(a.tobytes(), paint_face("aldern:3", 30, 36).tobytes())
        self.assertNotEqual(a.tobytes(), paint_face("aldern:4", 30, 36).tobytes())
        for fk in OFFICERS:                                     # every faction's faces paint
            self.assertEqual(paint_face(OFFICERS[fk][-1].key, 20, 24).size, (20, 24))
        ps = [presence(o) for o in OFFICER.values()]
        self.assertTrue(min(ps) >= 0 and max(ps) <= 1)
        self.assertTrue(any(p >= 0.6 for p in ps) and any(p < 0.36 for p in ps))   # heroes and nobodies
        web = paint_web((1, 5, 10, 15, 20, 8), "#2f5fbf", "#7fa8f0", 40, 40)
        self.assertEqual((web.size, web.mode), ((40, 40), "RGBA"))


class CampaignRulesTest(unittest.TestCase):
    def setUp(self):
        from game.campaign import Campaign
        self.c = Campaign("aldern")

    def test_setup(self):
        from game.officers import OFFICER, OFFICERS, SQUAD_SLOTS
        c = self.c
        for city in CITIES:
            self.assertTrue(c.officers_in(city.key), city.key)        # every city has a commander
        for key, squad in c.squads.items():
            self.assertLessEqual(len(squad), SQUAD_SLOTS)
            self.assertLessEqual(c.power(key), OFFICER[key].leadership)
        self.assertEqual(c.officer_city[OFFICERS["aldern"][0].key], FACTION["aldern"].capital)
        self.assertTrue(c.controls("kronholm"))
        self.assertFalse(c.controls(FACTION["north"].capital))
        from game.campaign import Campaign
        self.assertFalse(any(Campaign(None).controls(x.key) for x in CITIES))   # spectator manages nothing

    def test_hire_and_assign(self):
        from game.officers import OFFICER, SQUAD_SLOTS
        c = self.c
        city = "kronholm"
        gold = c.gold["aldern"]
        key = CITY[city].pool[0]
        n = len(c.free[city])
        t = c.hire(city, key)
        self.assertIsNotNone(t)
        self.assertEqual(c.gold["aldern"], gold - ROSTER[key].cost)
        self.assertEqual(len(c.free[city]), n + 1)                  # stands in the city from the purchase
        self.assertFalse(c.can_hire(city, "troll")[0])               # not in this city's pool
        c.gold["aldern"] = 0
        self.assertEqual(c.can_hire(city, key), (False, "НЕ ХВАТАЕТ ЗОЛОТА"))
        off = c.officers_in(city)[0].key
        for tr in list(c.squads[off]):
            c.unassign(off, tr.id)
        self.assertEqual(c.power(off), 0)
        self.assertTrue(c.assign(off, t.id))
        self.assertNotIn(t, c.free[city])
        self.assertTrue(c.unassign(off, t.id))
        self.assertIn(t, c.free[city])
        # leadership caps the squad's power, 7 slots cap its size
        c.free[city] = [c._new("knight") for _ in range(12)]
        added = [tr for tr in list(c.free[city]) if c.assign(off, tr.id)]
        self.assertLessEqual(c.power(off), OFFICER[off].leadership)
        self.assertEqual(len(added), min(SQUAD_SLOTS, OFFICER[off].leadership // ROSTER["knight"].cost))
        rest = c.free[city][0]
        ok, why = c.can_assign(off, rest.id)
        self.assertFalse(ok)
        self.assertIn(why, ("НЕ ХВАТАЕТ ЛИДЕРСТВА", "ВСЕ 7 МЕСТ ЗАНЯТЫ"))
        other = next(o for o in OFFICER if c.officer_city[o] != city)
        self.assertFalse(c.can_assign(other, rest.id)[0])           # only officers in the same city

    def test_defection(self):
        c = self.c
        off = c.officers_in("kronholm")[-1]
        up = c.upkeep("aldern")
        c.defect(off.key, "league")
        self.assertIn(off, c.officers_of("league"))
        self.assertNotIn(off, c.officers_of("aldern"))
        self.assertNotIn(off, c.officers_in("kronholm"))           # no longer commands an aldern city
        self.assertLessEqual(c.upkeep("aldern"), up)


class WorldGenTest(unittest.TestCase):
    def test_cities_on_land_roads_avoid_the_sea(self):
        from game import worldgen
        water = worldgen.water_mask()
        for c in CITIES:
            self.assertFalse(water[c.y - 3:c.y + 3, c.x - 3:c.x + 3].any(), c.key)
        self.assertEqual(worldgen.roads_cross_sea(), [])


class MapScreenTest(unittest.TestCase):
    def test_drag_click_and_panels(self):
        os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
        os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
        import pygame
        from game.assets import ensure_unit_sheets
        from game.mapview import WorldMapScreen
        from game.render import Renderer
        from game.sim import H, W
        pygame.init()
        pygame.display.set_mode((W, H))
        m = WorldMapScreen(Renderer(ensure_unit_sheets()))
        surf = pygame.Surface((W, H))

        def ev(kind, pos, **kw):
            return pygame.event.Event(kind, pos=pos, **kw)

        cam0 = list(m.cam)
        m.handle(ev(pygame.MOUSEBUTTONDOWN, (200, 120), button=1), (200, 120))
        m.handle(ev(pygame.MOUSEMOTION, (150, 90), buttons=(1, 0, 0), rel=(-50, -30)), (150, 90))
        m.handle(ev(pygame.MOUSEBUTTONUP, (150, 90), button=1), (150, 90))
        self.assertEqual((m.cam[0] - cam0[0], m.cam[1] - cam0[1]), (50, 30))
        self.assertIsNone(m.selected)                         # a drag is not a click
        c = CITY["kronholm"]
        m.cam = [c.x - W / 2, c.y - H / 2]
        pos = (W // 2, H // 2 + 5)                            # on the name ribbon
        m.handle(ev(pygame.MOUSEBUTTONDOWN, pos, button=1), pos)
        m.handle(ev(pygame.MOUSEBUTTONUP, pos, button=1), pos)
        self.assertEqual(m.selected, "kronholm")
        m.update(0.1, pos)
        m.draw(surf)
        pos = (W // len(ALL_FACTIONS) * 8 + 5, H - 10)        # goblins on the faction bar
        m.handle(ev(pygame.MOUSEBUTTONDOWN, pos, button=1), pos)
        self.assertEqual(m.faction_panel, "goblin")
        m.update(0.1, pos)
        m.draw(surf)
        m.handle(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE), pos)
        self.assertIsNone(m.faction_panel)
        b = next(b for b in m.buttons if b.action == "diplomacy")
        m.handle(ev(pygame.MOUSEBUTTONDOWN, b.rect.center, button=1), b.rect.center)
        self.assertTrue(m.diplomacy)
        x0, y0 = m._diplo_origin()
        m.update(0.1, (x0 + m.CELL_W + 3, y0 + 3))
        self.assertEqual(m.hover_rel, (ALL_FACTIONS[0].key, ALL_FACTIONS[1].key))
        m.draw(surf)
        b = next(b for b in m.buttons if b.action == "battle")
        self.assertEqual(m.handle(ev(pygame.MOUSEBUTTONDOWN, b.rect.center, button=1), b.rect.center), "battle")


def _pygame_ui():
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    import pygame
    from game.assets import ensure_unit_sheets
    from game.hires import HIRES
    from game.render import Renderer
    from game.sim import H, W
    pygame.init()
    pygame.display.set_mode((W, H))
    HIRES.sync = True
    return pygame, Renderer(ensure_unit_sheets())


class CampaignScreensTest(unittest.TestCase):
    def test_army_hire_card_and_zoom(self):
        pygame, renderer = _pygame_ui()
        from game.campaign import Campaign
        from game.hires import HIRES
        from game.mapview import WorldMapScreen
        from game.sim import H, W
        m = WorldMapScreen(renderer, campaign=Campaign("aldern"))
        surf = pygame.Surface((W, H))

        def click(pos, button=1):
            m.update(0.05, pos)
            m.draw(surf)
            m.handle(pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=pos, button=button), pos)
            m.handle(pygame.event.Event(pygame.MOUSEBUTTONUP, pos=pos, button=button), pos)

        m.selected = FACTION["north"].capital                       # a foreign city: no buttons
        self.assertEqual(m._city_buttons(), [])
        m.selected = "kronholm"
        actions = [a for _, a in m._city_buttons()]
        self.assertEqual(actions, ["army", "hire"])
        rect = m._city_buttons()[1][0]
        self.assertLess(rect.right, m._city_panel_rect().x)         # left of the city window
        click(rect.center)
        self.assertEqual(m.window, ("hire", "kronholm"))
        n, gold = len(m.camp.free["kronholm"]), m.camp.gold["aldern"]
        click(m._hire_button(0).center)
        self.assertEqual(len(m.camp.free["kronholm"]), n + 1)
        self.assertLess(m.camp.gold["aldern"], gold)
        m.window = ("army", "kronholm")
        off = m._win_officers()[0].key
        for t in list(m.camp.squads[off]):
            m.camp.unassign(off, t.id)
        click(m._free_rect(0).center)                               # free warrior -> officer's squad
        self.assertEqual(len(m.camp.squads[off]), 1)
        click(m._slot_rect(0).center)                               # slot -> back to the city
        self.assertEqual(len(m.camp.squads[off]), 0)
        m.update(0.05, (0, 0))
        m.draw(surf)
        face = next(r for r, k in m.cards.hits if k == off)
        click(face.center)                                          # the officer's face opens his card
        self.assertEqual(m.cards.key, off)
        m.update(0.05, (0, 0))
        m.draw(surf)
        self.assertTrue(HIRES.items)                                # painted portrait + stat web registered
        m.handle(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RIGHT), (0, 0))
        self.assertNotEqual(m.cards.key, off)
        m.handle(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE), (0, 0))
        self.assertIsNone(m.cards.key)
        self.assertIsNotNone(m.window)
        m.window = None
        m.selected = None
        m.handle(pygame.event.Event(pygame.MOUSEWHEEL, x=0, y=-1), (240, 140))
        self.assertEqual(m.zoom, 0.5)
        m.handle(pygame.event.Event(pygame.MOUSEWHEEL, x=0, y=-1), (240, 140))
        m.handle(pygame.event.Event(pygame.MOUSEWHEEL, x=0, y=-1), (240, 140))
        self.assertEqual(m.zoom, 0.25)                              # no further than the whole map
        for _ in range(4):
            m.handle(pygame.event.Event(pygame.MOUSEWHEEL, x=0, y=1), (240, 140))
        self.assertEqual(m.zoom, 1.0)                               # never closer than 1:1
        m.update(0.05, (240, 140))
        m.draw(surf)

    def test_faction_select(self):
        pygame, renderer = _pygame_ui()
        from game.select import SelectScreen
        from game.sim import H, W
        surf = pygame.Surface((W, H))
        for i, expect in ((1, "sylvan"), (8, None)):
            sel = SelectScreen(renderer)
            pos = sel._banner_rect(i).center
            sel.update(0.05, pos)
            sel.draw(surf)
            self.assertEqual(sel.focus, i)
            sel.handle(pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=pos, button=1), pos)
            for _ in range(40):
                sel.update(0.05, pos)
                sel.draw(surf)
            self.assertEqual(sel.result, ("play", expect))          # 8 = the Chronicler (spectator)
        sel = SelectScreen(renderer)
        sel.update(0.05, (5, 5))
        sel.draw(surf)
        leader = sel._leader_rect().center
        sel.handle(pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=leader, button=1), leader)
        self.assertEqual(sel.cards.key, "aldern:0")                 # the leader's portrait opens his card
        sel.draw(surf)
        self.assertEqual(sel.handle(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE), (5, 5)), None)
        self.assertEqual(sel.handle(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE), (5, 5)), "quit")


if __name__ == "__main__":
    unittest.main()
