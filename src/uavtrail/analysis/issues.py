"""One-off or systemic: the question a production-support lead answers every morning.

For each failure code, every attempt at the steps where that code occurs is a trial. The analysis looks for the
place (a value of one dimension: a slot, an operator, a release, a supplier lot...) whose failure rate stands out
from the rest of the line beyond what chance explains (config/analysis.yaml). The best such place becomes a
systemic issue; its failures are set aside and the search repeats for a second and third place. Failures no place
explains are one-offs, unless the code fails so often everywhere that it is systemic without a place.
"""

from __future__ import annotations

import hashlib
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from typing import Any

from ..config import analysis as settings
from ..config import codes as code_book
from .stats import hypergeom_tail, wilson


@dataclass
class Issue:
    key: str
    code: str
    label: str
    owner: str
    kind: str  # systemic | widespread | one_off
    where: list[dict[str, str]]  # [{dimension, value}], most telling first
    failures: int
    attempts: int
    rate: float
    rest_rate: float | None
    p_value: float | None
    units: int
    first_seen: str
    last_seen: str
    lost_minutes: float
    action: str
    examples: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _value(row: dict[str, Any], dim: str) -> str | None:
    if dim in ("slot", "fixture", "station", "operator", "release"):
        v = row.get(dim)
    else:
        v = (row.get("dims") or {}).get(dim)
    return None if v in (None, "") else str(v)


def _best_place(
    rows: list[dict[str, Any]], code: str, dims: list[str], cfg: dict[str, Any], tests: int
) -> dict[str, Any] | None:
    found: list[dict[str, Any]] = []
    for dim in dims:
        known = [r for r in rows if _value(r, dim) is not None]
        values = Counter(_value(r, dim) for r in known)
        if len(values) < 2:
            continue
        fails = Counter(_value(r, dim) for r in known if r["code"] == code)
        total_fail = sum(fails.values())
        for v, n_v in values.items():
            k_v = fails.get(v, 0)
            if k_v < cfg["min_failures"]:
                continue
            n_r, k_r = len(known) - n_v, total_fail - k_v
            rate, rest = k_v / n_v, (k_r / n_r if n_r else 0.0)
            if rest and rate < cfg["min_lift"] * rest:
                continue
            # given all failures of this code, how surprising is it that this many fell here? Fisher's exact test:
            # the failures are a draw from all attempts, and the rest of the line's rate is not taken as known.
            p = hypergeom_tail(k_v, len(known), n_v, total_fail)
            if p > cfg["alpha"] / max(tests, 1):
                continue
            found.append(
                {
                    "dimension": dim,
                    "value": v,
                    "k": k_v,
                    "n": n_v,
                    "rate": rate,
                    "rest": k_r / n_r if n_r else 0.0,
                    "p": p,
                    "spec": cfg["specificity"].get(dim, 1),
                }
            )
    if not found:
        return None
    best = min(found, key=lambda c: c["p"])
    # a narrower place that explains nearly the same failures is the more useful answer (the slot, not its station)
    narrower = [c for c in found if c["spec"] < best["spec"] and c["k"] >= 0.8 * best["k"]]
    return min(narrower, key=lambda c: (c["spec"], c["p"])) if narrower else best


