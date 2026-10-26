"""The station on one emulated slot: the fuse guard, an offline server, and a crash in the middle of a step."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest
from conftest import ROOT

from uavsim import campaign, qemu
from uavsim import firmware as fw
from uavsim.build import build
from uavsim.line import ServerThread, SimSlot
from uavsim.orin_sim import Module
from uavtrail import config, keys, releases
from uavtrail.station.clock import SimClock
from uavtrail.station.outbox import Outbox
from uavtrail.station.registry import LocalRegistry, ServerRegistry
from uavtrail.station.runner import Runner, Unit
from uavtrail.station.sender import Sender
from uavtrail.trail.chain import verify

pytestmark = pytest.mark.qemu
START = dt.datetime(2026, 10, 27, 6, tzinfo=dt.UTC)


@pytest.fixture(scope="module")
def line(tmp_path_factory: pytest.TempPathFactory):
    if not (qemu.available() and fw.available()):
        pytest.skip("needs qemu-system-arm and arm-none-eabi-gcc")
    out = tmp_path_factory.mktemp("station")
    c = campaign.load(ROOT / "tests" / "campaigns" / "small.yaml")
    built = build(c, out)
    rel = releases.load("R2026.09", built["releases"], built["artifacts"], releases.trusted_keys(built["trust"]))
    slot = SimSlot("ST-1", "FX-A", 1, config.targets(), START)
    slot.up(seed=1)
    yield {"slot": slot, "release": rel, "built": built, "out": out}
    slot.down()


def _load(slot: SimSlot, n: int) -> Unit:
    uid = bytes([n]) * 12
    slot.mcus["fc"].insert_board(uid, "C", "L1")
    slot.mcus["pmu"].insert_board(bytes([n + 100]) * 12, "A", "P1")
    assert slot.device is not None
    slot.device.insert(Module(f"14000000{n:05d}", 3767, "0000", "300", "B1"))
    return Unit(f"HX2-26-9{n:05d}", {"fc": [1, 2, 3, 4, 5, 6], "pmu": [0] * 6}, {"fc_lot": "L1"})


def _runner(line: dict, outbox: Outbox, registry, mode: str = "production", key=None) -> Runner:
    key = key or keys.generate(line["out"] / f"k-{mode}-{id(outbox)}.key")
    return Runner(
        line["slot"].wiring(),
        line["release"],
        config.recipe("standard"),
        config.codes(),
        config.targets(),
        line["built"]["artifacts"],
        registry,
        outbox,
        key,
        SimClock(START),
        config.line()["durations"] | {"recover": config.line()["recover"]},
        "OP-1",
        mode=mode,
    )


def test_a_unit_is_released_with_a_verifiable_trail(line: dict, tmp_path: Path) -> None:
    outbox = Outbox(tmp_path / "o.sqlite")
    r = _runner(line, outbox, LocalRegistry())
    out = r.run(_load(line["slot"], 1))
    assert out.status == "released" and out.first_pass
    events = outbox.pending()
    assert verify(events, {"ST-1": keys.public_hex(r.key)}) == []
    kinds = [e["kind"] for e in events]
    assert kinds[0] == "start" and kinds.count("intent") == kinds.count("result") == 18
    assert line["slot"].device.module.fuses == line["release"].spec["fuses"]


def test_a_station_in_engineering_mode_never_burns_fuses(line: dict, tmp_path: Path) -> None:
    outbox = Outbox(tmp_path / "o.sqlite")
    r = _runner(line, outbox, LocalRegistry(), mode="engineering")
    out = r.run(_load(line["slot"], 2))
    assert out.status == "held" and out.code == "fuse_precondition" and out.step == "orin_fuse"
    assert line["slot"].device.module.fuses == {}
    hold = [e for e in outbox.pending() if e["kind"] == "result" and not e["data"]["ok"]][-1]
    assert any("engineering mode" in u for u in hold["data"]["evidence"]["unmet"])


def test_a_crash_mid_step_leaves_an_intent_and_the_next_run_continues_the_chain(line: dict, tmp_path: Path) -> None:
    outbox = Outbox(tmp_path / "o.sqlite")
    registry = LocalRegistry()
    r = _runner(line, outbox, registry)
    unit = _load(line["slot"], 3)

    def crash(*_: object) -> None:
        raise KeyboardInterrupt("power cut")

    r._orin_flash = crash  # type: ignore[method-assign]
    with pytest.raises(KeyboardInterrupt):
        r.run(unit)
    events = outbox.pending()
    assert events[-1]["kind"] == "intent" and events[-1]["data"]["step"] == "orin_flash"
    registry.heads[unit.serial] = (events[-1]["seq"], events[-1]["hash"])
    r2 = _runner(line, outbox, registry, key=r.key)  # the station restarted
    line["slot"].device.insert(line["slot"].device.module)
    assert r2.run(unit).status == "released"
    everything = outbox.pending()
    assert verify(everything, {"ST-1": keys.public_hex(r.key)}) == []
    starts = [e for e in everything if e["kind"] == "start"]
    assert len(starts) == 2 and starts[1]["prev"] == events[-1]["hash"]  # the second run continues the first


def test_an_offline_server_keeps_the_trail_in_the_outbox(line: dict, tmp_path: Path, clean_db: str) -> None:
    outbox = Outbox(tmp_path / "o.sqlite")
    r = _runner(line, outbox, LocalRegistry())
    r.run(_load(line["slot"], 4))
    dead = Sender(outbox, "http://127.0.0.1:9")
    assert dead.flush() == 0 and outbox.backlog() > 30
    with ServerThread() as url:
        live = Sender(outbox, url)
        live.register("ST-1", keys.public_hex(r.key))
        sent = live.flush()
        assert sent > 30 and outbox.backlog() == 0 and live.rejected == []
        assert ServerRegistry(url).head("HX2-26-900004") is not None
