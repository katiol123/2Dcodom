"""Builds every sprite the battle needs with PixelForge and caches the sheets.

Every unit gets its own seeded look (see :func:`game.units.look_for`); a look
is identified by a hash of its spec, and its sheet is written as PNG+JSON (the
engine's normal export) into ``.cache/battle/<engine hash>/``.  Missing sheets
are built in parallel worker processes by :class:`SpriteFactory`, which can
also prefetch the next battle in the background.
Nothing here imports pygame - the simulation only needs animation timings.
"""

from __future__ import annotations

import concurrent.futures as cf
import hashlib
import json
import math
import os
import random
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from pixelforge import fx as pfx
from pixelforge.canvas import Canvas
from pixelforge.color import mix, ramp, rgba
from pixelforge.export import save_sheet, sheet
from pixelforge.anim import Animation, Sprite
from pixelforge.shading import Ink, Material, PartBuffer, Shader
from pixelforge.units.creatures import QuadSpec, build_quadruped
from pixelforge.units.humanoid import HumanoidSpec, build_humanoid

from .units import TEAMS, Look, look_for

ROOT = Path(__file__).resolve().parent.parent
FROZEN = getattr(sys, "frozen", False)          # running from a PyInstaller .exe
APP_VERSION = "2.0"


def _user_cache_root() -> Path:
    """Writable per-user folder for the packaged game (sources are not shipped)."""
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Caches"
    else:
        base = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache")
    return base / "PixelForgeBattle"


CACHE = _user_cache_root() if FROZEN else ROOT / ".cache" / "battle"


@dataclass
class AnimInfo:
    name: str
    durations: List[int]          # ms per frame
    events: List[List[str]]
    loop: bool

    @property
    def total(self) -> float:
        return sum(self.durations) / 1000.0

    def event_time(self, event: str) -> Optional[float]:
        """Seconds from animation start to the start of the frame carrying ``event``."""
        t = 0
        for d, ev in zip(self.durations, self.events):
            if event in ev:
                return t / 1000.0
            t += d
        return None

    def frame_at(self, t: float) -> int:
        ms = t * 1000.0
        if self.loop:
            ms %= max(1, sum(self.durations))
        for i, d in enumerate(self.durations):
            if ms < d:
                return i
            ms -= d
        return len(self.durations) - 1


def _source_hash() -> str:
    if FROZEN:
        return "app-" + APP_VERSION
    h = hashlib.sha1()
    for p in sorted((ROOT / "pixelforge").rglob("*.py")):
        h.update(p.read_bytes())
    return h.hexdigest()[:12]


def cache_dir() -> Path:
    """Folder for generated sprites; its name changes whenever the art code does."""
    d = CACHE / _source_hash()
    d.mkdir(parents=True, exist_ok=True)
    return d


@dataclass(frozen=True)
class Slot:
    """One unit of a battle plan: its team, class and look (sprite sheet name)."""
    team: int
    key: str
    look: str


def look_name(key: str, team_key: str, spec: Look) -> str:
    digest = hashlib.sha1(repr(spec).encode("utf-8")).hexdigest()[:10]
    return f"{key}_{team_key}_{digest}"


def plan_battle(squads: Sequence[Sequence[str]], seed: int) -> Tuple[List[Slot], Dict[int, str], Dict[str, Look]]:
    """Seeded looks for every unit of both squads.

    Returns (slots, summon looks per team, {look name: spec}).  A team with a
    necromancer also gets the look its raised skeletons will wear."""
    slots: List[Slot] = []
    looks: Dict[str, Look] = {}
    summons: Dict[int, str] = {}
    for team, squad in enumerate(squads):
        t = TEAMS[team]
        for i, key in enumerate(squad):
            spec = look_for(key, t, seed * 131 + i * 17 + team * 7919)
            name = look_name(key, t.key, spec)
            looks[name] = spec
            slots.append(Slot(team, key, name))
        if "necromancer" in squad:
            spec = look_for("skeleton", t, seed * 131 + 999)
            name = look_name("skeleton", t.key, spec)
            looks[name] = spec
            summons[team] = name
    return slots, summons, looks


def build_sheet(name: str, spec: Look, out_dir: str) -> str:
    """Worker-process entry point: render one look's animations to PNG+JSON."""
    sprite = build_quadruped(spec) if isinstance(spec, QuadSpec) else build_humanoid(spec)
    save_sheet(sprite, os.path.join(out_dir, f"{name}.png"))
    return name


def _load_meta(out_dir: Path, name: str) -> dict:
    with open(out_dir / f"{name}.json", encoding="utf-8") as fh:
        meta = json.load(fh)
    meta["path"] = str(out_dir / f"{name}.png")
    return meta


