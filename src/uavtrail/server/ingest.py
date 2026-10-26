"""Accepting trail events from stations.

Each event must continue its unit's chain exactly (next seq, prev = current head), hash to what it says and carry a
valid signature of the station that sent it. An event already stored with the same hash is a harmless resend; the
same (unit, seq) with another hash is a conflict and is refused, as is anything else that does not fit. Accepted
events update the derived tables (units, attempts, recoveries) in the same transaction.
"""

from __future__ import annotations

import json
from collections import defaultdict
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Connection

from .. import keys
from ..trail.chain import event_hash, genesis
from . import db

DIM_FIELDS = {
    "fc_identify": {"board_rev": "fc_rev", "lot": "fc_lot"},
    "pmu_identify": {"board_rev": "pmu_rev", "lot": "pmu_lot"},
    "orin_identify": {"sku": "orin_sku", "fab": "orin_fab", "batch": "orin_batch"},
}


def station_keys() -> dict[str, str]:
    return {r["station"]: r["public_key"] for r in db.rows("select station, public_key from stations")}


def register_station(station: str, public_key: str) -> bool:
    """True if registered now or already with this key; False if the station exists with another key."""
    with db.begin() as c:
        existing = c.execute(text("select public_key from stations where station = :s"), {"s": station}).scalar()
        if existing is None:
            c.execute(
                text("insert into stations (station, public_key) values (:s, :k)"), {"s": station, "k": public_key}
            )
            return True
        return bool(existing == public_key)


def _dims(step: str, evidence: dict[str, Any]) -> dict[str, str]:
    if step == "scan_unit":  # what MES says the airframe is built from, before any board is read
        return {k: str(v) for k, v in (evidence.get("kit") or {}).items() if k in ("fc_lot", "pmu_lot", "orin_batch")}
    fields = DIM_FIELDS.get(step, {})
    source = evidence.get("unverified") or evidence
    return {name: str(source[k]) for k, name in fields.items() if k in source}


def _derive(c: Connection, e: dict[str, Any]) -> None:
    d, unit, at = e["data"], e["unit"], e["at"]
    if e["kind"] == "start":
        c.execute(
            text(
                """insert into units (unit, status, release, station, slot, runs, operator, started_at, updated_at)
                   values (:u, 'in_progress', :r, :st, :sl, 1, :op, :at, :at)
                   on conflict (unit) do update set status = 'in_progress', release = :r, station = :st, slot = :sl,
                     runs = units.runs + 1, operator = :op, step = null, hold_code = null, hold_owner = null, updated_at = :at"""
            ),
            {
                "u": unit,
                "r": d.get("release"),
                "st": e["station"],
                "sl": d.get("slot"),
                "op": d.get("operator"),
                "at": at,
            },
        )
    elif e["kind"] == "intent":
        c.execute(
            text("update units set step = :s, updated_at = :at where unit = :u"), {"s": d["step"], "at": at, "u": unit}
        )
    elif e["kind"] == "result":
        evidence = d.get("evidence") or {}
        dims = _dims(d["step"], evidence)
        if dims:
            c.execute(
                text("update units set dims = dims || cast(:d as jsonb) where unit = :u"),
                {"d": json.dumps(dims), "u": unit},
            )
        c.execute(
            text(
                """insert into attempts (unit, seq, run, step, attempt, ok, code, seconds, at, station, fixture, slot,
                                         release, operator, dims, evidence)
                   select :u, :seq, u.runs, :step, :att, :ok, :code, :sec, :at, :st, :fx, :sl, u.release, u.operator, u.dims,
                          cast(:ev as jsonb)
                   from units u where u.unit = :u"""
            ),
            {
                "u": unit,
                "seq": e["seq"],
                "step": d["step"],
                "att": d["attempt"],
                "ok": d["ok"],
                "code": d.get("code"),
                "sec": d.get("seconds", 0),
                "at": at,
                "st": e["station"],
                "fx": d.get("fixture", ""),
                "sl": d.get("slot", ""),
                "ev": json.dumps({k: v for k, v in evidence.items() if k != "certificate"}),
            },
        )
        if d["ok"] and d["step"] == "release_unit":
            c.execute(
                text(
                    """update units set status = 'released', step = null, updated_at = :at, certificate = cast(:cert as jsonb),
                         first_pass = (runs = 1 and not exists (
                            select 1 from attempts a where a.unit = :u and a.run = units.runs and not a.ok))
                       where unit = :u"""
                ),
                {"at": at, "u": unit, "cert": json.dumps(evidence.get("certificate"))},
            )
    elif e["kind"] == "recovery":
        c.execute(
            text(
                """insert into recoveries (unit, seq, step, code, action, seconds, at, slot)
                   values (:u, :seq, :step, :code, :act, :sec, :at, :sl)"""
            ),
            {
                "u": unit,
                "seq": e["seq"],
                "step": d["step"],
                "code": d["code"],
                "act": d["action"],
                "sec": d.get("seconds", 0),
                "at": at,
                "sl": d.get("slot", ""),
            },
        )
    elif e["kind"] == "hold":
        c.execute(
            text(
                """update units set status = 'held', step = :s, hold_code = :c, hold_owner = :o, first_pass = false,
                     hold_seconds = hold_seconds + :sec, updated_at = :at where unit = :u"""
            ),
            {"s": d["step"], "c": d["code"], "o": d["owner"], "sec": d.get("seconds", 0), "at": at, "u": unit},
        )


