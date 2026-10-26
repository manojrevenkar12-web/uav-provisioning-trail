"""The traceability server: stations post their trail and claim identities here; the console and people read it.

Who is asking: with UAV_API_TOKENS set ("token:actor:role,..."), a bearer token decides; otherwise (development)
the x-uav-role and x-uav-actor headers do. Roles: station, operator, lead, engineering, quality.
"""

from __future__ import annotations

import datetime as dt
import os
from pathlib import Path
from typing import Annotated, Any

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from ..config import root
from . import db, ingest

app = FastAPI(title="uav-provisioning-trail", version="0.1.0")
ROLES = ("station", "operator", "lead", "engineering", "quality")


class Caller(BaseModel):
    actor: str
    role: str


def caller(request: Request) -> Caller:
    tokens = os.environ.get("UAV_API_TOKENS")
    if tokens:
        auth = request.headers.get("authorization", "")
        given = auth.removeprefix("Bearer ").strip()
        for entry in tokens.split(","):
            token, actor, role = entry.split(":")
            if given and given == token:
                return Caller(actor=actor, role=role)
        raise HTTPException(401, "a valid bearer token is required")
    role = request.headers.get("x-uav-role", "lead")
    if role not in ROLES:
        raise HTTPException(400, f"unknown role {role}")
    return Caller(actor=request.headers.get("x-uav-actor", "") or f"dev-{role}", role=role)


Who = Annotated[Caller, Depends(caller)]


def need(who: Caller, *roles: str) -> None:
    if who.role not in roles:
        raise HTTPException(403, f"{who.role} cannot do this; it needs {' or '.join(roles)}")


@app.exception_handler(HTTPException)
async def problem(_: Request, exc: HTTPException) -> JSONResponse:
    return JSONResponse(
        {"title": str(exc.detail), "status": exc.status_code},
        status_code=exc.status_code,
        media_type="application/problem+json",
    )


@app.exception_handler(RequestValidationError)
async def invalid(_: Request, exc: RequestValidationError) -> JSONResponse:
    detail = "; ".join(f"{'.'.join(str(p) for p in e['loc'][1:])}: {e['msg']}" for e in exc.errors())
    return JSONResponse(
        {"title": "the request is not valid", "status": 422, "detail": detail},
        status_code=422,
        media_type="application/problem+json",
    )


# --------------------------------------------------------------------------- stations


class StationIn(BaseModel):
    station: str = Field(pattern=r"^[A-Z0-9-]{2,20}$")
    public_key: str = Field(pattern=r"^[0-9a-f]{64}$")


@app.post("/api/stations")
def register(body: StationIn, who: Who) -> dict[str, Any]:
    need(who, "station", "lead")
    if not ingest.register_station(body.station, body.public_key):
        raise HTTPException(409, f"{body.station} is registered with another key")
    return {"station": body.station, "registered": True}


class TrailIn(BaseModel):
    events: list[dict[str, Any]] = Field(max_length=2000)


@app.post("/api/trail")
def trail(body: TrailIn, who: Who) -> dict[str, Any]:
    need(who, "station", "lead")
    return ingest.ingest(body.events)


class ClaimIn(BaseModel):
    kind: str = Field(pattern=r"^(fc_uid|pmu_uid|orin_serial|machine_id)$")
    value: str = Field(min_length=1, max_length=64)
    unit: str = Field(min_length=3, max_length=32)


@app.post("/api/registry/claims")
def claim(body: ClaimIn, who: Who) -> JSONResponse:
    need(who, "station", "lead")
    owner = ingest.claim(body.kind, body.value, body.unit)
    if owner:
        return JSONResponse({"owner": owner}, status_code=409)
    return JSONResponse({"owner": body.unit})


@app.get("/api/units/{unit}/head")
def unit_head(unit: str, _: Who) -> dict[str, Any]:
    h = ingest.head(unit)
    if h is None:
        raise HTTPException(404, "no trail for this unit")
    return {"seq": h[0], "hash": h[1]}


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "events": db.scalar("select count(*) from trail"),
        "time": dt.datetime.now(dt.UTC).isoformat(),
    }


# --------------------------------------------------------------------------- reading


@app.get("/api/overview")
def overview(_: Who) -> dict[str, Any]:
    from ..analysis import kpi
    from ..analysis.issues import analyse, watch_list

    attempts = db.rows("select * from attempts")
    found = analyse(attempts, db.rows("select * from recoveries"))
    return {
        "kpis": kpi.summary(),
        "systemic": [i.as_dict() for i in found if i.kind != "one_off"][:6],
        "one_off": sum(i.failures for i in found if i.kind == "one_off"),
        "watch": watch_list(attempts),
        "hours": kpi.by_hour(),
        "pareto": kpi.pareto()[:8],
    }


