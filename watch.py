#!/usr/bin/env python3
"""Preliminary text display for Z1TRack.

Reads tracker_state.json (the data contract written by `python -m z1rtrack.cli`)
and renders a plain-text dashboard, refreshing whenever the file changes. This
is a *display*, deliberately kept separate from the data-producing service --
it only reads the JSON contract, the same way any future GUI/OBS overlay would.

Scope note (v0): per-level "extra item" slot identities are hidden. Their room
addresses are known to be wrong (validated against real seed logs) and showing
them during actual play would be actively misleading. Boss/Triforce/Map/
Compass/Heart status per level are shown because those *are* validated, as
long as the seed does not have "Shuffle Dungeon Drops" enabled (in which case
those four can relocate to rooms this build doesn't know about yet).

Usage:
    python3 watch.py [--file tracker_state.json] [--interval 0.5]
"""
from __future__ import annotations

import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from z1rtrack import state as statelib  # noqa: E402


def _mark(v) -> str:
    if v is True:
        return "X"
    if v is False:
        return "."
    return "?"


def render(state: dict) -> str:
    lines = []
    meta = state.get("meta", {})
    lines.append("=" * 60)
    lines.append(
        f"Z1TRack  connected={meta.get('connected')}  "
        f"playing={meta.get('playing')}  level={meta.get('level')} "
        f"room={meta.get('room')}"
    )
    rom = meta.get("rom") or {}
    lines.append(
        f"ROM loaded={rom.get('loaded')}  z1rLikely={rom.get('z1rLikely')}  "
        f"quest=E{(rom.get('quest') or {}).get('early')}/"
        f"L{(rom.get('quest') or {}).get('late')}"
    )
    for note in state.get("notes", []):
        lines.append(f"  ! {note.get('code')}: {note.get('message')}")
    lines.append("-" * 60)

    inv = state.get("inventory")
    hearts = state.get("hearts")
    tri = state.get("triforce")
    if inv is not None:
        have = []
        if inv["sword"]["name"]:
            have.append(inv["sword"]["name"])
        for key in ("bow", "recorder", "bait", "rod", "raft", "book", "ladder",
                    "magical_key", "bracelet", "letter", "boomerang",
                    "mag_boomerang", "mag_shield", "clock"):
            if inv.get(key, {}).get("have"):
                have.append(key)
        if inv["arrow"]["name"]:
            have.append(inv["arrow"]["name"])
        if inv["candle"]["name"]:
            have.append(inv["candle"]["name"])
        if inv["ring"]["name"]:
            have.append(inv["ring"]["name"])
        if inv["potion"]["name"]:
            have.append(inv["potion"]["name"])
        lines.append("Items: " + (", ".join(have) if have else "(none)"))
        lines.append(
            f"Bombs={inv['bombs']['value']}  Rupees={inv['rupees']['value']}  "
            f"Keys={inv['keys']['value']}"
        )
    if hearts is not None:
        lines.append(
            f"Hearts: {hearts['filled']}+{hearts['partial']}/{hearts['max']}"
        )
    if tri is not None:
        lines.append(f"Triforce pieces: {tri['count']}/8")

    lines.append("-" * 60)
    locs = state.get("locations", {})
    ow = locs.get("overworld", {})
    for key in ("white_sword", "armos", "coast"):
        loc = ow.get(key, {})
        item = (loc.get("item") or {}).get("name", "?")
        lines.append(f"{loc.get('label', key):20s} [{_mark(loc.get('taken'))}] {item}")
    hc = locs.get("overworldHeartCaves", {})
    lines.append(f"OW Heart Caves cleared: {hc.get('cleared')}/{hc.get('total')}")

    lines.append("-" * 60)
    lines.append("Lvl  Triforce  Heart   Items (major)")
    for lvl in locs.get("levels", []):
        t = lvl.get("triforce", {}).get("taken")
        h = lvl.get("heart", {}).get("taken")
        items = lvl.get("items", {})
        total, taken = items.get("total"), items.get("taken")
        if total is None:
            items_str = "?"
        elif total == 0:
            items_str = "(none)"
        else:
            items_str = f"{taken}/{total}" + ("  ALL CLEAR" if taken == total else "")
        lines.append(
            f" {lvl['level']:<3}  [{_mark(t)}]      [{_mark(h)}]    {items_str}"
        )
    lines.append("=" * 60)
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", default="tracker_state.json")
    parser.add_argument("--interval", type=float, default=0.5)
    parser.add_argument("--once", action="store_true", help="render once and exit")
    args = parser.parse_args()

    last_mtime = None
    while True:
        try:
            mtime = os.path.getmtime(args.file)
        except OSError:
            mtime = None
        if mtime != last_mtime:
            state = statelib.load_json(args.file)
            if state is not None:
                os.system("clear" if os.name != "nt" else "cls")
                print(render(state))
            last_mtime = mtime
        if args.once:
            return 0
        time.sleep(args.interval)


if __name__ == "__main__":
    sys.exit(main())
