"""Non-humanoid units.

* :func:`build_slime` - drawn directly with the low-level PartBuffer API;
  shows squash & stretch (volume-preserving rx*ry) driving every animation.
* :func:`build_quadruped` - a 4-legged rig (wolf, boar, bear...) with a
  four-beat walk, bite attack and death.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Optional, Tuple

from .. import fx
from ..anim import Animation, Sprite, from_poses
from ..color import ColorLike, mix
from ..rig import Blob, Custom, Limb, Pixels, Poly, Pose, Rig
from ..shading import BASE, HIGHLIGHT, LIGHT, SHADOW, Ink, Material, PartBuffer, Shader
from .humanoid import CRISP


# --- slime ----------------------------------------------------------------------

@dataclass
class SlimeSpec:
    name: str = "slime"
    color: ColorLike = "#63c74d"
    eye: ColorLike = "#181425"
    size: int = 32
    volume: float = 36.0     # rx * ry stays ~constant: squash & stretch keeps volume


def _slime_frame(spec: SlimeSpec, rx: float, lift: float = 0.0, dx: float = 0.0,
                 shader: Optional[Shader] = None, puddle: bool = False):
    body = Material.of("slime", spec.color, shiny=True)
    eye = Material.of("eye", spec.eye, flat=True)
    W = H = spec.size
    ground = H - 3
    ry = spec.volume / rx
    buf = PartBuffer(W, H)
    cx = math.floor(W / 2 + dx) + (0.5 if round(rx * 2) % 2 else 0.0)
    cy = ground + 1 - ry - lift
    ink = Ink(body, "body", 1)
    buf.ellipse(cx, cy, rx, ry, ink)
    # flatten the bottom when on the ground (slimes sit, they are not balls)
    if lift <= 0:
        for x in range(int(cx - rx), int(cx + rx) + 1):
            for y in range(int(cy), ground + 1):
                if buf.get(x, y) is None and buf.get(x, y - 1) is not None and y >= cy + ry * 0.55:
                    buf.set(x, y, ink)
    if not puddle:
        # eyes look right (facing direction), scale a little with the body
        ex = cx + rx * 0.35
        ey = cy - ry * 0.15
        for ox in (0, 3):
            for oy in (0, 1) if ry > 3.5 else (0,):
                buf.set(int(ex + ox - 1), int(ey + oy), Ink(eye, "eye", 2, level=BASE, outline=False))
        # specular glint
        buf.set(int(cx - rx * 0.5), int(cy - ry * 0.55), Ink(body, "glint", 2, level=HIGHLIGHT, outline=False))
    return (shader or Shader()).render(buf)


def build_slime(spec: SlimeSpec = SlimeSpec(), shadow: bool = True) -> Sprite:
    sp = Sprite(spec.name, spec.size, spec.size, (spec.size // 2, spec.size - 3))
    base = math.sqrt(spec.volume) * 1.15

    def F(k_rx, lift=0.0, dx=0.0, **kw):
        img = _slime_frame(spec, base * k_rx, lift, dx, **kw)
        if shadow:
            r = max(3.0, base * k_rx * (1.0 - min(0.5, lift / 12)))
            img = fx.drop_shadow(img, rx=r, ry=1.0, cx=spec.size / 2 + dx, cy=spec.size - 1)
        return img

    idle = Animation("idle")
    for k, d in ((1.0, 180), (1.06, 160), (1.0, 180), (0.95, 160)):
        idle.add(F(k), d)
    sp.add(idle)

    hop = Animation("walk")
    for k, lift, dx, d in ((1.25, 0, 0, 120), (0.8, 1, 1, 70), (0.9, 4, 2, 80), (0.95, 5, 3, 80),
                           (0.85, 2, 4, 70), (1.3, 0, 5, 120), (1.1, 0, 5, 80)):
        hop.add(F(k, lift, dx - 2.5), d)
    sp.add(hop)

    atk = Animation("attack", loop=False)
    atk.add(F(1.35), 220)                 # anticipation: squash low
    atk.add(F(0.75, 2, 2), 60)            # stretch up/forward
    atk.add(F(1.5, 0, 5), 200, ["hit"])   # splat into the target
    atk.add(F(1.1, 0, 2), 120)
    atk.add(F(1.0), 100)
    sp.add(atk)

    hurt = Animation("hurt", loop=False)
    hurt.add(fx.flash(F(1.3, 0, -1)), 70)
    hurt.add(F(1.3, 0, -1), 120)
    hurt.add(F(1.05), 100)
    sp.add(hurt)

    death = Animation("death", loop=False)
    death.add(fx.flash(F(1.3)), 90, ["hit"])
    for k, d in ((1.5, 100), (1.9, 100), (2.4, 120)):
        death.add(F(k), d)
    puddle = _slime_frame(spec, base * 2.9, puddle=True)
    death.add(puddle, 900, ["dead"])
    sp.add(death)

    vanish = Animation("vanish", loop=False)
    for t in (0.2, 0.45, 0.7, 0.9, 1.01):
        vanish.add(fx.dissolve(puddle, t, color=mix(spec.color, "#ffffff", 0.6)), 90)
    sp.add(vanish)
    return sp


# --- quadruped ------------------------------------------------------------------

@dataclass
class QuadSpec:
    name: str = "wolf"
    fur: ColorLike = "#8b9bb4"
    belly: ColorLike = "#c0cbdc"
    eye: ColorLike = "#fee761"
    nose: ColorLike = "#181425"
    body_len: float = 11.0
    body_w: float = 6.0
    leg_len: float = 5.0
    tail: str = "bushy"      # bushy | thin | none
    ears: str = "pointy"     # pointy | round
    tusks: Optional[ColorLike] = None
    collar: Optional[ColorLike] = None   # e.g. a team color
    rider_skin: Optional[ColorLike] = None   # set to seat a rider on the back
    rider_top: ColorLike = "#124e89"
    rider_eye: ColorLike = "#fee761"
    rider_blade: ColorLike = "#c0cbdc"
    size: Tuple[int, int] = (48, 32)
    kind: str = "wolf"                   # wolf | horse | griffon | elephant | bear (body proportions)
    rider: Optional[str] = None          # goblin | human (default goblin when rider_skin is set)
    rider_helmet: Optional[ColorLike] = None
    rider_turban: bool = False
    rider_weapon: str = "sword"          # sword | saber | lance | bow
    rider_cloth: Optional[ColorLike] = None   # saddle cloth / howdah in team colours
    rider_shield: Optional[ColorLike] = None
    mane: Optional[ColorLike] = None     # horses
    wings: Optional[ColorLike] = None    # griffons
    head_color: Optional[ColorLike] = None   # griffon's white eagle head


def build_quad_rig(spec: QuadSpec) -> Rig:
    W, H = spec.size
    fur = Material.of("fur", spec.fur)
    belly = Material.of("belly", spec.belly)
    eye = Material.of("eye", spec.eye, flat=True)
    nose = Material.of("nose", spec.nose, flat=True)
    rig = Rig(W, H, (W * 0.36, H - 3 - spec.leg_len * 2 - 1), Shader(**CRISP))
    L, bw = spec.body_len, spec.body_w

    kind = spec.kind
    leg_w = {"elephant": 8, "bear": 4, "horse": 3}.get(kind, 4)
    rig.bone("root", None, 0)
    rig.bone("spine", "root", L, world=0, z=10, material=fur, shapes=[
        Limb(width=bw, t0=0.0, t1=1.0),
        Limb(material=belly, width=2, t0=0.15, t1=0.85, z=0.1, group="belly", level=BASE),
    ])
    # move the belly stripe to the underside
    rig.bones["spine"].shapes[1] = Poly(material=belly, z=0.1, group="belly", points=[
        (1, bw / 2 - 1.5), (L - 1, bw / 2 - 1.5), (L - 2, bw / 2 + 0.2), (2, bw / 2 + 0.2)])
    neck_len, neck_w = {"horse": (7, bw - 2), "griffon": (5, bw - 2), "elephant": (3, bw - 4),
                        "bear": (3, bw - 2)}.get(kind, (4, bw - 2))
    rig.bone("neck", "spine", neck_len, world=-35, attach=0.92, z=11, material=fur, shapes=[Limb(width=neck_w)])
    if spec.mane is not None:
        rig.bones["neck"].shapes.append(Limb(material=Material.of("mane", spec.mane), width=2, t0=-0.2, t1=1.1,
                                             z=0.3, group="mane"))
        rig.bones["neck"].shapes[-1] = Poly(material=Material.of("mane", spec.mane), z=0.3, group="mane",
                                            points=[(-1, -neck_w / 2 - 1), (neck_len * 0.9, -neck_w / 2 - 2),
                                                    (neck_len * 1.1, -neck_w / 2), (0, -neck_w / 2 + 1)])
    if spec.collar is not None:
        rig.bones["neck"].shapes.append(Limb(material=Material.of("collar", spec.collar), width=bw - 1.5,
                                             t0=0.1, t1=0.25, z=0.2, group="collar"))
    hmat = Material.of("headc", spec.head_color) if spec.head_color is not None else fur
    hr = {"elephant": (bw * 0.45, bw * 0.42), "bear": (4, 3.5), "horse": (3, 2.5)}.get(kind, (3.5, 3))
    head = rig.bone("head", "neck", 0, world=0, z=12, material=hmat, shapes=[
        Blob(rx=hr[0], ry=hr[1], t=0, offset=(0.5, -0.5)),
        Pixels(material=eye, level=BASE, z=0.5, outline=False, points=[(1.5 + hr[0] - 3.5, -1.5)]),
    ])
    if kind == "griffon":
        rig.bone("snout", "head", 4, world=35, offset=(2.5, -1), z=12.2, material=nose, group="beak",
                 shapes=[Poly(points=[(-1, -1.5), (4.5, 1.5), (0.5, 2)])])
        rig.bone("jaw", "head", 2, world=35, offset=(2, 0.5), z=11.9, material=nose, group="beak",
                 shapes=[Limb(width=1, t0=0.1, t1=0.9)])
    elif kind == "elephant":
        rig.bone("snout", "head", 8, world=80, offset=(hr[0] - 1, 1.5), z=12.2, material=fur, group="head",
                 shapes=[Limb(width=5, t0=0, t1=1.0, width_end=4)])
        rig.bone("trunk2", "snout", 7, world=100, z=12.25, material=fur, group="head",
                 shapes=[Limb(width=4, t0=0, t1=1.0, width_end=3)])
        rig.bone("jaw", "head", 2, world=60, offset=(3, 3), z=11.9, material=fur, group="jaw",
                 shapes=[Limb(width=2, t0=0.1, t1=0.9)])
        head.shapes.append(Blob(z=-0.3, group="ear", rx=hr[0] * 0.65, ry=hr[1] * 0.95, t=0, offset=(-hr[0] * 0.55, 0)))
    else:
        sl, sw, sa = {"horse": (6, 3, 55), "bear": (3, 4, 15)}.get(kind, (4.5, 3, 10))
        rig.bone("snout", "head", sl, world=sa, offset=(1.5, -0.5), z=12.2, material=fur, group="head",
                 shapes=[Limb(width=sw, t0=0, t1=0.85),
                         Pixels(material=nose, level=BASE, z=0.4, outline=False, points=[(0, -1)], t=1.0)])
        rig.bone("jaw", "head", 4 if kind != "horse" else 3, world=25 if kind != "horse" else 60,
                 offset=(1.0, 1.2), z=11.9, material=belly, group="jaw", shapes=[Limb(width=2, t0=0.1, t1=0.9)])
    if kind == "elephant":
        pass
    elif spec.ears == "pointy" and kind != "griffon":
        if kind == "horse":
            head.shapes.append(Poly(z=0.3, group="ear", points=[(-1.5, -2), (-1, -5), (0.5, -2)]))
        else:
            head.shapes.append(Poly(z=0.3, group="ear", points=[(-2.5, -2.5), (-1.5, -6.5), (0.5, -2.5)]))
    elif kind != "griffon":
        head.shapes.append(Blob(z=0.3, group="ear", rx=1.5, ry=1.5, t=0, offset=(-1.5 - hr[0] + 3.5, -3 - hr[1] + 3)))
    if spec.tusks is not None:
        tusk = Material.of("tusk", spec.tusks)
        if kind == "elephant":
            head.shapes.append(Poly(material=tusk, z=0.6, group="tusk",
                                    points=[(hr[0] - 2, hr[1] * 0.5), (hr[0] + 4, hr[1] + 2), (hr[0] + 5.5, hr[1]),
                                            (hr[0], hr[1] * 0.3)]))
        else:
            rig.bones["snout"].shapes.append(Poly(material=tusk, z=0.5, group="tusk",
                                                  points=[(2.5, 1), (3.5, -2.5), (4, 1.5)]))
    if spec.tail != "none":
        if spec.tail == "long":
            tm = Material.of("tailc", spec.mane) if spec.mane is not None else fur
            rig.bone("tail", "root", 9, world=-200, z=9, material=tm,
                     shapes=[Limb(width=2, t0=0.0, t1=1.0, width_end=3)])
        else:
            w = 3 if spec.tail == "bushy" else 1
            rig.bone("tail", "root", 7 if spec.tail == "bushy" else 6, world=-160, z=9, material=fur,
                     shapes=[Limb(width=w, t0=0.1, t1=1.0, width_end=w + (1 if spec.tail == "bushy" else 0))])
    if spec.wings is not None:
        wm = Material.of("qwings", spec.wings)
        rig.bone("wing", "spine", 10, world=-130, attach=0.5, offset=(0, -bw / 2 + 1), z=14.5, material=wm, shapes=[
            Poly(points=[(0, 0), (-3, -7), (-10, -13), (-16, -12), (-15, -7), (-11, -2), (-5, 1.5)]),
            Pixels(level=SHADOW, z=0.1, outline=False, t=0.0,
                   points=[(-6, -5), (-9, -8), (-12, -9), (-9, -3), (-12, -5)]),
        ])
    if spec.rider_cloth is not None:
        cloth = Material.of("cloth", spec.rider_cloth)
        trim = Material.of("trim", "#feae34", shiny=True)
        if kind == "elephant":
            # howdah: a little tower on the back
            rig.bones["spine"].shapes.append(Poly(material=cloth, z=2.5, group="howdah", points=[
                (L * 0.3, -bw / 2 - 4), (L * 0.7, -bw / 2 - 4), (L * 0.72, -bw / 2 + 1.5), (L * 0.28, -bw / 2 + 1.5)]))
            rig.bones["spine"].shapes.append(Poly(material=trim, z=2.6, group="howdahtrim", points=[
                (L * 0.27, -bw / 2 - 5), (L * 0.73, -bw / 2 - 5), (L * 0.73, -bw / 2 - 3.5), (L * 0.27, -bw / 2 - 3.5)]))
            rig.bones["spine"].shapes.append(Poly(material=cloth, z=0.4, group="blanket", points=[
                (L * 0.3, -bw / 2 + 1), (L * 0.7, -bw / 2 + 1), (L * 0.66, bw / 2 - 3), (L * 0.34, bw / 2 - 3)]))
            rig.bones["spine"].shapes.append(Pixels(material=trim, level=LIGHT, z=0.5, outline=False, t=0.0,
                                                    points=[(L * 0.38, bw / 2 - 3.5), (L * 0.5, bw / 2 - 3.5),
                                                            (L * 0.62, bw / 2 - 3.5)]))
        else:
            rig.bones["spine"].shapes.append(Poly(material=cloth, z=0.3, group="saddle", points=[
                (L * 0.3, -bw / 2 - 0.5), (L * 0.66, -bw / 2 - 0.5), (L * 0.62, bw / 2 + 1.5), (L * 0.34, bw / 2 + 1.5)]))
            rig.bones["spine"].shapes.append(Pixels(material=trim, level=LIGHT, z=0.4, outline=False, t=0.0,
                                                    points=[(L * 0.36, bw / 2 + 1), (L * 0.48, bw / 2 + 1),
                                                            (L * 0.6, bw / 2 + 1)]))
    if spec.rider_skin is not None:
        if spec.rider == "human":
            _add_human_rider(rig, spec)
        else:
            _add_rider(rig, spec)
    ll = spec.leg_len
    # legs tuck *behind* the body (z < spine) so only the part below the belly
    # shows - drawing them on top makes noisy contour lines across the torso
    for side, z, depth in (("b", 4, -1), ("f", 8, 0)):
        rig.bone(f"hip_{side}", "root", ll, world=70, offset=(1.5, 0), z=z, depth=depth, material=fur,
                 group=f"hleg_{side}", shapes=[Limb(width=max(leg_w, 4) if side == "f" else max(leg_w, 3), t0=-0.2)])
        rig.bone(f"hock_{side}", f"hip_{side}", ll + 1, world=105, z=z + 0.1, depth=depth, material=fur,
                 group=f"hleg_{side}", shapes=[Limb(width=max(2, leg_w - 1))])
        rig.bone(f"hpaw_{side}", f"hock_{side}", 1.5, world=0, z=z + 0.2, depth=depth, ground=True,
                 material=fur, group=f"hleg_{side}", shapes=[Limb(width=2)])
        rig.bone(f"shoulder_{side}", "spine", ll, world=95, attach=0.85, z=z + 0.3, depth=depth, material=fur,
                 group=f"fleg_{side}", shapes=[Limb(width=max(3, leg_w), t0=-0.3)])
        rig.bone(f"wrist_{side}", f"shoulder_{side}", ll, world=88, z=z + 0.4, depth=depth, material=fur,
                 group=f"fleg_{side}", shapes=[Limb(width=max(2, leg_w - 1))])
        rig.bone(f"fpaw_{side}", f"wrist_{side}", 1.5, world=0, z=z + 0.5, depth=depth, ground=True,
                 material=fur, group=f"fleg_{side}", shapes=[Limb(width=2)])
    return rig


def _add_rider(rig: Rig, spec: QuadSpec) -> None:
    """A goblin sitting on the back: torso, big-eared head, dangling leg, sword arm."""
    skin = Material.of("rskin", spec.rider_skin)
    top = Material.of("rtop", spec.rider_top)
    eye = Material.of("reye", spec.rider_eye, flat=True)
    blade = Material.of("rblade", spec.rider_blade, shiny=True)
    wood = Material.of("rwood", "#733e39")
    rig.bone("rider_hip", "spine", 0, attach=0.42, offset=(0, -spec.body_w / 2 + 0.5), z=13, material=top)
    rig.bone("rider_leg", "rider_hip", 4, world=75, z=13.2, material=top, group="rleg",
             shapes=[Limb(width=2, t0=0.0, t1=1.0)])
    rig.bone("rider_torso", "rider_hip", 5, world=-95, z=13.4, material=top, group="rtorso",
             shapes=[Limb(width=4, t0=0.0, t1=0.95)])
    rig.bone("rider_head", "rider_torso", 0, world=0, z=13.6, material=skin, group="rhead", shapes=[
        Blob(rx=2.5, ry=2.2, t=0, offset=(0.5, -2.2)),
        Poly(z=-0.1, group="rear", points=[(-1, -3), (-6, -5.5), (-1.5, -1.5)]),
        Poly(z=0.1, group="rnose", points=[(2.5, -2.5), (5, -1.2), (2.5, -1.2)]),
        Pixels(material=eye, level=BASE, z=0.3, outline=False, points=[(1.8, -2.6)]),
    ])
    rig.bone("rider_arm", "rider_torso", 3.5, world=30, attach=0.8, z=14, material=skin, group="rarm",
             shapes=[Limb(width=2)])
    rig.bone("rider_blade", "rider_arm", 8, world=-60, z=13.9, material=blade, group="rblade", shapes=[
        Limb(width=1, t0=0.2, t1=1.0),
        Limb(material=wood, width=1, t0=-0.1, t1=0.2, group="rhilt"),
    ])


def _add_human_rider(rig: Rig, spec: QuadSpec) -> None:
    """A human rider: armoured torso, helmet or turban, a lance / saber / sword / bow and maybe a shield."""
    skin = Material.of("rskin", spec.rider_skin)
    top = Material.of("rtop", spec.rider_top, shiny=spec.rider_top in ("#8b9bb4", "#c0cbdc"))
    eye = Material.of("reye", spec.rider_eye, flat=True)
    blade = Material.of("rblade", spec.rider_blade, shiny=True)
    wood = Material.of("rwood", "#733e39")
    big = spec.kind == "elephant"
    hip_t = 0.5 if big else 0.45
    lift = spec.body_w / 2 + (4.5 if big else 0.5)
    rig.bone("rider_hip", "spine", 0, attach=hip_t, offset=(0, -lift), z=13, material=top)
    rig.bone("rider_leg", "rider_hip", 5, world=80, z=13.2, material=Material.of("rlegs", "#3e2731"), group="rleg",
             shapes=[] if big else [Limb(width=2, t0=0.0, t1=1.0)])
    rig.bone("rider_torso", "rider_hip", 6, world=-95, z=13.4, material=top, group="rtorso",
             shapes=[Limb(width=4, t0=0.0, t1=0.95)])
    head_shapes = [Blob(rx=2.5, ry=2.5, t=0, offset=(0.5, -2.5)),
                   Pixels(material=eye, level=BASE, z=0.3, outline=False, points=[(2, -2.8)])]
    if spec.rider_turban:
        head_shapes.append(Blob(material=Material.of("rturban", spec.rider_helmet or "#ffffff"), rx=3.2, ry=2.2,
                                t=0, offset=(0, -4.6), z=0.4, group="rhelm"))
    elif spec.rider_helmet is not None:
        hm = Material.of("rhelm", spec.rider_helmet, shiny=True)
        head_shapes.append(Blob(material=hm, rx=3, ry=1.8, t=0, offset=(0.3, -4.4), z=0.4, group="rhelm"))
        head_shapes.append(Pixels(material=hm, level=LIGHT, z=0.45, group="rhelm", t=0.0, points=[(0.3, -6.5)]))
    rig.bone("rider_head", "rider_torso", 0, world=0, z=13.6, material=skin, group="rhead", shapes=head_shapes)
    if spec.rider_shield is not None:
        rig.bone("rider_shield", "rider_torso", 0, attach=0.55, offset=(-2.5, 0), z=13.3,
                 material=Material.of("rshield", spec.rider_shield, shiny=True), group="rshield",
                 shapes=[Blob(rx=2.5, ry=3.5, t=0)])
    rig.bone("rider_arm", "rider_torso", 4, world=30, attach=0.8, z=14, material=top, group="rarm",
             shapes=[Limb(width=2)])
    w = spec.rider_weapon
    if w == "lance":
        cloth = Material.of("pennant", spec.rider_cloth or "#e43b44")
        shapes = [Limb(material=wood, width=1, t0=-0.15, t1=0.92),
                  Poly(material=blade, group="ltip", z=0.2, points=[(17.5, -1), (21, 0), (17.5, 1)]),
                  Poly(material=cloth, group="pennant", z=0.1, points=[(14, -1), (17, -1), (16, -4), (14, -3)])]
        rig.bone("rider_blade", "rider_arm", 18, world=-15, z=13.9, material=wood, group="rblade", shapes=shapes)
    elif w == "bow":
        string = Material.of("rstring", "#ead4aa", flat=True)
        rig.bone("rider_blade", "rider_arm", 0, world=-90, z=14.2, material=wood, group="rblade", shapes=[
            Custom(fn=lambda buf, st, ink: _small_bow(buf, st, ink)),
            Custom(material=string, level=BASE, outline=False, group="rstring",
                   fn=lambda buf, st, ink: _small_bow(buf, st, ink, string=True))])
    else:
        L = 8 if w == "sword" else 7
        if w == "saber":
            bl = Poly(material=blade, points=[(-0.5, 0), (0.5, 0), (2.5, -L * 0.6), (2.5, -L), (1, -L * 0.6)])
        else:
            bl = Limb(width=1, t0=0.2, t1=1.0)
        rig.bone("rider_blade", "rider_arm", L, world=-60, z=13.9, material=blade, group="rblade", shapes=[
            bl, Limb(material=wood, width=1, t0=-0.1, t1=0.2, group="rhilt")])


def _small_bow(buf, st, ink, string: bool = False):
    """Rider's bow: a 9px arc (or its string) through the hand, curving forward."""
    pts = []
    for i in range(7):
        u = -1 + i / 3
        if string:
            pts.append(st.point(0, (-0.5, u * 4.5)))
        else:
            pts.append(st.point(0, (2.0 * (1 - u * u) - 0.5, u * 4.5)))
    for a, b in zip(pts, pts[1:]):
        buf.line(math.floor(a[0]), math.floor(a[1]), math.floor(b[0]), math.floor(b[1]), ink)


