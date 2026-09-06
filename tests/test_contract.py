"""Contract smoke test: build a synthetic seed, a fake RAM snapshot, and verify
that the produced tracker_state.json tells the expected story end to end.
"""

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests import rom_builder
from z1rtrack import ram as ramlib
from z1rtrack import rom as romlib
from z1rtrack import state as statelib

DUNGEON_EARLY_BASE = 0x06FF  # RAM["dungeon_early"]


def fake_ram(items: dict, screens: dict | None = None) -> bytes:
    hexs = ["00"] * (0x800)
    for addr, val in items.items():
        hexs[addr] = f"{val:02x}"
    if screens:
        for addr, byte in screens.items():
            hexs[addr] = f"{byte:02x}"
    return ramlib.hex_to_ram("".join(hexs))


class TrackerContractTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.rom_path = os.path.join(self.dir, "seed.nes")
        layout = rom_builder.vanilla_layout()
        with open(self.rom_path, "wb") as f:
            f.write(rom_builder.build_rom(layout))
        self.ledger = romlib.build_ledger(self.rom_path)

    def test_ledger_structure(self):
        self.assertEqual(self.ledger.quest_early, 1)
        self.assertEqual(self.ledger.quest_late, 1)
        self.assertEqual(len(self.ledger.levels), 9)

        l1 = self.ledger.levels[1]
        self.assertEqual(l1.entrance, 0x10)
        self.assertEqual(l1.heart.room, 0x11)
        self.assertEqual(l1.heart.item, 0x1A)
        self.assertEqual(l1.triforce.room, 0x13)
        self.assertEqual(l1.triforce.item, 0x1B)
        self.assertEqual(len(l1.checks), 1)
        self.assertEqual(l1.checks[0].room, 0x12)
        self.assertEqual(l1.checks[0].item, 0x0A)  # Bow

        # Level 3's item is Bait (0x04), which is not a major item -- must
        # not show up as a check even though the room legitimately has it.
        l3 = self.ledger.levels[3]
        self.assertEqual(len(l3.checks), 0)

        # Level 9 has neither heart nor Triforce, per vanilla rules.
        l9 = self.ledger.levels[9]
        self.assertIsNone(l9.heart)
        self.assertIsNone(l9.triforce)

        self.assertTrue(self.ledger.overworld["coast"].item == 0x1A)
        self.assertFalse(self.ledger.z1r_likely)

    def test_dungeon_no_item_sentinel_excluded_from_checks(self):
        """Item byte 0x03 is the dungeon 'no item here' sentinel (aliased to
        Magical Sword in the ROM's item table) and must never be counted as
        a real check, even though literal Magical Sword is a major item."""
        layout = rom_builder.vanilla_layout()
        layout.set_item(2, 0x03)
        data = rom_builder.build_rom(layout)
        led = romlib.build_ledger("seed", data=data)
        self.assertEqual(len(led.levels[2].checks), 0)

    def test_ram_taken_bits_and_state(self):
        raw = fake_ram({}, screens={
            DUNGEON_EARLY_BASE + 0x12: 0x10,  # level 1 item room taken
            DUNGEON_EARLY_BASE + 0x11: 0x10,  # level 1 heart room taken
            0x067F + 0x0A: 0x10,              # white sword OW screen taken
        })
        state = statelib.build_state(raw, self.ledger, connected=True, source="test")
        l1 = state["locations"]["levels"][0]
        self.assertEqual(l1["items"]["total"], 1)
        self.assertEqual(l1["items"]["taken"], 1)
        self.assertTrue(l1["items"]["checks"][0]["taken"])
        self.assertTrue(l1["heart"]["taken"])
        self.assertFalse(l1["triforce"]["taken"])
        self.assertTrue(state["locations"]["overworld"]["white_sword"]["taken"])
        self.assertIn("White Sword", state["provenance"])
        self.assertIn("Level 1 - Item", state["provenance"]["Bow"])

    def test_no_rom_fallback(self):
        raw = fake_ram({0x0671: 0x07, 0x066F: 0x20})
        state = statelib.build_state(raw, None, connected=True, source="test")
        self.assertEqual(state["triforce"]["count"], 3)
        self.assertEqual(state["hearts"]["max"], 3)
        self.assertTrue(any(n["code"] == "no_seed" for n in state["notes"]))
        for lv in state["locations"]["levels"]:
            self.assertIsNone(lv["items"]["total"])

    def test_hex_ram_errors(self):
        with self.assertRaises(ramlib.RamError):
            ramlib.hex_to_ram("aabb")
        with self.assertRaises(ramlib.RamError):
            ramlib.hex_to_ram("zz" * 0x800)

    def test_atomic_write(self):
        state = statelib.build_state(None, self.ledger, connected=False, source="none")
        out = os.path.join(self.dir, "tracker_state.json")
        statelib.write_json_atomic(out, state)
        with open(out) as f:
            loaded = json.load(f)
        self.assertEqual(loaded["schema"], 1)
        self.assertTrue(loaded["meta"]["rom"]["loaded"])
        leftover = [p for p in os.listdir(self.dir) if p.endswith(".tmp")]
        self.assertEqual(leftover, [])

    def test_verify_cli(self):
        from z1rtrack import service
        code = service.run_cli(["verify", "--rom", self.rom_path])
        self.assertEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
