# Z1Track Module 1 — Code Review & Logic Check

Scope: `rom.py`, `traversal.py`, `items.py`, `ram.py`, `state.py`, `service.py`,
`display.py`, and the test suite. Ranked by how much each issue can actually
corrupt tracker output.

---

## 1. `is_z1r_level_format` iterates the wrong range — corrupts dungeon discovery

In `rom.py`:

```python
is_z1r_format = traversal.is_z1r_level_format(
    [reader.level_info(lvl) for lvl in range(10)],
    ROM["stairway_list_offset"],
)
```

`range(10)` includes level index `0`. `level_info(0)` reads
`0x19300–0x193FC`, which per the ROM map is palette control codes / sprite
palettes / Link's starting position / warp screen table — not a level info
block. The byte the check inspects (`0x1933D`) falls in an undocumented gap
between the warp-screen table and the real dungeon data at `0x193FF`. Its
value is unrelated noise.

`is_z1r_level_format` returns `False` for the *entire ROM* if any single
block's checked byte isn't in `range(0,5)` — so this bogus level-0 read can
flip the whole detection to `False` on a real Z1R seed. When that happens,
`read_stairway_list` won't pop the trailing "entrance direction" byte, and
per `traversal.py`'s own docstring, that byte gets fed into
wall-connectivity discovery as a fake staircase room, which "can corrupt
connectivity for other rooms." That's checks silently appearing/disappearing
per level — the core output of Module 1.

**Fix:** `range(1, 10)`.

Your test fixture never triggers this because `rom_builder.py` never writes
`level_info(0)`, so the byte defaults to `0x00`, which is coincidentally in
range. That's why it's untested.

---

## 2. `MAJOR_ITEMS` is missing Magical Shield, and inconsistently missing base-tier items

```python
MAJOR_ITEMS = frozenset({
    0x01, 0x02, 0x03, 0x05, 0x07, 0x09, 0x0A, 0x0B, 0x0C, 0x0D, 0x0E,
    0x10, 0x11, 0x13, 0x14, 0x1A, 0x1B, 0x1D, 0x1E,
})
```

`0x1C` (Magical Shield) is absent entirely. It's not tiered, not minor, no
reason to exclude it — this looks like a plain omission. Any dungeon that
places Magical Shield in a room will never register that room as a check,
ever, under any flagset.

Also asymmetric: for the three tiered items, only the "upgrade" tier is
included (`0x07` Red Candle but not `0x06` Blue Candle, `0x09` Silver Arrow
but not `0x08` Wood Arrow, `0x13` Red Ring but not `0x12` Blue Ring) — yet
for Sword, the base tier (`0x01` Wood Sword) *is* included alongside
`0x02`/`0x03`. If that asymmetry is deliberate (e.g., base-tier
candle/arrow/ring can never land in a dungeon room under your flag rules),
fine, but nothing documents that, and it contradicts the sword precedent.

Concretely: your own `rom_builder.vanilla_layout()` sets Level 7 = `0x1C`
and Level 8 = `0x12`. Neither will ever show up as a check. `test_contract.py`
only asserts on levels 1 and 3, so this ships silently. Add assertions for
levels 7/8 once you fix it, or you'll reintroduce it.

---

## 3. Overworld heart-cave count can overcount

```python
heart_cave_screens_found = _cave_destination_screens(reader, 1)
coast_item = reader.u8(ROM["coast_item"]) & 0x3F
if coast_item == 0x1A and coast_screen not in heart_cave_screens_found:
    heart_cave_screens_found.append(coast_screen)
```

