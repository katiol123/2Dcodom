"""pygame renderer: draws the World at 480x270 and scales it up with
nearest-neighbour so every pixel stays crisp."""

from __future__ import annotations

import math
import random
from typing import Dict, List, Optional, Tuple

import pygame

from pixelforge.assets import ui as pui
from pixelforge.assets import vfx as pvfx
from pixelforge.canvas import Canvas
from pixelforge.color import mix, ramp, rgba
from pixelforge.text import FONT, glyph

from . import assets
from .sim import FIELD, H, W, World, Unit
from .units import ORDER, ROSTER

INK = (24, 20, 37)


def to_surface(c: Canvas) -> pygame.Surface:
    img = c.to_image()
    return pygame.image.frombuffer(img.tobytes(), img.size, "RGBA").convert_alpha()


def _c(hexstr: str) -> Tuple[int, int, int]:
    return rgba(hexstr)[:3]


# --- pixel font -------------------------------------------------------------------------

class Font:
    def __init__(self):
        self.cache: Dict[tuple, pygame.Surface] = {}

    def render(self, text: str, color, scale: int = 1, outline=INK, spacing: int = 1) -> pygame.Surface:
        key = (text, tuple(color) if not isinstance(color, str) else color, scale, outline)
        s = self.cache.get(key)
        if s is not None:
            return s
        col = _c(color) if isinstance(color, str) else color
        width = sum(len(glyph(ch)[0]) + spacing for ch in text) - spacing if text else 1
        base = pygame.Surface((width + 2, 7), pygame.SRCALPHA)
        for layer, c in ((0, outline), (1, col)):
            if c is None:
                continue
            x = 1
            for ch in text:
                g = glyph(ch)
                for j, row in enumerate(g):
                    for i, px in enumerate(row):
                        if px == "#":
                            if layer == 0:
                                for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1), (1, 1), (-1, 1), (1, -1), (-1, -1)):
                                    base.set_at((x + i + dx, 1 + j + dy), c)
                            else:
                                base.set_at((x + i, 1 + j), c)
                x += len(g[0]) + spacing
        if scale != 1:
            base = pygame.transform.scale(base, (base.get_width() * scale, base.get_height() * scale))
        self.cache[key] = base
        return base

    def draw(self, surf: pygame.Surface, text: str, x: float, y: float, color, scale: int = 1,
             anchor: str = "topleft", outline=INK) -> pygame.Rect:
        s = self.render(text, color, scale, outline)
        r = s.get_rect(**{anchor: (round(x), round(y))})
        surf.blit(s, r)
        return r


# --- sprite banks ---------------------------------------------------------------------------

class UnitArt:
    """All frames of one unit type/team, plus flipped and tinted variants (lazy)."""

    def __init__(self, meta: dict):
        sheet = pygame.image.load(meta["path"]).convert_alpha()
        self.w, self.h = meta["frame_width"], meta["frame_height"]
        self.anchor = tuple(meta["anchor"])
        self.frames: Dict[str, List[pygame.Surface]] = {}
        for name, a in meta["animations"].items():
            self.frames[name] = [sheet.subsurface((f["x"], f["y"], f["w"], f["h"])).copy() for f in a["frames"]]
        self._var: Dict[tuple, pygame.Surface] = {}

    def get(self, anim: str, i: int, flip: bool, tint: Optional[str] = None) -> pygame.Surface:
        key = (anim, i, flip, tint)
        s = self._var.get(key)
        if s is None:
            s = self.frames[anim][i]
            if flip:
                s = pygame.transform.flip(s, True, False)
            if tint is not None:
                s = s.copy()
                if tint == "white":
                    s.fill((255, 255, 255, 0), special_flags=pygame.BLEND_RGBA_MAX)
                elif tint == "hit":
                    s.fill((150, 140, 140, 0), special_flags=pygame.BLEND_RGBA_ADD)
                elif tint == "slow":
                    s.fill((150, 210, 255, 255), special_flags=pygame.BLEND_RGBA_MULT)
                    s.fill((10, 30, 60, 0), special_flags=pygame.BLEND_RGBA_ADD)
                elif tint == "rage":
                    s.fill((255, 170, 160, 255), special_flags=pygame.BLEND_RGBA_MULT)
                    s.fill((60, 0, 0, 0), special_flags=pygame.BLEND_RGBA_ADD)
                elif tint == "corpse":
                    s.fill((150, 140, 160, 255), special_flags=pygame.BLEND_RGBA_MULT)
                elif tint == "stealth":
                    mask = pygame.Surface(s.get_size(), pygame.SRCALPHA)
                    for y in range(s.get_height()):
                        for x in range(s.get_width()):
                            if (x + y) % 2 == 0:
                                mask.set_at((x, y), (255, 255, 255, 255))
                            else:
                                mask.set_at((x, y), (255, 255, 255, 0))
                    s.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
            self._var[key] = s
        return s


