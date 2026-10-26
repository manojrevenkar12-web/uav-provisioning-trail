"""Does the work instruction the operator reads describe what the station actually does?

Compares a work instruction export (config/instructions/<doc>.yaml) with the recipe and the release a station
runs: steps the station does that the instruction does not mention, steps it mentions that no longer exist,
steps in another order, versions it quotes that are not the ones being installed, and irreversible steps
without a warning.
"""

from __future__ import annotations

import re
from typing import Any

import yaml

from ..config import root

VERSION = re.compile(r"\b\d+\.\d+\.\d+\b")


def load(document: str) -> dict[str, Any]:
    return dict(yaml.safe_load((root() / "config" / "instructions" / f"{document}.yaml").read_text(encoding="utf-8")))


def check(instruction: dict[str, Any], recipe: dict[str, Any], release: dict[str, Any]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    doc = instruction["document"]
    steps = {s["id"]: s for s in instruction["steps"]}
    recipe_ids = [s["id"] for s in recipe["steps"]]
    doc_ids = [s["id"] for s in instruction["steps"]]
    for sid in recipe_ids:
        if sid not in steps:
            findings.append(
                {"kind": "missing_step", "step": sid, "detail": f"the station runs {sid}; {doc} does not describe it"}
            )
    for sid in doc_ids:
        if sid not in recipe_ids:
            findings.append(
                {
                    "kind": "obsolete_step",
                    "step": sid,
                    "detail": f"{doc} tells the operator to do {sid}; the recipe no longer has it",
                }
            )
    shared_recipe = [s for s in recipe_ids if s in steps]
    shared_doc = [s for s in doc_ids if s in recipe_ids]
    if shared_recipe != shared_doc:
        first = next(i for i, (a, b) in enumerate(zip(shared_recipe, shared_doc, strict=True)) if a != b)
        findings.append(
            {
                "kind": "order",
                "step": shared_doc[first],
                "detail": f"{doc} has {shared_doc[first]} where the station runs {shared_recipe[first]}",
            }
        )
    for rs in recipe["steps"]:
        s = steps.get(rs["id"])
        if not s:
            continue
        target = rs.get("target")
        if target in release["artifacts"]:
            released = str(release["artifacts"][target]["version"])
            quoted = {str(v) for v in (s.get("versions") or {}).values()} | set(VERSION.findall(s.get("text", "")))
            for q in sorted(quoted - {released}):
                findings.append(
                    {
                        "kind": "version_drift",
                        "step": rs["id"],
                        "detail": f"{doc} says {q}; {release['release']} installs {released}",
                    }
                )
        if rs.get("irreversible") and "irreversible" not in s.get("text", "").lower():
            findings.append(
                {
                    "kind": "missing_warning",
                    "step": rs["id"],
                    "detail": f"{rs['id']} cannot be undone; {doc} does not say so",
                }
            )
    return findings
