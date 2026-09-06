#!/usr/bin/env python3
"""Z1TRack -- single-launcher entry point.

Intended usage (no CLI knowledge required):
  1. Unzip the whole Z1Track folder somewhere.
  2. Put your seed's .nes file in that same folder (or be ready to pick it
     from a file dialog on first run).
  3. In FCEUX: load the seed, then run
     z1rtrack/connectors/connector_fceux_file.lua from the Lua console.
  4. Double-click this file (or `python run.py`).

That's it -- one window opens showing the live tracker. This starts the same
RAM-polling/ROM-ledger service used by `python -m z1rtrack.cli`, in a
background thread, and the display (`display.py`) in the foreground. No
terminal/CLI flags needed for the common case; everything defaults to files
living next to this script.
"""
from __future__ import annotations

import glob
import os
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from z1rtrack.service import TrackerRunner  # noqa: E402
import display as displaymod  # noqa: E402

RAM_FILE = os.path.join(HERE, "ram.hex")
STATE_FILE = os.path.join(HERE, "tracker_state.json")


def _find_rom(root: tk.Tk) -> "str | None":
    candidates = sorted(glob.glob(os.path.join(HERE, "*.nes")))
    if len(candidates) == 1:
        return candidates[0]
    if len(candidates) > 1:
        messagebox.showinfo(
            "Z1TRack",
            "Found more than one .nes file in this folder -- pick the seed "
            "you're playing.",
        )
    else:
        messagebox.showinfo(
            "Z1TRack",
            "No .nes file found in this folder. Pick your seed file.",
        )
    path = filedialog.askopenfilename(
        parent=root,
        title="Pick your Z1R seed .nes file",
        filetypes=[("NES ROM", "*.nes"), ("All files", "*.*")],
        initialdir=HERE,
    )
    return path or None


def main() -> int:
    root = tk.Tk()
    root.withdraw()  # hide the blank root window while we resolve the ROM

    rom_path = _find_rom(root)
    if not rom_path:
        messagebox.showerror("Z1TRack", "No seed selected -- exiting.")
        return 1

    runner = TrackerRunner(
        rom_path=rom_path,
        output=STATE_FILE,
        source="file",
        ram_file=RAM_FILE,
        poll_ms=250,
        write_every_ms=500,
    )
    thread = threading.Thread(target=runner.run, daemon=True)
    thread.start()

    root.deiconify()
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