@app.get("/api/codes")
def codes_(_: Who) -> dict[str, Any]:
    """The failure vocabulary (config/codes.yaml): what each code means and who owns it."""
    from ..config import codes

    return {
        k: {"label": v.get("label", k), "owner": v.get("owner"), "signal": bool(v.get("signal"))}
        for k, v in codes().items()
    }


@app.get("/api/slots")
def slots(_: Who) -> list[dict[str, Any]]:
    """Every slot of the line: what is on it now and how it has done."""
    from ..analysis import kpi
    from ..config import line

    stats = {r["slot"]: r for r in kpi.by_slot()}
    current = {
        r["slot"]: r
        for r in db.rows(
            """select distinct on (slot) slot, unit, status, step, hold_code, hold_owner, release, updated_at
           from units where slot is not null order by slot, updated_at desc"""
        )
    }
    recent: dict[str, list[dict[str, Any]]] = {}
    for r in db.rows(
        """select slot, unit, status, hold_code from (
             select slot, unit, status, hold_code, row_number() over (partition by slot order by updated_at desc) as n
             from units where slot is not null) x
           where n <= :n order by slot, n desc""",
        n=12,
    ):
        recent.setdefault(r["slot"], []).append({"unit": r["unit"], "status": r["status"], "hold_code": r["hold_code"]})
    out = []
    for station, st in line()["stations"].items():
        for fixture, count in st["fixtures"].items():
            for i in range(1, count + 1):
                name = f"{fixture}/{i}"
                out.append(
                    {
                        "slot": name,
                        "station": station,
                        "fixture": fixture,
                        "index": i,
                        "current": current.get(name),
                        "stats": stats.get(name),
                        "recent": recent.get(name, []),
                    }
                )
    return out


@app.get("/api/issues")
def issues(_: Who) -> dict[str, Any]:
    from ..analysis.issues import analyse, watch_list

    attempts = db.rows("select * from attempts")
    found = [i.as_dict() for i in analyse(attempts, db.rows("select * from recoveries"))]
    actions = db.rows("select * from issue_actions order by at")
    for i in found:
        i["actions"] = [a for a in actions if a["issue"] == i["key"]]
        i["effect"] = _effect(i, attempts)
    return {"issues": found, "watch": watch_list(attempts)}


def _effect(issue: dict[str, Any], attempts: list[dict[str, Any]]) -> dict[str, Any] | None:
    """For an issue marked fixed: its failure rate in its place before and after the fix took effect."""
    fixes = [a for a in issue["actions"] if a["action"] == "fixed"]
    if not fixes or not issue["where"]:
        return None
    t = fixes[-1]["effective_at"]
    w = issue["where"][0]

    def place(r: dict[str, Any]) -> Any:
        return (
            r.get(w["dimension"])
            if w["dimension"] in ("slot", "fixture", "station", "operator", "release")
            else (r.get("dims") or {}).get(w["dimension"])
        )

    steps = {r["step"] for r in attempts if r["code"] == issue["code"]}
    rows = [r for r in attempts if r["step"] in steps and place(r) == w["value"]]
    before = [r for r in rows if r["at"] < t]
    after = [r for r in rows if r["at"] >= t]

    def rate(rs: list[dict[str, Any]]) -> dict[str, Any]:
        k = sum(1 for r in rs if r["code"] == issue["code"])
        return {"failures": k, "attempts": len(rs), "rate": round(k / len(rs), 4) if rs else None}

    b, a = rate(before), rate(after)
    holding = a["attempts"] >= 5 and (a["rate"] or 0) <= (b["rate"] or 0) / 3
    return {
        "since": t.isoformat(),
        "before": b,
        "after": a,
        "verdict": "holding" if holding else ("too early to tell" if a["attempts"] < 5 else "not holding"),
    }


class ActionIn(BaseModel):
    action: str = Field(pattern=r"^(acknowledge|fixed|not_a_problem|note)$")
    note: str = Field(min_length=3, max_length=2000)
    owner: str | None = Field(default=None, pattern=r"^(production|engineering|quality|supplier)$")
    effective_at: dt.datetime | None = None


@app.post("/api/issues/{key}/actions")
def act(key: str, body: ActionIn, who: Who) -> dict[str, Any]:
    need(who, "lead", "engineering", "quality")
    if not key.isalnum() or len(key) != 12:
        raise HTTPException(404, "no such issue")
    effective = body.effective_at or dt.datetime.now(dt.UTC)
    with db.begin() as c:
        from sqlalchemy import text

        row = (
            c.execute(
                text(
                    """insert into issue_actions (issue, action, owner, note, actor, effective_at)
                   values (:i, :a, :o, :n, :w, :e) returning *"""
                ),
                {"i": key, "a": body.action, "o": body.owner, "n": body.note, "w": who.actor, "e": effective},
            )
            .mappings()
            .one()
        )
    return dict(row)


