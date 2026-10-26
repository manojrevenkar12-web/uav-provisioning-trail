"""A whole shift on the emulated line: real firmware in QEMU, the real station software, the real server."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from uavtrail import evaluate
from uavtrail.server import db
from uavtrail.server.api import app

pytestmark = [pytest.mark.qemu, pytest.mark.db]


def test_the_shift_runs_and_the_server_holds_every_event(shift: dict) -> None:
    s = shift["summary"]
    assert s["units"] == 72 and s["rejected_events"] == []
    assert db.scalar("select count(distinct unit) from trail") == 72
    outbox_backlog = sum(1 for f in shift["out"].glob("outbox-*.sqlite"))
    assert outbox_backlog >= 1


def test_the_analysis_names_every_injected_cause_and_nothing_else(shift: dict) -> None:
    truth = json.loads((shift["out"] / "truth.json").read_text())
    result = evaluate.issues(truth)
    assert result["missed"] == [] and result["false_alarms"] == []
    assert result["found"] == len(truth["expected"]) == 3


def test_every_trail_and_certificate_verifies(shift: dict) -> None:
    t = evaluate.trail()
    assert t["chains_broken"] == [] and t["certificates_bad"] == [] and t["released"] > 30


def test_no_fuse_was_burnt_without_its_guard(shift: dict) -> None:
    truth = json.loads((shift["out"] / "truth.json").read_text())
    irr = evaluate.irreversible(truth)
    assert irr["burns"] > 30 and irr["unguarded"] == [] and irr["burnt_without_trail"] == []
    held_before_fuse = db.scalar(
        """select count(*) from units u where status = 'held' and exists (
             select 1 from attempts a where a.unit = u.unit and a.step = 'orin_fuse' and a.ok)"""
    )
    assert held_before_fuse == 0


def test_a_released_unit_has_the_released_software_in_its_certificate(shift: dict) -> None:
    row = db.rows(
        "select unit, release, certificate from units where status = 'released' and release = 'R2026.10' limit 1"
    )[0]
    cert = row["certificate"]["certificate"]
    assert cert["installed"]["fc"]["version"] == "1.15.0" and cert["installed"]["orin"]["version"] == "3.2.0"
    assert cert["installed"]["orin_boot"]["services"]["payload-bridge.service"] == "active"
    assert cert["module"]["sku"] == "0000"  # the 0001 modules fail the service under 3.2.0 and are held


def test_kpis_and_views(shift: dict) -> None:
    c = TestClient(app, headers={"x-uav-role": "lead"})
    o = c.get("/api/overview").json()
    k = o["kpis"]
    assert k["units"]["started"] == 72
    assert 0 < k["first_pass_yield"]["value"] < k["final_yield"]["value"] <= 1
    assert k["flash_success"]["of"] >= 72 * 2 and k["downtime_minutes"] > 0
    slots = c.get("/api/slots").json()
    assert len(slots) == 12 and sum(1 for s in slots if s["stats"]) == 12
    issues = c.get("/api/issues").json()["issues"]
    pogo = next(i for i in issues if i["kind"] == "systemic" and i["code"] == "link_refused")
    assert pogo["where"][0] == {"dimension": "slot", "value": "FX-B/1"}
    used = c.get("/api/where-used", params={"target": "orin", "version": "3.2.0"}).json()
    assert used["units"] and all(u["release"] == "R2026.10" for u in used["units"])
    unit = used["units"][0]["unit"]
    detail = c.get(f"/api/units/{unit}").json()
    assert detail["chain"]["verified"] and detail["events"][0]["kind"] == "start"
    assert c.get(f"/api/units/{unit}/certificate").json()["certificate"]["unit"] == unit


def test_an_issue_marked_fixed_reports_whether_the_fix_holds(shift: dict) -> None:
    c = TestClient(app, headers={"x-uav-role": "lead", "x-uav-actor": "Lead"})
    issues = c.get("/api/issues").json()["issues"]
    pogo = next(i for i in issues if i["kind"] == "systemic" and i["code"] == "link_refused")
    mid = db.scalar("select min(at) + (max(at) - min(at)) / 2 from attempts")
    r = c.post(
        f"/api/issues/{pogo['key']}/actions",
        json={"action": "fixed", "note": "pogo block replaced", "effective_at": mid.isoformat()},
    )
    assert r.status_code == 200
    again = next(i for i in c.get("/api/issues").json()["issues"] if i["key"] == pogo["key"])
    assert again["actions"][0]["action"] == "fixed"
    assert again["effect"]["verdict"] == "not holding"  # the emulated fixture never got a new pogo block
