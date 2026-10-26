"""A Jetson Orin-class module in force-recovery mode, as a station sees it: a USB device it can enumerate, an
EEPROM it can read, storage it can flash and read back, and a first boot that reports back.

One device server sits in each fixture slot for a shift; the line simulator inserts a module (with its own
EEPROM, storage health and fuse state, which travels with the module) and sets the slot's cable faults. Durations
are modelled from the bundle's nominal partition sizes and the link speed, so the line's clock is realistic while
the flash itself takes milliseconds.
"""

from __future__ import annotations

import hashlib
import json
import random
import socketserver
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from uavtrail.targets.orin import crc8_maxim


def eeprom_bytes(
    layout: dict[str, Any], board_id: int, sku: str, fab: str, serial: str, batch: str, crc_ok: bool = True
) -> bytes:
    raw = bytearray(layout["size"])
    a, b = layout["board_id"]
    raw[a:b] = board_id.to_bytes(b - a, "little")
    for key, value in (("sku", sku), ("fab", fab), ("serial", serial), ("batch", batch)):
        s, e = layout[key]
        raw[s:e] = value.encode().ljust(e - s, b"\0")[: e - s]
    raw[layout["crc_byte"]] = crc8_maxim(bytes(raw[: layout["crc_byte"]])) ^ (0 if crc_ok else 0x5A)
    return bytes(raw)


@dataclass
class Module:
    serial: str
    board_id: int
    sku: str
    fab: str
    batch: str
    eeprom_crc_ok: bool = True
    nvme_defect: bool = False  # a bad block in APP: what is read back differs
    fuses: dict[str, Any] = field(default_factory=dict)  # irreversible, travels with the module


@dataclass
class SlotFaults:
    enumerate_fail_p: float = 0.0  # a worn cable or port
    usb2: bool = False  # enumerates at USB2 speed: flashes take three times as long
    drop_during_flash_p: float = 0.0


@dataclass
class ReleaseDefects:
    """What is wrong with a bundle that its manifest does not say (the truth the station must discover)."""

    service_fails_on_sku: dict[str, str] = field(default_factory=dict)  # service -> SKU


