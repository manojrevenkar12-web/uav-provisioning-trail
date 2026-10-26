"""One shift on the emulated line.

Every fixture slot holds two emulated microcontrollers (QEMU, behind a fixture link that can misbehave) and a
recovery-mode mission computer. Airframes arrive in order; each goes to the slot that is free first by its own
clock, carrying the faults the campaign gives it. The station software that runs them is the real one
(uavtrail.station), talking to the real traceability server over HTTP. Held units the production team owns get
one rework run at the end of the shift.

What the campaign injected is written to truth.json next to the run; only uavtrail.evaluate reads it.
"""

from __future__ import annotations

import datetime as dt
import heapq
import json
import random
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import uvicorn

from uavtrail import config, keys, releases
from uavtrail.server import api
from uavtrail.station.clock import SimClock
from uavtrail.station.outbox import Outbox
from uavtrail.station.registry import ServerRegistry
from uavtrail.station.runner import Endpoint, Outcome, Runner, Slot, Unit
from uavtrail.station.sender import Sender

from . import qemu
from .build import build, release_versions
from .campaign import Campaign
from .faults import FaultPlan, FixtureLink
from .orin_sim import Module, OrinDevice, OrinServer, ReleaseDefects, SlotFaults
from .world import Airframe, generate


@dataclass
class SimSlot:
    station: str
    fixture: str
    index: int
    layouts: dict[str, Any]
    start: dt.datetime
    unit_index: int = 0
    mcus: dict[str, qemu.EmulatedMcu] = field(default_factory=dict)
    links: dict[str, FixtureLink] = field(default_factory=dict)
    device: OrinDevice | None = None
    server: OrinServer | None = None
    clock: SimClock | None = None

    @property
    def name(self) -> str:
        return f"{self.fixture}/{self.index}"

    def up(self, seed: int) -> None:
        for target in ("fc", "pmu"):
            m = qemu.EmulatedMcu(target, self.layouts[target]["qemu"]["machine"], self.layouts[target])
            m.start()
            link = FixtureLink(m.gdb_port)
            link.start()
            self.mcus[target], self.links[target] = m, link
        self.device = OrinDevice(self.layouts["orin"], seed=seed)
        self.server = OrinServer(self.device)
        self.clock = SimClock(self.start)

    def wiring(self) -> Slot:
        def ep(t: str) -> Endpoint:
            return Endpoint("127.0.0.1", self.links[t].listen_port, self.mcus[t].uart_port)

        assert self.server is not None
        return Slot(
            self.station, self.fixture, self.index, ep("fc"), ep("pmu"), Endpoint("127.0.0.1", self.server.port)
        )

    def down(self) -> None:
        for link in self.links.values():
            link.stop()
        for m in self.mcus.values():
            m.stop()
        if self.server:
            self.server.stop()


class ServerThread:
    def __init__(self) -> None:
        self.port = qemu.free_port()
        self.server = uvicorn.Server(uvicorn.Config(api.app, host="127.0.0.1", port=self.port, log_level="warning"))
        self.thread = threading.Thread(target=self.server.run, daemon=True)

    def __enter__(self) -> str:
        self.thread.start()
        while not self.server.started:
            time.sleep(0.05)
        return f"http://127.0.0.1:{self.port}"

    def __exit__(self, *exc: object) -> None:
        self.server.should_exit = True
        self.thread.join(timeout=10)


