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

from .sim import FIELD, SUMMON_HP, Lightning, Ring, Vfx

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


def _poison(t: "Unit", seconds: float) -> None:
    if not t.type.undead:
        t.status["poison"] = max(t.status.get("poison", 0.0), seconds)


MAD_AURA = 75.0
DIVERS = ("rogue", "wolf", "monk", "wolf_rider", "wraith", "griffon_knight", "assassin", "vampire", "war_dog")
BODYGUARDS = ("knight", "treant", "halberdier", "shieldbearer")
CROWD_LOVERS = ("mage", "shaman", "hammerer", "ogre", "war_elephant", "fire_dervish", "goblin_bomber", "frost_giant")
COUNTERS = ("spearman", "halberdier", "militia", "uhlan")   # meet a charge at them with the polearm
CHARGERS = {  # key: (cooldown, min distance, max distance, rush seconds, text)
    "barbarian": (10.0, 35, 95, 1.4, "НА ПРОРЫВ!"), "wolf_rider": (9.0, 35, 110, 1.4, "НА ПРОРЫВ!"),
    "mamluk": (9.0, 40, 120, 1.4, "НАТИСК!"), "valkyrie": (10.0, 35, 100, 1.2, "С НЕБЕС!"),
    "lancer": (7.0, 45, 130, 1.6, "ТАРАН!"), "uhlan": (4.0, 45, 140, 1.3, "В ПИКИ!"),
}


def mad_aura(world: "World", u: "Unit") -> bool:
    """A mad goblin of u's side is close: goblins forget how to be afraid."""
    return any(a.key == "mad_goblin" and math.hypot(a.x - u.x, a.y - u.y) < MAD_AURA for a in world.allies(u))


# --- target selection -------------------------------------------------------------------

def score(world: "World", u: "Unit", e: "Unit") -> float:
    d = u.dist(e)
    if u.key in ("troll", "iron_golem", "bear", "zombie") or u.has("rampage"):   # straight ahead: whoever is closest
        return -d + (25.0 if e is u.target else 0.0) + u.bias * 3.0
    divers = DIVERS
    s = -d * (0.45 if u.key in divers else 1.0)    # divers ignore distance to reach the backline
    s += u.type.prefers.get(e.key, 0.0)
    wounded = 1.0 - e.hp / e.max_hp
    s += wounded * (75.0 if u.key in ("barbarian", "ghoul") else 30.0)
    if e is u.target:
        s += 25.0                                   # hysteresis: do not flip-flop
    if not u.ranged:
        crowd = len(_attackers(world, e, u))
        s -= max(0, crowd - 1) * 30.0               # spread out, don't all dogpile
    if u.key in BODYGUARDS and not e.ranged and e.target is not None and e.target.ranged \
            and e.target.team == u.team:
        s += 70.0                                   # bodyguard
    if u.key in COUNTERS and e.has("charge"):
        s += 70.0 if e.target is u else 30.0     # a charger coming at me is the best target
    if u.key in divers:
        if e.key == "spearman":
            s -= 15.0                           # long reach: an awkward target for divers
        if e.key in ("knight", "paladin"):
            s -= 25.0
    if u.key == "crossbowman":
        s += e.type.armor * 80.0                    # armor breaker
    if u.key == "alchemist":
        s += e.type.armor * 60.0                    # acid for the heaviest armor
    if u.key == "assassin":
        s += min(80.0, e.dealt * 0.15)              # head hunter: whoever has dealt the most damage
    if u.key == "duelist" and not e.ranged:
        s += min(70.0, e.dealt * 0.12)              # challenge the most dangerous fighter
    if u.key == "mamluk" and e.target is not None and e.target.team == u.team and e.target is not u:
        s += 40.0                                   # hit the flank of an enemy busy with my friends
    if u.key == "goblin_bomber":
        hurt = sum(1 - o.hp / o.max_hp for o in world.enemies(u) if math.hypot(o.x - e.x, o.y - e.y) < 30)
        s += hurt * 40.0                            # a blast finishes off a wounded crowd
    if u.key == "bog_spider" and (e.has("charge") or e.key in DIVERS):
        s += 30.0
    if e.key == "war_drummer" and (u.ranged or u.key in DIVERS):
        s += 40.0                                   # the drummer stands out
    if u.key in ("paladin", "cleric") and e.type.undead:
        s += 30.0
    if u.ranged:
        if in_range(u, e):
            s += 40.0
        if e.target is u:
            s += 25.0                               # shoot whoever is coming for me
        if e.key == "knight" and u.key == "archer":
            s -= 30.0                               # arrows bounce off the shield
    if u.key in CROWD_LOVERS:
        # artillery / storm caller / "into the thick of it" / crush: go where the enemies are packed
        cluster = sum(1 for o in world.enemies(u) if o is not e and math.hypot(o.x - e.x, o.y - e.y) < 30)
        s += cluster * (22.0 if u.ranged else 20.0)
    if u.key == "orc" and not e.ranged:
        s += e.hp * 0.06                            # challenge the toughest fighter on the field
    if u.key in ("monk", "bladedancer") and not e.ranged and e.target is not None and e.target.ranged \
            and e.target.team == u.team:
        s += 80.0                                   # interceptor: catch divers on our shooters
    if u.key == "mad_goblin" and e.target is not None and e.target.team == u.team and e.target.type.goblin:
        s += 60.0                                   # chieftain: whoever hits my goblins
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
    if u.key == "goblin":
        if u.has("panic") and mad_aura(world, u):
            del u.status["panic"]
            world.text(u, "!", "#e43b44", big=True)
        elif not u.panic_used and u.hp < u.max_hp * 0.3 and not mad_aura(world, u):
            u.panic_used = True
            u.status["panic"] = 8.0
            u.action = None
            world.text(u, "АААА!", "#ffffff", big=True)
            world.sounds.append("dodge")
    if u.has("panic") and world.rng.random() < 0.3:
        world.burst(u.x, u.y, 22, "#c0cbdc", n=1, speed=15, up=30, life=0.4)    # sweat drops
    if u.has("frenzy") and world.rng.random() < 0.3:
        world.burst(u.x + world.rng.uniform(-4, 4), u.y, 8, "#b55088", n=1, speed=5, up=40, life=0.5, gravity=-40)
    if u.key == "troll":
        _troll(world, u)
    if u.key in NEW_PASSIVES:
        NEW_PASSIVES[u.key](world, u)
    if u.key == "paladin" and world.rng.random() < 0.06:
        world.burst(u.x + world.rng.uniform(-14, 14), u.y + world.rng.uniform(-4, 4), 2, "#fee761",
                    n=1, speed=2, up=25, life=0.6, gravity=-20)
    if u.has("divine") and world.rng.random() < 0.5:
        world.burst(u.x, u.y, 18, "#fee761", n=1, speed=20, up=20, life=0.4, gravity=-10)
    if u.has("charge") and world.rng.random() < 0.5:
        world.vfx.append(Vfx("dust", u.x - u.facing * 6, u.y - 6, flip=u.facing < 0))