class OrinDevice:
    def __init__(self, layout: dict[str, Any], seed: int = 0) -> None:
        self.layout = layout
        self.rng = random.Random(seed)
        self.module: Module | None = None
        self.faults = SlotFaults()
        self.defects: dict[str, ReleaseDefects] = {}
        self.stored: dict[str, str] = {}
        self.bundle: dict[str, Any] | None = None
        self.lock = threading.Lock()

    def insert(self, module: Module | None, faults: SlotFaults | None = None) -> None:
        with self.lock:
            self.module, self.stored, self.bundle = module, {}, None
            if faults is not None:
                self.faults = faults

    # ------------------------------------------------------------------ operations

    def handle(self, req: dict[str, Any]) -> dict[str, Any]:
        with self.lock:
            op = req.get("op")
            fn = getattr(self, f"op_{op}", None)
            if fn is None:
                return {"ok": False, "code": "usb_protocol", "detail": f"unknown op {op}"}
            return fn(req)

    def _speed(self) -> float:
        return float(self.layout["usb2_mb_per_s"] if self.faults.usb2 else self.layout["usb3_mb_per_s"])

    def op_enumerate(self, _: dict[str, Any]) -> dict[str, Any]:
        if self.module is None:
            return {
                "ok": False,
                "code": "usb_no_device",
                "detail": "nothing in recovery mode on this port",
                "duration_s": 10,
            }
        if self.rng.random() < self.faults.enumerate_fail_p:
            return {
                "ok": False,
                "code": "usb_enumeration_failed",
                "detail": "no device on the recovery port within 10 s",
                "duration_s": 10,
            }
        usb_id = "0955:7323" if self.module.sku == "0000" else "0955:7423"
        return {
            "ok": True,
            "result": {"usb_id": usb_id, "speed": "usb2" if self.faults.usb2 else "usb3"},
            "duration_s": 4,
        }

    def op_read_eeprom(self, _: dict[str, Any]) -> dict[str, Any]:
        m = self.module
        assert m is not None
        raw = eeprom_bytes(self.layout["eeprom"], m.board_id, m.sku, m.fab, m.serial, m.batch, m.eeprom_crc_ok)
        return {"ok": True, "result": raw.hex(), "duration_s": 1}

    def op_flash(self, req: dict[str, Any]) -> dict[str, Any]:
        bundle_dir = Path(req["bundle"])
        manifest = json.loads((bundle_dir / "manifest.json").read_text())
        self.stored, self.bundle = {}, manifest
        elapsed = 25.0  # initrd boot, NFS and SSH over usb0 before the first byte
        for i, part in enumerate(manifest["partitions"]):
            if i == len(manifest["partitions"]) - 1 and self.rng.random() < self.faults.drop_during_flash_p:
                return {
                    "ok": False,
                    "code": "usb_reset_during_flash",
                    "detail": f"the link reset while writing {part['name']}",
                    "duration_s": elapsed + part["nominal_mb"] / self._speed() / 2,
                    "evidence": {"partition": part["name"]},
                }
            digest = hashlib.sha256((bundle_dir / part["file"]).read_bytes()).hexdigest()
            assert self.module is not None
            if self.module.nvme_defect and part["name"] == "APP":
                digest = hashlib.sha256(digest.encode()).hexdigest()
            self.stored[part["name"]] = digest
            elapsed += part["nominal_mb"] / self._speed()
        return {
            "ok": True,
            "result": {"partitions": len(self.stored), "speed": "usb2" if self.faults.usb2 else "usb3"},
            "duration_s": round(elapsed, 1),
        }

    def op_read_back(self, _: dict[str, Any]) -> dict[str, Any]:
        total = sum(p["nominal_mb"] for p in (self.bundle or {}).get("partitions", []))
        return {"ok": True, "result": dict(self.stored), "duration_s": round(10 + total / 120, 1)}

    def op_first_boot(self, _: dict[str, Any]) -> dict[str, Any]:
        m, b = self.module, self.bundle
        assert m is not None
        if not b or any(self.stored.get(p["name"]) != p["sha256"] for p in b["partitions"]):
            return {
                "ok": False,
                "code": "boot_failed",
                "detail": "the module did not come up after the flash",
                "duration_s": 120,
            }
        defects = self.defects.get(b["version"], ReleaseDefects())
        services = {s: ("failed" if defects.service_fails_on_sku.get(s) == m.sku else "active") for s in b["services"]}
        machine_id = b.get("machine_id") or f"{self.rng.getrandbits(128):032x}"
        key = hashlib.sha256(f"{m.serial}:{self.rng.getrandbits(64)}".encode()).hexdigest()
        return {
            "ok": True,
            "duration_s": 75,
            "result": {
                "l4t": b["l4t"],
                "image_version": b["version"],
                "services": services,
                "machine_id": machine_id,
                "device_key_sha256": key,
                "fused": bool(m.fuses),
            },
        }

    def op_burn_fuses(self, req: dict[str, Any]) -> dict[str, Any]:
        m = self.module
        assert m is not None
        if m.fuses and m.fuses != req["config"]:
            return {
                "ok": False,
                "code": "fuse_conflict",
                "detail": "the module is already fused differently",
                "duration_s": 5,
                "evidence": {"burnt": m.fuses},
            }
        m.fuses = dict(req["config"])
        return {"ok": True, "result": {"fused": True}, "duration_s": 15}

    def op_read_fuses(self, _: dict[str, Any]) -> dict[str, Any]:
        assert self.module is not None
        return {"ok": True, "result": dict(self.module.fuses), "duration_s": 1}


class _Handler(socketserver.StreamRequestHandler):
    def handle(self) -> None:
        line = self.rfile.readline()
        if not line:
            return
        device: OrinDevice = self.server.device  # type: ignore[attr-defined]
        try:
            answer = device.handle(json.loads(line))
        except Exception as e:  # a simulator bug must not look like a device answer
            answer = {"ok": False, "code": "simulator_error", "detail": repr(e)}
        self.wfile.write(json.dumps(answer).encode() + b"\n")


class OrinServer(socketserver.ThreadingTCPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, device: OrinDevice) -> None:
        super().__init__(("127.0.0.1", 0), _Handler)
        self.device = device
        self.port = self.server_address[1]
        threading.Thread(target=self.serve_forever, daemon=True).start()

    def stop(self) -> None:
        self.shutdown()
        self.server_close()
