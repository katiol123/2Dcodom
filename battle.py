#!/usr/bin/env python3
"""АВТОБИТВА: two squads of up to 7 units fight on their own.

    python battle.py                 # world map; "БЫСТРЫЙ БОЙ" -> squad builder -> endless battles
    python battle.py --auto          # skip the builder, fight with the last / given squads
    python battle.py --blue knight,mage,wolf --red ogre,necromancer --auto
    python battle.py --record b.mp4  # render one battle to video (needs ffmpeg), no window
    python battle.py --record b.gif  # ...or to an animated GIF

Map: drag with the left mouse button (or arrows/WASD), click cities and factions, ESC quits.
Battle keys: SPACE pause, R rematch, M / ESC squad builder, 1-4 speed (x0.5, x1, x2, x4), F fullscreen.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)


def _dpi_aware() -> None:
    """Tell Windows we draw at real pixels: otherwise display scaling (125%/150%)
    stretches the window with smoothing and the pixel art looks blurry."""
    if sys.platform != "win32":
        return
    import ctypes
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)      # per-monitor aware
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def present(logical, screen):
    """Blit the 480x270 frame scaled by a whole number (nearest neighbour), centred.
    Returns (offset_x, offset_y, scale) so mouse positions can be mapped back."""
    import pygame
    from game.sim import H, W
    sw, sh = screen.get_size()
    k = max(1, min(sw // W, sh // H))
    ox, oy = (sw - W * k) // 2, (sh - H * k) // 2
    if (ox, oy) != (0, 0):
        screen.fill((0, 0, 0))
    screen.blit(pygame.transform.scale(logical, (W * k, H * k)), (ox, oy))
    from game.hires import HIRES
    HIRES.present(screen, ox, oy, k)          # painted portraits stay sharp at any scale
    return ox, oy, k


def _icon_surface():
    """Window/taskbar icon: the engine's sword icon, scaled up pixel-perfect."""
    import pygame
    from pixelforge.assets.items import sword
    img = sword().scaled(2).to_image()
    return pygame.image.frombuffer(img.tobytes(), img.size, "RGBA")


