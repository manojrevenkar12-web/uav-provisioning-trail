"""Runs a held-out set of campaigns (written by someone who has not seen the code, from
heldout/WRITING_CAMPAIGNS.md only) and scores the analysis and the trail on them.

The first run of a set is written once to reports/heldout/<set>/first_run.json and never rewritten; every later
run goes to latest.json. CI checks that the first run has not changed.
"""

from __future__ import annotations

import datetime as dt
import json
from typing import Any

from uavtrail import evaluate
from uavtrail.config import data_dir, root
from uavtrail.server import db

from . import campaign as campaigns
from .line import run


def score(set_name: str, units: int | None = None) -> dict[str, Any]:
    base = root() / "heldout" / set_name
    status = (base / "STATUS").read_text().strip() if (base / "STATUS").exists() else "held-out"
    results = []
    for path in sorted((base / "campaigns").glob("*.yaml")):
        c = campaigns.load(path)
        db.reset()
        out = data_dir() / "heldout" / set_name / c.name
        summary = run(c, out, units)
        ev = evaluate.run(out)
        results.append(
            {
                "campaign": c.name,
                "units": summary["units"],
                "issues": ev["issues"],
                "trail": {
                    "chains_broken": len(ev["trail"]["chains_broken"]),
                    "certificates_bad": len(ev["trail"]["certificates_bad"]),
                    "released": ev["trail"]["released"],
                },
                "irreversible": ev["irreversible"],
            }
        )
    expected = sum(r["issues"]["expected"] for r in results)
    found = sum(r["issues"]["found"] for r in results)
    report = {
        "set": set_name,
        "status": status,
        "run_at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        "campaigns": len(results),
        "systemic_found": {"found": found, "of": expected, "rate": round(found / expected, 3) if expected else None},
        "false_alarms": sum(len(r["issues"]["false_alarms"]) for r in results),
        "chains_broken": sum(r["trail"]["chains_broken"] for r in results),
        "certificates_bad": sum(r["trail"]["certificates_bad"] for r in results),
        "unguarded_burns": sum(len(r["irreversible"]["unguarded"]) for r in results),
        "results": results,
    }
    out_dir = root() / "reports" / "heldout" / set_name
    out_dir.mkdir(parents=True, exist_ok=True)
    first = out_dir / "first_run.json"
    text = json.dumps(report, indent=1, default=str)
    if not first.exists():
        first.write_text(text)
        report["recorded_as"] = "first_run"
    (out_dir / "latest.json").write_text(text)
    return report


def summary_line(report: dict[str, Any]) -> str:
    s = report["systemic_found"]
    return (
        f"{report['set']} ({report['status']}): {s['found']}/{s['of']} systemic causes named, "
        f"{report['false_alarms']} false alarms, {report['chains_broken']} broken trails, "
        f"{report['unguarded_burns']} unguarded burns over {report['campaigns']} campaigns"
    )
