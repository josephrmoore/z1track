#!/usr/bin/env python3
"""Z1TRack -- single-launcher entry point (pure RAM-only build).

Intended usage (no CLI knowledge required):
  1. Unzip the whole Z1Track folder somewhere.
  2. In FCEUX: load your seed, then run
     z1rtrack/connectors/connector_fceux_file.lua from the Lua console.
  3. Double-click this file (or `python run.py`).

That's it -- one window opens showing the live tracker. This build never
opens, reads, or references the seed .nes file in any way -- there is no ROM
path anywhere in this program, by design, so the community can trust it
isn't inspecting the ROM (no spoilers, no cheating potential). It starts the
same RAM-polling service used by `python -m z1rtrack.cli`, in a background
thread, and the display (`display.py`) in the foreground.
"""
from __future__ import annotations

import os
import sys
import threading
import tkinter as tk

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from z1rtrack.service import TrackerRunner  # noqa: E402
import display as displaymod  # noqa: E402

RAM_FILE = os.path.join(HERE, "ram.hex")
STATE_FILE = os.path.join(HERE, "tracker_state.json")


def main() -> int:
    root = tk.Tk()

    runner = TrackerRunner(
        output=STATE_FILE,
        source="file",
        ram_file=RAM_FILE,
        poll_ms=250,
        write_every_ms=500,
    )
    thread = threading.Thread(target=runner.run, daemon=True)
    thread.start()

    root.title("Z1TRack")
    displaymod.STATE_FILE = STATE_FILE
    displaymod.DisplayApp(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    # On Windows, double-clicking a .py file opens a console that closes the
    # instant the script exits -- including on a crash -- so any error would
    # otherwise flash and vanish before it's readable. Never let that happen:
    # catch everything, print it, and hold the window open until the user
    # acknowledges it.
    try:
        code = main()
    except BaseException:
        import traceback
        traceback.print_exc()
        code = 1
    if code != 0:
        try:
            input("\nZ1TRack stopped (see message above). Press Enter to close this window...")
        except (EOFError, KeyboardInterrupt):
            pass
    sys.exit(code)
