-- FCEUX Lua connector for the Z1 Click-to-Track overworld tracker.
-- FILE-BASED, no LuaSocket required (same approach as the earlier project).
--
-- Does exactly two things:
--   1. Continuously writes the current RAM ($0000-$07FF) as a 4096-char hex
--      string to ram.hex, a few times a second. This already includes every
--      byte the Python side needs ($10 current level, $EB overworld pos,
--      $0526 dungeon-return overworld screen) -- no RAM changes needed
--      beyond the existing full-range dump.
--   2. Writes rom_info.json ONCE, at script start: the ROM's md5 hash (the
--      sole seed-identity key) and filename (a display label only). The ROM
--      doesn't change mid-session, so this never needs to be rewritten.
--
-- Usage: keep this script and click_tracker.py in the same folder. FCEUX >
-- File > Lua > New Lua Script Window > run this file.

local RAM_OUTPUT_PATH = "ram.hex"
local ROM_INFO_PATH = "rom_info.json"
local RAM_SIZE = 0x800  -- $0000-$07FF inclusive = 2048 bytes

-- Write ROM identity once.
local function write_rom_info()
  local hash = rom.gethash("md5")
  local filename = rom.getfilename()
  -- Minimal manual JSON (two known-safe string fields, no library needed).
  local escaped_name = filename:gsub('\\', '\\\\'):gsub('"', '\\"')
  local json = string.format('{"rom_hash":"%s","rom_filename":"%s"}', hash, escaped_name)
  local f = io.open(ROM_INFO_PATH, "w")
  if f then
    f:write(json)
    f:close()
    print("Z1ClickTrack: wrote " .. ROM_INFO_PATH .. " (hash=" .. hash .. ")")
  else
    print("Z1ClickTrack: FAILED to open " .. ROM_INFO_PATH .. " for writing")
  end
end

write_rom_info()

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
    local f = io.open(RAM_OUTPUT_PATH, "w")
    if f then
      f:write(table.concat(t))
      f:close()
      if not wrote_once then
        print("Z1ClickTrack: writing RAM snapshots to " .. RAM_OUTPUT_PATH)
        wrote_once = true
      end
    elseif not wrote_once then
      print("Z1ClickTrack: FAILED to open " .. RAM_OUTPUT_PATH .. " for writing")
      wrote_once = true
    end
  end
  emu.frameadvance()
end
