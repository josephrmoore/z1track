#!/usr/bin/env python3
"""Z1 Click-to-Track: manual overworld coordinate logger.

Not an automatic tracker. The RAM is read once, at the moment of a click,
to answer "what overworld screen is this?" -- nothing is polled or inferred
beyond that. See zelda-click-tracker-brief.md for the full spec.

Reuses the old project's plumbing (file-based FCEUX Lua connector writing
ram.hex) and nothing else -- the rest of the old app (auto-inventory/
triforce/etc. tracking) is gone; this is a different product.

To redesign the look: edit LAYOUT only. It's the sole place pixel positions,
colors, fonts, and spacing live -- nothing else in this file cares about
where things are drawn. SECTIONS is the content (what slots exist, their
icons, single/multi capacity) and is independent of how it's laid out.
"""
from __future__ import annotations

import json
import math
import os
import sys
import tempfile
import tkinter as tk
from tkinter import messagebox

HERE = os.path.dirname(os.path.abspath(__file__))
SPR = os.path.join(HERE, "clicktracksprites")
MAP_DIR = os.path.join(SPR, "map")
RAM_FILE = os.path.join(HERE, "ram.hex")
ROM_INFO_FILE = os.path.join(HERE, "rom_info.json")
RAM_SIZE = 0x800
MULTI_CAP = 4
# The Lua connector rewrites ram.hex roughly every 15 frames (~0.25s at 60fps).
# If it's older than this, the connector isn't actually running right now
# (crashed, closed, or pointed at the wrong folder) -- the bytes in the file
# might still *look* like a perfectly valid, plausible screen (this is
# exactly how a stale-but-well-formed file was mistaken for a live one
# before), so freshness has to be checked independently of whether the
# value decodes cleanly.
STALE_SECONDS = 2.0

# ---------------------------------------------------------------- content
# What exists: sections, their slots, icon assets, and single/multi capacity.
# This is data-model content, not layout -- redesigning the look should never
# require touching this block.

SECTIONS = {
    "levels": {
        "capacity": "single",
        "folder": "levels",
        "slots": [
            ("L1", "01 aquamentus.png"), ("L2", "02 dodongo.png"), ("L3", "03 manhandla.png"),
            ("L4", "04 gleeok.png"), ("L5", "05 digdogger.png"), ("L6", "06 gohma.png"),
            ("L7", "07 moblin.png"), ("L8", "08 gleeok 8.png"), ("L9", "09 ganontriforce.png"),
        ],
    },
    "swords": {
        "capacity": "single",
        "folder": "swords",
        "slots": [
            ("wood", "wood sword.png"), ("white", "white sword.png"), ("magical", "magical sword.png"),
        ],
    },
    "stairs": {
        "capacity": "single",
        "folder": "stairs",
        "slots": [("stair1", "1.png"), ("stair2", "2.png"), ("stair3", "3.png"), ("stair4", "4.png")],
    },
    "money_hint": {
        "capacity": "multi",
        "folder": "money-hints",
        "slots": [("plus", "+.png"), ("minus", "-.png"), ("plusminus", "+_-.png"), ("hint", "_.png")],
    },
    "shops": {
        "capacity": "multi",
        "folder": "shops",
        "slots": [
            ("bomb", "bomb.png"), ("bait", "meat.png"), ("ring", "bluering.png"),
            ("arrow", "arrow.png"), ("key", "key.png"), ("candle", "blue candle.png"),
            ("potion", "potion.png"),
        ],
    },
}

# Derived lookups (built once from SECTIONS -- not hand-duplicated).
CAPACITY: dict[str, str] = {}
ICON_DIR: dict[str, str] = {}
for _section in SECTIONS.values():
    for _slot_id, _fname in _section["slots"]:
        CAPACITY[_slot_id] = _section["capacity"]
        ICON_DIR[_slot_id] = os.path.join(SPR, _section["folder"], _fname)


def thumb_path(coord: str) -> str:
    return os.path.join(MAP_DIR, f"{coord}.png")


# ----------------------------------------------------------------- layout
# How it looks: every pixel position, color, font, and spacing rule lives
# here. Redesign by editing this dict -- nothing below reads a hardcoded
# number outside of it. Icon and thumbnail spacing is computed at render
# time from actual (post-scale) image sizes plus "margin", so mismatched
# asset sizes can never silently overlap -- there's nothing to keep in sync
# by hand when swapping art.

