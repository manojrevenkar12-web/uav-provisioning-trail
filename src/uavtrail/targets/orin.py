"""The mission computer: a Jetson Orin-class module, flashed over USB in force-recovery mode.

On a real station this wraps NVIDIA's initrd flash (`l4t_initrd_flash.sh --flash-only --network usb0 ...`, see
`initrd_flash_command`); on the emulated line it talks to uavsim's recovery-mode device. Either way the station
does the same things in the same order and trusts nothing it has not read back:

1. the module enumerates in recovery mode with an expected USB id, and at USB3 speed
2. its EEPROM passes the CRC-8 in byte 255 and identifies a board id, SKU and FAB the release allows
3. the image bundle on the host matches the hashes in the signed release before a byte is sent
4. after the flash, every partition is read back and hashed
5. first boot reports its L4T release, the services the release needs, a machine-id and the device key
"""

from __future__ import annotations

import json
import socket
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .errors import TargetError


def crc8_maxim(data: bytes) -> int:
    crc = 0
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = (crc >> 1) ^ 0x8C if crc & 1 else crc >> 1
    return crc


@dataclass(frozen=True)
class ModuleId:
    board_id: int
    sku: str
    fab: str
    serial: str
    batch: str


def parse_eeprom(raw: bytes, layout: dict[str, Any]) -> ModuleId:
    size, crc_at = layout["size"], layout["crc_byte"]
    if len(raw) != size:
        raise TargetError("eeprom_unreadable", f"{len(raw)} bytes read, {size} expected")

    def text(span: list[int]) -> str:
        return raw[span[0] : span[1]].rstrip(b"\0 ").decode(errors="replace")

    a, b = layout["board_id"]
    found = ModuleId(
        int.from_bytes(raw[a:b], "little"),
        text(layout["sku"]),
        text(layout["fab"]),
        text(layout["serial"]),
        text(layout["batch"]),
    )
    if crc8_maxim(raw[:crc_at]) != raw[crc_at]:
        # NVIDIA's guidance: a wrong CRC alone can be repaired; anything else about the EEPROM is an RMA. What the
        # fields say is kept as evidence (unverified), so the analysis can still see the batch.
        raise TargetError(
            "eeprom_crc",
            "the module EEPROM fails its CRC-8",
            stored=raw[crc_at],
            computed=crc8_maxim(raw[:crc_at]),
            unverified=found.__dict__,
        )
    return found


def initrd_flash_command(board: str, usb_instance: str, massflash: int | None = None) -> list[str]:
    """The NVIDIA command a hardware station runs for step 4 (Jetson Linux developer guide, "Flashing Support")."""
    cmd = [
        "sudo",
        "./tools/kernel_flash/l4t_initrd_flash.sh",
        "--flash-only",
        "--network",
        "usb0",
        "--usb-instance",
        usb_instance,
    ]
    if massflash:
        cmd += ["--massflash", str(massflash)]
    return [*cmd, board, "internal"]


class OrinTarget:
    """Client for the recovery-mode device (JSON lines over TCP on the emulated line)."""

    def __init__(self, host: str, port: int, layout: dict[str, Any], timeout: float = 10.0) -> None:
        self.host, self.port, self.layout, self.timeout = host, port, layout, timeout
        self.seconds = 0.0  # modelled time the device reports, for the line clock

    def _call(self, op: str, **args: Any) -> Any:
        try:
            with socket.create_connection((self.host, self.port), timeout=self.timeout) as s:
                s.sendall(json.dumps({"op": op, **args}).encode() + b"\n")
                buf = b""
                while not buf.endswith(b"\n"):
                    chunk = s.recv(65536)
                    if not chunk:
                        break
                    buf += chunk
        except OSError as e:
            raise TargetError("usb_link_lost", f"{op}: {e}") from e
        if not buf:
            raise TargetError("usb_link_lost", f"{op}: no answer")
        answer = json.loads(buf)
        self.seconds += float(answer.get("duration_s", 0.0))
        if not answer.get("ok"):
            raise TargetError(answer["code"], answer.get("detail", ""), **answer.get("evidence", {}))
        return answer.get("result")

    def enumerate(self) -> dict[str, Any]:
        found = self._call("enumerate")
        if found["usb_id"] not in self.layout["usb_recovery_ids"]:
            raise TargetError(
                "usb_unexpected_device", f"{found['usb_id']} is not a module in recovery mode", usb_id=found["usb_id"]
            )
        return dict(found)

    def identify(self) -> ModuleId:
        return parse_eeprom(bytes.fromhex(self._call("read_eeprom")), self.layout["eeprom"])

    def flash(self, bundle: Path) -> dict[str, Any]:
        return dict(self._call("flash", bundle=str(bundle)))

    def read_back(self) -> dict[str, str]:
        return dict(self._call("read_back"))

    def first_boot(self) -> dict[str, Any]:
        return dict(self._call("first_boot"))

    def burn_fuses(self, fuse_config: dict[str, Any]) -> dict[str, Any]:
        """Irreversible. Only the station's guard (station/guards.py) may call this."""
        return dict(self._call("burn_fuses", config=fuse_config))

    def fuses(self) -> dict[str, Any]:
        return dict(self._call("read_fuses"))