NEST_EVERY = 24.0
DUMB_EVERY = 6.0


def _troll(world: "World", u: "Unit") -> None:
    """Goblin nest, kicks and the occasional stupor."""
    u.abil.setdefault("nest", NEST_EVERY)
    u.abil.setdefault("dumb", DUMB_EVERY)
    if u.abil["nest"] <= 0:
        u.abil["nest"] = NEST_EVERY
        f = u.facing
        for dx, dy in ((f * 20, -5), (f * 20, 5), (-f * 20, -5), (-f * 20, 5)):   # 2 in front, 2 behind
            g = world.summon(u, u.x + dx, u.y + dy, "goblin")
            if g is not None:
                g.hop = 0.45
        world.text(u, "ГНЕЗДО!", "#a7f070")
        world.burst(u.x, u.y, 34, "#63c74d", n=10, speed=40, up=50, life=0.5)
        world.sounds.append("smoke")
    if u.abil["dumb"] <= 0:
        u.abil["dumb"] = DUMB_EVERY
        if world.rng.random() < 0.2 and not u.has("stupor"):
            u.status["stupor"] = 5.0
            u.action = None
            world.text(u, "...?", "#c0cbdc", big=True)
    # any cowardly goblin (of either side) that bumps into the troll may get kicked - once per goblin
    reach = u.type.radius + 8
    for g in world.units:
        if (g.key == "goblin" and g.alive and not g.kick_checked and g.hop <= 0 and g.rising <= 0
                and math.hypot(g.x - u.x, (g.y - u.y) * 1.4) <= reach):
            g.kick_checked = True
            if world.rng.random() < 0.25:
                world.kick(u, g)


def _frenzy_targets(world: "World", u: "Unit") -> List["Unit"]:
    """Up to two allies already in the thick of the fight (melee, next to their target)."""
    cands = [a for a in world.allies(u) if not a.ranged and not a.has("frenzy") and a.rising <= 0
             and math.hypot(a.x - u.x, a.y - u.y) < 140 and a.target is not None and in_melee_range(a, a.target, 8)]
    cands.sort(key=lambda a: math.hypot(a.x - u.x, a.y - u.y))
    return cands[:2]


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
    if u.key == "lancer" and u.has("charge"):
        # two knights at full gallop: lance against lance, nobody gets the first blow
        for e in world.enemies(u):
            if e.key == "lancer" and e.has("charge") and in_melee_range(u, e, slack=10):
                _joust(world, u, e)
                return True
    if u.key in COUNTERS and u.cd <= 0.35:
        # brace: meet an enemy rushing at me with the spear before it reaches me
        for e in world.enemies(u):
            if e.has("charge") and in_melee_range(u, e, slack=10):   # any rush that comes within reach
                if u.has("charge") and e.key in COUNTERS:      # two couched lances, head on
                    _joust(world, u, e)
                    return True
                # the braced spear meets the rush at once - a rusher would be past before a swing lands;
                # a rider's own rush ends in the counter (no double bonus)
                u.status.pop("lancehit", None)
                world.start_action(u, "strike", e, cooldown=0.45)
                u.action["fired"] = True
                _melee(world, u, e, counter=True)
                u.cd = u.cooldown()
                return True
    if u.key in CHARGERS and u.abil.get("leap", 0) <= 0 and u.target is not None:
        cd, lo, hi, secs, label = CHARGERS[u.key]
        if lo < u.dist(u.target) < hi:
            u.abil["leap"] = cd
            u.status["charge"] = secs
            if u.key in ("lancer", "uhlan"):
                u.status["lancehit"] = secs + 0.6
            if u.key == "mamluk":
                u.status["stunhit"] = secs + 0.6
            world.text(u, label, "#feae34")
            world.sounds.append("rage")
    if u.key in NEW_ABILITIES and NEW_ABILITIES[u.key](world, u):
        return True
    if u.key == "goblin_shaman" and u.abil.get("frenzy", 0) <= 0 and u.cd <= 0.5:
        picks = _frenzy_targets(world, u)
        if picks:
            u.abil["frenzy"] = 4.0
            world.start_action(u, "frenzy", picks[0], anim="cast", event="cast", cooldown=1.0)
            u.action["picks"] = picks
            return True
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
            u.abil["raise"] = 8.0
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
            m = world.summon(u, t.x, t.y, "skeleton", hp=SUMMON_HP, rising=0.6)
            if m is not None:
                world.text(m, "ВОССТАНЬ!", "#63c74d", big=True)
                world.burst(t.x, t.y, 4, "#63c74d", n=20, speed=40, up=70, life=0.8, gravity=-10)
                world.rings.append(Ring(t.x, t.y, 2, 22, "#63c74d", 0.5))
                world.sounds.append("smoke")
        return
    if kind == "frenzy":
        for al in a.get("picks", []):
            if al.alive:
                al.status["frenzy"] = 5.0
                world.text(al, "БЕШЕНСТВО!", "#b55088", big=True)
                world.rings.append(Ring(al.x, al.y, 2, 16, "#b55088", 0.4))
                world.burst(al.x, al.y, 16, "#b55088", n=10, speed=30, up=50, life=0.6, gravity=-20)
        world.sounds.append("rage")
        return
    if kind in NEW_ACTIONS:
        NEW_ACTIONS[kind](world, u, t, a)
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
            lo, hi = (25, 32) if u.key == "dryad" else (35, 45)
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
        elif u.key == "goblin_shaman":
            world.cast_orb(u, t, "spore", speed=140)
        else:
            _new_shot(world, u, t, a)
        return
    _melee(world, u, t, counter=bool(a.get("counter")))


