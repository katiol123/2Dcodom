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
from typing import Dict, List, Optional, Sequence, Tuple

from .assets import AnimInfo, Slot
from .units import ROSTER, TEAMS, Team, UnitType

W, H = 480, 270
FIELD = (16.0, 150.0, 464.0, 256.0)   # x0, y0, x1, y1 for unit feet
COUNTDOWN = 2.6
SUMMON_HP = 130
REVIVE_DELAY = 2.5


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
class Lightning:
    points: List[Tuple[float, float]]
    color: str = "#73eff7"
    life: float = 0.28
    t: float = 0.0


@dataclass
class Decal:
    kind: str          # scorch | arrow | blood
    x: float
    y: float
    angle: float = 0.0
    color: str = ""


@dataclass
class Projectile:
    kind: str          # arrow | bolt | fireball | dark | holy
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


TRAILS = {
    "fireball": ["#feae34", "#f77622", "#e43b44", "#5a6988"],
    "dark": ["#63c74d", "#265c42", "#68386c", "#181425"],
    "holy": ["#fee761", "#ffffff", "#ead4aa"],
}


# --- units --------------------------------------------------------------------------

class Unit:
    _ids = 0

    def __init__(self, utype: UnitType, team: int, x: float, y: float, anims: Dict[str, AnimInfo],
                 look: str = ""):
        Unit._ids += 1
        self.id = Unit._ids
        self.type = utype
        self.key = utype.key
        self.team = team
        self.team_key = TEAMS[team].key
        self.look = look
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
        self.last_dtype = ""
        self.last_blunt = False
        self.dot_tick = 0.0
        self.dot_acc = 0.0
        self.dot_show = 0.0
        self.regen_acc = 0.0
        self.kills = 0
        self.dealt = 0.0
        self.healed = 0.0
        self.taken = 0.0
        self.taunted_by: Optional[Unit] = None
        self.flee = 0.0               # seconds of forced retreat
        self.rage = False
        self.smoke_used = False
        self.bubble_used = False
        self.hits = 0                 # combo counters (monk, hammerer)
        self.summoned = False
        self.summoner: Optional[Unit] = None
        self.revive_at: Optional[float] = None
        self.revived = False
        self.rising = 0.0             # >0 while climbing out of the ground
        self.raised = False           # corpse consumed by a necromancer
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
        if name not in self.anims:
            name = "attack" if name == "cast" else "idle"
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
    """``slots``: one :class:`~game.assets.Slot` per unit; ``anims``: AnimInfo per look name;
    ``summon_looks``: look name of the necromancer's skeletons for each team (optional)."""

    def __init__(self, slots: Sequence[Slot], anims: Dict[str, Dict[str, AnimInfo]], seed: int = 1,
                 summon_looks: Optional[Dict[int, str]] = None, teams: Tuple[Team, Team] = TEAMS):
        self.rng = random.Random(seed)
        self.seed = seed
        self.teams = teams
        self.anims = anims
        self.summon_looks = summon_looks or {}
        self.units: List[Unit] = []
        self.projectiles: List[Projectile] = []
        self.texts: List[FloatText] = []
        self.particles: List[Particle] = []
        self.rings: List[Ring] = []
        self.vfx: List[Vfx] = []
        self.bolts: List[Lightning] = []
        self.decals: List[Decal] = []
        self.feed: List[Tuple[float, str, int, str]] = []   # (time, killer, team, victim)
        self.time = -COUNTDOWN
        self.hitstop = 0.0
        self.slowmo = 0.0
        self.winner: Optional[int] = None
        self.end_time = 0.0
        self.sounds: List[str] = []   # event names for an optional audio layer
        self._spawn(slots)

    # formation: melee line in front, flankers on the edges, shooters behind.
    def _spawn(self, slots: Sequence[Slot]) -> None:
        y0, y1 = FIELD[1] + 6, FIELD[3] - 6
        for team in (0, 1):
            mine = [s for s in slots if s.team == team]
            lanes = {"front": [], "flank": [], "back": []}
            for s in mine:
                lanes[ROSTER[s.key].lane].append(s)
            placed = []
            for lane, x in (("front", 148.0), ("back", 74.0)):
                group = lanes[lane]
                n = len(group)
                ys = [y0 + 8 + (y1 - y0 - 16) * (i + 0.5) / n for i in range(n)]
                self.rng.shuffle(ys)
                placed += [(s, x + self.rng.uniform(-6, 6), y) for s, y in zip(group, ys)]
            edges = [y0, y1]
            self.rng.shuffle(edges)
            for i, s in enumerate(lanes["flank"]):
                placed.append((s, 118.0 - (i // 2) * 14, edges[i % 2] + (i // 2) * (8 if edges[i % 2] == y0 else -8)))
            for s, x, y in placed:
                if team == 1:
                    x = W - x
                u = Unit(ROSTER[s.key], team, x, y + self.rng.uniform(-3, 3), self.anims[s.look], s.look)
                u.bias = self.rng.random()
                u.anim_t = self.rng.uniform(0, 1)
                self.units.append(u)

    def summon(self, necro: Unit, x: float, y: float) -> Optional[Unit]:
        look = self.summon_looks.get(necro.team)
        if look is None:
            return None
        u = Unit(ROSTER["skeleton"], necro.team, x, y, self.anims[look], look)
        u.summoned = True
        u.summoner = necro
        u.revived = True               # summons do not get the free revive
        u.hp = u.max_hp = u.chip = float(SUMMON_HP)
        u.rising = 0.6
        u.bias = self.rng.random()
        self.units.append(u)
        return u

    # --- queries ----------------------------------------------------------------
    def enemies(self, u: Unit) -> List[Unit]:
        return [o for o in self.units if o.team != u.team and o.alive and o.rising <= 0]

    def allies(self, u: Unit) -> List[Unit]:
        return [o for o in self.units if o.team == u.team and o.alive and o is not u]

    def alive_count(self, team: int) -> int:
        return sum(1 for u in self.units if u.team == team and u.alive)

    def standing(self, team: int) -> int:
        """Alive units plus skeletons that are about to get back up."""
        return sum(1 for u in self.units if u.team == team and (u.alive or u.revive_at is not None))

    def roster(self, team: int) -> List[Unit]:
        return [u for u in self.units if u.team == team and not u.summoned]

    def team_hp(self, team: int) -> Tuple[float, float]:
        us = self.roster(team)
        return sum(max(0.0, u.hp) for u in us), sum(u.max_hp for u in us)

    def corpses(self) -> List[Unit]:
        return [u for u in self.units if u.dead and not u.raised and u.revive_at is None
                and self.time - u.death_t > 1.0]

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

    # --- combat -------------------------------------------------------------------
    def deal(self, src: Optional[Unit], dst: Unit, amount: float, dtype: str, *, crit: bool = False,
             ranged: bool = False, source_xy: Optional[Tuple[float, float]] = None, quiet: bool = False,
             label: Optional[str] = None, pierce: bool = False) -> float:
        """Apply damage. dtype: physical | magic | holy | burn | bleed."""
        if dst.dead:
            return 0.0
        if dst.has("divine"):
            if not quiet:
                self.text(dst, "ЩИТ", "#fee761")
            return 0.0
        stunned = dst.has("stun")
        sx = source_xy[0] if source_xy else (src.x if src else dst.x)
        if dtype == "physical" and not stunned and self.rng.random() < dst.type.dodge:
            self.text(dst, "УКЛОН", "#c0cbdc")
            self.sounds.append("dodge")
            return 0.0
        # knight shield: works against hits from the front; crossbow bolts punch through
        if dst.key == "knight" and dtype == "physical" and not stunned and not pierce:
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
        blunt = bool(src is not None and src.type.blunt and dtype == "physical" and not ranged)
        if dst.type.undead and (blunt or dtype == "holy"):
            mult *= 1.5
        if dtype == "physical":
            red = dst.type.armor * (0.25 if pierce else 0.7 if blunt else 1.0)
        elif dtype in ("magic", "holy"):
            red = dst.type.resist
        else:
            red = 0.0
        dmg = round(max(1.0, amount * mult * (1.0 - red)))
        dst.hp -= dmg
        dst.taken += dmg
        dst.last_dtype = dtype
        dst.last_blunt = blunt
        if dtype not in ("burn", "bleed"):
            dst.flash = 0.07
            dst.flash_crit = crit
        dst.last_hit = self.time
        if src is not None:
            src.dealt += dmg
            if src.rage and dtype == "physical" and not ranged:
                self.heal(src, src, dmg * 0.25, quiet=True)
        if not quiet:
            col = {"magic": "#c08cff", "holy": "#fee761", "burn": "#feae34", "bleed": "#f6757a"}.get(dtype, "#ffffff")
            if crit:
                col = "#fee761"
            self.text(dst, (label + " " if label else "") + str(int(dmg)), col, big=crit,
                      life=0.6 if dtype in ("burn", "bleed") else 0.9)
        if dtype == "physical":
            blood = "#c0cbdc" if dst.type.undead else "#a22633"
            self.burst(dst.x, dst.y, 18, blood, n=4 + int(dmg / 6), speed=55, up=70, life=0.5)
        if crit:
            self.hitstop = max(self.hitstop, 0.07)
        self.sounds.append("hit")
        if dst.hp <= 0:
            if dst.key == "paladin" and not dst.bubble_used:
                dst.hp = 1                    # the divine shield saves him exactly once
                ai.divine_shield(self, dst)
            else:
                self.kill(dst, src)
        return dmg

    def heal(self, src: Optional[Unit], dst: Unit, amount: float, quiet: bool = False) -> float:
        if dst.dead:
            return 0.0
        amount = min(amount, dst.max_hp - dst.hp)
        if amount <= 0:
            return 0.0
        dst.hp += amount
        if src is not None and src is not dst:
            src.healed += amount
        if not quiet and amount >= 1:
            self.text(dst, f"+{int(amount)}", "#63c74d")
        return amount

    def kill(self, u: Unit, src: Optional[Unit]) -> None:
        u.dead = True
        u.hp = 0
        u.status.clear()
        u.action = None
        u.set_anim("death", 1.0, restart=True)
        u.death_t = self.time
        blood = "#c0cbdc" if u.type.undead else "#a22633"
        self.burst(u.x, u.y, 14, blood, n=14, speed=70, up=90, life=0.7)
        if not u.type.undead:
            self.decals.append(Decal("blood", u.x + self.rng.uniform(-4, 4), u.y + 1))
        if src is not None:
            src.kills += 1
        self.feed.append((self.time, src.type.name if src else "ОГОНЬ", u.team, u.type.name))
        self.sounds.append("death")
        # skeletons get back up unless smashed (blunt) or purified (holy)
        if u.key == "skeleton" and not u.revived and not (u.last_blunt or u.last_dtype == "holy"):
            u.revive_at = self.time + REVIVE_DELAY
        self._check_winner()
        for a in self.allies(u):
            if a.key == "orc" and a.abil.get("warcry", 0) > 4:
                a.abil["warcry"] = 4          # a fallen ally makes the orc roar sooner

    def _check_winner(self) -> None:
        for team in (0, 1):
            if self.standing(team) == 0 and self.winner is None:
                self.winner = 1 - team
                self.end_time = self.time
                self.slowmo = 1.6

    # --- update -------------------------------------------------------------------
    def step(self, dt: float) -> None:
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
        for u in list(self.units):
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
        for b in self.bolts:
            b.t += dt
        self.bolts = [b for b in self.bolts if b.t < b.life]
        for u in self.units:
            u.flash = max(0.0, u.flash - dt)
            if u.chip > u.hp:
                if self.time - u.last_hit > 0.35:   # hold the trail briefly, then drain it
                    u.chip = max(u.hp, u.chip - max(12.0, (u.chip - u.hp) * 2.5) * dt)
            else:
                u.chip = u.hp

    def _update_unit(self, u: Unit, dt: float) -> None:
        u.anim_t += dt * u.anim_speed
        if u.dead:
            if u.revive_at is not None and self.time >= u.revive_at:
                ai.revive(self, u)
            return
        if u.rising > 0:                      # climbing out of the ground: untouchable, idle
            u.rising -= dt
            return
        info = u.anims[u.anim]
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
            self._tick(u)
            if u.dead:
                return
        ai.passives(self, u)
        if u.has("stun"):
            u.action = None
            u.set_anim("hurt", 0.0)
            u.anim_t = 0.08     # recoil frame, frozen
            u.vx = u.vy = 0.0
            return

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

    def _tick(self, u: Unit) -> None:
        """Twice a second: damage/heal over time."""
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
            u.regen_acc += self.heal(u, u, heal, quiet=True)
        if u.key == "paladin":
            for a in self.allies(u) + [u]:
                if a.hp < a.max_hp and math.hypot(a.x - u.x, a.y - u.y) < 55:
                    a.regen_acc += self.heal(u, a, 0.8, quiet=True)
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

    def start_action(self, u: Unit, kind: str, target: Optional[Unit], anim: str = "attack",
                     event: str = "hit", cooldown: Optional[float] = None) -> None:
        if anim not in u.anims:
            anim, event = "attack", "hit"
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
                    # big bodies shove small ones
                    wa = b.type.radius / (a.type.radius + b.type.radius)
                    a.x -= nx * push * 2 * wa
                    a.y -= ny * push * 2 * wa
                    b.x += nx * push * 2 * (1 - wa)
                    b.y += ny * push * 2 * (1 - wa)
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

    def shoot_bolt(self, u: Unit, target: Unit) -> None:
        """Crossbow: fast, flat, accurate, pierces armor and shields."""
        sx, sy, sz = u.x + u.facing * 12, u.y, 18.0
        dist = math.hypot(target.x - sx, target.y - sy)
        dur = 0.08 + dist / 420.0
        tx = target.x + target.vx * dur + self.rng.uniform(-1.5, 1.5)
        ty = target.y + target.vy * dur + self.rng.uniform(-1, 1)
        lo, hi = u.type.damage
        self.projectiles.append(Projectile("bolt", u, sx, sy, sz, tx, ty, dur, self.rng.uniform(lo, hi), False,
                                           target, arc=min(8.0, dist * 0.04)))
        self.sounds.append("bow")

    def cast_orb(self, u: Unit, target: Unit, kind: str = "fireball", speed: float = 165.0) -> None:
        sx, sy, sz = u.x + u.facing * 8, u.y, 36.0
        dist = math.hypot(target.x - sx, target.y - sy)
        dur = 0.25 + dist / speed
        tx = target.x + target.vx * dur * 0.6
        ty = target.y + target.vy * dur * 0.6
        lo, hi = u.type.damage
        self.projectiles.append(Projectile(kind, u, sx, sy, sz, tx, ty, dur, self.rng.uniform(lo, hi),
                                           False, target))
        self.sounds.append("fireball" if kind == "fireball" else "nova")

    def cast_fireball(self, u: Unit, target: Unit) -> None:
        self.cast_orb(u, target, "fireball")

    def _step_projectiles(self, dt: float) -> None:
        for p in self.projectiles:
            p.t += dt
            k = min(1.0, p.t / p.duration)
            if p.kind in TRAILS and p.target is not None and p.target.alive and k < 0.8:
                # gentle homing for magic
                p.tx += (p.target.x - p.tx) * min(1.0, dt * 2.5)
                p.ty += (p.target.y - p.ty) * min(1.0, dt * 2.5)
            ox, oy = p.x, p.y - p.z
            p.x = p.sx + (p.tx - p.sx) * k
            p.y = p.sy + (p.ty - p.sy) * k
            if p.kind in ("arrow", "bolt"):
                p.z = p.sz + (10.0 - p.sz) * k + p.arc * 4 * k * (1 - k)
            else:
                p.z = p.sz + (14.0 - p.sz) * k
                if self.rng.random() < 0.9:
                    self.particles.append(Particle(p.x, p.y, p.z, self.rng.uniform(-15, 15), 0,
                                                   self.rng.uniform(5, 25), self.rng.choice(TRAILS[p.kind]),
                                                   0.35, -20.0))
            if p.t > dt:
                p.angle = math.degrees(math.atan2((p.y - p.z) - oy, p.x - ox))
            if k >= 1.0:
                p.done = True
                self._impact(p)
        self.projectiles = [p for p in self.projectiles if not p.done]

    def _victim_at(self, p: Projectile, slack: float = 2.0) -> Optional[Unit]:
        victims = [u for u in self.units if u.alive and u.team != p.owner.team and u.rising <= 0
                   and abs(u.x - p.x) < u.type.radius + slack and abs(u.y - p.y) < 7 + slack]
        return min(victims, key=lambda u: abs(u.x - p.x) + abs(u.y - p.y)) if victims else None

    def _impact(self, p: Projectile) -> None:
        owner = p.owner
        if p.kind in ("arrow", "bolt"):
            v = self._victim_at(p)
            if v is not None:
                self.deal(owner, v, p.damage, "physical", crit=p.crit, ranged=True, source_xy=(p.sx, p.sy),
                          label="КРИТ" if p.crit else None, pierce=p.kind == "bolt")
                self.vfx.append(Vfx("hit_spark", v.x, v.y - 18))
                if p.kind == "bolt" and v.alive:
                    v.x += 4 if p.tx > p.sx else -4      # heavy bolt knocks back
            else:
                self.decals.append(Decal("arrow", p.x, p.y, p.angle))
                self.burst(p.x, p.y, 0, "#b86f50", n=3, speed=20, up=20, life=0.3)
        elif p.kind == "fireball":
            self.vfx.append(Vfx("explosion", p.x, p.y - 14))
            self.decals.append(Decal("scorch", p.x, p.y))
            self.burst(p.x, p.y, 10, "#fee761", n=10, speed=90, up=90, life=0.5)
            self.burst(p.x, p.y, 10, "#f77622", n=10, speed=70, up=110, life=0.7)
            self.sounds.append("explosion")
            for u in list(self.units):
                if u.alive and u.team != owner.team and u.rising <= 0:
                    d = math.hypot(u.x - p.x, (u.y - p.y) * 1.5)
                    if d < 26:
                        k = 1.0 if d < 9 else 0.6
                        self.deal(owner, u, p.damage * k, "magic", source_xy=(p.x, p.y))
                        u.status["burn"] = 3.0
                        if u.alive and not u.ranged:
                            u.x += (u.x - p.x) / (d + 0.1) * 4
        else:  # dark / holy orbs: single target
            v = self._victim_at(p, slack=4.0)
            color = TRAILS[p.kind][0]
            self.burst(p.x, p.y, 14, color, n=12, speed=60, up=60, life=0.45)
            self.rings.append(Ring(p.x, p.y, 2, 12, color, 0.3))
            if v is not None:
                dealt = self.deal(owner, v, p.damage, "magic" if p.kind == "dark" else "holy", source_xy=(p.sx, p.sy))
                if p.kind == "dark" and owner.alive and dealt > 0:
                    got = self.heal(owner, owner, dealt * 0.5, quiet=True)
                    if got >= 3:
                        self.text(owner, f"+{int(got)}", "#63c74d")

    # --- summary ------------------------------------------------------------------
    def mvp(self) -> Optional[Unit]:
        if not self.units:
            return None
        return max(self.units, key=lambda u: u.dealt + u.healed + u.kills * 60)


from . import ai  # noqa: E402  (ai imports names defined above)
