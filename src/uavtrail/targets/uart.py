"""The microcontroller's console. On the line it is a USB-serial adapter in the fixture; on the emulated line it is
QEMU's serial port on a TCP socket. Either way the station only needs lines, with a deadline."""

from __future__ import annotations

import socket
import time
from typing import Protocol


class Uart(Protocol):
    def lines_until(self, done: tuple[str, ...], timeout: float) -> list[str]: ...
    def close(self) -> None: ...


class TcpUart:
    def __init__(self, host: str, port: int, connect_timeout: float = 3.0) -> None:
        deadline = time.monotonic() + connect_timeout
        while True:
            try:
                self.sock = socket.create_connection((host, port), timeout=1.0)
                break
            except OSError:
                if time.monotonic() > deadline:
                    raise
                time.sleep(0.05)
        self.buf = b""

    def lines_until(self, done: tuple[str, ...], timeout: float) -> list[str]:
        """Every line until one starting with any of `done`, or until the deadline (what arrived so far)."""
        lines: list[str] = []
        deadline = time.monotonic() + timeout
        while True:
            while b"\n" in self.buf:
                line, self.buf = self.buf.split(b"\n", 1)
                text = line.decode(errors="replace").strip()
                if text:
                    lines.append(text)
                    if text.startswith(done):
                        return lines
            left = deadline - time.monotonic()
            if left <= 0:
                return lines
            self.sock.settimeout(left)
            try:
                chunk = self.sock.recv(4096)
            except TimeoutError:
                return lines
            except OSError:
                return lines
            if not chunk:
                return lines
            self.buf += chunk

    def close(self) -> None:
        self.sock.close()
