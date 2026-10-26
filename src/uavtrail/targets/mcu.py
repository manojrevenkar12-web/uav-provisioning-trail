"""A microcontroller on the fixture, reached through a debug probe's GDB server.

The station never trusts a write it has not read back. Programming is: identify the board from what the PCBA
supplier programmed, erase and write the image, read the whole image back and compare hashes, write the unit's
configuration and read that back too, then reset the part, let it boot and read its banner and self-test from the
console. Each of these raises a TargetError with a stable code when it fails.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any

from .errors import TargetError
from .layout import CFG_SIZE, OTP_SIZE, Identity, RecordError, parse_otp
from .rsp import LinkError, ProtocolError, RspClient
from .uart import Uart

BOOT = re.compile(r"^BOOT (\w+) (.*)$")
PAIR = re.compile(r"(\w+)=(\S+)")


@dataclass
class Boot:
    target: str
    fields: dict[str, str]
    selftest: dict[str, str]
    passed: bool
    lines: list[str]


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def parse_console(lines: list[str]) -> Boot:
    target, fields, selftest, passed = "", {}, {}, False
    for line in lines:
        m = BOOT.match(line)
        if m:
            target, fields = m.group(1), dict(PAIR.findall(m.group(2)))
        elif line.startswith("SELFTEST PASS"):
            passed = True
        elif line.startswith("SELFTEST FAIL"):
            passed = False
        elif line.startswith("SELFTEST "):
            selftest = dict(PAIR.findall(line))
    if not target:
        raise TargetError("banner_missing", "no boot banner on the console", console=lines[-5:])
    return Boot(target, fields, selftest, passed, lines)


class McuTarget:
    def __init__(self, kind: str, layout: dict[str, Any], probe: RspClient) -> None:
        self.kind = kind
        self.layout = layout
        self.probe = probe

    # --------------------------------------------------------------------------- link

    def connect(self) -> None:
        try:
            self.probe.connect()
        except LinkError as e:
            raise TargetError("link_refused", str(e), probe=f"{self.probe.host}:{self.probe.port}") from e
        except ProtocolError as e:
            raise TargetError("link_garbled", str(e)) from e

    def close(self) -> None:
        self.probe.close()

    def _io(self, what: str, fn: Any, *args: Any) -> Any:
        try:
            return fn(*args)
        except LinkError as e:
            raise TargetError("link_dropped", f"{what}: {e}") from e
        except ProtocolError as e:
            raise TargetError("link_garbled", f"{what}: {e}") from e

    # --------------------------------------------------------------------------- operations

    def identify(self) -> Identity:
        raw = self._io("read identity", self.probe.read_memory, self.layout["otp"], OTP_SIZE)
        try:
            return parse_otp(raw)
        except RecordError as e:
            raise TargetError(e.code, e.detail, unverified=e.unverified) from e

    def _erase_and_write(self, address: int, length: int, data: bytes) -> None:
        if self.probe.supports_flash_packets:  # a probe with a flash driver
            self._io("erase", self.probe.flash_erase, address, length)
            self._io("write", self.probe.flash_write, address, data)
            self._io("commit", self.probe.flash_done)
        else:  # QEMU maps flash as memory: erasing is writing the erased value
            self._io("erase", self.probe.write_memory, address, b"\xff" * length)
            self._io("write", self.probe.write_memory, address, data)

    def _verify(self, address: int, data: bytes, code: str) -> str:
        back = self._io("read back", self.probe.read_memory, address, len(data))
        if back != data:
            first = next(i for i, (a, b) in enumerate(zip(back, data, strict=True)) if a != b)
            raise TargetError(
                code,
                f"read back differs from what was written at {address + first:#x}",
                offset=first,
                expected=sha256(data),
                actual=sha256(back),
            )
        return sha256(back)

    def program(self, image: bytes) -> str:
        """Erases the image region, writes the image, reads it back. Returns the read-back hash."""
        if len(image) > self.layout["image_max"]:
            raise TargetError("image_too_large", f"{len(image)} bytes > {self.layout['image_max']}")
        block = self.layout["erase_block"]
        span = -(-len(image) // block) * block
        self._erase_and_write(self.layout["flash_base"], span, image)
        return self._verify(self.layout["flash_base"], image, "verify_mismatch")

    def write_config(self, record: bytes) -> str:
        assert len(record) == CFG_SIZE
        self._erase_and_write(self.layout["config"], self.layout["config_block"], record)
        return self._verify(self.layout["config"], record, "config_verify_mismatch")

    def boot(self, uart: Uart) -> Boot:
        """Resets the part and reads what it prints until its self-test verdict."""
        self._io("reset", self.probe.monitor, self.layout["reset_command"])
        self._io("run", self.probe.resume)
        lines = uart.lines_until(("SELFTEST PASS", "SELFTEST FAIL"), float(self.layout["banner_timeout_s"]))
        if not any(line.startswith(("SELFTEST PASS", "SELFTEST FAIL")) for line in lines):
            if any(line.startswith("BOOT") for line in lines):
                raise TargetError("selftest_timeout", "booted but no self-test verdict", console=lines[-5:])
            raise TargetError("banner_missing", "no boot banner on the console", console=lines[-5:])
        return parse_console(lines)
