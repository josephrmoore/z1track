"""Item and location tables for Zelda 1 + Z1R.

Sources:
  - tetraly/zelda-randomizer (open reference implementation of Z1R):
      rom_reader.py, data_table.py, constants.py
  - Archipelago TLoZ connector + Locations.py (verified working memory client)

Item IDs are the ROM code values (same table the randomizer writes and the
Address Space protocol uses).  Room numbers are indices into the per-grid
128-room level data / screen-state arrays (see REFERENCE.md).
"""


# --- ROM item codes ---------------------------------------------------------
ITEM_NAMES = {
    0x00: "Bombs",
    0x01: "Wood Sword",
    0x02: "White Sword",
    0x03: "Magical Sword",
    0x04: "Bait",
    0x05: "Recorder",
    0x06: "Blue Candle",
    0x07: "Red Candle",
    0x08: "Wood Arrows",
    0x09: "Silver Arrows",
    0x0A: "Bow",
    0x0B: "Magical Key",
    0x0C: "Raft",
    0x0D: "Stepladder",
    0x0E: "Triforce of Power",
    0x0F: "Five Rupees",
    0x10: "Magical Rod",
    0x11: "Book of Magic",
    0x12: "Blue Ring",
    0x13: "Red Ring",
    0x14: "Power Bracelet",
    0x15: "Letter",
    0x16: "Compass",
    0x17: "Map",
    0x18: "Rupee",
    0x19: "Key",
    0x1A: "Heart Container",
    0x1B: "Triforce",
    0x1C: "Magical Shield",
    0x1D: "Wooden Boomerang",
    0x1E: "Magical Boomerang",
    0x1F: "Blue Potion",
    0x20: "Red Potion",
    0x21: "Clock",
    0x22: "Recovery Heart",
    0x23: "Fairy",
    0x24: "Fairy (stationary)",
}

# Item IDs that can validly report "empty"/"no item" for a room byte.
NO_ITEM_IDS = frozenset({0x1F, 0x3F})

# Dungeon room-grid item byte sentinels for "this room has no placed item".
# 0x03 is aliased Item.NO_ITEM/Item.MAGICAL_SWORD in the reference randomizer
# (real Magical Sword only ever lives in its own overworld cave, never a
# dungeon room byte); 0x0E is Item.TRIFORCE_OF_POWER, Ganon's own sentinel,
# distinct from the 8 collectible Item.TRIFORCE (0x1B) pieces.
DUNGEON_NO_ITEM_IDS = frozenset({0x03, 0x0E})

# Items that are displayed as boxes inside a dungeon in the tracker UI.
# (Compass/Map are separate accessory fields, kept out of the shuffle boxes.)
MAJOR_ITEMS = frozenset({
    0x01, 0x02, 0x03, 0x05, 0x06, 0x07, 0x08, 0x09, 0x0A, 0x0B, 0x0C, 0x0D,
    0x0E, 0x10, 0x11, 0x12, 0x13, 0x14, 0x1A, 0x1B, 0x1C, 0x1D, 0x1E,
})


# --- ROM addresses (tetraly convention: file offset = 0x10 + value below) ---
ROM = {
    "overworld_data":         0x18400,
    "levels_1_6_first_quest": 0x18700,
    "levels_7_9_first_quest": 0x18A00,
    "levels_1_6_second_quest":0x18D00,
    "levels_7_9_second_quest":0x19000,
    "level_info":             0x19300,  # + level * 0xFC
    "level_info_stride":      0xFC,
    "start_room_offset":      0x2F,   # Entrance Room (per-seed, authoritative)
    "triforce_room_offset":   0x30,   # Triforce Room (for Compass) -- updated
                                       # by the randomizer itself whenever the
                                       # Triforce is shuffled, so this is
                                       # always correct regardless of flags.
    "boss_room_offset":       0x3E,   # informational only -- NOT used to
                                       # infer Heart Container location; some
                                       # seeds have zero or multiple "boss"
                                       # rooms and it's unrelated to the heart.
    "stairway_list_offset":   0x34,   # up to 10 room numbers, 0xFF-terminated
    "pointer_overworld":      0x18000,
    "pointer_levels_1_6":     0x18002,
    "pointer_levels_7_9":     0x1800E,
    "cave_items":             0x18600,  # 20 caves x 3 item bytes
    "cave_prices":            0x1863C,  # 20 caves x 3 price bytes
    "white_sword_item":       0x18607,
    "armos_item":             0x10CF5,
    "coast_item":             0x1788A,
    "triforce_requirement":   0x5F17,
    "white_sword_hearts":     0x48FD,
    "magical_sword_hearts":   0x4906,
    # Direct authoritative pointers to *which overworld screen* holds these
    # two specials (neither is fixed -- confirmed both via real gameplay and
    # via the community ROM map; previously wrongly assumed fixed/guessed).
    "armos_screen_addr":      0x10CB2,
    "coast_screen_addr":      0x1789A,
}