def _loading(screen, scale, font, name, i, n, title="КУЁМ ПИКСЕЛИ..."):
    import pygame
    from game.render import INK
    from game.sim import W, H
    surf = pygame.Surface((W, H))
    surf.fill(INK)
    font.draw(surf, title, W // 2, H // 2 - 20, "#fee761", scale=2, anchor="center")
    pygame.draw.rect(surf, (90, 105, 136), (W // 2 - 80, H // 2, 160, 6), 1)
    pygame.draw.rect(surf, (44, 232, 245), (W // 2 - 79, H // 2 + 1, int(158 * (i + 1) / n), 4))
    font.draw(surf, name.upper().replace("_", " "), W // 2, H // 2 + 12, "#8b9bb4", anchor="center")
    present(surf, screen)
    pygame.display.flip()
    pygame.event.pump()


def _squad(arg):
    from game.units import ROSTER, SQUAD_MAX
    keys = [k.strip() for k in arg.split(",") if k.strip()]
    bad = [k for k in keys if k not in ROSTER]
    if bad or not keys or len(keys) > SQUAD_MAX:
        raise argparse.ArgumentTypeError(f"1-{SQUAD_MAX} of: {', '.join(ROSTER)}")
    return keys


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--scale", type=int, default=0, help="window scale (default: fit screen)")
    ap.add_argument("--blue", type=_squad, help="comma separated unit keys for the left squad")
    ap.add_argument("--red", type=_squad, help="comma separated unit keys for the right squad")
    ap.add_argument("--auto", action="store_true", help="skip the squad builder")
    ap.add_argument("--record", metavar="FILE", help="render one battle to .mp4/.gif without a window")
    ap.add_argument("--fps", type=int, default=30, help="recording frame rate")
    ap.add_argument("--mute", action="store_true")
    ap.add_argument("--quit-after", type=float, default=0, help=argparse.SUPPRESS)  # smoke tests
    args = ap.parse_args(argv)

    if args.record:
        os.environ["SDL_VIDEODRIVER"] = "dummy"
        os.environ["SDL_AUDIODRIVER"] = "dummy"
    os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
    os.environ.setdefault("SDL_RENDER_SCALE_QUALITY", "0")   # never smooth when SDL scales
    _dpi_aware()
    import pygame
    from game.assets import SpriteFactory, ensure_unit_sheets
    from game.audio import Sfx
    from game.match import new_battle, prefetch
    from game.menu import Menu
    from game.render import Font, Renderer
    from game.sim import H, W
    from game.units import CLASSIC

    pygame.init()
    pygame.display.set_caption("PixelForge - Автобитва")
    pygame.display.set_icon(_icon_surface())
    if args.record:
        scale = args.scale or 2
        screen = pygame.display.set_mode((W * scale, H * scale))
    else:
        info = pygame.display.Info()
        scale = args.scale or max(1, min((info.current_w - 40) // W, (info.current_h - 80) // H))
        screen = pygame.display.set_mode((W * scale, H * scale))
    font = Font()
    loading = lambda name, i, n, **kw: _loading(screen, scale, font, name, i, n, **kw)  # noqa: E731
    factory = SpriteFactory(workers=1 if args.record else None)
    try:
        renderer = Renderer(ensure_unit_sheets(loading), seed=args.seed or 0)
        logical = pygame.Surface((W, H))
        seed = args.seed if args.seed is not None else int(time.time()) % 100000
        menu = Menu(renderer)
        if args.blue:
            menu.squads[0] = args.blue
        if args.red:
            menu.squads[1] = args.red
        if args.record:
            world, metas = new_battle(menu.squads, seed, factory)
            renderer.add_metas(metas)
            return _record(args, world, renderer, logical, screen, scale)
        return _run(args, screen, scale, font, factory, renderer, logical, menu, seed, loading, Sfx,
                    new_battle, prefetch)
    finally:
        factory.close()


def _run(args, screen, scale, font, factory, renderer, logical, menu, seed, loading, Sfx, new_battle, prefetch):
    import pygame
    from game.sim import H, W
    sfx = Sfx(enabled=not args.mute)
    import game.audio as _audio
    _audio.SFX = sfx                                  # the map's interface sounds and its tune
    clock = pygame.time.Clock()
    speed, paused, fullscreen = 1.0, False, False
    acc = 0.0
    step = 1.0 / 60.0
    real = 0.0
    world = None

    def start(new_seed):
        w, metas = new_battle(menu.squads, new_seed, factory, loading)
        renderer.add_metas(metas)
        prefetch(menu.squads, new_seed + 1, factory)     # draw the next battle's faces in the background
        return w

    view = (0, 0, scale)
    worldmap = None
    siege = None                                      # a campaign storm being fought for real
    import random as _random
    fate = _random.Random(seed)

    def finish_siege(w):
        from game.match import battle_outcome
        battle_outcome(w, siege, fate)
        worldmap.finish_battle()
    titling = not (args.auto or args.blue or args.red)  # the title screen: new / continue / quick battle
    title = None
    on_map = False
    select = None                                     # a new campaign: faction choice, then the world map
    picking = False
    if args.auto:
        world = start(seed)
    while True:
        dt = clock.tick(60) / 1000.0
        real += dt
        if args.quit_after and real > args.quit_after:
            pygame.quit()
            where = (f"battle t={world.time:.1f}s" if world else "title" if titling else "select" if picking
                     else "map" if on_map else "menu")
            print(f"ok: {where} seed={seed} sfx={'on' if sfx.ok else 'off'}")
            return 0
        _audio.music(titling or picking or on_map)                  # the tune plays on the map, not in battle
        mx, my = pygame.mouse.get_pos()
        mouse = ((mx - view[0]) // view[2], (my - view[1]) // view[2])
        for ev in pygame.event.get():
            if hasattr(ev, "pos") and ev.type in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP, pygame.MOUSEMOTION):
                # where the event happened, not where the cursor was when the frame began
                mouse = ((ev.pos[0] - view[0]) // view[2], (ev.pos[1] - view[1]) // view[2])
            if ev.type == pygame.QUIT:
                if on_map and worldmap is not None and not worldmap.runner.busy():
                    worldmap.autosave(force=True)             # the window's X keeps the campaign too
                pygame.quit()
                return 0
            if ev.type == pygame.KEYDOWN and ev.key == pygame.K_f:
                fullscreen = not fullscreen
                # fullscreen at the desktop resolution; present() keeps whole-number scaling
                screen = (pygame.display.set_mode((0, 0), pygame.FULLSCREEN) if fullscreen
                          else pygame.display.set_mode((W * scale, H * scale)))
                continue
            if titling:
                if title and title.handle(ev, mouse) == "quit":
                    pygame.quit()
                    return 0
                continue
            if picking:
                if select and select.handle(ev, mouse) == "quit":
                    picking, select, titling = False, None, True      # ESC: back to the title
                continue
            if on_map:
                action = worldmap.handle(ev, mouse) if worldmap else None
                if action in ("quit", "menu"):
                    if worldmap.runner.busy():
                        worldmap._say("ДОЖДИСЬ КОНЦА ХОДА", "#fee761")
                    else:
                        worldmap.autosave(force=True)
                        worldmap, on_map, titling = None, False, True
                continue
            if world is None:
                action = menu.handle(ev, mouse)
                if action == "back":
                    titling = True
                    continue
                if action == "start":
                    seed += 1
                    world = start(seed)
                    paused = False
                continue
            if ev.type == pygame.KEYDOWN and siege is not None:
                if ev.key == pygame.K_SPACE:
                    paused = not paused
                elif ev.key == pygame.K_ESCAPE:                  # skip to the outcome
                    while world.winner is None and world.time < 240:
                        world.step(step)
                    world.end_time = world.time - 10
                elif ev.key in (pygame.K_1, pygame.K_2, pygame.K_3, pygame.K_4):
                    speed = {pygame.K_1: 0.5, pygame.K_2: 1.0, pygame.K_3: 2.0, pygame.K_4: 4.0}[ev.key]
                continue
            if ev.type == pygame.KEYDOWN:
                if ev.key == pygame.K_SPACE:
                    paused = not paused
                elif ev.key == pygame.K_r:
                    seed += 1
                    world = start(seed)
                elif ev.key in (pygame.K_m, pygame.K_ESCAPE):
                    world = None
                elif ev.key in (pygame.K_1, pygame.K_2, pygame.K_3, pygame.K_4):
                    speed = {pygame.K_1: 0.5, pygame.K_2: 1.0, pygame.K_3: 2.0, pygame.K_4: 4.0}[ev.key]
        if titling:
            if title is None:
                from game.title import TitleScreen
                title = TitleScreen(renderer, lambda: loading("", 0, 1, title="РИСУЕМ КАРТУ МИРА..."))
            title.update(dt, mouse)
            title.draw(logical)
            if title.result:
                choice, saved = title.result, title.saved
                title, titling = None, False
                if choice == "new":
                    picking = True
                elif choice == "battle":
                    pass                                      # the squad builder (world is None)
                else:
                    from game.mapview import WorldMapScreen
                    worldmap = WorldMapScreen(renderer, campaign=saved)
                    worldmap.autosaving = True
                    on_map = True
        elif picking:
            if select is None:
                from game.select import SelectScreen
                select = SelectScreen(renderer, lambda: loading("", 0, 1, title="РИСУЕМ КАРТУ МИРА..."))
            select.update(dt, mouse)
            select.draw(logical)
            if select.result:
                from game.campaign import Campaign
                from game.mapview import WorldMapScreen
                fresh = _random.SystemRandom().randrange(1 << 30)    # every new campaign is a new world
                worldmap = WorldMapScreen(renderer, campaign=Campaign(select.result[1], seed=fresh))
                worldmap.autosaving = True
                worldmap.flash = 1.0                      # the select screen's white flash fades into the map
                picking, select, on_map = False, None, True
        elif on_map:
            if worldmap is None:
                from game.mapview import WorldMapScreen
                worldmap = WorldMapScreen(renderer, lambda: loading("", 0, 1, title="РИСУЕМ КАРТУ МИРА..."))
            worldmap.update(dt, mouse)
            worldmap.draw(logical)
            b = worldmap.battle_request()
            if b is not None and siege is None:            # a storm to fight for real
                from game.match import campaign_battle
                siege = b
                world, metas = campaign_battle(b, factory, lambda name, i, n: loading(name, i, n,
                                                                                      title="К БОЮ..."))
                renderer.add_metas(metas)
                on_map, paused, speed = False, False, 1.0
        elif world is None:
            menu.update(dt, mouse)
            menu.draw(logical)
        else:
            if not paused:
                acc += min(dt, 0.1) * speed
                while acc >= step:
                    world.step(step)
                    acc -= step
                sfx.play(world.sounds)
            if siege is not None:
                if world.winner is not None and world.time - world.end_time > 3.0:
                    finish_siege(world)
                    world, siege, on_map = None, None, True
                    continue
            elif world.winner is not None and world.time - world.end_time > 7.0:
                seed += 1
                world = start(seed)                       # rematch: same squads, new faces
            if siege is not None:
                from game.factions import CITY, FACTION
                renderer.hint = (f"{FACTION[siege.attacker].short} (СЛЕВА) ШТУРМУЕТ {CITY[siege.city].name}, "
                                 f"ЗАЩИЩАЕТ {FACTION[siege.defender].short}." +
                                 ("  СТУЖА: -30% СКОРОСТИ (КРОМЕ СЕВЕРА)." if getattr(siege, "frost", False) else "")
                                 + "  ESC - ИТОГ, 1-4 СКОРОСТЬ")
            else:
                renderer.hint = "ПРОБЕЛ-ПАУЗА  R-РЕВАНШ  M-СОСТАВ  1-4 СКОРОСТЬ"
            renderer.draw(world, logical, real, paused, speed)
        view = present(logical, screen)
        pygame.display.flip()


def _record(args, world, renderer, logical, screen, scale) -> int:
    import pygame
    from game.sim import H, W
    fps = args.fps
    out = args.record
    size = (W * scale, H * scale)
    frames = []
    proc = None
    if out.lower().endswith(".gif"):
        from PIL import Image
    else:
        proc = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
                                 "-s", f"{size[0]}x{size[1]}", "-r", str(fps), "-i", "-", "-c:v", "libx264",
                                 "-pix_fmt", "yuv420p", "-crf", "18", out], stdin=subprocess.PIPE)
    real = 0.0
    sub = 2
    n = 0
    while True:
        for _ in range(sub):
            world.step(1.0 / fps / sub)
        world.sounds.clear()
        real += 1.0 / fps
        renderer.draw(world, logical, real)
        pygame.transform.scale(logical, size, screen)
        data = pygame.image.tobytes(screen, "RGB")
        if proc:
            proc.stdin.write(data)
        else:
            from PIL import Image
            frames.append(Image.frombytes("RGB", size, data).quantize(colors=128, dither=Image.Dither.NONE))
        n += 1
        if (world.winner is not None and world.time - world.end_time > 4.0) or world.time > 240:
            break
    if proc:
        proc.stdin.close()
        proc.wait()
    else:
        frames[0].save(out, save_all=True, append_images=frames[1:], duration=int(1000 / fps), loop=0)
    print(f"recorded {n} frames, winner={world.teams[world.winner].name if world.winner is not None else '-'}"
          f" in {world.end_time:.1f}s -> {out}")
    return 0


def _crash(exc: BaseException) -> None:
    """In the windowed .exe there is no console: log the error and show it in a dialog."""
    import traceback
    text = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    log = None
    try:
        from game.assets import CACHE
        CACHE.mkdir(parents=True, exist_ok=True)
        log = CACHE / "crash.log"
        log.write_text(text, encoding="utf-8")
    except Exception:
        pass
    msg = f"Игра завершилась с ошибкой:\n\n{exc}\n\nПодробности: {log or '-'}"
    if sys.platform == "win32":
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, msg, "Автобитва", 0x10)
    else:
        print(text, file=sys.stderr)


if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()   # sprite workers inside the packaged .exe
    if getattr(sys, "frozen", False):
        try:
            sys.exit(main())
        except SystemExit:
            raise
        except BaseException as e:  # noqa: BLE001 - last-resort handler for the packaged game
            _crash(e)
            sys.exit(1)
    sys.exit(main())