def _qbase(spec: QuadSpec) -> Pose:
    p = Pose(body={"spine": -3, "neck": -40, "head": 0, "snout": 10, "jaw": 25, "tail": -165,
                   "rider_torso": -95, "rider_arm": 30, "rider_blade": -60, "rider_leg": 75},
             ground=spec.size[1] - 3)
    k = spec.kind
    if k == "horse":
        p.body.update(neck=-55, snout=60, jaw=65, tail=-230)
    elif k == "griffon":
        p.body.update(neck=-50, snout=35, jaw=35, wing=-130, tail=-170)
    elif k == "elephant":
        p.body.update(neck=-15, snout=80, trunk2=100, jaw=60, tail=-200)
    elif k == "bear":
        p.body.update(neck=-20, snout=15, jaw=30)
    if spec.rider == "human":
        p.body.update(rider_arm={"lance": 60, "bow": 0}.get(spec.rider_weapon, 30),
                      rider_blade={"lance": -12, "bow": -90}.get(spec.rider_weapon, -60), rider_leg=80)
    return p


def _legs(p: Pose, phase: float, amp: float = 26.0) -> None:
    """Four-beat walk: hind-back, fore-back, hind-front, fore-front a quarter apart."""
    for leg, off in (("h_b", 0.0), ("f_b", 0.25), ("h_f", 0.5), ("f_f", 0.75)):
        kind, side = leg.split("_")
        ph = math.tau * (phase + off)
        s, c = math.sin(ph), math.cos(ph)
        lift = max(0.0, c) ** 1.4
        if kind == "h":
            p.body[f"hip_{side}"] = 70 - amp * s
            p.body[f"hock_{side}"] = 105 - amp * 0.6 * s + 35 * lift
            p.body[f"hpaw_{side}"] = 0 + 40 * lift
        else:
            p.body[f"shoulder_{side}"] = 95 - amp * s
            p.body[f"wrist_{side}"] = 90 - amp * s + 55 * lift
            p.body[f"fpaw_{side}"] = 0 + 50 * lift


