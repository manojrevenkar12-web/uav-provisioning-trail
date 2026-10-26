"""Measures the station and the analysis against what the emulated line really injected. The only module that
reads a run's truth.json (tests/test_isolation.py checks it).

- issues: every systemic fault is named (same code, its place among the issue's places); no systemic issue is
  raised that the truth does not explain
- trail: every unit's chain verifies, every released unit has a certificate whose signature verifies
- irreversible: every module the line fused was fused in a run whose trail shows verify and first boot passed
  before the burn, and the trail records every burn the modules carry
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from . import keys
from .analysis.issues import analyse
from .releases import canonical
from .server import db
from .trail.chain import verify


def issues(truth: dict[str, Any]) -> dict[str, Any]:
    found = analyse(db.rows("select * from attempts"), db.rows("select * from recoveries"))
    systemic = [i for i in found if i.kind == "systemic"]
    matched: dict[str, str] = {}
    used: set[str] = set()
    for exp in truth["expected"]:
        for i in systemic:  # a fault may show as more than one issue (a bad cable: failures and slow links)
            places = {(w["dimension"], w["value"]) for w in i.where}
            if i.code in exp.get("codes", [exp["code"]]) and (exp["dimension"], exp["value"]) in places:
                matched.setdefault(exp["fault"], i.key)
                used.add(i.key)
    false_alarms = [i.as_dict() for i in systemic if i.key not in used]
    return {
        "expected": len(truth["expected"]),
        "found": len(matched),
        "missed": [e for e in truth["expected"] if e["fault"] not in matched],
        "false_alarms": [{"code": f["code"], "where": f["where"], "failures": f["failures"]} for f in false_alarms],
        "one_off_groups": sum(1 for i in found if i.kind == "one_off"),
    }


def chains(unit: str | None = None) -> dict[str, list[str]]:
    """Every unit (or the one given) whose stored trail does not verify, with what is wrong."""
    station_keys = {r["station"]: r["public_key"] for r in db.rows("select station, public_key from stations")}
    events: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in db.rows(
        "select unit, raw from trail where cast(:u as text) is null or unit = :u order by unit, seq", u=unit
    ):
        events[r["unit"]].append(json.loads(r["raw"]))
    return {u: p for u, evs in events.items() if (p := verify(evs, station_keys))}


def trail() -> dict[str, Any]:
    broken = chains()
    certs = db.rows("select unit, certificate from units where status = 'released'")
    bad_certs = []
    for c in certs:
        cert = c["certificate"] or {}
        ok = bool(cert) and keys.verify(cert["station_key"], canonical(cert["certificate"]), cert["signature"])
        if not ok:
            bad_certs.append(c["unit"])
    units = db.scalar("select count(distinct unit) from trail")
    return {
        "units": units,
        "chains_broken": [{"unit": u, "problems": p[:3]} for u, p in broken.items()],
        "released": len(certs),
        "certificates_bad": bad_certs,
    }


def irreversible(truth: dict[str, Any]) -> dict[str, Any]:
    burns = db.rows(
        """select a.unit, a.run, a.seq from attempts a
           where a.step = 'orin_fuse' and a.ok and (a.evidence->>'burnt')::boolean"""
    )
    unguarded = []
    for b in burns:
        prior = {
            r["step"]
            for r in db.rows(
                "select step from attempts where unit = :u and run = :r and ok and seq < :s",
                u=b["unit"],
                r=b["run"],
                s=b["seq"],
            )
        }
        if not {"orin_verify", "orin_first_boot"} <= prior:
            unguarded.append(b["unit"])
    fused_in_truth = {u["unit"] for u in truth.get("fused", [])}
    burnt_in_trail = {b["unit"] for b in burns}
    return {"burns": len(burns), "unguarded": unguarded, "burnt_without_trail": sorted(fused_in_truth - burnt_in_trail)}


def run(run_dir: Path) -> dict[str, Any]:
    truth = json.loads((run_dir / "truth.json").read_text())
    return {
        "campaign": truth["campaign"],
        "issues": issues(truth),
        "trail": trail(),
        "irreversible": irreversible(truth),
    }
