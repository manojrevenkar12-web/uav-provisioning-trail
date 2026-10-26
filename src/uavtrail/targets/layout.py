"""The on-flash records shared with the firmware (firmware/src/layout.h)."""

from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass

OTP_MAGIC = 0x3150544F  # "OTP1"
CFG_MAGIC = 0x47464355  # "UCFG"
OTP_FORMAT = "<I12sc11sI"  # magic, uid, board_rev, lot, crc
CFG_FORMAT = "<II16s6iI"  # magic, layout, unit_serial, cal[6], crc
OTP_SIZE = struct.calcsize(OTP_FORMAT)
CFG_SIZE = struct.calcsize(CFG_FORMAT)
CAL_LIMIT = 500_000  # the firmware rejects calibration offsets beyond this (micro-units)


@dataclass(frozen=True)
class Identity:
    uid: str
    board_rev: str
    lot: str


class RecordError(ValueError):
    def __init__(self, code: str, detail: str, unverified: dict[str, str] | None = None) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail
        self.unverified = unverified or {}


def pack_otp(uid: bytes, board_rev: str, lot: str) -> bytes:
    body = struct.pack("<I12sc11s", OTP_MAGIC, uid, board_rev.encode(), lot.encode())
    return body + struct.pack("<I", zlib.crc32(body))


def parse_otp(raw: bytes) -> Identity:
    magic, uid, rev, lot, crc = struct.unpack(OTP_FORMAT, raw[:OTP_SIZE])
    if magic != OTP_MAGIC:
        raise RecordError("otp_blank", "no supplier identity programmed (blank or erased)")
    if crc != zlib.crc32(raw[: OTP_SIZE - 4]):
        fields = {
            "uid": uid.hex(),
            "board_rev": rev.decode(errors="replace"),
            "lot": lot.rstrip(b"\0").decode(errors="replace"),
        }
        raise RecordError("otp_crc", "the supplier identity fails its CRC", fields)
    return Identity(uid.hex(), rev.decode(), lot.rstrip(b"\0").decode())


def pack_config(unit_serial: str, cal: list[int]) -> bytes:
    if len(unit_serial) > 16:
        raise RecordError("serial_too_long", unit_serial)
    if len(cal) != 6:
        raise RecordError("calibration_shape", f"6 offsets expected, got {len(cal)}")
    body = struct.pack("<II16s6i", CFG_MAGIC, 1, unit_serial.encode(), *cal)
    return body + struct.pack("<I", zlib.crc32(body))


def config_crc(record: bytes) -> str:
    return record[-4:][::-1].hex()  # as the firmware prints it: big-endian hex of the little-endian word
