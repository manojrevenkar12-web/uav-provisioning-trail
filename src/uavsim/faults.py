"""The fixture between the station and the part: pogo pins, cables, a power supply. On the emulated line it is a TCP
proxy in front of QEMU's GDB stub that can misbehave the way fixtures do.

- refuse: the probe cannot attach (no contact)
- drop: the link dies part-way through a transfer (brown-out, a cable pulled)
- corrupt: one written byte arrives wrong at the part (marginal signal on SWD); the packet is well-formed, so only
  the station's read-back can catch it

The plan for the next connection is set by the line simulator before each unit; `None` is a healthy fixture.
"""

from __future__ import annotations

import contextlib
import random
import socket
import threading
from collections.abc import Callable
from dataclasses import dataclass, field

from uavtrail.targets.rsp import checksum


@dataclass
class FaultPlan:
    kind: str  # refuse | drop | corrupt
    after_writes: int = (
        3  # drop: on which memory write the link dies; corrupt: which data write (not erase fill) is hit
    )
    seed: int = 0


@dataclass
class FixtureLink:
    target_port: int
    listen_port: int = 0
    plan: FaultPlan | None = None  # one-shot: the next attach only
    policy: Callable[[], FaultPlan | None] | None = None  # asked on every attach without a plan (a worn fixture)
    _server: socket.socket | None = None
    _stop: threading.Event = field(default_factory=threading.Event)
    connections: int = 0

    def start(self) -> None:
        self._server = socket.socket()
        self._server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server.bind(("127.0.0.1", self.listen_port))
        self._server.listen(4)
        self.listen_port = self._server.getsockname()[1]
        threading.Thread(target=self._accept, daemon=True).start()

    def stop(self) -> None:
        self._stop.set()
        if self._server:
            self._server.close()

    def _accept(self) -> None:
        assert self._server is not None
        while not self._stop.is_set():
            try:
                client, _ = self._server.accept()
            except OSError:
                return
            plan, self.plan = self.plan, None  # a plan applies to one attach
            if plan is None and self.policy is not None:
                plan = self.policy()
            self.connections += 1
            if plan and plan.kind == "refuse":
                client.close()
                continue
            try:
                upstream = socket.create_connection(("127.0.0.1", self.target_port), timeout=5)
            except OSError:
                client.close()
                continue
            for s in (client, upstream):
                s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            threading.Thread(target=self._pump_up, args=(client, upstream, plan), daemon=True).start()
            threading.Thread(target=self._pump_down, args=(upstream, client), daemon=True).start()

    @staticmethod
    def _pump_down(src: socket.socket, dst: socket.socket) -> None:
        try:
            while chunk := src.recv(65536):
                dst.sendall(chunk)
        except OSError:
            pass
        finally:
            for s in (src, dst):
                with contextlib.suppress(OSError):
                    s.shutdown(socket.SHUT_RDWR)

    def _pump_up(self, src: socket.socket, dst: socket.socket, plan: FaultPlan | None) -> None:
        """Station to part, packet by packet, so a fault can hit a chosen memory write."""
        buf, writes, data_writes = b"", 0, 0
        rng = random.Random(plan.seed if plan else 0)
        try:
            while True:
                chunk = src.recv(65536)
                if not chunk:
                    break
                buf += chunk
                out = b""
                while buf:
                    if buf[:1] != b"$":
                        out, buf = out + buf[:1], buf[1:]
                        continue
                    end = buf.find(b"#")
                    if end < 0 or len(buf) < end + 3:
                        break
                    payload, buf = buf[1:end], buf[end + 3 :]
                    if payload.startswith(b"M") and b":" in payload:
                        writes += 1
                        head, data = payload.split(b":", 1)
                        is_data = bool(data.strip(b"f")) and bool(data.strip(b"0"))  # not an erase or wipe fill
                        data_writes += is_data
                        if plan and plan.kind == "drop" and writes == plan.after_writes:
                            dst.sendall(out)
                            raise ConnectionAbortedError
                        if plan and plan.kind == "corrupt" and is_data and data_writes == plan.after_writes:
                            raw = bytearray(bytes.fromhex(data.decode()))
                            raw[rng.randrange(len(raw))] ^= 1 << rng.randrange(8)
                            payload = head + b":" + raw.hex().encode()
                    out += b"$" + payload + b"#" + checksum(payload)
                if out:
                    dst.sendall(out)
        except (OSError, ConnectionAbortedError):
            pass
        finally:
            for s in (src, dst):
                with contextlib.suppress(OSError):
                    s.shutdown(socket.SHUT_RDWR)
                s.close()
