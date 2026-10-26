"""Builds the mission-computer image bundles a release ships: partition files and a manifest, as the host side of
an initrd flash would hold them. The files are small stand-ins; `nominal_mb` is the size the clock uses."""

from __future__ import annotations

import hashlib
import json
import random
from pathlib import Path
from typing import Any

PARTITIONS = [("QSPI_BOOT", 64), ("esp", 64), ("kernel", 80), ("kernel-dtb", 1), ("APP", 6200)]


def build(
    version: str, l4t: str, services: list[str], out_dir: Path, machine_id: str | None = None
) -> tuple[Path, str]:
    """Writes out_dir/orin-<version>/ and returns it with the sha256 of its manifest."""
    d = out_dir / f"orin-{version}"
    d.mkdir(parents=True, exist_ok=True)
    rng = random.Random(f"orin-{version}")
    parts: list[dict[str, Any]] = []
    for name, nominal in PARTITIONS:
        data = rng.randbytes(4096 + 512 * len(name))
        (d / f"{name}.img").write_bytes(data)
        parts.append(
            {"name": name, "file": f"{name}.img", "sha256": hashlib.sha256(data).hexdigest(), "nominal_mb": nominal}
        )
    manifest: dict[str, Any] = {"version": version, "l4t": l4t, "partitions": parts, "services": services}
    if machine_id:
        manifest["machine_id"] = machine_id  # baked into the image by mistake: every unit gets the same one
    text = json.dumps(manifest, indent=2, sort_keys=True)
    (d / "manifest.json").write_text(text)
    return d, hashlib.sha256(text.encode()).hexdigest()
