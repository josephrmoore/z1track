-- FCEUX Lua connector for Z1TRack -- FILE-BASED, no LuaSocket required.
--
-- Many FCEUX Windows builds (confirmed: 2.6.6 win64) do not ship LuaSocket,
-- so connector_fceux.lua (the socket version) will fail with
-- "module 'socket' not found". This version avoids sockets entirely: it
-- just writes the current RAM ($0000-$07FF) as a 4096-character hex string
-- to a local file, several times a second, using plain Lua io -- no external
-- dependencies at all.
--
-- The Python side watches this file for changes instead of listening on a
-- TCP port.
--
-- Usage:
--   1. Keep this script, run.py/display.py, and your seed .nes all in the
--      SAME folder (e.g. the unzipped Z1Track folder). FCEUX > File > Lua >
--      New Lua Script Window > run this file from there.
--   2. By default this writes "ram.hex" using a path relative to FCEUX's own
--      working directory, which is normally the folder FCEUX was launched
--      from -- one folder, no path editing needed for most setups.
--   3. If ram.hex ends up somewhere unexpected (or the tracker never shows
--      connected=true), change OUTPUT_PATH below to an absolute path
--      instead, e.g. "C:\\Z1Track\\ram.hex", and pass the same absolute path
--      to run.py's --ram-file.

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