def _tweak(spec: QuadSpec, p: Pose, phase: str, k: float = 0.0) -> Pose:
    """Kind- and rider-specific angles on top of the generic quadruped poses."""
    kind, w = spec.kind, spec.rider_weapon
    if kind == "horse":
        p.body["jaw"] = 65
        p.body["tail"] = -240 + (8 * k if phase == "walk" else 0)
        if phase == "crouch":
            p.body.update(neck=-75, snout=40)
        elif phase in ("lunge", "bite"):
            p.body.update(neck=-45, snout=65)
        elif phase == "walk":
            p.body["neck"] = -55 + 4 * k
            p.body["tail"] = -230 + 8 * k
        elif phase == "idle":
            p.body["neck"] = -55 + 2 * k
    if kind == "griffon":
        wing = {"idle": -130 + 6 * k, "walk": -130 + 28 * k, "crouch": -100, "lunge": -165, "bite": -150}.get(phase)
        if wing is not None:
            p.body["wing"] = wing
        if phase in ("lunge", "bite"):
            p.body["jaw"] = 55
    if kind == "elephant":
        trunk = {"crouch": (160, 190), "lunge": (20, 40), "bite": (55, 80),
                 "walk": (80 + 8 * k, 100 + 12 * k), "idle": (80 + 3 * k, 100 + 6 * k)}.get(phase)
        if trunk is not None:
            p.body["snout"], p.body["trunk2"] = trunk
        p.body["jaw"] = 60
    if spec.rider == "human":
        if w == "lance":
            arm, blade, torso = {"crouch": (25, -8, -105), "lunge": (-5, 0, -78), "bite": (-5, 2, -75)}.get(
                phase, (60, -12, -95))
        elif w == "bow":
            arm, blade, torso = {"crouch": (-10, -90, -100), "lunge": (0, -90, -92), "bite": (-5, -90, -95)}.get(
                phase, (0, -90, -95))
        else:
            arm, blade, torso = {"crouch": (-120, -150, -105), "lunge": (-20, -10, -80), "bite": (40, 40, -75)}.get(
                phase, (30, -60, -95))
        p.body.update(rider_arm=arm, rider_blade=blade, rider_torso=torso)
    return p


