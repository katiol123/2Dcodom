"""Frames, animations, sprites and tweening helpers.

Timing guidelines baked into the unit builders (from common pixel-art practice):

* idle 4 frames, slow (~150-250 ms);   walk 8 frames (~90-110 ms);
* attack: anticipation (held longer) -> fast smear frame (40-60 ms) ->
  impact (held, emits the ``hit`` event) -> recovery;
* hurt: 1 white flash frame + recoil;  death: hit, fall, bounce, rest.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from .canvas import Canvas


@dataclass
class Frame:
    image: Canvas
    duration: int = 100            # ms
    events: List[str] = field(default_factory=list)


@dataclass
class Animation:
    name: str
    frames: List[Frame] = field(default_factory=list)
    loop: bool = True

    @property
    def duration(self) -> int:
        return sum(f.duration for f in self.frames)

    def add(self, image: Canvas, duration: int = 100, events: Sequence[str] = ()) -> "Animation":
        self.frames.append(Frame(image, duration, list(events)))
        return self

    def map(self, fn: Callable[[Canvas], Canvas], name: Optional[str] = None) -> "Animation":
        return Animation(name or self.name, [Frame(fn(f.image), f.duration, list(f.events)) for f in self.frames],
                         self.loop)

    def flipped(self) -> "Animation":
        return self.map(lambda c: c.flipped())

    def frame_at(self, t_ms: int) -> Frame:
        t = t_ms % self.duration if self.loop else min(t_ms, self.duration - 1)
        for f in self.frames:
            if t < f.duration:
                return f
            t -= f.duration
        return self.frames[-1]


@dataclass
class Sprite:
    name: str
    width: int
    height: int
    anchor: Tuple[int, int] = (0, 0)   # pivot, e.g. between the feet
    animations: Dict[str, Animation] = field(default_factory=dict)

    def add(self, anim: Animation) -> Animation:
        self.animations[anim.name] = anim
        return anim

    def __getitem__(self, name: str) -> Animation:
        return self.animations[name]

    def flipped(self, suffix: str = "") -> "Sprite":
        s = Sprite(self.name + suffix, self.width, self.height,
                   (self.width - 1 - self.anchor[0], self.anchor[1]))
        for a in self.animations.values():
            s.add(a.flipped())
        return s

    def map(self, fn: Callable[[Canvas], Canvas], name: Optional[str] = None) -> "Sprite":
        s = Sprite(name or self.name, self.width, self.height, self.anchor)
        for a in self.animations.values():
            s.add(a.map(fn))
        return s


# --- easing -------------------------------------------------------------------

def linear(t: float) -> float:
    return t


def ease_in(t: float) -> float:
    return t * t


def ease_out(t: float) -> float:
    return 1 - (1 - t) * (1 - t)


def ease_in_out(t: float) -> float:
    return 3 * t * t - 2 * t * t * t


def ping_pong(n: int) -> List[float]:
    """0..1..0 phases for ``n`` frames (breathing, bobbing)."""
    return [0.5 - 0.5 * math.cos(math.tau * i / n) for i in range(n)]


def tween(rig, keys: Sequence, frames: int, ease: Callable[[float], float] = ease_in_out):
    """Sample ``frames`` poses through key poses spaced evenly in time."""
    keys = list(keys)
    out = []
    segs = len(keys) - 1
    for i in range(frames):
        u = i / max(1, frames - 1) * segs
        k = min(int(u), segs - 1)
        out.append(rig.lerp(keys[k], keys[k + 1], ease(u - k)))
    return out


def from_poses(rig, name: str, poses: Iterable, loop: bool = True) -> Animation:
    anim = Animation(name, loop=loop)
    for p in poses:
        anim.add(rig.render(p), p.duration, p.events)
    return anim
