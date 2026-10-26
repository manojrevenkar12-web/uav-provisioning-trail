"""Systemic or one-off, on synthetic attempts with a known answer."""

from __future__ import annotations

import random

from uavtrail.analysis.issues import analyse, watch_list
from uavtrail.analysis.stats import binom_tail, hypergeom_tail, wilson

SLOTS = [f"FX-{f}/{i}" for f in "AB" for i in range(1, 5)]


def attempts(
    rng: random.Random, n: int, fail: callable, step: str = "fc_attach", code: str = "link_refused"
) -> list[dict]:  # type: ignore[valid-type]
    rows = []
    for i in range(n):
        slot = SLOTS[i % len(SLOTS)]
        row = {
            "unit": f"U{i:04d}",
            "step": step,
            "slot": slot,
            "fixture": slot.split("/")[0],
            "station": "ST-1" if slot.startswith("FX-A") else "ST-2",
            "operator": rng.choice(["OP-1", "OP-2"]),
            "release": "R1",
            "dims": {"fc_lot": rng.choice(["L1", "L2"])},
            "seconds": 10.0,
            "at": f"2026-10-27T06:{i % 60:02d}",
        }
        failed = fail(row, rng)
        rows.append(row | {"ok": not failed, "code": code if failed else None})
    return rows


def test_the_statistics() -> None:
    assert abs(binom_tail(1, 1, 0.5) - 0.5) < 1e-12
    assert abs(binom_tail(0, 10, 0.3) - 1.0) < 1e-12
    assert abs(binom_tail(2, 3, 0.5) - 0.5) < 1e-12
    assert abs(hypergeom_tail(2, 4, 2, 2) - 1 / 6) < 1e-12  # both marked items drawn: 1 of C(4,2)
    assert abs(hypergeom_tail(0, 10, 3, 4) - 1.0) < 1e-12
    lo, hi = wilson(5, 10)
    assert lo < 0.5 < hi


def test_a_bad_slot_is_named_as_the_slot_not_its_fixture_or_station() -> None:
    rng = random.Random(1)
    rows = attempts(rng, 400, lambda r, g: (r["slot"] == "FX-A/3" and g.random() < 0.5) or g.random() < 0.01)
    found = analyse(rows)
    systemic = [i for i in found if i.kind == "systemic"]
    assert len(systemic) == 1 and systemic[0].where[0] == {"dimension": "slot", "value": "FX-A/3"}
    assert any(i.kind == "one_off" for i in found)


def test_a_bad_lot_is_named_as_the_lot() -> None:
    rng = random.Random(2)
    rows = attempts(
        rng, 400, lambda r, g: r["dims"]["fc_lot"] == "L2" and g.random() < 0.2, step="fc_identify", code="otp_crc"
    )
    systemic = [i for i in analyse(rows) if i.kind == "systemic"]
    assert systemic[0].where[0] == {"dimension": "fc_lot", "value": "L2"}


def test_noise_is_called_systemic_no_more_often_than_alpha_allows() -> None:
    """Pure noise, 200 shifts: the share of shifts with a false systemic issue stays below alpha (0.05 per code)."""
    false = 0
    for seed in range(200):
        rng = random.Random(seed)
        rows = attempts(rng, 300, lambda r, g: g.random() < 0.03)
        false += any(i.kind == "systemic" for i in analyse(rows))
    assert false / 200 <= 0.05


def test_a_code_failing_everywhere_is_widespread() -> None:
    rng = random.Random(3)
    rows = attempts(rng, 300, lambda r, g: g.random() < 0.3)
    assert [i.kind for i in analyse(rows)] == ["widespread"]


def test_slow_links_are_watched_before_they_fail() -> None:
    rows = [{"step": "orin_enumerate", "ok": True, "slot": "FX-C/2", "evidence": {"slow_link": True}} for _ in range(4)]
    rows += [
        {"step": "orin_enumerate", "ok": True, "slot": "FX-C/1", "evidence": {"slow_link": False}} for _ in range(4)
    ]
    assert [w["slot"] for w in watch_list(rows)] == ["FX-C/2"]
