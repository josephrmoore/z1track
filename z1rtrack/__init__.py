"""Z1TRack - disconnection-proof auto-tracker data source for
The Legend of Zelda 1 (NES) + Z1R randomizer seeds.

The service reads seed data from the .nes ROM (static ledger) and live state
from a 2KB RAM snapshot supplied by an emulator connector, and writes a single
JSON contract (tracker_state.json) that a separate display reads.
"""

__version__ = "0.1.0"