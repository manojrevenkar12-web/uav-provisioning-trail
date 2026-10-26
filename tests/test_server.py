"""The traceability server: it accepts a chain once and in order, refuses anything else, and never lets the
trail be changed."""

from __future__ import annotations

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient
from sqlalchemy import text

from uavtrail import keys
from uavtrail.server import db
from uavtrail.server.api import app
from uavtrail.trail.chain import Chain

pytestmark = pytest.mark.db


@pytest.fixture
def client(clean_db: str) -> TestClient:
    return TestClient(app, headers={"x-uav-role": "station", "x-uav-actor": "ST-1"})


def _events(key: Ed25519PrivateKey, unit: str = "HX2-26-000001") -> list[dict]:
    c = Chain(unit, "ST-1", key)
    c.append("start", "2026-10-27T06:00:00+01:00", slot="FX-A/1", fixture="FX-A", release="R2026.09", operator="OP-07")
    c.append("intent", "2026-10-27T06:00:01+01:00", slot="FX-A/1", fixture="FX-A", step="scan_unit", attempt=1)
    c.append(
        "result",
        "2026-10-27T06:00:09+01:00",
        slot="FX-A/1",
        fixture="FX-A",
        step="scan_unit",
        attempt=1,
        ok=True,
        seconds=8,
        evidence={},
    )
    c.append(
        "hold",
        "2026-10-27T06:00:20+01:00",
        slot="FX-A/1",
        fixture="FX-A",
        step="fc_identify",
        code="otp_blank",
        owner="supplier",
        detail="",
        seconds=150,
    )
    return c.events


def test_a_chain_is_accepted_once_and_derives_the_unit(client: TestClient) -> None:
    key = Ed25519PrivateKey.generate()
    assert client.post("/api/stations", json={"station": "ST-1", "public_key": keys.public_hex(key)}).status_code == 200
    events = _events(key)
    first = client.post("/api/trail", json={"events": events}).json()
    assert first == {"accepted": 4, "duplicates": 0, "rejected": []}
    again = client.post("/api/trail", json={"events": events}).json()
    assert again == {"accepted": 0, "duplicates": 4, "rejected": []}
    u = client.get("/api/units/HX2-26-000001").json()
    assert u["unit"]["status"] == "held" and u["unit"]["hold_code"] == "otp_blank" and u["chain"]["verified"]
    assert client.get("/api/units/HX2-26-000001/head").json()["seq"] == 4


def test_gaps_forgeries_and_strangers_are_refused(client: TestClient) -> None:
    key = Ed25519PrivateKey.generate()
    client.post("/api/stations", json={"station": "ST-1", "public_key": keys.public_hex(key)})
    events = _events(key)
    gap = client.post("/api/trail", json={"events": events[1:]}).json()
    assert gap["accepted"] == 0 and "gap" in gap["rejected"][0]["why"]
    forged = [dict(e) for e in events]
    forged[0] = forged[0] | {"data": forged[0]["data"] | {"release": "R2026.10"}}
    assert "hash" in client.post("/api/trail", json={"events": forged}).json()["rejected"][0]["why"]
    stranger = _events(Ed25519PrivateKey.generate(), unit="HX2-26-000002")
    assert "not signed" in client.post("/api/trail", json={"events": stranger}).json()["rejected"][0]["why"]
    assert client.post("/api/stations", json={"station": "ST-1", "public_key": "ab" * 32}).status_code == 409


def test_the_trail_cannot_be_edited_or_deleted(client: TestClient) -> None:
    key = Ed25519PrivateKey.generate()
    client.post("/api/stations", json={"station": "ST-1", "public_key": keys.public_hex(key)})
    client.post("/api/trail", json={"events": _events(key)})
    for sql in ("update trail set kind = 'x'", "delete from trail"):
        with pytest.raises(Exception, match="append-only"), db.begin() as c:
            c.execute(text(sql))
    assert db.scalar("select count(*) from trail") == 4


def test_claims_are_first_come(client: TestClient) -> None:
    body = {"kind": "fc_uid", "value": "0102", "unit": "HX2-26-000001"}
    assert client.post("/api/registry/claims", json=body).status_code == 200
    assert client.post("/api/registry/claims", json=body).status_code == 200  # the owner may claim again
    taken = client.post("/api/registry/claims", json=body | {"unit": "HX2-26-000009"})
    assert taken.status_code == 409 and taken.json()["owner"] == "HX2-26-000001"


def test_roles(client: TestClient) -> None:
    op = TestClient(app, headers={"x-uav-role": "operator"})
    assert op.post("/api/trail", json={"events": []}).status_code == 403
    assert (
        op.post("/api/issues/0123456789ab/actions", json={"action": "fixed", "note": "new pogo block"}).status_code
        == 403
    )
    assert op.get("/api/units").status_code == 200
    assert op.get("/api/units/nope").status_code == 404
    assert op.get("/api/units?status=bogus").status_code == 422


def test_bearer_tokens_replace_headers(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("UAV_API_TOKENS", "t-lead:Mia:lead,t-st:ST-1:station")
    anon = TestClient(app)
    assert anon.get("/api/units").status_code == 401
    assert TestClient(app, headers={"authorization": "Bearer t-lead"}).get("/api/units").status_code == 200
    spoof = TestClient(app, headers={"authorization": "Bearer t-st", "x-uav-role": "lead"})
    assert (
        spoof.post("/api/issues/0123456789ab/actions", json={"action": "note", "note": "hi there"}).status_code == 403
    )
