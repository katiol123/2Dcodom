"""2D skeletal rig rendered as pixel art.

A :class:`Rig` is a tree of :class:`Bone` s.  Each bone carries shapes
(limbs, blobs, polygons, single pixels, or custom draw callbacks) that are
rasterised into a :class:`~pixelforge.shading.PartBuffer` and then shaded.
Animations are just lists of :class:`Pose` s - so walk / attack / death /
anything else is authored as joint angles, not by redrawing pixels.

Angle convention (screen space, y grows downward): 0 = right (+x),
90 = down, -90 = up, 180 = left.  Sprites are authored facing **right**;
mirror the finished frames for the left-facing version.

* ``Bone.angle`` / ``Pose.angles`` - local angle relative to the parent bone.
* ``Pose.body`` - angle in *body space* (relative to the root's rotation,
  i.e. "world" angle while the character stands upright).  Usually the
  easiest way to author a pose: "upper arm points 45 deg forward-down".
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from .canvas import Grid
from .shading import Ink, Material, PartBuffer, Shader

Vec = Tuple[float, float]


def _rot(p: Vec, deg: float) -> Vec:
    a = math.radians(deg)
    c, s = math.cos(a), math.sin(a)
    return (p[0] * c - p[1] * s, p[0] * s + p[1] * c)


def _snap(v: float, odd: bool) -> float:
    """Snap so shapes keep a constant pixel width between frames."""
    return math.floor(v) + 0.5 if odd else float(round(v))


def lerp_angle(a: float, b: float, t: float) -> float:
    d = (b - a + 540.0) % 360.0 - 180.0
    return a + d * t


# --- bone state ---------------------------------------------------------------

@dataclass
class BoneState:
    bone: "Bone"
    start: Vec
    end: Vec
    angle: float      # world angle
    delta: float      # world angle minus rest world angle

    def point(self, t: float = 1.0, offset: Vec = (0.0, 0.0)) -> Vec:
        """Point at fraction ``t`` along the bone plus an offset given in the
        bone's *rest orientation* (it rotates with the bone)."""
        ox, oy = _rot(offset, self.delta)
        return (self.start[0] + (self.end[0] - self.start[0]) * t + ox,
                self.start[1] + (self.end[1] - self.start[1]) * t + oy)


# --- shapes -------------------------------------------------------------------

@dataclass
class Shape:
    material: Optional[Material] = None   # default: bone material
    z: float = 0.0                         # added to bone z
    level: Optional[int] = None            # force shade level
    group: Optional[str] = None            # default: bone group
    outline: bool = True

    def ink(self, bone: "Bone") -> Ink:
        return Ink(self.material or bone.material, self.group or bone.group or bone.name,
                   bone.z + self.z, bone.depth, self.level, bone.contour, self.outline)

    def draw(self, buf: Grid, st: BoneState, ink: Ink) -> None:  # pragma: no cover
        raise NotImplementedError


@dataclass
class Limb(Shape):
    """Round-capped thick segment along the bone (``t0``..``t1``)."""
    width: float = 2.0
    t0: float = 0.0
    t1: float = 1.0
    width_end: Optional[float] = None  # taper: draw as two halves

    def draw(self, buf, st, ink):
        odd = int(round(self.width)) % 2 == 1
        a = st.point(self.t0)
        b = st.point(self.t1)
        if self.width_end is not None and self.width_end != self.width:
            m = st.point((self.t0 + self.t1) / 2)
            odd2 = int(round(self.width_end)) % 2 == 1
            buf.capsule(_snap(a[0], odd), _snap(a[1], odd), _snap(m[0], odd), _snap(m[1], odd), self.width, ink)
            buf.capsule(_snap(m[0], odd2), _snap(m[1], odd2), _snap(b[0], odd2), _snap(b[1], odd2), self.width_end, ink)
            return
        if self.width <= 1:
            buf.line(a[0], a[1], b[0], b[1], ink)
        else:
            buf.capsule(_snap(a[0], odd), _snap(a[1], odd), _snap(b[0], odd), _snap(b[1], odd), self.width, ink)


