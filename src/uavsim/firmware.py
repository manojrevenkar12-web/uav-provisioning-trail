"""Builds the firmware images a release ships (make in firmware/), cached by their inputs."""

from __future__ import annotations

import hashlib
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FIRMWARE = ROOT / "firmware"


def available() -> bool:
    return shutil.which("arm-none-eabi-gcc") is not None and shutil.which("make") is not None


def build(target: str, version: str, known_revs: str, out_dir: Path) -> Path:
    """firmware/build output copied to out_dir/<target>-<version>.bin; rebuilt only when the sources change."""
    sources = b"".join(p.read_bytes() for p in sorted(FIRMWARE.rglob("*")) if p.is_file() and "build" not in p.parts)
    key = hashlib.sha256(sources + f"{target}{version}{known_revs}".encode()).hexdigest()[:12]
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{target}-{version}.bin"
    stamp = out_dir / f"{target}-{version}.key"
    if out.exists() and stamp.exists() and stamp.read_text() == key:
        return out
    stem = FIRMWARE / "build" / f"{target}-{version}-{key}"
    subprocess.run(
        [
            "make",
            "-s",
            "-C",
            str(FIRMWARE),
            f"TARGET={target}",
            f"VERSION={version}",
            f"KNOWN_REVS={known_revs}",
            f"OUT=build/{stem.name}",
        ],
        check=True,
        capture_output=True,
    )
    shutil.copyfile(Path(f"{stem}.bin"), out)
    stamp.write_text(key)
    return out