def _joust(world: "World", a: "Unit", b: "Unit") -> None:
    """Two riders with lances (uhlans, or mounted knights) rushing at each other: both lances strike at once (counter damage), both riders are
    thrown back and shaken, both rushes are spent - and both ride off for another run-up."""
    world.text(a, "СШИБКА!", "#feae34", big=True)
    world.hitstop = max(world.hitstop, 0.1)
    world.sounds.append("block")
    hits = []
    for u, t in ((a, b), (b, a)):
        lo, hi = u.type.damage
        hits.append((u, t, world.rng.uniform(lo, hi) * COUNTER_BONUS))
    for u, t, dmg in hits:                           # simultaneous: nobody strikes first
        u.facing = 1 if t.x >= u.x else -1
        for k in ("charge", "lancehit", "stunhit"):
            u.status.pop(k, None)
        u.action = None
        u.cd = u.cooldown()
        world.deal(u, t, dmg, u.type.damage_type, crit=True, label="СШИБКА")
    for u, t, _ in hits:
        if u.alive:
            u.x = min(FIELD[2], max(FIELD[0], u.x - u.facing * 14))
            u.vx = u.vy = 0.0
            _stun(world, u, 0.4, quiet=True)
            u.status["regroup"] = 1.2
    world.burst((a.x + b.x) / 2, (a.y + b.y) / 2, 14, "#feae34", n=14, speed=60, up=40, life=0.5)


def charging_at(e: "Unit", u: "Unit") -> bool:
    """``e`` is in a rush (barbarian leap, orc war cry, wolf howl) aimed at ``u``."""
    return e.has("charge") and e.target is u


def _melee(world: "World", u: "Unit", t: "Unit", counter: bool = False) -> None:
    rng = world.rng
    if not in_melee_range(u, t, slack=12 if counter else 6):   # a braced spear covers its whole reach
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
    if u.key == "goblin_bomber":
        explode(world, u, 1.0)
        return
    if u.key == "barbarian" and t.hp < t.max_hp * 0.3:
        dmg *= 1.4
        crit = True
        label = "КАЗНЬ"
    if counter:
        dmg *= COUNTER_BONUS
        crit = True
        label = "КОНТРУДАР"
    if u.key == "goblin":
        if t.target is not u:
            dmg *= 1.5
            crit = True
            label = "ИСПОДТИШКА"
        crowd = sum(1 for a in world.allies(u) if a.type.goblin and math.hypot(a.x - u.x, a.y - u.y) < 50)
        dmg *= 1.0 + 0.1 * min(3, crowd)
        _poison(t, 4.0)
    if u.key == "mad_goblin":
        _bleed(t, 3.0)
    dmg, crit, label = _new_melee_mods(world, u, t, dmg, crit, label)
    if u.key == "wolf":
        pack = sum(1 for a in world.allies(u) if a.key == "wolf" and math.hypot(a.x - u.x, a.y - u.y) < 60)
        dmg *= 1.0 + 0.2 * pack
        _bleed(t, 2.5)
    combo = (u.key == "monk" and u.hits % 4 == 0) or (u.key == "hammerer" and u.hits % 3 == 0)
    if combo and u.key == "monk":
        label, crit = "КОМБО", True
    world.deal(u, t, dmg, u.type.damage_type, crit=crit, label=label, unblockable=u.key == "halberdier",
               fire=u.key == "fire_dervish")
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
            _stun(world, t, 0.6, quiet=True)                 # thrown off its feet
            if not t.ranged and t.taunted_by is None:        # and it turns on the one who stabbed it
                t.target = u
                t.taunted_by = u
                t.status["taunt"] = 1.5
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
    _new_melee_after(world, u, t, dmg)
    if u.has("stunhit") and t.alive:
        del u.status["stunhit"]
        u.status.pop("charge", None)
        _stun(world, t, 0.8 if u.key == "mamluk" else 1.1)
        world.hitstop = max(world.hitstop, 0.09)
        world.sounds.append("stun")
    elif u.has("charge"):
        u.status.pop("charge", None)
    if u.key == "barbarian":
        for e in world.enemies(u):
            if e is not t and abs(e.x - t.x) < 18 and abs(e.y - t.y) < 12:
                world.deal(u, e, dmg * 0.5, "physical")
                world.vfx.append(Vfx("hit_spark", e.x, e.y - 16))


def _stun(world: "World", t: "Unit", seconds: float, quiet: bool = False) -> None:
    if t.dead or t.has("divine") or "stun" in t.type.immune:
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

    if _special_move(world, u, t, dt):
        return

    if u.has("panic") or u.has("fear"):      # cowardly goblin running for its life / banshee's scream
        threat = nearest_threat(world, u) or t
        sx_, sy_ = (threat.x, threat.y) if u.has("panic") else u.fear_src
        fx, fy = _norm(u.x - sx_, (u.y - sy_) * 1.5)
        fx += -0.8 if u.team == 0 else 0.8
        if (u.x < FIELD[0] + 12 and fx < 0) or (u.x > FIELD[2] - 12 and fx > 0):
            fx, fy = 0.0, (1.0 if u.y < (FIELD[1] + FIELD[3]) / 2 else -1.0)
        nx, ny = _norm(fx, fy)
        _move(u, nx, ny, dt)
        return

    if _try_abilities(world, u):
        return

    if u.key in ("cleric", "dryad"):
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
    if _new_positioning(world, u, t, dt):
        return

    want_x, want_y = u.x, u.y
    if u.ranged:
        threat = nearest_threat(world, u)
        holds = u.key in ("crossbowman", "frost_giant")          # stands his ground
        danger = 80.0 if u.key == "horse_archer" else DANGER
        kiting = (threat is not None and u.dist(threat) < danger and threat.target is u) or u.flee > 0
        if kiting and not holds and u.has("cornered"):
            # pinned against the edge: stop running in circles and fight back point-blank
            u.facing = 1 if t.x >= u.x else -1
            if u.cd <= 0 and in_range(u, t, 10):
                _shoot(world, u, t)
                return
            _move(u, 0, 0, dt)
            u.facing = 1 if t.x >= u.x else -1
            return
        if not holds and kiting:
            src = threat or t
            # did the last steps actually get us anywhere? if not, we are cornered
            px, py = u.kite_pos
            moved = math.hypot(u.x - px, u.y - py)
            u.kite_pos = (u.x, u.y)
            u.stuck = u.stuck + dt if moved < u.speed() * dt * 0.35 else max(0.0, u.stuck - dt * 2)
            if u.stuck > 0.35:
                u.stuck = 0.0
                u.status["cornered"] = 2.0
            fx, fy = _norm(u.x - src.x, (u.y - src.y) * 1.5)
            home = -1 if u.team == 0 else 1
            fx += home * 0.6
            # cornered against an edge: slide along it instead
            if (u.x < FIELD[0] + 12 and fx < 0) or (u.x > FIELD[2] - 12 and fx > 0):
                fx = 0.0
                fy = 1.0 if u.y < (FIELD[1] + FIELD[3]) / 2 else -1.0
            if u.key == "horse_archer" and u.cd <= 0 and in_range(u, t):
                _shoot(world, u, t)       # shooting at full gallop: keeps riding away
                u.vx, u.vy = fx * u.speed() * 0.9, fy * u.speed() * 0.6
                u.action["moving"] = True
                return
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
        if u.key in DIVERS and t.ranged and abs(t.x - u.x) > 70 and not u.type.incorporeal:
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


