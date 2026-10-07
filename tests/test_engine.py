import json
import os
import tempfile
import unittest

from pixelforge import color
from pixelforge.anim import Animation
from pixelforge.canvas import Canvas, Grid
from pixelforge.rig import Blob, Limb, Pose, Rig
from pixelforge.shading import Ink, Material, PartBuffer, Shader
from pixelforge.text import draw_text, text_width


class ColorTest(unittest.TestCase):
    def test_hex_roundtrip(self):
        self.assertEqual(color.rgba("#e43b44"), (228, 59, 68, 255))
        self.assertEqual(color.rgba("fff"), (255, 255, 255, 255))
        self.assertEqual(color.to_hex((228, 59, 68, 255)), "#e43b44")

    def test_ramp_is_ordered_and_hue_shifted(self):
        r = color.ramp("#3e8948")  # green
        lum = [color.luminance(c) for c in r]
        self.assertEqual(lum, sorted(lum))
        h_dark, _, _ = color.to_hsv(r[0])
        h_base, _, _ = color.to_hsv(r[2])
        h_light, _, _ = color.to_hsv(r[4])
        self.assertGreater(h_dark, h_base)   # shadows drift toward blue (higher hue)
        self.assertLess(h_light, h_base)     # lights drift toward yellow (lower hue)


class CanvasTest(unittest.TestCase):
    def test_line_endpoints_and_no_doubles(self):
        g = Grid(10, 10)
        g.line(0, 0, 9, 4, 1)
        pts = [(x, y) for x, y, _ in g.items()]
        self.assertIn((0, 0), pts)
        self.assertIn((9, 4), pts)
        self.assertEqual(len(pts), 10)  # one pixel per column for a shallow line

    def test_ellipse_symmetric(self):
        g = Grid(16, 16)
        g.ellipse(8, 8, 3, 3, 1)
        for x, y, _ in list(g.items()):
            self.assertTrue(g.filled(15 - x, y))
            self.assertTrue(g.filled(x, 15 - y))
        self.assertEqual(g.bbox(), (5, 5, 10, 10))

    def test_capsule_width_constant(self):
        g = Grid(20, 20)
        g.capsule(5, 2, 5, 17, 2, 1)
        for y in range(4, 16):
            self.assertEqual(sum(g.filled(x, y) for x in range(20)), 2)

    def test_palette_swap_and_flip(self):
        c = Canvas(3, 1)
        c.set(0, 0, "#ff0000")
        self.assertEqual(c.flipped().get(2, 0), (255, 0, 0, 255))
        self.assertEqual(c.replace({"#ff0000": "#00ff00"}).get(0, 0), (0, 255, 0, 255))


class ShaderTest(unittest.TestCase):
    def setUp(self):
        self.mat = Material.of("m", "#e43b44")
        self.buf = PartBuffer(16, 16)
        self.buf.ellipse(8, 8, 4, 4, Ink(self.mat, "a"))

    def test_light_side_brighter(self):
        img = Shader(outline="none").render(self.buf)
        tl = color.luminance(img.get(5, 5))
        br = color.luminance(img.get(10, 10))
        self.assertGreater(tl, br)

    def test_selout_uses_material_dark(self):
        img = Shader(outline="selout").render(self.buf)
        self.assertEqual(img.get(8, 12), self.mat.color(0))   # shadow side: darkest ramp step
        self.assertGreater(color.luminance(img.get(8, 3)),      # lit side: lighter outline
                           color.luminance(img.get(8, 12)))
        self.assertIsNone(img.get(0, 0))

    def test_outline_no_corners(self):
        img = Shader(outline="color", corners=False).render(self.buf)
        filled = sum(1 for _ in img.items())
        img2 = Shader(outline="color", corners=True).render(self.buf)
        self.assertGreater(sum(1 for _ in img2.items()), filled)


