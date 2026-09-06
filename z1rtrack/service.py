"""Tracker service: polls the live RAM source, reconciles against the ROM
ledger, and writes tracker_state.json.

Live sources:
  1. A Lua connector (BizHawk/FCEUX) streaming JSON lines over TCP.
  2. A raw-hex RAM file (demo / headless / test mode, polled on change).

The loop is fully stateless between reads: every poll re-derives the entire
tracker state from absolute RAM + the static ROM ledger.  On any disconnect or
cold restart the display repopulates from the next successful poll, so the
service never needs to replay events.
"""

from __future__ import annotations

import json
import os
import socket
import sys
import time

from . import ram as ramlib
from . import rom as romlib
from . import state as statelib

DEFAULT_PORT = 52981

# A RamSource legitimately has no *new* frame available on most polls (the
# poll interval and the connector's write/send interval are similar, so most
# checks land between updates -- that's normal, not a disconnect). Sources
# therefore cache the last good read and keep returning it as long as it's
# not older than this, so "connected" reflects real disconnects, not polling
# aliasing. Only silence longer than this counts as actually disconnected.
STALE_SECONDS = 3.0


class RamSource:
    """Abstract live-RAM source: returns raw 2KB bytes or None."""

    def read(self) -> bytes | None:
        raise NotImplementedError


class TcpRamSource(RamSource):
    """Client connection to a Lua connector (the Lua binds the port)."""

    def __init__(self, host: str, port: int, timeout: float = 3.0):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.sock: socket.socket | None = None
        self.buffer = b""
        self._last_ram: bytes | None = None
        self._last_update: float = 0.0

    def read(self) -> bytes | None:
        if self.sock is None:
            self._connect()
            if self.sock is None:
                return None
        try:
            chunk = self.sock.recv(65536)
            if not chunk:
                raise ConnectionError("closed")
            self.buffer += chunk
            # Lua connectors send one JSON line per tick.
            while b"\n" in self.buffer:
                raw, self.buffer = self.buffer.split(b"\n", 1)
                data = json.loads(raw.decode("utf-8", "replace"))
                if "ram" in data:
                    self._last_ram = ramlib.hex_to_ram(data["ram"])
                    self._last_update = time.time()
        except socket.timeout:
            # No new line arrived within the socket timeout -- routine, not a
            # disconnect (this will happen most polls if the connector writes
            # less often than we poll). Must NOT drop() here: that would wipe
            # _last_ram and defeat the STALE_SECONDS grace period entirely,
            # since every plain timeout would otherwise look identical to a
            # real disconnect. Fall through to the staleness check below.
            pass
        except (OSError, ValueError, KeyError, json.JSONDecodeError) as e:
            # An actual socket error, or unparseable/malformed data -- this
            # is a real disconnect signal, unlike a plain timeout above.
            self.drop()
            raise ConnectionError(str(e)) from e
        # No new complete message parsed this call -- if the socket is still
        # open and our last frame isn't stale, that's a live connection with
        # nothing new to report yet, not a disconnect.
        if self._last_ram is not None and (time.time() - self._last_update) < STALE_SECONDS:
            return self._last_ram
        return None

    def _connect(self) -> None:
        try:
            self.sock = socket.create_connection((self.host, self.port), timeout=self.timeout)
            self.buffer = b""
        except OSError:
            self.sock = None

    def drop(self) -> None:
        if self.sock is not None:
            try:
                self.sock.close()
            except OSError:
                pass
        self.sock = None
        self.buffer = b""
        self._last_ram = None


class FileRamSource(RamSource):
    """Demo/headless mode: watch a file containing 4096 hex chars of RAM."""

    def __init__(self, path: str):
        self.path = path
        self.last_mtime = None
        self._last_ram: bytes | None = None
        self._last_update: float = 0.0

    def read(self) -> bytes | None:
        try:
            mtime = os.path.getmtime(self.path)
        except OSError:
            return None  # file genuinely gone -- actually disconnected
        if mtime != self.last_mtime:
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    text = f.read().strip()
                self._last_ram = ramlib.hex_to_ram(text)
                self._last_update = time.time()
                self.last_mtime = mtime
            except (OSError, ValueError):
                pass  # transient read race (e.g. mid-write); fall through to cache
        # File exists but hasn't changed since last poll -- normal between
        # connector writes, not a disconnect, as long as it's still fresh.
        if self._last_ram is not None and (time.time() - self._last_update) < STALE_SECONDS:
            return self._last_ram
        return None


class RomWatcher:
    """Re-reads and re-parses the seed ROM when the file on disk changes."""

    def __init__(self, path: str | None):
        self.path = path
        self.ledger = None
        self._mtime = None
        self.changed = False

    def refresh(self) -> bool:
        """Returns True when the ledger was (re)built this call."""
        if not self.path:
            self.changed = False
            return False
        try:
            mtime = os.path.getmtime(self.path)
        except OSError:
            return False
        if mtime == self._mtime and self.ledger is not None:
            self.changed = False
            return False
        try:
            self.ledger = romlib.build_ledger(self.path)
            self._mtime = mtime
            self.changed = True
            return True
        except romlib.RomError as e:
            print(f"ROM parse failed: {e}", file=sys.stderr)
            self.ledger = None
            return False