class SpriteFactory:
    """Builds missing sheets in worker processes and caches the metadata."""

    def __init__(self, workers: Optional[int] = None):
        self.dir = cache_dir()
        self.metas: Dict[str, dict] = {}
        self.pending: Dict[str, cf.Future] = {}
        n = workers if workers is not None else min(4, os.cpu_count() or 1)
        self.pool: Optional[cf.ProcessPoolExecutor] = None
        if n > 1:
            try:
                self.pool = cf.ProcessPoolExecutor(max_workers=n)
            except (OSError, NotImplementedError):   # no multiprocessing available
                self.pool = None

    def _ready(self, name: str) -> bool:
        return (self.dir / f"{name}.json").exists() and (self.dir / f"{name}.png").exists()

    def prefetch(self, looks: Dict[str, Look]) -> None:
        """Start building in the background; returns immediately."""
        if self.pool is None:
            return
        for name, spec in looks.items():
            if name not in self.pending and not self._ready(name):
                self.pending[name] = self.pool.submit(build_sheet, name, spec, str(self.dir))

    def ensure(self, looks: Dict[str, Look],
               progress: Optional[Callable[[str, int, int], None]] = None) -> Dict[str, dict]:
        """Block until every look has a sheet; returns their metadata."""
        todo = [n for n in looks if not self._ready(n)]
        self.prefetch({n: looks[n] for n in todo})
        total = len(todo)
        for i, name in enumerate(todo):
            if progress:
                progress(name, i, total)
            fut = self.pending.pop(name, None)
            if fut is not None:
                try:
                    fut.result()
                except Exception:          # a broken worker: fall back to building here
                    build_sheet(name, looks[name], str(self.dir))
            elif not self._ready(name):
                build_sheet(name, looks[name], str(self.dir))
        out = {}
        for name in looks:
            if name not in self.metas:
                self.metas[name] = _load_meta(self.dir, name)
            out[name] = self.metas[name]
        return out

    def close(self) -> None:
        if self.pool is not None:
            self.pool.shutdown(wait=False, cancel_futures=True)


def ensure_unit_sheets(progress: Optional[Callable[[str, int, int], None]] = None) -> Dict[str, dict]:
    """Seed-0 looks of every class for both teams, keyed ``"knight_blue"`` (menus, tests)."""
    from .units import ALL
    looks = {}
    keys = {}
    for t in TEAMS:
        for k in ALL:
            spec = look_for(k, t, 0)
            name = look_name(k, t.key, spec)
            looks[name] = spec
            keys[f"{k}_{t.key}"] = name
    factory = SpriteFactory()
    try:
        metas = factory.ensure(looks, progress)
    finally:
        factory.close()
    return {short: metas[name] for short, name in keys.items()}


def anim_infos(meta: dict) -> Dict[str, AnimInfo]:
    return {name: AnimInfo(name, [f["duration"] for f in a["frames"]], [f["events"] for f in a["frames"]], a["loop"])
            for name, a in meta["animations"].items()}


# --- extra art made with the engine ---------------------------------------------

def arrow_canvas(angle_deg: float, length: int = 9, bolt: bool = False) -> Canvas:
    """Arrow (or a stubby steel crossbow bolt) pointing at ``angle_deg`` on a 13x13 canvas."""
    c = Canvas(13, 13)
    a = math.radians(angle_deg)
    dx, dy = math.cos(a), math.sin(a)
    cx = cy = 6
    tail = (round(cx - dx * length / 2), round(cy - dy * length / 2))
    head = (round(cx + dx * length / 2), round(cy + dy * length / 2))
    c.line(*tail, *head, "#8b9bb4" if bolt else "#b86f50")
    c.set(*head, "#ffffff")
    c.set(round(cx + dx * (length / 2 - 1)), round(cy + dy * (length / 2 - 1)), "#c0cbdc")
    # fletching: two light pixels beside the tail
    nx, ny = -dy, dx
    for s in (-1, 1):
        c.set(round(tail[0] + nx * s + dx), round(tail[1] + ny * s + dy), "#ead4aa")
    return c