def build_quadruped(spec: QuadSpec = QuadSpec(), shadow: bool = True) -> Sprite:
    rig = build_quad_rig(spec)
    W, H = spec.size
    base = _qbase(spec)
    sp = Sprite(spec.name, W, H, (round(rig.origin[0] + spec.body_len / 2), H - 3))

    idle = []
    for i, b in enumerate((0, 0, 1, 1)):
        p = base.copy(duration=200)
        _legs(p, 0.0, amp=0)
        p.body.update(tail=-165 + 8 * b, neck=-40 + 3 * b)
        if spec.kind != "wolf":
            p.body.update({k: v for k, v in base.body.items() if k in ("tail", "neck")})
        p.offsets = {"spine": (0, b * 0.6)}
        idle.append(_tweak(spec, p, "idle", b))

    walk = []
    for i in range(8):
        p = base.copy(duration=95)
        _legs(p, i / 8)
        p.body["tail"] = -160 + 10 * math.sin(math.tau * i / 8)
        p.body["neck"] = -38 + 3 * math.cos(math.tau * i / 4)
        if spec.kind != "wolf":
            p.body.update({k: v for k, v in base.body.items() if k in ("tail", "neck")})
        walk.append(_tweak(spec, p, "walk", math.sin(math.tau * i / 8)))

    crouch = base.copy(duration=220)
    _legs(crouch, 0.0, amp=0)
    crouch.body.update(spine=6, neck=-15, head=10, jaw=25, tail=-150,
                       shoulder_f=125, wrist_f=60, shoulder_b=120, wrist_b=65, hip_f=50, hock_f=130, hip_b=55, hock_b=125)
    crouch.body.update(rider_torso=-105, rider_arm=-120, rider_blade=-150)
    _tweak(spec, crouch, "crouch")
    lunge = base.copy(duration=60, shift=(4, 0))
    _legs(lunge, 0.0, amp=0)
    lunge.body.update(spine=-8, neck=-10, head=0, jaw=65, tail=-185,
                      shoulder_f=40, wrist_f=20, shoulder_b=50, wrist_b=30, hip_f=110, hock_f=150, hip_b=105, hock_b=140)
    lunge.body.update(rider_torso=-80, rider_arm=-20, rider_blade=-10)
    _tweak(spec, lunge, "lunge")
    bite = lunge.copy(duration=200, events=["hit"])
    bite.body.update(jaw=20, neck=-5, head=15, rider_torso=-75, rider_arm=40, rider_blade=40)
    _tweak(spec, bite, "bite")
    rec = rig.lerp(bite, idle[0], 0.5)
    rec.ground, rec.duration = base.ground, 120
    attack = [crouch, lunge, bite, rec, idle[0].copy(duration=100)]

    hit = base.copy(duration=80, post=[fx.flash], events=["hit"])
    _legs(hit, 0, amp=0)
    hit.body.update(neck=-70, jaw=50, spine=-12)
    recoil = hit.copy(post=[], events=[], duration=140, shift=(-1, 0))
    hurt = [hit, recoil, idle[0].copy(duration=100)]

    down = base.copy(duration=120, shift=(-1, 0))
    _legs(down, 0, amp=0)
    down.body.update(spine=8, neck=-10, head=20, jaw=45,
                     shoulder_f=135, wrist_f=150, shoulder_b=130, wrist_b=150, hip_f=20, hock_f=160, hip_b=30, hock_b=150)
    lie = base.copy(duration=900, ground_all=True, shift=(-1, 0), events=["dead"])
    lie.body.update(spine=0, neck=10, head=10, jaw=40, tail=180,
                    shoulder_f=20, wrist_f=10, shoulder_b=35, wrist_b=20, hip_f=-10, hock_f=0, hip_b=5, hock_b=10,
                    fpaw_f=0, fpaw_b=0, hpaw_f=0, hpaw_b=0)
    land = lie.copy(duration=90, shift=(-1, -1), events=[])
    death = [hit.copy(), recoil.copy(), down, land, lie]

    def fin(a: Animation) -> Animation:
        if not shadow:
            return a
        return a.map(lambda img: fx.drop_shadow(img, rx=spec.body_len * 0.75, ry=1.0,
                                                cx=rig.origin[0] + spec.body_len / 2, cy=H - 1))

    sp.add(fin(from_poses(rig, "idle", idle)))
    sp.add(fin(from_poses(rig, "walk", walk)))
    sp.add(fin(from_poses(rig, "attack", attack, loop=False)))
    sp.add(fin(from_poses(rig, "hurt", hurt, loop=False)))
    d = sp.add(fin(from_poses(rig, "death", death, loop=False)))
    corpse = d.frames[-1].image
    van = Animation("vanish", loop=False)
    for t in (0.2, 0.45, 0.7, 0.9, 1.01):
        van.add(fx.dissolve(corpse, t, color="#fee761" if t < 0.9 else None), 90)
    sp.add(van)
    return sp