LAYOUT = {
    "canvas": (1300, 830),
    "colors": {
        "bg": "black", "fg": "white", "status": "yellow", "clear": "orange",
        # Coordinate labels drawn over an actual thumbnail image need a dark
        # color to stay readable against the (mostly light) map art; labels
        # drawn in a fallback box (solid bg fill, no image) need "fg" instead
        # or they'd be invisible against it.
        "thumb_label_on_image": "black",
    },
    "fonts": {
        "fallback_icon": ("Courier", 8),
        "thumb_label": ("Courier", 12, "bold"),
        "status": ("Courier", 11),
        "clear_button": ("Courier", 11, "bold"),
        "waiting": ("Courier", 14),
    },
    "icon_box": (72, 72),          # icons are scaled down (integer factor) to fit this box
    "icon_fallback_size": 48,      # square placeholder if an icon asset fails to load
    "thumb_subsample": 3,          # map/*.png are 253x177 native; divide both dims by this
    "thumb_fallback_size": (84, 59),
    "margin": 12,                  # gap between an icon/thumbnail and whatever follows it
    "column_divider_x": [230, 830],  # static vertical dividers between the 3 columns
    "column_gap": 20,   # gap (and divider line) between stacked sections in a column
    "clear_button": (1170, 6, 1272, 34),
    "status_pos": (650, 780),
    "waiting_pos": (650, 400),
    "sections": {
        # direction: which way consecutive icons *within* a section stack.
        # thumbs_dir: where an icon's own coordinate thumbnail(s) render:
        #   "right"     -- single column of thumbnails, to the icon's right
        #   "right_row" -- thumbnails in a horizontal row, to the icon's right
        #   "below"     -- thumbnails stacked in a column, below the icon
        "levels":     {"origin": (8, 8), "direction": "vertical",   "thumbs_dir": "right"},
        "swords":     {"x": 250,          "direction": "horizontal", "thumbs_dir": "below"},
        "stairs":     {"x": 250,          "direction": "horizontal", "thumbs_dir": "below"},
        "money_hint": {"x": 250,          "direction": "horizontal", "thumbs_dir": "below"},
        "shops":      {"origin": (840, 8), "direction": "vertical",   "thumbs_dir": "right_row"},
    },
    # Sections stacked in the same column, top to bottom: each one's origin
    # is computed from the previous one's actual rendered height (+ gap), so
    # a bigger/smaller icon or a full 4-slot stack of thumbnails can never
    # silently overlap the next section -- there's no fixed y to fall out of
    # sync with the art. A divider line is drawn in each gap automatically.
    "column_stacks": [["swords", "stairs", "money_hint"]],
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
    """Seconds since ram.hex was last written, or None if it doesn't exist.
    A large/growing age with a live FCEUX session means the connector Lua
    script has stopped updating it (crashed, or never running) -- the file
    can be perfectly valid-looking hex and still be frozen from minutes ago."""
    try:
        return __import__("time").time() - os.path.getmtime(RAM_FILE)
    except OSError:
        return None


def get_current_coordinate() -> "tuple[str | None, str, dict]":
    """Returns (coordinate_or_None, status_code, debug_info).

    status_code is one of: "ok", "no_ram", "invalid",
    "no_dungeon_return" (in a dungeon, but the game hasn't recorded an
    overworld return screen yet this file).

    debug_info always has "age" (seconds since ram.hex was last written,
    or None); on a successful read it also has "level"/"eb"/"ret" (the raw
    bytes) so a frozen-but-valid file is easy to tell apart from a genuinely
    wrong address.
    """
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

class ClickTrackerApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.icons: dict[str, "tk.PhotoImage | None"] = {}
        self.thumbs: dict[str, "tk.PhotoImage | None"] = {}
        cw, ch = LAYOUT["canvas"]
        self.canvas = tk.Canvas(root, width=cw, height=ch,
                                 bg=LAYOUT["colors"]["bg"], highlightthickness=0)
        self.canvas.pack()
        self.data: "dict | None" = None
        self.rom_hash: "str | None" = None
        self._status_after = None
        self._last_debug: "dict | None" = None
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

    # ---- image loading (cached, scaled to fit LAYOUT["icon_box"]) ----

    def _icon(self, slot_id: str) -> "tk.PhotoImage | None":
        if slot_id not in self.icons:
            path = ICON_DIR[slot_id]
            try:
                img = tk.PhotoImage(file=path)
                box_w, box_h = LAYOUT["icon_box"]
                factor = max(1, math.ceil(max(img.width() / box_w, img.height() / box_h)))
                if factor > 1:
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
                    n = LAYOUT["thumb_subsample"]
                    self.thumbs[coord] = tk.PhotoImage(file=path).subsample(n, n)
                except tk.TclError:
                    self.thumbs[coord] = None
            else:
                self.thumbs[coord] = None
        return self.thumbs[coord]

    # ---- click handling ----

    def _on_click(self, slot_id: str, _event=None):
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

    def _flash_status(self, msg: str):
        self.render()
        x, y = LAYOUT["status_pos"]
        self.canvas.create_text(x, y, text=msg, fill=LAYOUT["colors"]["status"],
                                 font=LAYOUT["fonts"]["status"], tags="status")
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

    def _draw_icon_slot(self, slot_id: str, x: int, y: int, thumbs_dir: str) -> "tuple[int, int]":
        """Draws one icon plus its logged coordinate thumbnail(s). Returns
        the icon's actual (post-scale) (width, height), which callers use to
        compute where the next icon in the section goes."""
        colors, fonts = LAYOUT["colors"], LAYOUT["fonts"]
        icon = self._icon(slot_id)
        on_click = lambda e, s=slot_id: self._on_click(s, e)  # noqa: E731
        if icon:
            iw, ih = icon.width(), icon.height()
            # Bind the click directly to the image item itself -- an extra
            # rectangle layered on top (or underneath, unbound) either hides
            # the icon or silently swallows the click: in a Tk canvas, only
            # the topmost item under the pointer gets the event, so exactly
            # one of the two problems happens if the icon and the clickable
            # region are two different, differently-ordered items.
            img_id = self.canvas.create_image(x, y, image=icon, anchor="nw")
            self.canvas.tag_bind(img_id, "<Button-1>", on_click)
        else:
            iw = ih = LAYOUT["icon_fallback_size"]
            # fill=bg (not "") so the interior -- not just the outline -- is
            # hit-testable, matching how a real icon's full bbox is
            # clickable; still visually just an outlined box with a label.
            rect = self.canvas.create_rectangle(x, y, x + iw, y + ih,
                                                 outline=colors["fg"], fill=colors["bg"])
            self.canvas.tag_bind(rect, "<Button-1>", on_click)
            txt = self.canvas.create_text(x + iw // 2, y + ih // 2, text=slot_id,
                                           fill=colors["fg"], font=fonts["fallback_icon"])
            self.canvas.tag_bind(txt, "<Button-1>", on_click)

        coords = (self.data["slots"].get(slot_id) or []) if self.data else []
        margin = LAYOUT["margin"]
        thumb_w, thumb_h = LAYOUT["thumb_fallback_size"]
        if thumbs_dir == "right":
            tx, ty = x + iw + margin, y
            for c in coords:
                self._draw_thumb(c, tx, ty)
        elif thumbs_dir == "below":
            tx, ty = x, y + ih + margin
            for c in coords:
                self._draw_thumb(c, tx, ty)
                ty += thumb_h + margin
        elif thumbs_dir == "right_row":
            tx, ty = x + iw + margin, y
            for c in coords:
                self._draw_thumb(c, tx, ty)
                tx += thumb_w + margin
        return iw, ih

    def _draw_thumb(self, coord: str, x: int, y: int):
        colors, fonts = LAYOUT["colors"], LAYOUT["fonts"]
        fw, fh = LAYOUT["thumb_fallback_size"]
        img = self._thumb(coord)
        if img:
            self.canvas.create_image(x, y, image=img, anchor="nw")
            self.canvas.create_text(x + img.width() // 2, y + img.height() // 2,
                                     text=coord, fill=colors["thumb_label_on_image"],
                                     font=fonts["thumb_label"])
        else:
            # Section 5's required fallback: no image asset -> plain text,
            # never a blank gap.
            self.canvas.create_rectangle(x, y, x + fw, y + fh, outline=colors["fg"])
            self.canvas.create_text(x + fw // 2, y + fh // 2, text=coord,
                                     fill=colors["fg"], font=fonts["thumb_label"])

    def _render_section(self, section_id: str, origin: "tuple[int, int] | None" = None):
        """Walks one section's slots along its configured direction, using
        each icon's actual size (+ margin, + thumbnail size when thumbnails
        would otherwise extend past the next icon's position) to compute
        where the next one goes -- so nothing overlaps regardless of how the
        underlying art assets change. Every item drawn is tagged with the
        section id so its total rendered extent can be measured afterward
        (used to stack sections in the same column dynamically)."""
        section = SECTIONS[section_id]
        layout = LAYOUT["sections"][section_id]
        margin = LAYOUT["margin"]
        thumb_w, thumb_h = LAYOUT["thumb_fallback_size"]
        x, y = origin if origin is not None else layout["origin"]
        direction = layout["direction"]
        thumbs_dir = layout["thumbs_dir"]
        before = self.canvas.find_all()
        for slot_id, _ in section["slots"]:
            iw, ih = self._draw_icon_slot(slot_id, x, y, thumbs_dir)
            if direction == "vertical":
                step = ih
                if thumbs_dir in ("right", "right_row"):
                    step = max(step, thumb_h)
                y += step + margin
            else:
                step = iw
                if thumbs_dir == "below":
                    step = max(step, thumb_w)
                x += step + margin
        after = self.canvas.find_all()
        for item in set(after) - set(before):
            self.canvas.addtag_withtag(section_id, item)

    # ---- full render ----

    def render(self, waiting: bool = False):
        colors, fonts = LAYOUT["colors"], LAYOUT["fonts"]
        self.canvas.delete("all")

        if waiting:
            wx, wy = LAYOUT["waiting_pos"]
            self.canvas.create_text(
                wx, wy, text="Waiting for FCEUX connector...\n"
                              "(run click_tracker.lua in FCEUX > Lua)",
                fill=colors["fg"], font=fonts["waiting"], justify="center",
            )
            self.root.title("Z1 Click Tracker -- waiting")
            return

        self.root.title(f"Z1 Click Tracker -- {self.data.get('rom_filename_at_creation', '')}")

        cw, ch = LAYOUT["canvas"]
        for div_x in LAYOUT["column_divider_x"]:
            self.canvas.create_line(div_x, 0, div_x, ch, fill=colors["fg"])

        stacked_ids = {sid for stack in LAYOUT["column_stacks"] for sid in stack}
        for section_id in SECTIONS:
            if section_id not in stacked_ids:
                self._render_section(section_id)

        gap = LAYOUT["column_gap"]
        for stack in LAYOUT["column_stacks"]:
            x = LAYOUT["sections"][stack[0]]["x"]
            y = 8
            left_x = min(LAYOUT["column_divider_x"], default=0)
            right_x = max(LAYOUT["column_divider_x"], default=cw)
            for i, section_id in enumerate(stack):
                if i > 0:
                    self.canvas.create_line(left_x, y, right_x, y, fill=colors["fg"])
                    y += gap
                self._render_section(section_id, origin=(x, y))
                bbox = self.canvas.bbox(section_id)
                y = (bbox[3] if bbox else y) + gap

        cx1, cy1, cx2, cy2 = LAYOUT["clear_button"]
        clear_rect = self.canvas.create_rectangle(cx1, cy1, cx2, cy2, outline=colors["fg"])
        clear_txt = self.canvas.create_text((cx1 + cx2) // 2, (cy1 + cy2) // 2,
                                             text="Clear Log", fill=colors["clear"],
                                             font=fonts["clear_button"])
        self.canvas.tag_bind(clear_rect, "<Button-1>", self._on_clear)
        self.canvas.tag_bind(clear_txt, "<Button-1>", self._on_clear)

        self._draw_debug_line()

    def _draw_debug_line(self):
        """Persistent (not auto-clearing) readout of the last click's raw
        RAM read -- diagnostic aid so a frozen ram.hex (Lua connector died,
        file just isn't updating) is easy to tell apart from a live file
        whose addresses are simply wrong for a given setup."""
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
        self.canvas.create_text(8, LAYOUT["canvas"][1] - 10, text=text,
                                 fill="gray60", font=("Courier", 9), anchor="w")


def main() -> int:
    root = tk.Tk()
    root.title("Z1 Click Tracker")
    ClickTrackerApp(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
