"""The guard on irreversible steps. Burning the module's fuses cannot be undone: a wrong burn scraps a module or
locks it to the wrong keys. The guard lists every precondition that is not met; the step runs only if the list is
empty, and the list is recorded in the trail either way."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class FuseContext:
    release_fuses: dict[str, Any]
    mode: str
    passed_this_run: set[str] = field(default_factory=set)
    module_supported: bool = False
    current_fuses: dict[str, Any] | None = None
    trail_persisted: bool = False


REQUIRED_STEPS = ("orin_identify", "orin_flash", "orin_verify", "orin_first_boot")


def unmet(ctx: FuseContext) -> list[str]:
    out: list[str] = []
    if not ctx.release_fuses:
        out.append("the release declares no fuse values")
    if ctx.mode != "production":
        out.append(f"the station is in {ctx.mode} mode")
    missing = [s for s in REQUIRED_STEPS if s not in ctx.passed_this_run]
    if missing:
        out.append("not passed in this run: " + ", ".join(missing))
    if not ctx.module_supported:
        out.append("the module is not identified as one the release supports")
    if ctx.current_fuses is None:
        out.append("the module's current fuses were not read")
    elif ctx.current_fuses and ctx.current_fuses != ctx.release_fuses:
        out.append("the module is already fused with other values")
    if not ctx.trail_persisted:
        out.append("the intent to burn is not yet stored in the trail")
    return out


def already_done(ctx: FuseContext) -> bool:
    return bool(ctx.current_fuses) and ctx.current_fuses == ctx.release_fuses
