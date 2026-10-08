"""Smooth pictures over the pixel frame (painted officer faces, the stat web).

The game draws everything at 480x270 and ``present()`` scales the frame up by a whole
number. Painted pictures would turn into mush that way, so a screen blits a small copy into
the logical frame (for screenshots and scale 1) *and* registers the picture here; after the
upscale ``present()`` paints it again at the real screen resolution on top.

Pictures are painted by Pillow in a background thread; until one is ready the caller's
placeholder shows (painting a face takes a few hundredths of a second).
"""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Dict, List, Optional, Set, Tuple

import pygame

_frombytes = getattr(pygame.image, "frombytes", None) or pygame.image.fromstring
Paint = Callable[[int, int], "object"]          # (w, h) -> PIL image (RGB or RGBA) of exactly that size


class HiRes:
    def __init__(self, workers: int = 2):
        self.items: List[Tuple[pygame.Rect, str, Paint]] = []
        self.done: Dict[Tuple[str, int, int], pygame.Surface] = {}
        self.ready: Dict[Tuple[str, int, int], object] = {}
        self.pending: Set[Tuple[str, int, int]] = set()
        self.lock = threading.Lock()
        self.pool = ThreadPoolExecutor(max_workers=workers)
        self.sync = False                           # tests: paint immediately

    def _job(self, k: Tuple[str, int, int], paint: Paint) -> None:
        try:
            img = paint(k[1], k[2])
        except Exception:                           # never kill the game over a portrait
            img = None
        with self.lock:
            self.ready[k] = img
            self.pending.discard(k)

    def get(self, key: str, paint: Paint, w: int, h: int) -> Optional[pygame.Surface]:
        k = (key, w, h)
        s = self.done.get(k)
        if s is not None:
            return s
        with self.lock:
            img = self.ready.pop(k, None)
            busy = k in self.pending
        if img is None and not busy:
            if self.sync:
                self._job(k, paint)
                with self.lock:
                    img = self.ready.pop(k, None)
            else:
                with self.lock:
                    self.pending.add(k)
                self.pool.submit(self._job, k, paint)
        if img is None:
            return None
        mode = img.mode
        surf = _frombytes(img.tobytes(), img.size, mode)
        surf = surf.convert_alpha() if mode == "RGBA" and pygame.display.get_init() and pygame.display.get_surface() \
            else surf
        self.done[k] = surf
        return surf

    def blit(self, s: pygame.Surface, rect: pygame.Rect, key: str, paint: Paint) -> bool:
        """Small copy into the logical frame + a sharp copy after the upscale. False = still painting."""
        rect = pygame.Rect(rect)
        small = self.get(key, paint, rect.w, rect.h)
        if small is not None:
            s.blit(small, rect)
        self.items.append((rect, key, paint))
        return small is not None

    def drop(self) -> None:
        """Forget what was registered so far (a modal window now covers it)."""
        self.items = []

    def present(self, screen: pygame.Surface, ox: int, oy: int, k: int) -> None:
        items, self.items = self.items, []
        if k <= 1:
            return
        for rect, key, paint in items:
            big = self.get(key, paint, rect.w * k, rect.h * k)
            if big is not None:
                screen.blit(big, (ox + rect.x * k, oy + rect.y * k))


HIRES = HiRes()
