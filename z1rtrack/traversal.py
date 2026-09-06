"""Dungeon room-graph traversal.

Determines which of the 128 shared room-grid slots actually belong to a
given level, by starting at that level's Entrance Room (a per-seed ROM
field, not a guess) and following wall connectivity outward -- the same
approach the reference randomizer itself uses to enumerate a level's rooms.

This is quest/shape agnostic by construction: it only ever reads the wall
bytes actually present in the ROM for whatever layout was generated (1st
Quest, 2nd Quest, Mixed, or fully procedural Shapes), so it does not depend
on any hardcoded per-level room table.

Room byte layout (6 planes x 128 rooms), verified against
http://www.bwass.org/romhack/zelda1/zelda1bank6.txt and the tetraly/
zelda-randomizer reference implementation:
    plane 0: top wall (bits 7-5) / bottom wall (bits 4-2) / palette0 (1-0)
             -- OR, if this room IS an item staircase/transport staircase,
             bits 6-0 are the LEFT exit room number instead.
    plane 1: left wall (bits 7-5) / right wall (bits 4-2) / palette1 (1-0)
             -- OR, for staircase rooms, bits 6-0 are the RIGHT exit room.
    plane 2: enemy code (low 6 bits) + high-bit extension from plane 3 bit 7
    plane 3: room type (low 6 bits) + movable-block flag (bit 6) + enemy ext (bit 7)
    plane 4: item code (low 5 bits)
    plane 5: enemy drop-bit flags
"""
from __future__ import annotations

from typing import Iterable, List, Set

SOLID_WALL = 1
ITEM_STAIRCASE = 0x3F
TRANSPORT_STAIRCASE = 0x3E
ROOM_TABLE_SIZE = 0x80


def room_type(grid: bytes, room: int) -> int:
    return grid[3 * ROOM_TABLE_SIZE + room] & 0x3F


def room_item(grid: bytes, room: int) -> int:
    return grid[4 * ROOM_TABLE_SIZE + room] & 0x1F


def _staircase_exits(grid: bytes, stair_room: int):
    rtype = room_type(grid, stair_room)
    b0 = grid[0 * ROOM_TABLE_SIZE + stair_room]
    b1 = grid[1 * ROOM_TABLE_SIZE + stair_room]
    if rtype == ITEM_STAIRCASE:
        return [b0 & 0x7F]
    if rtype == TRANSPORT_STAIRCASE:
        return [b0 & 0x7F, b1 & 0x7F]
    return []


def discover_level_rooms(grid: bytes, stairway_list: Iterable[int],
                          entrance_room: int) -> Set[int]:
    """Return the set of room-grid indices reachable from entrance_room.

    stairway_list: the level's raw "Stairway Data" room numbers (from
    level_info, 0xFF-terminated in the ROM, already filtered by the caller).
    """
    # Map: regular room -> the staircase-type room that connects to it. A
    # staircase room's own exits are defined by explicit fields (plane 0/1),
    # not by wall-following, so we resolve this once up front.
    staircase_of = {}
    for stair_room in stairway_list:
        for exit_room in _staircase_exits(grid, stair_room):
            staircase_of[exit_room] = stair_room

    visited: Set[int] = set()
    stack: List[int] = [entrance_room]
    while stack:
        room = stack.pop()
        if room in visited or not (0 <= room < ROOM_TABLE_SIZE):
            continue
        visited.add(room)

        rtype = room_type(grid, room)
        if rtype == ITEM_STAIRCASE:
            continue  # dead end
        if rtype == TRANSPORT_STAIRCASE:
            stack.extend(_staircase_exits(grid, room))
            continue

        b0 = grid[0 * ROOM_TABLE_SIZE + room]
        b1 = grid[1 * ROOM_TABLE_SIZE + room]
        north = (b0 >> 5) & 0x07
        south = (b0 >> 2) & 0x07
        west = (b1 >> 5) & 0x07
        east = (b1 >> 2) & 0x07
        if north != SOLID_WALL:
            stack.append(room - 0x10)
        if south != SOLID_WALL:
            stack.append(room + 0x10)
        if west != SOLID_WALL:
            stack.append(room - 1)
        if east != SOLID_WALL:
            stack.append(room + 1)

        if room in staircase_of:
            stack.append(staircase_of[room])

    return visited


def is_z1r_level_format(level_infos: List[bytes], stairway_list_offset: int) -> bool:
    """Detect whether the ROM's level_info blocks carry the randomizer's
    extra trailing "entrance direction" byte immediately after the real
    stairway room list (see read_stairway_list). Matches tetraly/
    zelda-randomizer's own is_z1r check: true iff the last byte of every
    level's 10-byte stairway window is a small direction code (0-4)."""
    for info in level_infos:
        last = info[stairway_list_offset + 9]
        if last not in range(0, 5):
            return False
    return True


def read_stairway_list(level_info: bytes, stairway_list_offset: int,
                        level_num: int, is_z1r: bool = False) -> List[int]:
    """Parse the 0xFF-terminated stairway room list from a level_info block.

    Two documented quirks handled here:
      - Vanilla 1st-Quest Level 3 omits its one stairway room entirely; it
        must be hardcoded (room 0x0F) or the traversal misses part of the
        dungeon (see tetraly/zelda-randomizer, data_table.py).
      - Randomized ROMs append one extra byte right after the real list: an
        "entrance direction" code, NOT a room number. If left in, it gets
        fed into the traversal as a bogus staircase room, which can corrupt
        connectivity for other rooms depending on what that byte's value
        coincidentally decodes to. Must be popped off when is_z1r is true.
    """
    raw = level_info[stairway_list_offset:stairway_list_offset + 10]
    rooms = [v for v in raw if v != 0xFF]
    if is_z1r and rooms:
        rooms.pop()
    if level_num == 3 and not rooms:
        rooms = [0x0F]
    return rooms
