from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("UAV_ROOT", str(ROOT))


@pytest.fixture(scope="session")
def layouts() -> dict:
    return yaml.safe_load((ROOT / "config" / "targets.yaml").read_text())


@pytest.fixture(scope="session")
def firmware(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    from uavsim import firmware as fw

    if not fw.available():
        pytest.skip("arm-none-eabi-gcc is not installed")
    out = tmp_path_factory.mktemp("fw")
    return {
        "fc": fw.build("fc", "1.14.2", "BC", out),
        "fc_new": fw.build("fc", "1.15.0", "BC", out),
        "pmu": fw.build("pmu", "2.3.1", "AB", out),
    }


@pytest.fixture
def emulated_fc(layouts: dict) -> Iterator:
    from uavsim import qemu

    if not qemu.available():
        pytest.skip("qemu-system-arm is not installed")
    mcu = qemu.EmulatedMcu("fc", layouts["fc"]["qemu"]["machine"], layouts["fc"])
    mcu.start()
    try:
        yield mcu
    finally:
        mcu.stop()


@pytest.fixture(scope="session")
def database() -> str:
    url = os.environ.get("UAV_TEST_DATABASE_URL")
    if not url:
        pytest.skip("UAV_TEST_DATABASE_URL is not set")
    os.environ["UAV_DATABASE_URL"] = url
    from uavtrail.server import db

    db.reset_engine()
    return url


@pytest.fixture
def clean_db(database: str) -> str:
    from uavtrail.server import db

    db.reset()
    return database


@pytest.fixture(scope="session")
def shift(database: str, tmp_path_factory: pytest.TempPathFactory) -> dict:
    """A small shift on the emulated line with strong, known faults, run once for the session."""
    from uavsim import campaign, qemu
    from uavsim import firmware as fw
    from uavsim.line import run
    from uavtrail.server import db

    if not (qemu.available() and fw.available()):
        pytest.skip("needs qemu-system-arm and arm-none-eabi-gcc")
    db.reset()
    c = campaign.load(ROOT / "tests" / "campaigns" / "small.yaml")
    out = tmp_path_factory.mktemp("shift")
    summary = run(c, out)
    return {"out": out, "summary": summary, "campaign": c}
