"""Builds the single output contract the display reads: tracker_state.json.

Pure RAM-only: this never opens, reads, or references the seed .nes file in
any way, by design -- that's the whole point of this build, so the community
can trust it isn't inspecting the ROM (no spoilers, no cheating potential).
Everything here is derived from a live 2KB RAM snapshot alone.

Every poll produces the complete state from the current RAM snapshot (no
event history), so a cold restart after any disconnect reproduces the exact
same JSON from the current RAM alone. The snapshot file on disk is only a
safety net for mid-run unsaved resets.

Module coverage (see project brief):
  1. Inventory                    -- fully live from RAM (incl. sword).
  2. Triforce (8 pieces)          -- fully live from RAM.
  3. Overworld Heart Containers   -- dropped (not MVP).
  4. Secrets Found / Not Taken    -- flat count only (no region breakdown --
                                     no trustworthy screen-to-region table
                                     was found; see ram.decode_secrets).
  5. Dungeon Rooms Cleared        -- dropped (not MVP; the per-dungeon ask
                                     was confirmed unbuildable from RAM
                                     alone -- a real room and a room that
                                     doesn't exist in that dungeon's shape
                                     are byte-identical in RAM).
  +. Enemy kill counter ($0050, "Nth enemy has the bomb") -- bonus, fully
     live from RAM.
"""

from __future__ import annotations

import datetime
import json
import os
import tempfile
from typing import Optional

from . import ram as ramlib

SCHEMA_VERSION = 1


def build_state(
    raw: Optional[bytes],
    now: Optional[datetime.datetime] = None,
    connected: bool = False,
    source: str = "none",
) -> dict:
    """raw: full 2KB RAM bytes (or None when no live source)."""
    now = now or datetime.datetime.now(datetime.timezone.utc)

    if raw is not None:
        snap = ramlib.decode(raw)
        playing = snap["playing"]
        game_mode = snap["gameMode"]
        level = snap["level"]
        room = snap["room"]
        inventory = snap["inventory"]
        hearts = snap["hearts"]
        triforce = snap["triforce"]
        secrets = snap["secrets"]
        enemy_kill_counter = snap["enemyKillCounter"]
    else:
        playing = False
        game_mode = None
        level = None
        room = None
        inventory = None
        hearts = None
        triforce = None
        secrets = None
        enemy_kill_counter = None

    notes = [{
        "code": "secrets_flat_no_regions",
        "message": "Secrets found/left-behind is a flat, map-wide count, "
                   "not broken down by region: no trustworthy screen-to-"
                   "region table was found (an AI-supplied one didn't match "
                   "the real source of either established community "
                   "tracker, so it wasn't used).",
    }]

    return {
        "schema": SCHEMA_VERSION,
        "updatedAt": now.isoformat(),
        "meta": {
            "source": source,
            "connected": connected,
            "playing": playing,
            "gameMode": game_mode,
            "level": level,
            "room": room,
        },
        "inventory": inventory,
        "hearts": hearts,
        "triforce": triforce,
        "secrets": secrets,
        "enemyKillCounter": enemy_kill_counter,
        "notes": notes,
    }


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
