"""The numbers a production-support lead is measured on, from the trail.

- software first-pass yield: airframes released in their first run with no failed attempt, of those finished
- flash success: program and image-flash attempts that succeeded, of all such attempts
- downtime: slot minutes lost to failed attempts, the recoveries they caused and holds
- final yield: released of started, after rework
"""

from __future__ import annotations

from typing import Any

from ..server import db

FLASH_STEPS = ("fc_program", "pmu_program", "orin_flash")


def summary() -> dict[str, Any]:
    u = db.rows(
        """select count(*) as started,
                  count(*) filter (where status = 'released') as released,
                  count(*) filter (where status = 'held') as held,
                  count(*) filter (where status = 'in_progress') as in_progress,
                  count(*) filter (where status = 'released' and first_pass) as first_pass,
                  count(*) filter (where status <> 'in_progress') as finished,
                  coalesce(sum(hold_seconds), 0) as hold_seconds,
                  count(*) filter (where runs > 1) as reworked
           from units"""
    )[0]
    f = db.rows(
        """select count(*) as attempts, count(*) filter (where ok) as ok,
                  count(*) filter (where ok and attempt = 1) as first_ok,
                  count(*) filter (where attempt = 1) as first
           from attempts where step = any(:steps)""",
        steps=list(FLASH_STEPS),
    )[0]
    lost = db.scalar("select coalesce(sum(seconds), 0) from attempts where not ok") or 0
    rec = db.scalar("select coalesce(sum(seconds), 0) from recoveries") or 0
    span = db.rows("select min(at) as first, max(at) as last from attempts")[0]
    cycle = db.scalar(
        """select percentile_cont(0.5) within group (order by extract(epoch from (r.at - s.at)))
           from trail s join trail r on r.unit = s.unit and r.kind = 'result' and r.data->>'step' = 'release_unit'
                                     and (r.data->>'ok')::boolean
           where s.kind = 'start' and s.seq = (select max(seq) from trail x where x.unit = s.unit and x.kind = 'start' and x.seq < r.seq)"""
    )
    return {
        "units": {k: int(v) for k, v in u.items() if k != "hold_seconds"},
        "first_pass_yield": _share(u["first_pass"], u["finished"]),
        "final_yield": _share(u["released"], u["started"]),
        "flash_success": _share(f["ok"], f["attempts"]),
        "flash_first_attempt": _share(f["first_ok"], f["first"]),
        "downtime_minutes": round((float(lost) + float(rec) + float(u["hold_seconds"])) / 60, 1),
        "cycle_minutes_median": round(float(cycle) / 60, 1) if cycle else None,
        "window": {
            "from": span["first"].isoformat() if span["first"] else None,
            "to": span["last"].isoformat() if span["last"] else None,
        },
    }


def _share(k: Any, n: Any) -> dict[str, Any]:
    k, n = int(k or 0), int(n or 0)
    return {"value": round(k / n, 4) if n else None, "of": n, "count": k}


def by_slot() -> list[dict[str, Any]]:
    return db.rows(
        """with lost as (
             select slot, sum(seconds) as s from attempts where not ok group by slot
             union all select slot, sum(seconds) from recoveries group by slot
             union all select slot, sum(hold_seconds) from units group by slot),
           l as (select slot, sum(s) / 60 as lost_minutes from lost group by slot),
           u as (select slot, count(*) as units,
                        count(*) filter (where status = 'released' and first_pass) as first_pass,
                        count(*) filter (where status <> 'in_progress') as finished,
                        count(*) filter (where status = 'held') as held
                 from units group by slot),
           top as (select distinct on (slot) slot, code, count(*) as n from attempts where not ok group by slot, code
                   order by slot, count(*) desc)
           select u.slot, split_part(u.slot, '/', 1) as fixture, u.units, u.held,
                  case when u.finished > 0 then round(u.first_pass::numeric / u.finished, 4) end as first_pass_yield,
                  round(coalesce(l.lost_minutes, 0)::numeric, 1) as lost_minutes, top.code as top_code, top.n as top_code_failures
           from u left join l using (slot) left join top using (slot) order by u.slot"""
    )


def by_hour() -> list[dict[str, Any]]:
    return db.rows(
        """select date_trunc('hour', at) as hour,
                  count(*) filter (where step = 'release_unit' and ok) as released,
                  count(*) filter (where not ok) as failures,
                  count(*) filter (where step = any(:steps)) as flashes,
                  count(*) filter (where step = any(:steps) and ok) as flashes_ok
           from attempts group by 1 order by 1""",
        steps=list(FLASH_STEPS),
    )


def pareto() -> list[dict[str, Any]]:
    return db.rows(
        """select code, count(*) as failures, count(distinct unit) as units, round(sum(seconds)::numeric / 60, 1) as lost_minutes
           from attempts where not ok group by code order by count(*) desc"""
    )
