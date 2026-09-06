"""Reconciles the static ROM ledger with the live RAM snapshot into the
single output contract the display reads: tracker_state.json.

Every poll produces the complete state from absolute data (no event history),
so a cold restart after any disconnect reproduces the exact same JSON from
the current RAM alone.  The snapshot file on disk is only a safety net for
mid-run unsaved resets.
"""

from __future__ import annotations

import datetime
import json
import os
import tempfile
from typing import Optional

from . import ram as ramlib
from .items import ITEM_NAMES
from .rom import Ledger, LedgerLocation

SCHEMA_VERSION = 1
OW_LABELS = {"white_sword": "White Sword Cave", "armos": "Armos Statue", "coast": "Coast"}


def _item_view(item: Optional[int]) -> Optional[dict]:
    if item is None:
        return None
    return {"id": item, "name": ITEM_NAMES.get(item, f"0x{item:02X}")}


def _taken(raw: bytes, loc: Optional[LedgerLocation]) -> Optional[bool]:
    if loc is None or loc.screen is None:
        return None
    return ramlib.taken(raw, loc.screen)


def _check_view(loc: LedgerLocation, raw: bytes) -> dict:
    return {
        "room": loc.room,
        "item": _item_view(loc.item),
        "taken": _taken(raw, loc),
    }


def _resolved(raw: bytes, loc: Optional[LedgerLocation]) -> dict:
    """View for a named dungeon location (heart/triforce)."""
    return {
        "room": loc.room if loc else None,
        "item": _item_view(loc.item if loc else None),
        "taken": _taken(raw, loc),
    }


def build_state(
    raw: Optional[bytes],
    ledger: Optional[Ledger],
    now: Optional[datetime.datetime] = None,
    connected: bool = False,
    source: str = "none",
    seed_changed: bool = False,
) -> dict:
    """raw: full 2KB RAM bytes (or None when no live source)."""
    now = now or datetime.datetime.now(datetime.timezone.utc)

    if raw is not None:
        snap = ramlib.decode(raw)
        playing = snap["playing"]
        game_mode = snap["gameMode"]
        level = snap["level"]
        room = snap["room"]
        screens = snap["screens"]
    else:
        playing = False
        game_mode = None
        level = None
        room = None
        screens = None

    state = {
        "schema": SCHEMA_VERSION,
        "updatedAt": now.isoformat(),
        "meta": {
            "source": source,
            "connected": connected,
            "playing": playing,
            "gameMode": game_mode,
            "level": level,
            "room": room,
            "rom": {
                "loaded": ledger is not None,
                "path": ledger.rom_path if ledger else None,
                "hash": ledger.rom_hash if ledger else None,
                "z1rLikely": ledger.z1r_likely if ledger else None,
                "quest": ({"early": ledger.quest_early, "late": ledger.quest_late}
                          if ledger else None),
                "seedChangedSinceLastRead": seed_changed,
            },
        },
        "inventory": snap["inventory"] if raw is not None else None,
        "hearts": snap["hearts"] if raw is not None else None,
        "triforce": snap["triforce"] if raw is not None else None,
        "locations": _locations(raw, screens, ledger),
        "provenance": _provenance(raw, ledger),
        "notes": [],
    }

    if ledger is None:
        state["notes"].append({
            "code": "no_seed",
            "message": "No .nes file parsed; per-location details and item "
                       "attribution are unavailable. Inventory, heart and "
                       "triforce totals are still live from RAM.",
        })
    if seed_changed:
        state["notes"].append({
            "code": "seed_changed",
            "message": "The ROM file changed since the last read; the ledger "
                       "was rebuilt. Confirm this is the intended seed.",
        })
    if ledger is not None and not ledger.dungeon_layout_confident:
        state["notes"].append({
            "code": "dungeon_layout_unconfirmed",
            "message": "This ROM's dungeon data pointers weren't recognized "
                       "(possibly an older/different randomizer version); "
                       "falling back to a best-effort layout. Triforce "
                       "tracking should still be reliable, but Heart/Items "
                       "per level may be wrong for this seed.",
        })
    return state


