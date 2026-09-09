#!/usr/bin/env python3
"""Z1 Click-to-Track: manual overworld coordinate logger.

Not an automatic tracker. The RAM is read once, at the moment of a click,
to answer "what overworld screen is this?" -- nothing is polled or inferred
beyond that. See zelda-click-tracker-brief.md for the full spec.

Reuses the old project's plumbing (file-based FCEUX Lua connector writing
ram.hex) and nothing else -- the rest of the old app (auto-inventory/
triforce/etc. tracking) is gone; this is a different product.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import tkinter as tk
from tkinter import messagebox

HERE = os.path.dirname(os.path.abspath(__file__))
SPR = os.path.join(HERE, "clicktracksprites")
RAM_FILE = os.path.join(HERE, "ram.hex")
ROM_INFO_FILE = os.path.join(HERE, "rom_info.json")
RAM_SIZE = 0x800
MULTI_CAP = 4

# ------------------------------------------------------------ slot definitions

LEVEL_ICONS = [
    ("L1", "01 aquamentus.png"), ("L2", "02 dodongo.png"), ("L3", "03 manhandla.png"),
    ("L4", "04 gleeok.png"), ("L5", "05 digdogger.png"), ("L6", "06 gohma.png"),
    ("L7", "07 moblin.png"), ("L8", "08 gleeok 8.png"), ("L9", "09 ganontriforce.png"),
]
SWORD_ICONS = [
    ("wood", "wood sword.png"), ("white", "white sword.png"), ("magical", "magical sword.png"),
]
STAIR_ICONS = [
    ("stair1", "1.png"), ("stair2", "2.png"), ("stair3", "3.png"), ("stair4", "4.png"),
]
MONEYHINT_ICONS = [
    ("plus", "+.png"), ("minus", "-.png"), ("plusminus", "+_-.png"), ("hint", "_.png"),
]
SHOP_ICONS = [
    ("bomb", "bomb.png"), ("bait", "meat.png"), ("ring", "bluering.png"),
    ("arrow", "arrow.png"), ("key", "key.png"), ("candle", "blue candle.png"),
    ("potion", "potion.png"),
]

CAPACITY = {}
for _id, _ in LEVEL_ICONS + SWORD_ICONS + STAIR_ICONS:
    CAPACITY[_id] = "single"
for _id, _ in MONEYHINT_ICONS + SHOP_ICONS:
    CAPACITY[_id] = "multi"

ICON_DIR = {}
for _id, _f in LEVEL_ICONS:
    ICON_DIR[_id] = os.path.join(SPR, "levels", _f)
for _id, _f in SWORD_ICONS:
    ICON_DIR[_id] = os.path.join(SPR, "swords", _f)
for _id, _f in STAIR_ICONS:
    ICON_DIR[_id] = os.path.join(SPR, "stairs", _f)
for _id, _f in MONEYHINT_ICONS:
    ICON_DIR[_id] = os.path.join(SPR, "money-hints", _f)
for _id, _f in SHOP_ICONS:
    ICON_DIR[_id] = os.path.join(SPR, "shops", _f)

MAP_DIR = os.path.join(SPR, "map")


def thumb_path(coord: str) -> str:
    return os.path.join(MAP_DIR, f"{coord}.png")


# ------------------------------------------------------------ RAM / coordinate

def _read_ram_bytes(addrs: list[int]) -> "list[int] | None":
    """Single-shot read of ram.hex; returns the byte at each requested
    address, or None if the file isn't there / isn't valid right now."""
    try:
        with open(RAM_FILE, "r", encoding="utf-8") as f:
            text = f.read().strip()
    except OSError:
        return None
    if len(text) != RAM_SIZE * 2:
        return None
    try:
        raw = bytes.fromhex(text)
    except ValueError:
        return None
    return [raw[a] for a in addrs]


def _translate(raw_byte: int) -> "str | None":
    x = raw_byte & 0x0F        # column, 0-15 -> A-P
    y = (raw_byte >> 4) & 0x0F  # row, 0-7 -> 1-8
    if y > 7:
        return None
    return chr(ord("A") + x) + str(y + 1)


def get_current_coordinate() -> "tuple[str | None, str]":
    """Returns (coordinate_or_None, status_code).

    status_code is one of: "ok", "no_ram", "invalid",
    "no_dungeon_return" (in a dungeon, but the game hasn't recorded an
    overworld return screen yet this file).
    """
    vals = _read_ram_bytes([0x10, 0xEB, 0x0526])
    if vals is None:
        return None, "no_ram"
    level, eb, ret = vals
    if level == 0:
        coord = _translate(eb)
        return (coord, "ok") if coord else (None, "invalid")
    if ret == 0xFF:
        return None, "no_dungeon_return"
    coord = _translate(ret)
    return (coord, "ok") if coord else (None, "invalid")


# ------------------------------------------------------------ persistence

def read_rom_info() -> "dict | None":
    try:
        with open(ROM_INFO_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def log_path(rom_hash: str) -> str:
    return os.path.join(HERE, f"log_{rom_hash}.json")


def load_log(rom_hash: str, filename: str) -> dict:
    try:
        with open(log_path(rom_hash), "r", encoding="utf-8") as f:
            data = json.load(f)
        data.setdefault("slots", {})
        return data
    except (OSError, ValueError):
        return {"rom_hash": rom_hash, "rom_filename_at_creation": filename, "slots": {}}


def save_log(data: dict) -> None:
    path = log_path(data["rom_hash"])
    fd, tmp = tempfile.mkstemp(dir=HERE, prefix=".clicklog-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, path)
    except OSError:
        try:
            os.unlink(tmp)
        except OSError:
            pass


def update_slot(data: dict, slot_id: str, coord: str) -> None:
    slots = data["slots"]
    if CAPACITY[slot_id] == "single":
        slots[slot_id] = [coord]
    else:
        lst = slots.setdefault(slot_id, [])
        lst.append(coord)
        if len(lst) > MULTI_CAP:
            del lst[0]


# ------------------------------------------------------------------------ UI

BG = "black"
FG = "white"


class ClickTrackerApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.icons: dict[str, tk.PhotoImage] = {}
        self.thumbs: dict[str, tk.PhotoImage] = {}
        self.canvas = tk.Canvas(root, width=1200, height=760, bg=BG, highlightthickness=0)
        self.canvas.pack()
        self.data: "dict | None" = None
        self.rom_hash: "str | None" = None
        self._status_after = None
        self._await_rom()

    # ---- identity / bootstrapping ----

    def _await_rom(self):
        info = read_rom_info()
        if info and info.get("rom_hash"):
            self.rom_hash = info["rom_hash"]
            self.data = load_log(self.rom_hash, info.get("rom_filename", ""))
            self.render()
        else:
            self.render(waiting=True)
            self.root.after(1000, self._await_rom)

    # ---- image loading (cached) ----

    def _icon(self, slot_id: str) -> "tk.PhotoImage | None":
        if slot_id not in self.icons:
            path = ICON_DIR[slot_id]
            try:
                img = tk.PhotoImage(file=path)
                if img.width() > 90:
                    factor = max(1, img.width() // 70)
                    img = img.subsample(factor, factor)
                self.icons[slot_id] = img
            except tk.TclError:
                self.icons[slot_id] = None
        return self.icons[slot_id]

    def _thumb(self, coord: str) -> "tk.PhotoImage | None":
        if coord not in self.thumbs:
            path = thumb_path(coord)
            if os.path.exists(path):
                try:
                    img = tk.PhotoImage(file=path)
                    img = img.subsample(3, 3)  # 253x177 -> ~84x59
                    self.thumbs[coord] = img
                except tk.TclError:
                    self.thumbs[coord] = None
            else:
                self.thumbs[coord] = None
        return self.thumbs[coord]

    # ---- click handling ----

    def _on_click(self, slot_id: str, _event=None):
        if self.data is None:
            return
        coord, status = get_current_coordinate()
        if coord is None:
            messages = {
                "no_ram": "Not connected to FCEUX (ram.hex not found).",
                "invalid": "Invalid position data from RAM.",
                "no_dungeon_return": "No known overworld square yet "
                                      "(haven't entered a dungeon this file).",
            }
            self._flash_status(messages.get(status, "Could not read a coordinate."))
            return
        update_slot(self.data, slot_id, coord)
        save_log(self.data)
        self.render()

    def _flash_status(self, msg: str):
        self.render()
        self.canvas.create_text(600, 745, text=msg, fill="yellow",
                                 font=("Courier", 11), tags="status")
        if self._status_after:
            self.root.after_cancel(self._status_after)
        self._status_after = self.root.after(2500, self.render)

    # ---- clear ----

    def _on_clear(self, _event=None):
        if self.data is None:
            return
        if not messagebox.askyesno(
            "Z1 Click Tracker",
            "Clear ALL tracked coordinates for this seed? This cannot be undone.",
        ):
            return
        self.data["slots"] = {}
        save_log(self.data)
        self.render()

    # ---- drawing helpers ----

    def _draw_icon_slot(self, slot_id: str, x: int, y: int, thumbs_dir: str):
        """thumbs_dir: 'right', 'below', or 'right_row' -- where coordinate
        thumbnails render relative to the icon."""
        icon = self._icon(slot_id)
        iw, ih = (icon.width(), icon.height()) if icon else (48, 48)
        if icon:
            self.canvas.create_image(x, y, image=icon, anchor="nw")
        else:
            self.canvas.create_rectangle(x, y, x + 48, y + 48, outline=FG)
            self.canvas.create_text(x + 24, y + 24, text=slot_id, fill=FG,
                                     font=("Courier", 8))

        # Clickable hit-region over the icon.
        rect = self.canvas.create_rectangle(x, y, x + iw, y + ih, outline="", fill="black")
        self.canvas.tag_bind(rect, "<Button-1>", lambda e, s=slot_id: self._on_click(s, e))
        if icon:
            self.canvas.tag_bind(rect, "<Button-1>", lambda e, s=slot_id: self._on_click(s, e))

        coords = (self.data["slots"].get(slot_id) or []) if self.data else []
        if thumbs_dir == "right":
            tx, ty = x + iw + 8, y
            for c in coords:
                self._draw_thumb(c, tx, ty)
        elif thumbs_dir == "below":
            tx, ty = x, y + ih + 4
            for c in coords:
                self._draw_thumb(c, tx, ty)
                ty += 62
        elif thumbs_dir == "right_row":
            tx, ty = x + iw + 8, y
            for c in coords:
                self._draw_thumb(c, tx, ty)
                tx += 88
        return iw, ih

    def _draw_thumb(self, coord: str, x: int, y: int):
        img = self._thumb(coord)
        if img:
            self.canvas.create_image(x, y, image=img, anchor="nw")
            self.canvas.create_text(x + img.width() // 2, y + img.height() // 2,
                                     text=coord, fill="white", font=("Courier", 12, "bold"))
        else:
            self.canvas.create_rectangle(x, y, x + 84, y + 59, outline=FG)
            self.canvas.create_text(x + 42, y + 30, text=coord, fill=FG,
                                     font=("Courier", 12, "bold"))

    # ---- full render ----

    def render(self, waiting: bool = False):
        self.canvas.delete("all")

        if waiting:
            self.canvas.create_text(
                600, 380, text="Waiting for FCEUX connector...\n"
                                "(run click_tracker.lua in FCEUX > Lua)",
                fill=FG, font=("Courier", 14), justify="center",
            )
            self.root.title("Z1 Click Tracker -- waiting")
            return

        self.root.title(f"Z1 Click Tracker -- {self.data.get('rom_filename_at_creation', '')}")

        # Divider lines matching the mockup's 3-column layout.
        self.canvas.create_line(230, 0, 230, 760, fill=FG)
        self.canvas.create_line(830, 0, 830, 760, fill=FG)
        self.canvas.create_line(230, 250, 830, 250, fill=FG)
        self.canvas.create_line(230, 500, 830, 500, fill=FG)

        # Column 1: Levels (single, icon + thumbnail to the right).
        y = 8
        for slot_id, _ in LEVEL_ICONS:
            self._draw_icon_slot(slot_id, 8, y, "right")
            y += 76

        # Column 2 top: Swords (single, icon above, thumbnail below).
        x = 250
        for slot_id, _ in SWORD_ICONS:
            self._draw_icon_slot(slot_id, x, 8, "below")
            x += 190

        # Column 2 middle: Stairs (single, icon above, thumbnail below).
        x = 250
        for slot_id, _ in STAIR_ICONS:
            self._draw_icon_slot(slot_id, x, 258, "below")
            x += 140

        # Column 2 bottom: Money/Hint (multi, icon above, thumbnails stacked below).
        x = 250
        for slot_id, _ in MONEYHINT_ICONS:
            self._draw_icon_slot(slot_id, x, 508, "below")
            x += 140

        # Column 3: Shops (multi, icon on left, thumbnails in a row to the right).
        y = 8
        for slot_id, _ in SHOP_ICONS:
            self._draw_icon_slot(slot_id, 840, y, "right_row")
            y += 100

        # Clear button -- top-right corner, away from every icon column.
        clear_rect = self.canvas.create_rectangle(1090, 6, 1192, 34, outline=FG)
        clear_txt = self.canvas.create_text(1141, 20, text="Clear Log", fill="orange",
                                             font=("Courier", 11, "bold"))
        self.canvas.tag_bind(clear_rect, "<Button-1>", self._on_clear)
        self.canvas.tag_bind(clear_txt, "<Button-1>", self._on_clear)


def main() -> int:
    root = tk.Tk()
    root.title("Z1 Click Tracker")
    ClickTrackerApp(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