Coast is gated on actually holding `0x1A` this seed. The numbered-cave path
(`_cave_destination_screens(reader, 1)`) isn't — every screen destined for
"cave slot 1" gets counted as a heart cave regardless of what item that cave
slot actually holds in this seed's `cave_items()` table. If item shuffle can
put something other than a heart in slot 1, you'll report a cave as
"cleared toward N/5" that never held a heart. Your own comment acknowledges
overcounting is possible but attributes it to something else ("inactive
alternate overworld layout") — the missing item-check is a more direct cause
and is fixable the same way Coast is handled: look up `cave_items()[1]` and
only count screens where that slot's item is `0x1A`.

---

## 4. Write throttle in `service.py` is a no-op

```python
changed = state != last_state
...
if changed or flip or (now - last_write) >= self.write_every:
```

`state` includes `"updatedAt": now.isoformat()`, refreshed every call. So
`changed` is true on essentially every poll, and `write_every_ms` never
actually gates anything — you write at full `poll_ms` cadence always, not
the documented "minimum interval between writes." Not a correctness bug
(data's still right), but it's not doing what the code and CLI help text
claim, and it multiplies `os.replace()` calls (and thus your Windows-
permission-retry path) far more than intended.

**Fix:** compare state with `updatedAt` (and any other purely-informational
timestamp) stripped out, or hash the meaningful subset.

---

## 5. TCP source: timeout handling contradicts its own staleness design

`TcpRamSource.__init__` takes `timeout` but never uses it — `_connect()`
hardcodes `socket.create_connection(..., timeout=2.0)`. More importantly: a
bare `socket.timeout` (which will happen routinely — it just means no new
line arrived in the last 2s, not a real disconnect) is caught by the same
except-block as an actual socket error, calls `self.drop()`, and `drop()`
unconditionally sets `self._last_ram = None`. That defeats the
`STALE_SECONDS = 3.0` grace period entirely for this source — the class
defines a 3-second tolerance for staleness but the timeout path never
reaches the code that would honor it, because the cache is already nuked and
`ConnectionError` is raised before that check runs. Given the whole point of
this module is "instantly current even across drops, don't flap on
transient blips," this is worth tightening: don't wipe `_last_ram` on a
plain timeout, only on an actual `recv()` returning empty / connection reset.

---

## 6. Dead / inconsistent constants (landmines, not bugs yet)

- `WHITE_SWORD_CAVE = 0x04` is defined in `items.py` but the call site uses
  a literal `2`: `_find_unique_cave_screen(reader, 2, OW_SCREENS["white_sword"])`.
  Either the constant is stale or the call site should use it — right now
  you have two "sources of truth" for the same cave number that disagree,
  and only one is live.
- `ARMOS_CAVE = 0x14`, `COAST_CAVE = 0x15` — out of range for the 20-slot
  numbered-cave system (0–19) and unused anywhere. Armos/Coast are correctly
  handled via their own direct ROM addresses; these two constants are
  leftover from an earlier design and should be deleted before someone
  "helpfully" wires them in.
- `LEVEL_ROOMS` in `items.py` (hardcoded boss/map/compass/triforce rooms per
  level) is dead — superseded by the traversal-based discovery in `rom.py`.
  It's not cross-checked against the dynamic result anywhere, so it can
  silently drift from reality and mislead whoever reads it next expecting
  it to be authoritative. Delete or clearly mark as historical reference.

---

## 7. Minor, no action needed unless you want it clean

- `MAJOR_ITEMS` contains `0x03` and `0x0E`, which are also in
  `DUNGEON_NO_ITEM_IDS` and get filtered out before the `MAJOR_ITEMS` check
  ever runs. Harmless, just redundant.
- `_cave_destination_screens`'s local var `table1` actually reads ROM-map
  "Table 2" (`0x18480`), not "Table 1" (`0x18400`). Naming only; the offset
  math (`0x80` into the 0x300 slice) is correct.
- `display.py`'s `.replace("_", " ")` on item names is a no-op since
  `ITEM_NAMES` already use spaces.
- `decode_hearts`'s `containersCollected = max(0, containers - 3)` hardcodes
  a 3-heart start. A "Starting Hearts" flag that changes this will silently
  misreport. Not a bug against current default assumptions, just a landmine
  for a flag you've already told me exists.

---

## What actually checks out

- RAM screen-state block boundaries (`0x067F/0x06FF/0x077F`) are contiguous
  and match the RAM map exactly; `taken()`'s `0x10` bit masking is correct
  and applied consistently.
- The dungeon room-byte plane layout and the `0x1F` item mask are correctly
  derived — you're reading the "floor items" table as plane 4 of the level
  block, which is right per the ROM map, and item codes above `0x1F` genuinely
  can't appear there, so the mask isn't losing real data.
- Staircase BFS + reverse staircase lookup (`traversal.py`) is structurally
  sound.
- Mixed-quest handling (independent early/late pointer resolution) is
  correctly implemented.
- Armos/Coast screen discovery (reading them as direct per-seed ROM values
  rather than hardcoded vanilla positions) is the right call and matches the
  ROM map addresses exactly.

---

## Priority order if fixing

1. **#1** — silent, seed-dependent corruption of the entire discovery pipeline
2. **#2** — guaranteed miss on two vanilla item types with zero test coverage
3. **#3** — overworld heart-cave overcounting
4. **#4 / #5** — service-layer correctness of the "always current" guarantee
5. Constant cleanup (#6) and minor items (#7)
