# Zelda 1 Click-to-Track — Addendum (Revision 4)

## 0. Status of this document

This is an addendum to `zelda-click-tracker-brief.md` (Revision 3), not a
replacement. Give the builder both documents plus `1st_Quest_Layout.jpg` and
`2nd_Quest_Layout.jpg`. Rev 3 remains the source of truth for everything not
mentioned here: coordinate translation (2.1), the click-to-log flow (4),
thumbnail rendering (5), seed identity and persistence (6.1–6.2, 6.4).

Four changes, in the order the user specified:

1. Per-level Heart Container / Triforce Piece toggles
2. First/Second Quest switcher
3. Layout consolidation to a single static background
4. Outlined text for coordinate labels drawn over map thumbnails

Two items below are **contradictions or gaps in the source material** that
the builder should not silently resolve by guessing — flagged inline and
collected again in Section 7.

---

## 1. Level Item Toggles (Heart Container / Triforce Piece)

### 1.1 What this is

Beside every level icon, up to two small on/off buttons: one for "has this
level's Heart Container been found" and one for "has this level's Triforce
Piece been found." Click toggles it; click again untoggles it. This is
**pure boolean state — it does not read RAM and does not log a coordinate.**
It is unrelated to the existing Levels section's coordinate-logging click
(clicking the level's enemy icon itself still logs the dungeon-entrance
coordinate exactly as in Rev 3 — that behavior is unchanged and must not be
merged with the new toggle clicks).

### 1.2 The S/F label

Each toggle carries a static letter, `F` (Floor) or `S` (Stairs), meaning
*where in the dungeon that item was found* — sitting in the open (F) vs.
behind a bombed/burned secret room reached via a staircase (S). This is
**item-tracking metadata, not a coordinate.**

