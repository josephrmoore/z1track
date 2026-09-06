"""Contract smoke test (pure RAM-only build): build a fake RAM snapshot and
verify the produced tracker_state.json tells the expected story end to end.

This build never opens, reads, or references a .nes file anywhere -- there's
no ROM ledger to reconcile against. Everything is derived straight from a
2KB RAM snapshot.
"""

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from z1rtrack import ram as ramlib
from z1rtrack import state as statelib


def fake_ram(items: dict) -> bytes:
    """items: {address: byte_value}. Everything else is zeroed."""
    hexs = ["00"] * 0x800
    for addr, val in items.items():
        hexs[addr] = f"{val:02x}"
    return ramlib.hex_to_ram("".join(hexs))


class TrackerContractTest(unittest.TestCase):
    def test_hex_ram_errors(self):
        with self.assertRaises(ramlib.RamError):
            ramlib.hex_to_ram("aabb")
        with self.assertRaises(ramlib.RamError):
            ramlib.hex_to_ram("zz" * 0x800)

    def test_inventory_tiers_and_shared_slots(self):
        raw = fake_ram({
            0x0657: 3,   # sword: magical
            0x065A: 1,   # bow
            0x0659: 2,   # arrow: silver
            0x065B: 2,   # candle: red
            0x0662: 1,   # ring: blue
            0x065E: 2,   # potion: red
        })
        inv = ramlib.decode_inventory(raw)
        self.assertEqual(inv["sword"]["name"], "Magical Sword")
        self.assertTrue(inv["bow"]["have"])
        self.assertEqual(inv["arrow"]["name"], "Silver Arrows")
        self.assertEqual(inv["candle"]["name"], "Red Candle")
        self.assertEqual(inv["ring"]["name"], "Blue Ring")
        self.assertEqual(inv["potion"]["name"], "Red Potion")

    def test_letter_potion_shared_slot(self):
        # Letter alone (no potion yet) -> should read as having the letter.
        raw = fake_ram({0x0666: 1})
        inv = ramlib.decode_inventory(raw)
        self.assertTrue(inv["letter"]["have"])
        self.assertIsNone(inv["potion"]["name"])

    def test_triforce_bits(self):
        raw = fake_ram({0x0671: 0b00000101})  # pieces 1 and 3 (0-indexed 0,2)
        tri = ramlib.decode_triforce(raw)
        self.assertEqual(tri["count"], 2)
        self.assertTrue(tri["pieces"][0])
        self.assertTrue(tri["pieces"][2])
        self.assertFalse(tri["pieces"][1])

    def test_hearts(self):
        raw = fake_ram({0x066F: 0x25, 0x0670: 0xFF})  # 3 containers, 5 filled, full partial
        hearts = ramlib.decode_hearts(raw)
        self.assertEqual(hearts["max"], 3)
        self.assertEqual(hearts["filled"], 5)
        self.assertEqual(hearts["partial"], 1.0)

    def test_enemy_kill_counter(self):
        raw = fake_ram({0x0050: 7})
        ekc = ramlib.decode_enemy_kill_counter(raw)
        self.assertEqual(ekc["count"], 7)
        self.assertEqual(ekc["resetAt"], 10)

    def test_secrets_found_and_left_behind(self):
        base = ramlib.RAM["ow_screens"]
        raw = fake_ram({
            base + 0x00: 0x80,        # secret found, not taken
            base + 0x01: 0x80 | 0x10,  # secret found AND taken
            base + 0x02: 0x00,        # nothing
        })
        secrets = ramlib.decode_secrets(raw)
        self.assertEqual(secrets["found"], 2)
        self.assertEqual(secrets["leftBehind"], 1)

    def test_build_state_connected(self):
        raw = fake_ram({0x0671: 0x07, 0x066F: 0x20})
        state = statelib.build_state(raw, connected=True, source="test")
        self.assertEqual(state["schema"], 1)
        self.assertTrue(state["meta"]["connected"])
        self.assertEqual(state["triforce"]["count"], 3)
        self.assertEqual(state["hearts"]["max"], 3)
        self.assertIsNotNone(state["secrets"])
        self.assertIsNotNone(state["enemyKillCounter"])
        # No ROM-related keys should exist anywhere in the contract.
        self.assertNotIn("rom", state["meta"])
        self.assertNotIn("locations", state)
        self.assertNotIn("provenance", state)

    def test_build_state_disconnected(self):
        state = statelib.build_state(None, connected=False, source="none")
        self.assertFalse(state["meta"]["connected"])
        self.assertIsNone(state["inventory"])
        self.assertIsNone(state["triforce"])
        self.assertIsNone(state["secrets"])

    def test_atomic_write(self):
        raw = fake_ram({0x0671: 0x01})
        state = statelib.build_state(raw, connected=True, source="test")
        tmpdir = tempfile.mkdtemp()
        out = os.path.join(tmpdir, "tracker_state.json")
        statelib.write_json_atomic(out, state)
        with open(out) as f:
            loaded = json.load(f)
        self.assertEqual(loaded["schema"], 1)
        leftover = [p for p in os.listdir(tmpdir) if p.endswith(".tmp")]
        self.assertEqual(leftover, [])

    def test_once_cli(self):
        from z1rtrack import service
        tmpdir = tempfile.mkdtemp()
        ram_file = os.path.join(tmpdir, "ram.hex")
        out_file = os.path.join(tmpdir, "tracker_state.json")
        with open(ram_file, "w") as f:
            f.write("00" * 0x800)
        code = service.run_cli(["once", "--ram-file", ram_file, "-o", out_file])
        self.assertEqual(code, 0)
        self.assertTrue(os.path.exists(out_file))


if __name__ == "__main__":
    unittest.main()
