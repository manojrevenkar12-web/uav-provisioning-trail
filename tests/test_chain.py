"""The paper trail: whole chains verify; any edit, gap, reorder or foreign signature is found."""

from __future__ import annotations

import copy

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from uavtrail import keys
from uavtrail.trail.chain import Chain, event_hash, genesis, verify


def _chain(n: int = 5) -> tuple[list[dict], dict[str, str]]:
    key = Ed25519PrivateKey.generate()
    c = Chain("HX2-26-000001", "ST-1", key)
    for i in range(n):
        c.append("result", f"2026-10-27T06:0{i}:00+01:00", step=f"s{i}", ok=True)
    return c.events, {"ST-1": keys.public_hex(key)}


def test_a_whole_chain_verifies() -> None:
    events, ks = _chain()
    assert events[0]["prev"] == genesis("HX2-26-000001")
    assert verify(events, ks) == []


def test_editing_an_event_is_found() -> None:
    events, ks = _chain()
    bad = copy.deepcopy(events)
    bad[2]["data"]["ok"] = False
    assert any("altered" in p for p in verify(bad, ks))


def test_a_missing_event_is_found() -> None:
    events, ks = _chain()
    assert any("missing" in p for p in verify(events[:2] + events[3:], ks))


def test_rehashing_an_edit_still_breaks_the_signature_and_the_link() -> None:
    events, ks = _chain()
    bad = copy.deepcopy(events)
    bad[1]["data"]["ok"] = False
    bad[1]["hash"] = event_hash(bad[1])
    problems = verify(bad, ks)
    assert any("not signed" in p for p in problems) and any("does not follow" in p for p in problems)


def test_another_stations_key_is_refused() -> None:
    events, _ = _chain()
    other = {"ST-1": keys.public_hex(Ed25519PrivateKey.generate())}
    assert all("not signed" in p for p in verify(events, other))


def test_a_rework_run_continues_the_chain() -> None:
    events, ks = _chain(2)
    key2 = Ed25519PrivateKey.generate()
    c = Chain("HX2-26-000001", "ST-2", key2, head=events[-1]["hash"], seq=events[-1]["seq"])
    c.append("start", "2026-10-27T09:00:00+01:00")
    assert verify(events + c.events, ks | {"ST-2": keys.public_hex(key2)}) == []