# ================================================================================================
# Units of the eight realms (griffon knight ... iron golem): passives, abilities, shots, melee.
# ================================================================================================

def _home(u: "Unit") -> int:
    return -1 if u.team == 0 else 1


def _near(world: "World", u: "Unit", units, r: float) -> List["Unit"]:
    return [o for o in units if math.hypot(o.x - u.x, (o.y - u.y) * 1.4) < r]


def explode(world: "World", u: "Unit", power: float) -> None:
    """Goblin bomber goes off: full damage to enemies around, half to friends."""
    if u.exploded:
        return
    u.exploded = True
    lo, hi = u.type.damage
    dmg = world.rng.uniform(lo, hi) * power
    world.vfx.append(Vfx("explosion", u.x, u.y - 14))
    world.decals.append(__import__("game.sim", fromlist=["Decal"]).Decal("scorch", u.x, u.y))
    world.burst(u.x, u.y, 10, "#fee761", n=16, speed=110, up=100, life=0.6)
    world.burst(u.x, u.y, 10, "#3a4466", n=12, speed=70, up=120, life=0.8, size=2)
    world.rings.append(Ring(u.x, u.y, 4, 36, "#feae34", 0.4))
    world.text(u, "БАБАХ!", "#feae34", big=True, life=1.2)
    world.hitstop = max(world.hitstop, 0.08)
    world.sounds.append("explosion")
    for o in list(world.units):
        if o is u or o.dead or o.rising > 0:
            continue
        d = math.hypot(o.x - u.x, (o.y - u.y) * 1.4)
        if d < 36:
            k = 1.0 if o.team != u.team else 0.35
            world.deal(u, o, dmg * k * (1.0 if d < 14 else 0.7), "magic", source_xy=(u.x, u.y), fire=True)
    if u.alive:
        u.hp = 0
        world.kill(u, None)


def land(world: "World", p) -> None:
    """A lobbed boulder or flask hits the ground."""
    owner = p.owner
    if p.kind == "boulder":
        world.burst(p.x, p.y, 4, "#c0f8ff", n=18, speed=80, up=80, life=0.6, size=2)
        world.burst(p.x, p.y, 4, "#ffffff", n=8, speed=60, up=60, life=0.5)
        world.rings.append(Ring(p.x, p.y, 3, 24, "#73eff7", 0.4))
        world.sounds.append("explosion")
        for e in list(world.units):
            if e.alive and e.team != owner.team and e.rising <= 0:
                d = math.hypot(e.x - p.x, (e.y - p.y) * 1.5)
                if d < 22:
                    world.deal(owner, e, p.damage * (1.0 if d < 9 else 0.6), "physical", ranged=True,
                               source_xy=(p.sx, p.sy))
                    if e.alive:
                        e.status["slow"] = max(e.status.get("slow", 0.0), 2.0)
        return
    acid = p.kind == "flask_acid"
    col = "#a7f070" if acid else "#f77622"
    world.burst(p.x, p.y, 6, col, n=16, speed=70, up=60, life=0.5)
    world.burst(p.x, p.y, 6, "#ffffff", n=5, speed=40, up=40, life=0.3)
    world.rings.append(Ring(p.x, p.y, 2, 20, col, 0.35))
    if not acid:
        world.vfx.append(Vfx("explosion", p.x, p.y - 12))
    world.sounds.append("explosion" if not acid else "smoke")
    for e in list(world.units):
        if e.alive and e.team != owner.team and e.rising <= 0:
            d = math.hypot(e.x - p.x, (e.y - p.y) * 1.5)
            if d < 20:
                world.deal(owner, e, p.damage * (1.0 if d < 8 else 0.6), "magic", source_xy=(p.x, p.y), fire=not acid)
                if e.alive:
                    if acid:
                        e.status["corrode"] = 5.0
                    else:
                        e.status["burn"] = 3.0


# --- passives ---------------------------------------------------------------------------------

def _p_ranger(world, u):
    if "camo0" not in u.once:                      # starts the battle hidden
        u.once.add("camo0")
        u.status["stealth"] = 999.0
    if not u.has("stealth") and u.abil.get("camo", 0) <= 0 and world.time - u.last_hit > 5.0:
        u.status["stealth"] = 999.0
        world.burst(u.x, u.y, 10, "#3e8948", n=10, speed=25, up=30, life=0.5)


def _p_druid(world, u):
    if u.hp < u.max_hp * 0.5 and "shape" not in u.once:
        look = world.summon_looks.get((u.team, "bear"))
        if look is None:
            return
        u.once.add("shape")
        from .units import ROSTER
        frac = u.hp / u.max_hp
        u.type = ROSTER["bear"]
        u.key = "bear"
        u.look = look
        u.anims = world.anims[look]
        u.max_hp = float(u.type.hp)
        u.hp = u.chip = min(u.max_hp, u.max_hp * (frac + 0.4))
        u.action = None
        u.cd = 0.3
        u.set_anim("idle", restart=True)
        world.text(u, "ОБОРОТЕНЬ!", "#a7f070", big=True, life=1.2)
        world.burst(u.x, u.y, 14, "#a7f070", n=24, speed=60, up=80, life=0.7)
        world.rings.append(Ring(u.x, u.y, 4, 30, "#63c74d", 0.5))
        world.sounds.append("rage")


