"""Real firmware, flashed into an emulated STM32F405 over the GDB remote protocol, read back and booted."""

from __future__ import annotations

from pathlib import Path

import pytest

from uavtrail.targets.errors import TargetError
from uavtrail.targets.layout import config_crc, pack_config, pack_otp
from uavtrail.targets.mcu import McuTarget
from uavtrail.targets.rsp import RspClient
from uavtrail.targets.uart import TcpUart

pytestmark = pytest.mark.qemu

UID = bytes.fromhex("0102030405060708090a0b0c")


def _target(mcu, layouts) -> McuTarget:
    t = McuTarget("fc", layouts["fc"], RspClient("127.0.0.1", mcu.gdb_port))
    t.connect()
    return t


def test_program_verify_configure_and_boot(emulated_fc, layouts, firmware: dict[str, Path]) -> None:
    emulated_fc.insert_board(UID, "C", "L2609-114")
    t = _target(emulated_fc, layouts)
    ident = t.identify()
    assert (ident.uid, ident.board_rev, ident.lot) == (UID.hex(), "C", "L2609-114")
    image = firmware["fc"].read_bytes()
    t.program(image)
    record = pack_config("HX2-26-000123", [120, -40, 15, 0, 3, -7])
    t.write_config(record)
    uart = TcpUart("127.0.0.1", emulated_fc.uart_port)
    boot = t.boot(uart)
    t.close()
    uart.close()
    assert boot.target == "fc" and boot.passed
    assert boot.fields["fw"] == "1.14.2"
    assert boot.fields["uid"] == UID.hex()
    assert boot.fields["unit"] == "HX2-26-000123"
    assert boot.fields["cfg"] == config_crc(record)
    assert boot.selftest == {"img": "ok", "otp": "ok", "cfg": "ok", "cal": "ok", "sensors": "ok"}


def test_a_board_revision_the_firmware_does_not_know_fails_its_self_test(emulated_fc, layouts, firmware) -> None:
    emulated_fc.insert_board(UID, "D", "L2611-002")
    t = _target(emulated_fc, layouts)
    t.program(firmware["fc_new"].read_bytes())
    t.write_config(pack_config("HX2-26-000124", [0] * 6))
    uart = TcpUart("127.0.0.1", emulated_fc.uart_port)
    boot = t.boot(uart)
    assert not boot.passed and boot.selftest["sensors"] == "fail"
    uart.close()
    t.close()


def test_calibration_out_of_range_fails_the_self_test(emulated_fc, layouts, firmware) -> None:
    emulated_fc.insert_board(UID, "C", "L1")
    t = _target(emulated_fc, layouts)
    t.program(firmware["fc"].read_bytes())
    t.write_config(pack_config("HX2-26-000125", [900_000, 0, 0, 0, 0, 0]))
    uart = TcpUart("127.0.0.1", emulated_fc.uart_port)
    boot = t.boot(uart)
    assert not boot.passed and boot.selftest["cal"] == "bad"
    uart.close()
    t.close()


def test_a_board_without_supplier_identity_is_refused(emulated_fc, layouts) -> None:
    emulated_fc.insert_board(UID, "C", "L1", otp_override=b"\x00" * 32)
    t = _target(emulated_fc, layouts)
    with pytest.raises(TargetError) as e:
        t.identify()
    assert e.value.code == "otp_blank"
    t.close()  # the probe takes one client at a time; the station lets go before the next board goes in
    emulated_fc.insert_board(UID, "C", "L1", otp_override=pack_otp(UID, "C", "L1")[:-1] + b"\x00")
    t = _target(emulated_fc, layouts)
    with pytest.raises(TargetError) as e:
        t.identify()
    assert e.value.code == "otp_crc"
    t.close()


def test_a_corrupted_image_fails_its_own_check_at_boot(emulated_fc, layouts, firmware) -> None:
    """If flash were corrupted after the read-back, the firmware's CRC trailer still catches it at boot."""
    emulated_fc.insert_board(UID, "C", "L1")
    t = _target(emulated_fc, layouts)
    image = bytearray(firmware["fc"].read_bytes())
    t.program(bytes(image))
    t.write_config(pack_config("HX2-26-000126", [0] * 6))
    image[200] ^= 0x01  # a bit inside the code that the banner path does not execute
    t.probe.write_memory(layouts["fc"]["flash_base"] + 200, bytes([image[200]]))
    uart = TcpUart("127.0.0.1", emulated_fc.uart_port)
    boot = t.boot(uart)
    assert boot.selftest["img"] == "bad" and not boot.passed
    uart.close()
    t.close()


@pytest.mark.parametrize(
    ("kind", "code"), [("refuse", "link_refused"), ("drop", "link_dropped"), ("corrupt", "verify_mismatch")]
)
def test_fixture_faults_surface_as_their_own_codes(emulated_fc, layouts, firmware, kind: str, code: str) -> None:
    from uavsim.faults import FaultPlan, FixtureLink

    emulated_fc.insert_board(UID, "C", "L1")
    link = FixtureLink(emulated_fc.gdb_port)
    link.start()
    link.plan = FaultPlan(kind, after_writes=1 if kind == "corrupt" else 4, seed=7)
    t = McuTarget("fc", layouts["fc"], RspClient("127.0.0.1", link.listen_port, timeout=2))
    with pytest.raises(TargetError) as e:
        t.connect()
        t.program(firmware["fc"].read_bytes())
    assert e.value.code == code
    if code == "verify_mismatch":
        assert e.value.evidence["expected"] != e.value.evidence["actual"]
    t.close()
    # the next attach through the same fixture is healthy again
    t = McuTarget("fc", layouts["fc"], RspClient("127.0.0.1", link.listen_port, timeout=2))
    t.connect()
    t.program(firmware["fc"].read_bytes())
    t.close()
    link.stop()
