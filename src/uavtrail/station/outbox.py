"""The station's local copy of the trail. Every event is committed here before the action it announces, so the
trail survives a lost network or a station crash; a sender ships pending events to the traceability server, which
accepts each (unit, seq) once."""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any


class Outbox:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self.db.execute("pragma journal_mode=wal")
        self.db.execute("pragma synchronous=full")
        self.db.execute(
            "create table if not exists events (unit text, seq integer, hash text, body text, sent integer default 0, "
            "primary key (unit, seq))"
        )
        self.lock = threading.Lock()

    def put(self, event: dict[str, Any]) -> None:
        with self.lock:
            self.db.execute(
                "insert into events (unit, seq, hash, body) values (?, ?, ?, ?)",
                (event["unit"], event["seq"], event["hash"], json.dumps(event, sort_keys=True)),
            )

    def has(self, unit: str, event_hash: str) -> bool:
        with self.lock:
            return (
                self.db.execute("select 1 from events where unit = ? and hash = ?", (unit, event_hash)).fetchone()
                is not None
            )

    def pending(self, limit: int = 500) -> list[dict[str, Any]]:
        with self.lock:
            rows = self.db.execute("select body from events where sent = 0 order by rowid limit ?", (limit,)).fetchall()
        return [json.loads(r[0]) for r in rows]

    def mark_sent(self, events: list[dict[str, Any]]) -> None:
        with self.lock:
            self.db.executemany(
                "update events set sent = 1 where unit = ? and seq = ?", [(e["unit"], e["seq"]) for e in events]
            )

    def backlog(self) -> int:
        with self.lock:
            return int(self.db.execute("select count(*) from events where sent = 0").fetchone()[0])

    def close(self) -> None:
        self.db.close()
