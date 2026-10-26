"""The digital paper trail of one airframe: an append-only chain of events, each carrying the hash of the one
before it and the station's signature.

The station writes an `intent` event before every action and a `result` event after it. A gap between them is
evidence: a crash, a power cut or a pulled cable mid-step leaves an intent without a result, and the next attempt
knows that step must be redone and checked, not assumed. Nothing in the chain is ever edited; a correction is a
new event.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from .. import keys


def genesis(unit: str) -> str:
    return hashlib.sha256(f"uav-trail:{unit}".encode()).hexdigest()


def event_hash(event: dict[str, Any]) -> str:
    body = {k: v for k, v in event.items() if k not in ("hash", "sig")}
    return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


@dataclass
class Chain:
    unit: str
    station: str
    key: Ed25519PrivateKey
    head: str = ""
    seq: int = 0
    events: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.head:
            self.head = genesis(self.unit)

    def append(self, kind: str, at: str, **data: Any) -> dict[str, Any]:
        self.seq += 1
        event = {
            "unit": self.unit,
            "seq": self.seq,
            "station": self.station,
            "kind": kind,
            "at": at,
            "prev": self.head,
            "data": data,
        }
        digest = event_hash(event)
        event["hash"] = digest
        event["sig"] = keys.sign(self.key, bytes.fromhex(digest))
        self.head = digest
        self.events.append(event)
        return event


def verify(events: list[dict[str, Any]], station_keys: dict[str, str]) -> list[str]:
    """Problems with a unit's chain, in order; empty if it is whole. station_keys: station -> public key (hex)."""
    problems: list[str] = []
    if not events:
        return ["no events"]
    head = genesis(events[0]["unit"])
    for i, e in enumerate(sorted(events, key=lambda x: x["seq"]), start=1):
        if e["seq"] != i:
            problems.append(f"event {i} is missing (found seq {e['seq']})")
            break
        if e["prev"] != head:
            problems.append(f"event {e['seq']} does not follow event {e['seq'] - 1}")
        if event_hash(e) != e["hash"]:
            problems.append(f"event {e['seq']} was altered after it was written")
        public = station_keys.get(e["station"])
        if public is None or not keys.verify(public, bytes.fromhex(e["hash"]), e["sig"]):
            problems.append(f"event {e['seq']} is not signed by station {e['station']}")
        head = e["hash"]
    return problems