@app.get("/api/units")
def units(
    _: Who,
    status: str | None = Query(None, pattern=r"^(released|held|in_progress)$"),
    q: str | None = Query(None, max_length=32),
    slot: str | None = Query(None, max_length=16),
    code: str | None = Query(None, pattern=r"^[a-z_]{3,40}$"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    where = """(cast(:st as text) is null or status = :st) and (cast(:q as text) is null or unit ilike :ql)
               and (cast(:sl as text) is null or slot = :sl) and (cast(:c as text) is null or hold_code = :c)"""
    params = {"st": status, "q": q, "ql": f"%{q or ''}%", "sl": slot, "c": code}
    total = db.scalar(f"select count(*) from units where {where}", **params)
    rows = db.rows(
        f"""select unit, status, release, station, slot, step, hold_code, hold_owner, runs, first_pass, operator, dims,
                   started_at, updated_at from units where {where} order by updated_at desc, unit limit :n offset :o""",
        **params,
        n=limit,
        o=offset,
    )
    return {"total": total, "rows": rows}


@app.get("/api/units/{unit}")
def unit(unit: str, _: Who) -> dict[str, Any]:
    from .. import evaluate

    row = db.rows("select * from units where unit = :u", u=unit)
    if not row:
        raise HTTPException(404, "no such unit")
    events = db.rows("select seq, kind, at, station, hash, prev, data from trail where unit = :u order by seq", u=unit)
    for e in events:
        if e["kind"] == "result" and e["data"].get("step") == "release_unit":
            e["data"].pop("evidence", None)  # the certificate has its own endpoint
    broken = evaluate.chains(unit).get(unit, [])
    return {
        "unit": row[0],
        "events": events,
        "chain": {"verified": not broken, "problems": broken, "events": len(events)},
    }


@app.get("/api/units/{unit}/certificate")
def certificate(unit: str, _: Who) -> dict[str, Any]:
    cert = db.scalar("select certificate from units where unit = :u and status = 'released'", u=unit)
    if not cert:
        raise HTTPException(404, "no certificate: the unit is not released")
    return dict(cert)


@app.get("/api/releases")
def releases_(_: Who) -> list[dict[str, Any]]:
    import yaml

    out = []
    counts = {
        r["release"]: r
        for r in db.rows(
            """select release, count(*) filter (where status = 'released') as released,
                  count(*) filter (where status = 'held') as held, count(*) as units from units group by release"""
        )
    }
    for path in sorted((root() / "releases").glob("*.yaml")):
        spec = yaml.safe_load(path.read_text())
        out.append(
            {
                "release": spec["release"],
                "product": spec["product"],
                "artifacts": {t: a["version"] for t, a in spec["artifacts"].items()},
                "compatible": spec["compatible"],
                "units": counts.get(spec["release"], {}),
            }
        )
    return out


@app.get("/api/where-used")
def where_used(
    _: Who, target: str = Query(pattern=r"^(fc|pmu|orin)$"), version: str = Query(pattern=r"^[0-9.]{3,16}$")
) -> dict[str, Any]:
    """Every released airframe carrying this version: the recall list when a version turns out bad."""
    rows = db.rows(
        """select unit, release, slot, updated_at as released_at from units
           where status = 'released' and certificate->'certificate'->'installed'->:t->>'version' = :v order by unit""",
        t=target,
        v=version,
    )
    return {"target": target, "version": version, "units": rows}


@app.get("/api/instructions")
def instructions_(_: Who, release: str = Query(pattern=r"^R[0-9.]{4,12}$")) -> dict[str, Any]:
    import yaml

    from ..analysis import instructions
    from ..config import recipe

    path = root() / "releases" / f"{release}.yaml"
    if not path.exists():
        raise HTTPException(404, f"no release {release}")
    spec = yaml.safe_load(path.read_text())
    doc = instructions.load(spec["instruction"])
    return {
        "document": doc["document"],
        "revision": doc["revision"],
        "release": release,
        "findings": instructions.check(doc, recipe(spec["recipe"]), spec),
    }


def mount_console() -> None:
    web = Path(os.environ.get("UAV_WEB", root() / "web" / "dist"))
    if not web.exists():
        return
    app.mount("/assets", StaticFiles(directory=web / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def console(path: str) -> FileResponse:
        if path.startswith("api/"):
            raise HTTPException(404, "no such endpoint")
        f = web / path
        return FileResponse(f if path and f.is_file() else web / "index.html")
