"""The campaign save (title screen ПРОДОЛЖИТЬ): one autosave slot, written on the player's turn.

pygame-free. The Campaign pickles itself (hooks dropped, see ``Campaign.__getstate__``); newcomer
officers live in the global OFFICER table, so they are registered again on load.
"""

from __future__ import annotations

import pickle
from pathlib import Path
from typing import Optional

from .assets import cache_dir

VERSION = 1
NAME = "campaign.sav"


def path() -> Path:
    return cache_dir().parent / NAME


def exists() -> bool:
    return load() is not None


def save(camp) -> bool:
    try:
        p = path()
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".tmp")
        tmp.write_bytes(pickle.dumps({"version": VERSION, "camp": camp}, protocol=pickle.HIGHEST_PROTOCOL))
        tmp.replace(p)
        return True
    except Exception:
        return False


def load():
    """The saved Campaign, or None when there is none (or it is from an older build)."""
    from .officers import FIRST_NEWCOMER, newcomer
    try:
        data = pickle.loads(path().read_bytes())
    except Exception:
        return None
    if not isinstance(data, dict) or data.get("version") != VERSION:
        return None
    camp = data["camp"]
    for key in sorted(set(camp.ostats) | set(camp.dead)):
        faction, n = key.split(":")
        if int(n) >= FIRST_NEWCOMER:                       # "<faction>:100+" - a young talent
            newcomer(faction, int(n) - FIRST_NEWCOMER)
    return camp


def describe(camp) -> str:
    from .factions import FACTION
    who = FACTION[camp.player].name if camp.player else "ЛЕТОПИСЕЦ"
    return f"{who}, ХОД {camp.turn}"


def clear() -> None:
    try:
        path().unlink()
    except OSError:
        pass
