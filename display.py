#!/usr/bin/env python3
"""Z1TRack live display -- reads tracker_state.json and renders it using the
sprites/ folder, matching the community tracker layout.

Pure Python stdlib (tkinter) -- no pip install required. Designed to be run
directly: `python display.py` (or double-clicked once packaged), no CLI args
needed for normal use.

This is a *display* in the data/display split: it only ever reads the JSON
contract written by the z1rtrack service (`python -m z1rtrack.cli`). It does
not touch RAM, ROM, or the network itself.
"""
from __future__ import annotations

import json
import os
import sys
import tkinter as tk

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from z1rtrack import state as statelib  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
SPRITES = os.path.join(HERE, "sprites")
STATE_FILE = os.path.join(HERE, "tracker_state.json")
NOTES_FILE = os.path.join(HERE, "manual_notes.json")
POLL_MS = 250

BG_W, BG_H = 646, 287
PAD_RIGHT = 30  # extra canvas room so L7-9 heart/triforce icons aren't clipped

# ---------------------------------------------------------------- coordinates

# Per-level: first item-check box top-left corner, box width, and how many
# template boxes exist there (items.total for the seed may be 1 or 2 and is
# rendered dynamically; the template just needs to have enough boxes for the
# larger of 1st/2nd Quest -- see the Level 4 special case).
LEVEL_BOXES = {
    1: [(244, 18), (285, 18)],
    2: [(244, 88)],
    3: [(244, 159)],
    4: [(404, 18), (445, 18)],
    5: [(403, 88)],
    6: [(404, 159)],
    7: [(563, 19)],
    8: [(563, 88), (604, 88)],
    9: [(564, 159), (605, 159)],
}
BOX_W, BOX_H = 39, 38

# heart/triforce icon position: just right of each level's last box
LEVEL_HEART_TRIFORCE_ANCHOR = {
    1: (326, 18), 2: (285, 88), 3: (285, 159),
    4: (486, 18), 5: (444, 88), 6: (445, 159),
    7: (604, 19), 8: (645, 88), 9: (646, 159),
}

OW_SPECIAL_BOXES = {
    # key -> (icon box top-left already in bkgrnd.png, item icon goes here)
    "white_sword": (244 + BOX_W + 1, 246),
    "armos":       (404 + BOX_W + 1, 246),
    "coast":       (564 + BOX_W + 1, 246),
}

CAVE_HEART_ROW_Y = BG_H + 4  # below the whole template, in the padded area
CAVE_HEART_START_X = 13
CAVE_HEART_SPACING = 26

# Inventory: 14 boxes, top-left corners (from the black-box detection).
# NOTE: exact left-to-right/row content assignment below is a best-effort
# guess (grouped by rough category); trivial to reorder once confirmed.
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


def _owned_item_sprites(inv: dict) -> list:
    """Every individually-selectable major item the player currently owns, as
    (sprite_path, label) pairs, for the manual dungeon-box picker. Tiered
    items only offer their current tier (matching the inventory grid); this
    is a flat list of single items (not the combined bow+arrow display), one
    item per dungeon box being the whole point."""
    out = []

    def add(cond, sprite, label):
        if cond:
            out.append((sprite, label))

    add(inv["bow"]["have"], "items/bow.png", "Bow")
    if inv["arrow"]["value"] == 2:
        out.append(("items/silverarrows.png", "Silver Arrows"))
    elif inv["arrow"]["value"] == 1:
        out.append(("items/arrow.png", "Arrow"))
    if inv["candle"]["value"] == 2:
        out.append(("items/red candle.png", "Red Candle"))
    elif inv["candle"]["value"] == 1:
        out.append(("items/blue candle.png", "Blue Candle"))
    if inv["ring"]["value"] == 2:
        out.append(("items/red ring.png", "Red Ring"))
    elif inv["ring"]["value"] == 1:
        out.append(("items/bluering.png", "Blue Ring"))
    if inv["potion"]["value"] == 2:
        out.append(("items/red potion.png", "Red Potion"))
    elif inv["potion"]["value"] == 1:
        out.append(("items/blue potion.png", "Blue Potion"))
    elif inv["letter"]["have"]:
        out.append(("items/letter.png", "Letter"))
    if inv["mag_boomerang"]["have"]:
        out.append(("items/magic boomerang.png", "Magic Boomerang"))
    elif inv["boomerang"]["have"]:
        out.append(("items/boomerang.png", "Boomerang"))
    add(inv["recorder"]["have"], "items/recorder.png", "Recorder")
    add(inv["bait"]["have"], "items/meat.png", "Bait")
    add(inv["rod"]["have"], "items/wand.png", "Wand")
    add(inv["raft"]["have"], "items/raft.png", "Raft")
    add(inv["book"]["have"], "items/book.png", "Book")
    add(inv["ladder"]["have"], "items/ladder.png", "Ladder")
    add(inv["magical_key"]["have"], "items/key.png", "Magical Key")
    add(inv["bracelet"]["have"], "items/bracelet.png", "Bracelet")
    return out


class DisplayApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.icons = IconCache()
        self.canvas = tk.Canvas(
            root, width=BG_W + PAD_RIGHT, height=CAVE_HEART_ROW_Y + 30,
            bg="black", highlightthickness=0,
        )
        self.canvas.pack()
        self.bg_image = tk.PhotoImage(file=os.path.join(SPRITES, "bkgrnd.png"))
        self._last_mtime = None
        self._rom_hash = None
        # Manual click-to-cycle notes for dungeon item boxes: {"L{level}_{i}": [sprite, label]}.
        # Heart/Triforce stay automatic (both proven reliable); the item
        # boxes are user-annotated instead of auto-detected, since dungeon
        # item *identity* isn't reliably known for every flagset. Persisted
        # locally, keyed to the loaded ROM so switching seeds starts clean.
        self.manual: dict[str, list] = {}
        self._last_inventory: dict | None = None
        self.redraw(None)
        self.tick()

    def _notes_path(self) -> str:
        return NOTES_FILE

    def _load_notes(self, rom_hash: str) -> None:
        try:
            with open(self._notes_path(), "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            data = {}
        if data.get("rom_hash") == rom_hash:
            self.manual = data.get("selections", {})
        else:
            self.manual = {}
        self._rom_hash = rom_hash

    def _save_notes(self) -> None:
        try:
            with open(self._notes_path(), "w", encoding="utf-8") as f:
                json.dump({"rom_hash": self._rom_hash, "selections": self.manual}, f)
        except OSError:
            pass

    def _on_box_click(self, level: int, box_index: int, _event=None) -> None:
        key = f"L{level}_{box_index}"
        owned = _owned_item_sprites(self._last_inventory or {})
        cycle = [None] + owned  # None = empty slot, then each owned item once
        current = self.manual.get(key)  # None, or [sprite, label]

        cur_idx = -1  # not found (e.g. item no longer owned) -> restart at empty
        for i, c in enumerate(cycle):
            if c is None and current is None:
                cur_idx = i
                break
            if c is not None and current is not None and c[0] == current[0]:
                cur_idx = i
                break

        choice = cycle[(cur_idx + 1) % len(cycle)]
        if choice is None:
            self.manual.pop(key, None)
        else:
            self.manual[key] = list(choice)
        self._save_notes()
        self.redraw(statelib.load_json(STATE_FILE))

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

    def redraw(self, state: dict | None):
        self.canvas.delete("all")
        self.canvas.create_image(0, 0, image=self.bg_image, anchor="nw")

        if state is None:
            self.root.title("Z1TRack -- waiting for tracker_state.json...")
            return

        meta = state.get("meta", {})
        connected = meta.get("connected")
        self.root.title(f"Z1TRack -- {'connected' if connected else 'disconnected'}")

        rom_hash = ((meta.get("rom") or {}).get("hash"))
        if rom_hash != self._rom_hash:
            self._load_notes(rom_hash)  # fresh seed -> start manual notes clean

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
            self._last_inventory = inv
            for key, (x, y) in INV_BOXES.items():
                icons = _inv_icon_for(inv, key)
                if not icons:
                    continue
                ix = x + 2
                for icon_path in icons:
                    self._put(icon_path, ix, y + 2)
                    ix += 18  # side-by-side spacing for bow+arrow

        # Per-level: item boxes are manual click-to-cycle (dungeon item
        # *identity* isn't reliably auto-detectable for every flagset, so the
        # player records what they found instead of the tool guessing).
        # Heart/Triforce stay fully automatic -- both proven reliable.
        locs = state.get("locations", {})
        for lvl_data in locs.get("levels", []):
            level = lvl_data["level"]
            boxes = LEVEL_BOXES.get(level, [])
            for i, (bx, by) in enumerate(boxes):
                key = f"L{level}_{i}"
                # Clickable region over the box, filled to match the
                # template's black box (a fully transparent/empty-fill
                # rectangle in tkinter is only hit-testable on its outline,
                # not its interior -- must actually match the background to
                # both look right and be clickable across the whole box).
                # Recreated every redraw since canvas.delete("all") clears
                # old canvas items (and their bindings) too.
                rect = self.canvas.create_rectangle(
                    bx, by, bx + BOX_W, by + BOX_H, outline="", fill="black",
                )
                self.canvas.tag_bind(
                    rect, "<Button-1>",
                    lambda e, lv=level, ix=i: self._on_box_click(lv, ix, e),
                )
                choice = self.manual.get(key)
                if choice:
                    self._put(choice[0], bx + 11, by + 2)

            hx, hy = LEVEL_HEART_TRIFORCE_ANCHOR.get(level, (0, 0))
            heart = lvl_data.get("heart") or {}
            if heart.get("room") is not None:
                sprite = ("levelicons/level_heart_taken.png" if heart.get("taken")
                          else "levelicons/level_heart_nottaken.png")
                self._put(sprite, hx + 2, hy)
            triforce = lvl_data.get("triforce") or {}
            if triforce.get("room") is not None:
                sprite = ("levelicons/triforce_taken.png" if triforce.get("taken")
                          else "levelicons/triforce_nottaken.png")
                self._put(sprite, hx + 4, hy + 21)

        # Overworld specials
        ow = locs.get("overworld", {})
        for key, (x, y) in OW_SPECIAL_BOXES.items():
            loc = ow.get(key, {})
            if loc.get("taken") and loc.get("item"):
                item_name = loc["item"]["name"].lower().replace("_", " ")
                sprite = f"items/{item_name}.png"
                path = os.path.join(SPRITES, sprite)
                if os.path.exists(path):
                    self._put(sprite, x + 2, y + 2)

        # Overworld heart caves (count only)
        hc = locs.get("overworldHeartCaves", {})
        cleared = hc.get("cleared") or 0
        total = hc.get("total") or 5
        for i in range(total):
            sprite = ("cave hearts/caves_heart_taken.png" if i < cleared
                      else "cave hearts/caves_heart_nottaken.png")
            self._put(sprite, CAVE_HEART_START_X + i * CAVE_HEART_SPACING,
                      CAVE_HEART_ROW_Y)


def main() -> int:
    root = tk.Tk()
    root.title("Z1TRack")
    DisplayApp(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