def _p_vampire(world, u):
    if u.hp < u.max_hp * 0.3 and "bats" not in u.once:
        u.once.add("bats")
        u.status["bats"] = 2.0
        u.status["stealth"] = 2.0
        u.action = None
        world.heal(u, u, u.max_hp * 0.25)
        world.text(u, "СТАЯ МЫШЕЙ!", "#c49be8", big=True)
        world.burst(u.x, u.y, 20, "#181425", n=24, speed=60, up=50, life=0.8, gravity=-30, size=2)
        for e in world.enemies(u):
            if e.target is u:
                e.target = None
        world.sounds.append("smoke")
    if u.has("bats") and world.rng.random() < 0.6:
        world.burst(u.x + world.rng.uniform(-8, 8), u.y, 18 + world.rng.uniform(0, 12), "#181425", n=1,
                    speed=30, up=20, life=0.4, gravity=-20, size=2)


def _p_drummer(world, u):
    for a in _near(world, u, world.allies(u), 80):
        a.status["rhythm"] = max(a.status.get("rhythm", 0.0), 0.4)
    u.status["rhythm"] = 0.4
    if u.abil.get("drum", 0) <= 0 and any(u.dist(e) < 160 for e in world.enemies(u)):
        u.abil["drum"] = 12.0
        world.text(u, "БУМ! БУМ!", "#feae34", big=True)
        world.rings.append(Ring(u.x, u.y, 4, 70, "#feae34", 0.6))
        for a in _near(world, u, world.allies(u) + [u], 80):
            a.status["warcry"] = 5.0
            world.burst(a.x, a.y, 20, "#feae34", n=5, speed=20, up=50, life=0.5, gravity=-20)
        world.sounds.append("warcry")


def _p_elephant(world, u):
    if u.hp < u.max_hp * 0.25 and "rampage" not in u.once:
        u.once.add("rampage")
        u.status["rampage"] = 4.0
        u.action = None
        world.text(u, "БЕШЕНСТВО!", "#e43b44", big=True, life=1.2)
        world.sounds.append("warcry")
    # the archer in the howdah
    if u.abil.get("howdah", 0) <= 0:
        foes = [e for e in world.enemies(u) if not e.has("stealth") and u.dist(e) < 170]
        if foes:
            u.abil["howdah"] = 2.5
            e = min(foes, key=lambda o: u.dist(o))
            world.shoot_arrow(u, e, damage=world.rng.uniform(7, 10), sz=42.0)
    # trample whoever is in the way
    if math.hypot(u.vx, u.vy) > 6:
        victims = world.units if u.has("rampage") else world.enemies(u)
        for e in list(victims):
            if e is u or e.dead or e.rising > 0 or e.has("trampled"):
                continue
            if abs(e.x - (u.x + u.facing * 8)) < u.type.radius + e.type.radius and abs(e.y - u.y) < 8:
                e.status["trampled"] = 1.2
                world.deal(u, e, 8, "physical", label="ТОПОТ")
                if e.alive and "stun" not in e.type.immune and e.type.radius < 12:
                    e.x += u.facing * 8
                    e.y += 4 if e.y > u.y else -4


def _p_militia(world, u):
    if u.hp < u.max_hp * 0.25 and "flinch" not in u.once:
        u.once.add("flinch")
        u.status["panic"] = 3.0
        u.action = None
        world.text(u, "ДРОГНУЛ!", "#ffffff", big=True)


NEW_PASSIVES = {"militia": _p_militia, "ranger": _p_ranger, "druid": _p_druid, "vampire": _p_vampire, "war_drummer": _p_drummer,
                "war_elephant": _p_elephant}


# --- abilities (return True when the turn is used) -----------------------------------------------

def _a_griffon(world, u):
    if u.abil.get("dive", 0) > 0 or u.cd > 0.3:
        return False
    prey = [e for e in world.enemies(u) if e.ranged and not e.has("stealth") and 40 < u.dist(e) < 240]
    if not prey:
        return False
    t = max(prey, key=lambda e: score(world, u, e))
    u.abil["dive"] = 9.0
    world.burst(u.x, u.y, 20, "#ffffff", n=12, speed=50, up=60, life=0.5)
    side = -1 if t.x > u.x else 1
    u.x = min(FIELD[2], max(FIELD[0], t.x + side * 14))
    u.y = t.y
    u.facing = -side
    u.hop = 0.45
    u.target = t
    u.status["divehit"] = 2.0
    u.cd = 0.0
    world.text(u, "ПИКЕ!", "#fee761", big=True)
    world.vfx.append(Vfx("dust", u.x, u.y - 6, flip=u.facing < 0))
    world.sounds.append("rage")
    return False


def _a_dryad(world, u):
    if u.abil.get("roots", 0) > 0 or u.cd > 0.5:
        return False
    for e in world.enemies(u):
        if (not e.ranged and e.target is not None and e.target.team == u.team and u.dist(e) < 150
                and in_melee_range(e, e.target, 8) and not e.has("root")):
            u.abil["roots"] = 8.0
            world.start_action(u, "roots", e, anim="cast", event="cast", cooldown=1.0)
            return True
    return False


def _a_banshee(world, u):
    if u.abil.get("wail", 0) > 0 or u.cd > 0.5:
        return False
    if any(not e.ranged and u.dist(e) < 55 for e in world.enemies(u)):
        u.abil["wail"] = 9.0
        world.start_action(u, "wail", u, anim="cast", event="cast", cooldown=0.9)
        return True
    return False


def _a_ghoul(world, u):
    if u.abil.get("feed", 0) > 0 or u.hp > u.max_hp * 0.7:
        return False
    bodies = [c for c in world.corpses() if math.hypot(c.x - u.x, c.y - u.y) < 28 and not c.kicked]
    if bodies:
        u.abil["feed"] = 6.0
        world.start_action(u, "feed", min(bodies, key=lambda c: math.hypot(c.x - u.x, c.y - u.y)),
                           cooldown=0.9)
        return True
    return False


def _a_ice_witch(world, u):
    if u.abil.get("tomb", 0) > 0 or u.cd > 0.5:
        return False
    cands = [e for e in world.enemies(u) if u.dist(e) < 150 and not e.has("stealth") and not e.has("freeze")
             and "freeze" not in e.type.immune]
    if not cands:
        return False
    t = max(cands, key=lambda e: e.dealt + (200 if e.has("charge") else 0) + (60 if e.target is u else 0))
    if t.dealt < 30 and not t.has("charge"):
        return False
    u.abil["tomb"] = 10.0
    world.start_action(u, "freeze", t, anim="cast", event="cast", cooldown=1.0)
    return True


