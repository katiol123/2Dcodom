#!/usr/bin/env python3
"""АВТОБИТВА: two squads of 7 fight on their own.

    python battle.py                 # window, endless battles (new seed each round)
    python battle.py --seed 7        # a specific battle
    python battle.py --record b.mp4  # render a battle to video (needs ffmpeg), no window
    python battle.py --record b.gif  # ...or to an animated GIF

Keys: SPACE pause, R new battle, 1-4 speed (x0.5, x1, x2, x4), F fullscreen, ESC quit.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)


def _icon_surface():
    """Window/taskbar icon: the engine's sword icon, scaled up pixel-perfect."""
    import pygame
    from pixelforge.assets.items import sword
    img = sword().scaled(2).to_image()
    return pygame.image.frombuffer(img.tobytes(), img.size, "RGBA")


def _loading(screen, scale, font, name, i, n):
    import pygame
    from game.render import INK
    from game.sim import W, H
    surf = pygame.Surface((W, H))
    surf.fill(INK)
    font.draw(surf, "КУЁМ ПИКСЕЛИ...", W // 2, H // 2 - 20, "#fee761", scale=2, anchor="center")
    pygame.draw.rect(surf, (90, 105, 136), (W // 2 - 80, H // 2, 160, 6), 1)
    pygame.draw.rect(surf, (44, 232, 245), (W // 2 - 79, H // 2 + 1, int(158 * (i + 1) / n), 4))
    font.draw(surf, name.upper().replace("_", " "), W // 2, H // 2 + 12, "#8b9bb4", anchor="center")
    pygame.transform.scale(surf, screen.get_size(), screen)
    pygame.display.flip()
    pygame.event.pump()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--scale", type=int, default=0, help="window scale (default: fit screen)")
    ap.add_argument("--record", metavar="FILE", help="render one battle to .mp4/.gif without a window")
    ap.add_argument("--fps", type=int, default=30, help="recording frame rate")
    ap.add_argument("--mute", action="store_true")
    ap.add_argument("--quit-after", type=float, default=0, help=argparse.SUPPRESS)  # smoke tests
    args = ap.parse_args(argv)

    if args.record:
        os.environ["SDL_VIDEODRIVER"] = "dummy"
        os.environ["SDL_AUDIODRIVER"] = "dummy"
    os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
    import pygame
    from game.assets import anim_infos, ensure_unit_sheets
    from game.audio import Sfx
    from game.render import Font, Renderer
    from game.sim import H, W, World

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
    metas = ensure_unit_sheets(lambda name, i, n: _loading(screen, scale, font, name, i, n))
    anims = {k: anim_infos(m) for k, m in metas.items()}
    seed = args.seed if args.seed is not None else int(time.time()) % 100000
    world = World(anims, seed)
    renderer = Renderer(world, metas, seed)
    logical = pygame.Surface((W, H))
    sfx = Sfx(enabled=not (args.mute or args.record))

    if args.record:
        return _record(args, world, renderer, logical, screen, scale)

    clock = pygame.time.Clock()
    speed, paused, fullscreen = 1.0, False, False
    acc = 0.0
    step = 1.0 / 60.0
    real = 0.0
    while True:
        dt = clock.tick(60) / 1000.0
        real += dt
        if args.quit_after and real > args.quit_after:
            pygame.quit()
            print(f"ok: t={world.time:.1f}s seed={seed} sfx={'on' if sfx.ok else 'off'}")
            return 0
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT or (ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE):
                pygame.quit()
                return 0
            if ev.type == pygame.KEYDOWN:
                if ev.key == pygame.K_SPACE:
                    paused = not paused
                elif ev.key == pygame.K_r:
                    seed += 1
                    world = World(anims, seed)
                elif ev.key in (pygame.K_1, pygame.K_2, pygame.K_3, pygame.K_4):
                    speed = {pygame.K_1: 0.5, pygame.K_2: 1.0, pygame.K_3: 2.0, pygame.K_4: 4.0}[ev.key]
                elif ev.key == pygame.K_f:
                    fullscreen = not fullscreen
                    flags = pygame.FULLSCREEN | pygame.SCALED if fullscreen else 0
                    screen = pygame.display.set_mode((W * scale, H * scale), flags)
        if not paused:
            acc += min(dt, 0.1) * speed
            while acc >= step:
                world.step(step)
                acc -= step
            sfx.play(world.sounds)
        if world.winner is not None and world.time - world.end_time > 7.0:
            seed += 1
            world = World(anims, seed)
        renderer.draw(world, logical, real, paused, speed)
        pygame.transform.scale(logical, screen.get_size(), screen)
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
    if getattr(sys, "frozen", False):
        try:
            sys.exit(main())
        except SystemExit:
            raise
        except BaseException as e:  # noqa: BLE001 - last-resort handler for the packaged game
            _crash(e)
            sys.exit(1)
    sys.exit(main())
