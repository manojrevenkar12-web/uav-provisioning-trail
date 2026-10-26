"""Releases: what may be installed on an airframe, signed by release engineering.

A release names one version per target, the board revisions and module SKUs it supports and the fuse values for
the irreversible step. `build` adds the sha256 of every artifact file and signs the canonical JSON; `load` refuses
a release whose signature does not verify against a trusted key, or whose files on the station no longer match.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from . import keys
from .targets.errors import TargetError


def canonical(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def artifact_path(artifacts: Path, target: str, version: str) -> Path:
    if target == "orin":
        return artifacts / f"orin-{version}" / "manifest.json"
    return artifacts / f"{target}-{version}.bin"


def build(source: Path, artifacts: Path, signing_key: Path, out_dir: Path) -> Path:
    spec = yaml.safe_load(source.read_text(encoding="utf-8"))
    for target, art in spec["artifacts"].items():
        path = artifact_path(artifacts, target, art["version"])
        if not path.exists():
            raise FileNotFoundError(f"{spec['release']}: {path} is not built")
        art["sha256"] = sha256_file(path)
    key = keys.load_private(signing_key)
    body = canonical(spec)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{spec['release']}.json").write_bytes(body)
    (out_dir / f"{spec['release']}.sig").write_text(
        json.dumps({"key": keys.fingerprint(keys.public_hex(key)), "signature": keys.sign(key, body)})
    )
    return out_dir / f"{spec['release']}.json"


@dataclass(frozen=True)
class Release:
    id: str
    spec: dict[str, Any]
    digest: str  # sha256 of the signed JSON: what the trail and certificates refer to
    signed_by: str

    def version(self, target: str) -> str:
        return str(self.spec["artifacts"][target]["version"])

    def artifact(self, artifacts: Path, target: str) -> Path:
        return artifact_path(artifacts, target, self.version(target))


def load(release_id: str, releases_dir: Path, artifacts: Path, trusted: dict[str, str]) -> Release:
    """trusted: key fingerprint -> public key (hex)."""
    body = (releases_dir / f"{release_id}.json").read_bytes()
    sig = json.loads((releases_dir / f"{release_id}.sig").read_text())
    public = trusted.get(sig["key"])
    if public is None:
        raise TargetError("release_unverified", f"{release_id} is signed by an untrusted key {sig['key']}")
    if not keys.verify(public, body, sig["signature"]):
        raise TargetError("release_unverified", f"{release_id}: the signature does not match its content")
    spec = json.loads(body)
    for target, art in spec["artifacts"].items():
        path = artifact_path(artifacts, target, art["version"])
        if not path.exists() or sha256_file(path) != art["sha256"]:
            raise TargetError(
                "release_unverified", f"{release_id}: {path.name} is missing or differs from the release", target=target
            )
    if "orin" in spec["artifacts"]:
        bundle = artifact_path(artifacts, "orin", spec["artifacts"]["orin"]["version"]).parent
        manifest = json.loads((bundle / "manifest.json").read_text())
        for part in manifest["partitions"]:
            if sha256_file(bundle / part["file"]) != part["sha256"]:
                raise TargetError(
                    "bundle_mismatch",
                    f"{release_id}: {part['file']} differs from the bundle manifest",
                    partition=part["name"],
                )
    return Release(spec["release"], spec, hashlib.sha256(body).hexdigest(), sig["key"])


def trusted_keys(path: Path) -> dict[str, str]:
    """A YAML list of release-signing public keys (hex)."""
    if not path.exists():
        return {}
    return {keys.fingerprint(k): k for k in yaml.safe_load(path.read_text()) or []}
