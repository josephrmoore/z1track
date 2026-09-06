"""Builds a synthetic, deterministic Z1R layout .nes in memory for tests.

The randomizer data tables live at fixed file offsets (= address + 0x10).
We patch exactly the bytes the real reader consults.

Each level gets a small, fully-enclosed 4-room mini-dungeon (entrance -> heart
-> item -> triforce, connected eastward) so the real wall-connectivity
traversal engine has bounded, deterministic data to discover -- matching how
real ROMs work (solid walls by default; specific doors opened between real
rooms), rather than the old approach of writing item bytes directly into a
hardcoded room list with no wall data at all.
"""

from __future__ import annotations

from z1rtrack.items import ROM

SOLID = 1  # WallType.SOLID_WALL
ALL_SOLID_BYTE = (SOLID << 5) | (SOLID << 2)  # both directions in a byte = solid


class SeedLayout:
    def __init__(self):
        self.grid_early = bytearray(0x300)
        self.grid_late = bytearray(0x300)
        self._init_walls(self.grid_early)
        self._init_walls(self.grid_late)
        self.cave_items = bytearray(60)
        self.cave_prices = bytearray(60)
        self.ow_items = {
            "white_sword": 0x02,
            "armos": 0x14,
            "coast": 0x1A,
        }
        # level -> {"entrance": int, "triforce_room": int}, filled in by
        # _make_level_dungeon(); consumed when writing level_info.
        self.level_meta = {}

        for level in range(1, 10):
            self._make_level_dungeon(level)

    def _init_walls(self, grid: bytearray) -> None:
        for room in range(0x80):
            grid[0 * 0x80 + room] = ALL_SOLID_BYTE
            grid[1 * 0x80 + room] = ALL_SOLID_BYTE

    def _grid_for(self, level: int) -> bytearray:
        return self.grid_early if level <= 6 else self.grid_late

    def _open_east(self, grid: bytearray, room: int) -> None:
        # byte1 bits [4:2] = right/east wall type; clear to 0 (OPEN_DOOR)
        grid[1 * 0x80 + room] &= ~(0x07 << 2) & 0xFF

    def _make_level_dungeon(self, level: int) -> None:
        """entrance -> heart -> item -> triforce, four rooms, all eastward.
        Levels 7-9 reuse the same room numbers as 1-3 (fine: separate grid).
        Level 9 gets no heart/triforce rooms (matches vanilla: L9 has neither).
        """
        grid = self._grid_for(level)
        base = ((level - 1) % 6 + 1) * 0x10  # 0x10, 0x20, ... 0x60
        entrance, heart_room, item_room, triforce_room = base, base + 1, base + 2, base + 3

        self._open_east(grid, entrance)
        self._open_east(grid, heart_room)
        self._open_east(grid, item_room)

        self.level_meta[level] = {
            "entrance": entrance,
            "heart_room": heart_room,
            "item_room": item_room,
            "triforce_room": triforce_room if level <= 8 else None,
        }

    # ---- content setters (write the item byte, plane 4) -------------------

    def set_item(self, level: int, item: int) -> None:
        grid = self._grid_for(level)
        room = self.level_meta[level]["item_room"]
        grid[4 * 0x80 + room] = item

    def set_heart(self, level: int, item: int = 0x1A) -> None:
        grid = self._grid_for(level)
        room = self.level_meta[level]["heart_room"]
        grid[4 * 0x80 + room] = item

    def set_triforce(self, level: int, item: int = 0x1B) -> None:
        room = self.level_meta[level]["triforce_room"]
        if room is None:
            return
        grid = self._grid_for(level)
        grid[4 * 0x80 + room] = item

    def set_ow(self, key: str, item: int) -> None:
        self.ow_items[key] = item


def build_rom(layout: "SeedLayout | None" = None) -> bytes:
    layout = layout or SeedLayout()

    # header: iNES, 128 KB PRG (mapper 0, horizontal mirroring)
    data = bytearray(0x10 + 128 * 1024)
    data[0:4] = b"NES\x1a"
    data[4] = 8          # PRG in 16KB banks
    data[5] = 0          # CHR
    data[6] = 0x00
    data[7] = 0x00

    def u16(addr: int, val: int) -> None:
        file = 0x10 + addr
        data[file] = val & 0xFF
        data[file + 1] = (val >> 8) & 0xFF

    # quest pointers -> 1st-quest grids
    u16(ROM["pointer_levels_1_6"], 0x8700)
    u16(ROM["pointer_levels_7_9"], 0x8A00)

    # grids
    data[0x10 + ROM["levels_1_6_first_quest"]:0x10 + ROM["levels_1_6_first_quest"] + 0x300] = layout.grid_early
    data[0x10 + ROM["levels_7_9_first_quest"]:0x10 + ROM["levels_7_9_first_quest"] + 0x300] = layout.grid_late

    # per-level info blocks: entrance room, triforce room, stairway list (none)
    for level in range(1, 10):
        meta = layout.level_meta[level]
        base = 0x10 + ROM["level_info"] + level * ROM["level_info_stride"]
        data[base + ROM["start_room_offset"]] = meta["entrance"]
        data[base + ROM["triforce_room_offset"]] = meta["triforce_room"] or 0
        stair_off = base + ROM["stairway_list_offset"]
        data[stair_off:stair_off + 10] = bytes([0xFF] * 10)  # no staircases

    # cave items / prices
    data[0x10 + ROM["cave_items"]:0x10 + ROM["cave_items"] + 60] = layout.cave_items
    data[0x10 + ROM["cave_prices"]:0x10 + ROM["cave_prices"] + 60] = layout.cave_prices

    # overworld specials
    data[0x10 + ROM["white_sword_item"]] = layout.ow_items["white_sword"]
    data[0x10 + ROM["armos_item"]] = layout.ow_items["armos"]
    data[0x10 + ROM["coast_item"]] = layout.ow_items["coast"]

    return bytes(data)


def vanilla_layout() -> SeedLayout:
    """A small fully-enclosed test dungeon per level: one major item, one
    Heart Container, one Triforce (levels 1-8 only)."""
    layout = SeedLayout()
    per_level_item = {
        1: 0x0A,   # Bow
        2: 0x10,   # Magical Rod
        3: 0x04,   # Bait (not major -- deliberately excluded from checks by test)
        4: 0x0C,   # Raft
        5: 0x1D,   # Wooden Boomerang
        6: 0x1D,   # Wooden Boomerang
        7: 0x1C,   # Magical Shield
        8: 0x12,   # Blue Ring
        9: 0x0B,   # Magical Key
    }
    for level, item in per_level_item.items():
        layout.set_item(level, item)
    for level in range(1, 9):
        layout.set_heart(level)
        layout.set_triforce(level)
    return layout
