-- FCEUX Lua connector for the Z1 Click-to-Track overworld tracker.
-- FILE-BASED, no LuaSocket required.

local RAM_OUTPUT_PATH = "ram.hex"
local ROM_INFO_PATH = "rom_info.json"
local RAM_SIZE = 0x800  -- $0000-$07FF inclusive = 2048 bytes

-- Write ROM identity once.
local function write_rom_info()
  local hash = rom.gethash("md5")
  local filename = rom.getfilename()
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