def with_signals(attempts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Adds degradation signals as trials of their own: every successful enumeration is a trial of `slow_link`,
    failed when the module linked at USB2. A cable going bad shows here long before it stops enumerating."""
    out = list(attempts)
    for r in attempts:
        if r["step"] == "orin_enumerate" and r["ok"]:
            slow = bool((r.get("evidence") or {}).get("slow_link"))
            out.append(
                r | {"step": "orin_link_speed", "ok": not slow, "code": "slow_link" if slow else None, "seconds": 0.0}
            )
    return out


def analyse(attempts: list[dict[str, Any]], recoveries: list[dict[str, Any]] | None = None) -> list[Issue]:
    cfg = settings()
    attempts = with_signals(attempts)
    book = code_book()
    dims: list[str] = list(cfg["dimensions"])
    by_code_steps: dict[str, set[str]] = defaultdict(set)
    for r in attempts:
        if not r["ok"] and r["code"]:
            by_code_steps[r["code"]].add(r["step"])
    recovery_seconds: dict[tuple[str, str], float] = defaultdict(float)
    for rec in recoveries or []:
        recovery_seconds[(rec["unit"], rec["code"])] += float(rec["seconds"])
    issues: list[Issue] = []
    for code, steps in sorted(by_code_steps.items()):
        rows = [r for r in attempts if r["step"] in steps]
        # every place this code could be pinned on: the family the significance level is divided over
        tests = sum(len({_value(r, d) for r in rows} - {None}) for d in dims)
        meta = book.get(code, {"label": code, "owner": "engineering"})
        for _ in range(int(cfg["max_issues_per_code"])):
            place = _best_place(rows, code, dims, cfg, tests)
            if place is None:
                break
            inside = [r for r in rows if _value(r, place["dimension"]) == place["value"]]
            where = [{"dimension": place["dimension"], "value": place["value"]}]
            sub = _best_place(inside, code, [d for d in dims if d != place["dimension"]], cfg, tests)
            if sub and sub["k"] >= 0.8 * place["k"]:
                where.append({"dimension": sub["dimension"], "value": sub["value"]})
            issues.append(_issue(code, meta, "systemic", where, inside, place, cfg, recovery_seconds))
            rows = [r for r in rows if _value(r, place["dimension"]) != place["value"]]
        left = [r for r in rows if r["code"] == code]
        if left:
            rate = len(left) / len(rows) if rows else 0.0
            kind = "widespread" if rate >= cfg["widespread_rate"] and len(left) >= cfg["min_failures"] else "one_off"
            issues.append(_issue(code, meta, kind, [], rows, None, cfg, recovery_seconds))
    order = {"systemic": 0, "widespread": 1, "one_off": 2}
    return sorted(issues, key=lambda i: (order[i.kind], -i.lost_minutes))


def _issue(
    code: str,
    meta: dict[str, Any],
    kind: str,
    where: list[dict[str, str]],
    rows: list[dict[str, Any]],
    place: dict[str, Any] | None,
    cfg: dict[str, Any],
    recovery_seconds: dict[tuple[str, str], float],
) -> Issue:
    failed = [r for r in rows if r["code"] == code]
    units = sorted({r["unit"] for r in failed})
    lost = sum(float(r["seconds"]) for r in failed) + sum(recovery_seconds.get((u, code), 0.0) for u in units)
    ident = code + "|" + "|".join(f"{w['dimension']}={w['value']}" for w in where) + ("" if where else f"|{kind}")
    times = sorted(str(r["at"]) for r in failed)
    if kind == "systemic":
        action = cfg["actions"].get(where[0]["dimension"], "")
    elif kind == "widespread":
        action = "Systemic with no single place to blame: review the step itself with engineering."
    else:
        action = "No pattern: handle unit by unit; watch whether it recurs."
    return Issue(
        key=hashlib.sha256(ident.encode()).hexdigest()[:12],
        code=code,
        label=str(meta.get("label", code)),
        owner=str(meta.get("owner", "engineering")),
        kind=kind,
        where=where,
        failures=len(failed),
        attempts=len(rows),
        rate=round(len(failed) / len(rows), 4) if rows else 0.0,
        rest_rate=round(place["rest"], 4) if place else None,
        p_value=place["p"] if place else None,
        units=len(units),
        first_seen=times[0] if times else "",
        last_seen=times[-1] if times else "",
        lost_minutes=round(lost / 60, 1),
        action=action,
        examples=units[:5],
    )


def watch_list(attempts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Slots whose modules enumerate at USB2: a cable or port going bad, usually before it starts failing."""
    cfg = settings()["watch"]
    per_slot: dict[str, list[bool]] = defaultdict(list)
    for r in attempts:
        if r["step"] == "orin_enumerate" and r["ok"]:
            per_slot[r["slot"]].append(bool((r.get("evidence") or {}).get("slow_link")))
    out = []
    for slot, flags in sorted(per_slot.items()):
        share = sum(flags) / len(flags)
        if len(flags) >= cfg["min_units"] and share >= cfg["slow_link_share"]:
            lo, hi = wilson(sum(flags), len(flags))
            out.append(
                {
                    "slot": slot,
                    "signal": "slow_link",
                    "share": round(share, 3),
                    "units": len(flags),
                    "interval": [round(lo, 3), round(hi, 3)],
                    "why": "modules on this slot enumerate at USB2: flashes take about three times as long and the link is marginal",
                }
            )
    return out
