"""The station and the firmware must agree on where things live in flash, and on the records' shape."""

from __future__ import annotations

import re

import pytest
from conftest import ROOT

from uavtrail.targets.layout import (
    CFG_MAGIC,
    CFG_SIZE,
    OTP_MAGIC,
    OTP_SIZE,
    RecordError,
    pack_config,
    pack_otp,
    parse_otp,
)

HEADER = (ROOT / "firmware" / "src" / "layout.h").read_text()


def _define(block: str, name: str) -> int:
    m = re.search(rf"#define {name} (0x[0-9A-Fa-f]+)u", block)
    assert m, name
    return int(m.group(1), 16)


@pytest.mark.parametrize(("target", "macro"), [("fc", "TARGET_FC"), ("pmu", "TARGET_PMU")])
def test_addresses_agree_with_the_firmware(layouts: dict, target: str, macro: str) -> None:
    block = HEADER.split(f"defined({macro})")[1].split("#elif")[0].split("#else")[0]
    assert _define(block, "OTP_ADDR") == layouts[target]["otp"]
    assert _define(block, "CFG_ADDR") == layouts[target]["config"]
    assert layouts[target]["image_max"] <= layouts[target]["otp"] - layouts[target]["flash_base"]


def test_magics_and_sizes_agree_with_the_firmware() -> None:
    assert _define(HEADER, "OTP_MAGIC") == OTP_MAGIC
    assert _define(HEADER, "CFG_MAGIC") == CFG_MAGIC
    assert OTP_SIZE == 4 + 12 + 1 + 11 + 4
    assert CFG_SIZE == 4 + 4 + 16 + 6 * 4 + 4


def test_records_round_trip_and_reject_damage() -> None:
    raw = pack_otp(bytes(range(12)), "C", "L2609-114")
    ident = parse_otp(raw)
    assert (ident.board_rev, ident.lot, ident.uid) == ("C", "L2609-114", bytes(range(12)).hex())
    with pytest.raises(RecordError) as e:
        parse_otp(raw[:-1] + bytes([raw[-1] ^ 1]))
    assert e.value.code == "otp_crc" and e.value.unverified["lot"] == "L2609-114"
    with pytest.raises(RecordError) as e:
        parse_otp(b"\xff" * OTP_SIZE)
    assert e.value.code == "otp_blank"
    assert len(pack_config("HX2-26-000001", [1, 2, 3, 4, 5, 6])) == CFG_SIZE
    with pytest.raises(RecordError):
        pack_config("X" * 17, [0] * 6)