def _locations(raw, screens, ledger) -> dict:
    locs: dict = {"levels": [], "overworld": {}, "overworldHeartCaves": {}}

    if ledger:
        # If the dungeon grid pointers weren't recognized, room-discovery ran
        # against best-effort/possibly-wrong data -- Heart/Items scanning is
        # not trustworthy in that case (can produce dozens of bogus "checks"
        # spanning nearly the whole room table). Triforce is unaffected: it
        # reads level_info directly, independent of grid content.
        confident = ledger.dungeon_layout_confident
        for level in range(1, 10):
            led = ledger.levels.get(level)
            if led is None:
                continue

            if confident:
                checks = [_check_view(c, raw) for c in led.checks]
                taken_count = sum(1 for c in checks if c["taken"] is True)
                items_view = {"total": len(checks), "taken": taken_count, "checks": checks}
                heart_view = _resolved(raw, led.heart)
            else:
                items_view = {"total": None, "taken": None, "checks": []}
                heart_view = {"room": None, "item": None, "taken": None}

            locs["levels"].append({
                "level": level,
                "heart": heart_view,
                "triforce": _resolved(raw, led.triforce),
                "items": items_view,
            })
    else:
        # Seedless fallback: only what RAM alone can honestly say.
        for level in range(1, 10):
            locs["levels"].append({
                "level": level,
                "heart": {"taken": None, "item": None, "room": None},
                "triforce": {"taken": None, "item": None, "room": None},
                "items": {"total": None, "taken": None, "checks": []},
            })

    ow = {}
    if ledger:
        for key, loc in ledger.overworld.items():
            ow[key] = {
                "label": OW_LABELS.get(key, loc.label),
                "item": _item_view(loc.item),
                "taken": _taken(raw, loc),
                "screen": loc.screen,
            }
        for key, loc in ledger.other_ow_screens.items():
            ow[key] = {
                "label": loc.label,
                "item": _item_view(loc.item),
                "taken": _taken(raw, loc),
                "screen": loc.screen,
            }
    else:
        for key, label in OW_LABELS.items():
            ow[key] = {"label": label, "item": None, "taken": None, "screen": None}
    locs["overworld"] = ow

    # Overworld heart caves: count only -- never reveal which in the UI data.
    cleared = 0
    heart_screens = []
    if ledger:
        for screen_offset, verified in ledger.heart_cave_screens:
            taken_flag = ramlib.taken(raw, ramlib.RAM["ow_screens"] + screen_offset)
            if taken_flag:
                cleared += 1
            heart_screens.append({"screen": screen_offset, "taken": taken_flag, "verified": verified})
    locs["overworldHeartCaves"] = {
        "total": (len(ledger.heart_cave_screens) if ledger else 0),
        "cleared": cleared,
        "screens": heart_screens,
    }
    return locs


def _pc(raw: bytes) -> list:
    return ramlib.decode(raw)["triforce"]["pieces"]


def _provenance(raw, ledger) -> dict:
    prov: dict = {}
    if raw is None or ledger is None:
        return prov
    for level in range(1, 10):
        led = ledger.levels.get(level)
        if not led:
            continue
        for loc in (list(led.checks) + [led.triforce, led.heart]):
            if loc and loc.item is not None and _taken(raw, loc):
                _add(prov, loc.item, loc.label)
    for key, loc in ledger.overworld.items():
        if loc.item is not None and _taken(raw, loc):
            _add(prov, loc.item, loc.label)
    return prov


def _add(prov: dict, item: int, label: str) -> None:
    name = ITEM_NAMES.get(item, f"0x{item:02X}")
    prov.setdefault(name, [])
    if label not in prov[name]:
        prov[name].append(label)


# ------------------------------------------------------------------ persistence

def write_json_atomic(path: str, state: dict, retries: int = 5,
                       retry_delay: float = 0.05) -> None:
    """Write the contract atomically so a reader never sees a torn file.

    On Windows, os.replace() can transiently fail with PermissionError if
    another process (antivirus, a sync client like Dropbox/OneDrive watching
    the destination folder, an editor with the file open, etc.) is holding a
    momentary lock on the destination file. That's not a real error -- it
    clears on its own almost immediately -- so retry briefly before giving up.
    """
    import time as _time

    directory = os.path.dirname(os.path.abspath(path)) or "."
    fd, tmp = tempfile.mkstemp(dir=directory, prefix=".tracker-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
        last_err = None
        for attempt in range(retries + 1):
            try:
                os.replace(tmp, path)
                return
            except PermissionError as e:
                last_err = e
                if attempt < retries:
                    _time.sleep(retry_delay)
        raise last_err
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def load_json(path: str) -> Optional[dict]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None