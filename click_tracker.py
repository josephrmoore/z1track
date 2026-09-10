#!/usr/bin/env python3
"""Z1 Click-to-Track: manual overworld coordinate logger.

Not an automatic tracker. The RAM is read once, at the moment of a click,
to answer "what overworld screen is this?" -- nothing is polled or inferred
beyond that. See zelda-click-tracker-brief.md (Rev 3) and
zelda-click-tracker-brief-addendum-rev4.md for the full spec.

Rev 4: the dynamic, self-sizing chrome layout (icons/dividers computed from
LAYOUT + asset dimensions) has been retired in favor of one static
background image (clicktracksprites/background.png) -- see the addendum,
Section 3. Everything still interactive (the 27 coordinate-logging slots,
the new per-level Heart/Triforce/Item toggles, the quest switcher, Clear)
is drawn on top of it and hit-tested via a flat list of pixel regions
(CLICK_REGIONS, rebuilt on every render) rather than per-item Tk bindings --
a plain rectangle can't be both invisible *and* hit-testable in its
interior against an arbitrary image background, so region checking is done
in Python instead of relying on Tk's per-item event dispatch.
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
ICONS = os.path.join(SPR, "icons")
MAP_DIR = os.path.join(SPR, "map")
RAM_FILE = os.path.join(HERE, "ram.hex")
ROM_INFO_FILE = os.path.join(HERE, "rom_info.json")
RAM_SIZE = 0x800
MULTI_CAP = 4
STALE_SECONDS = 2.0
THUMB_SIZE = (84, 59)  # map/*.png (253x177 native) subsampled by 3
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
# Addendum Rev 4, Section 8: every anchor/offset below is given relative to
# the *same* per-row "map image placement" point -- the spot where a
# logged coordinate's thumbnail renders. The clickable hit-region for
# logging a coordinate sits to that anchor's left (over the static icon
# baked into the background); Heart/Triforce/Item toggles sit further left
# still, at their own fixed offsets. None of this is guessed from the
# mockup screenshots -- it's the literal pixel data supplied for the
# delivered background.png.

BG_SIZE = (3840, 2160)

LEVEL_ANCHORS = {
    "L1": (500, 85), "L2": (500, 320), "L3": (500, 550), "L4": (500, 780),
    "L5": (500, 1000), "L6": (500, 1235), "L7": (500, 1460), "L8": (500, 1690),
    "L9": (500, 1920),
}
_COL2_POINTS = [(1100, 85), (1100, 320), (1100, 550), (1100, 780),
                 (1100, 1000), (1100, 1235), (1100, 1460)]
_COL2_SLOTS = SECTIONS["swords"]["slots"] + SECTIONS["stairs"]["slots"]
COL2_ANCHORS = dict(zip(_COL2_SLOTS, _COL2_POINTS))

_COL3_POINTS = [(1660, 80), (1660, 270), (1660, 460), (1660, 650), (1660, 830),
                 (1660, 1020), (1660, 1205), (1660, 1390), (1660, 1580),
                 (1660, 1765), (1660, 1950)]
_COL3_SLOTS = SECTIONS["shops"]["slots"] + SECTIONS["money_hint"]["slots"]
COL3_ANCHORS = dict(zip(_COL3_SLOTS, _COL3_POINTS))

ANCHORS: dict[str, "tuple[int, int]"] = {**LEVEL_ANCHORS, **COL2_ANCHORS, **COL3_ANCHORS}

# Clickable coordinate-logging region = anchor + offset, sized (w, h),
# category by section (levels vs. col2 vs. col3 all use different offsets).
_CLICK_RULE = {
    "levels": {"offset": (-430, -20), "size": (335, 195)},
    "swords": {"offset": (-240, -15), "size": (165, 195)},
    "stairs": {"offset": (-240, -15), "size": (165, 195)},
    "shops": {"offset": (-230, -15), "size": (190, 160)},
    "money_hint": {"offset": (-230, -15), "size": (190, 160)},
}

# Heart/Triforce/Item-toggle offsets, relative to a level's own anchor
# point (LEVEL_ANCHORS) -- fixed regardless of quest (addendum 3.4: pick
# one location per row, don't vary it by quest).
HEART_OFFSET = (-255, 20)
TRIFORCE_OFFSET = (-255, 90)
ITEM_POS_SINGLE = (-175, 55)   # one item this quest -> centered
ITEM_POS_FIRST = (-175, 20)    # two items -> first, aligned with heart
ITEM_POS_SECOND = (-175, 90)   # two items -> second, aligned with triforce

CLEAR_BUTTON_POS = (2830, 90)
QUEST1_BUTTON_POS = (2875, 2025)
QUEST2_BUTTON_POS = (2970, 2025)

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
        return __import__("time").time() - os.path.getmtime(RAM_FILE)
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
        cw, ch = BG_SIZE
        self.canvas = tk.Canvas(root, width=cw, height=ch, bg="black", highlightthickness=0)
        self.canvas.pack()
        self.bg_image = tk.PhotoImage(file=os.path.join(SPR, "background.png"))
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
        self.canvas.create_text(1920, BG_SIZE[1] - 40, text=msg, fill="yellow",
                                 font=("Courier", 16), tags="status")
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

    def _draw_thumb(self, coord: str, x: int, y: int):
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
            fw, fh = THUMB_SIZE
            self.canvas.create_rectangle(x, y, x + fw, y + fh, outline="white")
            self.canvas.create_text(x + fw // 2, y + fh // 2, text=coord,
                                     fill="white", font=("Courier", 12, "bold"))

    def _draw_coord_slot(self, slot_id: str, section_id: str):
        ax, ay = ANCHORS[slot_id]
        rule = _CLICK_RULE[section_id]
        ox, oy = rule["offset"]
        w, h = rule["size"]
        x1, y1 = ax + ox, ay + oy
        self._add_region(x1, y1, x1 + w, y1 + h, lambda s=slot_id: self._on_slot_click(s))

        coords = (self.data["slots"].get(slot_id) or []) if self.data else []
        if not coords:
            return
        tw, th = THUMB_SIZE
        if CAPACITY[slot_id] == "single":
            self._draw_thumb(coords[0], ax, ay)
            self._add_delete_region(ax, ay, ax + tw, ay + th,
                                     lambda s=slot_id: self._on_delete_entry(s, 0))
        else:
            # Multiple thumbnails: row out to the right of the anchor --
            # rows in this layout are close enough together vertically that
            # stacking downward would overlap the next slot.
            tx = ax
            for i, c in enumerate(coords):
                self._draw_thumb(c, tx, ay)
                self._add_delete_region(tx, ay, tx + tw, ay + th,
                                         lambda s=slot_id, idx=i: self._on_delete_entry(s, idx))
                tx += tw + 8

    def _draw_level_toggles(self, level: str):
        ax, ay = LEVEL_ANCHORS[level]
        toggles = self.data["item_toggles"][level]
        quest = self.data["active_quest"]

        if level in LEVELS_WITH_HEART_TRIFORCE:
            hx, hy = ax + HEART_OFFSET[0], ay + HEART_OFFSET[1]
            heart_img = self._img("heartON.png" if toggles["heart"] else "heartOFF.png")
            self._put(heart_img, hx, hy)
            hw = heart_img.width() if heart_img else 52
            hh = heart_img.height() if heart_img else 52
            self._add_region(hx, hy, hx + hw, hy + hh,
                              lambda lv=level: self._on_heart_triforce_click(lv, "heart"))

            tx, ty = ax + TRIFORCE_OFFSET[0], ay + TRIFORCE_OFFSET[1]
            tri_img = self._img("triforceON.png" if toggles["triforce"] else "triforceOFF.png")
            self._put(tri_img, tx, ty)
            tw = tri_img.width() if tri_img else 48
            th = tri_img.height() if tri_img else 55
            self._add_region(tx, ty, tx + tw, ty + th,
                              lambda lv=level: self._on_heart_triforce_click(lv, "triforce"))

        items = QUEST_ITEMS[quest][level]
        positions = [ITEM_POS_SINGLE] if len(items) == 1 else [ITEM_POS_FIRST, ITEM_POS_SECOND]
        for i, (role, (ox, oy)) in enumerate(zip(items, positions)):
            ix, iy = ax + ox, ay + oy
            on = toggles["items"][i]
            letter = "F" if role == "floor" else "S"
            img = self._img(f"{letter} on.png" if on else f"{letter} off.png")
            self._put(img, ix, iy)
            iw = img.width() if img else 47
            ih = img.height() if img else 48
            self._add_region(ix, iy, ix + iw, iy + ih,
                              lambda lv=level, idx=i: self._on_item_click(lv, idx))

    def _draw_quest_switcher(self):
        quest = self.data["active_quest"]
        qx, qy = QUEST1_BUTTON_POS
        img1 = self._img("1 on.png" if quest == 1 else "1 off.png")
        self._put(img1, qx, qy)
        w1 = img1.width() if img1 else 54
        h1 = img1.height() if img1 else 62
        self._add_region(qx, qy, qx + w1, qy + h1, lambda: self._on_quest_click(1))

        qx, qy = QUEST2_BUTTON_POS
        img2 = self._img("2 on.png" if quest == 2 else "2 off.png")
        self._put(img2, qx, qy)
        w2 = img2.width() if img2 else 62
        h2 = img2.height() if img2 else 62
        self._add_region(qx, qy, qx + w2, qy + h2, lambda: self._on_quest_click(2))

    def _draw_clear_button(self):
        cx, cy = CLEAR_BUTTON_POS
        img = self._img("clear button.png")
        self._put(img, cx, cy)
        w = img.width() if img else 208
        h = img.height() if img else 70
        self._add_region(cx, cy, cx + w, cy + h, self._on_clear)

    # ---- full render ----

    def render(self, waiting: bool = False):
        self.canvas.delete("all")
        self._click_regions = []
        self._delete_regions = []

        if waiting:
            self.canvas.create_text(
                1920, 1080, text="Waiting for FCEUX connector...\n"
                                  "(run click_tracker.lua in FCEUX > Lua)",
                fill="white", font=("Courier", 28), justify="center",
            )
            self.root.title("Z1 Click Tracker -- waiting")
            return

        self.root.title(f"Z1 Click Tracker -- {self.data.get('rom_filename_at_creation', '')}")
        self.canvas.create_image(0, 0, image=self.bg_image, anchor="nw")

        for section_id, section in SECTIONS.items():
            for slot_id in section["slots"]:
                self._draw_coord_slot(slot_id, section_id)

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
        self.canvas.create_text(16, BG_SIZE[1] - 16, text=text,
                                 fill="gray60", font=("Courier", 14), anchor="w")


def main() -> int:
    root = tk.Tk()
    root.title("Z1 Click Tracker")
    ClickTrackerApp(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
