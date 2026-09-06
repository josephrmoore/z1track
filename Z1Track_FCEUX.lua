-- Z1Track's FCEUX connector. Run this from inside FCEUX -- it's the one
-- required manual step (Python can't reach inside the emulator for you).
--
-- Setup (do this every time you start a session):
--   1. Keep this script, run.py / Z1Track.bat, and your seed .nes all in the
--      SAME folder (the unzipped Z1Track folder).
--   2. In FCEUX: File > Open ROM, load your seed .nes.
--   3. File > Lua > New Lua Script Window, open this file, click Run.
--      (It will print "Z1TRack: writing RAM snapshots to ram.hex" once it's
--      working -- leave this Lua window open while you play.)
--   4. Double-click Z1Track.bat (or run `python run.py`) to start the
--      tracker + display -- that's the single launcher step.
--
-- This writes the current RAM as a plain hex file (no LuaSocket needed --
-- many FCEUX Windows builds don't ship it, so this avoids sockets entirely).
--
-- By default this writes "ram.hex" using a path relative to FCEUX's own
-- working directory, which is normally the folder FCEUX was launched from --
-- one folder, no path editing needed for most setups. If ram.hex ends up
-- somewhere unexpected (or the tracker never shows connected=true), change
-- OUTPUT_PATH below to an absolute path instead, e.g. "C:\\Z1Track\\ram.hex",
-- and pass that same absolute path to run.py's --ram-file.

local OUTPUT_PATH = "ram.hex"
local RAM_SIZE = 0x800                  -- $0000-$07FF inclusive = 2048 bytes

local frames = 0
local wrote_once = false

while true do
  frames = frames + 1
  if frames % 15 == 0 then
    local ram_str = memory.readbyterange(0x0000, RAM_SIZE)
    local t = {}
    for i = 1, #ram_str do
      t[i] = string.format("%02x", ram_str:byte(i))
    end
    local f = io.open(OUTPUT_PATH, "w")
    if f then
      f:write(table.concat(t))
      f:close()
      if not wrote_once then
        print("Z1TRack: writing RAM snapshots to " .. OUTPUT_PATH)
        wrote_once = true
      end
    elseif not wrote_once then
      print("Z1TRack: FAILED to open " .. OUTPUT_PATH .. " for writing -- check the path/permissions")
      wrote_once = true
    end
  end
  emu.frameadvance()
end