@dataclass
class Blob(Shape):
    """Ellipse at fraction ``t`` along the bone, shifted by ``offset`` (rest frame).
    The ellipse itself is axis-aligned unless ``rotate`` is set."""
    rx: float = 2.0
    ry: float = 2.0
    t: float = 1.0
    offset: Vec = (0.0, 0.0)
    rotate: bool = False

    def draw(self, buf, st, ink):
        cx, cy = st.point(self.t, self.offset)
        if self.rotate and abs(self.rx - self.ry) > 0.01:
            pts = [_rot((self.rx * math.cos(a), self.ry * math.sin(a)), st.delta)
                   for a in (i * math.tau / 24 for i in range(24))]
            buf.polygon([(cx + x, cy + y) for x, y in pts], ink)
            return
        cx = _snap(cx, (round(self.rx * 2)) % 2 == 1)
        cy = _snap(cy, (round(self.ry * 2)) % 2 == 1)
        buf.ellipse(cx, cy, self.rx, self.ry, ink)


@dataclass
class Poly(Shape):
    """Polygon in the bone's rest frame, relative to the bone start."""
    points: Sequence[Vec] = ()

    def draw(self, buf, st, ink):
        pts = [st.point(0.0, p) for p in self.points]
        buf.polygon(pts, ink)


@dataclass
class Pixels(Shape):
    """Individual pixels (eyes, buckles, gems) relative to point ``t`` of the
    bone in the rest frame. Rounded after rotation, so they stay crisp."""
    points: Sequence[Vec] = ()
    t: float = 1.0

    def draw(self, buf, st, ink):
        for p in self.points:
            x, y = st.point(self.t, p)
            buf.plot(int(math.floor(x)), int(math.floor(y)), ink)


@dataclass
class Custom(Shape):
    """Arbitrary drawing: ``fn(buf, bone_state, ink)``."""
    fn: Callable = None

    def draw(self, buf, st, ink):
        self.fn(buf, st, ink)


# --- bones & rig --------------------------------------------------------------

@dataclass
class Bone:
    name: str
    parent: Optional[str]
    length: float = 0.0
    angle: float = 0.0                       # rest local angle
    material: Optional[Material] = None
    shapes: List[Shape] = field(default_factory=list)
    z: float = 0.0
    attach: float = 1.0                      # where on the parent this bone starts
    offset: Vec = (0.0, 0.0)                 # extra start offset (parent rest frame)
    group: Optional[str] = None              # shading volume (default: name)
    depth: int = 0                           # -1 = far side, drawn darker
    contour: bool = True
    ground: bool = False                     # used by Pose.ground (feet)
    world: Optional[float] = None            # rest angle given in body space instead of ``angle``


@dataclass
class Pose:
    angles: Dict[str, float] = field(default_factory=dict)   # local angles
    body: Dict[str, float] = field(default_factory=dict)     # body-space angles
    offsets: Dict[str, Vec] = field(default_factory=dict)    # screen-space start shifts
    root: Optional[Vec] = None
    rotation: float = 0.0
    ground: Optional[int] = None    # lock lowest ``ground`` bone pixel to this row
    ground_all: bool = False        # ...or the lowest pixel of the whole body (lying down)
    shift: Vec = (0, 0)             # applied after ground lock (lunges, knockback)
    hidden: frozenset = frozenset()
    fx: List[Callable] = field(default_factory=list)  # fn(buf, states, rig)
    duration: int = 100             # ms, used when the pose becomes a frame
    events: List[str] = field(default_factory=list)
    post: List[Callable] = field(default_factory=list)  # fn(canvas) -> canvas

    def copy(self, **kw) -> "Pose":
        p = Pose(dict(self.angles), dict(self.body), dict(self.offsets), self.root, self.rotation,
                 self.ground, self.ground_all, self.shift, self.hidden, list(self.fx), self.duration,
                 list(self.events), list(self.post))
        for k, v in kw.items():
            setattr(p, k, v)
        return p