WOLF = QuadSpec()
BOAR = QuadSpec(name="boar", fur="#733e39", belly="#b86f50", eye="#181425", body_len=10, body_w=8,
                leg_len=3.5, tail="thin", ears="round", tusks="#ead4aa")
FOX = QuadSpec(name="fox", fur="#f77622", belly="#ead4aa", eye="#181425", body_len=9, body_w=6,
               leg_len=4, tail="bushy")


# --- spider ----------------------------------------------------------------------

@dataclass
class SpiderSpec:
    name: str = "spider"
    body: ColorLike = "#3e2731"
    mark: ColorLike = "#e43b44"         # pattern on the abdomen (team colour in battle)
    legs: ColorLike = "#181425"
    eye: ColorLike = "#e43b44"
    fang: ColorLike = "#ead4aa"
    size: Tuple[int, int] = (54, 40)


# (attach x on the body, upper body-space angle, lower body-space angle) per leg, front to back
_SPIDER_LEGS = ((5.0, -45, 72), (3.0, -70, 88), (0.0, -108, 95), (-3.0, -132, 110))


def build_spider_rig(spec: SpiderSpec) -> Rig:
    W, H = spec.size
    body = Material.of("sbody", spec.body)
    mark = Material.of("smark", spec.mark)
    legm = Material.of("slegs", spec.legs)
    eye = Material.of("seye", spec.eye, flat=True)
    fang = Material.of("sfang", spec.fang)
    rig = Rig(W, H, (W * 0.48, H - 16), Shader(**CRISP))
    rig.bone("root", None, 0)
    rig.bone("body", "root", 0, world=0, z=10, material=body, shapes=[
        Blob(rx=7.5, ry=5.5, t=0, offset=(-7, -1), group="abdomen"),
        Blob(rx=4.5, ry=3.5, t=0, offset=(3, 0), z=0.2, group="thorax"),
        Poly(material=mark, z=0.3, group="mark", points=[(-10, -4), (-6, -5), (-4, -3), (-7, -2), (-10, -1)]),
        Pixels(material=mark, level=LIGHT, z=0.35, outline=False, t=0.0, points=[(-8, 1), (-6, 2)]),
        Pixels(material=eye, level=BASE, z=0.5, outline=False, t=0.0, points=[(5, -2), (6, -1), (4, -1), (6, -2)]),
    ])
    rig.bone("fangs", "body", 3, world=80, offset=(6.5, 1.5), z=10.4, material=fang, group="fangs",
             shapes=[Limb(width=1, t0=0.0, t1=1.0)])
    for side, z, depth in (("b", 5, -1), ("f", 14, 0)):
        for i, (ax, up, down) in enumerate(_SPIDER_LEGS):
            rig.bone(f"leg{i}{side}", "body", 9, world=up, offset=(ax + (1.5 if side == "b" else 0), -1), z=z,
                     depth=depth, material=legm, group=f"leg{i}{side}", shapes=[Limb(width=2, t0=-0.1)])
            rig.bone(f"shank{i}{side}", f"leg{i}{side}", 12, world=down, z=z + 0.1, depth=depth, material=legm,
                     group=f"leg{i}{side}", ground=True, shapes=[Limb(width=1, t0=0.0, t1=1.0)])
    return rig