> **Naming collision warning:** the existing code already has a `stairs`
> section (`SECTIONS["stairs"]`, 4 numbered slots tracking *overworld*
> hidden-staircase entrance coordinates). This new `S` label is a
> completely different concept (a dungeon item's hiding spot). Use distinct
> identifiers in code — e.g. `drop_type: "floor" | "stairs"` for the new
> toggles — so nothing in the codebase conflates the two "stairs."

### 1.3 On/off visual state

Per the source notes: highlighted (on) = colored image or yellow text;
off = grey image or white text. This is the **same on/off visual
convention used by the quest switcher** (Section 2) — implement one
helper/style for "highlighted vs. dimmed" and reuse it for both, rather
than building two separate styling paths.

Whether the heart/triforce glyphs are image assets (on/off variant pairs)
or drawn as colored text/canvas shapes is an open implementation choice
the source material leaves either way — confirm with the user which art
assets actually exist before assuming; see Section 7.

### 1.4 Which levels get which toggles, and why it varies

Composition depends on the active quest (Section 2). At most one heart
toggle and one triforce toggle per level; a level with only one item that
quest shows only one toggle (the other role isn't drawn at all — not
present-but-off, just absent).

### 1.5 Data model

This does not fit the existing `CAPACITY`/single-multi coordinate-list
model (Rev 3 §3) — it's boolean state per level per role, not a coordinate
list. Add a separate structure, e.g. in the log JSON:

```json
"item_toggles": {
  "L1": {"heart": false, "triforce": true},
  "L2": {"heart": false, "triforce": false},
  ...
  "L9": {}
}
```

Only store the on/off boolean. The label (F/S) and whether the role even
exists for that level are *derived* at render time from the active quest,
not stored per-toggle.

### 1.6 Interaction with Clear

Rev 3 §6.3's "Clear Tracker" must now also reset `item_toggles` to all-false
(in addition to the existing 27 slots). Recommended default: Clear does
**not** reset the active quest selection (Section 2) — quest is a property
of the seed/ROM, not logged progress. Flag for the user to override if
wrong, same pattern as Rev 3's original clear-scope decision.

---

## 2. First/Second Quest Switcher

### 2.1 UI

Small "1" / "2" control (bottom-right in the mockups). Clicking one makes
it active (highlighted per §1.3's convention) and re-renders every level
row's toggles per the table below. This does not touch RAM.

### 2.2 Quest table (from source notes)

| Level | 1st Quest | 2nd Quest |
|---|---|---|
| L1 | Floor + Stairs (both items present) | Floor only |
| L2 | Floor only | Stairs only |
| L3 | Stairs only | Floor only |
| L4 | Stairs only | 2× Stairs (both items present, both stairs-found) |
| L5 | Stairs only | *(same as 1st)* |
| L6 | Stairs only | *(same as 1st)* |
| L7 | Stairs only | *(same as 1st)* |
| L8 | 2× Stairs (both items present, both stairs-found) | *(same as 1st)* |
| L9 | 2× Stairs — **but also stated as no triforce, no heart** | *(same as 1st)* |

**L9 is contradictory in the source notes as written** (see Section 7,
item 1) — the mockups show plain "S S" text on that row with no toggle
icons at all, which suggests L9 has zero interactive toggles despite the
"2 STAIRS" line. Build L9 with **no toggles** (matching the mockups) unless
the user says otherwise; don't try to reconcile the text literally.

**Important gap:** this table gives the *count* of items per level per
quest, but does not say *which role* (heart vs. triforce) gets the F vs.
the S label when only one item exists (L2/L3 in 1st quest; L1/L2/L3 in 2nd
quest). That assignment is only visible in the mockup images — read it
directly off each row rather than inferring it from this table.

### 2.3 Persistence

Recommended default: `active_quest` (1 or 2) is stored per-log (i.e., a
property of the current seed), similar to how `rom_hash`/`rom_filename` are
scoped in Rev 3 §6.2 — add it as a top-level field alongside `item_toggles`.
Confirm with the user if a global (not per-seed) default is actually
intended instead.

---

## 3. Layout Consolidation

### 3.1 The change

Per the user: everything except (a) the item toggles from Section 1, (b)
the quest switcher from Section 2, (c) the coordinate thumbnails from
Rev 3 §5, and (d) the Clear button, becomes **one static background image**.
All the currently-dynamic chrome — level/sword/stair/shop/money-hint icons,
frame boxes, dividers, section labels — stops being computed/drawn by
`LAYOUT`/`_render_section`/`_draw_icon_slot`'s icon-drawing path and is
instead baked into a single background PNG.

This is a genuine architectural reversal of Rev 3's design intent (which
went out of its way to make icon layout self-adjusting from asset
dimensions, specifically to avoid hardcoded pixel positions). That
self-adjusting system should now be **retired for the chrome elements**,
not preserved alongside the new static image — keeping both would just be
wasted, unused code. `_draw_thumb` (Rev 3 §5) stays exactly as-is; only its
anchor points change source (see 3.3).

### 3.2 Why this actually simplifies things further

The heart/triforce toggles (Section 1) can never be part of a static
image anyway — they have on/off state and must be drawn dynamically
regardless of quest. That means the "L1–L4 differ by quest" problem
(Section 2) is already solved by the toggles being dynamic; **there is no
need for two separate background images, one per quest.** One
quest-invariant background (everything that never changes: enemy icons,
sword icons, numbered stair icons, shop icons, key/bomb/ring/candle/potion
icons, dividers, static frame art) plus dynamically-drawn, quest-aware
heart/triforce glyphs on top is sufficient. Confirm this matches the
user's intent before building two backgrounds.

### 3.3 Click hit-testing on a static image

Icons baked into a flat background can't have a Tk event bound to "part of
an image." Every element that's still clickable (the 27 existing
coordinate-logging slots, the new per-level toggles, the quest switcher,
Clear) needs an **invisible rectangle canvas item** positioned over its
location in the final background, tagged/bound to the existing handler
(`_on_click`, or new toggle/quest handlers). This requires a fixed pixel
bounding box per clickable region — something only obtainable once the
actual background asset exists. Two ways to get there, either is fine, but
one of them has to happen:

- the user supplies a coordinate map alongside the background PNG, or
- the builder measures the final PNG once delivered and hardcodes a
  region table.

Don't guess these coordinates from the mockup screenshots — the mockups
are reference art, not necessarily final pixel-exact assets.

### 3.4 Icon position consistency (already resolved, not open)

The user has explicitly directed: the slight position mismatch for the
heart/triforce/level icons between the two mockups is an unintentional
artifact of early mockup work. Pick **one** location per level row and use
it for both quests — don't preserve the discrepancy.

---

