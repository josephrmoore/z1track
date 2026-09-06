#!/usr/bin/env python3
"""Preliminary text display for Z1TRack (pure RAM-only build).

Reads tracker_state.json (the data contract written by `python -m z1rtrack.cli`)
and renders a plain-text dashboard, refreshing whenever the file changes. This
is a *display*, deliberately kept separate from the data-producing service.

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

SWORD_NAMES = {0: "No Sword", 1: "Wood Sword", 2: "White Sword", 3: "Magical Sword"}


def render(state: dict) -> str:
    lines = []
    meta = state.get("meta", {})
    lines.append("=" * 60)
    lines.append(
        f"Z1TRack  connected={meta.get('connected')}  "
        f"playing={meta.get('playing')}  level={meta.get('level')} "
        f"room={meta.get('room')}"
    )
    for note in state.get("notes", []):
        lines.append(f"  ! {note.get('code')}: {note.get('message')}")
    lines.append("-" * 60)

    inv = state.get("inventory")
    hearts = state.get("hearts")
    tri = state.get("triforce")
    if inv is not None:
        have = [SWORD_NAMES.get(inv["sword"]["value"], "?")]
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
    secrets = state.get("secrets")
    if secrets is not None:
        lines.append(
            f"Secrets found: {secrets.get('found')}  "
            f"left behind: {secrets.get('leftBehind')}"
        )
    ekc = state.get("enemyKillCounter")
    if ekc is not None:
        lines.append(
            f"Enemies killed (no damage): {ekc.get('count')}/{ekc.get('resetAt')}"
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
