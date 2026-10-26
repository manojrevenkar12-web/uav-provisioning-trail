"""Everything a campaign's line needs before the first airframe: firmware and image bundles built the way the
campaign's truth says the code really behaves, a release-signing key and the signed releases, station keys."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from uavtrail import keys, releases
from uavtrail.config import root

from . import bundles, firmware
from .campaign import Campaign


def release_specs(campaign: Campaign) -> dict[str, dict[str, Any]]:
    ids = {r["release"] for r in campaign.spec["releases"]}
    return {rid: yaml.safe_load((root() / "releases" / f"{rid}.yaml").read_text()) for rid in sorted(ids)}


def release_versions(campaign: Campaign) -> dict[str, dict[str, str]]:
    return {
        rid: {t: str(a["version"]) for t, a in spec["artifacts"].items()}
        for rid, spec in release_specs(campaign).items()
    }


def build(campaign: Campaign, out: Path) -> dict[str, Any]:
    specs = release_specs(campaign)
    artifacts = out / "artifacts"
    gaps = {
        (f["target"], str(f["version"])): f["missing_rev"] for f in campaign.faults if f["kind"] == "firmware_board_gap"
    }
    baked = {str(f["version"]) for f in campaign.faults if f["kind"] == "baked_machine_id"}
    for spec in specs.values():
        for target in ("fc", "pmu"):
            version = str(spec["artifacts"][target]["version"])
            revs = "".join(
                sorted(
                    {
                        r
                        for s in specs.values()
                        if str(s["artifacts"][target]["version"]) == version
                        for r in s["compatible"][target]
                    }
                )
            )
            revs = revs.replace(gaps.get((target, version), "#"), "")
            firmware.build(target, version, revs, artifacts)
        orin = spec["artifacts"]["orin"]
        bundles.build(
            str(orin["version"]),
            str(orin["l4t"]),
            list(orin["services"]),
            artifacts,
            machine_id="7c3f0e2a9b8d4c1e8f6a5b4c3d2e1f00" if str(orin["version"]) in baked else None,
        )
    key_dir = out / "keys"
    release_key = key_dir / "release.key"
    if not release_key.exists():
        keys.generate(release_key)
    trust = out / "trust.yaml"
    trust.write_text(yaml.safe_dump([keys.public_hex(keys.load_private(release_key))]))
    for rid in specs:
        releases.build(root() / "releases" / f"{rid}.yaml", artifacts, release_key, out / "releases")
    return {"artifacts": artifacts, "releases": out / "releases", "trust": trust, "keys": key_dir}
