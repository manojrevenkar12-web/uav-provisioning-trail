"""The mission computer: EEPROM identity with its CRC, recovery-mode flashing, read-back, first boot, fuses."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from conftest import ROOT

from uavsim import bundles
from uavsim.orin_sim import Module, OrinDevice, OrinServer, ReleaseDefects, SlotFaults, eeprom_bytes
from uavtrail.targets.errors import TargetError
from uavtrail.targets.orin import OrinTarget, crc8_maxim, initrd_flash_command, parse_eeprom

LAYOUT = yaml.safe_load((ROOT / "config" / "targets.yaml").read_text())["orin"]


def module(**kw: object) -> Module:
    base = {"serial": "1423000000123", "board_id": 3767, "sku": "0000", "fab": "300", "batch": "B26W38"}
    return Module(**(base | kw))  # type: ignore[arg-type]


@pytest.fixture
def slot(tmp_path: Path):
    device = OrinDevice(LAYOUT, seed=1)
    server = OrinServer(device)
    bundle, _ = bundles.build("3.1.4", "36.4.3", ["uav-link.service", "payload-bridge.service"], tmp_path)
    yield device, OrinTarget("127.0.0.1", server.port, LAYOUT), bundle
    server.stop()


def test_crc8_and_eeprom_parsing() -> None:
    assert crc8_maxim(b"123456789") == 0xA1  # the CRC-8/MAXIM check value
    raw = eeprom_bytes(LAYOUT["eeprom"], 3767, "0001", "301", "1423000000999", "B26W41")
    m = parse_eeprom(raw, LAYOUT["eeprom"])
    assert (m.board_id, m.sku, m.fab, m.serial, m.batch) == (3767, "0001", "301", "1423000000999", "B26W41")
    bad = eeprom_bytes(LAYOUT["eeprom"], 3767, "0001", "301", "1423000000999", "B26W41", crc_ok=False)
    with pytest.raises(TargetError) as e:
        parse_eeprom(bad, LAYOUT["eeprom"])
    assert e.value.code == "eeprom_crc" and e.value.evidence["unverified"]["batch"] == "B26W41"


def test_flash_read_back_and_first_boot(slot) -> None:
    device, t, bundle = slot
    device.insert(module())
    assert t.enumerate()["speed"] == "usb3"
    assert t.identify().sku == "0000"
    t.flash(bundle)
    manifest = yaml.safe_load((bundle / "manifest.json").read_text())
    assert t.read_back() == {p["name"]: p["sha256"] for p in manifest["partitions"]}
    boot = t.first_boot()
    assert boot["image_version"] == "3.1.4" and set(boot["services"].values()) == {"active"}
    assert len(boot["machine_id"]) == 32


def test_a_usb2_link_makes_the_flash_three_times_slower(slot) -> None:
    device, t, bundle = slot
    device.insert(module())
    t.seconds = 0
    t.flash(bundle)
    fast = t.seconds
    device.insert(module(), SlotFaults(usb2=True))
    t.seconds = 0
    assert t.enumerate()["speed"] == "usb2"
    t.seconds = 0
    t.flash(bundle)
    assert t.seconds > 2.5 * fast - 25 * 2


def test_a_bad_nvme_shows_in_the_read_back(slot) -> None:
    device, t, bundle = slot
    device.insert(module(nvme_defect=True))
    t.flash(bundle)
    manifest = yaml.safe_load((bundle / "manifest.json").read_text())
    back = t.read_back()
    assert back["APP"] != next(p["sha256"] for p in manifest["partitions"] if p["name"] == "APP")
    with pytest.raises(TargetError) as e:
        t.first_boot()
    assert e.value.code == "boot_failed"


def test_a_service_bug_shows_only_on_its_sku(slot) -> None:
    device, t, bundle = slot
    device.defects["3.1.4"] = ReleaseDefects({"payload-bridge.service": "0001"})
    device.insert(module(sku="0001"))
    t.flash(bundle)
    assert t.first_boot()["services"]["payload-bridge.service"] == "failed"


def test_fuses_are_irreversible(slot) -> None:
    device, t, _ = slot
    m = module()
    device.insert(m)
    t.burn_fuses({"secure_boot": 1})
    assert t.fuses() == {"secure_boot": 1}
    with pytest.raises(TargetError) as e:
        t.burn_fuses({"secure_boot": 0})
    assert e.value.code == "fuse_conflict"
    device.insert(m)  # the module keeps its fuses wherever it goes
    assert t.fuses() == {"secure_boot": 1}


def test_an_empty_port_and_a_flaky_cable(slot) -> None:
    device, t, _ = slot
    device.insert(None)
    with pytest.raises(TargetError) as e:
        t.enumerate()
    assert e.value.code == "usb_no_device"
    device.insert(module(), SlotFaults(enumerate_fail_p=1.0))
    with pytest.raises(TargetError) as e:
        t.enumerate()
    assert e.value.code == "usb_enumeration_failed"


def test_the_hardware_station_runs_nvidias_initrd_flash() -> None:
    cmd = initrd_flash_command("jetson-orin-nano-devkit", "1-3", massflash=4)
    assert cmd[:2] == ["sudo", "./tools/kernel_flash/l4t_initrd_flash.sh"]
    assert "--flash-only" in cmd and cmd[3:5] == ["--network", "usb0"] and "--massflash" in cmd
