"""Detects clickable/display regions from a hand-painted color-key overlay
image, instead of hardcoded pixel offsets.

Color key (confirmed with the source):
    GREEN  - map-thumbnail / coordinate-logging click positions
    CYAN   - Clear button
    ORANGE - quest switcher ("1"/"2") buttons
    RED    - Heart Container toggle
    YELLOW - Triforce Piece toggle
    BLUE   - item toggle position "2a" (first of two)
    PURPLE - item toggle position "2b" (second of two)
    PINK   - item toggle position "1" (single item, centered)

Each flat color may appear as several separate same-colored boxes (e.g. one
red box per level with a Heart). Boxes are grouped into blobs (connected
same-color regions), sorted by position, and matched to specific slot/level
IDs by the caller (click_tracker.py) -- this module only knows about colors
and pixel geometry, nothing about game semantics.

PINK/BLUE/PURPLE can visually overlap (a level needing the single "1"
position in one quest and the two-item "2a"/"2b" positions in the other
quest occupies the same row) -- confirmed with the source: whichever color
was painted on top clips the one underneath, but each blob's top-left
corner is always correct, and every box of a given color is the same
width/height. So every blob's final size is forced to the *mode* (most
common) size seen for that color, keeping only its own detected top-left.

No PIL/numpy dependency: reads pixels directly via Tkinter's own
PhotoImage.get()/.transparency_get() (confirmed fast enough -- ~1.9M
pixels/sec -- to just re-detect on every launch rather than caching, so
resizing the background+overlay pair always "just works" with no stale
lookup table to regenerate).
"""
from __future__ import annotations

import tkinter as tk
from collections import Counter, deque

Box = "tuple[int, int, int, int]"  # (x1, y1, x2, y2)

COLORS: dict[str, "tuple[int, int, int]"] = {
    "green": (0, 255, 24),
    "cyan": (0, 246, 255),
    "orange": (255, 150, 0),
    "red": (255, 0, 0),
    "yellow": (255, 252, 0),
    "blue": (0, 36, 255),
    "purple": (150, 0, 255),
    "pink": (255, 0, 234),
    "lilac": (181, 164, 255),  # icon-clickable areas, in a separate overlay
    # file (clickoverlay.png) from the rest of the color key (overlaypositions.png)
}


def _scan_pixels(img: tk.PhotoImage) -> "dict[str, list[tuple[int, int]]]":
    """One full pass over the image; returns each color's matching,
    non-transparent pixel coordinates."""
    w, h = img.width(), img.height()
    by_rgb = {rgb: name for name, rgb in COLORS.items()}
    found: dict[str, list] = {name: [] for name in COLORS}
    for y in range(h):
        for x in range(w):
            if img.transparency_get(x, y):
                continue
            name = by_rgb.get(img.get(x, y))
            if name:
                found[name].append((x, y))
    return found


def _connected_components(points: "list[tuple[int, int]]") -> "list[set]":
    """Groups points into 4-connected blobs (flood fill)."""
    remaining = set(points)
    blobs = []
    while remaining:
        start = next(iter(remaining))
        blob = set()
        queue = deque([start])
        remaining.discard(start)
        while queue:
            x, y = queue.popleft()
            blob.add((x, y))
            for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                if (nx, ny) in remaining:
                    remaining.discard((nx, ny))
                    queue.append((nx, ny))
        blobs.append(blob)
    return blobs


def _bbox(points) -> Box:
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return (min(xs), min(ys), max(xs) + 1, max(ys) + 1)


def _standardize(boxes: "list[Box]") -> "list[Box]":
    """Forces every box of one color to that color's modal (w,h), keeping
    each box's own top-left corner (handles overlap-clipping)."""
    if not boxes:
        return boxes
    sizes = [(x2 - x1, y2 - y1) for x1, y1, x2, y2 in boxes]
    mode_w, mode_h = Counter(sizes).most_common(1)[0][0]
    return [(x1, y1, x1 + mode_w, y1 + mode_h) for x1, y1, _, _ in boxes]


def detect(overlay_path: str) -> "dict[str, list[Box]]":
    """Returns {color_name: [box, ...]}, each list sorted top-to-bottom
    then left-to-right (row-major) -- callers assign meaning/order on top
    of this raw geometry."""
    img = tk.PhotoImage(file=overlay_path)
    pixels_by_color = _scan_pixels(img)
    result: "dict[str, list[Box]]" = {}
    for name, points in pixels_by_color.items():
        if not points:
            result[name] = []
            continue
        boxes = [_bbox(b) for b in _connected_components(points)]
        boxes = _standardize(boxes)
        boxes.sort(key=lambda b: (b[1], b[0]))
        result[name] = boxes
    return result


def cluster_by_x(boxes: "list[Box]", gap: int = 40) -> "list[list[Box]]":
    """Splits boxes into columns by x-position: sort by x, start a new
    column whenever the gap to the previous box's x exceeds `gap`. Each
    resulting column is then re-sorted top-to-bottom. Purely structural
    (based on relative spacing, not absolute pixel positions), so it holds
    up under resizing the source images."""
    by_x = sorted(boxes, key=lambda b: b[0])
    columns: "list[list[Box]]" = []
    for box in by_x:
        if columns and box[0] - columns[-1][-1][0] <= gap:
            columns[-1].append(box)
        else:
            columns.append([box])
    for col in columns:
        col.sort(key=lambda b: b[1])
    return columns
