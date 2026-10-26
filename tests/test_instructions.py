"""The work instruction against the recipe and release the station runs."""

from __future__ import annotations

import yaml
from conftest import ROOT

from uavtrail.analysis import instructions
from uavtrail.config import recipe


def _check(release: str) -> list[dict]:
    spec = yaml.safe_load((ROOT / "releases" / f"{release}.yaml").read_text())
    return instructions.check(instructions.load(spec["instruction"]), recipe(spec["recipe"]), spec)


def test_the_current_instruction_drifts_from_the_new_release() -> None:
    kinds = {(f["kind"], f["step"]) for f in _check("R2026.10")}
    assert ("version_drift", "fc_program") in kinds
    assert ("version_drift", "orin_flash") in kinds
    assert ("obsolete_step", "pmu_calibrate") in kinds
    assert ("missing_warning", "orin_fuse") in kinds


def test_versions_that_match_are_not_reported() -> None:
    kinds = {(f["kind"], f["step"]) for f in _check("R2026.09")}
    assert not any(k == "version_drift" for k, _ in kinds)


def test_missing_and_reordered_steps() -> None:
    spec = yaml.safe_load((ROOT / "releases" / "R2026.09.yaml").read_text())
    doc = instructions.load("WI-SW-014")
    steps = [s for s in doc["steps"] if s["id"] != "orin_verify"]
    steps[1], steps[2] = steps[2], steps[1]
    found = instructions.check(doc | {"steps": steps}, recipe("standard"), spec)
    assert {"missing_step", "order"} <= {f["kind"] for f in found}