class TrackerRunner:
    def __init__(self, rom_path: str | None, output: str,
                 source: str = "tcp", host: str = "127.0.0.1", port: int = DEFAULT_PORT,
                 ram_file: str | None = None, poll_ms: int = 250,
                 write_every_ms: int = 1000):
        self.output = output
        self.poll = poll_ms / 1000.0
        self.write_every = write_every_ms / 1000.0
        self.rom_watcher = RomWatcher(rom_path)
        if source == "file" or ram_file:
            self.source: RamSource = FileRamSource(ram_file or "ram.hex")
        else:
            self.source = TcpRamSource(host, port)

    def _read_ram(self):
        try:
            return self.source.read()
        except ConnectionError as e:
            sys.stderr.write(f"source: {e}\n")
            return None

    def run(self) -> None:
        last_write = 0.0
        last_state = None
        detected = False
        # initial ROM parse (logs a human-readable ledger on --verbose)
        self.rom_watcher.refresh()
        if self.rom_watcher.ledger is not None:
            print(f"LEDGER OK: {self.rom_watcher.ledger.rom_hash[:12]}  "
                  f"quest E{self.rom_watcher.ledger.quest_early}/L{self.rom_watcher.ledger.quest_late}  "
                  f"z1r={self.rom_watcher.ledger.z1r_likely}")
        while True:
            ram_now = self._read_ram()
            self.rom_watcher.refresh()
            seed_changed = self.rom_watcher.changed
            ledger = self.rom_watcher.ledger

            try:
                state = statelib.build_state(
                    ram_now, ledger,
                    connected=ram_now is not None,
                    source=type(self.source).__name__,
                    seed_changed=seed_changed,
                )
            except ramlib.RamError as e:
                sys.stderr.write(f"ram: {e}\n")
                state = statelib.build_state(None, ledger, connected=False,
                                             source=type(self.source).__name__)

            now = time.time()
            # Write on change, or at least once per write window, plus always
            # when connection state flips. Compare everything except
            # "updatedAt" (a wall-clock timestamp that's different on every
            # single poll by construction) -- comparing the raw state dict
            # made this throttle a no-op, writing at full poll_ms cadence
            # regardless of write_every_ms, which also meant hitting the
            # Windows-lock retry path far more often than necessary.
            comparable = {k: v for k, v in state.items() if k != "updatedAt"}
            last_comparable = (
                {k: v for k, v in last_state.items() if k != "updatedAt"}
                if last_state is not None else None
            )
            changed = comparable != last_comparable
            flip = ((state["meta"]["connected"] is True) != detected)
            detected = state["meta"]["connected"] is True
            if changed or flip or (now - last_write) >= self.write_every:
                try:
                    statelib.write_json_atomic(self.output, state)
                    last_write = now
                    last_state = state
                except OSError as e:
                    # Never let a transient write failure (e.g. WinError 5 /
                    # Access is denied, from a reader or AV briefly holding a
                    # lock on the destination file) kill the service. Skip
                    # this write; the next poll will try again.
                    sys.stderr.write(f"write: {e} (will retry next poll)\n")
            time.sleep(self.poll)


def run_cli(argv):
    import argparse

    parser = argparse.ArgumentParser(
        prog="z1rtrack",
        description="Zelda-1 Randomizer auto-tracker data source. Writes "
                    "tracker_state.json for a display to read.")
    parser.add_argument("--rom", help="path to the seed .nes file")
    parser.add_argument("-o", "--output", default="tracker_state.json",
                        help="output contract file (default: tracker_state.json)")
    parser.add_argument("--source", choices=["tcp", "file"], default="tcp",
                        help="live RAM source")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--ram-file", help="hex RAM snapshot file to watch (--source file)")
    parser.add_argument("--poll-ms", type=int, default=250,
                        help="RAM poll interval in ms")
    parser.add_argument("--write-ms", type=int, default=1000,
                        help="minimum interval between file writes in ms")
    sub = parser.add_subparsers(dest="command")

    led = sub.add_parser("verify", help="parse the ROM and print the ledger")
    led.add_argument("--rom")

    one = sub.add_parser("once", help="read RAM once in demo mode and write state")
    one.add_argument("--rom")
    one.add_argument("--ram-file")
    one.add_argument("-o", "--output", default="tracker_state.json")

    args = parser.parse_args(argv)

    if args.command == "verify":
        rom_path = args.rom
        if not rom_path:
            parser.error("verify requires --rom")
        try:
            ledger = romlib.build_ledger(rom_path)
        except romlib.RomError as e:
            print(f"ROM parse failed: {e}", file=sys.stderr)
            return 1
        print(json.dumps(romlib.dump_ledger(ledger), indent=2))
        return 0

    if args.command == "once":
        raw = None
        if args.ram_file:
            with open(args.ram_file, "r", encoding="utf-8") as f:
                raw = ramlib.hex_to_ram(f.read().strip())
        ledger = None
        if args.rom:
            try:
                ledger = romlib.build_ledger(args.rom)
            except romlib.RomError as e:
                print(f"ROM parse failed: {e}", file=sys.stderr)
        state = statelib.build_state(raw, ledger,
                                     connected=raw is not None,
                                     source="once")
        statelib.write_json_atomic(args.output, state)
        print(f"wrote {args.output}")
        return 0

    TrackerRunner(
        rom_path=args.rom,
        output=args.output,
        source=args.source,
        host=args.host,
        port=args.port,
        ram_file=args.ram_file,
        poll_ms=args.poll_ms,
        write_every_ms=args.write_ms,
    ).run()
    return 0