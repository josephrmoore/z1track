"""Decodes a full 2 KB NES RAM snapshot ($0000-$07FF) into the live game
state: inventory, hearts, triforce, per-screen "taken" bits and context.

The snapshot is the raw truth for "what has been collected where".  Together
with the static ROM ledger it fully reconstructs the tracker on any cold
restart -- no event history required.
"""

from __future__ import annotations

from typing import Optional

from .items import FLAG_ITEMS, RAM, TIER_ITEMS

RAM_SIZE = 0x0800
RAM_HEX_CHARS = RAM_SIZE * 2

TRIFORCE_PIECES = 8


class RamError(ValueError):
    pass


def hex_to_ram(hex_str: str) -> bytes:
    """Parse the 4096-hex-char payload sent by the Lua connectors."""
    s = hex_str.strip()
    if len(s) != RAM_HEX_CHARS:
        raise RamError(f"expected {RAM_HEX_CHARS} hex chars, got {len(s)}")
    try:
        return bytes.fromhex(s)
    except ValueError as e:
        raise RamError(f"bad hex: {e}")


def is_playing(ram: bytes) -> bool:
    return ram[RAM["game_mode"]] == 0x05


def decode_inventory(ram: bytes) -> dict:
    """In-memory contact structure; kept flat for the display."""
    inv = {}
    for key, tiers in TIER_ITEMS.items():
        value = ram[RAM[key]]
        name = tiers.get(value)
        inv[key] = {
            "value": value,
            "have": value > 0,
            "name": name,
        }
    for key, (_name, _) in FLAG_ITEMS.items():
        value = ram[RAM[key]]
        inv[key] = {"value": value, "have": value > 0}

    inv["bombs"] = {"value": ram[RAM["bombs"]]}
    inv["rupees"] = {"value": ram[RAM["rupees"]]}
    inv["keys"] = {"value": ram[RAM["keys"]]}
    inv["max_bombs"] = {"value": ram[RAM["max_bombs"]]}

    inv["boomerang"] = {"value": ram[RAM["boomerang"]], "have": ram[RAM["boomerang"]] > 0}
    inv["mag_boomerang"] = {
        "value": ram[RAM["mag_boomerang"]],
        "have": ram[RAM["mag_boomerang"]] > 0,
    }
    inv["mag_shield"] = {"value": ram[RAM["mag_shield"]], "have": ram[RAM["mag_shield"]] > 0}

    inv["compass"] = {
        "value": ram[RAM["compass"]],
        "have": ram[RAM["compass"]] > 0,
        "haveLevels": [bool(ram[RAM["compass"]] & (1 << i)) for i in range(8)],
    }
    inv["map"] = {
        "value": ram[RAM["map"]],
        "have": ram[RAM["map"]] > 0,
        "haveLevels": [bool(ram[RAM["map"]] & (1 << i)) for i in range(8)],
    }
    inv["compass_9"] = {"value": ram[RAM["compass_9"]], "have": ram[RAM["compass_9"]] > 0}
    inv["map_9"] = {"value": ram[RAM["map_9"]], "have": ram[RAM["map_9"]] > 0}
    inv["letter"] = {"value": ram[RAM["letter"]], "have": ram[RAM["letter"]] > 0}
    return inv


def decode_hearts(ram: bytes) -> dict:
    hc = ram[RAM["hearts"]]
    containers = (hc >> 4) + 1
    filled = hc & 0x0F
    partial = ram[RAM["partial_heart"]]
    partial_val = 1.0 if partial >= 0x80 else (0.5 if partial > 0 else 0.0)
    return {
        "max": containers,
        "filled": filled,
        "partial": partial_val,
        "total": filled + partial_val,
        "containersCollected": max(0, containers - 3),
    }


def decode_triforce(ram: bytes) -> dict:
    bits = ram[RAM["triforce"]]
    pieces = [bool(bits & (1 << i)) for i in range(TRIFORCE_PIECES)]
    return {
        "count": sum(pieces),
        "pieces": pieces,
    }


def decode_screens(ram: bytes) -> dict:
    """The three 128-byte screen-state blocks.  Per-byte bit 0x10 = item taken
    on that screen/room (verified in the Archipelago client)."""
    ow = ram[RAM["ow_screens"]:RAM["ow_screens"] + RAM["ow_screens_len"]]
    early = ram[RAM["dungeon_early"]:RAM["dungeon_early"] + RAM["dungeon_screens_len"]]
    late = ram[RAM["dungeon_late"]:RAM["dungeon_late"] + RAM["dungeon_screens_len"]]
    return {
        "overworld": list(ow),
        "dungeonEarly": list(early),
        "dungeonLate": list(late),
    }


def decode_secrets(ram: bytes) -> dict:
    """Pure-RAM overworld secrets, flat (no region breakdown -- no trustworthy
    screen-to-region table is available; a table an AI produced for this was
    checked against the real source of the two established community
    trackers and did not match anything there, so it was not used).

    Per the documented overworld screen-state byte (%Ss-I-EEE):
      S (0x80) = secret discovered on this screen
      I (0x10) = item obtained on this screen
    "Found" = S set. "Left behind" = S set but I not set (found the secret,
    never picked up what was there).
    """
    base = RAM["ow_screens"]
    length = RAM["ow_screens_len"]
    screens = ram[base:base + length]
    found = sum(1 for b in screens if b & 0x80)
    taken_count = sum(1 for b in screens if (b & 0x80) and (b & 0x10))
    return {
        "found": found,
        "leftBehind": found - taken_count,
    }


def decode_enemy_kill_counter(ram: bytes) -> dict:
    """Live "Nth enemy has the bomb" counter ($0050): counts enemies killed
    without taking damage, resets to 0 once it reaches 10."""
    return {"count": ram[0x0050], "resetAt": 10}


def taken(ram: Optional[bytes], screen: Optional[int]) -> Optional[bool]:
    if ram is None or screen is None:
        return None
    if 0x067F <= screen <= 0x06FE:
        return bool(ram[screen] & 0x10)
    if 0x06FF <= screen <= 0x07FE:
        return bool(ram[screen] & 0x10)
    return None


def decode(ram: bytes) -> dict:
    if len(ram) < RAM_SIZE:
        raise RamError(f"short snapshot: {len(ram)} bytes")
    return {
        "playing": is_playing(ram),
        "gameMode": ram[RAM["game_mode"]],
        "level": ram[RAM["current_level"]],
        "room": ram[RAM["current_room"]],
        "inventory": decode_inventory(ram),
        "hearts": decode_hearts(ram),
        "triforce": decode_triforce(ram),
        "secrets": decode_secrets(ram),
        "enemyKillCounter": decode_enemy_kill_counter(ram),
        "screens": decode_screens(ram),
        "takeAny": ram[RAM["take_any"]],
        "shopSlots": {
            "left": ram[RAM["shop_slot_left"]],
            "middle": ram[RAM["shop_slot_mid"]],
            "right": ram[RAM["shop_slot_right"]],
        },
    }