class RigTest(unittest.TestCase):
    def make(self):
        m = Material.of("m", "#8b9bb4")
        rig = Rig(32, 32, (16, 10))
        rig.bone("root", None, 0)
        rig.bone("arm", "root", 10, world=90, material=m, shapes=[Limb(width=2)])
        rig.bone("hand", "arm", 0, material=m, shapes=[Blob(rx=2, ry=2, t=0)], ground=True)
        return rig

    def test_forward_kinematics(self):
        st = self.make().solve(Pose(body={"arm": 0}))
        self.assertAlmostEqual(st["arm"].end[0], 26)
        self.assertAlmostEqual(st["arm"].end[1], 10)

    def test_ground_lock(self):
        rig = self.make()
        for a in (60, 90, 120):
            img = rig.render(Pose(body={"arm": a}, ground=28))
            box = img.bbox()
            self.assertEqual(box[3], 29)  # body pixel on row 28 + 1px outline

    def test_lerp_midpoint(self):
        rig = self.make()
        p = rig.lerp(Pose(body={"arm": 0}), Pose(body={"arm": 90}), 0.5)
        self.assertAlmostEqual(rig.solve(p)["arm"].angle, 45)


class UnitsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from pixelforge.units.humanoid import PRESETS, build_humanoid, ground_row
        cls.spec = PRESETS["knight"]
        cls.sprite = build_humanoid(cls.spec, shadow=False)
        cls.ground = ground_row(cls.spec)

    def test_animation_set(self):
        for name in ("idle", "walk", "attack", "cast", "hurt", "death", "vanish"):
            self.assertIn(name, self.sprite.animations)
            for f in self.sprite[name].frames[:-1] if name == "vanish" else self.sprite[name].frames:
                self.assertIsNotNone(f.image.bbox(), name)
        self.assertEqual(len(self.sprite["walk"].frames), 8)
        self.assertTrue(any("hit" in f.events for f in self.sprite["attack"].frames))
        self.assertFalse(self.sprite["death"].loop)

    def test_feet_on_ground_while_walking(self):
        for f in self.sprite["walk"].frames:
            self.assertEqual(f.image.bbox()[3], self.ground + 1)

    def test_deterministic(self):
        from pixelforge.units.humanoid import build_humanoid
        again = build_humanoid(self.spec, shadow=False)
        self.assertEqual(again["attack"].frames[2].image.px, self.sprite["attack"].frames[2].image.px)

    def test_creatures(self):
        from pixelforge.units.creatures import BOAR, build_quadruped, build_slime
        for sp in (build_slime(), build_quadruped(BOAR)):
            self.assertIn("walk", sp.animations)
            self.assertIn("death", sp.animations)


class ExportTest(unittest.TestCase):
    def test_sheet_json(self):
        from pixelforge.anim import Sprite
        from pixelforge.export import save_gif, save_sheet
        sp = Sprite("t", 8, 8)
        a = Animation("blink")
        for i in range(3):
            c = Canvas(8, 8)
            c.set(i, i, "#ffffff")
            a.add(c, 50 + i, ["e"] if i == 1 else [])
        sp.add(a)
        with tempfile.TemporaryDirectory() as d:
            meta = save_sheet(sp, os.path.join(d, "t.png"))
            with open(os.path.join(d, "t.json")) as fh:
                self.assertEqual(json.load(fh), meta)
            self.assertEqual(meta["animations"]["blink"]["frames"][1]["x"], 8)
            self.assertEqual(meta["animations"]["blink"]["frames"][1]["events"], ["e"])
            save_gif(a, os.path.join(d, "t.gif"))
            self.assertTrue(os.path.getsize(os.path.join(d, "t.gif")) > 0)


class AssetsTest(unittest.TestCase):
    def test_tiles_full_and_items(self):
        from pixelforge.assets import items, tiles
        for name, a in tiles.tileset().animations.items():
            img = a.frames[0].image
            self.assertEqual(sum(1 for _ in img.items()), 256, name)  # tiles are opaque
        self.assertGreater(len(items.item_set().animations), 5)

    def test_text(self):
        c = Canvas(40, 6)
        end = draw_text(c, "HP 10", 0, 0, "#ffffff")
        self.assertEqual(end, text_width("HP 10"))
        self.assertEqual(text_width("Ж"), 5)


if __name__ == "__main__":
    unittest.main()
