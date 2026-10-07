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


if __name__ == "__main__":
    unittest.main()
