#!/usr/bin/env python3
"""Z1 Click-to-Track: manual overworld coordinate logger.

Not an automatic tracker. The RAM is read once, at the moment of a click,
to answer "what overworld screen is this?" -- nothing is polled or inferred
beyond that. See zelda-click-tracker-brief.md (Rev 3) and
zelda-click-tracker-brief-addendum-rev4.md for the full spec.

Rev 4: the dynamic, self-sizing chrome layout (icons/dividers computed from
LAYOUT + asset dimensions) was retired in favor of one static background
image -- see the addendum, Section 3.

v2: hardcoded pixel offsets for every clickable/display region were
themselves retired in favor of a hand-painted color-key overlay image
(clicktracksprites/v2/overlaypositions.png) -- see regionmap.py for the
color key and detection logic. Regions are re-detected fresh every launch
(confirmed fast enough, no caching needed), so resizing the background+
overlay pair in an image editor and dropping in the new files "just works"
with no coordinates to hand-recompute anywhere.

Everything still interactive (the 27 coordinate-logging slots, the
per-level Heart/Triforce/Item toggles, the quest switcher, Clear) is
hit-tested via a flat list of pixel regions (CLICK_REGIONS, rebuilt on
every render) rather than per-item Tk bindings -- a plain rectangle can't
be both invisible *and* hit-testable in its interior against an arbitrary
image background, so region checking is done in Python instead of relying
on Tk's per-item event dispatch.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import tkinter as tk
from tkinter import messagebox

import regionmap

HERE = os.path.dirname(os.path.abspath(__file__))
SPR = os.path.join(HERE, "clicktracksprites")
V2 = os.path.join(SPR, "v2")
ICONS = os.path.join(SPR, "icons")
MAP_DIR = os.path.join(SPR, "map")
BACKGROUND_PATH = os.path.join(V2, "background.png")
OVERLAY_PATH = os.path.join(V2, "overlaypositions.png")
CLICK_OVERLAY_PATH = os.path.join(V2, "clickoverlay.png")
RAM_FILE = os.path.join(HERE, "ram.hex")
ROM_INFO_FILE = os.path.join(HERE, "rom_info.json")
RAM_SIZE = 0x800
MULTI_CAP = 4
STALE_SECONDS = 2.0
LEVEL_IDS = [f"L{i}" for i in range(1, 10)]
LEVELS_WITH_HEART_TRIFORCE = set(f"L{i}" for i in range(1, 9))  # L9 has neither

# ---------------------------------------------------------------- content
# What exists: sections, their slots, and single/multi capacity. Independent
# of layout -- these are the 27 RAM-coordinate-logging slots from Rev 3,
# unchanged in meaning; only their on-screen positions moved to the new
# static background (see ANCHORS below).

SECTIONS = {
    "levels": {
        "capacity": "single",
        "slots": ["L1", "L2", "L3", "L4", "L5", "L6", "L7", "L8", "L9"],
    },
    "swords": {
        "capacity": "single",
        "slots": ["wood", "white", "magical"],
    },
    "stairs": {
        "capacity": "single",
        "slots": ["stair1", "stair2", "stair3", "stair4"],
    },
    "shops": {
        # Order matches the background image's column top-to-bottom.
        "capacity": "multi",
        "slots": ["key", "bomb", "ring", "candle", "arrow", "bait", "potion"],
    },
    "money_hint": {
        "capacity": "multi",
        "slots": ["plus", "minus", "plusminus", "hint"],
    },
}

CAPACITY: dict[str, str] = {}
for _section in SECTIONS.values():
    for _slot_id in _section["slots"]:
        CAPACITY[_slot_id] = _section["capacity"]


def thumb_path(coord: str) -> str:
    return os.path.join(MAP_DIR, f"{coord}.png")


# ----------------------------------------------------------------- layout
# Every clickable/display position comes from regionmap.detect() reading
# clicktracksprites/v2/overlaypositions.png -- see regionmap.py for the
# color key. Nothing here is a hardcoded pixel number; it's all derived
# from that image, fresh, every launch. See _build_layout() below for how
# raw color blobs get matched to specific slot/level IDs.

_COL2_SLOTS = SECTIONS["swords"]["slots"] + SECTIONS["stairs"]["slots"]
_COL3_SLOTS = SECTIONS["shops"]["slots"] + SECTIONS["money_hint"]["slots"]

# Levels needing an item-toggle position "1" (single item, in *some* quest)
# vs. "2a"/"2b" (two items, in *some* quest) -- a level can need either, or
# (L1, L4) both, depending on which quest is active. Independent of
# Heart/Triforce, which exist for L1-L8 always and never for L9.
ITEM_POS1_LEVELS = ["L1", "L2", "L3", "L4", "L5", "L6", "L7"]
ITEM_POS2_LEVELS = ["L1", "L4", "L8", "L9"]


def _build_layout(overlay_path: str, click_overlay_path: str) -> dict:
    raw = regionmap.detect(overlay_path)

    # Icon-clickable areas (lilac, addendum "the green map icons should be
    # right-clickable" -- i.e. logging a coordinate isn't limited to
    # clicking near the thumbnail position, the enemy/sword/shop icon
    # itself is clickable too) live in a separate overlay file, one lilac
    # box per slot (unlike green's 4-per-slot for multi-capacity slots --
    # there's still only one icon to click, regardless of how many
    # coordinates are currently logged there).
    click_raw = regionmap.detect(click_overlay_path)
    lilac_cols = regionmap.cluster_by_x(click_raw["lilac"])
    lilac_levels = next(c for c in lilac_cols if len(c) == len(SECTIONS["levels"]["slots"]))
    lilac_col2 = next(c for c in lilac_cols if len(c) == len(_COL2_SLOTS))
    lilac_col3 = next(c for c in lilac_cols if len(c) == len(_COL3_SLOTS))
    icon_click_box = dict(zip(SECTIONS["levels"]["slots"], lilac_levels))
    icon_click_box.update(zip(_COL2_SLOTS, lilac_col2))
    icon_click_box.update(zip(_COL3_SLOTS, lilac_col3))

    green_cols = regionmap.cluster_by_x(raw["green"])
    levels_col = next(c for c in green_cols if len(c) == len(SECTIONS["levels"]["slots"]))
    col2_col = next(c for c in green_cols if len(c) == len(_COL2_SLOTS))
    col3_subcols = sorted(
        (c for c in green_cols if len(c) == len(_COL3_SLOTS)),
        key=lambda c: c[0][0],
    )
    if len(col3_subcols) != 4:
        raise ValueError(
            f"expected 4 green sub-columns of {len(_COL3_SLOTS)} boxes each for "
            f"shops/money-hint (one per multi-slot thumbnail position), found "
            f"{len(col3_subcols)} -- check overlaypositions.png's green boxes.")

    coord_box = dict(zip(SECTIONS["levels"]["slots"], levels_col))
    coord_box.update(zip(_COL2_SLOTS, col2_col))
    multi_coord_boxes = {
        slot_id: [col3_subcols[c][row] for c in range(4)]
        for row, slot_id in enumerate(_COL3_SLOTS)
    }

    heart_levels = [f"L{i}" for i in range(1, 9)]
    heart_box = dict(zip(heart_levels, raw["red"]))
    triforce_box = dict(zip(heart_levels, raw["yellow"]))
    item_pos1_box = dict(zip(ITEM_POS1_LEVELS, raw["pink"]))
    item_pos2a_box = dict(zip(ITEM_POS2_LEVELS, raw["blue"]))
    item_pos2b_box = dict(zip(ITEM_POS2_LEVELS, raw["purple"]))

    quest_sorted = sorted(raw["orange"], key=lambda b: b[0])  # left-to-right
    quest_box = {1: quest_sorted[0], 2: quest_sorted[1]}
    clear_box = raw["cyan"][0]

    return {
        "coord_box": coord_box,
        "multi_coord_boxes": multi_coord_boxes,
        "icon_click_box": icon_click_box,
        "heart_box": heart_box,
        "triforce_box": triforce_box,
        "item_pos1_box": item_pos1_box,
        "item_pos2a_box": item_pos2a_box,
        "item_pos2b_box": item_pos2b_box,
        "quest_box": quest_box,
        "clear_box": clear_box,
    }


LAYOUT: dict = {}  # populated by ClickTrackerApp.__init__ -- PhotoImage (used
# inside _build_layout/regionmap.detect) needs a Tk root to already exist,
# which isn't true yet at module-import time.

# Per-level, per-quest major-item locations ("floor" or "stairs" -- i.e. a
# secret room reached via a staircase). Independent of Heart/Triforce,
# which always exist as a separate pair of toggles for L1-L8 and never for
# L9. One or two entries per level; two means two separate item toggles.
QUEST_ITEMS = {
    1: {
        "L1": ["floor", "stairs"], "L2": ["floor"], "L3": ["stairs"],
        "L4": ["stairs"], "L5": ["stairs"], "L6": ["stairs"], "L7": ["stairs"],
        "L8": ["stairs", "stairs"], "L9": ["stairs", "stairs"],
    },
    2: {
        "L1": ["floor"], "L2": ["stairs"], "L3": ["floor"],
        "L4": ["stairs", "stairs"], "L5": ["stairs"], "L6": ["stairs"], "L7": ["stairs"],
        "L8": ["stairs", "stairs"], "L9": ["stairs", "stairs"],
    },
}


# ------------------------------------------------------------ RAM / coordinate

def _read_ram_bytes(addrs: list[int]) -> "list[int] | None":
    """Single-shot read of ram.hex; returns the byte at each requested
    address, or None if the file isn't there / isn't valid right now."""
    try:
        with open(RAM_FILE, "rb") as f:
            raw = f.read()
    except OSError:
        return None
    if len(raw) != RAM_SIZE:
        return None
    return [raw[a] for a in addrs]


def _translate(raw_byte: int) -> "str | None":
    x = raw_byte & 0x0F         # column, 0-15 -> A-P
    y = (raw_byte >> 4) & 0x0F  # row, 0-7 -> 1-8
    if y > 7:
        return None
    return chr(ord("A") + x) + str(y + 1)


STATUS_MESSAGES = {
    "no_ram": "Not connected to FCEUX (ram.hex not found).",
    "stale": "Not connected -- ram.hex hasn't updated recently "
             "(is the Lua connector running, in the right folder?).",
    "invalid": "Invalid position data from RAM.",
    "no_dungeon_return": "No known overworld square yet "
                          "(haven't entered a dungeon this file).",
}


def ram_file_age() -> "float | None":
    try:
        return time.time() - os.path.getmtime(RAM_FILE)
    except OSError:
        return None


def get_current_coordinate() -> "tuple[str | None, str, dict]":
    """Returns (coordinate_or_None, status_code, debug_info). See
    STATUS_MESSAGES for status_code meanings."""
    age = ram_file_age()
    if age is None:
        return None, "no_ram", {"age": age}
    if age > STALE_SECONDS:
        return None, "stale", {"age": age}
    vals = _read_ram_bytes([0x10, 0xEB, 0x0526])
    if vals is None:
        return None, "no_ram", {"age": age}
    level, eb, ret = vals
    debug = {"age": age, "level": level, "eb": eb, "ret": ret}
    if level == 0:
        coord = _translate(eb)
        return (coord, "ok", debug) if coord else (None, "invalid", debug)
    if ret == 0xFF:
        return None, "no_dungeon_return", debug
    coord = _translate(ret)
    return (coord, "ok", debug) if coord else (None, "invalid", debug)


# ------------------------------------------------------------ persistence

def read_rom_info() -> "dict | None":
    try:
        with open(ROM_INFO_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def log_path(rom_hash: str) -> str:
    return os.path.join(HERE, f"log_{rom_hash}.json")


def _fresh_item_toggles() -> dict:
    return {lv: {"heart": False, "triforce": False, "items": [False, False]}
            for lv in LEVEL_IDS}


def new_log(rom_hash: str, filename: str) -> dict:
    return {
        "rom_hash": rom_hash,
        "rom_filename_at_creation": filename,
        "active_quest": 1,
        "item_toggles": _fresh_item_toggles(),
        "slots": {},
    }


def load_log(rom_hash: str, filename: str) -> dict:
    try:
        with open(log_path(rom_hash), "r", encoding="utf-8") as f:
            data = json.load(f)
        data.setdefault("slots", {})
        data.setdefault("active_quest", 1)
        data.setdefault("item_toggles", _fresh_item_toggles())
        for lv in LEVEL_IDS:
            data["item_toggles"].setdefault(
                lv, {"heart": False, "triforce": False, "items": [False, False]})
        return data
    except (OSError, ValueError):
        return new_log(rom_hash, filename)


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


def toggle_heart_or_triforce(data: dict, level: str, role: str) -> None:
    t = data["item_toggles"][level]
    t[role] = not t[role]


def toggle_item(data: dict, level: str, index: int) -> None:
    t = data["item_toggles"][level]
    t["items"][index] = not t["items"][index]


def remove_slot_entry(data: dict, slot_id: str, index: int) -> None:
    """Deletes one logged coordinate (right-click-to-fix-a-misclick).
    Works uniformly for single- and multi-capacity slots since a
    single-capacity slot's list only ever has one entry, at index 0."""
    lst = data["slots"].get(slot_id)
    if lst and 0 <= index < len(lst):
        del lst[index]


