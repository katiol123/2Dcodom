"""16x16 item icons: built from shapes, shaded and selectively outlined by the
same shader as units, so icons match the sprites' lighting."""

from __future__ import annotations

import math
from typing import Callable, Dict

from ..anim import Animation, Sprite
from ..canvas import Canvas
from ..color import ColorLike, mix
from ..shading import BASE, HIGHLIGHT, LIGHT, SHADOW, Ink, Material, PartBuffer, Shader

SHADER = Shader()


def _render(size: int, draw: Callable[[PartBuffer], None], shader: Shader = SHADER) -> Canvas:
    buf = PartBuffer(size, size)
    draw(buf)
    return shader.render(buf)


def sword(blade: ColorLike = "#c0cbdc", hilt: ColorLike = "#733e39", guard: ColorLike = "#feae34",
          size: int = 16) -> Canvas:
    steel, wood, gold = Material.of("steel", blade, shiny=True), Material.of("wood", hilt), Material.of("gold", guard, shiny=True)

    def d(b):
        b.capsule(4.5, 11.5, 13.5, 2.5, 2, Ink(steel, "blade", 1))
        b.line(5, 11, 13, 3, Ink(steel, "edge", 1.5, level=HIGHLIGHT, outline=False))
        b.capsule(2.5, 13.5, 4.5, 11.5, 2, Ink(wood, "hilt", 2))
        b.capsule(3.5, 9.5, 6.5, 12.5, 2, Ink(gold, "guard", 3))
        b.set(1, 14, Ink(gold, "pommel", 3))
    return _render(size, d)


def axe(head: ColorLike = "#8b9bb4", handle: ColorLike = "#b86f50", size: int = 16) -> Canvas:
    steel, wood = Material.of("steel", head, shiny=True), Material.of("wood", handle)

    def d(b):
        b.capsule(3.5, 13.5, 11.5, 3.5, 2, Ink(wood, "handle", 1))
        b.polygon([(8, 2), (13, 1), (15, 6), (12, 9), (10, 5)], Ink(steel, "head", 2))
    return _render(size, d)


def potion(liquid: ColorLike = "#e43b44", glass: ColorLike = "#c0cbdc", cork: ColorLike = "#b86f50",
           size: int = 16) -> Canvas:
    liq = Material.of("liquid", liquid, shiny=True)
    gl = Material.of("glass", glass, shiny=True)
    ck = Material.of("cork", cork)

    def d(b):
        b.circle(8, 10, 5, Ink(gl, "glass", 1))
        b.rect(6, 3, 4, 4, Ink(gl, "glass", 1))
        b.ellipse(8, 10.5, 4, 3.5, Ink(liq, "liquid", 2))
        b.rect(6, 1, 4, 2, Ink(ck, "cork", 3))
        b.set(5, 8, Ink(gl, "glint", 4, level=HIGHLIGHT, outline=False))
        b.set(5, 9, Ink(gl, "glint", 4, level=LIGHT, outline=False))
    return _render(size, d)


def shield(face: ColorLike = "#124e89", rim: ColorLike = "#c0cbdc", emblem: ColorLike = "#feae34",
           size: int = 16) -> Canvas:
    f, r, e = Material.of("face", face), Material.of("rim", rim, shiny=True), Material.of("emblem", emblem, shiny=True)
    pts = [(2, 2), (14, 2), (14, 8), (8, 15), (2, 8)]
    inner = [(4, 4), (12, 4), (12, 8), (8, 12.5), (4, 8)]

    def d(b):
        b.polygon(pts, Ink(r, "rim", 1))
        b.polygon(inner, Ink(f, "face", 2, contour=False))
        b.rect(7, 5, 2, 6, Ink(e, "emblem", 3))
        b.rect(5, 7, 6, 2, Ink(e, "emblem", 3))
    return _render(size, d)


