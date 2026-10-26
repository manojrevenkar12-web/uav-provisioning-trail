"""What can go wrong at a target, as stable codes. The analysis groups failures by these codes, so a code means one
thing everywhere and its text is for people."""

from __future__ import annotations

from typing import Any


class TargetError(Exception):
    def __init__(self, code: str, detail: str, **evidence: Any) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail
        self.evidence = evidence