def _a_rune_priest(world, u):
    if u.cd > 0.5:
        return False
    if u.abil.get("rune", 0) <= 0:
        hit = [a for a in world.allies(u) + [u] if not a.has("rune") and math.hypot(a.x - u.x, a.y - u.y) < 150
               and any(e.target is a for e in world.enemies(u))]
        if hit:
            hit.sort(key=lambda a: a.hp / a.max_hp)
            u.abil["rune"] = 7.0
            world.start_action(u, "runes", hit[0], anim="cast", event="cast", cooldown=1.0)
            u.action["picks"] = hit[:2]
            return True
    if u.abil.get("thunder", 0) <= 0:
        foes = world.enemies(u)
        best, n = None, 1
        for e in foes:
            if u.dist(e) > 150:
                continue
            k = sum(1 for o in foes if math.hypot(o.x - e.x, (o.y - e.y) * 1.4) < 30)
            if k > n:
                best, n = e, k
        if best is not None:
            u.abil["thunder"] = 12.0
            world.start_action(u, "thunder", best, anim="cast", event="cast", cooldown=1.0)
            return True
    return False


def _a_assassin(world, u):
    t = u.target
    if u.abil.get("jump", 0) > 0 or t is None or not (25 < u.dist(t) < 150):
        return False
    u.abil["jump"] = 14.0
    world.burst(u.x, u.y, 8, "#262b44", n=14, speed=35, up=25, life=0.6, gravity=-15, size=2)
    u.x = min(FIELD[2], max(FIELD[0], t.x - t.facing * 11))
    u.y = t.y + (2 if u.y > t.y else -2)
    u.facing = 1 if t.x >= u.x else -1
    u.status["stealth"] = 0.5
    u.cd = 0.0
    world.burst(u.x, u.y, 8, "#a7f070", n=10, speed=35, up=25, life=0.6, gravity=-15)
    world.text(u, "ИЗ ТЕНИ!", "#a7f070", big=True)
    world.sounds.append("smoke")
    return False


def _a_spider(world, u):
    if u.abil.get("web", 0) > 0 or u.cd > 0.4:
        return False
    cands = [e for e in world.enemies(u) if 20 < u.dist(e) < 110 and not e.has("root") and not e.has("stealth")
             and "root" not in e.type.immune]
    if not cands:
        return False
    t = max(cands, key=lambda e: (60 if e.has("charge") else 0) + (40 if e.key in DIVERS else 0)
            + (30 if e is u.target else 0) - u.dist(e) * 0.2)
    u.abil["web"] = 7.0
    world.start_action(u, "web", t, anim="cast", event="cast", cooldown=0.8)
    return True


def _valk_body(world, u):
    if "valhalla" in u.once:
        return None
    bodies = [c for c in world.corpses() if c.team == u.team and not c.summoned and not c.kicked
              and not c.type.undead and c.key != "goblin_bomber" and math.hypot(c.x - u.x, c.y - u.y) < 260]
    return min(bodies, key=lambda c: math.hypot(c.x - u.x, c.y - u.y)) if bodies else None


def _a_valkyrie(world, u):
    body = _valk_body(world, u)
    if body is not None and math.hypot(body.x - u.x, body.y - u.y) < 22 and u.cd <= 0.5:
        u.once.add("valhalla")
        world.start_action(u, "valhalla", body, anim="cast", event="cast", cooldown=1.2)
        return True
    return False


def _a_harpooner(world, u):
    if u.abil.get("harpoon", 0) > 0 or u.cd > 0.3:
        return False
    prey = [e for e in world.enemies(u) if e.ranged and not e.has("stealth") and 40 < u.dist(e) < 120
            and e.type.radius < 12]
    if not prey:
        return False
    t = max(prey, key=lambda e: score(world, u, e))
    u.abil["harpoon"] = 8.0
    world.start_action(u, "harpoon", t, cooldown=0.9)
    return True


def _a_uhlan(world, u) -> bool:
    """Run-up: when the lance charge is (nearly) ready and the enemy is too close to charge, ride off."""
    if u.has("regroup") or u.has("charge") or u.abil.get("leap", 0) > 0.6:
        return False
    near = [e for e in world.enemies(u) if not e.has("stealth")]
    if near and min(u.dist(e) for e in near) < CHARGERS["uhlan"][1]:
        u.status["regroup"] = 1.3                     # a proper run-up, not just a step back
        world.text(u, "РАЗБЕГ", "#c0cbdc")
    return False


NEW_ABILITIES = {"uhlan": _a_uhlan, "harpooner": _a_harpooner, "griffon_knight": _a_griffon, "dryad": _a_dryad, "banshee": _a_banshee, "ghoul": _a_ghoul,
                 "ice_witch": _a_ice_witch, "rune_priest": _a_rune_priest, "assassin": _a_assassin,
                 "bog_spider": _a_spider, "valkyrie": _a_valkyrie}


# --- resolved actions -------------------------------------------------------------------------------

def _r_roots(world, u, t, a):
    if t is not None and t.alive and "root" not in t.type.immune:
        t.status["root"] = 2.5
        world.text(t, "КОРНИ!", "#63c74d", big=True)
        world.burst(t.x, t.y, 2, "#63c74d", n=14, speed=20, up=30, life=0.6)
        world.sounds.append("smoke")


def _r_wail(world, u, t, a):
    world.text(u, "ВОПЛЬ!", "#c0cbdc", big=True, life=1.2)
    world.rings.append(Ring(u.x, u.y, 4, 60, "#c0cbdc", 0.6))
    world.rings.append(Ring(u.x, u.y, 2, 44, "#73eff7", 0.45))
    world.sounds.append("nova")
    for e in world.enemies(u):
        if u.dist(e) < 60 and "fear" not in e.type.immune:
            e.status["fear"] = 1.5
            e.status["slow"] = max(e.status.get("slow", 0.0), 2.0)
            e.fear_src = (u.x, u.y)
            e.action = None
            world.text(e, "!", "#c49be8", big=True)


def _r_feed(world, u, t, a):
    if t is not None and t.dead and not t.raised:
        t.raised = True
        world.heal(u, u, 70)
        world.text(u, "ЧАВК!", "#a22633", big=True)
        world.burst(t.x, t.y, 6, "#a22633", n=14, speed=40, up=40, life=0.6)


def _r_freeze(world, u, t, a):
    if t is not None and t.alive and "freeze" not in t.type.immune and not t.has("divine"):
        t.status["freeze"] = 2.0
        t.action = None
        world.text(t, "ЗАМОРОЖЕН!", "#73eff7", big=True)
        world.rings.append(Ring(t.x, t.y, 2, 16, "#ffffff", 0.4))
        world.burst(t.x, t.y, 16, "#c0f8ff", n=16, speed=40, up=50, life=0.6)
        world.sounds.append("nova")


