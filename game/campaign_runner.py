"""Runs campaign actions in a worker thread so that a storm can stop halfway and wait for the
screen: a real battle to be fought, or the player's answer card (pure Python, no pygame).

The map screen calls ``start`` for anything that may lead to a battle (playing a card, ending
the turn, a spectator round). While the worker runs, the screen shows a frozen frame and only
serves ``request`` - ``ask`` (watch an AI battle or work it out?), ``answer`` (the player's city
is stormed and he holds answer cards) or ``battle`` (fight it now); ``reply`` lets the worker go on.
"""

from __future__ import annotations

import threading
import traceback
from typing import Callable, Optional

WATCH_MODES = ("ask", "calc", "watch")          # what to do with battles between computer realms


class Runner:
    def __init__(self, camp):
        self.camp = camp
        self.watch_ai = "ask"
        self.request: Optional[dict] = None
        self._reply = None
        self._event = threading.Event()
        self.thread: Optional[threading.Thread] = None
        self.result = None
        self.error: Optional[str] = None
        self.finished = False
        camp.battle_hook = self._battle_hook
        camp.answer_hook = self._answer_hook

    # --- main thread ---------------------------------------------------------------------------
    def busy(self) -> bool:
        return self.thread is not None and self.thread.is_alive()

    def start(self, fn: Callable[[], object]) -> None:
        def work():
            try:
                self.result = fn()
            except Exception:                       # keep the game alive; the screen shows it
                self.error = traceback.format_exc()
            self.finished = True
        self.finished = False
        self.result = None
        self.error = None
        self.thread = threading.Thread(target=work, daemon=True)
        self.thread.start()

    def reply(self, value) -> None:
        self._reply = value
        self.request = None
        self._event.set()

    def collect(self):
        """The finished action's result, once (None while running or already collected)."""
        if self.finished and not self.busy():
            self.finished = False
            return ("error", self.error) if self.error else ("ok", self.result)
        return None

    # --- worker thread -------------------------------------------------------------------------
    def _in_worker(self) -> bool:
        return self.thread is not None and threading.current_thread() is self.thread

    def _wait(self, req: dict):
        self._event.clear()
        self.request = req
        self._event.wait()
        return self._reply

    def _battle_hook(self, camp, b) -> bool:
        if not self._in_worker():
            return False
        if camp.player not in (b.attacker, b.defender):
            if self.watch_ai == "calc":
                return False
            if self.watch_ai == "ask":
                choice = self._wait({"kind": "ask", "battle": b})
                if choice == "never":
                    self.watch_ai = "calc"
                if choice != "watch":
                    return False
        return bool(self._wait({"kind": "battle", "battle": b}))

    def _answer_hook(self, camp, b, cards):
        if not self._in_worker():
            return None
        return self._wait({"kind": "answer", "battle": b, "cards": cards})
