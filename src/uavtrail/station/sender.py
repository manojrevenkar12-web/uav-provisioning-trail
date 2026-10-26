"""Ships the outbox to the traceability server. Resends are harmless (the server accepts each event once); a
rejected event stays pending and is reported, because a trail the server refuses is a problem to look at."""

from __future__ import annotations

from typing import Any

import httpx

from .outbox import Outbox


class Sender:
    def __init__(self, outbox: Outbox, base_url: str, token: str | None = None) -> None:
        self.outbox = outbox
        headers = {"authorization": f"Bearer {token}"} if token else {}
        self.http = httpx.Client(base_url=base_url, timeout=15.0, headers=headers)
        self.rejected: list[dict[str, Any]] = []

    def register(self, station: str, public_key: str) -> None:
        r = self.http.post("/api/stations", json={"station": station, "public_key": public_key})
        r.raise_for_status()

    def flush(self) -> int:
        """Sends everything pending; returns how many events the server now holds from this batch."""
        sent = 0
        while batch := self.outbox.pending():
            try:
                r = self.http.post("/api/trail", json={"events": batch})
            except httpx.HTTPError:
                return sent  # offline: the events stay in the outbox
            if r.status_code >= 400:
                return sent
            body = r.json()
            bad = {(x["unit"], x["seq"]) for x in body["rejected"]}
            ok = [e for e in batch if (e["unit"], e["seq"]) not in bad]
            self.outbox.mark_sent(ok)
            self.rejected += body["rejected"]
            sent += len(ok)
            if bad:
                return sent
        return sent
