"""Unit brains.

Every unit runs the same loop - *passives -> pick target (utility scores) ->
use ability -> attack or move* - but each role scores targets and positions
itself differently:

* **knight**      bodyguard: protects own shooters, taunts enemies diving them;
* **barbarian**   executioner: hunts wounded enemies, cleaves, rages at low HP;
* **spearman**    anti-charge: braces against an enemy charging *at him* and meets it with
                  the spear first (+100% damage, knockback, the charge is broken);
* **orc**         challenger: picks a fight with the toughest melee enemy, war cry charge;
* **rogue**       assassin: flanks along the field edge, shadow-steps behind shooters;
* **archer**      kiter: keeps distance, retreats from melee, volleys clusters;
* **mage**        artillery: fireballs the densest cluster, frost-novas divers;
* **paladin**     holy frontliner: healing aura, hunts undead, divine shield once;
* **cleric**      healer: keeps the most wounded ally alive, cleanses burns/bleeds;
* **crossbowman** armor breaker: picks the heaviest armor, holds the line (no kiting);
* **necromancer** vulture: walks to fresh corpses and raises them as skeletons;
* **skeleton**    death grip: never switches targets; gets back up unless smashed/purified;
* **monk**        interceptor: catches divers on own shooters, otherwise hunts enemy ones;
* **hammerer**    into the thick of it: goes for packed enemies, every 3rd blow quakes;
* **shaman**      storm caller: chain lightning, healing rain for the group;
* **wolf**        pack hunter: wolves gang up on the same prey, flank to the backline;
* **ogre**        crush: wades into the biggest crowd, sweeping club knocks back and stuns.

Melee attackers spread over both sides of a target ("slots"), so fights form
small surrounds instead of single-file queues.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, List, Optional, Tuple

if TYPE_CHECKING:  # pragma: no cover
    from .sim import Unit, World

from .sim import FIELD, Lightning, Ring, Vfx

RETARGET = 0.35
COUNTER_BONUS = 2.0    # spearman meeting a charge with the spear: +100% damage
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
    return dx <= u.type.attack_range + t.type.radius * 0.5 + slack and dy <= 7 + slack * 0.5 + u.type.radius * 0.2


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


def _bleed(t: "Unit", seconds: float) -> None:
    if not t.type.undead:
        t.status["bleed"] = max(t.status.get("bleed", 0.0), seconds)


# --- target selection -------------------------------------------------------------------

def score(world: "World", u: "Unit", e: "Unit") -> float:
    d = u.dist(e)
    divers = ("rogue", "wolf", "monk")
    s = -d * (0.45 if u.key in divers else 1.0)    # divers ignore distance to reach the backline
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
    if u.key == "spearman" and e.has("charge"):
        s += 70.0 if e.target is u else 30.0     # a charger coming at me is the best target
    if u.key in divers:
        if e.key == "spearman":
            s -= 15.0                           # long reach: an awkward target for divers
        if e.key in ("knight", "paladin"):
            s -= 25.0
    if u.key == "crossbowman":
        s += e.type.armor * 80.0                    # armor breaker
    if u.key in ("paladin", "cleric") and e.type.undead:
        s += 30.0
    if u.ranged:
        if in_range(u, e):
            s += 40.0
        if e.target is u:
            s += 25.0                               # shoot whoever is coming for me
        if e.key == "knight" and u.key == "archer":
            s -= 30.0                               # arrows bounce off the shield
    if u.key in ("mage", "shaman", "hammerer", "ogre"):
        # artillery / storm caller / "into the thick of it" / crush: go where the enemies are packed
        cluster = sum(1 for o in world.enemies(u) if o is not e and math.hypot(o.x - e.x, o.y - e.y) < 30)
        s += cluster * (22.0 if u.ranged else 20.0)
    if u.key == "orc" and not e.ranged:
        s += e.hp * 0.06                            # challenge the toughest fighter on the field
    if u.key == "monk" and not e.ranged and e.target is not None and e.target.ranged \
            and e.target.team == u.team:
        s += 80.0                                   # interceptor: catch divers on our shooters
    if u.key == "wolf" and any(a.key == "wolf" and a.target is e for a in world.allies(u)):
        s += 60.0                                   # pack hunt: the same prey as the other wolves
    if e.summoned:
        s -= 15.0                                   # minions are less important than their master
    return s + u.bias * 3.0


def pick_target(world: "World", u: "Unit") -> Optional["Unit"]:
    if u.taunted_by is not None and u.taunted_by.alive:
        return u.taunted_by
    t = u.target
    if u.key == "skeleton" and t is not None and t.alive and not t.has("stealth") and t.rising <= 0:
        return t                                    # death grip: never lets go of its victim
    cands = [e for e in world.enemies(u) if not e.has("stealth")]
    if not cands:
        return None
    return max(cands, key=lambda e: score(world, u, e))


def heal_target(world: "World", u: "Unit", reach: float) -> Optional["Unit"]:
    """Most wounded ally (incl. self) that is worth a heal."""
    best, bf = None, 0.85
    for a in world.allies(u) + [u]:
        frac = a.hp / a.max_hp
        if (frac < bf or (a.has("burn") or a.has("bleed")) and frac < 0.95) and u.dist(a) < reach and a.rising <= 0:
            best, bf = a, frac
    return best


# --- special events ------------------------------------------------------------------------

def divine_shield(world: "World", u: "Unit") -> None:
    u.bubble_used = True
    u.status["divine"] = 3.0
    u.status.pop("burn", None)
    u.status.pop("bleed", None)
    world.text(u, "БОЖЕСТВЕННЫЙ ЩИТ!", "#fee761", big=True, life=1.3)
    world.rings.append(Ring(u.x, u.y, 4, 30, "#fee761", 0.5))
    world.burst(u.x, u.y, 20, "#fee761", n=18, speed=40, up=60, life=0.7, gravity=-20)
    world.sounds.append("nova")


def revive(world: "World", u: "Unit") -> None:
    """A skeleton pulls itself back together at half health."""
    u.dead = False
    u.revived = True
    u.revive_at = None
    u.hp = u.chip = u.max_hp * 0.7
    u.rising = 0.6
    u.set_anim("idle")
    world.text(u, "ВОССТАЛ!", "#c0cbdc", big=True)
    world.burst(u.x, u.y, 4, "#ead4aa", n=14, speed=40, up=60, life=0.6)
    world.sounds.append("rage")


def chain_lightning(world: "World", u: "Unit", first: "Unit") -> None:
    lo, hi = u.type.damage
    dmg = world.rng.uniform(lo, hi)
    pts = [(u.x + u.facing * 8, u.y - 36)]
    hit: List["Unit"] = []
    cur: Optional["Unit"] = first
    for i in range(3):
        if cur is None:
            break
        pts.append((cur.x, cur.y - 16))
        hit.append(cur)
        world.deal(u, cur, dmg * (0.7 ** i), "magic")
        if cur.alive:
            cur.status["slow"] = max(cur.status.get("slow", 0.0), 1.5)
        world.burst(cur.x, cur.y, 16, "#73eff7", n=6, speed=40, up=40, life=0.3)
        nxt = [e for e in world.enemies(u) if e not in hit and math.hypot(e.x - cur.x, e.y - cur.y) < 60]
        cur = min(nxt, key=lambda e: math.hypot(e.x - hit[-1].x, e.y - hit[-1].y)) if nxt else None
    world.bolts.append(Lightning(pts))
    world.sounds.append("nova")


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
    if u.key == "paladin" and world.rng.random() < 0.06:
        world.burst(u.x + world.rng.uniform(-14, 14), u.y + world.rng.uniform(-4, 4), 2, "#fee761",
                    n=1, speed=2, up=25, life=0.6, gravity=-20)
    if u.has("divine") and world.rng.random() < 0.5:
        world.burst(u.x, u.y, 18, "#fee761", n=1, speed=20, up=20, life=0.4, gravity=-10)
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
            for a in world.allies(u) + [u]:
                if math.hypot(a.x - u.x, a.y - u.y) < 70:
                    a.status["warcry"] = 6.0
                    world.burst(a.x, a.y, 20, "#feae34", n=6, speed=20, up=50, life=0.6, gravity=-20)
            world.sounds.append("warcry")
            return False
    if u.key == "wolf" and u.abil.get("howl", 0) <= 0:
        if any(u.dist(e) < 130 for e in world.enemies(u)):
            u.abil["howl"] = 99.0
            world.text(u, "АУУУ!", "#c0cbdc", big=True)
            world.rings.append(Ring(u.x, u.y - 2, 4, 40, "#c0cbdc", 0.5))
            for a in world.allies(u) + [u]:
                if a.key == "wolf" and math.hypot(a.x - u.x, a.y - u.y) < 90:
                    a.status["charge"] = 1.3
                    a.abil["howl"] = 99.0
            world.sounds.append("warcry")
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
            u.x = min(FIELD[2], max(FIELD[0], t.x - t.facing * 11))
            u.y = t.y + (2 if u.y > t.y else -2)
            u.facing = 1 if t.x >= u.x else -1
            u.status["stealth"] = 0.7
            u.cd = 0.0
            world.burst(u.x, u.y, 8, "#8b9bb4", n=16, speed=35, up=25, life=0.6, gravity=-15, size=2)
            world.text(u, "ТЕНЬ!", "#c0cbdc", big=True)
            world.sounds.append("smoke")
            return False
    if u.key == "spearman" and u.cd <= 0.35:
        # brace: meet an enemy rushing at me with the spear before it reaches me
        for e in world.enemies(u):
            if charging_at(e, u) and in_melee_range(u, e, slack=10):
                world.start_action(u, "strike", e, cooldown=0.45)   # a quick thrust
                u.action["counter"] = True
                u.cd = u.cooldown()
                return True
    if u.key == "barbarian" and u.abil.get("leap", 0) <= 0 and u.target is not None:
        if 35 < u.dist(u.target) < 95:
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
    if u.key == "necromancer" and u.abil.get("raise", 0) <= 0 and u.cd <= 0.5:
        minions = sum(1 for m in world.units if m.summoner is u and m.alive)
        bodies = [c for c in world.corpses() if math.hypot(c.x - u.x, c.y - u.y) < 150 and not c.summoned]
        if minions < 2 and bodies:
            u.abil["raise"] = 6.0
            body = min(bodies, key=lambda c: math.hypot(c.x - u.x, c.y - u.y))
            world.start_action(u, "raise", body, anim="cast", event="cast", cooldown=1.2)
            return True
    if u.key == "shaman" and u.abil.get("rain", 0) <= 0 and u.cd <= 0.5:
        hurt = [a for a in world.allies(u) + [u] if a.hp < a.max_hp * 0.75 and math.hypot(a.x - u.x, a.y - u.y) < 90]
        if len(hurt) >= 2:
            u.abil["rain"] = 12.0
            world.start_action(u, "rain", u, anim="cast", event="cast", cooldown=1.0)
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
        world.sounds.append("nova")
        for e in world.enemies(u):
            d = math.hypot(e.x - u.x, (e.y - u.y) * 1.4)
            if d < 38:
                world.deal(u, e, 12, "magic")
                e.status["slow"] = 3.0
                e.x += (e.x - u.x) / (d + 0.1) * 12
                e.y += (e.y - u.y) / (d + 0.1) * 5
        u.flee = 1.4
        return
    if kind == "raise":
        if t is not None and t.dead and not t.raised:
            t.raised = True
            m = world.summon(u, t.x, t.y)
            if m is not None:
                world.text(m, "ВОССТАНЬ!", "#63c74d", big=True)
                world.burst(t.x, t.y, 4, "#63c74d", n=20, speed=40, up=70, life=0.8, gravity=-10)
                world.rings.append(Ring(t.x, t.y, 2, 22, "#63c74d", 0.5))
                world.sounds.append("smoke")
        return
    if kind == "rain":
        world.text(u, "ЦЕЛЕБНЫЙ ДОЖДЬ", "#63c74d", big=True)
        world.rings.append(Ring(u.x, u.y, 6, 70, "#63c74d", 0.6))
        for al in world.allies(u) + [u]:
            if math.hypot(al.x - u.x, al.y - u.y) < 90:
                world.heal(u, al, 25)
                world.vfx.append(Vfx("heal", al.x, al.y - 14))
        world.sounds.append("nova")
        return
    if kind == "heal":
        if t is not None and t.alive:
            lo, hi = 35, 45
            world.heal(u, t, rng.uniform(lo, hi))
            t.status.pop("burn", None)
            t.status.pop("bleed", None)
            world.vfx.append(Vfx("heal", t.x, t.y - 14))
            world.rings.append(Ring(t.x, t.y, 2, 14, "#fee761", 0.35))
            world.sounds.append("nova")
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
        elif u.key == "crossbowman":
            world.shoot_bolt(u, t)
        elif u.key == "mage":
            world.cast_orb(u, t, "fireball")
        elif u.key == "necromancer":
            world.cast_orb(u, t, "dark", speed=150)
        elif u.key == "cleric":
            world.cast_orb(u, t, "holy", speed=180)
        elif u.key == "shaman":
            chain_lightning(world, u, t)
        return
    _melee(world, u, t, counter=bool(a.get("counter")))


def charging_at(e: "Unit", u: "Unit") -> bool:
    """``e`` is in a rush (barbarian leap, orc war cry, wolf howl) aimed at ``u``."""
    return e.has("charge") and e.target is u


def _melee(world: "World", u: "Unit", t: "Unit", counter: bool = False) -> None:
    rng = world.rng
    if not in_melee_range(u, t, slack=6):
        world.text(u, "МИМО", "#8b9bb4")
        return
    lo, hi = u.type.damage
    dmg = rng.uniform(lo, hi)
    crit = False
    label = None
    u.hits += 1
    if u.key == "rogue":
        if t.target is not u or (t.x - u.x) * t.facing > 0:
            dmg *= 1.9
            crit = True
            label = "В СПИНУ"
            _bleed(t, 3.0)
    elif rng.random() < 0.1:
        dmg *= 1.6
        crit = True
    if u.key == "barbarian" and t.hp < t.max_hp * 0.3:
        dmg *= 1.5
        crit = True
        label = "КАЗНЬ"
    if counter:
        dmg *= COUNTER_BONUS
        crit = True
        label = "КОНТРУДАР"
    if u.key == "wolf":
        pack = sum(1 for a in world.allies(u) if a.key == "wolf" and math.hypot(a.x - u.x, a.y - u.y) < 60)
        dmg *= 1.0 + 0.2 * pack
        _bleed(t, 2.5)
    combo = (u.key == "monk" and u.hits % 4 == 0) or (u.key == "hammerer" and u.hits % 3 == 0)
    if combo and u.key == "monk":
        label, crit = "КОМБО", True
    world.deal(u, t, dmg, u.type.damage_type, crit=crit, label=label)
    fx_x = (u.x + t.x) / 2 + u.facing * 3
    world.vfx.append(Vfx("hit_spark", fx_x, t.y - 16 - rng.uniform(0, 6), flip=u.facing < 0))
    if counter:
        # the charge breaks on the spear: knocked back, the rush (and its stun) is lost
        t.status.pop("charge", None)
        t.status.pop("stunhit", None)
        if t.alive:
            t.x = min(FIELD[2], max(FIELD[0], t.x + u.facing * 20))
            t.vx = t.vy = 0.0
            t.action = None
        world.vfx.append(Vfx("dust", t.x, t.y - 6, flip=u.facing > 0))
        world.burst(t.x, t.y, 16, "#c0cbdc", n=8, speed=50, up=40, life=0.4)
    if u.key == "monk" and combo and t.alive:
        _stun(world, t, 0.7)
        t.x += u.facing * 10
    if u.key == "hammerer" and combo:
        world.text(u, "СОТРЯСЕНИЕ!", "#feae34", big=True)
        world.rings.append(Ring(t.x, t.y, 4, 34, "#b86f50", 0.45))
        world.rings.append(Ring(t.x, t.y, 2, 22, "#feae34", 0.35))
        world.burst(t.x, t.y, 2, "#b86f50", n=22, speed=90, up=60, life=0.6)
        for i in range(-2, 3):
            world.vfx.append(Vfx("dust", t.x + i * 9, t.y - 6, flip=i < 0))
        world.sounds.append("explosion")
        for e in world.enemies(u):
            if math.hypot(e.x - t.x, (e.y - t.y) * 1.4) < 30:
                if e is not t:
                    world.deal(u, e, dmg * 0.7, "physical")
                if e.alive:
                    _stun(world, e, 0.8, quiet=e is not t)
    if u.key == "ogre":
        for e in world.enemies(u):
            if e is not t and abs(e.x - t.x) < 18 and abs(e.y - t.y) < 12:
                world.deal(u, e, dmg * 0.5, "physical")
                e.x += u.facing * 6
        if t.alive:
            t.x += u.facing * 10
            if t.type.radius <= 7:
                _stun(world, t, 0.5)
        world.burst(t.x, t.y, 2, "#b86f50", n=10, speed=60, up=40, life=0.5)
    if u.has("stunhit") and t.alive:
        del u.status["stunhit"]
        u.status.pop("charge", None)
        _stun(world, t, 1.1)
        world.hitstop = max(world.hitstop, 0.09)
        world.sounds.append("stun")
    elif u.has("charge"):
        u.status.pop("charge", None)
    if u.key == "barbarian":
        for e in world.enemies(u):
            if e is not t and abs(e.x - t.x) < 18 and abs(e.y - t.y) < 12:
                world.deal(u, e, dmg * 0.6, "physical")
                world.vfx.append(Vfx("hit_spark", e.x, e.y - 16))


def _stun(world: "World", t: "Unit", seconds: float, quiet: bool = False) -> None:
    if t.dead or t.has("divine"):
        return
    t.status["stun"] = max(t.status.get("stun", 0.0), seconds)
    t.action = None
    if not quiet:
        world.text(t, "ОГЛУШЁН", "#fee761", big=True)


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

    if u.key == "cleric":
        h = heal_target(world, u, 200)
        if h is not None:
            if math.hypot(h.x - u.x, h.y - u.y) <= u.type.attack_range:
                if u.cd <= 0:
                    world.start_action(u, "heal", h, anim="cast", event="cast")
                    return
            elif not _threatened(world, u):
                nx, ny = _norm(h.x - u.x, h.y - u.y)
                _move(u, nx, ny, dt)
                return

    if u.key == "necromancer" and _scavenge(world, u, dt):
        return

    want_x, want_y = u.x, u.y
    if u.ranged:
        threat = nearest_threat(world, u)
        holds = u.key == "crossbowman"          # stands his ground
        if not holds and ((threat is not None and u.dist(threat) < DANGER and threat.target is u) or u.flee > 0):
            src = threat or t
            fx, fy = _norm(u.x - src.x, (u.y - src.y) * 1.5)
            home = -1 if u.team == 0 else 1
            fx += home * 0.6
            # cornered against an edge: slide along it instead
            if (u.x < FIELD[0] + 12 and fx < 0) or (u.x > FIELD[2] - 12 and fx > 0):
                fx = 0.0
                fy = 1.0 if u.y < (FIELD[1] + FIELD[3]) / 2 else -1.0
            if u.cd <= 0 and in_range(u, t) and threat is not None and u.dist(threat) > 22 and u.flee <= 0:
                _shoot(world, u, t)       # turn and shoot while they close in
                return
            _move(u, fx, fy, dt)
            return
        if in_range(u, t):
            if u.cd <= 0:
                _shoot(world, u, t)
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
        if u.key in ("rogue", "wolf", "monk") and t.ranged and abs(t.x - u.x) > 70:
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


def _scavenge(world: "World", u: "Unit", dt: float) -> bool:
    """Vulture: when a raise is nearly ready, walk toward the nearest fresh corpse
    that is not in the middle of enemy fighters."""
    if _threatened(world, u) or u.abil.get("raise", 0) > 2.0:
        return False
    if sum(1 for m in world.units if m.summoner is u and m.alive) >= 2:
        return False
    foes = [e for e in world.enemies(u) if not e.ranged]
    bodies = [c for c in world.corpses() if not c.summoned
              and all(math.hypot(e.x - c.x, e.y - c.y) > 35 for e in foes)]
    if not bodies:
        return False
    c = min(bodies, key=lambda b: math.hypot(b.x - u.x, b.y - u.y))
    d = math.hypot(c.x - u.x, c.y - u.y)
    if d <= 120 or d > 320:
        return False
    nx, ny = _norm(c.x - u.x, c.y - u.y)
    _move(u, nx, ny, dt)
    return True


def _threatened(world: "World", u: "Unit") -> bool:
    th = nearest_threat(world, u)
    return th is not None and u.dist(th) < DANGER and th.target is u


def _shoot(world: "World", u: "Unit", t: "Unit") -> None:
    if u.type.caster:
        world.start_action(u, "shot", t, anim="cast", event="cast")
    else:
        world.start_action(u, "shot", t)


def _melee_slot(world: "World", u: "Unit", t: "Unit") -> Tuple[float, float]:
    """Stand beside the target; pick the less crowded side (surrounds form naturally)."""
    others = _attackers(world, t, u)
    left = sum(1 for o in others if o.x < t.x)
    right = len(others) - left
    my_side = -1 if u.x < t.x else 1
    if u.key in ("rogue", "monk") and t.target is not None and t.target is not u:
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
        if abs(u.vx) > 2.0:
            u.facing = 1 if u.vx > 0 else -1
        u.set_anim("walk", max(0.6, v / 38.0))
    else:
        u.set_anim("idle")