## 4. Outlined Labels Over Map Thumbnails

Applies specifically to `_draw_thumb`'s on-image text branch (Rev 3 §5 —
the coordinate code, e.g. "P8", drawn on top of a map thumbnail). Change
from solid-color fill to white text with a 1–2px black outline for
readability. Tkinter's canvas text has no native stroke/outline property —
the standard workaround is drawing the same string multiple times at small
pixel offsets (e.g. 8 offsets: N/S/E/W/diagonals) in black, then once more
in white on top, all at the same anchor point. This does **not** apply to
any other UI text (labels, letters, status line, debug line) — only the
coordinate labels overlaid on map thumbnail images.

---

## 5. Data Model Summary (diff against Rev 3 §6.2's log schema)

```json
{
  "rom_hash": "...",
  "rom_filename_at_creation": "...",
  "active_quest": 1,
  "item_toggles": {
    "L1": {"heart": false, "triforce": false},
    "...": "...",
    "L9": {}
  },
  "slots": { "...": "unchanged from Rev 3" }
}
```

`Clear Tracker` (Rev 3 §6.3) resets `slots` and `item_toggles`, not
`active_quest`.

---

## 6. Suggested build order for this increment

1. DONE SEE BELOW Confirm the two open items in Section 7 with the user before writing
   any rendering code — both affect what gets built, not just how.
2. Data model: `item_toggles` + `active_quest` fields, load/save, Clear
   reset (cheap, no UI, unit-testable against dummy data).
3. Quest table as a data structure (per Section 2.2), driving which
   toggles exist and their F/S label per level — read exact per-level
   role assignment off the mockups, not inferred from the count table.
4. Retire the dynamic chrome-layout rendering path; wire up the static
   background image once delivered, with a hardcoded hit-region table
   (Section 3.3) reusing the existing `_on_click`/slot-id plumbing.
5. Toggle click handler (boolean flip, no RAM read) + quest-switcher click
   handler, both using one shared highlighted/dimmed style helper.
6. Outlined-text change to `_draw_thumb` (isolated, low-risk, do last).

---

## 7. Answers to Questions

1. **L9 contradiction.** Level 9 has NO HEART and NO TRIFORCE as it's the end of the game. You are expected to have all of those before you enter.
2. **All needed art (icons and otherwise) are in the project folder.
3. **One universal background will be used. You will just switch the layout of the F and S icons and the 1 2 switcher icons on quest change. Everything else stays the same.


## 8. Coordinate Mapping

MAP IMG PLACEMENT

Use top-left origin on loaded map images to place @ (x, y) for column rendering:
1. LEVELS (Col 1, 9 total): L1: (500, 85) | L2: (500, 320) | L3: (500, 550) | L4: (500, 780) | L5: (500, 1000) | L6: (500, 1235) | L7: (500, 1460) | L8: (500, 1690) | L9: (500, 1920)
2. SWORDS & STAIRS (Col 2, 7 total): (1100, 85), (1100, 320), (1100, 550), (1100, 780), (1100, 1000), (1100, 1235), (1100, 1460)
3. SHOPS / MONEY / HINTS (Col 3, 11 total): (1660, 80), (1660, 270), (1660, 460), (1660, 650), (1660, 830), (1660, 1020), (1660, 1205), (1660, 1390), (1660, 1580), (1660, 1765), (1660, 1950)

CLICKABLE AREA

The (X,Y) of the clickable area is given as a coordinate offset from the map image coordinates given above. That plus the width & height of each clickable area should be enough to place them.

For each item in:

1. LEVELS
** OFFSET TOPLEFT = (-430, -20)
** WIDTH/HEIGHT = (335, 195)

2. SWORD/STAIRS
**OFFSET TOPLEFT = (-240,-15)
**WIDTH/HEIGHT = (165, 195)

3. SHOPS/MONEY/HINTS
**OFFSET TOPLEFT = (-230, -15)
**WIDTH/HEIGHT = (190, 160)

EXAMPLE So level 1 clickable is at TOPLEFT: (70,65) since the map img is at (500,85), calculating from the offsets: 500-430=70, 85-20=65. With a TOPLEFT of (70, 65) the BOTTOMRIGHT should be (405,260) since the WIDTH is 335 and the HEIGHT is 195