"""Tiny retro sound effects synthesised with numpy (no audio files needed).
Silently disabled if there is no audio device."""

from __future__ import annotations

from typing import Dict, List

SR = 22050


def _make(np):
    rng = np.random.default_rng(1)

    def t(sec):
        return np.linspace(0, sec, int(SR * sec), endpoint=False)

    def env(n, attack=0.005, decay=6.0):
        x = np.linspace(0, 1, n)
        return np.exp(-decay * x) * np.minimum(1.0, np.arange(n) / max(1, int(SR * attack)))

    def noise(sec, decay=8.0, lp=0.5):
        n = int(SR * sec)
        w = rng.uniform(-1, 1, n)
        # crude low-pass: running average
        k = max(1, int(1 / max(lp, 0.02)))
        w = np.convolve(w, np.ones(k) / k, mode="same")
        return w * env(n, decay=decay)

    def tone(f0, f1, sec, shape="square", decay=5.0):
        tt = t(sec)
        f = np.linspace(f0, f1, len(tt))
        ph = np.cumsum(f) / SR * 2 * np.pi
        w = np.sign(np.sin(ph)) if shape == "square" else np.sin(ph)
        return w * env(len(tt), decay=decay)

    def mix(*parts):
        n = max(len(p) for p in parts)
        out = np.zeros(n)
        for p in parts:
            out[:len(p)] += p
        return out

    return {
        "hit": noise(0.09, 22, 0.35) * 0.8,
        "block": mix(tone(1400, 1300, 0.12, "sine", 18) * 0.5, noise(0.05, 30, 1.0) * 0.4),
        "dodge": noise(0.12, 12, 0.08) * 0.4,
        "bow": mix(tone(520, 180, 0.12, "sine", 14) * 0.5, noise(0.05, 30, 0.2) * 0.3),
        "fireball": noise(0.35, 5, 0.12) * 0.5,
        "explosion": mix(noise(0.6, 5, 0.06) * 1.0, tone(90, 40, 0.4, "sine", 6) * 0.6),
        "death": tone(330, 90, 0.35, "square", 5) * 0.25,
        "stun": mix(tone(900, 700, 0.15, "square", 10) * 0.2, noise(0.08, 25, 0.3) * 0.6),
        "warcry": mix(tone(110, 80, 0.45, "square", 3) * 0.3, noise(0.4, 4, 0.1) * 0.4),
        "rage": tone(160, 120, 0.4, "square", 4) * 0.3,
        "nova": mix(tone(1800, 600, 0.35, "sine", 6) * 0.35, noise(0.3, 8, 0.6) * 0.3),
        "smoke": noise(0.4, 6, 0.1) * 0.4,
        "taunt": tone(600, 800, 0.18, "square", 8) * 0.2,
    }


class Sfx:
    def __init__(self, enabled: bool = True):
        self.ok = False
        self.sounds: Dict[str, object] = {}
        if not enabled:
            return
        try:
            import numpy as np
            import pygame
            pygame.mixer.pre_init(SR, -16, 1, 512)
            pygame.mixer.init()
            freq, size, channels = pygame.mixer.get_init()
            pygame.mixer.set_num_channels(24)
            for name, wave in _make(np).items():
                w = np.clip(wave * 0.6, -1, 1)
                arr = (w * 32767).astype(np.int16)
                if channels > 1:
                    arr = np.repeat(arr[:, None], channels, axis=1)
                self.sounds[name] = pygame.sndarray.make_sound(np.ascontiguousarray(arr))
            self.ok = True
        except Exception:
            self.ok = False

    def play(self, events: List[str]) -> None:
        if not self.ok:
            events.clear()
            return
        played = set()
        for e in events:
            if e in played or e not in self.sounds:
                continue
            played.add(e)
            self.sounds[e].play()
        events.clear()