def run(
    campaign: Campaign, out: Path, units: int | None = None, base_url: str | None = None, fresh: bool = True
) -> dict[str, Any]:
    out.mkdir(parents=True, exist_ok=True)
    if fresh:  # a new shift on a clean server: the stations' outboxes start empty too
        for f in out.glob("outbox-*.sqlite*"):
            f.unlink()
    built = build(campaign, out)
    layouts, line, codes = config.targets(), config.line(), config.codes()
    versions = release_versions(campaign)
    airframes = generate(campaign, versions, units)
    trusted = releases.trusted_keys(built["trust"])
    loaded = {rid: releases.load(rid, built["releases"], built["artifacts"], trusted) for rid in versions}
    recipes = {rid: config.recipe(r.spec["recipe"]) for rid, r in loaded.items()}
    start = dt.datetime.fromisoformat(campaign.spec["start"])
    rng = random.Random(campaign.spec["seed"] * 7919)
    faults = campaign.faults
    truth_events: list[dict[str, Any]] = []

    slots: list[SimSlot] = []
    for station, st in line["stations"].items():
        for fixture, count in st["fixtures"].items():
            for i in range(1, count + 1):
                slots.append(SimSlot(station, fixture, i, layouts, start))
    for n, s in enumerate(slots):
        s.up(seed=campaign.spec["seed"] * 100 + n)
        _wire_slot_faults(s, faults, rng, truth_events)

    with ServerThread() if base_url is None else _Given(base_url) as url:
        registry = ServerRegistry(url, token=None)
        station_keys, outboxes, senders = {}, {}, {}
        for station in line["stations"]:
            kp = built["keys"] / f"{station}.key"
            station_keys[station] = keys.load_private(kp) if kp.exists() else keys.generate(kp)
            outboxes[station] = Outbox(out / f"outbox-{station}.sqlite")
            senders[station] = Sender(outboxes[station], url)
            senders[station].register(station, keys.public_hex(station_keys[station]))

        queue: list[tuple[dt.datetime, int, SimSlot]] = [(start, n, s) for n, s in enumerate(slots)]
        heapq.heapify(queue)
        outcomes: list[dict[str, Any]] = []
        rework: list[Airframe] = []

        def one(a: Airframe, is_rework: bool) -> None:
            _, n, slot = heapq.heappop(queue)
            assert slot.clock is not None and slot.device is not None
            slot.clock.spend(float(line["durations"]["load_unit"]))
            slot.unit_index = a.index
            operator = rng.choice(campaign.spec["operators"][slot.station])
            _wire_unit_faults(slot, a, operator, faults, rng, truth_events, versions)
            for m_target in ("fc", "pmu"):
                board = getattr(a, m_target)
                slot.mcus[m_target].insert_board(
                    board.uid, board.rev, board.lot, otp_override=b"\0" * 32 if board.otp_blank else None
                )
            mod = a.module
            slot.device.insert(
                Module(
                    mod["serial"],
                    mod["board_id"],
                    mod["sku"],
                    mod["fab"],
                    mod["batch"],
                    eeprom_crc_ok=mod["eeprom_crc_ok"],
                    nvme_defect=mod["nvme_defect"],
                    fuses=mod.setdefault("fuses", {}),
                )
            )
            runner = Runner(
                slot.wiring(),
                loaded[a.release],
                recipes[a.release],
                codes,
                layouts,
                built["artifacts"],
                registry,
                outboxes[slot.station],
                station_keys[slot.station],
                slot.clock,
                line["durations"] | {"recover": line["recover"]},
                operator,
                mode=line["stations"][slot.station].get("mode", "production"),
            )
            kit = {"fc_lot": a.fc.lot, "pmu_lot": a.pmu.lot, "orin_batch": a.module["batch"]}
            result: Outcome = runner.run(Unit(a.serial, a.calibration, kit))
            mod["fuses"] = slot.device.module.fuses if slot.device.module else {}
            senders[slot.station].flush()
            outcomes.append(
                {
                    "unit": a.serial,
                    "index": a.index,
                    "rework": is_rework,
                    "status": result.status,
                    "code": result.code,
                    "owner": result.owner,
                    "slot": slot.name,
                    "operator": operator,
                    "release": a.release,
                    "first_pass": result.first_pass,
                }
            )
            if result.status == "held" and result.owner == "production" and not is_rework:
                rework.append(a)
            heapq.heappush(queue, (slot.clock.now(), n, slot))

        t0 = time.monotonic()
        for a in airframes:
            one(a, False)
        for a in rework:
            one(a, True)
        rejected = [r for s in senders.values() for r in s.rejected]
        for o in outboxes.values():
            o.close()
    for s in slots:
        s.down()

    truth = {
        "campaign": campaign.name,
        "expected": campaign.expected() + _derived_expectations(airframes, loaded),
        "faults": faults,
        "units": [{"unit": a.serial, "index": a.index, "injected": a.injected} for a in airframes],
        "events": truth_events,
        "fused": [{"unit": a.serial, "module": a.module["serial"]} for a in airframes if a.module.get("fuses")],
    }
    (out / "truth.json").write_text(json.dumps(truth, indent=1))
    (out / "outcomes.json").write_text(json.dumps(outcomes, indent=1))
    return {
        "units": len(airframes),
        "reworked": len(rework),
        "released": sum(o["status"] == "released" for o in outcomes if not o["rework"]),
        "rejected_events": rejected,
        "seconds": round(time.monotonic() - t0, 1),
        "shift_end": max(s.clock.now() for s in slots if s.clock).isoformat(),
    }