def _r_runes(world, u, t, a):
    for al in a.get("picks", []):
        if al.alive:
            al.status["rune"] = 6.0
            world.text(al, "РУНА!", "#2ce8f5")
            world.rings.append(Ring(al.x, al.y, 2, 14, "#2ce8f5", 0.4))
    world.sounds.append("nova")


def _r_thunder(world, u, t, a):
    if t is None:
        return
    x, y = t.x, t.y
    world.text((x, y - 30), "РУНА ГРОМА!", "#2ce8f5", big=True)
    world.rings.append(Ring(x, y, 4, 32, "#2ce8f5", 0.45))
    world.bolts.append(Lightning([(x + 3, y - 70), (x - 2, y - 40), (x + 2, y - 18), (x, y)]))
    world.burst(x, y, 2, "#2ce8f5", n=20, speed=80, up=60, life=0.5)
    world.sounds.append("explosion")
    for e in world.enemies(u):
        if math.hypot(e.x - x, (e.y - y) * 1.4) < 30:
            world.deal(u, e, 20, "magic", source_xy=(x, y))
            if e.alive:
                _stun(world, e, 0.6, quiet=True)


def _r_web(world, u, t, a):
    if t is not None and t.alive:
        world.cast_orb(u, t, "web", speed=200)


def _r_valhalla(world, u, t, a):
    if t is None or not t.dead or t.raised or t.revive_at is not None:
        return
    t.dead = False
    t.hp = t.chip = t.max_hp * 0.4
    t.status.clear()
    t.rising = 0.6
    t.action = None
    t.set_anim("idle")
    world.text(t, "ВАЛЬХАЛЛА ПОДОЖДЁТ!", "#fee761", big=True, life=1.4)
    world.rings.append(Ring(t.x, t.y, 2, 26, "#fee761", 0.6))
    world.burst(t.x, t.y, 30, "#ffffff", n=24, speed=40, up=70, life=0.9, gravity=-20)
    world.sounds.append("nova")


def _r_harpoon(world, u, t, a):
    if t is None or t.dead:
        return
    sx, sy = t.x, t.y
    t.x = min(FIELD[2], max(FIELD[0], u.x + u.facing * 15))
    t.y = u.y + (2 if t.y > u.y else -2)
    t.vx = t.vy = 0.0
    t.action = None
    world.bolts.append(Lightning([(u.x + u.facing * 8, u.y - 18), (sx, sy - 16)], color="#b86f50", life=0.25))
    lo, hi = u.type.damage
    world.deal(u, t, world.rng.uniform(lo, hi) * 0.7, "physical", label="ГАРПУН")
    if t.alive:
        _stun(world, t, 0.6, quiet=True)
    world.text(u, "ГАРПУН!", "#feae34", big=True)
    world.burst(t.x, t.y, 12, "#c0cbdc", n=10, speed=50, up=30, life=0.4)
    world.sounds.append("hit")


NEW_ACTIONS = {"harpoon": _r_harpoon, "roots": _r_roots, "wail": _r_wail, "feed": _r_feed, "freeze": _r_freeze, "runes": _r_runes,
               "thunder": _r_thunder, "web": _r_web, "valhalla": _r_valhalla}


def _new_shot(world, u, t, a) -> None:
    k = u.key
    if k == "ranger":
        ambush = u.has("stealth")
        u.status.pop("stealth", None)
        u.abil["camo"] = 5.0
        world.shoot_arrow(u, t, 2.0 if ambush else 1.0)
        if ambush:
            world.text(u, "ЗАСАДА!", "#a7f070")
    elif k == "horse_archer":
        world.shoot_arrow(u, t, sz=24.0)
    elif k == "slinger":
        lo, hi = u.type.damage
        world.throw(u, t, "stone", world.rng.uniform(lo, hi))
    elif k in ("dryad", "druid"):
        world.cast_orb(u, t, "thorn", speed=160)
    elif k == "banshee":
        world.cast_orb(u, t, "wailorb", speed=150)
    elif k == "ice_witch":
        world.cast_orb(u, t, "frost", speed=170)
    elif k == "rune_priest":
        world.cast_orb(u, t, "rune", speed=170)
    elif k == "frost_giant":
        lo, hi = u.type.damage
        if in_melee_range(u, t, 8):           # blind spot: just a punch
            world.deal(u, t, world.rng.uniform(lo, hi) * 0.5, "physical", label="КУЛАК")
            return
        world.throw(u, t, "boulder", world.rng.uniform(lo, hi))
    elif k == "alchemist":
        lo, hi = u.type.damage
        if world.rng.random() < 0.08:          # unstable flask
            world.text(u, "ОЙ!", "#f77622", big=True)
            world.vfx.append(Vfx("explosion", u.x, u.y - 14))
            world.sounds.append("explosion")
            for o in _near(world, u, world.allies(u) + world.enemies(u) + [u], 20):
                world.deal(None, o, world.rng.uniform(lo, hi) * 0.6, "magic", fire=True, source_xy=(u.x, u.y))
            return
        u.hits += 1
        world.throw(u, t, "flask_acid" if u.hits % 2 == 0 else "flask_fire", world.rng.uniform(lo, hi))


# --- melee modifiers ----------------------------------------------------------------------------------

def _new_melee_mods(world, u, t, dmg, crit, label):
    k = u.key
    if k == "lancer":
        if u.has("lancehit"):
            del u.status["lancehit"]
            dmg *= 2.5
            crit, label = True, "ТАРАН"
            u.status["regroup"] = 1.3
            if t.alive and t.type.radius < 12:
                t.x = min(FIELD[2], max(FIELD[0], t.x + u.facing * 16))
        else:
            dmg *= 0.85
    if k == "uhlan" and u.has("lancehit"):
        del u.status["lancehit"]
        dmg *= 2.0
        crit, label = True, "ПИКА"
        u.status["regroup"] = 1.0
        if t.alive and t.type.radius < 12:
            t.x = min(FIELD[2], max(FIELD[0], t.x + u.facing * 14))
    if k == "griffon_knight" and u.has("divehit"):
        del u.status["divehit"]
        dmg *= 2.0
        crit, label = True, "ПИКЕ"
        _stun(world, t, 0.8)
    if k == "assassin":
        if t.has("poison"):
            dmg *= 1.6
            crit, label = True, "ДОБИТЬ"
        _poison(t, 5.0)
    if k == "duelist":
        if t is not u.last_target:
            dmg *= 1.6
            crit, label = True, "ВЫПАД"
        u.last_target = t
    if k in ("ghoul",):
        _poison(t, 4.0)
    if k == "zombie":
        _poison(t, 3.0)
    if k == "war_dog" and t.alive:
        t.status["slow"] = max(t.status.get("slow", 0.0), 1.0)
    if k == "bog_spider":
        _poison(t, 4.0)
    if k == "bear":
        _bleed(t, 3.0)
    if k == "mamluk":
        _bleed(t, 2.0)
    if k == "halberdier" and u.hits % 3 == 0:
        crit, label = True, "КРЮК"
    return dmg, crit, label


