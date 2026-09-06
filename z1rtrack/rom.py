"""Reads a Z1R (or vanilla) Legend of Zelda .nes file and builds the static
"ledger" of where every item is placed.

The randomizer writes item IDs into the ROM's data tables; the *layout* of
those tables is identical in vanilla and randomized ROMs (the randomizer
patches bytes in place).  We therefore read the .nes file directly (no
emulator required) using the exact conventions of the reference randomizer
(tetraly/zelda-randomizer): file offset = 0x10 + address.

The ledger is immutable for a given seed, which makes it the
disconnection-proof half of the tracker: ROM hash -> ledger, cached.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Optional

from .items import (
    DUNGEON_NO_ITEM_IDS,
    ITEM_NAMES,
    LEVELS_WITH_HEART,
    MAJOR_ITEMS,
    NO_ITEM_IDS,
    OW_SCREENS,
    POINTER_TO_GRID,
    RAM,
    ROM,
)
from . import traversal

NES_HEADER_OFFSET = 0x10


class RomError(ValueError):
    """Raised when a ROM file fails structural checks."""


@dataclass
class LedgerLocation:
    """A single trackable item location with its seeded contents."""
    id: str                     # stable machine id, e.g. "level1-item"
    label: str                  # display label, e.g. "Level 1 - Item"
    room: Optional[int]         # dungeon room / OW screen index (None if n/a)
    screen: Optional[int]       # RAM screen-state index (dungeon room or OW screen)
    item: Optional[int]         # ROOT item id from the ROM table
    taken_confident: bool = True
    extra: dict = field(default_factory=dict)


@dataclass
class LevelLedger:
    level: int
    entrance: int
    rooms: list                        # every discovered room index (sorted)
    checks: list                       # LedgerLocation per room with a real item
    heart: Optional[LedgerLocation]    # None for level 9 (no heart) or if not found
    triforce: Optional[LedgerLocation] # None for level 9 (no triforce piece)
    screen_base: int   # $06FF for levels 1-6, $077F for 7-9


@dataclass
class Ledger:
    """Parsed seed data: what the randomizer placed where, per quest grid."""
    rom_path: str
    rom_hash: str                # sha256 of PRG region (identifies the seed)
    z1r_likely: bool
    quest_early: Optional[int]   # 1 or 2
    quest_late: Optional[int]
    levels: dict                 # level int -> LevelLedger
    overworld: dict              # OW location key -> LedgerLocation
    other_ow_screens: dict       # name -> LedgerLocation (start/letter/magical)
    heart_cave_screens: list     # (screen index, verified) pairs
    caves: list                  # raw cave table: [{items: [..3], prices: [..3]}]
    olive: dict = field(default_factory=dict)  # misc ROM facts (requirements)
    dungeon_layout_confident: bool = True  # False if the quest pointers were
        # unrecognized and we fell back to a best-effort guess -- Triforce
        # tracking (reads level_info directly, independent of grid content)
        # stays reliable either way, but Heart/Items scanning depends on
        # reading the right grid and may be wrong for this seed.

    def location_for(self, level: Optional[int], room: Optional[int]) \
            -> Optional[LedgerLocation]:
        """All known locations whose screen-state is the given room index."""
        if level is None or room is None:
            return None
        led = self.levels.get(level)
        if led is None:
            return None
        for loc in led.checks + [led.heart, led.triforce]:
            if loc and loc.room == room:
                return loc
        return None


def parse_header(data: bytes) -> dict:
    if len(data) < 16 or data[0:4] != b"NES\x1a":
        raise RomError("not an iNES NES ROM (.nes) - bad header")
    prg_kb = data[4] * 16
    chr_kb = data[5] * 8
    flags6 = data[6]
    flags7 = data[7]
    mapper = (flags7 & 0xF0) | (flags6 >> 4)
    return {
        "prg_kb": prg_kb,
        "chr_kb": chr_kb,
        "mapper": mapper,
        "mirroring": "vertical" if flags6 & 0x01 else "horizontal",
        "with_trainer": bool(flags6 & 0x04),
    }


def _u8(data: bytes, addr: int) -> int:
    """tetraly convention: addr is the CPU-ish address, file offset = +0x10."""
    return data[NES_HEADER_OFFSET + addr]


def _u16(data: bytes, addr: int) -> int:
    lo = _u8(data, addr)
    hi = _u8(data, addr + 1)
    return (hi << 8) | lo


def _slices(data: bytes, addr: int, n: int) -> bytes:
    return data[NES_HEADER_OFFSET + addr: NES_HEADER_OFFSET + addr + n]


def item_name(item: Optional[int]) -> Optional[str]:
    if item is None:
        return None
    return ITEM_NAMES.get(item, f"Unknown(0x{item:02X})")


def rom_checksum(data: bytes, header: dict) -> str:
    """Hash the PRG region so that the seed identity ignores CHR/header noise."""
    if header["with_trainer"]:
        prg_start = 0x10 + 512
    else:
        prg_start = 0x10
    end = prg_start + header["prg_kb"] * 1024
    return hashlib.sha256(data[prg_start:end]).hexdigest()


class RomReader:
    """Minimal, tetraly-compatible reader over an in-memory .nes file."""

    def __init__(self, data: bytes):
        self.data = data

    def u8(self, addr: int) -> int:
        return _u8(self.data, addr)

    def u16(self, addr: int) -> int:
        return _u16(self.data, addr)

    def slices(self, addr: int, n: int) -> bytes:
        return _slices(self.data, addr, n)

    def level_block(self, is_early: bool, quest: int) -> bytes:
        key = ("levels_1_6" if is_early else "levels_7_9")
        key += "_first_quest" if quest == 1 else "_second_quest"
        return self.slices(ROM[key], 0x300)

    def level_info(self, level: int) -> bytes:
        base = ROM["level_info"] + level * ROM["level_info_stride"]
        return self.slices(base, ROM["level_info_stride"])

    def cave_items(self) -> list:
        out = []
        items = self.slices(ROM["cave_items"], 60)
        prices = self.slices(ROM["cave_prices"], 60)
        for c in range(20):
            out.append({
                "cave": c,
                "items": [b & 0x3F for b in items[c * 3:(c + 1) * 3]],
                "prices": [prices[c * 3 + i] for i in range(3)],
            })
        return out


# ---------------------------------------------------------------- ledger build

def _detect_z1r(reader: RomReader) -> bool:
    """Heuristic: vanilla ROMs hold the default items at the three special OW
    slots (armos=Power Bracelet, coast=Heart Container, white sword cave=
    White Sword).  Any deviation implies a randomized seed."""
    vanilla = (
        reader.u8(ROM["armos_item"]) == 0x14 and
        reader.u8(ROM["coast_item"]) == 0x1A and
        (reader.u8(ROM["white_sword_item"]) & 0x3F) == 0x02
    )
    return not vanilla


def _find_armos_screen(reader: RomReader) -> int:
    """The Armos statue's overworld screen is a direct, stored ROM value
    (confirmed via the community ROM map and cross-checked against real
    gameplay: 0x10CB2 read 0x34/E4 exactly where the player found it, vs the
    0x24/E3 default everywhere else) -- no scanning/heuristics needed."""
    return reader.u8(ROM["armos_screen_addr"])


def _find_coast_screen(reader: RomReader) -> int:
    """Likewise a direct stored value. Unlike Armos, this has not been
    observed to differ from the 0x5F default in any tested seed -- reading
    it directly is a harmless simplification (one less hardcoded constant),
    not a claim that it varies."""
    return reader.u8(ROM["coast_screen_addr"])


def _cave_destination_screens(reader: RomReader, cave_num: int) -> list:
    """Every overworld screen whose CURRENT entrance destination points at
    the given cave number (0-19). Cave Shuffle can move which screen leads
    to which cave, so this must be read fresh per-seed rather than assumed
    fixed -- confirmed via real gameplay: White Sword Cave's actual screen
    differed from the old hardcoded guess in 2 of 3 tested seeds.

    Destination byte encoding (screen-attribute table 2, %DDDDDD.. top 6
    bits): 0x10-0x23 map to real numbered caves 0-19 (dest - 0x10); other
    values are dungeon entrances/specials, not caves, and are skipped.
    """
    ow = reader.slices(ROM["overworld_data"], 0x300)
    table1 = ow[0x80:0x100]
    screens = []
    for screen in range(0x80):
        dest = table1[screen] >> 2
        if 0x10 <= dest <= 0x23 and (dest - 0x10) == cave_num:
            screens.append(screen)
    return screens


def _find_unique_cave_screen(reader: RomReader, cave_num: int, default: int) -> int:
    """For caves confirmed to map to exactly one screen (White Sword, Wood
    Sword): use the scan result if it's unambiguous, otherwise fall back to
    the historical default rather than guess between multiple matches."""
    screens = _cave_destination_screens(reader, cave_num)
    if len(screens) == 1:
        return screens[0]
    return default


def build_ledger(path: str, data: bytes = None) -> Ledger:
    """Parse a .nes file into a Ledger, or raise RomError.

    This is a hard boundary: absolutely anything unexpected about the ROM
    (truncated file, unfamiliar layout/mapper, a randomizer version this
    tracker doesn't understand, corrupted data, etc.) must turn into a plain
    RomError here, never an unhandled crash. Every caller (the live service
    loop, `verify`, `once`) depends on that to keep running RAM-only if the
    ROM can't be understood, instead of taking the whole tool down.
    """
    if data is None:
        with open(path, "rb") as f:
            data = f.read()
    try:
        return _build_ledger_inner(path, data)
    except RomError:
        raise
    except Exception as e:
        raise RomError(f"could not parse ROM ({type(e).__name__}: {e})") from e


def _build_ledger_inner(path: str, data: bytes) -> Ledger:
    header = parse_header(data)
    reader = RomReader(data)
    checksum = rom_checksum(data, header)

    p16 = reader.u16(ROM["pointer_levels_1_6"])
    p79 = reader.u16(ROM["pointer_levels_7_9"])
    q_early = _quest_from_pointer(p16)
    q_late = _quest_from_pointer(p79)
    dungeon_layout_confident = True
    if q_early is None or q_late is None:
        # Unrecognized pointer table (seen on at least one older/different
        # randomizer-version seed) -- rather than refuse the whole ROM, fall
        # back to the 1st-Quest grid address as a best-effort default and
        # flag reduced confidence, instead of a hard failure. level_info
        # (entrance/boss/triforce room *numbers*, read separately) has been
        # verified reliable regardless of this, so Triforce tracking in
        # particular should still work; Heart/Items scanning may not.
        q_early = q_early or 1
        q_late = q_late or 1
        dungeon_layout_confident = False

    early_grid = reader.level_block(True, q_early)
    late_grid = reader.level_block(False, q_late)

    cave_items_raw = reader.cave_items()

    is_z1r_format = traversal.is_z1r_level_format(
        [reader.level_info(lvl) for lvl in range(10)],
        ROM["stairway_list_offset"],
    )

    levels = {}
    for level in range(1, 10):
        grid = early_grid if level <= 6 else late_grid
        screen_base = RAM["dungeon_early"] if level <= 6 else RAM["dungeon_late"]
        levels[level] = _build_level(reader, level, grid, screen_base, is_z1r_format)

    armos_screen = _find_armos_screen(reader)
    coast_screen = _find_coast_screen(reader)
    # White Sword Cave = cave slot 2 -- confirmed a clean, unique match (no
    # ambiguity seen in testing), unlike the other named caves below.
    white_sword_screen = _find_unique_cave_screen(reader, 2, OW_SCREENS["white_sword"])

    overworld = {}
    ow = {
        "white_sword": (ROM["white_sword_item"], white_sword_screen),
        "armos":       (ROM["armos_item"], armos_screen),
        "coast":       (ROM["coast_item"], coast_screen),
    }
    for key, (rom_addr, screen_offset) in ow.items():
        item = reader.u8(rom_addr) & 0x3F
        overworld[key] = LedgerLocation(
            id="ow-" + key,
            label={"white_sword": "White Sword Cave",
                   "armos": "Armos Statue",
                   "coast": "Coast"}[key],
            room=screen_offset,
            screen=RAM["ow_screens"] + screen_offset,
            item=item if item not in NO_ITEM_IDS and item != 0 else None,
        )

    # Wood Sword Cave = cave 0, also a clean unique match. Magical Sword (3)
    # and Letter (8) showed 0 or multiple matches in testing -- ambiguous,
    # so keep the historical default for those two rather than guess wrong;
    # they're already marked taken_confident=False below.
    other_ow_screen = {
        "start_sword_cave": _find_unique_cave_screen(reader, 0, OW_SCREENS["start_sword_cave"]),
        "magical_sword": OW_SCREENS["magical_sword"],
        "letter_cave": OW_SCREENS["letter_cave"],
    }
    other_ow = {}
    for key in ("start_sword_cave", "magical_sword", "letter_cave"):
        screen_offset = other_ow_screen[key]
        other_ow[key] = LedgerLocation(
            id="ow-" + key,
            label=key.replace("_", " ").title(),
            room=screen_offset,
            screen=RAM["ow_screens"] + screen_offset,
            item=None,
            taken_confident=False,
        )

    # Heart-container caves: dynamically found (cave slot 1 = "Red Potion or
    # Heart Container"), not a hardcoded vanilla-position list -- Cave
    # Shuffle can move which screens lead there, same mechanism as White
    # Sword Cave above. Coast is folded in too (tracked via its own direct
    # address, not the numbered-cave system) if it currently holds a heart.
    # This can occasionally over-count (a handful of these screens can be
    # inert leftover data for an inactive alternate overworld layout rather
    # than real locations), but that's a much smaller error than the
    # previous hardcoded-vanilla-position bug (false "taken" on a location
    # that never held a heart this seed, and silently missing the real one).
    heart_cave_screens_found = _cave_destination_screens(reader, 1)
    coast_item = reader.u8(ROM["coast_item"]) & 0x3F
    if coast_item == 0x1A and coast_screen not in heart_cave_screens_found:
        heart_cave_screens_found.append(coast_screen)

    return Ledger(
        rom_path=path,
        rom_hash=checksum,
        z1r_likely=_detect_z1r(reader),
        quest_early=q_early,
        quest_late=q_late,
        levels=levels,
        overworld=overworld,
        other_ow_screens=other_ow,
        heart_cave_screens=[(s, True) for s in sorted(heart_cave_screens_found)],
        caves=cave_items_raw,
        olive=_read_requirements(reader),
        dungeon_layout_confident=dungeon_layout_confident,
    )


def _quest_from_pointer(p: int) -> Optional[int]:
    grid = POINTER_TO_GRID.get(p)
    if grid is None:
        return None
    return 1 if p in (0x8700, 0x8A00) else 2


def _build_level(reader: "RomReader", level: int, grid: bytes,
                  screen_base: int, is_z1r_format: bool) -> LevelLedger:
    """Discover every room belonging to this level (via wall-connectivity
    traversal from its ROM-stored Entrance Room -- quest/shape agnostic, no
    hardcoded room table), then classify what's found:

      - triforce: read directly from the ROM's own "Triforce Room (for
        Compass)" field. The reference randomizer updates this field itself
        whenever it shuffles the Triforce, so it is always correct.
      - heart: whichever discovered room actually holds a Heart Container.
        NOT assumed to be the boss's room -- some seeds have zero or several
        enemies that could be called a "boss", and the heart can be shuffled
        anywhere, so it must be found by scanning, not inferred.
      - checks: every other discovered room that holds a real item (i.e.
        everything except the heart/triforce rooms, which get their own
        dedicated indicators, and except empty-room sentinel values).
    """
    info = reader.level_info(level)
    entrance = info[ROM["start_room_offset"]]
    triforce_room = info[ROM["triforce_room_offset"]]
    stairway_list = traversal.read_stairway_list(
        info, ROM["stairway_list_offset"], level, is_z1r_format)

    rooms = traversal.discover_level_rooms(grid, stairway_list, entrance)

    def loc(key: str, label: str, room: int) -> LedgerLocation:
        item = traversal.room_item(grid, room)
        return LedgerLocation(
            id=f"level{level}-{key}",
            label=f"Level {level} - {label}",
            room=room,
            screen=screen_base + room,
            item=item if item not in DUNGEON_NO_ITEM_IDS else None,
        )

    has_triforce = level <= LEVELS_WITH_HEART  # levels 1-8 only, not 9
    triforce = loc("triforce", "Triforce", triforce_room) if has_triforce else None

    heart = None
    if has_triforce:  # same 1-8 rule: level 9 has no Heart Container either
        heart_room = next(
            (r for r in sorted(rooms) if traversal.room_item(grid, r) == 0x1A),
            None,
        )
        if heart_room is not None:
            heart = loc("heart", "Heart", heart_room)

    # Only major items count toward "checks" -- keys, bombs, rupees, compass,
    # and map are deliberately not tracked (per explicit scope: minor pickups
    # don't matter for "did I leave something behind", only major items do).
    exclude = {triforce.room if triforce else None, heart.room if heart else None}
    checks = []
    for i, room in enumerate(sorted(rooms)):
        if room in exclude:
            continue
        item = traversal.room_item(grid, room)
        if item in DUNGEON_NO_ITEM_IDS or item not in MAJOR_ITEMS:
            continue
        checks.append(LedgerLocation(
            id=f"level{level}-check{i}",
            label=f"Level {level} - Item",
            room=room,
            screen=screen_base + room,
            item=item,
        ))

    return LevelLedger(
        level=level,
        entrance=entrance,
        rooms=sorted(rooms),
        checks=checks,
        heart=heart,
        triforce=triforce,
        screen_base=screen_base,
    )


def _read_requirements(reader: RomReader) -> dict:
    return {
        "triforce_required": reader.u8(ROM["triforce_requirement"]),
        "white_sword_hearts": reader.u8(ROM["white_sword_hearts"]) // 0x10 + 1,
        "magical_sword_hearts": reader.u8(ROM["magical_sword_hearts"]) // 0x10 + 1,
    }


def dump_ledger(ledger: Ledger) -> dict:
    """Human/debug friendly view of the ledger (also used by `verify`)."""
    out = {
        "rom": ledger.rom_path,
        "romHash": ledger.rom_hash,
        "z1rLikely": ledger.z1r_likely,
        "quest": {"early": ledger.quest_early, "late": ledger.quest_late},
        "levels": {},
        "overworld": {},
        "heartCaveScreens": [s for s, _ in ledger.heart_cave_screens],
        "requirements": ledger.olive,
    }
    for level, led in ledger.levels.items():
        out["levels"][str(level)] = {
            "entrance": led.entrance,
            "roomCount": len(led.rooms),
            "rooms": led.rooms,
            "checks": [_dump_loc(c) for c in led.checks],
            "heart": _dump_loc(led.heart),
            "triforce": _dump_loc(led.triforce),
        }
    for key, loc in ledger.overworld.items():
        out["overworld"][key] = _dump_loc(loc)
    return out


def _dump_loc(loc: Optional[LedgerLocation]) -> Optional[dict]:
    if loc is None:
        return None
    return {
        "id": loc.id,
        "label": loc.label,
        "room": loc.room,
        "screen": loc.screen,
        "item": loc.item,
        "itemName": item_name(loc.item),
    }