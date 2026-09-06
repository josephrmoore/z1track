-- FCEUX Lua connector for Z1TRack.
--
-- Binds a local TCP server (LuaSocket) and streams one JSON line every ~4 Hz:
--   {"t": <frame count>, "ram": "<4096 lowercase hex chars of $0000-$07FF>"}
--
-- FCEUX's memory library has no readbytetable function. The real API is
-- memory.readbyterange(address, length), which returns a Lua STRING (not a
-- table) -- individual bytes come from string.byte()/str:byte(i). See
-- https://fceux.com/web/help/LuaFunctionsList.html (Memory Library section).
--
-- LuaSocket ships built into the official Windows FCEUX build (statically
-- linked -- see LuaPerks in the FCEUX docs), so require("socket") should work
-- out of the box there. Linux/macOS builds may need a separate luasocket
-- install; if require("socket") errors, that's the first thing to check.
--
-- Usage: FCEUX > File > Lua > New Lua Script Window, then Run this file.

local HOST = "127.0.0.1"
local PORT = 52981
local RAM_SIZE = 0x800  -- $0000-$07FF inclusive = 2048 bytes

local socket = require("socket")
local client, server

local function open_server()
  server = server or socket.tcp()
  server:setoption("reuseaddr", true)
  local ok, err = server:bind(HOST, PORT)
  if not ok then
    error("Z1TRack connector bind failed: " .. tostring(err))
  end
  server:listen(5)
  print(string.format("Z1TRack connector listening on %s:%d", HOST, PORT))
end

local function accept_client()
  if client then
    client:close()
  end
  client = server:accept()
  if client then
    client:settimeout(0.05)
    print("Z1TRack tracker connected")
  end
end

open_server()

local frames = 0

while true do
  if not client then
    accept_client()
  end

  frames = frames + 1
  if frames % 15 == 0 and client then
    local ram_str = memory.readbyterange(0x0000, RAM_SIZE)
    local t = {}
    for i = 1, #ram_str do
      t[i] = string.format("%02x", ram_str:byte(i))
    end
    local line = string.format(
      '{"t": %d, "ram": "%s"}',
      emu.framecount(),
      table.concat(t)
    )
    local ok, err = client:send(line .. "\n")
    if not ok and (err == "closed" or err == "Connection reset by peer") then
      client = nil
    end
  end

  emu.frameadvance()
end
