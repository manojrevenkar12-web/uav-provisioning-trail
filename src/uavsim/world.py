"""The airframes of a campaign: what each is made of, and which faults it will meet. Generated from the campaign's
seed, so a campaign always produces the same shift."""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any

from .campaign import Campaign


@dataclass
class Board:
    uid: bytes
    rev: str
    lot: str
    otp_blank: bool = False


@dataclass
class Airframe:
    index: int
    serial: str
    release: str
    fc: Board
    pmu: Board
    module: dict[str, Any]
    calibration: dict[str, list[int]]
    injected: list[str] = field(default_factory=list)  # fault ids this unit carries (truth)


def _pick(rng: random.Random, weights: dict[str, float]) -> str:
    keys = list(weights)
    return rng.choices(keys, weights=[weights[k] for k in keys])[0]


def release_for(campaign: Campaign, index: int) -> str:
    active = [r for r in campaign.spec["releases"] if r["from_unit"] <= index]
    return str(max(active, key=lambda r: r["from_unit"])["release"])


def generate(campaign: Campaign, release_versions: dict[str, dict[str, str]], n: int | None = None) -> list[Airframe]:
    spec = campaign.spec
    rng = random.Random(spec["seed"])
    mix = spec["mix"]
    units: list[Airframe] = []
    for i in range(1, (n or spec["units"]) + 1):
        serial = f"HX2-{rng.randrange(26, 27)}-{i:06d}"
        fc = Board(rng.randbytes(12), _pick(rng, mix["fc_rev"]), _pick(rng, mix["fc_lot"]))
        pmu = Board(rng.randbytes(12), _pick(rng, mix["pmu_rev"]), _pick(rng, mix["pmu_lot"]))
        sku = _pick(rng, mix["orin_sku"])
        module = {
            "serial": f"14{rng.randrange(10**12):012d}",
            "board_id": 3767,
            "sku": sku,
            "fab": "300" if rng.random() < 0.7 else "301",
            "batch": _pick(rng, mix["orin_batch"]),
            "eeprom_crc_ok": True,
            "nvme_defect": False,
        }
        cal = {t: [rng.randint(-120_000, 120_000) for _ in range(6)] for t in ("fc", "pmu")}
        units.append(Airframe(i, serial, release_for(campaign, i), fc, pmu, module, cal))

    for f in campaign.faults:
        k, p = f["kind"], float(f.get("p", 0))
        for u in units:
            if k == "supplier_eeprom_crc" and u.module["batch"] == f["orin_batch"] and rng.random() < p:
                u.module["eeprom_crc_ok"] = False
                u.injected.append(f["id"])
            elif k == "supplier_otp_blank" and getattr(u, f["target"]).lot == f["lot"] and rng.random() < p:
                getattr(u, f["target"]).otp_blank = True
                u.injected.append(f["id"])
            elif k == "nvme_defect" and rng.random() < p:
                u.module["nvme_defect"] = True
                u.injected.append(f["id"])
            elif k == "calibration_outlier" and rng.random() < p:
                u.calibration[f["target"]][rng.randrange(6)] = rng.choice([-1, 1]) * rng.randint(600_000, 900_000)
                u.injected.append(f["id"])
            elif k == "board_swap" and u.index > 5 and rng.random() < p:
                donor = units[rng.randrange(0, u.index - 1)]
                u.fc = Board(donor.fc.uid, donor.fc.rev, donor.fc.lot)  # a board already used in another airframe
                u.injected.append(f["id"])
            elif k == "firmware_board_gap":
                if (
                    release_versions.get(u.release, {}).get(f["target"]) == f["version"]
                    and getattr(u, f["target"]).rev == f["missing_rev"]
                ):
                    u.injected.append(f["id"])
    return units