def background(w: int, h: int, horizon: int, seed: int = 4) -> Canvas:
    """Sky gradient, two mountain ranges (atmospheric perspective), forest line,
    grass field with dirt patches, rocks, flowers and tufts."""
    rnd = random.Random(seed)
    c = Canvas(w, h)
    sky = [rgba(x) for x in ("#3a4466", "#5a6988", "#8b9bb4", "#c0cbdc", "#ead4aa")]
    for y in range(horizon):
        t = y / horizon
        for x in range(w):
            c.set(x, y, pfx.dither_pick(sky, t ** 1.2, x, y))
    # sun glow
    c.circle(w * 0.72, horizon * 0.42, 9, "#fee761")
    c.circle(w * 0.72, horizon * 0.42, 6, "#ffffff")
    # two mountain ranges; the far one lighter and bluer (atmospheric perspective)
    noise = pfx.ValueNoise(seed, period=16)
    for layer, (col, base, amp, freq) in enumerate((("#8b9bb4", 0.62, 0.42, 4.0), ("#5a6988", 0.86, 0.30, 7.0))):
        tones = ramp(col, 1, 1)
        snow = rgba("#ffffff") if layer == 0 else tones[2]
        for x in range(w):
            ridge = 1.0 - abs(noise.fbm(x / w * freq + layer * 3.7, layer * 1.3, 3) * 2 - 1)  # sharp crests
            top = int(horizon * (base - amp * ridge ** 1.6))
            # light from the left: slopes falling to the right are lit
            nxt = 1.0 - abs(noise.fbm((x + 1) / w * freq + layer * 3.7, layer * 1.3, 3) * 2 - 1)
            lit = nxt < ridge
            for y in range(top, horizon):
                depth = y - top
                if layer == 0 and depth < 3 and ridge > 0.8:
                    c.set(x, y, snow)
                elif depth < 6 and lit and pfx.bayer(x, y) < 0.8 - depth * 0.12:
                    c.set(x, y, tones[2])
                else:
                    c.set(x, y, tones[1] if depth > 1 else tones[2])
    # forest line on the horizon
    fr = ramp("#265c42", 2, 1)
    for x in range(-4, w + 4, 5):
        r = rnd.uniform(4, 7)
        cy = horizon - r * 0.6 + rnd.uniform(-1, 1)
        c.ellipse(x + 0.5, cy, r * 0.8, r, fr[1])
        c.ellipse(x - 0.5, cy - 1, r * 0.5, r * 0.7, fr[2])
    for x in range(w):
        for y in range(horizon - 2, horizon + 3):
            c.set(x, y, fr[0] if y >= horizon else c.get(x, y))
    # field
    g = ramp("#3e8948", 2, 2)
    d = ramp("#b86f50", 2, 1)
    fnoise = pfx.ValueNoise(seed + 1, period=12)
    for y in range(horizon + 3, h):
        depth = (y - horizon) / (h - horizon)        # 0 far .. 1 near
        for x in range(w):
            # calm ground: two close tones in big soft patches, so units stand out
            v = fnoise.fbm(x / 70, y / 35, 2)
            patch = fnoise(x / 70 + 5, y / 30 + 5)
            if patch > 0.72 and depth > 0.15:
                col = pfx.dither_pick(d[2:4], v, x, y)
            else:
                tones = g[1:3] if depth > 0.25 else g[0:2]
                col = pfx.dither_pick(tones, min(0.99, max(0.0, (v - 0.5) * 2.2 + 0.5)), x, y)
            c.set(x, y, col)
    # tufts / flowers / rocks, denser and bigger near the camera
    rock = Material.of("rock", "#8b9bb4")
    for _ in range(int(w * h / 700)):
        x, y = rnd.randrange(w), rnd.randrange(horizon + 6, h)
        k = rnd.random()
        if k < 0.7:
            c.set(x, y, g[3])
            c.set(x, y - 1, g[4] if rnd.random() < 0.3 else g[3])
            c.set(x + 1, y, g[1])
        elif k < 0.92:
            c.set(x, y, rnd.choice(["#fee761", "#ffffff", "#f6757a", "#2ce8f5"]))
        else:
            buf = PartBuffer(9, 7)
            r = 1.5 + (y - horizon) / (h - horizon) * 2
            buf.ellipse(4.5, 4, r + 0.5, r * 0.75, Ink(rock, "r"))
            c.blit(Shader().render(buf), x - 4, y - 4)
    return c


def scorch(r: int = 9) -> Canvas:
    """Burnt ground decal under an explosion."""
    c = Canvas(r * 2 + 2, r + 2)
    tones = [rgba("#181425"), rgba("#262b44"), rgba("#3e2731")]
    for y in range(c.height):
        for x in range(c.width):
            d = math.hypot((x + 0.5 - c.width / 2) / r, (y + 0.5 - c.height / 2) / (r / 2))
            if d < 1 and pfx.bayer(x, y) > d * 0.9:
                c.set(x, y, tones[min(2, int(d * 3))])
    return c


