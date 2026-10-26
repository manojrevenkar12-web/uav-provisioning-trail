"""A campaign: one shift on the emulated line, with the faults it carries. The faults are the truth."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

# What each kind of fault is, and what a correct analysis says about it.
#   systemic: where the problem lives (the dimension and value the analysis should name), and the code it shows as
#   one_off: should be called one-off, never systemic
KINDS: dict[str, dict[str, Any]] = {
    "fixture_contact": {"systemic": True, "code": "link_refused", "dimension": "slot", "key": "slot"},
    # a bad cable shows as failed enumerations and as modules linking at USB2: naming either at the slot is right
    "usb_cable": {
        "systemic": True,
        "code": "usb_enumeration_failed",
        "also": ["slow_link"],
        "dimension": "slot",
        "key": "slot",
    },
    "usb_drop": {"systemic": True, "code": "usb_reset_during_flash", "dimension": "slot", "key": "slot"},
    "supplier_eeprom_crc": {"systemic": True, "code": "eeprom_crc", "dimension": "orin_batch", "key": "orin_batch"},
    "supplier_otp_blank": {"systemic": True, "code": "otp_blank", "dimension": "{target}_lot", "key": "lot"},
    "firmware_board_gap": {
        "systemic": True,
        "code": "selftest_fail",
        "dimension": "{target}_rev",
        "key": "missing_rev",
    },
    "baked_machine_id": {"systemic": True, "code": "machine_id_duplicate", "dimension": "release", "key": "release"},
    "service_on_sku": {"systemic": True, "code": "service_failed", "dimension": "orin_sku", "key": "sku"},
    "operator_handling": {"systemic": True, "code": "link_dropped", "dimension": "operator", "key": "operator"},
    "random_link": {"systemic": False},
    "nvme_defect": {"systemic": False},
    "calibration_outlier": {"systemic": False},
    "board_swap": {"systemic": False},
}


@dataclass
class Campaign:
    name: str
    spec: dict[str, Any]
    path: Path

    @property
    def faults(self) -> list[dict[str, Any]]:
        return list(self.spec.get("faults", []))

    def expected(self) -> list[dict[str, Any]]:
        """The systemic issues a correct analysis reports: code, dimension and value."""
        out = []
        for f in self.faults:
            k = KINDS[f["kind"]]
            if k["systemic"]:
                dim = k["dimension"].format(target=f.get("target", ""))
                out.append(
                    {
                        "fault": f["id"],
                        "code": k["code"],
                        "codes": [k["code"], *k.get("also", [])],
                        "dimension": dim,
                        "value": str(f[k["key"]]),
                    }
                )
        return out


def load(path: Path) -> Campaign:
    spec = yaml.safe_load(path.read_text(encoding="utf-8"))
    for f in spec.get("faults", []):
        if f.get("kind") not in KINDS:
            raise ValueError(f"{path.name}: unknown fault kind {f.get('kind')!r}")
        if "id" not in f:
            raise ValueError(f"{path.name}: every fault needs an id")
    return Campaign(spec["campaign"], spec, path)