class _Given:
    def __init__(self, url: str) -> None:
        self.url = url

    def __enter__(self) -> str:
        return self.url

    def __exit__(self, *exc: object) -> None:
        return None


def _wire_slot_faults(
    slot: SimSlot, faults: list[dict[str, Any]], rng: random.Random, truth: list[dict[str, Any]]
) -> None:
    assert slot.device is not None
    sf = SlotFaults()
    for f in faults:
        if f.get("slot") != slot.name:
            continue
        if f["kind"] == "fixture_contact":
            link = slot.links[f["target"]]

            def policy(f: dict[str, Any] = f) -> FaultPlan | None:
                active = f.get("from_unit", 0) <= slot.unit_index <= f.get("to_unit", 10**9)
                if active and rng.random() < float(f["p"]):
                    truth.append({"fault": f["id"], "unit_index": slot.unit_index, "slot": slot.name})
                    return FaultPlan("refuse")
                return None

            link.policy = policy
        elif f["kind"] == "usb_cable":
            sf.enumerate_fail_p = float(f.get("enumerate_fail_p", 0))
            sf.usb2 = bool(f.get("usb2", False))
        elif f["kind"] == "usb_drop":
            sf.drop_during_flash_p = float(f.get("p", 0))
    slot.device.faults = sf


def _wire_unit_faults(
    slot: SimSlot,
    a: Airframe,
    operator: str,
    faults: list[dict[str, Any]],
    rng: random.Random,
    truth: list[dict[str, Any]],
    versions: dict[str, dict[str, str]],
) -> None:
    assert slot.device is not None
    for link in slot.links.values():
        link.plan = None
    for f in faults:
        k = f["kind"]
        if k == "operator_handling" and operator == f["operator"] and rng.random() < float(f["p"]):
            slot.links[f["target"]].plan = FaultPlan("drop", after_writes=rng.randint(2, 6))
            truth.append({"fault": f["id"], "unit": a.serial})
        elif k == "random_link" and rng.random() < float(f["p"]):
            target = rng.choice(["fc", "pmu"])
            kind = rng.choice(["refuse", "drop", "corrupt"])
            slot.links[target].plan = FaultPlan(
                kind, after_writes=1 if kind == "corrupt" else rng.randint(2, 6), seed=rng.randrange(10**6)
            )
            truth.append({"fault": f["id"], "unit": a.serial, "target": target, "kind": kind})
        elif k == "service_on_sku":
            slot.device.defects.setdefault(str(f["version"]), ReleaseDefects()).service_fails_on_sku[f["service"]] = (
                str(f["sku"])
            )


def _derived_expectations(airframes: list[Airframe], loaded: dict[str, Any]) -> list[dict[str, Any]]:
    """Board revisions arriving before the release that supports them: real, systemic, and not a fault anyone
    injected. A correct analysis names them too."""
    out = []
    seen: set[tuple[str, str]] = set()
    for a in airframes:
        for target in ("fc", "pmu"):
            rev = getattr(a, target).rev
            if rev not in loaded[a.release].spec["compatible"][target] and (target, rev) not in seen:
                seen.add((target, rev))
                out.append(
                    {
                        "fault": f"derived-{target}-rev-{rev}",
                        "code": "board_rev_unsupported",
                        "dimension": f"{target}_rev",
                        "value": rev,
                    }
                )
    return out
