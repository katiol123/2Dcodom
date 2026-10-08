"""Tiny retro sound effects synthesised with numpy (no audio files needed), the sounds of the
map's card table and a quiet lute-and-drone loop for the world map.
Silently disabled if there is no audio device.

The map's interface plays its sounds through ``ui(name)`` (a no-op until ``battle.py`` installs
the ``Sfx`` instance as ``SFX``), so tests and headless runs stay silent."""

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

    def pluck(freq, sec=0.9, bright=1.0, decay=4.0):
        """A plucked string: harmonics that die away faster the higher they are."""
        tt = t(sec)
        out = np.zeros(len(tt))
        for k in range(1, 9):
            amp = (1.0 / k) * (bright if k > 2 else 1.0)
            out += amp * np.sin(2 * np.pi * freq * k * tt) * np.exp(-decay * (0.6 + 0.5 * k) * tt)
        return out * np.minimum(1.0, np.arange(len(tt)) / (SR * 0.002)) * 0.35

    def bell(freq, sec=1.2, decay=3.0):
        tt = t(sec)
        parts = ((1.0, 1.0), (2.76, 0.5), (5.4, 0.25), (8.93, 0.12))
        return sum(a * np.sin(2 * np.pi * freq * r * tt) * np.exp(-decay * r ** 0.5 * tt) for r, a in parts) * 0.3

    def at(wave, sec, total):
        out = np.zeros(int(SR * total))
        i = int(SR * sec)
        n = min(len(wave), len(out) - i)
        out[i:i + n] += wave[:n]
        return out

    def swish(sec=0.12, rise=True):
        n = int(SR * sec)
        w = rng.uniform(-1, 1, n)
        w = w - np.convolve(w, np.ones(6) / 6, mode="same")        # keep the hiss, drop the rumble
        shape = np.sin(np.linspace(0, np.pi, n)) ** (1.5 if rise else 0.7)
        return w * shape

    def drum(f=70, sec=0.35):
        return mix(tone(f * 1.6, f, sec, "sine", 9) * 0.9, noise(0.08, 30, 0.3) * 0.3)

    def horn(f, sec=0.7):
        tt = t(sec)
        vib = 1 + 0.006 * np.sin(2 * np.pi * 5.5 * tt)
        ph = np.cumsum(f * vib) / SR * 2 * np.pi
        saw = sum(np.sin(k * ph) / k for k in range(1, 7))
        envl = np.minimum(1, tt / 0.06) * np.exp(-1.8 * np.maximum(0, tt - 0.25))
        return saw * envl * 0.25

    def tick(sec=0.015, level=0.3):
        n = int(SR * sec)
        return rng.uniform(-1, 1, n) * np.exp(-np.linspace(0, 7, n)) * level

    D, A, F, C = 146.8, 220.0, 174.6, 261.6
    ui = {
        "deal": mix(swish(0.09) * 0.35, at(tick(0.02, 0.25), 0.07, 0.1)),
        "flip": mix(at(tick(0.015, 0.3), 0, 0.06), at(tick(0.015, 0.2), 0.035, 0.06)),
        "play": mix(swish(0.22) * 0.45, at(drum(90, 0.25) * 0.5, 0.16, 0.42)),
        "coins": mix(*[at(bell(2400 + 300 * k, 0.4, 9) * 0.5, 0.06 * k, 0.6) for k in range(4)]),
        "drums": mix(at(drum(65), 0, 0.9), at(drum(65), 0.18, 0.9), at(drum(80), 0.42, 0.9) * 1.2),
        "horn": mix(horn(D), horn(A) * 0.7),
        "whisper": swish(0.5, False) * 0.25 * (0.6 + 0.4 * np.sin(np.linspace(0, 40, int(SR * 0.5)))),
        "stamp": mix(drum(55, 0.3) * 0.9, noise(0.06, 25, 0.5) * 0.5),
        "tear": swish(0.25, False) * 0.5,
        "harp": mix(*[at(pluck(f, 1.2), 0.07 * k, 1.6) for k, f in enumerate((D, F, A, 2 * D, 2 * F))]),
        "refuse": mix(at(pluck(A, 0.8), 0, 1.0), at(pluck(F / 1.5, 0.9), 0.18, 1.0)),
        "betrayal": mix(horn(D * 0.5, 1.0), horn(D * 0.5 * 1.414, 1.0) * 0.8) * 0.9,
        "gong": mix(bell(98, 2.6, 1.2) * 1.6, at(drum(50, 0.6) * 0.6, 0, 2.6)),
        "fanfare": mix(*[at(horn(f, 0.35) * 0.8, 0.11 * k, 0.9) for k, f in enumerate((D * 2, F * 2, A * 2, D * 4))]),
        "turn": mix(bell(587, 1.0, 4) * 0.7, at(drum(70, 0.3) * 0.5, 0, 1.0)),
        "click": tick(0.012, 0.25),
        "march": mix(*[at(tick(0.05, 0.5 if k % 2 else 0.3), 0.09 * k, 0.8) for k in range(8)]),
        "seal": mix(at(drum(60, 0.3), 0, 0.9), at(bell(880, 0.8, 5) * 0.5, 0.05, 0.9)),
        "levelup": mix(*[at(pluck(f, 0.6, 1.4), 0.06 * k, 0.9) for k, f in enumerate((D * 2, F * 2, A * 2, C * 2, D * 4))]),
    }
    return {
        **ui,
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


def _music(np):
    """About half a minute of a slow modal tune: a drone, a lute and now and then a soft drum."""
    rng = np.random.default_rng(7)
    total = 32.0
    out = np.zeros(int(SR * total))
    tt = np.arange(len(out)) / SR
    out += 0.05 * np.sin(2 * np.pi * 73.4 * tt) + 0.03 * np.sin(2 * np.pi * 110 * tt)   # D and A drone
    out *= 0.8 + 0.2 * np.sin(2 * np.pi * tt / 8)
    scale = [146.8, 164.8, 174.6, 196.0, 220.0, 246.9, 261.6, 293.7]           # D dorian
    beat = 0.5
    i = 0
    deg = 0
    while i * beat < total - 2:
        if rng.random() < 0.72:
            deg = int(np.clip(deg + rng.choice([-2, -1, -1, 1, 1, 2, 0]), 0, len(scale) - 1))
            f = scale[deg]
            n = int(SR * 1.6)
            nt = np.arange(n) / SR
            note = sum((1 / k) * np.sin(2 * np.pi * f * k * nt) * np.exp(-3.2 * (0.6 + 0.5 * k) * nt)
                       for k in range(1, 7)) * 0.11
            a = int(SR * i * beat)
            out[a:a + n] += note[:len(out) - a]
        if i % 8 == 0:
            n = int(SR * 0.5)
            nt = np.arange(n) / SR
            d = np.sin(2 * np.pi * (60 + 40 * np.exp(-12 * nt)) * nt) * np.exp(-7 * nt) * 0.1
            a = int(SR * i * beat)
            out[a:a + n] += d[:len(out) - a]
        i += 1
    fade = int(SR * 1.5)                                       # seamless loop: crossfade the ends
    out[:fade] = out[:fade] * np.linspace(0, 1, fade) + out[-fade:] * np.linspace(1, 0, fade)
    out = out[:-fade]
    return out / max(1e-6, np.abs(out).max()) * 0.6


SFX = None                       # the game's Sfx, installed by battle.py


def ui(name: str) -> None:
    """Play an interface sound (silently nothing without an audio device)."""
    if SFX is not None and SFX.ok and name in SFX.sounds:
        SFX.sounds[name].play()


def music(on: bool) -> None:
    if SFX is not None:
        SFX.music(on)


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
            self._np, self._channels = np, channels
            self.tune = None
            self.music_on = False
        except Exception:
            self.ok = False

    def music(self, on: bool) -> None:
        """The world map's tune (built on first use, looped on its own channel)."""
        if not self.ok or on == self.music_on:
            return
        import pygame
        self.music_on = on
        if not on:
            if self.tune is not None:
                self.tune.fadeout(600)
            return
        if self.tune is None:
            np = self._np
            arr = (np.clip(_music(np), -1, 1) * 32767 * 0.8).astype(np.int16)
            if self._channels > 1:
                arr = np.repeat(arr[:, None], self._channels, axis=1)
            self.tune = pygame.sndarray.make_sound(np.ascontiguousarray(arr))
            self.tune.set_volume(0.55)
        self.tune.play(loops=-1, fade_ms=1500)

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
