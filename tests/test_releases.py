"""Only signed releases install, and only while their files still match."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from conftest import ROOT

from uavsim import bundles
from uavtrail import keys, releases
from uavtrail.targets.errors import TargetError


@pytest.fixture
def built(tmp_path: Path) -> dict:
    art = tmp_path / "artifacts"
    art.mkdir()
    (art / "fc-1.14.2.bin").write_bytes(b"fc image")
    (art / "pmu-2.3.1.bin").write_bytes(b"pmu image")
    bundles.build("3.1.4", "36.4.3", ["uav-link.service"], art)
    key = tmp_path / "release.key"
    k = keys.generate(key)
    releases.build(ROOT / "releases" / "R2026.09.yaml", art, key, tmp_path / "rel")
    trusted = {keys.fingerprint(keys.public_hex(k)): keys.public_hex(k)}
    return {"art": art, "rel": tmp_path / "rel", "trusted": trusted}


def test_a_signed_release_loads(built: dict) -> None:
    r = releases.load("R2026.09", built["rel"], built["art"], built["trusted"])
    assert r.version("fc") == "1.14.2" and len(r.digest) == 64


def test_an_untrusted_signer_is_refused(built: dict) -> None:
    with pytest.raises(TargetError) as e:
        releases.load("R2026.09", built["rel"], built["art"], {})
    assert e.value.code == "release_unverified"


def test_an_edited_release_is_refused(built: dict) -> None:
    path = built["rel"] / "R2026.09.json"
    spec = json.loads(path.read_text())
    spec["compatible"]["fc"].append("D")
    path.write_bytes(releases.canonical(spec))
    with pytest.raises(TargetError) as e:
        releases.load("R2026.09", built["rel"], built["art"], built["trusted"])
    assert "signature" in e.value.detail


def test_a_swapped_image_is_refused(built: dict) -> None:
    (built["art"] / "fc-1.14.2.bin").write_bytes(b"something else")
    with pytest.raises(TargetError) as e:
        releases.load("R2026.09", built["rel"], built["art"], built["trusted"])
    assert e.value.code == "release_unverified"


def test_a_changed_partition_in_the_bundle_is_refused(built: dict) -> None:
    (built["art"] / "orin-3.1.4" / "APP.img").write_bytes(b"tampered")
    with pytest.raises(TargetError) as e:
        releases.load("R2026.09", built["rel"], built["art"], built["trusted"])
    assert e.value.code == "bundle_mismatch"