def gem(color: ColorLike = "#2ce8f5", size: int = 16) -> Canvas:
    m = Material.of("gem", color, shiny=True)

    def d(b):
        b.polygon([(4, 6), (6, 3), (10, 3), (12, 6), (8, 13)], Ink(m, "gem", 1))
        b.line(4, 6, 11, 6, Ink(m, "facet", 2, level=LIGHT, outline=False))
        b.line(8, 7, 8, 11, Ink(m, "facet", 2, level=SHADOW, outline=False))
        b.set(6, 4, Ink(m, "glint", 3, level=HIGHLIGHT, outline=False))
    return _render(size, d)


def heart(color: ColorLike = "#e43b44", size: int = 16) -> Canvas:
    m = Material.of("heart", color, shiny=True)

    def d(b):
        b.circle(5.5, 6, 3, Ink(m, "h", 1))
        b.circle(10.5, 6, 3, Ink(m, "h", 1))
        b.polygon([(2.6, 7), (13.4, 7), (8, 13.5)], Ink(m, "h", 1))
    return _render(size, d)


def key(color: ColorLike = "#feae34", size: int = 16) -> Canvas:
    m = Material.of("gold", color, shiny=True)

    def d(b):
        b.circle(5, 6, 3, Ink(m, "k", 1))
        b.capsule(7, 7.5, 13.5, 7.5, 2, Ink(m, "k", 1))
        b.rect(11, 8, 1, 3, Ink(m, "k", 1))
        b.rect(13, 8, 1, 2, Ink(m, "k", 1))
        b.set(4, 5, None)
        b.set(5, 6, None)
        b.set(4, 6, None)
        b.set(5, 5, None)
    return _render(size, d)


def scroll(paper: ColorLike = "#ead4aa", ribbon: ColorLike = "#a22633", size: int = 16) -> Canvas:
    p, r = Material.of("paper", paper), Material.of("ribbon", ribbon)

    def d(b):
        b.rect(3, 4, 10, 8, Ink(p, "sheet", 1))
        b.capsule(2.5, 3.5, 13.5, 3.5, 3, Ink(p, "roll_top", 2))
        b.capsule(2.5, 12.5, 13.5, 12.5, 3, Ink(p, "roll_bot", 2))
        for y in (6, 8, 10):
            b.line(5, y, 10 - (y == 10) * 3, y, Ink(p, "text", 1.5, level=SHADOW, outline=False))
        b.rect(7, 2, 2, 12, Ink(r, "ribbon", 3))
    return _render(size, d)


def coin(color: ColorLike = "#feae34", size: int = 16, frames: int = 6) -> Animation:
    """Spinning coin: the ellipse width follows |cos| of the spin angle."""
    m = Material.of("gold", color, shiny=True)
    anim = Animation("coin")
    for i in range(frames):
        w = abs(math.cos(math.pi * i / frames))
        rx = max(0.6, 5 * w)

        def d(b, rx=rx):
            b.ellipse(8, 8, rx, 5, Ink(m, "coin", 1))
            if rx > 2.5:
                b.ellipse(8, 8, rx - 2, 3, Ink(m, "inner", 2, level=SHADOW, outline=False, contour=False))
                b.rect(8, 6, 1, 4, Ink(m, "mark", 3, level=LIGHT, outline=False))
        anim.add(_render(size, d), 90)
    return anim


ICONS: Dict[str, Callable[[], Canvas]] = {
    "sword": sword, "axe": axe, "potion_red": potion,
    "potion_blue": lambda: potion("#0099db"), "potion_green": lambda: potion("#63c74d"),
    "shield": shield, "gem": gem, "gem_red": lambda: gem("#e43b44"), "heart": heart,
    "key": key, "scroll": scroll,
}


def item_set() -> Sprite:
    sp = Sprite("items", 16, 16)
    for name, fn in ICONS.items():
        sp.add(Animation(name, loop=False).add(fn(), 1000))
    sp.add(coin())
    return sp