class Rig:
    def __init__(self, width: int, height: int, origin: Vec, shader: Optional[Shader] = None):
        self.width, self.height = width, height
        self.origin = origin
        self.shader = shader or Shader()
        self.bones: Dict[str, Bone] = {}
        self._rest: Dict[str, float] = {}

    def add(self, bone: Bone) -> Bone:
        if bone.parent is not None and bone.parent not in self.bones:
            raise KeyError(f"parent {bone.parent!r} of {bone.name!r} not defined yet")
        if bone.world is not None:
            parent_world = self._rest_world()[bone.parent] if bone.parent else 0.0
            bone.angle = bone.world - parent_world
        self.bones[bone.name] = bone
        self._rest = {}
        return bone

    def bone(self, name: str, parent: Optional[str] = None, length: float = 0.0, **kw) -> Bone:
        return self.add(Bone(name, parent, length, **kw))

    # --- kinematics -----------------------------------------------------------
    def _rest_world(self) -> Dict[str, float]:
        if not self._rest:
            w: Dict[str, float] = {}
            for b in self.bones.values():
                w[b.name] = (w[b.parent] if b.parent else 0.0) + b.angle
            self._rest = w
        return self._rest

    def solve(self, pose: Optional[Pose] = None) -> Dict[str, BoneState]:
        pose = pose or Pose()
        rest = self._rest_world()
        out: Dict[str, BoneState] = {}
        for b in self.bones.values():
            if b.parent is None:
                start = pose.root or self.origin
                world = pose.body.get(b.name, pose.angles.get(b.name, b.angle)) + pose.rotation
                start = (start[0] + pose.offsets.get(b.name, (0, 0))[0],
                         start[1] + pose.offsets.get(b.name, (0, 0))[1])
            else:
                ps = out[b.parent]
                start = ps.point(b.attach, b.offset)
                o = pose.offsets.get(b.name)
                if o:
                    start = (start[0] + o[0], start[1] + o[1])
                if b.name in pose.body:
                    world = pose.body[b.name] + pose.rotation
                else:
                    world = ps.angle + pose.angles.get(b.name, b.angle)
            a = math.radians(world)
            end = (start[0] + math.cos(a) * b.length, start[1] + math.sin(a) * b.length)
            out[b.name] = BoneState(b, start, end, world, world - rest[b.name])
        return out

    def local_angles(self, pose: Pose) -> Dict[str, float]:
        """Resolve a pose (incl. body-space angles) to plain local angles."""
        st = self.solve(pose.copy(rotation=0.0))
        res = {}
        for b in self.bones.values():
            res[b.name] = st[b.name].angle - (st[b.parent].angle if b.parent else 0.0)
        return res

    def lerp(self, a: Pose, b: Pose, t: float) -> Pose:
        """Blend two poses (angles are interpolated the short way round)."""
        la, lb = self.local_angles(a), self.local_angles(b)
        p = (b if t >= 0.5 else a).copy()
        p.body = {}
        p.angles = {k: lerp_angle(la[k], lb[k], t) for k in la}
        keys = set(a.offsets) | set(b.offsets)
        p.offsets = {k: tuple(x + (y - x) * t for x, y in zip(a.offsets.get(k, (0, 0)), b.offsets.get(k, (0, 0))))
                     for k in keys}
        ra, rb = a.root or self.origin, b.root or self.origin
        p.root = (ra[0] + (rb[0] - ra[0]) * t, ra[1] + (rb[1] - ra[1]) * t)
        p.rotation = lerp_angle(a.rotation, b.rotation, t)
        p.shift = tuple(round(x + (y - x) * t) for x, y in zip(a.shift, b.shift))
        p.duration = round(a.duration + (b.duration - a.duration) * t)
        return p

    # --- rendering ------------------------------------------------------------
    def rasterize(self, pose: Optional[Pose] = None) -> PartBuffer:
        pose = pose or Pose()
        states = self.solve(pose)
        buf = PartBuffer(self.width, self.height)
        for b in self.bones.values():
            if b.name in pose.hidden:
                continue
            st = states[b.name]
            for s in b.shapes:
                s.draw(buf, st, s.ink(b))
        for fn in pose.fx:
            fn(buf, states, self)
        dx, dy = pose.shift
        if pose.ground is not None:
            probe = Grid(self.width, self.height * 3)  # tall: feet may hang below the frame
            for b in self.bones.values():
                if (b.ground or pose.ground_all) and b.name not in pose.hidden:
                    for s in b.shapes:
                        s.draw(probe, states[b.name], True)
            box = probe.bbox() or buf.bbox()
            if box:
                dy += pose.ground - box[3]
        if dx or dy:
            buf = buf.shifted(int(dx), int(dy))
        return buf

    def render(self, pose: Optional[Pose] = None):
        pose = pose or Pose()
        img = self.shader.render(self.rasterize(pose))
        for fn in pose.post:
            img = fn(img)
        return img
