-- BizHawk Lua connector for Z1TRack.
--
-- Binds a local TCP server that accepts exactly one client (the tracker
-- service) and streams a JSON line per tick:
--   {"t": <monotonic ms>, "ram": "<4096 lowercase hex chars of $0000-$07FF>"}
--
-- Every ~15 frames (~4 Hz).  Reconnects are automatic: accept() again after
-- the current client disconnects.
--
-- NOTE: BizHawk is Windows/Linux only; on macOS use the FCEUX connector or a
-- RetroArch core (see connector_retroarch.md).  memory.readbyterange is
-- 1-indexed, hence [1, 0x800].
--
-- Usage: open a NES .lsnes from BizHawk Tools > Lua Console, then `dofile`
-- this script (edit the HOST/PORT below if needed).

local HOST = "127.0.0.1"
local PORT = 52981

local socket = require("socket")
local client, server

local function open_server()
  server = server or socket.tcp()
  server:setoption("reuseaddr", true)
  server:bind(HOST, PORT)
  server:listen(5)
  print(string.format("Z1TRack connector listening on %s:%d", HOST, PORT))
end

local function accept_client()
  if client then
    client:close()
  end
  client = server:accept()
  client:settimeout(0.05)
  print("Z1TRack tracker connected")
end

open_server()

local frames = 0
while true do
  if not client then
    accept_client()
  end

  frames = frames + 1
  if frames % 15 == 0 and client then
    local ram = memory.readbyterange(1, 0x800)
    local t = {}
    for i = 1, #ram do
      t[#t + 1] = string.format("%02x", ram[i])
    end
    local line = string.format(
      '{"t": %d, "ram": "%s"}',
      client.milliseconds or 0,
      table.concat(t)
    )
    local ok, err = client:send(line .. "\n")
    if not ok then
      if err == "closed" or err == "Connection reset by peer" then
        client = nil
      end
    end
  end

  -- Non-blocking poll; keep the Lua loop responsive.
  if client then
    local _, err = client:settimeout(0.05)
    if err then
      client = nil
    end
  end
  emu.frameadvance()
end