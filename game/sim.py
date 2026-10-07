"""Battle simulation: units, combat rules, abilities, projectiles and the
effect events the renderer turns into pixels.  No pygame in here, so the
whole fight can run headless (tests, balance runs, recording).

Coordinates are logical screen pixels (480x270); ``y`` is depth on the
ground plane (bigger = closer to the camera) and units are drawn sorted by it.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .assets import AnimInfo
from .units import ORDER, ROSTER, TEAMS, Team, UnitType

W, H = 480, 270
FIELD = (16.0, 150.0, 464.0, 256.0)   # x0, y0, x1, y1 for unit feet
COUNTDOWN = 2.6


# --- small effect records (rendered by render.py) -----------------------------------

@dataclass
class FloatText:
    x: float
    y: float
    text: str
    color: str
    big: bool = False
    t: float = 0.0
    life: float = 0.9


@dataclass
class Particle:
    x: float
    y: float          # ground y
    z: float          # height above ground
    vx: float
    vy: float
    vz: float
    color: str
    life: float
    gravity: float = 260.0
    t: float = 0.0
    size: int = 1


@dataclass
class Ring:
    x: float
    y: float
    r0: float
    r1: float
    color: str
    life: float = 0.45
    t: float = 0.0


@dataclass
class Vfx:
    name: str          # explosion | hit_spark | dust | heal
    x: float
    y: float
    t: float = 0.0
    flip: bool = False


@dataclass
class Decal:
    kind: str          # scorch | arrow | blood
    x: float
    y: float
    angle: float = 0.0
    color: str = ""


@dataclass
class Projectile:
    kind: str          # arrow | fireball
    owner: "Unit"
    sx: float
    sy: float
    sz: float
    tx: float
    ty: float
    duration: float
    damage: float
    crit: bool = False
    target: Optional["Unit"] = None
    t: float = 0.0
    arc: float = 0.0
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    angle: float = 0.0
    done: bool = False


# --- units --------------------------------------------------------------------------

class Unit:
    _ids = 0

    def __init__(self, utype: UnitType, team: int, x: float, y: float, anims: Dict[str, AnimInfo]):
        Unit._ids += 1
        self.id = Unit._ids
        self.type = utype
        self.key = utype.key
        self.team = team
        self.x, self.y = x, y
        self.vx = self.vy = 0.0
        self.hp = float(utype.hp)
        self.max_hp = float(utype.hp)
        self.chip = self.hp           # delayed "damage trail" for the health bar
        self.anims = anims
        self.anim = "idle"
        self.anim_t = 0.0
        self.anim_speed = 1.0
        self.facing = 1 if team == 0 else -1
        self.state = "idle"
        self.target: Optional[Unit] = None
        self.retarget = 0.0
        self.cd = 0.0
        self.action: Optional[dict] = None
        self.status: Dict[str, float] = {}
        self.abil: Dict[str, float] = {}
        self.flash = 0.0
        self.flash_crit = False
        self.dead = False
        self.death_t = 0.0
        self.last_hit = -9.0
        self.dot_tick = 0.0
        self.dot_acc = 0.0
        self.dot_show = 0.0
        self.regen_acc = 0.0
        self.kills = 0
        self.dealt = 0.0
        self.taken = 0.0
        self.taunted_by: Optional[Unit] = None
        self.flee = 0.0               # seconds of forced retreat (mage after nova, rogue smoke)
        self.slot = 0.0
        self.rage = False
        self.smoke_used = False
        self.bias = random.random()   # replaced by world rng

    # convenience
    @property
    def alive(self) -> bool:
        return not self.dead

    @property
    def ranged(self) -> bool:
        return self.type.ranged

    def has(self, s: str) -> bool:
        return self.status.get(s, 0.0) > 0

    def speed(self) -> float:
        v = self.type.speed
        if self.has("slow"):
            v *= 0.5
        if self.has("charge"):
            v *= 1.9
        if self.has("stealth"):
            v *= 1.3
        return v

    def cooldown(self) -> float:
        return self.type.cooldown * (0.6 if self.rage else 1.0)

    def set_anim(self, name: str, speed: float = 1.0, restart: bool = False) -> None:
        if name != self.anim or restart:
            self.anim = name
            self.anim_t = 0.0
        self.anim_speed = speed

    def frame(self) -> int:
        return self.anims[self.anim].frame_at(self.anim_t)

    def dist(self, o: "Unit") -> float:
        return math.hypot(o.x - self.x, (o.y - self.y) * 1.4)


# --- world ----------------------------------------------------------------------------

class World:
    def __init__(self, anims: Dict[str, Dict[str, AnimInfo]], seed: int = 1, teams: Tuple[Team, Team] = TEAMS):
        self.rng = random.Random(seed)
        self.seed = seed
        self.teams = teams
        self.units: List[Unit] = []
        self.projectiles: List[Projectile] = []
        self.texts: List[FloatText] = []
        self.particles: List[Particle] = []
        self.rings: List[Ring] = []
        self.vfx: List[Vfx] = []
        self.decals: List[Decal] = []
        self.feed: List[Tuple[float, str, int, str]] = []   # (time, killer, team, victim)
        self.time = -COUNTDOWN
        self.shake = 0.0
        self.hitstop = 0.0
        self.slowmo = 0.0
        self.winner: Optional[int] = None
        self.end_time = 0.0
        self.sounds: List[str] = []   # event names for an optional audio layer
        self._spawn(anims)

    # formation: melee line in front, rogue on a flank, shooters behind.  Each
    # side shuffles its lanes per battle, so match-ups differ from fight to fight.
    def _spawn(self, anims) -> None:
        cy = (FIELD[1] + FIELD[3]) / 2
        melee_lanes = [(150, cy - 36), (145, cy - 8), (140, cy + 20), (150, cy + 46)]
        back_lanes = [(78, cy - 16), (70, cy + 18)]
        for team in (0, 1):
            tk = self.teams[team].key
            melee = melee_lanes[:]
            back = back_lanes[:]
            self.rng.shuffle(melee)
            self.rng.shuffle(back)
            layout = dict(zip(("knight", "barbarian", "spearman", "orc"), melee))
            layout.update(zip(("archer", "mage"), back))
            layout["rogue"] = (118, self.rng.choice((FIELD[1] + 6, FIELD[3] - 6)))
            for key in ORDER:
                x, y = layout[key]
                y += self.rng.uniform(-3, 3)
                if team == 1:
                    x = W - x
                u = Unit(ROSTER[key], team, x, y, anims[f"{key}_{tk}"])
                u.team_key = tk
                u.bias = self.rng.random()
                u.anim_t = self.rng.uniform(0, 1)
                self.units.append(u)

    # --- queries ----------------------------------------------------------------
    def enemies(self, u: Unit) -> List[Unit]:
        return [o for o in self.units if o.team != u.team and o.alive]

    def allies(self, u: Unit) -> List[Unit]:
        return [o for o in self.units if o.team == u.team and o.alive and o is not u]

    def alive_count(self, team: int) -> int:
        return sum(1 for u in self.units if u.team == team and u.alive)

    def team_hp(self, team: int) -> Tuple[float, float]:
        us = [u for u in self.units if u.team == team]
        return sum(max(0.0, u.hp) for u in us), sum(u.max_hp for u in us)

    # --- effects helpers --------------------------------------------------------
    def text(self, u_or_xy, text: str, color: str, big: bool = False, life: float = 0.9) -> None:
        if isinstance(u_or_xy, Unit):
            x, y = u_or_xy.x + self.rng.uniform(-3, 3), u_or_xy.y - 40
        else:
            x, y = u_or_xy
        # stack instead of overlapping: fresh texts near the same spot push this one up
        fresh = sum(1 for t in self.texts if t.t < 0.3 and abs(t.x - x) < 14 and abs(t.y - y) < 20)
        self.texts.append(FloatText(x, y - 7 * min(fresh, 3), text, color, big, 0.0, life))

    def burst(self, x, y, z, color, n=8, speed=60.0, up=60.0, life=0.5, gravity=260.0, size=1) -> None:
        for _ in range(n):
            a = self.rng.uniform(0, math.tau)
            s = self.rng.uniform(0.3, 1.0) * speed
            self.particles.append(Particle(x, y, z, math.cos(a) * s, math.sin(a) * s * 0.4,
                                           self.rng.uniform(0.3, 1.0) * up, color,
                                           life * self.rng.uniform(0.6, 1.2), gravity, 0.0, size))

    def add_shake(self, amount: float) -> None:
        self.shake = max(self.shake, amount)

    # --- combat -------------------------------------------------------------------
    def deal(self, src: Optional[Unit], dst: Unit, amount: float, dtype: str, *, crit: bool = False,
             ranged: bool = False, source_xy: Optional[Tuple[float, float]] = None, quiet: bool = False,
             label: Optional[str] = None) -> float:
        if dst.dead:
            return 0.0
        stunned = dst.has("stun")
        sx = source_xy[0] if source_xy else (src.x if src else dst.x)
        # dodge (rogue)
        if dtype == "physical" and not stunned and self.rng.random() < dst.type.dodge:
            self.text(dst, "УКЛОН", "#c0cbdc")
            self.sounds.append("dodge")
            return 0.0
        # knight shield: works against hits from the front
        if dst.key == "knight" and dtype == "physical" and not stunned:
            front = (sx - dst.x) * dst.facing >= -2
            if front and self.rng.random() < (0.6 if ranged else 0.3):
                self.text(dst, "БЛОК", "#2ce8f5")
                self.vfx.append(Vfx("hit_spark", dst.x + dst.facing * 6, dst.y - 18))
                self.burst(dst.x + dst.facing * 6, dst.y, 18, "#fee761", n=5, speed=50, up=40, life=0.3)
                self.sounds.append("block")
                if ranged:
                    return 0.0
                amount *= 0.3
        mult = 1.0
        if src is not None and src.has("warcry"):
            mult *= 1.2
        red = {"physical": dst.type.armor, "magic": dst.type.resist}.get(dtype, 0.0)
        dmg = max(1.0, amount * mult * (1.0 - red))
        dmg = round(dmg)
        dst.hp -= dmg
        dst.taken += dmg
        if dtype not in ("burn", "bleed"):
            dst.flash = 0.07
            dst.flash_crit = crit
        dst.last_hit = self.time
        if src is not None:
            src.dealt += dmg
            if src.rage and dtype == "physical" and not ranged:
                heal = dmg * 0.25
                src.hp = min(src.max_hp, src.hp + heal)
        if not quiet:
            col = {"magic": "#c08cff", "burn": "#feae34", "bleed": "#f6757a"}.get(dtype, "#ffffff")
            if crit:
                col = "#fee761"
            self.text(dst, (label + " " if label else "") + str(int(dmg)), col, big=crit,
                      life=0.6 if dtype in ("burn", "bleed") else 0.9)
        # blood / sparks
        if dtype == "physical":
            self.burst(dst.x, dst.y, 18, "#a22633", n=4 + int(dmg / 6), speed=55, up=70, life=0.5)
        if crit:
            self.hitstop = max(self.hitstop, 0.07)
            self.add_shake(2.0)
        self.sounds.append("hit")
        if dst.hp <= 0:
            self.kill(dst, src)
        return dmg

    def kill(self, u: Unit, src: Optional[Unit]) -> None:
        u.dead = True
        u.hp = 0
        u.state = "dead"
        u.status.clear()
        u.action = None
        u.set_anim("death", 1.0, restart=True)
        u.death_t = self.time
        self.burst(u.x, u.y, 14, "#a22633", n=14, speed=70, up=90, life=0.7)
        self.decals.append(Decal("blood", u.x + self.rng.uniform(-4, 4), u.y + 1))
        self.add_shake(1.5)
        if src is not None:
            src.kills += 1
        self.feed.append((self.time, src.type.name if src else "ОГОНЬ", u.team, u.type.name))
        self.sounds.append("death")
        for team in (0, 1):
            if self.alive_count(team) == 0 and self.winner is None:
                self.winner = 1 - team
                self.end_time = self.time
                self.slowmo = 1.6
        # orc war cry is also triggered by a fallen ally
        for a in self.allies(u):
            if a.key == "orc" and a.abil.get("warcry", 0) > 4:
                a.abil["warcry"] = 4

    # --- update -------------------------------------------------------------------
    def step(self, dt: float) -> None:
        # global time effects
        self.shake = max(0.0, self.shake - dt * 12)
        if self.hitstop > 0:
            self.hitstop -= dt
            self._step_effects(dt * 0.25)
            return
        if self.slowmo > 0:
            self.slowmo -= dt
            dt *= 0.35
        self.time += dt
        self._step_effects(dt)
        if self.time < 0:
            for u in self.units:
                u.anim_t += dt
            return
        for u in self.units:
            self._update_unit(u, dt)
        self._separate(dt)
        self._step_projectiles(dt)

    def _step_effects(self, dt: float) -> None:
        for t in self.texts:
            t.t += dt
        self.texts = [t for t in self.texts if t.t < t.life]
        for p in self.particles:
            p.t += dt
            p.x += p.vx * dt
            p.y += p.vy * dt
            p.vz -= p.gravity * dt
            p.z += p.vz * dt
            if p.z < 0:
                p.z = 0
                p.vz = -p.vz * 0.3
                p.vx *= 0.5
                p.vy *= 0.5
        self.particles = [p for p in self.particles if p.t < p.life]
        for r in self.rings:
            r.t += dt
        self.rings = [r for r in self.rings if r.t < r.life]
        for v in self.vfx:
            v.t += dt
        self.vfx = [v for v in self.vfx if v.t < 1.0]
        for u in self.units:
            u.flash = max(0.0, u.flash - dt)
            if u.chip > u.hp:
                if self.time - u.last_hit > 0.35:   # hold the trail briefly, then drain it
                    u.chip = max(u.hp, u.chip - max(12.0, (u.chip - u.hp) * 2.5) * dt)
            else:
                u.chip = u.hp

    def _update_unit(self, u: Unit, dt: float) -> None:
        info = u.anims[u.anim]
        u.anim_t += dt * u.anim_speed
        if u.dead:
            return
        # statuses
        for k in list(u.status):
            u.status[k] -= dt
            if u.status[k] <= 0:
                del u.status[k]
                if k == "taunt":
                    u.taunted_by = None
        for k in list(u.abil):
            u.abil[k] = max(0.0, u.abil[k] - dt)
        u.cd = max(0.0, u.cd - dt)
        u.flee = max(0.0, u.flee - dt)
        u.dot_tick += dt
        if u.dot_tick >= 0.5:
            u.dot_tick = 0.0
            if u.has("burn"):
                self.deal(None, u, 3, "burn", quiet=True)
                u.dot_acc += 3
                self.burst(u.x, u.y, 16, "#f77622", n=2, speed=10, up=40, life=0.4, gravity=-30)
                if u.dead:
                    return
            if u.has("bleed"):
                self.deal(None, u, 3, "bleed", quiet=True)
                u.dot_acc += 3
                self.burst(u.x, u.y, 14, "#a22633", n=2, speed=8, up=10, life=0.4)
                if u.dead:
                    return
            if u.key == "orc" and u.hp < u.max_hp:
                heal = 2.0 if self.time - u.last_hit < 2 else 4.0
                u.hp = min(u.max_hp, u.hp + heal)
                u.regen_acc += heal
                if u.regen_acc >= 12:
                    self.text(u, f"+{int(u.regen_acc)}", "#63c74d")
                    self.burst(u.x, u.y, 20, "#63c74d", n=4, speed=10, up=30, life=0.5, gravity=-30)
                    u.regen_acc = 0.0
            # damage over time is summed into one number per second
            u.dot_show += 0.5
            if u.dot_show >= 1.0:
                u.dot_show = 0.0
                if u.dot_acc > 0 and u.alive:
                    self.text(u, str(int(u.dot_acc)), "#feae34", life=0.6)
                    u.dot_acc = 0.0
        ai.passives(self, u)
        if u.has("stun"):
            u.action = None
            u.set_anim("hurt", 0.0)
            u.anim_t = 0.08     # recoil frame, frozen
            u.vx = u.vy = 0.0
            return

        # finishing an action
        if u.action is not None:
            a = u.action
            ev_t = a["event_t"]
            if not a["fired"] and ev_t is not None and u.anim_t >= ev_t:
                a["fired"] = True
                ai.resolve_action(self, u, a)
            if u.anim_t >= info.total:
                u.action = None
                u.set_anim("idle")
            else:
                u.vx *= 0.8
                u.vy *= 0.8
                return

        ai.think(self, u, dt)

    def start_action(self, u: Unit, kind: str, target: Optional[Unit], anim: str = "attack",
                     event: str = "hit", cooldown: Optional[float] = None) -> None:
        info = u.anims[anim]
        cd = u.cooldown() if cooldown is None else cooldown
        speed = max(1.0, info.total / max(0.2, cd * 0.92))
        u.set_anim(anim, speed, restart=True)
        if target is not None:
            u.facing = 1 if target.x >= u.x else -1
        u.action = {"kind": kind, "target": target, "fired": False, "event_t": info.event_time(event)}
        u.cd = cd
        u.vx = u.vy = 0.0

    def _separate(self, dt: float) -> None:
        alive = [u for u in self.units if u.alive]
        for i, a in enumerate(alive):
            for b in alive[i + 1:]:
                dx, dy = b.x - a.x, (b.y - a.y) * 1.6
                d = math.hypot(dx, dy)
                min_d = a.type.radius + b.type.radius
                if d < min_d:
                    if d < 1e-3:
                        dx, dy, d = self.rng.uniform(-1, 1), 1.0, 1.0
                    push = (min_d - d) * 0.5
                    nx, ny = dx / d, dy / d / 1.6
                    a.x -= nx * push
                    a.y -= ny * push
                    b.x += nx * push
                    b.y += ny * push
        for u in alive:
            u.x += u.vx * dt
            u.y += u.vy * dt
            u.x = min(FIELD[2], max(FIELD[0], u.x))
            u.y = min(FIELD[3], max(FIELD[1], u.y))

    # --- projectiles -----------------------------------------------------------------
    def shoot_arrow(self, u: Unit, target: Unit, dmg_mult: float = 1.0, spread: float = 0.0) -> None:
        sx, sy, sz = u.x + u.facing * 10, u.y, 19.0
        dist = math.hypot(target.x - sx, target.y - sy)
        dur = 0.18 + dist / 270.0
        # lead the target, with a bit of human error
        tx = target.x + target.vx * dur * 0.85 + self.rng.uniform(-3, 3) + spread
        ty = target.y + target.vy * dur * 0.85 + self.rng.uniform(-2, 2)
        lo, hi = u.type.damage
        crit = self.rng.random() < 0.2
        dmg = self.rng.uniform(lo, hi) * dmg_mult * (2.0 if crit else 1.0)
        self.projectiles.append(Projectile("arrow", u, sx, sy, sz, tx, ty, dur, dmg, crit, target,
                                           arc=min(40.0, dist * 0.16)))
        self.sounds.append("bow")

    def cast_fireball(self, u: Unit, target: Unit) -> None:
        sx, sy, sz = u.x + u.facing * 8, u.y, 36.0
        dist = math.hypot(target.x - sx, target.y - sy)
        dur = 0.25 + dist / 165.0
        tx = target.x + target.vx * dur * 0.6
        ty = target.y + target.vy * dur * 0.6
        lo, hi = u.type.damage
        self.projectiles.append(Projectile("fireball", u, sx, sy, sz, tx, ty, dur, self.rng.uniform(lo, hi),
                                           False, target))
        self.sounds.append("fireball")

    def _step_projectiles(self, dt: float) -> None:
        for p in self.projectiles:
            p.t += dt
            k = min(1.0, p.t / p.duration)
            if p.kind == "fireball" and p.target is not None and p.target.alive and k < 0.8:
                # gentle homing
                p.tx += (p.target.x - p.tx) * min(1.0, dt * 2.5)
                p.ty += (p.target.y - p.ty) * min(1.0, dt * 2.5)
            ox, oy = p.x, p.y - p.z
            p.x = p.sx + (p.tx - p.sx) * k
            p.y = p.sy + (p.ty - p.sy) * k
            if p.kind == "arrow":
                p.z = p.sz + (10.0 - p.sz) * k + p.arc * 4 * k * (1 - k)
            else:
                p.z = p.sz + (14.0 - p.sz) * k
                if self.rng.random() < 0.9:
                    self.particles.append(Particle(p.x, p.y, p.z, self.rng.uniform(-15, 15), 0,
                                                   self.rng.uniform(5, 25),
                                                   self.rng.choice(["#feae34", "#f77622", "#e43b44", "#5a6988"]),
                                                   0.35, -20.0))
            if p.t > dt:
                p.angle = math.degrees(math.atan2((p.y - p.z) - oy, p.x - ox))
            if k >= 1.0:
                p.done = True
                self._impact(p)
        self.projectiles = [p for p in self.projectiles if not p.done]

    def _impact(self, p: Projectile) -> None:
        owner = p.owner
        if p.kind == "arrow":
            victims = [u for u in self.units if u.alive and u.team != owner.team
                       and abs(u.x - p.x) < u.type.radius + 2 and abs(u.y - p.y) < 7]
            if victims:
                v = min(victims, key=lambda u: abs(u.x - p.x) + abs(u.y - p.y))
                self.deal(owner, v, p.damage, "physical", crit=p.crit, ranged=True,
                          source_xy=(p.sx, p.sy), label="КРИТ" if p.crit else None)
                self.vfx.append(Vfx("hit_spark", v.x, v.y - 18))
            else:
                self.decals.append(Decal("arrow", p.x, p.y, p.angle))
                self.burst(p.x, p.y, 0, "#b86f50", n=3, speed=20, up=20, life=0.3)
        else:
            self.vfx.append(Vfx("explosion", p.x, p.y - 14))
            self.decals.append(Decal("scorch", p.x, p.y))
            self.add_shake(3.0)
            self.burst(p.x, p.y, 10, "#fee761", n=10, speed=90, up=90, life=0.5)
            self.burst(p.x, p.y, 10, "#f77622", n=10, speed=70, up=110, life=0.7)
            self.sounds.append("explosion")
            for u in list(self.units):
                if u.alive and u.team != owner.team:
                    d = math.hypot(u.x - p.x, (u.y - p.y) * 1.5)
                    if d < 26:
                        k = 1.0 if d < 9 else 0.6
                        self.deal(owner, u, p.damage * k, "magic", source_xy=(p.x, p.y))
                        u.status["burn"] = 3.0
                        if u.alive and not u.ranged:
                            # small knock-away
                            nx = (u.x - p.x) / (d + 0.1)
                            u.x += nx * 4

    # --- summary ------------------------------------------------------------------
    def mvp(self) -> Optional[Unit]:
        if not self.units:
            return None
        return max(self.units, key=lambda u: u.dealt + u.kills * 60)


from . import ai  # noqa: E402  (ai imports names defined above)
