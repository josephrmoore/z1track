# Zelda 1 Click-to-Track Overworld Tracker — Production Brief

## 0. Status of this document

Revision 3. Synthesized from the UI mockup, four pages of handwritten flow notes, the vanilla Zelda 1 RAM map, and direct inspection of five real Z1R-generated ROM files. Every item flagged as open in earlier revisions is now resolved: RAM→coordinate formula (2.1), the scribbled-out LOG branch (6.4), Money/Hint subtype meanings (3.1.1), asset coverage (Section 5), and seed identity (6.2, hash-keyed). One new item was added and resolved with a default you can override: the Clear/Reset function's scope (6.3). Nothing in this brief is currently blocking — full build can proceed.

---

## 1. Project Context (for the agent, so it doesn't reinvent solved parts)

A prior version of this project already exists and is **not being rebuilt**:

- FCEUX Lua script scaffolding
- RAM/ROM read interface
- The ability to read the current overworld screen value from RAM

That version failed because the RAM data available didn't reveal anything the original tool needed. The salvage plan discards the original tool's *purpose* but keeps 100% of the *plumbing*. The new purpose is narrower and fully achievable with what's already working: read current overworld screen → convert to a letter/number coordinate → let the user manually log that coordinate against a specific game element by clicking a UI icon → display it.

**This is a manual/click-driven tracker, not an automatic one.** The RAM value is only ever fetched at the moment of a user click. There is no polling, no automatic detection of "you found the sword," no game-state inference beyond "what screen is the player currently standing on." Do not add automatic detection — it isn't in the notes and isn't the design.

This is being built for a **randomizer** ROM, not vanilla Zelda 1 — the notes explicitly say "there will be multiple seeds," and vanilla NES Zelda has no seed variance. This assumption drives Section 6 (Log/Seed Identity) and must be validated (see Open Questions).

---

## 2. Coordinate System

- Overworld is 8 rows × 16 columns = 128 screens.
- Coordinate format: **Letter (A–P, 16 values) + Digit (1–8, 8 values)**, e.g. `A1`, `P8`, `H7`.
- Letter = column, Digit = row (confirmed by mockup examples: P8, C7, F1, B1, H7, A6, K2, etc. — always one letter A–P followed by one digit 1–8).

### 2.1 Translation formula — RESOLVED

The vanilla RAM map documents this exactly, zero page address `$EB`, "Map location":

> Value equals map x location + 0x10 * map y location. The map is 16x8 screens, top-left screen is x=0 & y=0. High nibble = Y coordinate, low nibble = X coordinate.

So:

```
raw = memory.readbyte(0xEB)
x   = raw & 0x0F            -- low nibble, 0–15, column, left→right
y   = (raw >> 4) & 0x0F     -- high nibble, 0–7, row, top→bottom

letter = string.char(string.byte("A") + x)   -- x=0→A, x=15→P
number = y + 1                                -- y=0→"1", y=7→"8"
coordinate = letter .. number
```

Sanity checks against the RAM map's own worked examples: `0x77` → x=7,y=7 → `H8` (the vanilla starting screen); `0x50` → x=0,y=5 → `A6` (Spectacle Rock); `0x37` → x=7,y=3 → `H4` (Level 1 entrance in vanilla — will differ per seed in the randomizer).

**Guard condition**: `$EB` only means "overworld screen" when the player is actually on the overworld. Zero page `$10` ("Current Level") is `0x00` for overworld and nonzero inside a dungeon. Before reading `$EB` on a click, check `$10 == 0`; if the player is in a dungeon when they click, either skip the read or surface an explicit "not on overworld" state — don't log a dungeon room number as if it were an overworld coordinate.

This should be verified once against the randomizer ROM specifically (nothing in the RAM map suggests randomizers relocate `$EB` or `$10`, but the map documents vanilla, and this project targets a randomizer build — confirm the addresses hold in practice before treating this as final).

---

## 3. Data Model

Four top-level **sections**, each containing one or more **slots**. Every slot has:
- an icon/asset (already exists, per your mockup art)
- a capacity mode: `single` or `multi`
- zero or more logged coordinate values

### 3.1 Sections and slots

| Section | Slots | Capacity mode |
|---|---|---|
| **Levels** | Level 1 – Level 9 (9 slots, one per dungeon) | single |
| **Stairs** | Stairs 1 – Stairs 4 (4 slots) | single |
| **Swords** | Wood, White, Magical (3 slots) | single |
| **Money/Hint** | 4 subtypes — see 3.1.1 | multi |
| **Shops** | Bomb, Bait, Ring, Arrow, Key, Candle, Potion (7 slots) | multi |

Total: 9 + 4 + 3 + 4 + 7 = **27 independently tracked slots**, each with its own storage.

#### 3.1.1 Money/Hint subtypes — RESOLVED