def _spider_pose(spec: SpiderSpec, phase: float = 0.0, amp: float = 0.0, **extra) -> Pose:
    p = Pose(body={"body": 0, "fangs": 80}, ground=spec.size[1] - 3)
    for side, off in (("f", 0.0), ("b", 0.5)):
        for i, (_, up, down) in enumerate(_SPIDER_LEGS):
            ph = math.tau * (phase + off + (i % 2) * 0.5)
            lift = max(0.0, math.cos(ph)) * amp
            p.body[f"leg{i}{side}"] = up + math.sin(ph) * amp * 0.8 - lift * 0.6
            p.body[f"shank{i}{side}"] = down + math.sin(ph) * amp * 0.5 - lift
    p.body.update(extra)
    return p


def build_spider(spec: SpiderSpec = SpiderSpec(), shadow: bool = True) -> Sprite:
    rig = build_spider_rig(spec)
    W, H = spec.size
    sp = Sprite(spec.name, W, H, (round(rig.origin[0] - 2), H - 3))
    idle = []
    for i, b in enumerate((0, 1, 1, 0)):
        p = _spider_pose(spec, 0.0, 0.0)
        p.offsets = {"body": (0, b * 0.6)}
        p.duration = 200
        idle.append(p)
    walk = [_spider_pose(spec, i / 6, 14.0).copy(duration=80) for i in range(6)]
    rear = _spider_pose(spec, 0, 0, fangs=40)
    rear.rotation, rear.duration = -18, 240
    for i in (0, 1):
        rear.body[f"leg{i}f"] = -80 - i * 10
        rear.body[f"shank{i}f"] = -20
        rear.body[f"leg{i}b"] = -75 - i * 10
        rear.body[f"shank{i}b"] = -10
    lunge = _spider_pose(spec, 0, 0, fangs=100)
    lunge.rotation, lunge.shift, lunge.duration = 8, (4, 0), 60
    bite = lunge.copy(duration=200, events=["hit"])
    bite.body["fangs"] = 120
    rec = rig.lerp(bite, idle[0], 0.5)
    rec.ground, rec.duration = idle[0].ground, 120
    attack = [rear, lunge, bite, rec, idle[0].copy(duration=100)]
    spit = rear.copy(duration=200)
    spit2 = rear.copy(duration=120, events=["cast"])
    spit2.rotation = -10
    cast = [spit, spit2, rec.copy(), idle[0].copy(duration=100)]
    hit = _spider_pose(spec, 0, 0)
    hit.post, hit.duration, hit.events = [fx.flash], 80, ["hit"]
    hit.shift = (-1, 0)
    hurt = [hit, hit.copy(post=[], events=[], duration=140), idle[0].copy(duration=100)]
    curl = _spider_pose(spec, 0, 0)
    for side in ("f", "b"):
        for i in range(4):
            curl.body[f"leg{i}{side}"] = -90 + (i - 1.5) * 12
            curl.body[f"shank{i}{side}"] = -160 + (i - 1.5) * 15
    curl.ground_all, curl.duration = True, 120
    flip = curl.copy(duration=900, events=["dead"], rotation=180, ground=H - 3)
    death = [hit.copy(), curl, curl.copy(rotation=90, duration=90), flip]

    def fin(a: Animation) -> Animation:
        if not shadow:
            return a
        return a.map(lambda img: fx.drop_shadow(img, rx=9.0, ry=1.0, cx=rig.origin[0] - 2, cy=H - 1))

    for name, poses, loop in (("idle", idle, True), ("walk", walk, True), ("attack", attack, False),
                              ("cast", cast, False), ("hurt", hurt, False)):
        sp.add(fin(from_poses(rig, name, poses, loop=loop)))
    d = sp.add(fin(from_poses(rig, "death", death, loop=False)))
    corpse = d.frames[-1].image
    van = Animation("vanish", loop=False)
    for t in (0.2, 0.45, 0.7, 0.9, 1.01):
        van.add(fx.dissolve(corpse, t, color="#a7f070" if t < 0.9 else None), 90)
    sp.add(van)
    return sp