def ingest(events: list[dict[str, Any]]) -> dict[str, Any]:
    known = station_keys()
    by_unit: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for e in events:
        by_unit[e["unit"]].append(e)
    accepted, duplicates, rejected = 0, 0, []
    for unit, evs in by_unit.items():
        with db.begin() as c:
            c.execute(text("select pg_advisory_xact_lock(hashtext(:u))"), {"u": unit})
            row = c.execute(
                text("select seq, hash from trail where unit = :u order by seq desc limit 1"), {"u": unit}
            ).first()
            seq, head = (int(row[0]), str(row[1])) if row else (0, genesis(unit))
            for e in sorted(evs, key=lambda x: x["seq"]):
                if e["seq"] <= seq:
                    stored = c.execute(
                        text("select hash from trail where unit = :u and seq = :s"), {"u": unit, "s": e["seq"]}
                    ).scalar()
                    if stored == e["hash"]:
                        duplicates += 1
                    else:
                        rejected.append(
                            {"unit": unit, "seq": e["seq"], "why": "conflict: another event holds this place"}
                        )
                    continue
                why = None
                if e["seq"] != seq + 1:
                    why = f"gap: expected seq {seq + 1}"
                elif e["prev"] != head:
                    why = "does not follow the unit's last event"
                elif event_hash(e) != e["hash"]:
                    why = "hash does not match the content"
                elif e["station"] not in known or not keys.verify(
                    known[e["station"]], bytes.fromhex(e["hash"]), e["sig"]
                ):
                    why = f"not signed by a registered key of {e['station']}"
                if why:
                    rejected.append({"unit": unit, "seq": e["seq"], "why": why})
                    break  # nothing after a bad event can fit either
                c.execute(
                    text(
                        """insert into trail (unit, seq, hash, prev, station, kind, at, data, sig, raw)
                           values (:u, :s, :h, :p, :st, :k, :at, cast(:d as jsonb), :sig, :raw)"""
                    ),
                    {
                        "u": unit,
                        "s": e["seq"],
                        "h": e["hash"],
                        "p": e["prev"],
                        "st": e["station"],
                        "k": e["kind"],
                        "at": e["at"],
                        "d": json.dumps(e["data"]),
                        "sig": e["sig"],
                        "raw": json.dumps(e, sort_keys=True),
                    },
                )
                _derive(c, e)
                seq, head = e["seq"], e["hash"]
                accepted += 1
    return {"accepted": accepted, "duplicates": duplicates, "rejected": rejected}


def claim(kind: str, value: str, unit: str) -> str | None:
    with db.begin() as c:
        c.execute(
            text("insert into claims (kind, value, unit) values (:k, :v, :u) on conflict (kind, value) do nothing"),
            {"k": kind, "v": value, "u": unit},
        )
        owner = c.execute(
            text("select unit from claims where kind = :k and value = :v"), {"k": kind, "v": value}
        ).scalar()
    return None if owner == unit else str(owner)


def head(unit: str) -> tuple[int, str] | None:
    row = db.rows("select seq, hash from trail where unit = :u order by seq desc limit 1", u=unit)
    return (int(row[0]["seq"]), str(row[0]["hash"])) if row else None
