"""Which unit a board, a module or a machine-id belongs to. A claim is atomic and first-come: the second airframe
to claim the same flight-controller UID or the same machine-id is told who owns it."""

from __future__ import annotations

import threading
from typing import Any, Protocol

import httpx

from ..targets.errors import TargetError


class Registry(Protocol):
    def claim(self, kind: str, value: str, unit: str) -> str | None:
        """None if `unit` now holds the claim; otherwise the unit that already does."""

    def head(self, unit: str) -> tuple[int, str] | None:
        """The last (seq, hash) recorded for a unit, so a re-run continues its chain."""


class LocalRegistry:
    def __init__(self) -> None:
        self.claims: dict[tuple[str, str], str] = {}
        self.heads: dict[str, tuple[int, str]] = {}
        self.lock = threading.Lock()

    def claim(self, kind: str, value: str, unit: str) -> str | None:
        with self.lock:
            owner = self.claims.setdefault((kind, value), unit)
            return None if owner == unit else owner

    def head(self, unit: str) -> tuple[int, str] | None:
        return self.heads.get(unit)


class ServerRegistry:
    def __init__(self, base_url: str, token: str | None = None, timeout: float = 5.0) -> None:
        headers = {"authorization": f"Bearer {token}"} if token else {}
        self.http = httpx.Client(base_url=base_url, timeout=timeout, headers=headers)

    def _call(self, method: str, path: str, **kw: Any) -> httpx.Response:
        try:
            return self.http.request(method, path, **kw)
        except httpx.HTTPError as e:
            raise TargetError("registry_unreachable", f"{method} {path}: {e}") from e

    def claim(self, kind: str, value: str, unit: str) -> str | None:
        r = self._call("POST", "/api/registry/claims", json={"kind": kind, "value": value, "unit": unit})
        if r.status_code == 409:
            return str(r.json()["owner"])
        if r.status_code >= 400:
            raise TargetError("registry_unreachable", f"claim answered {r.status_code}")
        return None

    def head(self, unit: str) -> tuple[int, str] | None:
        r = self._call("GET", f"/api/units/{unit}/head")
        if r.status_code == 404:
            return None
        if r.status_code >= 400:
            raise TargetError("registry_unreachable", f"head answered {r.status_code}")
        body = r.json()
        return int(body["seq"]), str(body["hash"])