# ------------------------------------------------------------------------ UI

class ClickTrackerApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.images: dict[str, "tk.PhotoImage | None"] = {}
        self.thumbs: dict[str, "tk.PhotoImage | None"] = {}
        global LAYOUT
        if not LAYOUT:
            LAYOUT = _build_layout(OVERLAY_PATH, CLICK_OVERLAY_PATH)
        self.bg_image = tk.PhotoImage(file=BACKGROUND_PATH)
        self.bg_size = (self.bg_image.width(), self.bg_image.height())
        cw, ch = self.bg_size
        self.canvas = tk.Canvas(root, width=cw, height=ch, bg="black", highlightthickness=0)
        self.canvas.pack()
        self.data: "dict | None" = None
        self.rom_hash: "str | None" = None
        self._status_after = None
        self._last_debug: "dict | None" = None
        self._click_regions: "list[tuple]" = []  # (x1, y1, x2, y2, handler)
        self._delete_regions: "list[tuple]" = []  # same shape, right-click only
        self.canvas.bind("<Button-1>", self._on_canvas_click)
        # Right-click-to-delete a logged coordinate. Bind both Button-2 and
        # Button-3: the "right click" physical button is Button-3 on
        # Windows/Linux and (usually) macOS with a real two-button mouse or
        # trackpad two-finger tap, but Button-2 on some older/alternate
        # macOS mouse configurations -- binding both costs nothing and
        # avoids a platform-specific dead end for this one feature.
        self.canvas.bind("<Button-2>", self._on_canvas_right_click)
        self.canvas.bind("<Button-3>", self._on_canvas_right_click)
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

    def _img(self, rel_path: str) -> "tk.PhotoImage | None":
        if rel_path not in self.images:
            try:
                self.images[rel_path] = tk.PhotoImage(file=os.path.join(ICONS, rel_path))
            except tk.TclError:
                self.images[rel_path] = None
        return self.images[rel_path]

    def _thumb(self, coord: str) -> "tk.PhotoImage | None":
        if coord not in self.thumbs:
            path = thumb_path(coord)
            if os.path.exists(path):
                try:
                    # map/*.png are 253x177 native -- subsample(3,3) -> ~84x59,
                    # a close match to the overlay's green box size (~79x58).
                    self.thumbs[coord] = tk.PhotoImage(file=path).subsample(3, 3)
                except tk.TclError:
                    self.thumbs[coord] = None
            else:
                self.thumbs[coord] = None
        return self.thumbs[coord]

    # ---- region-based click dispatch ----
    # A Tk canvas item can't be both invisible *and* hit-testable across its
    # full interior against an arbitrary image background (only a matching
    # solid fill achieves that, which isn't possible over photo content) --
    # so clickable areas are tracked as plain (x1,y1,x2,y2,handler) tuples
    # and checked directly against the click point instead of relying on
    # per-item Tk bindings.

    def _add_region(self, x1, y1, x2, y2, handler):
        self._click_regions.append((x1, y1, x2, y2, handler))

    def _add_delete_region(self, x1, y1, x2, y2, handler):
        self._delete_regions.append((x1, y1, x2, y2, handler))

    def _on_canvas_click(self, event):
        for x1, y1, x2, y2, handler in reversed(self._click_regions):
            if x1 <= event.x <= x2 and y1 <= event.y <= y2:
                handler()
                return

    def _on_canvas_right_click(self, event):
        for x1, y1, x2, y2, handler in reversed(self._delete_regions):
            if x1 <= event.x <= x2 and y1 <= event.y <= y2:
                handler()
                return

    # ---- click handlers ----

    def _on_slot_click(self, slot_id: str):
        if self.data is None:
            return
        coord, status, debug = get_current_coordinate()
        self._last_debug = debug
        if coord is None:
            self._flash_status(STATUS_MESSAGES.get(status, "Could not read a coordinate."))
            return
        update_slot(self.data, slot_id, coord)
        save_log(self.data)
        self.render()

    def _on_heart_triforce_click(self, level: str, role: str):
        if self.data is None:
            return
        toggle_heart_or_triforce(self.data, level, role)
        save_log(self.data)
        self.render()

    def _on_item_click(self, level: str, index: int):
        if self.data is None:
            return
        toggle_item(self.data, level, index)
        save_log(self.data)
        self.render()

    def _on_quest_click(self, quest: int):
        if self.data is None:
            return
        self.data["active_quest"] = quest
        save_log(self.data)
        self.render()

    def _on_delete_entry(self, slot_id: str, index: int):
        """Right-click on a logged coordinate's thumbnail -- fixes a
        misclick without the confirmation dialog Clear needs, since this
        only ever removes the one entry clicked, not everything."""
        if self.data is None:
            return
        remove_slot_entry(self.data, slot_id, index)
        save_log(self.data)
        self.render()

    def _flash_status(self, msg: str):
        self.render()
        self.canvas.create_text(self.bg_size[0] // 2, self.bg_size[1] - 40, text=msg,
                                 fill="yellow", font=("Courier", 16), tags="status")
        if self._status_after:
            self.root.after_cancel(self._status_after)
        self._status_after = self.root.after(2500, self.render)

    def _on_clear(self):
        if self.data is None:
            return
        if not messagebox.askyesno(
            "Z1 Click Tracker",
            "Clear ALL tracked coordinates and item/heart/triforce progress "
            "for this seed? This cannot be undone. (The quest selection is "
            "kept -- it's a property of the seed, not logged progress.)",
        ):
            return
        self.data["slots"] = {}
        self.data["item_toggles"] = _fresh_item_toggles()
        save_log(self.data)
        self.render()

    # ---- drawing helpers ----

    def _put(self, img: "tk.PhotoImage | None", x: int, y: int):
        if img:
            self.canvas.create_image(x, y, image=img, anchor="nw")

    def _draw_thumb(self, coord: str, x: int, y: int, fallback_size: "tuple[int, int]"):
        """Unchanged from Rev 3 except the on-image label is now white text
        with a black outline (addendum Section 4) instead of a solid fill,
        for readability against the map art."""
        img = self._thumb(coord)
        if img:
            self.canvas.create_image(x, y, image=img, anchor="nw")
            cx, cy = x + img.width() // 2, y + img.height() // 2
            for dx, dy in ((-1, -1), (-1, 0), (-1, 1), (0, -1),
                           (0, 1), (1, -1), (1, 0), (1, 1)):
                self.canvas.create_text(cx + dx, cy + dy, text=coord, fill="black",
                                         font=("Courier", 12, "bold"))
            self.canvas.create_text(cx, cy, text=coord, fill="white",
                                     font=("Courier", 12, "bold"))
        else:
            # Section 5's required fallback: no image asset -> plain text,
            # never a blank gap. (Not on-image, so no outline needed here.)
            fw, fh = fallback_size
            self.canvas.create_rectangle(x, y, x + fw, y + fh, outline="white")
            self.canvas.create_text(x + fw // 2, y + fh // 2, text=coord,
                                     fill="white", font=("Courier", 12, "bold"))

    def _draw_icon_at_box(self, box, on_img_name, off_img_name, on: bool, handler):
        """Draws a toggle/button icon anchored at box's top-left corner,
        using the icon's own rendered size (not the overlay box's size,
        which only marks the anchor point -- these small icons/buttons are
        painted much larger than their color-key marker box) for the
        click region."""
        x1, y1 = box[0], box[1]
        img = self._img(on_img_name if on else off_img_name)
        self._put(img, x1, y1)
        w = img.width() if img else (box[2] - box[0])
        h = img.height() if img else (box[3] - box[1])
        self._add_region(x1, y1, x1 + w, y1 + h, handler)

    def _draw_coord_slot(self, slot_id: str):
        box = LAYOUT["coord_box"].get(slot_id)
        coords = (self.data["slots"].get(slot_id) or []) if self.data else []

        # The icon itself (lilac overlay) is also clickable to log a new
        # coordinate, in addition to the thumbnail-position box(es) below --
        # same handler either way, just a second way to trigger it.
        icon_box = LAYOUT["icon_click_box"].get(slot_id)
        if icon_box is not None:
            ix1, iy1, ix2, iy2 = icon_box
            self._add_region(ix1, iy1, ix2, iy2, lambda s=slot_id: self._on_slot_click(s))

        if box is not None:
            # Single-capacity slot (levels, swords, stairs): one box, one
            # coordinate at a time.
            x1, y1, x2, y2 = box
            self._add_region(x1, y1, x2, y2, lambda s=slot_id: self._on_slot_click(s))
            if coords:
                self._draw_thumb(coords[0], x1, y1, (x2 - x1, y2 - y1))
                self._add_delete_region(x1, y1, x2, y2,
                                         lambda s=slot_id: self._on_delete_entry(s, 0))
            return

        # Multi-capacity slot (shops, money_hint): 4 fixed boxes, one per
        # possible FIFO position. Any of the 4 logs a new coordinate the
        # same way; which specific one is clicked doesn't matter -- only
        # which coordinates currently exist determines what's shown where.
        boxes = LAYOUT["multi_coord_boxes"][slot_id]
        for box in boxes:
            x1, y1, x2, y2 = box
            self._add_region(x1, y1, x2, y2, lambda s=slot_id: self._on_slot_click(s))
        for i, coord in enumerate(coords):
            x1, y1, x2, y2 = boxes[i]
            self._draw_thumb(coord, x1, y1, (x2 - x1, y2 - y1))
            self._add_delete_region(x1, y1, x2, y2,
                                     lambda s=slot_id, idx=i: self._on_delete_entry(s, idx))

    def _draw_level_toggles(self, level: str):
        toggles = self.data["item_toggles"][level]
        quest = self.data["active_quest"]

        if level in LEVELS_WITH_HEART_TRIFORCE:
            self._draw_icon_at_box(
                LAYOUT["heart_box"][level], "heartON.png", "heartOFF.png",
                toggles["heart"], lambda lv=level: self._on_heart_triforce_click(lv, "heart"))
            self._draw_icon_at_box(
                LAYOUT["triforce_box"][level], "triforceON.png", "triforceOFF.png",
                toggles["triforce"],
                lambda lv=level: self._on_heart_triforce_click(lv, "triforce"))

        items = QUEST_ITEMS[quest][level]
        if len(items) == 1:
            boxes = [LAYOUT["item_pos1_box"][level]]
        else:
            boxes = [LAYOUT["item_pos2a_box"][level], LAYOUT["item_pos2b_box"][level]]
        for i, (role, box) in enumerate(zip(items, boxes)):
            letter = "F" if role == "floor" else "S"
            self._draw_icon_at_box(
                box, f"{letter} on.png", f"{letter} off.png", toggles["items"][i],
                lambda lv=level, idx=i: self._on_item_click(lv, idx))

    def _draw_quest_switcher(self):
        quest = self.data["active_quest"]
        self._draw_icon_at_box(LAYOUT["quest_box"][1], "1 on.png", "1 off.png",
                                quest == 1, lambda: self._on_quest_click(1))
        self._draw_icon_at_box(LAYOUT["quest_box"][2], "2 on.png", "2 off.png",
                                quest == 2, lambda: self._on_quest_click(2))

    def _draw_clear_button(self):
        x1, y1 = LAYOUT["clear_box"][0], LAYOUT["clear_box"][1]
        img = self._img("clear button.png")
        self._put(img, x1, y1)
        w = img.width() if img else (LAYOUT["clear_box"][2] - x1)
        h = img.height() if img else (LAYOUT["clear_box"][3] - y1)
        self._add_region(x1, y1, x1 + w, y1 + h, self._on_clear)

    # ---- full render ----

    def render(self, waiting: bool = False):
        self.canvas.delete("all")
        self._click_regions = []
        self._delete_regions = []

        if waiting:
            self.canvas.create_text(
                self.bg_size[0] // 2, self.bg_size[1] // 2,
                text="Waiting for FCEUX connector...\n"
                     "(run click_tracker.lua in FCEUX > Lua)",
                fill="white", font=("Courier", 20), justify="center",
            )
            self.root.title("Z1 Click Tracker -- waiting")
            return

        self.root.title(f"Z1 Click Tracker -- {self.data.get('rom_filename_at_creation', '')}")
        self.canvas.create_image(0, 0, image=self.bg_image, anchor="nw")

        for section in SECTIONS.values():
            for slot_id in section["slots"]:
                self._draw_coord_slot(slot_id)

        for level in LEVEL_IDS:
            self._draw_level_toggles(level)

        self._draw_quest_switcher()
        self._draw_clear_button()
        self._draw_debug_line()

    def _draw_debug_line(self):
        d = self._last_debug
        if d is None:
            text = "debug: click any icon to sample RAM"
        else:
            age = d.get("age")
            age_s = f"{age:.1f}s ago" if age is not None else "no file"
            if "level" in d:
                text = (f"debug: ram.hex written {age_s} | "
                        f"level=0x{d['level']:02X} EB=0x{d['eb']:02X} "
                        f"ret($0526)=0x{d['ret']:02X}")
            else:
                text = f"debug: ram.hex written {age_s} (no valid data)"
        self.canvas.create_text(16, self.bg_size[1] - 16, text=text,
                                 fill="gray60", font=("Courier", 10), anchor="w")


def main() -> int:
    root = tk.Tk()
    root.title("Z1 Click Tracker")
    ClickTrackerApp(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())