"""One emulated microcontroller in a fixture slot: QEMU halted at reset with its GDB stub and console on TCP ports.

The same QEMU stays in the slot for a whole shift; each new board is "inserted" by programming the supplier's
identity into its OTP area and wiping the rest of the flash, which is what a fresh board looks like to the station.
"""

from __future__ import annotations

import shutil
import socket
import subprocess
import time
from dataclasses import dataclass, field

from uavtrail.targets.layout import pack_otp
from uavtrail.targets.rsp import RspClient


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def available() -> bool:
    return shutil.which("qemu-system-arm") is not None


@dataclass
class EmulatedMcu:
    kind: str
    machine: str
    layout: dict
    gdb_port: int = field(default_factory=free_port)
    uart_port: int = field(default_factory=free_port)
    proc: subprocess.Popen | None = None

    def start(self) -> None:
        self.proc = subprocess.Popen(
            [
                "qemu-system-arm",
                "-M",
                self.machine,
                "-display",
                "none",
                "-monitor",
                "none",
                "-S",
                "-gdb",
                f"tcp:127.0.0.1:{self.gdb_port}",
                "-serial",
                f"tcp:127.0.0.1:{self.uart_port},server=on,wait=off",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            if self.proc.poll() is not None:
                raise RuntimeError(f"QEMU exited: {self.proc.stderr.read().decode() if self.proc.stderr else ''}")
            try:
                with socket.create_connection(("127.0.0.1", self.gdb_port), timeout=0.2):
                    return
            except OSError:
                time.sleep(0.05)
        raise RuntimeError("QEMU's GDB stub did not come up")

    def insert_board(self, uid: bytes, board_rev: str, lot: str, otp_override: bytes | None = None) -> None:
        """What the PCBA supplier leaves on a new board: its identity in OTP, nothing else. The CPU is halted."""
        with RspClient("127.0.0.1", self.gdb_port) as probe:
            probe.monitor("system_reset")
            base, size = self.layout["flash_base"], self.layout["image_max"]
            probe.write_memory(base, b"\x00" * size)
            probe.write_memory(self.layout["config"], b"\x00" * self.layout["config_block"])
            probe.write_memory(
                self.layout["otp"], otp_override if otp_override is not None else pack_otp(uid, board_rev, lot)
            )

    def stop(self) -> None:
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        self.proc = None