def _new_melee_after(world, u, t, dmg):
    k = u.key
    if k == "death_knight" and t.alive:
        t.status["slow"] = max(t.status.get("slow", 0.0), 1.5)
    if k == "halberdier" and u.hits % 3 == 0 and t.alive:
        _stun(world, t, 0.6, quiet=True)
    if k == "war_elephant" and t.alive and t.type.radius < 12:
        t.x = min(FIELD[2], max(FIELD[0], t.x + u.facing * 10))
    if k == "treant" and u.hits % 3 == 0:
        world.text(u, "КОРНИ!", "#63c74d", big=True)
        world.rings.append(Ring(u.x, u.y, 4, 32, "#63c74d", 0.5))
        world.burst(u.x, u.y, 2, "#733e39", n=16, speed=60, up=30, life=0.5)
        for e in world.enemies(u):
            if math.hypot(e.x - u.x, (e.y - u.y) * 1.4) < 30:
                if e is not t:
                    world.deal(u, e, dmg * 0.5, "physical")
                if e.alive and "root" not in e.type.immune:
                    e.status["root"] = 1.5
    if k == "bladedancer" and u.hits % 3 == 0:
        world.text(u, "ВИХРЬ!", "#ffffff", big=True)
        world.rings.append(Ring(u.x, u.y, 4, 22, "#ffffff", 0.3))
        for e in world.enemies(u):
            if e is not t and math.hypot(e.x - u.x, (e.y - u.y) * 1.4) < 22:
                world.deal(u, e, dmg * 0.7, "physical")
    if k == "fire_dervish":
        world.rings.append(Ring(u.x, u.y, 4, 24, "#f77622", 0.35))
        world.burst(u.x, u.y, 10, "#feae34", n=14, speed=70, up=40, life=0.5)
        for e in world.enemies(u):
            if math.hypot(e.x - u.x, (e.y - u.y) * 1.4) < 24:
                if e is not t:
                    world.deal(u, e, dmg * 0.8, "magic", fire=True)
                if e.alive:
                    e.status["burn"] = max(e.status.get("burn", 0.0), 2.0)
        if u.hits % 4 == 0:
            u.status["stupor"] = 1.0
            world.text(u, "...", "#c0cbdc")


# --- movement overrides -------------------------------------------------------------------------------

def _special_move(world, u, t, dt) -> bool:
    if u.has("rampage"):                       # war elephant running amok
        if (u.x < FIELD[0] + 10 and u.facing < 0) or (u.x > FIELD[2] - 10 and u.facing > 0):
            u.facing = -u.facing
        _move(u, u.facing, math.sin(world.time * 3 + u.id) * 0.4, dt)
        return True
    if u.has("bats"):                          # vampire bats flutter back to their own side
        _move(u, _home(u), 0.3 if u.y < (FIELD[1] + FIELD[3]) / 2 else -0.3, dt)
        return True
    if u.has("regroup") and t is not None:     # lancer rides off for another charge
        fx, fy = _norm(u.x - t.x, (u.y - t.y) * 0.5)
        if (u.x < FIELD[0] + 12 and fx < 0) or (u.x > FIELD[2] - 12 and fx > 0):
            fx, fy = 0.0, (1.0 if u.y < (FIELD[1] + FIELD[3]) / 2 else -1.0)
        _move(u, fx, fy, dt)
        return True
    return False


def _new_positioning(world, u, t, dt) -> bool:
    """Support roles that stand somewhere specific instead of walking up to their target."""
    if u.key == "goblin_bomber" and world.time < 7.0 and not _threatened(world, u):
        _move(u, 0, 0, dt)                         # wait for the armies to clash first
        if t is not None:
            u.facing = 1 if t.x >= u.x else -1
        return True
    if u.key == "valkyrie":
        body = _valk_body(world, u)
        if body is not None and math.hypot(body.x - u.x, body.y - u.y) >= 22:
            nx, ny = _norm(body.x - u.x, body.y - u.y)
            _move(u, nx, ny, dt)
            return True
    if u.key == "war_drummer":
        if _threatened(world, u) or (t is not None and in_melee_range(u, t)):
            return False
        front = [a for a in world.allies(u) if not a.ranged and a.key != "war_drummer"]
        if not front:
            return False
        anchor = min(front, key=lambda a: math.hypot(a.x - u.x, a.y - u.y))
        wx, wy = anchor.x + _home(u) * 26, anchor.y
        if math.hypot(wx - u.x, wy - u.y) < 3:
            _move(u, 0, 0, dt)
            if t is not None:
                u.facing = 1 if t.x >= u.x else -1
        else:
            nx, ny = _norm(wx - u.x, wy - u.y)
            _move(u, nx, ny, dt)
        return True
    if u.key == "shieldbearer":
        if t is not None and (in_melee_range(u, t, 6) or t.target is u):
            return False
        shooters = [a for a in world.allies(u) if a.ranged]
        foes = world.enemies(u)
        if not shooters or not foes:
            return False
        s_ = min(shooters, key=lambda a: math.hypot(a.x - u.x, a.y - u.y))
        f = min(foes, key=lambda e: math.hypot(e.x - s_.x, e.y - s_.y))
        if math.hypot(f.x - s_.x, f.y - s_.y) > 160:
            return False
        nx, ny = _norm(f.x - s_.x, f.y - s_.y)
        wx, wy = s_.x + nx * 24, s_.y + ny * 10
        if math.hypot(wx - u.x, wy - u.y) < 3:
            _move(u, 0, 0, dt)
            u.facing = 1 if f.x >= u.x else -1
        else:
            mx, my = _norm(wx - u.x, wy - u.y)
            _move(u, mx, my, dt)
        return True
    return False
