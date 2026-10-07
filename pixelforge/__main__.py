"""Command line: ``python -m pixelforge <command>``.

    build [OUT]          generate every preset unit, creature, tile, item, VFX
                         -> OUT/sprites/*.png|json, OUT/gif/*.gif, OUT/preview/*.png
    unit NAME [OUT]      one humanoid preset (knight, mage, orc, ...) or random:SEED
    list                 show available presets
"""

from __future__ import annotations

import os
import sys

from .anim import Animation, Sprite
from .assets import items, tiles, ui, vfx
from .canvas import Canvas
from .export import contact_sheet, save_gif, save_sheet, save_sprite_gif
from .units import creatures, humanoid


def _units():
    out = [humanoid.build_humanoid(s) for s in humanoid.PRESETS.values()]
    out.append(creatures.build_slime())
    out.append(creatures.build_slime(creatures.SlimeSpec(name="slime_blue", color="#0099db")))
    for q in (creatures.WOLF, creatures.BOAR, creatures.FOX):
        out.append(creatures.build_quadruped(q))
    return out


def export_sprite(sp: Sprite, out: str, gifs: bool = True) -> None:
    save_sheet(sp, os.path.join(out, "sprites", f"{sp.name}.png"))
    if gifs:
        save_sprite_gif(sp, os.path.join(out, "gif", f"{sp.name}.gif"))


def scene(units, size=(160, 72)) -> Canvas:
    """Small diorama: tiles + units in idle pose, to judge everything together."""
    w, h = size
    c = Canvas(w, h)
    g, d = tiles.grass(seed=2), tiles.dirt(seed=3)
    for y in range(0, h, 16):
        for x in range(0, w, 16):
            c.blit(d if (y // 16 == 3) else g, x, y)
    x = 0
    for sp in units:
        img = sp["idle"].frames[0].image
        if x + sp.width > w:
            break
        c.blit(img, x, h - 16 - sp.height + 6)
        x += sp.width - 18 if sp.width >= 48 else sp.width - 8
    c.blit(ui.panel(54, 13), 2, 2)
    c.blit(ui.bar(30, 0.7), 4, 6)
    c.blit(ui.label("HP"), 37, 6)
    return c


def build(out: str = "out") -> None:
    os.makedirs(out, exist_ok=True)
    units = _units()
    for sp in units:
        export_sprite(sp, out)
        print("unit  ", sp.name, ", ".join(f"{a.name}:{len(a.frames)}" for a in sp.animations.values()))
    hum = [u for u in units if u.width == 48]
    contact_sheet(hum[:4], os.path.join(out, "preview", "humanoids_1.png"), scale=3)
    contact_sheet(hum[4:], os.path.join(out, "preview", "humanoids_2.png"), scale=3)
    contact_sheet([u for u in units if u.width != 48], os.path.join(out, "preview", "creatures.png"), scale=3)

    ts = tiles.tileset()
    export_sprite(ts, out, gifs=False)
    save_gif(ts["water"], os.path.join(out, "gif", "water.gif"), scale=8)
    it = items.item_set()
    export_sprite(it, out, gifs=False)
    save_gif(it["coin"], os.path.join(out, "gif", "coin.gif"), scale=8)
    for sp in vfx.vfx_set():
        export_sprite(sp, out, gifs=False)
        for a in sp.animations.values():
            save_gif(a, os.path.join(out, "gif", f"{a.name}.gif"), scale=8, background="#262b44")
    contact_sheet([ts, it] + vfx.vfx_set(), os.path.join(out, "preview", "assets.png"), scale=4)
    scene(units[:5]).save(os.path.join(out, "preview", "scene.png"), scale=4)
    print("tiles, items, vfx, previews ->", out)


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    cmd = argv.pop(0) if argv else "build"
    if cmd == "build":
        build(argv[0] if argv else "out")
    elif cmd == "list":
        print("humanoids:", ", ".join(humanoid.PRESETS), "| random:SEED")
        print("creatures: slime, wolf, boar, fox")
    elif cmd == "unit":
        name = argv[0]
        out = argv[1] if len(argv) > 1 else "out"
        spec = humanoid.random_spec(int(name.split(":")[1])) if name.startswith("random:") else humanoid.PRESETS[name]
        sp = humanoid.build_humanoid(spec)
        export_sprite(sp, out)
        contact_sheet([sp], os.path.join(out, "preview", f"{sp.name}.png"), scale=4)
        print("written", sp.name, "->", out)
    else:
        print(__doc__)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
