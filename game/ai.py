"""Unit brains.

Every unit runs the same loop - *passives -> pick target (utility scores) ->
use ability -> attack or move* - but each role scores targets and positions
itself differently:

* **knight**    bodyguard: protects own shooters, taunts enemies diving them;
* **barbarian** executioner: hunts wounded enemies, cleaves, rages at low HP;
* **spearman**  anti-charge: prefers fast/charging enemies, keeps them at spear length;
* **orc**       frontline brute: war cry charge + stun, buffs nearby allies;
* **rogue**     assassin: flanks along the field edge to the backline, backstabs,
                vanishes in smoke when hurt;
* **archer**    kiter: keeps distance, retreats from melee, volleys clusters;
* **mage**      artillery: fireballs the densest cluster, frost-novas divers.

Melee attackers spread over both sides of a target ("slots"), so fights form
small surrounds instead of single-file queues.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, List, Optional, Tuple

if TYPE_CHECKING:  # pragma: no cover
    from .sim import Unit, World

from .sim import FIELD, Ring, Vfx

RETARGET = 0.35
DANGER = 50.0          # shooters start backing off when melee is this close


# --- helpers ------------------------------------------------------------------------

def _norm(x: float, y: float) -> Tuple[float, float]:
    d = math.hypot(x, y)
    return (0.0, 0.0) if d < 1e-6 else (x / d, y / d)


def _attackers(world: "World", target: "Unit", exclude: "Unit") -> List["Unit"]:
    return [a for a in world.units if a.alive and a.team != target.team and a is not exclude
            and a.target is target and not a.ranged]


def in_melee_range(u: "Unit", t: "Unit", slack: float = 0.0) -> bool:
    dx = abs(t.x - u.x)
    dy = abs(t.y - u.y)
    return dx <= u.type.attack_range + t.type.radius * 0.5 + slack and dy <= 7 + slack * 0.5


def in_range(u: "Unit", t: "Unit", slack: float = 0.0) -> bool:
    if u.ranged:
        return math.hypot(t.x - u.x, t.y - u.y) <= u.type.attack_range + slack
    return in_melee_range(u, t, slack)


def nearest_threat(world: "World", u: "Unit") -> Optional["Unit"]:
    best, bd = None, 1e9
    for e in world.enemies(u):
        if e.ranged:
            continue
        d = u.dist(e)
        if d < bd:
            best, bd = e, d
    return best


# --- target selection -------------------------------------------------------------------

def score(world: "World", u: "Unit", e: "Unit") -> float:
    d = u.dist(e)
    s = -d * (0.45 if u.key == "rogue" else 1.0)   # the assassin ignores distance to reach the backline
    s += u.type.prefers.get(e.key, 0.0)
    wounded = 1.0 - e.hp / e.max_hp
    s += wounded * (75.0 if u.key == "barbarian" else 30.0)
    if e is u.target:
        s += 25.0                                   # hysteresis: do not flip-flop
    if not u.ranged:
        crowd = len(_attackers(world, e, u))
        s -= max(0, crowd - 1) * 30.0               # spread out, don't all dogpile
    if u.key == "knight" and not e.ranged and e.target is not None and e.target.ranged \
            and e.target.team == u.team:
        s += 70.0                                   # bodyguard
    if u.key == "spearman" and (e.has("charge") or e.key == "rogue"):
        s += 30.0
    if u.key == "rogue":
        if e.key == "spearman":
            s -= 40.0
        if e.key == "knight":
            s -= 25.0
    if u.ranged:
        if in_range(u, e):
            s += 40.0
        if e.target is u:
            s += 25.0                               # shoot whoever is coming for me
        if e.key == "knight" and u.key == "archer":
            s -= 30.0                               # arrows bounce off the shield
    if u.key == "mage":
        cluster = sum(1 for o in world.enemies(u) if o is not e and math.hypot(o.x - e.x, o.y - e.y) < 26)
        s += cluster * 22.0
    return s + u.bias * 3.0


def pick_target(world: "World", u: "Unit") -> Optional["Unit"]:
    if u.taunted_by is not None and u.taunted_by.alive:
        return u.taunted_by
    cands = [e for e in world.enemies(u) if not e.has("stealth")]
    if not cands:
        return None
    return max(cands, key=lambda e: score(world, u, e))


# --- passives & abilities -------------------------------------------------------------------

def passives(world: "World", u: "Unit") -> None:
    if u.key == "barbarian" and not u.rage and u.hp < u.max_hp * 0.5:
        u.rage = True
        world.text(u, "ЯРОСТЬ!", "#e43b44", big=True, life=1.2)
        world.rings.append(Ring(u.x, u.y, 4, 26, "#e43b44", 0.4))
        world.burst(u.x, u.y, 18, "#e43b44", n=14, speed=50, up=80, life=0.6)
        world.sounds.append("rage")
    if u.rage and world.rng.random() < 0.25:
        world.burst(u.x + world.rng.uniform(-5, 5), u.y, 8, "#e43b44", n=1, speed=5, up=40,
                    life=0.5, gravity=-40)
    if u.key == "rogue" and not u.smoke_used and u.hp < u.max_hp * 0.35:
        u.smoke_used = True
        u.status["stealth"] = 2.6
        u.flee = 1.0
        world.text(u, "ДЫМ!", "#8b9bb4", big=True)
        world.burst(u.x, u.y, 8, "#8b9bb4", n=26, speed=45, up=30, life=0.9, gravity=-15, size=2)
        world.burst(u.x, u.y, 8, "#c0cbdc", n=14, speed=35, up=20, life=0.8, gravity=-10, size=2)
        for e in world.enemies(u):
            if e.target is u:
                e.target = None
        world.sounds.append("smoke")
    if u.has("charge") and world.rng.random() < 0.5:
        world.vfx.append(Vfx("dust", u.x - u.facing * 6, u.y - 6, flip=u.facing < 0))


def _try_abilities(world: "World", u: "Unit") -> bool:
    """Returns True if an ability consumed the turn."""
    if u.key == "orc" and u.abil.get("warcry", 0) <= 0:
        near = [e for e in world.enemies(u) if u.dist(e) < 115]
        if near:
            u.abil["warcry"] = 16.0
            u.status["charge"] = 3.0
            u.status["stunhit"] = 3.5
            world.text(u, "ВААГХ!", "#feae34", big=True, life=1.3)
            world.rings.append(Ring(u.x, u.y - 2, 6, 60, "#feae34", 0.55))
            world.add_shake(2.0)
            for a in world.allies(u) + [u]:
                if math.hypot(a.x - u.x, a.y - u.y) < 70:
                    a.status["warcry"] = 6.0
                    world.burst(a.x, a.y, 20, "#feae34", n=6, speed=20, up=50, life=0.6, gravity=-20)
            world.sounds.append("warcry")
            return False
    if u.key == "knight" and u.abil.get("taunt", 0) <= 0:
        for e in world.enemies(u):
            # only once the diver is actually on top of our shooter, so assassins get their moment
            if (not e.ranged and e.target is not None and e.target.team == u.team and e.target.ranged
                    and e.dist(e.target) < 34 and u.dist(e) < 95 and e.taunted_by is None
                    and not e.has("stealth")):
                e.taunted_by = u
                e.status["taunt"] = 3.5
                e.target = u
                u.target = e
                u.abil["taunt"] = 9.0
                world.text(u, "КО МНЕ!", "#2ce8f5", big=True)
                world.text(e, "!", "#fee761", big=True)
                world.rings.append(Ring(u.x, u.y, 4, 30, "#2ce8f5", 0.4))
                world.sounds.append("taunt")
                break
    if u.key == "rogue" and u.abil.get("step", 0) <= 0 and u.target is not None and u.target.ranged:
        t = u.target
        d = u.dist(t)
        if 18 < d < 75:
            # shadow step: vanish in smoke and reappear behind the shooter
            u.abil["step"] = 12.0
            world.burst(u.x, u.y, 8, "#5a6988", n=16, speed=35, up=25, life=0.6, gravity=-15, size=2)
            bx = t.x - t.facing * 11
            u.x = min(FIELD[2], max(FIELD[0], bx))
            u.y = t.y + (2 if u.y > t.y else -2)
            u.facing = 1 if t.x >= u.x else -1
            u.status["stealth"] = 0.7
            u.cd = 0.0
            world.burst(u.x, u.y, 8, "#8b9bb4", n=16, speed=35, up=25, life=0.6, gravity=-15, size=2)
            world.text(u, "ТЕНЬ!", "#c0cbdc", big=True)
            world.sounds.append("smoke")
            return False
    if u.key == "barbarian" and u.abil.get("leap", 0) <= 0 and u.target is not None:
        d = u.dist(u.target)
        if 35 < d < 95:
            u.abil["leap"] = 10.0
            u.status["charge"] = 1.4
            world.text(u, "НА ПРОРЫВ!", "#feae34")
            world.sounds.append("rage")
    if u.key == "mage" and u.abil.get("nova", 0) <= 0:
        close = [e for e in world.enemies(u) if not e.ranged and u.dist(e) < 30]
        if close:
            u.abil["nova"] = 9.0
            world.start_action(u, "nova", close[0], anim="cast", event="cast", cooldown=0.9)
            return True
    if u.key == "archer" and u.abil.get("volley", 0) <= 0 and u.cd <= 0:
        targets = [e for e in world.enemies(u) if in_range(u, e) and not e.has("stealth")]
        if len(targets) >= 2:
            u.abil["volley"] = 9.0
            world.start_action(u, "volley", u.target or targets[0])
            return True
    return False


def resolve_action(world: "World", u: "Unit", a: dict) -> None:
    t = a["target"]
    kind = a["kind"]
    rng = world.rng
    if kind == "nova":
        world.rings.append(Ring(u.x, u.y, 4, 38, "#2ce8f5", 0.5))
        world.rings.append(Ring(u.x, u.y, 2, 28, "#ffffff", 0.35))
        world.burst(u.x, u.y, 6, "#2ce8f5", n=24, speed=110, up=40, life=0.5)
        world.burst(u.x, u.y, 6, "#ffffff", n=10, speed=80, up=30, life=0.4)
        world.add_shake(1.5)
        world.sounds.append("nova")
        for e in world.enemies(u):
            d = math.hypot(e.x - u.x, (e.y - u.y) * 1.4)
            if d < 38:
                world.deal(u, e, 12, "magic")
                e.status["slow"] = 3.0
                nx, ny = (e.x - u.x) / (d + 0.1), (e.y - u.y) / (d + 0.1)
                e.x += nx * 12
                e.y += ny * 5
        u.flee = 1.4
        return
    if t is None or t.dead:
        return
    if kind == "volley":
        targets = [e for e in world.enemies(u) if in_range(u, e, 20) and not e.has("stealth")]
        targets.sort(key=lambda e: u.dist(e))
        picks = (targets[:3] + [t, t])[:3]
        world.text(u, "ЗАЛП!", "#fee761", big=True)
        for i, e in enumerate(picks):
            world.shoot_arrow(u, e, 0.75, spread=(i - 1) * 2.0)
        return
    if u.ranged:
        if u.key == "archer":
            world.shoot_arrow(u, t)
        else:
            world.cast_fireball(u, t)
        return
    # melee strike
    if not in_melee_range(u, t, slack=6):
        world.text(u, "МИМО", "#8b9bb4")
        return
    lo, hi = u.type.damage
    dmg = rng.uniform(lo, hi)
    crit = False
    label = None
    if u.key == "rogue":
        backstab = t.target is not u or (t.x - u.x) * t.facing > 0
        if backstab:
            dmg *= 1.9
            crit = True
            label = "В СПИНУ"
            t.status["bleed"] = 3.0
    elif rng.random() < 0.1:
        dmg *= 1.6
        crit = True
    if u.key == "barbarian" and t.hp < t.max_hp * 0.3:
        dmg *= 1.5
        crit = True
        label = "КАЗНЬ"
    if u.key == "spearman" and (t.has("charge") or t.key == "rogue"):
        dmg *= 1.6
        crit = True
        label = label or "ПРОТИВ РЫВКА"
    world.deal(u, t, dmg, "physical", crit=crit, label=label)
    fx_x = (u.x + t.x) / 2 + u.facing * 3
    world.vfx.append(Vfx("hit_spark", fx_x, t.y - 16 - rng.uniform(0, 6), flip=u.facing < 0))
    if u.key == "spearman" and t.alive:
        t.x += u.facing * 6
    if u.has("stunhit") and t.alive:
        del u.status["stunhit"]
        u.status.pop("charge", None)
        t.status["stun"] = 1.1
        t.action = None
        world.text(t, "ОГЛУШЁН", "#fee761", big=True)
        world.hitstop = max(world.hitstop, 0.09)
        world.add_shake(3.0)
        world.sounds.append("stun")
    elif u.has("charge"):
        u.status.pop("charge", None)
    if u.key == "barbarian":
        for e in world.enemies(u):
            if e is not t and abs(e.x - t.x) < 18 and abs(e.y - t.y) < 12:
                world.deal(u, e, dmg * 0.6, "physical")
                world.vfx.append(Vfx("hit_spark", e.x, e.y - 16))


# --- movement / decision -------------------------------------------------------------------

def think(world: "World", u: "Unit", dt: float) -> None:
    u.retarget -= dt
    if u.target is None or u.target.dead or u.target.has("stealth") or u.retarget <= 0:
        u.target = pick_target(world, u)
        u.retarget = RETARGET + u.bias * 0.15
    t = u.target
    if t is None:
        _move(u, 0, 0, dt)
        u.set_anim("idle")
        return

    if _try_abilities(world, u):
        return

    want_x, want_y = u.x, u.y
    if u.ranged:
        threat = nearest_threat(world, u)
        if (threat is not None and u.dist(threat) < DANGER and threat.target is u) or u.flee > 0:
            src = threat or t
            fx, fy = _norm(u.x - src.x, (u.y - src.y) * 1.5)
            home = -1 if u.team == 0 else 1
            fx += home * 0.6
            # cornered against an edge: slide along it instead
            if (u.x < FIELD[0] + 12 and fx < 0) or (u.x > FIELD[2] - 12 and fx > 0):
                fx = 0.0
                fy = 1.0 if u.y < (FIELD[1] + FIELD[3]) / 2 else -1.0
            if u.cd <= 0 and in_range(u, t) and threat is not None and u.dist(threat) > 22 and u.flee <= 0:
                world.start_action(u, "shot", t)       # turn and shoot while they close in
                return
            _move(u, fx, fy, dt)
            return
        if in_range(u, t):
            if u.cd <= 0:
                world.start_action(u, "shot", t, anim="cast" if u.key == "mage" else "attack",
                                   event="cast" if u.key == "mage" else "hit")
                return
            _move(u, 0, 0, dt)
            u.facing = 1 if t.x >= u.x else -1
            return
        want_x, want_y = t.x, t.y
    else:
        if u.flee > 0:   # rogue slipping away in smoke
            home = -1 if u.team == 0 else 1
            _move(u, home, 0.4 if u.y < t.y else -0.4, dt)
            return
        if in_melee_range(u, t):
            u.facing = 1 if t.x >= u.x else -1
            if u.cd <= 0:
                world.start_action(u, "strike", t)
                return
            _move(u, 0, (t.y - u.y) * 0.3, dt, scale=0.4)
            return
        want_x, want_y = _melee_slot(world, u, t)
        if u.key == "rogue" and t.ranged and abs(t.x - u.x) > 70:
            # flank: run along the nearest field edge before diving in
            edge = FIELD[1] + 4 if u.y < (FIELD[1] + FIELD[3]) / 2 else FIELD[3] - 4
            want_y = edge
    dx, dy = want_x - u.x, want_y - u.y
    if math.hypot(dx, dy) < 1.5:
        _move(u, 0, 0, dt)
        u.facing = 1 if t.x >= u.x else -1
        return
    nx, ny = _norm(dx, dy)
    _move(u, nx, ny, dt)


def _melee_slot(world: "World", u: "Unit", t: "Unit") -> Tuple[float, float]:
    """Stand beside the target; pick the less crowded side (surrounds form naturally)."""
    others = _attackers(world, t, u)
    left = sum(1 for o in others if o.x < t.x)
    right = len(others) - left
    my_side = -1 if u.x < t.x else 1
    if u.key == "rogue" and t.target is not None and t.target is not u:
        my_side = -t.facing or my_side     # get behind
    elif (my_side < 0 and left >= 2 and right < left) or (my_side > 0 and right >= 2 and left < right):
        my_side = -my_side
    reach = u.type.attack_range * 0.8 + t.type.radius * 0.5
    stack = left if my_side < 0 else right
    y_off = ((stack % 3) - 1) * 4.0
    return t.x + my_side * reach, t.y + y_off


def _move(u: "Unit", nx: float, ny: float, dt: float, scale: float = 1.0) -> None:
    sp = u.speed() * scale
    tvx, tvy = nx * sp, ny * sp * 0.75
    k = min(1.0, dt * 10.0)
    u.vx += (tvx - u.vx) * k
    u.vy += (tvy - u.vy) * k
    v = math.hypot(u.vx, u.vy)
    if v > 4.0:
        if abs(u.vx) > 2.0 and u.target is None:
            u.facing = 1 if u.vx > 0 else -1
        elif u.target is not None and abs(u.vx) > 2.0:
            # walk facing the movement unless backpedalling a short distance
            u.facing = 1 if u.vx > 0 else -1
        u.set_anim("walk", max(0.6, v / 38.0))
    else:
        u.set_anim("idle")
