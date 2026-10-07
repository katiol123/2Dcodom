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
from ..rig import Blob, Limb, Pixels, Poly, Pose, Rig
from ..shading import BASE, HIGHLIGHT, LIGHT, Ink, Material, PartBuffer, Shader
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
    size: Tuple[int, int] = (48, 32)


def build_quad_rig(spec: QuadSpec) -> Rig:
    W, H = spec.size
    fur = Material.of("fur", spec.fur)
    belly = Material.of("belly", spec.belly)
    eye = Material.of("eye", spec.eye, flat=True)
    nose = Material.of("nose", spec.nose, flat=True)
    rig = Rig(W, H, (W * 0.36, H - 3 - spec.leg_len * 2 - 1), Shader(**CRISP))
    L, bw = spec.body_len, spec.body_w

    rig.bone("root", None, 0)
    rig.bone("spine", "root", L, world=0, z=10, material=fur, shapes=[
        Limb(width=bw, t0=0.0, t1=1.0),
        Limb(material=belly, width=2, t0=0.15, t1=0.85, z=0.1, group="belly", level=BASE),
    ])
    # move the belly stripe to the underside
    rig.bones["spine"].shapes[1] = Poly(material=belly, z=0.1, group="belly", points=[
        (1, bw / 2 - 1.5), (L - 1, bw / 2 - 1.5), (L - 2, bw / 2 + 0.2), (2, bw / 2 + 0.2)])
    rig.bone("neck", "spine", 4, world=-35, attach=0.92, z=11, material=fur, shapes=[Limb(width=bw - 2)])
    if spec.collar is not None:
        rig.bones["neck"].shapes.append(Limb(material=Material.of("collar", spec.collar), width=bw - 1.5,
                                             t0=0.1, t1=0.25, z=0.2, group="collar"))
    head = rig.bone("head", "neck", 0, world=0, z=12, material=fur, shapes=[
        Blob(rx=3.5, ry=3, t=0, offset=(0.5, -0.5)),
        Pixels(material=eye, level=BASE, z=0.5, outline=False, points=[(1.5, -1.5)]),
    ])
    rig.bone("snout", "head", 4.5, world=10, offset=(1.5, -0.5), z=12.2, material=fur, group="head",
             shapes=[Limb(width=3, t0=0, t1=0.85),
                     Pixels(material=nose, level=BASE, z=0.4, outline=False, points=[(0, -1)], t=1.0)])
    rig.bone("jaw", "head", 4, world=25, offset=(1.0, 1.2), z=11.9, material=belly, group="jaw",
             shapes=[Limb(width=2, t0=0.1, t1=0.9)])
    if spec.ears == "pointy":
        head.shapes.append(Poly(z=0.3, group="ear", points=[(-2.5, -2.5), (-1.5, -6.5), (0.5, -2.5)]))
    else:
        head.shapes.append(Blob(z=0.3, group="ear", rx=1.5, ry=1.5, t=0, offset=(-1.5, -3)))
    if spec.tusks is not None:
        tusk = Material.of("tusk", spec.tusks)
        rig.bones["snout"].shapes.append(Poly(material=tusk, z=0.5, group="tusk",
                                              points=[(2.5, 1), (3.5, -2.5), (4, 1.5)]))
    if spec.tail != "none":
        w = 3 if spec.tail == "bushy" else 1
        rig.bone("tail", "root", 7 if spec.tail == "bushy" else 6, world=-160, z=9, material=fur,
                 shapes=[Limb(width=w, t0=0.1, t1=1.0, width_end=w + (1 if spec.tail == "bushy" else 0))])
    ll = spec.leg_len
    # legs tuck *behind* the body (z < spine) so only the part below the belly
    # shows - drawing them on top makes noisy contour lines across the torso
    for side, z, depth in (("b", 4, -1), ("f", 8, 0)):
        rig.bone(f"hip_{side}", "root", ll, world=70, offset=(1.5, 0), z=z, depth=depth, material=fur,
                 group=f"hleg_{side}", shapes=[Limb(width=4 if side == "f" else 3, t0=-0.2)])
        rig.bone(f"hock_{side}", f"hip_{side}", ll + 1, world=105, z=z + 0.1, depth=depth, material=fur,
                 group=f"hleg_{side}", shapes=[Limb(width=2)])
        rig.bone(f"hpaw_{side}", f"hock_{side}", 1.5, world=0, z=z + 0.2, depth=depth, ground=True,
                 material=fur, group=f"hleg_{side}", shapes=[Limb(width=2)])
        rig.bone(f"shoulder_{side}", "spine", ll, world=95, attach=0.85, z=z + 0.3, depth=depth, material=fur,
                 group=f"fleg_{side}", shapes=[Limb(width=3, t0=-0.3)])
        rig.bone(f"wrist_{side}", f"shoulder_{side}", ll, world=88, z=z + 0.4, depth=depth, material=fur,
                 group=f"fleg_{side}", shapes=[Limb(width=2)])
        rig.bone(f"fpaw_{side}", f"wrist_{side}", 1.5, world=0, z=z + 0.5, depth=depth, ground=True,
                 material=fur, group=f"fleg_{side}", shapes=[Limb(width=2)])
    return rig


def _qbase(spec: QuadSpec) -> Pose:
    return Pose(body={"spine": -3, "neck": -40, "head": 0, "snout": 10, "jaw": 25, "tail": -165},
                ground=spec.size[1] - 3)


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
        p.offsets = {"spine": (0, b * 0.6)}
        idle.append(p)

    walk = []
    for i in range(8):
        p = base.copy(duration=95)
        _legs(p, i / 8)
        p.body["tail"] = -160 + 10 * math.sin(math.tau * i / 8)
        p.body["neck"] = -38 + 3 * math.cos(math.tau * i / 4)
        walk.append(p)

    crouch = base.copy(duration=220)
    _legs(crouch, 0.0, amp=0)
    crouch.body.update(spine=6, neck=-15, head=10, jaw=25, tail=-150,
                       shoulder_f=125, wrist_f=60, shoulder_b=120, wrist_b=65, hip_f=50, hock_f=130, hip_b=55, hock_b=125)
    lunge = base.copy(duration=60, shift=(4, 0))
    _legs(lunge, 0.0, amp=0)
    lunge.body.update(spine=-8, neck=-10, head=0, jaw=65, tail=-185,
                      shoulder_f=40, wrist_f=20, shoulder_b=50, wrist_b=30, hip_f=110, hock_f=150, hip_b=105, hock_b=140)
    bite = lunge.copy(duration=200, events=["hit"])
    bite.body.update(jaw=20, neck=-5, head=15)
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