# --- Quest pointer values -> grid base ---------------------------------------
POINTER_TO_GRID = {
    0x8700: ROM["levels_1_6_first_quest"],
    0x8D00: ROM["levels_1_6_second_quest"],
    0x8A00: ROM["levels_7_9_first_quest"],
    0x9000: ROM["levels_7_9_second_quest"],
}

LEVELS_WITH_HEART = 8  # levels 1-8 each have one heart; level 9 does not.


# --- Overworld screen state offsets (index into $067F-$06FE, verified AP) ---
# Armos and Coast are NOT here -- both are read directly from their own
# stored ROM addresses per-seed (rom.py: _find_armos_screen/_find_coast_screen),
# not assumed fixed.
OW_SCREENS = {
    "start_sword_cave": 0x77,
    "white_sword":      0x0A,
    "magical_sword":    0x21,
    "letter_cave":      0x0E,
}

# NOTE: heart-container cave screens are no longer a hardcoded list here --
# Cave Shuffle can move which screen leads to the "cave slot 1" (Old Man: Red
# Potion or Heart Container) location(s), so they're found dynamically per
# seed at ledger-build time (see rom.py: _cave_destination_screens(reader, 1)).
# The original vanilla-position discovery (M3=0x2C, P3=0x2F, H5=0x47,
# P6/coast=0x5F, L8=0x7B) was verified against real gameplay and is what
# validated this same mechanism before generalizing it.
# The tracker only ever reports the *count* of these cleared, never which.
#
# NOTE: the RAM-only build (this branch) dropped Overworld Heart Container
# tracking entirely (not MVP) -- it isn't reused below.


# --- RAM addresses (NES work RAM) --------------------------------------------
RAM = {
    "sword":            0x0657, "bombs":        0x0658, "arrow":        0x0659,
    "bow":              0x065A, "candle":       0x065B, "recorder":     0x065C,
    "bait":             0x065D, "potion":       0x065E, "rod":          0x065F,
    "raft":             0x0660, "book":         0x0661, "ring":         0x0662,
    "ladder":           0x0663, "magical_key":  0x0664, "bracelet":     0x0665,
    "letter":           0x0666, "compass":      0x0667, "map":          0x0668,
    "compass_9":        0x0669, "map_9":        0x066A, "clock":        0x066C,
    "rupees":           0x066D, "keys":         0x066E, "hearts":       0x066F,
    "partial_heart":    0x0670, "triforce":     0x0671,
    "boomerang":        0x0674, "mag_boomerang": 0x0675, "mag_shield":   0x0676,
    "take_any":         0x0678,
    "shop_slot_left":   0x0628, "shop_slot_mid": 0x0629, "shop_slot_right": 0x062A,
    "max_bombs":        0x067C,
    "game_mode":        0x0012, "current_level": 0x0010, "current_room": 0x00EB,
    # screen-state blocks
    "ow_screens":       0x067F, "ow_screens_len": 128,
    "dungeon_early":    0x06FF, "dungeon_late":  0x077F,
    "dungeon_screens_len": 128,
}

# Inventory byte names in the order they appear in the data; each entry maps a
# canonical key to (ram key, item value -> display behaviour).
SWORD_TIERS = {0: None, 1: "Wood Sword", 2: "White Sword", 3: "Magical Sword"}
ARROW_TIERS = {0: None, 1: "Wood Arrows", 2: "Silver Arrows"}
CANDLE_TIERS = {0: None, 1: "Blue Candle", 2: "Red Candle"}
POTION_TIERS = {0: None, 1: "Blue Potion", 2: "Red Potion"}
RING_TIERS = {0: None, 1: "Blue Ring", 2: "Red Ring"}

TIER_ITEMS = {
    "sword": SWORD_TIERS, "arrow": ARROW_TIERS, "candle": CANDLE_TIERS,
    "potion": POTION_TIERS, "ring": RING_TIERS,
}

FLAG_ITEMS = {
    "bow": ("Bow", "bow"), "recorder": ("Recorder", "recorder"),
    "bait": ("Bait", "bait"), "rod": ("Magical Rod", "rod"),
    "raft": ("Raft", "raft"), "book": ("Book of Magic", "book"),
    "ladder": ("Stepladder", "ladder"), "magical_key": ("Magical Key", "magical_key"),
    "bracelet": ("Power Bracelet", "bracelet"), "letter": ("Letter", "letter"),
    "boomerang": ("Wooden Boomerang", "boomerang"), "mag_boomerang": ("Magical Boomerang", "mag_boomerang"),
    "mag_shield": ("Magical Shield", "mag_shield"), "clock": ("Clock", "clock"),
}