#!/usr/bin/env python3
"""Z1TRack live display (pure RAM-only build) -- reads tracker_state.json and
renders it using the sprites/ folder.

Pure Python stdlib (tkinter) -- no pip install required. Designed to be run
directly: `python display.py` (or double-clicked once packaged), no CLI args
needed for normal use.

This is a *display* in the data/display split: it only ever reads the JSON
contract written by the z1rtrack service (`python -m z1rtrack.cli`). It does
not touch RAM, ROM, or the network itself.

Scope: Inventory (incl. sword) and Triforce reuse the exact layout already
validated in the earlier ROM-assisted build (same sprites, same coordinates).
Sword has no sprite yet (text fallback shown below the grid) -- new layout
and sliced sprites for it are expected in a follow-up. Secrets-found and the
enemy-kill counter are new, simple text readouts below the main graphic.
"""
from __future__ import annotations

import os
import sys
import tkinter as tk

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from z1rtrack import state as statelib  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
SPRITES = os.path.join(HERE, "sprites")
STATE_FILE = os.path.join(HERE, "tracker_state.json")
POLL_MS = 250

BG_W, BG_H = 646, 287
INFO_PANEL_H = 110  # extra room below the template for text-only readouts

# ---------------------------------------------------------------- coordinates

# Inventory: 14 boxes, top-left corners (from the black-box detection on the
# original template). Unchanged from the earlier build -- already validated.
INV_BOXES = {
    "candle":       (13, 128),
    "bomb":         (54, 128),
    "bow_arrow":    (95, 128),   # two icons side by side in one box
    "boomerang":    (137, 128),
    "recorder":     (13, 168),
    "meat":         (54, 168),
    "potion":       (95, 168),
    "wand":         (137, 168),
    "raft":         (13, 207),
    "ladder":       (54, 207),
    "book":         (95, 207),
    "key":          (137, 207),
    "ring":         (54, 247),
    "bracelet":     (95, 247),
}

# Triforce triangle piece + label positions (bounding box approx (7,4)-(183,79))
TRIFORCE_POSITIONS = [
    (60, 6), (95, 6),
    (42, 28), (78, 28), (113, 28),
    (25, 50), (60, 50), (95, 50),
]

SWORD_NAMES = {0: "No Sword", 1: "Wood Sword", 2: "White Sword", 3: "Magical Sword"}


class IconCache:
    def __init__(self):
        self._cache = {}

    def get(self, rel_path: str):
        if rel_path not in self._cache:
            full = os.path.join(SPRITES, rel_path)
            self._cache[rel_path] = tk.PhotoImage(file=full)
        return self._cache[rel_path]


def _inv_icon_for(inv: dict, key: str) -> "list[str] | None":
    """Return the sprite path(s) to draw for one inventory box, honoring the
    shared-slot rules (tiered items only ever show their highest tier;
    bow/arrow share one box and can both show at once)."""
    if key == "candle":
        if inv["candle"]["value"] == 2:
            return ["items/red candle.png"]
        if inv["candle"]["value"] == 1:
            return ["items/blue candle.png"]
        return None
    if key == "boomerang":
        if inv["mag_boomerang"]["have"]:
            return ["items/magic boomerang.png"]
        if inv["boomerang"]["have"]:
            return ["items/boomerang.png"]
        return None
    if key == "ring":
        if inv["ring"]["value"] == 2:
            return ["items/red ring.png"]
        if inv["ring"]["value"] == 1:
            return ["items/bluering.png"]
        return None
    if key == "potion":
        if inv["potion"]["value"] == 2:
            return ["items/red potion.png"]
        if inv["potion"]["value"] == 1:
            return ["items/blue potion.png"]
        if inv["letter"]["have"]:
            return ["items/letter.png"]
        return None
    if key == "bow_arrow":
        icons = []
        if inv["bow"]["have"]:
            icons.append("items/bow.png")
        if inv["arrow"]["value"] == 2:
            icons.append("items/silverarrows.png")
        elif inv["arrow"]["value"] == 1:
            icons.append("items/arrow.png")
        return icons or None
    simple = {
        "bomb": ("bomb", "items/bomb.png"),
        "recorder": ("recorder", "items/recorder.png"),
        "meat": ("bait", "items/meat.png"),
        "wand": ("rod", "items/wand.png"),
        "raft": ("raft", "items/raft.png"),
        "ladder": ("ladder", "items/ladder.png"),
        "book": ("book", "items/book.png"),
        "key": ("magical_key", "items/key.png"),
        "bracelet": ("bracelet", "items/bracelet.png"),
    }
    if key in simple:
        inv_key, sprite = simple[key]
        if inv_key == "bomb":
            return [sprite] if inv["bombs"]["value"] > 0 else None
        return [sprite] if inv[inv_key]["have"] else None
    return None


class DisplayApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.icons = IconCache()
        self.canvas = tk.Canvas(
            root, width=BG_W, height=BG_H + INFO_PANEL_H,
            bg="black", highlightthickness=0,
        )
        self.canvas.pack()
        self.bg_image = tk.PhotoImage(file=os.path.join(SPRITES, "bkgrnd.png"))
        self._last_mtime = None
        self.redraw(None)
        self.tick()

    def tick(self):
        try:
            mtime = os.path.getmtime(STATE_FILE)
        except OSError:
            mtime = None
        if mtime != self._last_mtime:
            state = statelib.load_json(STATE_FILE)
            self.redraw(state)
            self._last_mtime = mtime
        self.root.after(POLL_MS, self.tick)

    def _icon(self, path):
        return self.icons.get(path)

    def _put(self, path, x, y):
        self.canvas.create_image(x, y, image=self._icon(path), anchor="nw")

    def _text(self, x, y, s, **kw):
        kw.setdefault("fill", "white")
        kw.setdefault("anchor", "nw")
        kw.setdefault("font", ("Courier", 11))
        self.canvas.create_text(x, y, text=s, **kw)

    def redraw(self, state: dict | None):
        self.canvas.delete("all")
        self.canvas.create_image(0, 0, image=self.bg_image, anchor="nw")

        if state is None:
            self.root.title("Z1TRack -- waiting for tracker_state.json...")
            return

        meta = state.get("meta", {})
        connected = meta.get("connected")
        self.root.title(f"Z1TRack -- {'connected' if connected else 'disconnected'}")

        # Triforce triangle
        tri = state.get("triforce") or {}
        pieces = tri.get("pieces") or [False] * 8
        for i, (x, y) in enumerate(TRIFORCE_POSITIONS):
            if i < len(pieces) and pieces[i]:
                self._put(f"triforce pieces/t{i + 1}.png", x, y)
            self._put(f"triforce label numbers/{i + 1}.png", x + 9, y + 6)

        # Inventory grid
        inv = state.get("inventory")
        if inv:
            for key, (x, y) in INV_BOXES.items():
                icons = _inv_icon_for(inv, key)
                if not icons:
                    continue
                ix = x + 2
                for icon_path in icons:
                    self._put(icon_path, ix, y + 2)
                    ix += 18  # side-by-side spacing for bow+arrow

        # --- Info panel (text-only readouts below the main template) -------
        panel_y = BG_H + 8

        if inv:
            sword_name = SWORD_NAMES.get(inv["sword"]["value"], "?")
            self._text(13, panel_y, f"Sword: {sword_name}  (sprite pending)")

        secrets = state.get("secrets")
        if secrets is not None:
            found = secrets.get("found", 0)
            left = secrets.get("leftBehind", 0)
            if left:
                self._text(13, panel_y + 22, f"Secrets found: {found}  ({left} left behind)")
            else:
                self._text(13, panel_y + 22, f"Secrets found: {found}")

        ekc = state.get("enemyKillCounter")
        if ekc is not None:
            self._text(13, panel_y + 44,
                       f"Enemies killed (no damage): {ekc.get('count', 0)}/{ekc.get('resetAt', 10)}")

        hearts = state.get("hearts")
        if hearts is not None:
            self._text(13, panel_y + 66,
                       f"Hearts: {hearts['filled']}+{hearts['partial']}/{hearts['max']}")


def main() -> int:
    root = tk.Tk()
    root.title("Z1TRack")
    DisplayApp(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
