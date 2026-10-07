"""Side-view humanoid units (32x32 by default) with a full animation set.

    from pixelforge.units.humanoid import HumanoidSpec, build_humanoid
    sprite = build_humanoid(HumanoidSpec(name="knight", top="#8b9bb4", top_shiny=True,
                                         helmet="#c0cbdc", weapon="sword", shield="#a22633"))

Animations: ``idle`` ``walk`` ``attack`` ``cast`` ``hurt`` ``death`` ``vanish``.
Everything is described by :class:`HumanoidSpec` (colors, gear, build), so
new unit types are a few lines of data.  For anything more exotic build a
:class:`~pixelforge.rig.Rig` directly - see :func:`build_rig` as an example.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field, replace
from typing import Dict, List, Optional

from .. import fx
from ..anim import Animation, Sprite, from_poses
from ..color import ColorLike, mix, rgba
from ..rig import Blob, Custom, Limb, Pixels, Poly, Pose, Rig
from ..shading import BASE, HIGHLIGHT, LIGHT, OUTLINE, SHADOW, Material, Shader


@dataclass
class HumanoidSpec:
    name: str = "hero"
    skin: ColorLike = "#e8b796"
    eye: ColorLike = "#181425"
    hair: Optional[ColorLike] = "#733e39"
    hair_style: str = "short"            # short | long | spiky | none
    beard: Optional[ColorLike] = None
    top: ColorLike = "#124e89"           # tunic / armor / robe
    top_shiny: bool = False              # metal armor
    sleeves: Optional[ColorLike] = None  # default: skin for cloth, top for armor
    belt: Optional[ColorLike] = "#3e2731"
    bottom: ColorLike = "#3a4466"
    boots: ColorLike = "#3e2731"
    robe: bool = False                   # long robe instead of trousers
    helmet: Optional[ColorLike] = None
    helmet_style: str = "cap"            # cap | horned | hood | crown
    cape: Optional[ColorLike] = None
    weapon: Optional[str] = "sword"      # sword | axe | spear | staff | dagger | bow | crossbow | mace | hammer | None
    weapon_color: ColorLike = "#c0cbdc"
    handle_color: ColorLike = "#733e39"
    magic: ColorLike = "#2ce8f5"         # staff orb, spell sparks
    string_color: ColorLike = "#ead4aa"  # bow string / fletching
    shield: Optional[ColorLike] = None
    build: str = "normal"                # normal | stocky | slim
    size: int = 32
    outline: str = "selout"


# --- rig construction ---------------------------------------------------------

def _materials(spec: HumanoidSpec) -> Dict[str, Material]:
    m = {
        "skin": Material.of("skin", spec.skin),
        "eye": Material.of("eye", spec.eye, flat=True),
        "top": Material.of("top", spec.top, shiny=spec.top_shiny),
        "bottom": Material.of("bottom", spec.bottom),
        "boots": Material.of("boots", spec.boots),
        "steel": Material.of("steel", spec.weapon_color, shiny=True),
        "wood": Material.of("wood", spec.handle_color),
        "magic": Material.of("magic", spec.magic, shiny=True),
    }
    sleeves = spec.sleeves if spec.sleeves is not None else (spec.top if spec.top_shiny else spec.skin)
    m["sleeves"] = Material.of("sleeves", sleeves, shiny=spec.top_shiny)
    m["arm"] = Material.of("arm", spec.top if spec.top_shiny else spec.top)
    for k in ("hair", "beard", "belt", "helmet", "cape", "shield"):
        c = getattr(spec, k)
        if c is not None:
            m[k] = Material.of(k, c, shiny=k in ("helmet", "shield"))
    m["glow"] = Material.from_ramp("glow", [mix(spec.magic, "#ffffff", t) for t in (0, .2, .45, .7, .9)], flat=False)
    return m


# crisp unit look: near-black silhouette (tinted by the material), no lightened outline
# on the lit side, no single-pixel shading noise - reads clearly at 1x on any background
CRISP = dict(selout_lit_mix=0.0, outline_darken=0.6, despeckle=True)


def build_rig(spec: HumanoidSpec) -> Rig:
    s = spec.size / 32.0
    m = _materials(spec)
    shader = Shader(outline=spec.outline, **CRISP)
    fw, fh = frame_size(spec)
    rig = Rig(fw, fh, (fw // 2 - 1, ground_row(spec) - 10 * s), shader)

    torso_len = {"stocky": 6.5, "slim": 7.5}.get(spec.build, 7.0) * s
    torso_w = {"stocky": 7, "slim": 5}.get(spec.build, 6) * s
    leg_w = round((3 if spec.build != "slim" else 2) * s)
    arm_w = round((2 if spec.build != "stocky" else 3) * s)

    rig.bone("root", None, 0)
    # torso (+ hips in trouser color)
    torso = rig.bone("torso", "root", torso_len, world=-90, material=m["top"], z=10, shapes=[
        Limb(width=torso_w, t0=0.2, t1=0.92),
        Blob(material=m["bottom"] if not spec.robe else m["top"], rx=torso_w / 2, ry=2, t=0.1, z=-0.1),
    ])
    if spec.belt is not None:
        torso.shapes.append(Limb(material=m["belt"], width=torso_w, t0=0.22, t1=0.22, z=0.05,
                                 group="belt", level=BASE))
    if spec.robe:
        torso.shapes.append(Poly(material=m["top"], z=0.2, group="torso", points=[
            (-torso_w / 2, -torso_len * 0.3), (torso_w / 2, -torso_len * 0.3),
            (torso_w / 2 + 2.5, 9), (-torso_w / 2 - 1.5, 9)]))

    rig.bone("neck", "torso", 1.5 * s, angle=0)
    head = rig.bone("head", "neck", 0, angle=0, material=m["skin"], z=20, shapes=[
        Blob(rx=4 * s, ry=3.5 * s, t=0, offset=(0.5 * s, -3.5 * s)),
        Pixels(material=m["eye"], level=BASE, z=0.5, outline=False, points=[(2.6 * s, -3.6 * s)]),
        Pixels(level=SHADOW, z=0.4, outline=False, points=[(4.1 * s, -2.3 * s)]),  # nose shade
    ])
    if spec.hair is not None and spec.hair_style != "none" and spec.helmet_style != "hood":
        hm = m["hair"]
        hs = [Blob(material=hm, rx=4.2 * s, ry=2.2 * s, t=0, offset=(-0.2 * s, -6 * s), z=0.3, group="hair"),
              Blob(material=hm, rx=2 * s, ry=3 * s, t=0, offset=(-2.3 * s, -4 * s), z=0.3, group="hair")]
        if spec.hair_style == "long":
            hs.append(Custom(material=hm, z=-1, group="hair_back", fn=lambda buf, st, ink: buf.capsule(
                *_snapped(st.point(0, (-3 * s, -4 * s))), *_snapped(st.point(0, (-3.5 * s, 2 * s))), 3, ink)))
        if spec.hair_style == "spiky":
            hs.append(Poly(material=hm, z=0.35, group="hair", points=[
                (-4 * s, -6 * s), (-3 * s, -10 * s), (-1 * s, -7.5 * s), (0.5 * s, -10.5 * s),
                (2 * s, -7.5 * s), (4 * s, -9 * s), (4 * s, -6 * s)]))
        head.shapes.extend(hs)
    if spec.beard is not None:
        head.shapes.append(Poly(material=m["beard"], z=0.45, group="beard", points=[
            (0.5 * s, -2 * s), (4.5 * s, -2.2 * s), (4 * s, 1 * s), (1.5 * s, 2 * s)]))
    if spec.helmet is not None:
        hm = m["helmet"]
        if spec.helmet_style == "hood":
            head.shapes.append(Blob(material=hm, rx=4.8 * s, ry=4.4 * s, t=0, offset=(-0.4 * s, -4.1 * s),
                                    z=-0.2, group="helmet"))
            head.shapes.append(Poly(material=hm, z=0.3, group="helmet", points=[
                (-4.5 * s, -6 * s), (4.5 * s, -7.5 * s), (5 * s, -6 * s), (-1 * s, -3 * s), (-5 * s, -3 * s)]))
        else:
            head.shapes.append(Blob(material=hm, rx=4.5 * s, ry=2.3 * s, t=0, offset=(0.3 * s, -6.1 * s),
                                    z=0.6, group="helmet"))
            if spec.helmet_style == "horned":
                horn = Material.of("horn", "#ead4aa")
                head.shapes.append(Poly(material=horn, z=0.55, group="horn", points=[
                    (-3 * s, -6.5 * s), (-6.5 * s, -10 * s), (-5.5 * s, -7 * s), (-4 * s, -5 * s)]))
                head.shapes.append(Poly(material=horn, z=0.55, group="horn2", points=[
                    (3 * s, -7 * s), (5.5 * s, -10.5 * s), (6 * s, -7.5 * s), (4.5 * s, -5.5 * s)]))
            elif spec.helmet_style == "crown":
                gold = Material.of("gold", "#feae34", shiny=True)
                head.shapes.append(Poly(material=gold, z=0.7, group="crown", points=[
                    (-3.5 * s, -6 * s), (-3.5 * s, -9.5 * s), (-1.5 * s, -7.5 * s), (0.5 * s, -10 * s),
                    (2.5 * s, -7.5 * s), (4.5 * s, -9.5 * s), (4.5 * s, -6 * s)]))

    # arms: back (far, darker, behind torso) and front
    for side, z, depth in (("b", 4, -1), ("f", 30, 0)):
        rig.bone(f"upper_{side}", "torso", 4 * s, world=90, attach=0.85, z=z, depth=depth,
                 material=m["arm"], group=f"arm_{side}", shapes=[Limb(width=arm_w + (1 if spec.top_shiny else 0))])
        rig.bone(f"fore_{side}", f"upper_{side}", 4 * s, world=75, z=z + 0.1, depth=depth,
                 material=m["sleeves"], group=f"arm_{side}", shapes=[Limb(width=arm_w)])
        rig.bone(f"hand_{side}", f"fore_{side}", 0, world=75, z=z + 1, depth=depth,
                 material=m["skin"], group=f"hand_{side}", shapes=[Blob(rx=1.5 * s, ry=1.5 * s, t=0)])

    # legs
    for side, z, depth in (("b", 3, -1), ("f", 12, 0)):
        rig.bone(f"thigh_{side}", "root", 5 * s, world=90, z=z, depth=depth, material=m["bottom"],
                 group=f"leg_{side}", shapes=[Limb(width=leg_w)])
        rig.bone(f"shin_{side}", f"thigh_{side}", 5 * s, world=90, z=z + 0.1, depth=depth, material=m["bottom"],
                 group=f"leg_{side}", shapes=[Limb(width=leg_w, t1=0.5),
                                              Limb(material=m["boots"], width=leg_w, t0=0.45, group=f"boot_{side}")])
        rig.bone(f"foot_{side}", f"shin_{side}", 2.5 * s, world=0, z=z + 0.2, depth=depth, ground=True,
                 material=m["boots"], group=f"boot_{side}", shapes=[Limb(width=round(2 * s), t0=-0.2)])

    if spec.cape is not None:
        rig.bone("cape", "torso", 9 * s, world=100, attach=0.9, offset=(-1.5, 0), z=1, material=m["cape"],
                 shapes=[Poly(points=[(-1, 0), (1.5, 0), (2.5, 9 * s), (-3.5, 8.5 * s)])])

    if spec.shield is not None:
        rig.bone("shield", "fore_b", 0, world=0, attach=0.7, z=16, material=m["shield"], shapes=[
            Blob(rx=2.5, ry=4.5, t=0, offset=(1.5, 0), rotate=False),
            Pixels(level=HIGHLIGHT, z=0.2, outline=False, points=[(1.5, -0.5)]),
        ])

    _add_weapon(rig, spec, m, s)
    return rig


def _snapped(p):
    return (math.floor(p[0]) + 0.5, math.floor(p[1]) + 0.5)


def _add_weapon(rig: Rig, spec: HumanoidSpec, m: Dict[str, Material], s: float) -> None:
    w = spec.weapon
    if w is None:
        return
    z = 30.5  # between front forearm (30.1) and front hand (31)
    if w in ("sword", "dagger"):
        L = (11 if w == "sword" else 6) * s
        rig.bone("weapon", "hand_f", L, world=-90, z=z, material=m["steel"], shapes=[
            Limb(width=1, t0=0.2, t1=1.0),
            Limb(material=m["wood"], width=1, t0=-0.15, t1=0.1, group="hilt"),
        ])
        rig.bone("guard", "weapon", 1.5, world=0, attach=0.17, z=z + 0.2, material=m["wood"] if w == "dagger" else m["steel"],
                 group="guard", shapes=[Limb(width=1, t0=-1.0, t1=1.0)])
    elif w == "axe":
        L = 10 * s
        rig.bone("weapon", "hand_f", L, world=-90, z=z, material=m["wood"], shapes=[
            Limb(width=1, t0=-0.15, t1=1.0),
            Poly(material=m["steel"], group="axehead", z=0.2, points=[
                (0.5, -L + 0.5), (3.5, -L - 1.5), (4.5, -L + 2), (3.5, -L + 5.5), (0.5, -L + 3.5)]),
        ])
    elif w == "spear":
        L = 15 * s
        rig.bone("weapon", "hand_f", L, world=-90, z=z, material=m["wood"], shapes=[
            Limb(width=1, t0=-0.25, t1=0.9),
            Poly(material=m["steel"], group="tip", z=0.2, points=[
                (-1.5, -L + 2.5), (0.5, -L - 2.5), (2.5, -L + 2.5), (0.5, -L + 3.5)]),
        ])
    elif w == "staff":
        L = 13 * s
        rig.bone("weapon", "hand_f", L, world=-90, z=z, material=m["wood"], shapes=[
            Limb(width=1, t0=-0.35, t1=0.9),
            Blob(material=m["magic"], rx=1.5, ry=1.5, t=1.0, z=0.3, group="orb"),
        ])
    elif w == "bow":
        L = BOW_LEN
        string = Material.of("string", spec.string_color, flat=True)
        rig.bone("weapon", "hand_f", L, world=-90, z=z, material=m["wood"], shapes=[
            Custom(fn=lambda buf, st, ink: _draw_bow(buf, st, ink)),
        ])
        # straight string while not drawn; hidden in shooting poses (fx draws the pulled one)
        rig.bone("bowstring", "weapon", 0, attach=0.0, z=z - 0.2, material=string, group="string",
                 shapes=[Custom(level=BASE, outline=False,
                                fn=lambda buf, st, ink: _draw_string(buf, st, ink))])
    elif w == "mace":
        L = 8 * s
        rig.bone("weapon", "hand_f", L, world=-90, z=z, material=m["wood"], shapes=[
            Limb(width=1, t0=-0.2, t1=0.85),
            Blob(material=m["steel"], rx=2, ry=2, t=1.0, z=0.2, group="macehead"),
            Pixels(material=m["steel"], level=LIGHT, z=0.3, group="spikes", t=1.0,
                   points=[(0, -2.6), (2.4, 0), (-2.6, 0)]),
        ])
    elif w == "hammer":
        L = 11 * s
        rig.bone("weapon", "hand_f", L, world=-90, z=z, material=m["wood"], shapes=[
            Limb(width=1, t0=-0.2, t1=0.9),
            Poly(material=m["steel"], group="hammerhead", z=0.2, points=[
                (-3, -L - 1.5), (4, -L - 1.5), (4, -L + 2.5), (-3, -L + 2.5)]),
        ])
    elif w == "crossbow":
        L = 9.0
        string = Material.of("string", spec.string_color, flat=True)
        rig.bone("weapon", "hand_f", L, world=0, z=z, material=m["wood"], shapes=[
            Limb(width=2, t0=-0.35, t1=0.95),
            Custom(material=m["steel"], group="prod", z=0.3, fn=lambda buf, st, ink: _draw_prod(buf, st, ink)),
            Custom(material=string, group="string", z=0.25, level=BASE, outline=False,
                   fn=lambda buf, st, ink: _draw_xbow_string(buf, st, ink)),
        ])
        rig.bone("bolt", "weapon", 6, world=0, attach=0.35, offset=(0, -1), z=z + 0.4, material=m["steel"],
                 group="bolt", shapes=[Limb(width=1, t0=0.0, t1=1.0)])
    else:
        raise ValueError(f"unknown weapon {w!r}")


def _prod_points(st):
    pts = []
    for i in range(7):
        u = -1 + i / 3
        pts.append(st.point(0.92, (1.6 * (1 - u * u), 5.0 * u)))
    return pts


def _draw_prod(buf, st, ink):
    pts = _prod_points(st)
    for a, b in zip(pts, pts[1:]):
        buf.line(math.floor(a[0]), math.floor(a[1]), math.floor(b[0]), math.floor(b[1]), ink)


def _draw_xbow_string(buf, st, ink):
    pts = _prod_points(st)
    latch = st.point(0.4)
    for tip in (pts[0], pts[-1]):
        buf.line(math.floor(tip[0]), math.floor(tip[1]), math.floor(latch[0]), math.floor(latch[1]), ink)


BOW_LEN = 13.0     # tip to tip
BOW_BULGE = 3.0    # how far the bow limbs bow forward of the string


def bow_tips(st) -> tuple:
    """(top, bottom, grip) of a bow bone state; the bone runs tip-to-tip through the grip."""
    top = st.point(0.5, (-BOW_BULGE, 0))
    bot = st.point(-0.5, (-BOW_BULGE, 0))
    return top, bot, st.point(0.0)


def _draw_bow(buf, st, ink):
    pts = []
    for i in range(9):
        u = -1 + i / 4
        pts.append(st.point(u * 0.5, (BOW_BULGE * (1 - u * u) - BOW_BULGE, 0)))
    for a, b in zip(pts, pts[1:]):
        buf.line(math.floor(a[0]), math.floor(a[1]), math.floor(b[0]), math.floor(b[1]), ink)


def _draw_string(buf, st, ink):
    # the string bone sits at the bow's grip and shares its orientation
    top = st.point(0, (-BOW_BULGE, -BOW_LEN / 2))
    bot = st.point(0, (-BOW_BULGE, BOW_LEN / 2))
    buf.line(math.floor(top[0]), math.floor(top[1]), math.floor(bot[0]), math.floor(bot[1]), ink)


# --- poses --------------------------------------------------------------------

def frame_size(spec: HumanoidSpec):
    """Frames are wider/taller than the body so weapons, smears and the
    death fall never get clipped: 32px body -> 48x40 frame."""
    return round(spec.size * 1.5), round(spec.size * 1.25)


def ground_row(spec: HumanoidSpec) -> int:
    """Row the feet stand on (outline below it, one spare row for the shadow)."""
    return frame_size(spec)[1] - 3


def _base(spec: HumanoidSpec) -> Pose:
    has_w = spec.weapon is not None
    return Pose(body={
        "torso": -88,
        "upper_f": 75 if has_w else 95, "fore_f": 20 if has_w else 70,
        "upper_b": 100, "fore_b": 70 if spec.shield is None else 20,
        "thigh_f": 80, "shin_f": 95, "thigh_b": 100, "shin_b": 100,
        "foot_f": 0, "foot_b": 0,
        "hand_f": 20, "hand_b": 70,
        "weapon": {"spear": -80, "bow": -75, "crossbow": -35}.get(spec.weapon, -60),
        "cape": 105,
    }, ground=ground_row(spec))


def _with(p: Pose, **body) -> Pose:
    q = p.copy()
    q.body.update(body)
    return q


def idle_poses(spec: HumanoidSpec, rig: Rig) -> List[Pose]:
    base = _base(spec)
    out = []
    for i, b in enumerate((0, 0, 1, 1)):  # chest rises and falls by 1px
        p = _with(base, upper_f=base.body["upper_f"] + 3 * b, upper_b=base.body["upper_b"] - 2 * b,
                  cape=base.body["cape"] + 4 * b)
        p.offsets = {"torso": (0, b)}
        p.duration = 220 if i in (0, 2) else 160
        out.append(p)
    return out


def walk_poses(spec: HumanoidSpec, rig: Rig, frames: int = 8) -> List[Pose]:
    base = _base(spec)
    out = []
    armed = spec.weapon is not None
    for i in range(frames):
        ph = math.tau * i / frames
        sn, cs = math.sin(ph), math.cos(ph)
        tf, tb = 90 - 30 * sn, 90 + 30 * sn
        bend_f = 6 + 50 * max(0.0, cs) ** 1.3
        bend_b = 6 + 50 * max(0.0, -cs) ** 1.3
        amp_f = 10 if armed else 28
        p = _with(base,
                  torso=-84,
                  thigh_f=tf, shin_f=tf + bend_f, thigh_b=tb, shin_b=tb + bend_b,
                  foot_f=min(0, (tf + bend_f - 95) * 0.6) if cs < 0 else 0,
                  foot_b=min(0, (tb + bend_b - 95) * 0.6) if cs > 0 else 0,
                  upper_f=base.body["upper_f"] + amp_f * sn,
                  fore_f=base.body["fore_f"] + amp_f * sn,
                  hand_f=base.body["hand_f"] + amp_f * sn,
                  upper_b=90 - 26 * sn, fore_b=(65 if spec.shield is None else 20) - 20 * sn,
                  weapon=base.body["weapon"] + 6 * sn,
                  cape=118 + 6 * abs(cs))
        # foot angles are relative to world while planted, follow the shin while swinging
        for side, swing in (("f", cs > 0), ("b", cs < 0)):
            if swing:
                p.body.pop(f"foot_{side}")
                p.angles[f"foot_{side}"] = -80
        p.duration = 100
        out.append(p)
    return out


def _weapon_tip_angle(rig: Rig, pose: Pose, pivot_bone: str = "upper_f") -> float:
    st = rig.solve(pose)
    if "weapon" not in st:
        return st["hand_f"].angle
    piv = st[pivot_bone].start
    tip = st["weapon"].end
    return math.degrees(math.atan2(tip[1] - piv[1], tip[0] - piv[0]))


def bow_poses(spec: HumanoidSpec, rig: Rig) -> List[Pose]:
    """Nock -> full draw (held: anticipation) -> release (``hit`` = arrow leaves) -> recover."""
    from ..shading import Ink
    base = _base(spec)
    string = Material.of("string", spec.string_color, flat=True)
    shaft = Material.of("shaft", spec.handle_color)
    tip = Material.of("tip", spec.weapon_color, shiny=True)
    stance = dict(thigh_f=72, shin_f=88, thigh_b=108, shin_b=108, foot_f=0, foot_b=0)
    aim = dict(torso=-92, upper_f=-5, fore_f=-5, hand_f=-5, weapon=-92, **stance)

    def pulled(arrow: bool):
        def fx_(buf, states, rig_):
            top, bot, grip = bow_tips(states["weapon"])
            hx, hy = states["hand_b"].start
            ink = Ink(string, "string", 30.3, level=BASE, outline=False, contour=False)
            buf.line(math.floor(top[0]), math.floor(top[1]), math.floor(hx), math.floor(hy), ink)
            buf.line(math.floor(bot[0]), math.floor(bot[1]), math.floor(hx), math.floor(hy), ink)
            if arrow:
                y = math.floor(hy)
                buf.line(math.floor(hx), y, math.floor(grip[0]) + 3, y, Ink(shaft, "arrow", 32, level=LIGHT))
                buf.plot(math.floor(grip[0]) + 4, y, Ink(tip, "arrowtip", 32, level=HIGHLIGHT))
                buf.plot(math.floor(hx) - 1, y - 1, Ink(string, "fletch", 32, level=BASE))
                buf.plot(math.floor(hx) - 1, y + 1, Ink(string, "fletch", 32, level=BASE))
        return fx_

    nock = _with(base, upper_b=10, fore_b=-10, hand_b=0, **aim)
    nock.hidden, nock.fx, nock.duration = frozenset({"bowstring"}), [pulled(True)], 160
    draw = _with(base, upper_b=165, fore_b=-15, hand_b=0, **aim)
    draw.body["torso"] = -95
    draw.hidden, draw.fx, draw.duration = frozenset({"bowstring"}), [pulled(True)], 320
    release = _with(base, upper_b=190, fore_b=200, hand_b=180, **aim)
    release.duration, release.events = 70, ["hit"]
    follow = release.copy(duration=180)
    follow.body.update(upper_b=175, fore_b=170)
    settle = rig.lerp(follow, base, 0.5)
    settle.ground, settle.duration = base.ground, 140
    return [nock, draw, release, follow, settle]


def crossbow_poses(spec: HumanoidSpec, rig: Rig) -> List[Pose]:
    """Shoulder & aim (held) -> release (``hit``) with recoil -> crank the string back -> settle."""
    base = _base(spec)
    stance = dict(thigh_f=72, shin_f=88, thigh_b=108, shin_b=108, foot_f=0, foot_b=0)
    aim = _with(base, torso=-90, upper_f=-2, fore_f=-2, hand_f=0, weapon=0,
                upper_b=40, fore_b=-15, hand_b=0, **stance)
    aim.duration = 300
    fire = _with(aim, torso=-96, weapon=-10, hand_f=-10)
    fire.shift, fire.duration, fire.events = (-1, 0), 70, ["hit"]
    fire.hidden = frozenset({"bolt"})
    crank1 = _with(base, torso=-80, upper_f=50, fore_f=60, hand_f=60, weapon=70,
                   upper_b=70, fore_b=10, hand_b=10, **stance)
    crank1.hidden, crank1.duration = frozenset({"bolt"}), 200
    crank2 = _with(crank1, upper_b=100, fore_b=40)
    crank2.hidden, crank2.duration = frozenset({"bolt"}), 200
    settle = base.copy(duration=140)
    return [aim, fire, crank1, crank2, settle]


def fist_poses(spec: HumanoidSpec, rig: Rig) -> List[Pose]:
    """Unarmed jab: chamber the fist (held) -> straight punch (``hit``) -> recoil."""
    base = _base(spec)
    stance = dict(thigh_f=62, shin_f=82, thigh_b=112, shin_b=118, foot_f=0, foot_b=0)
    guard = _with(base, torso=-95, upper_f=120, fore_f=-40, hand_f=-40, upper_b=60, fore_b=-60, hand_b=-60, **stance)
    guard.shift, guard.duration = (-1, 0), 180
    jab = _with(guard, torso=-72, upper_f=-5, fore_f=-5, hand_f=0, upper_b=110, fore_b=-20)
    jab.shift, jab.duration, jab.events = (2, 0), 160, ["hit"]

    def streak(buf, states, rig_):
        from ..shading import Ink
        hx, hy = states["hand_f"].start
        mat = Material.of("swish", "#ffffff", flat=True)
        ink = Ink(mat, "swish", 50, level=BASE, contour=False, outline=False)
        for dy in (-1, 1):
            buf.line(math.floor(hx) - 8, math.floor(hy) + dy, math.floor(hx) - 3, math.floor(hy) + dy, ink)
    jab.fx = [streak]
    hold = jab.copy(fx=[], events=[], duration=120)
    recover = rig.lerp(hold, base, 0.5)
    recover.ground, recover.duration = base.ground, 120
    return [guard, jab, hold, recover]


def attack_poses(spec: HumanoidSpec, rig: Rig) -> List[Pose]:
    if spec.weapon == "bow":
        return bow_poses(spec, rig)
    if spec.weapon == "crossbow":
        return crossbow_poses(spec, rig)
    if spec.weapon is None:
        return fist_poses(spec, rig)
    base = _base(spec)
    m = _materials(spec)
    smear_mat = Material.from_ramp("smear", [mix(spec.weapon_color, "#ffffff", t) for t in (0, .3, .55, .8, 1)])
    legs = dict(thigh_f=65, shin_f=85, thigh_b=110, shin_b=115, foot_f=0, foot_b=0)
    if spec.weapon in ("spear",):
        wind = _with(base, torso=-96, upper_f=150, fore_f=170, hand_f=0, weapon=-5,
                     upper_b=60, fore_b=10 if spec.shield else 20, **legs)
        wind.shift, wind.duration = (-1, 0), 220
        thrust = _with(base, torso=-75, upper_f=10, fore_f=0, hand_f=0, weapon=-2,
                       upper_b=110, fore_b=60 if spec.shield is None else 10, **legs)
        thrust.shift, thrust.duration = (3, 0), 60

        def streak(buf, states, rig_, mat=smear_mat):
            st = states["weapon"]
            x0, y0 = st.start
            from ..shading import Ink
            ink = Ink(mat, "smear", 50, level=LIGHT, contour=False)
            for k, dy in enumerate((-1, 1)):
                buf.line(x0 - 11 + 2 * k, y0 + dy, x0 - 4 + 2 * k, y0 + dy, ink)
        thrust.fx = [streak]
        hit = thrust.copy(fx=[], duration=200, events=["hit"])
        hit.shift = (3, 0)
    else:
        overhead = spec.weapon is not None
        wind = _with(base, torso=-100, upper_f=-155, fore_f=-130, hand_f=-140, weapon=-145,
                     upper_b=120, fore_b=100 if spec.shield is None else 30, **legs)
        wind.shift, wind.duration = (-1, 0), 240
        swing = _with(base, torso=-80, upper_f=-20, fore_f=-10, hand_f=-10, weapon=-5,
                      upper_b=95, fore_b=70 if spec.shield is None else 20, **legs)
        swing.shift, swing.duration = (1, 0), 50
        hit = _with(base, torso=-68, upper_f=40, fore_f=45, hand_f=40, weapon=45,
                    upper_b=80, fore_b=60 if spec.shield is None else 10, **legs)
        hit.shift, hit.duration, hit.events = (2, 0), 220, ["hit"]
        if overhead:
            a_sw = _weapon_tip_angle(rig, swing)
            a_hit = _weapon_tip_angle(rig, hit)
            st = rig.solve(swing)
            r1 = math.dist(st["upper_f"].start, st["weapon"].end) + 0.5
            r0 = max(2.0, r1 - 6)

            def pivot(states):
                return states["upper_f"].start
            swing.fx = [fx.smear_arc(pivot, r0, r1, a_sw - 110, a_sw + 5, smear_mat, z=29)]
            hit.fx = [fx.smear_arc(pivot, r1 - 3, r1, a_hit - 60, a_hit - 10, smear_mat, z=29, level=3)]
        thrust = swing
    recover = rig.lerp(hit.copy(fx=[], events=[]), base, 0.5)
    recover.duration = 140
    recover.ground = base.ground
    settle = base.copy(duration=120)
    return [wind, thrust, hit, recover, settle]


def cast_poses(spec: HumanoidSpec, rig: Rig) -> List[Pose]:
    base = _base(spec)
    glow = _materials(spec)["glow"]
    from ..shading import Ink
    out = []
    raise_ = _with(base, torso=-94, upper_f=-25, fore_f=-60, hand_f=-80, weapon=-85,
                   upper_b=30, fore_b=-20, hand_b=-20)
    raise_.duration = 180
    out.append(raise_)
    rnd = random.Random(7)
    for k in range(4):
        p = raise_.copy(duration=90)

        def sparks(buf, states, rig_, k=k, seed=rnd.random()):
            r = random.Random(seed)
            src = states["weapon"].end if "weapon" in states else states["hand_f"].start
            cx, cy = src
            ink_hi = Ink(glow, "spark", 60, level=HIGHLIGHT, contour=False, outline=False)
            ink_lo = Ink(glow, "spark", 60, level=SHADOW, contour=False, outline=False)
            rad = 2 + k * 1.5
            for j in range(8):
                a = j * math.tau / 8 + k * 0.4
                x, y = cx + math.cos(a) * rad, cy + math.sin(a) * rad
                buf.plot(int(x), int(y), ink_hi if (j + k) % 2 else ink_lo)
            buf.circle(math.floor(cx) + 0.5, math.floor(cy) + 0.5, 1.5 if k % 2 else 1.0,
                       Ink(glow, "core", 61, level=HIGHLIGHT, contour=False))
        p.fx = [sparks]
        if k == 2:
            p.events = ["cast"]
        out.append(p)
    back = rig.lerp(raise_, base, 0.6)
    back.ground, back.duration = base.ground, 140
    out.append(back)
    return out


def hurt_poses(spec: HumanoidSpec, rig: Rig) -> List[Pose]:
    base = _base(spec)
    recoil = _with(base, torso=-108, upper_f=150, fore_f=130, upper_b=150, fore_b=140,
                   thigh_f=75, shin_f=100, thigh_b=105, shin_b=120, weapon=-120)
    recoil.shift = (-1, 0)
    flash_frame = recoil.copy(duration=70, post=[fx.flash])
    recoil.duration = 140
    back = rig.lerp(recoil, base, 0.5)
    back.ground, back.duration = base.ground, 110
    return [flash_frame, recoil, back]


def death_poses(spec: HumanoidSpec, rig: Rig) -> List[Pose]:
    base = _base(spec)
    g = base.ground
    recoil = _with(base, torso=-112, upper_f=-150, fore_f=-170, upper_b=-160, fore_b=-175,
                   thigh_f=78, shin_f=110, thigh_b=100, shin_b=125, weapon=-150)
    recoil.shift = (-1, 0)
    hit = recoil.copy(duration=90, post=[fx.flash], events=["hit"])
    recoil.duration = 140
    buckle = _with(recoil, torso=-115, thigh_f=60, shin_f=130, thigh_b=80, shin_b=140)
    buckle.rotation, buckle.duration, buckle.shift = -20, 110, (-2, 0)
    fall = _with(buckle, upper_f=-120, fore_f=-120, upper_b=-140, fore_b=-140)
    fall.rotation, fall.duration, fall.ground_all, fall.shift = -55, 90, True, (-3, 0)
    # body-space angles; rotation -90 turns body "up" (-90) into world "left" (180)
    lie = _with(base, torso=-90, upper_f=-85, fore_f=-80, upper_b=-95, fore_b=-90, hand_f=-80, hand_b=-90,
                thigh_f=90, shin_f=95, thigh_b=92, shin_b=88, foot_f=0, foot_b=0, weapon=-60, cape=-92)
    lie.rotation, lie.ground_all, lie.shift = -90, True, (-2, 0)
    impact = lie.copy(duration=80)
    bounce = lie.copy(duration=80, shift=(-2, -1))
    rest = lie.copy(duration=900, events=["dead"])
    for p in (impact, bounce, rest):
        p.ground = g
    fall.ground = g
    return [hit, recoil, buckle, fall, impact, bounce, rest]


# --- sprite assembly ----------------------------------------------------------

def build_humanoid(spec: HumanoidSpec, shadow: bool = True) -> Sprite:
    rig = build_rig(spec)
    sp = Sprite(spec.name, rig.width, rig.height, (round(rig.origin[0]), ground_row(spec)))

    def finish(anim: Animation) -> Animation:
        return anim.map(lambda img: _shadowed(img, ground_row(spec), rig.origin[0] + 1)) if shadow else anim

    sp.add(finish(from_poses(rig, "idle", idle_poses(spec, rig))))
    sp.add(finish(from_poses(rig, "walk", walk_poses(spec, rig))))
    sp.add(finish(from_poses(rig, "attack", attack_poses(spec, rig), loop=False)))
    sp.add(finish(from_poses(rig, "cast", cast_poses(spec, rig), loop=False)))
    sp.add(finish(from_poses(rig, "hurt", hurt_poses(spec, rig), loop=False)))
    death = finish(from_poses(rig, "death", death_poses(spec, rig), loop=False))
    sp.add(death)
    corpse = death.frames[-1].image
    vanish = Animation("vanish", loop=False)
    for t in (0.15, 0.35, 0.55, 0.75, 0.9, 1.01):
        vanish.add(fx.dissolve(corpse, t, color="#fee761" if t < 0.9 else None), 90)
    sp.add(vanish)
    return sp


def _shadowed(img, ground: int, cx: float):
    box = img.bbox()
    if box is None:
        return img
    w = max(4.0, min(7.0, (box[2] - box[0]) / 2.5))
    return fx.drop_shadow(img, rx=w, ry=1.0, cx=cx, cy=ground + 2)


# --- presets ------------------------------------------------------------------

PRESETS: Dict[str, HumanoidSpec] = {
    "knight": HumanoidSpec(name="knight", top="#8b9bb4", top_shiny=True, bottom="#5a6988",
                           boots="#3a4466", helmet="#c0cbdc", helmet_style="cap", hair=None,
                           weapon="sword", shield="#124e89", cape="#a22633", belt="#733e39"),
    "barbarian": HumanoidSpec(name="barbarian", skin="#d77643", top="#b86f50", sleeves="#d77643",
                              bottom="#733e39", boots="#3e2731", hair="#e43b44", hair_style="long",
                              beard="#e43b44", helmet="#8b9bb4", helmet_style="horned",
                              weapon="axe", build="stocky"),
    "mage": HumanoidSpec(name="mage", top="#68386c", robe=True, sleeves="#68386c", bottom="#68386c",
                         boots="#3e2731", helmet="#68386c", helmet_style="hood", beard="#c0cbdc",
                         hair="#c0cbdc", weapon="staff", magic="#2ce8f5", belt="#feae34", build="slim"),
    "spearman": HumanoidSpec(name="spearman", skin="#c28569", top="#3e8948", bottom="#5a6988",
                             boots="#733e39", hair="#3e2731", helmet="#b86f50", helmet_style="cap",
                             weapon="spear", weapon_color="#c0cbdc"),
    "rogue": HumanoidSpec(name="rogue", top="#262b44", sleeves="#262b44", bottom="#3a4466", boots="#181425",
                          hair="#fee761", hair_style="spiky", weapon="dagger", cape="#3e2731",
                          build="slim", belt="#733e39"),
    "orc": HumanoidSpec(name="orc", skin="#63c74d", eye="#e43b44", top="#733e39", sleeves="#63c74d",
                        bottom="#3e2731", boots="#181425", hair="#181425", hair_style="spiky",
                        weapon="axe", weapon_color="#8b9bb4", build="stocky"),
    "archer": HumanoidSpec(name="archer", skin="#e8b796", top="#3e8948", sleeves="#3e8948", bottom="#733e39",
                           boots="#3e2731", hair="#feae34", helmet="#265c42", helmet_style="hood",
                           weapon="bow", handle_color="#b86f50", weapon_color="#c0cbdc", cape="#265c42",
                           belt="#733e39", build="slim"),
    "king": HumanoidSpec(name="king", top="#a22633", sleeves="#a22633", bottom="#3e2731",
                         hair="#ead4aa", beard="#ead4aa", helmet="#feae34", helmet_style="crown",
                         cape="#124e89", weapon="sword", weapon_color="#fee761", belt="#feae34"),
}


def random_spec(seed: int, name: Optional[str] = None) -> HumanoidSpec:
    """Deterministic random villager/soldier for crowds and variety."""
    r = random.Random(seed)
    skins = ["#e8b796", "#c28569", "#b86f50", "#733e39", "#ead4aa"]
    cloth = ["#124e89", "#3e8948", "#a22633", "#68386c", "#b86f50", "#5a6988", "#265c42", "#be4a2f"]
    hairs = ["#3e2731", "#733e39", "#feae34", "#181425", "#e43b44", "#c0cbdc"]
    return HumanoidSpec(
        name=name or f"unit{seed}",
        skin=r.choice(skins), top=r.choice(cloth), bottom=r.choice(cloth[4:] + ["#3a4466"]),
        boots=r.choice(["#3e2731", "#733e39", "#181425"]),
        hair=r.choice(hairs), hair_style=r.choice(["short", "short", "long", "spiky"]),
        beard=r.choice([None, None, None, r.choice(hairs)]),
        helmet=r.choice([None, None, "#8b9bb4", "#b86f50"]),
        weapon=r.choice(["sword", "axe", "spear", "dagger", None]),
        shield=r.choice([None, None, r.choice(cloth)]),
        build=r.choice(["normal", "normal", "stocky", "slim"]),
    )