class VfxArt:
    def __init__(self, anim):
        self.frames = [to_surface(f.image) for f in anim.frames]
        self.flipped = [pygame.transform.flip(f, True, False) for f in self.frames]
        self.ends = []
        t = 0.0
        for f in anim.frames:
            t += f.duration / 1000.0
            self.ends.append(t)

    def frame(self, t: float, flip: bool = False) -> Optional[pygame.Surface]:
        for i, e in enumerate(self.ends):
            if t < e:
                return (self.flipped if flip else self.frames)[i]
        return None


# --- renderer ---------------------------------------------------------------------------------

class Renderer:
    def __init__(self, world: World, metas: Dict[str, dict], seed: int = 0):
        self.font = Font()
        self.metas = metas
        self.art = {k: UnitArt(m) for k, m in metas.items()}
        bg_path = assets.CACHE / "background.png"
        if bg_path.exists():
            self.bg = pygame.image.load(str(bg_path)).convert()
        else:
            canvas = assets.background(W, H, 120)
            canvas.save(str(bg_path))
            self.bg = to_surface(canvas)
        self.arrows = [to_surface(assets.arrow_canvas(a * 360 / 32)) for a in range(32)]
        self.vfx = {
            "explosion": VfxArt(pvfx.explosion(32)),
            "hit_spark": VfxArt(pvfx.hit_spark(16)),
            "dust": VfxArt(pvfx.dust(16)),
            "heal": VfxArt(pvfx.heal(24)),
        }
        self.fireball = VfxArt(pvfx.fireball(16))
        self.scorch = to_surface(assets.scorch(10))
        self.panel_cache: Dict[tuple, pygame.Surface] = {}
        self.portraits = {}
        for k, m in metas.items():
            idle = self.art[k].frames["idle"][0]
            top = idle.get_bounding_rect().top
            ax = m["anchor"][0]
            self.portraits[k] = idle.subsurface((ax - 8, max(0, top - 1), 18, 14)).copy()
            grey = self.portraits[k].copy()
            grey.fill((90, 90, 110, 255), special_flags=pygame.BLEND_RGBA_MULT)
            self.portraits[k + "_dead"] = grey
        self.world_surf = pygame.Surface((W, H))
        self.rnd = random.Random(seed)
        self.blood = []
        for i in range(6):
            s = pygame.Surface((9, 5), pygame.SRCALPHA)
            r = random.Random(i)
            for _ in range(7):
                s.set_at((r.randrange(1, 8), r.randrange(0, 5)), r.choice([(162, 38, 51), (104, 56, 108), (115, 62, 57)]))
            self.blood.append(s)
        self.hud_flash: Dict[int, float] = {}
        self.prev_hp: Dict[int, float] = {}

    def panel(self, w: int, h: int, base="#262b44", border="#5a6988") -> pygame.Surface:
        key = (w, h, base, border)
        if key not in self.panel_cache:
            self.panel_cache[key] = to_surface(pui.panel(w, h, base=base, border=border))
        return self.panel_cache[key]

    # --- world ---------------------------------------------------------------------------
    def draw(self, world: World, screen: pygame.Surface, real_time: float, paused: bool = False,
             speed: float = 1.0) -> None:
        ws = self.world_surf
        ws.blit(self.bg, (0, 0))
        self._decals(world, ws)
        self._units(world, ws, real_time)
        self._rings(world, ws)
        self._vfx(world, ws)
        self._particles(world, ws)
        self._bars(world, ws, real_time)
        self._texts(world, ws, real_time)
        sx = sy = 0
        if world.shake > 0:
            s = int(round(world.shake))
            sx, sy = self.rnd.randint(-s, s), self.rnd.randint(-s, s)
        screen.fill(INK)
        screen.blit(ws, (sx, sy))
        self._hud(world, screen, real_time)
        self._overlays(world, screen, real_time, paused, speed)

    def _decals(self, world: World, s: pygame.Surface) -> None:
        for i, d in enumerate(world.decals):
            if d.kind == "scorch":
                s.blit(self.scorch, (round(d.x) - 11, round(d.y) - 5))
            elif d.kind == "blood":
                s.blit(self.blood[i % len(self.blood)], (round(d.x) - 4, round(d.y) - 2))
        for d in world.decals:
            if d.kind == "arrow":
                # stuck in the ground: steep angle, only the back half shows
                img = self.arrows[int(((d.angle % 360) / 360) * 32) % 32]
                s.blit(img, (round(d.x) - 6, round(d.y) - 9))

    def _unit_sprite(self, u: Unit, real_time: float) -> pygame.Surface:
        art = self.art[f"{u.key}_{u.team_key}"]
        i = min(u.frame(), len(art.frames[u.anim]) - 1)
        tint = None
        if u.dead:
            if u.anim_t > u.anims["death"].total:
                tint = "corpse"
        elif u.flash > 0:
            tint = "white" if getattr(u, "flash_crit", False) else "hit"
        elif u.has("stealth"):
            tint = "stealth"
        elif u.has("slow"):
            tint = "slow"
        elif u.rage and int(real_time * 6) % 2 == 0:
            tint = "rage"
        return art.get(u.anim, i, u.facing < 0, tint)

    def _units(self, world: World, s: pygame.Surface, real_time: float) -> None:
        items = []
        for u in world.units:
            items.append((0 if u.dead else 1, u.y, 0, u))
        for p in world.projectiles:
            items.append((1, p.y, 1, p))
        items.sort(key=lambda it: (it[0], it[1]))
        # team markers under the living
        for u in world.units:
            if u.alive:
                col = _c(world.teams[u.team].accent)
                r = pygame.Rect(0, 0, 15, 5)
                r.center = (round(u.x), round(u.y) + 2)
                pygame.draw.ellipse(s, col, r, 1)
        for _, _, kind, obj in items:
            if kind == 0:
                u = obj
                art = self.art[f"{u.key}_{u.team_key}"]
                img = self._unit_sprite(u, real_time)
                ax = art.anchor[0] if u.facing > 0 else art.w - 1 - art.anchor[0]
                s.blit(img, (round(u.x) - ax, round(u.y) - art.anchor[1]))
                if u.has("stun"):
                    for k in range(3):
                        a = real_time * 7 + k * math.tau / 3
                        x = round(u.x + math.cos(a) * 6)
                        y = round(u.y - 36 + math.sin(a) * 2)
                        s.set_at((x, y), (254, 231, 97))
                        s.set_at((x + 1, y), (255, 255, 255))
                if u.has("warcry") and int(real_time * 10) % 3 == 0:
                    s.set_at((round(u.x) + self.rnd.randint(-6, 6), round(u.y) - self.rnd.randint(4, 30)),
                             (254, 174, 52))
            else:
                p = obj
                # ground shadow
                pygame.draw.line(s, (24, 20, 37), (round(p.x) - 2, round(p.y)), (round(p.x) + 1, round(p.y)))
                if p.kind == "arrow":
                    img = self.arrows[int(((p.angle % 360) / 360) * 32 + 0.5) % 32]
                    s.blit(img, (round(p.x) - 6, round(p.y - p.z) - 6))
                else:
                    f = self.fireball.frame((world.time * 1.0) % 0.28, flip=p.tx < p.sx) or self.fireball.frames[0]
                    s.blit(f, (round(p.x) - 10 if p.tx >= p.sx else round(p.x) - 5, round(p.y - p.z) - 8))

    def _rings(self, world: World, s: pygame.Surface) -> None:
        for r in world.rings:
            k = r.t / r.life
            rad = r.r0 + (r.r1 - r.r0) * (1 - (1 - k) ** 2)
            rect = pygame.Rect(0, 0, max(2, int(rad * 2)), max(2, int(rad * 0.8)))
            rect.center = (round(r.x), round(r.y))
            col = _c(r.color)
            pygame.draw.ellipse(s, col, rect, 1 if k > 0.5 else 2)

    def _vfx(self, world: World, s: pygame.Surface) -> None:
        for v in world.vfx:
            art = self.vfx[v.name]
            f = art.frame(v.t, v.flip)
            if f is not None:
                s.blit(f, (round(v.x) - f.get_width() // 2, round(v.y) - f.get_height() // 2))

    def _particles(self, world: World, s: pygame.Surface) -> None:
        for p in world.particles:
            col = _c(p.color)
            x, y = round(p.x), round(p.y - p.z)
            if p.size > 1:
                pygame.draw.rect(s, col, (x, y, p.size, p.size))
            else:
                s.set_at((x, y), col)

    def _bar(self, s: pygame.Surface, x: int, y: int, w: int, h: int, frac: float, chip: float,
             team_color: str, ticks: int = 0, real_time: float = 0.0) -> None:
        """Pixel health bar: rounded ink frame, white "chip" trail of recent damage,
        3-tone fill (lit top row, dark bottom row), 50-HP tick marks, blinks red when low."""
        pygame.draw.rect(s, INK, (x + 1, y, w - 2, h))
        pygame.draw.rect(s, INK, (x, y + 1, w, h - 2))
        inner = pygame.Rect(x + 1, y + 1, w - 2, h - 2)
        pygame.draw.rect(s, (38, 43, 68), inner)
        fw = int(round(inner.w * max(0.0, min(1.0, frac))))
        cw = int(round(inner.w * max(0.0, min(1.0, chip))))
        if cw > fw:
            pygame.draw.rect(s, (255, 241, 232), (inner.x + fw, inner.y, cw - fw, inner.h))
        if fw > 0:
            tones = self._tones(team_color)
            if frac < 0.3 and int(real_time * 5) % 2 == 0:
                tones = self._tones("#e43b44")
            pygame.draw.rect(s, tones[1], (inner.x, inner.y, fw, inner.h))
            pygame.draw.line(s, tones[2], (inner.x, inner.y), (inner.x + fw - 1, inner.y))
            if inner.h > 2:
                pygame.draw.line(s, tones[0], (inner.x, inner.bottom - 1), (inner.x + fw - 1, inner.bottom - 1))
        if ticks > 1:
            for k in range(1, ticks):
                tx = inner.x + int(inner.w * k / ticks)
                if tx < inner.x + fw:
                    s.set_at((tx, inner.y + inner.h // 2), INK)

    def _tones(self, color: str):
        t = self.panel_cache.get(("tones", color))
        if t is None:
            t = [c[:3] for c in ramp(color, 1, 1)]
            self.panel_cache[("tones", color)] = t
        return t

    def _bars(self, world: World, s: pygame.Surface, real_time: float) -> None:
        for u in world.units:
            if u.dead:
                continue
            team = world.teams[u.team]
            x = round(u.x) - 9
            y = round(u.y) - 41
            self._bar(s, x, y, 19, 4, u.hp / u.max_hp, u.chip / u.max_hp, team.accent,
                      ticks=int(u.max_hp // 50), real_time=real_time)
            # status pips above the bar
            icons = []
            if u.has("burn"):
                icons.append((254, 174, 52))
            if u.has("bleed"):
                icons.append((228, 59, 68))
            if u.has("slow"):
                icons.append((44, 232, 245))
            if u.rage:
                icons.append((162, 38, 51))
            if u.has("warcry"):
                icons.append((254, 231, 97))
            if u.has("taunt"):
                icons.append((255, 255, 255))
            for i, col in enumerate(icons):
                pygame.draw.rect(s, INK, (x + i * 4, y - 4, 4, 4))
                pygame.draw.rect(s, col, (x + 1 + i * 4, y - 3, 2, 2))

    def _texts(self, world: World, s: pygame.Surface, real_time: float) -> None:
        for t in world.texts:
            k = t.t / t.life
            if k > 0.7 and int(real_time * 20) % 2 == 0:
                continue          # blink out instead of alpha fading
            rise = 16 * (1 - (1 - min(1.0, k * 1.6)) ** 3)
            scale = 2 if (t.big and k < 0.15) else 1
            self.font.draw(s, t.text, t.x, t.y - rise, t.color, scale=scale, anchor="midbottom")

    # --- HUD -----------------------------------------------------------------------------------
    def _hud(self, world: World, s: pygame.Surface, real_time: float) -> None:
        for team in (0, 1):
            tm = world.teams[team]
            hp, mx = world.team_hp(team)
            right = team == 1
            px = W - 4 - 158 if right else 4
            s.blit(self.panel(158, 44, base="#181425", border=tm.color), (px, 3))
            name_x = px + 158 - 6 if right else px + 6
            self.font.draw(s, tm.name, name_x, 6, tm.light, anchor="topright" if right else "topleft")
            alive = world.alive_count(team)
            self.font.draw(s, f"{alive}/7", px + 6 if right else px + 158 - 6, 6, "#c0cbdc",
                           anchor="topleft" if right else "topright")
            chip = sum(u.chip for u in world.units if u.team == team)
            self._bar(s, px + 5, 14, 148, 5, hp / mx, chip / mx, tm.accent, ticks=7, real_time=real_time)
            # portraits
            units = [u for u in world.units if u.team == team]
            for i, u in enumerate(units):
                cx = px + 5 + i * 21 if not right else px + 158 - 5 - 20 - i * 21
                cy = 22
                prev = self.prev_hp.get(u.id, u.hp)
                if u.hp < prev:
                    self.hud_flash[u.id] = real_time
                self.prev_hp[u.id] = u.hp
                flash = real_time - self.hud_flash.get(u.id, -9) < 0.12
                border = "#ffffff" if flash else (tm.color if u.alive else "#3a4466")
                pygame.draw.rect(s, _c(border), (cx, cy, 20, 18))
                pygame.draw.rect(s, (38, 43, 68), (cx + 1, cy + 1, 18, 16))
                key = f"{u.key}_{tm.key}" + ("" if u.alive else "_dead")
                por = self.portraits[key]
                if right:
                    por = pygame.transform.flip(por, True, False)
                s.blit(por, (cx + 1, cy + 1), area=pygame.Rect(0, 0, 18, 13))
                if u.alive:
                    self._bar(s, cx + 1, cy + 14, 18, 3, u.hp / u.max_hp, u.chip / u.max_hp, tm.accent,
                              real_time=real_time)
                else:
                    for k in range(-4, 5):   # red cross over the fallen
                        s.set_at((cx + 10 + k, cy + 7 + k), (228, 59, 68))
                        s.set_at((cx + 10 + k, cy + 7 - k), (228, 59, 68))
        # centre: timer and kill feed
        t = max(0.0, world.end_time if world.winner is not None else world.time)
        self.font.draw(s, f"{int(t // 60)}:{int(t % 60):02d}", W // 2, 6, "#ffffff", scale=2, anchor="midtop")
        y = 22
        for when, killer, team, victim in world.feed[-4:]:
            age = world.time - when
            if age > 6 and world.winner is None:
                continue
            kcol = world.teams[1 - team].light
            vcol = world.teams[team].light
            k_s = self.font.render(killer, kcol)
            a_s = self.font.render(" > ", "#8b9bb4")
            v_s = self.font.render(victim, vcol)
            total = k_s.get_width() + a_s.get_width() + v_s.get_width()
            x = W // 2 - total // 2
            for part in (k_s, a_s, v_s):
                s.blit(part, (x, y))
                x += part.get_width()
            y += 7

    def _overlays(self, world: World, s: pygame.Surface, real_time: float, paused: bool, speed: float) -> None:
        if world.time < 0:
            n = math.ceil(-world.time / (2.6 / 3))
            txt = str(n) if n > 0 else "В БОЙ!"
            self.font.draw(s, "АВТОБИТВА", W // 2, 70, "#fee761", scale=3, anchor="center")
            self.font.draw(s, txt, W // 2, 100, "#ffffff", scale=4, anchor="center")
        elif world.time < 0.8:
            self.font.draw(s, "В БОЙ!", W // 2, 90, "#e43b44", scale=4, anchor="center")
        if world.winner is not None and world.time - world.end_time > 0.4:
            tm = world.teams[world.winner]
            pw, ph = 230, 70
            px, py = W // 2 - pw // 2, 70
            s.blit(self.panel(pw, ph, base="#181425", border=tm.color), (px, py))
            self.font.draw(s, "ПОБЕДА", W // 2, py + 8, "#fee761", scale=3, anchor="midtop")
            self.font.draw(s, tm.name, W // 2, py + 30, tm.light, scale=2, anchor="midtop")
            m = world.mvp()
            if m is not None:
                self.font.draw(s, f"ЛУЧШИЙ БОЕЦ: {m.type.name}  УРОН {int(m.dealt)}  УБИЙСТВ {m.kills}",
                               W // 2, py + 48, world.teams[m.team].light, anchor="midtop")
            surv = world.alive_count(world.winner)
            self.font.draw(s, f"ВЫЖИЛО {surv} ИЗ 7   ВРЕМЯ {int(world.end_time)} С", W // 2, py + 57, "#8b9bb4",
                           anchor="midtop")
        if paused:
            self.font.draw(s, "ПАУЗА", W // 2, H // 2, "#ffffff", scale=3, anchor="center")
        if speed != 1.0:
            self.font.draw(s, f"X{speed:g}", W - 4, H - 8, "#fee761", anchor="topright")
        self.font.draw(s, "ПРОБЕЛ-ПАУЗА  R-ЗАНОВО  1-4 СКОРОСТЬ", 4, H - 8, "#5a6988")