Three money-type, one hint-type:

| Icon | Meaning |
|---|---|
| `+` | Secrets that pay out money (burn/bomb/push a spot, get rupees) |
| `−` | Door repair charges (pay rupees to a door repair guy) |
| `+/−` | Gambling (game of chance — can pay out or take rupees) |
| `?` | Hints (information, not money) |

All four remain `multi` capacity — same 4-slot FIFO behavior as the rest of the Money/Hint section and Shops.

### 3.2 Single vs. multi behavior

- **single**: exactly one coordinate value stored. A new click either fills the slot (if empty) or **overwrites** the existing value (if occupied).
- **multi**: a list of coordinate values, ordered by recency. Cap at **4 entries per slot** (your number — "probably max 4," treat as a config constant, not a hard architectural limit). When a 5th value is logged, **drop the oldest entry and append the new one** — this is a FIFO ring buffer, not an unbounded list. This detail is stated in your prose ("as many as will fit on the screen before overwriting older values") but is not drawn out in the flowcharts — make sure the agent implements the eviction, not just an append.

---

## 4. Click-to-Log Flow

This merges the two flowchart drafts (the small "Front Flow" sketch and the fuller "PROG FLOW" sketch — they're the same logic at two levels of detail; build the fuller one).

```
User clicks somewhere in the UI
        │
        ▼
Is the click target a valid/clickable region (an icon)?
        │
   ┌────┴────┐
   NO         YES
   │           │
 do nothing    ▼
          Which region was clicked? → capture region/slot ID (X)
                        │
                        ▼
          Read current RAM overworld screen value
                        │
                        ▼
          Translate to letter+digit coordinate (Section 2)
                        │
                        ▼
          Is slot X a "multi" type? (Section 3.2)
                        │
              ┌─────────┴─────────┐
             YES                  NO
              │                    │
      Append coordinate      Is slot X currently empty?
      to X's list.                 │
      If list length > 4,    ┌─────┴─────┐
      drop oldest entry.    YES           NO
              │              │             │
              │        Add coordinate  Replace existing
              │        to X            coordinate in X
              └──────────────┬─────────────┘
                              ▼
                    Trigger re-render of slot X (Section 5)
                              ▼
                    Write updated state to the session log (Section 6)
```

---

## 5. Rendering / Display Logic

For **every** logged coordinate in every slot, on render:

```
For coordinate value C in slot:
    Does an image asset named "<C>.png" exist? (e.g. "A5.png", "P7.png")
        YES → render that image as the thumbnail, with the coordinate text
              overlaid on top (matches the mockup's screenshots-with-label style)
        NO  → do not attempt to render an image. Print the coordinate label
              as plain text in place of the thumbnail.
```

This fallback (image-missing → text-only) is drawn explicitly in your notes and must not silently fail or leave a blank space — the coordinate value itself is always the source of truth and always gets displayed even with zero art assets.

**Asset naming convention — CONFIRMED**: `<Letter><Digit>.png` — e.g. `A5.png`, `P7.png`, `M1.png`. You already have blank overworld thumbnails for all 128 coordinates under this naming scheme, so in the normal case every lookup should hit the image path, not the fallback. The fallback still needs to exist and needs to be exercised in testing (e.g. via a temporarily-renamed/missing file) — but it's a safety net for a missing asset, not the expected default path.

---

## 6. Persistence / Session Log

### 6.1 What gets stored

All slot state (every section, every slot, every logged coordinate, in order) — kept in a data structure in memory during a session, and also written to disk so state survives a full FCEUX restart/disconnect. This must be a genuine reload path, not just an in-memory cache: on script start, the log is read from disk before anything else happens.

### 6.2 Seed identity — RESOLVED (hash as sole key, filename as display label only)

Investigated two RAM/ROM-based options first (documented above in prior revisions): no in-game seed-check string exists in Z1R (verified empirically against your actual seed files), and no documented RAM address holds one either. That leaves ROM hash and ROM filename. Both are equally trivial to implement — FCEUX Lua exposes `rom.getfilename()` and `rom.gethash("md5")` as built-in one-line calls — so this was never a simplicity trade-off, only a reliability one.

**Final decision: `rom.gethash("md5")` is the sole identity key.** One value, one source of truth, no scenario where two things that were supposed to agree don't. Log files key off the hash: `log_<md5>.json`.

The filename is still captured, but only as a **display label stored inside the log's contents**, not part of the key or the lookup path:

```json
{
  "rom_hash": "64998f3f63ec97973e71ddea4384c0e1",
  "rom_filename_at_creation": "Legend_of_Zelda...ciyXfFNMQLrg_3_sword.nes",
  "slots": { ... }
}
```

This gets you the readability you wanted (glance at the JSON, or a future "list saved seeds" UI, and see the human-meaningful filename Z1R generated) without ever using that filename to *decide* which log is which. If the file gets renamed later, the label goes stale but harmlessly — identity still resolves correctly off the hash. Nothing in the system trusts the filename for correctness, only for display.

### 6.3 Clear/reset function — NEW REQUIREMENT

You flagged this after the seed-identity decision, correctly: a log with no way to wipe it means mis-clicks, testing, or a genuinely fresh start all become permanent stains on that seed's log. This needs a manual clear action.

**Scope decision needed, not yet made by you — default assumption stated below, override if wrong:**

Default: the clear action wipes only the **currently active log** (the one keyed to the currently-loaded ROM's hash) — not every log file on disk. Rationale: a "clear everything" button is a much scarier, harder-to-undo action for something that's supposed to be a low-friction utility, and nothing in the requirements asks for bulk deletion across seeds. If you actually want a "wipe all logs" option too (e.g. for cleaning up disk space across many old seeds), that's a distinct, additional action — say so and it gets added as a separate button, not folded into this one.

Behavior:

```
On "Clear Tracker" click:
    Prompt for confirmation (a single accidental click on this must not be able to destroy a log with no way back)
    On confirm:
        Reset in-memory data structure to empty (all 27 slots, all sections)
        Delete or overwrite the on-disk log file for the current hash key
        Re-render UI to reflect the now-empty state (all icons, no coordinate thumbnails)
    On cancel: no-op
```

Confirmation step is not optional — this is a destructive action with no undo, sitting next to a UI that's otherwise all low-stakes single-click actions (logging a coordinate). Without a confirm step, one misclick erases a session's worth of manual tracking.

### 6.4 Load flow

```
On script load:
    Determine current seed identity (per 6.2)
    Does a log file matching this seed identity exist on disk?
        YES → load it into the in-memory data structure, render all slots immediately
        NO  → do nothing — start with an empty data structure, clean slate
```

The scribbled-out branch is resolved: it was an `ELSE` that got struck through because the "no log found" case is just "do nothing" — there's nothing to load, so the in-memory structure starts empty. No warning state, no merge logic. Simplest possible reading was the correct one.

---

## 7. UI Layout (from mockup)

Three-column layout on a black background, thin white dividers, matching your mockup exactly:

```
┌───────────┬─────────────────────────────────────┬───────────────┐
│  LEVELS   │              SWORDS                  │               │
│  (9 icons,│      (3 icons: Wood/White/Magic)      │               │
│  stacked  ├─────────────────────────────────────┤    SHOPS      │
│  vertically,│            STAIRS                  │  (7 icons,    │
│  1 coord  │      (4 numbered slots)               │   stacked,    │
│  thumbnail│─────────────────────────────────────┤   up to 4     │
│  each)    │           MONEY / HINT                │   coord      │
│           │   (4 subtypes, up to 4 coord          │   thumbnails │
│           │    thumbnails each)                   │   each)      │
└───────────┴─────────────────────────────────────┴───────────────┘
```

Each slot's icon sits next to/above a dynamically-growing (or fixed, for single-slots) row/stack of coordinate thumbnails, rendered per Section 5. Empty slots show no thumbnail — the icon alone, no placeholder box (confirmed by the mockup: several level icons have no coordinate shown yet).

---

## 8. Open Questions — resolve before or during build, don't guess

Two small items remain, neither blocking for most of the build:

1. **Clear button UI placement.** Not specified anywhere in your notes or mockup — the mockup predates this feature. Needs a location that's visible but not adjacent to anything else clickable enough to invite a misclick next to it (e.g. not sandwiched between icon slots). Agent should propose a placement (corner of the layout, separate from the three-column grid) rather than guess something cramped into the existing grid.
2. **"Wipe all logs across all seeds" as a separate feature** — mentioned as a possibility in 6.3 but not something you've actually asked for. Only add it if you say so; the default single-seed clear (6.3) covers everything currently requested.

Neither blocks Sections 1–7. Only the clear-button's exact placement affects Section 7 styling, and even that can be built with a reasonable default and adjusted later.

---

## 9. Suggested build order

1. Data model + slot definitions (Section 3) — no UI yet, just the structure and single/multi/eviction logic, unit-testable in isolation.
2. Coordinate translation (Section 2.1) — implement directly, formula is confirmed. Verify `$EB`/`$10` hold in the actual randomizer ROM before trusting it beyond a quick smoke test.
3. Click flow (Section 4) wired to the data model.
4. Rendering (Section 5), including the image-missing fallback.
5. Persistence + load flow (Section 6) — seed identity, storage format, and clear/reset are all resolved and can be built together.
6. Layout/styling pass to match the mockup (Section 7), including placement for the Clear button (Section 8, item 1) — last, since it's the least functionally risky part.

Don't build 6 before 1–5 are working against dummy data; the mockup is a target, not a starting point.
