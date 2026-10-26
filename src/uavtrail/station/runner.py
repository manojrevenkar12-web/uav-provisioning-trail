"""Runs the recipe for one airframe on one fixture slot.

Every step is announced in the trail before it runs (intent) and recorded after (result, with its evidence and
how long it took). A failure is looked up in config/codes.yaml: if the code allows another attempt, the station
records the recovery it asks the operator for and starts again at the step the code names; when attempts are spent
the unit is held for the code's owner. The irreversible fuse step runs only when its guard finds nothing unmet.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from .. import keys
from ..releases import Release, canonical, sha256_file
from ..targets.errors import TargetError
from ..targets.layout import config_crc, pack_config
from ..targets.mcu import McuTarget
from ..targets.orin import ModuleId, OrinTarget
from ..targets.rsp import RspClient
from ..targets.uart import TcpUart
from ..trail.chain import Chain
from . import guards
from .clock import Clock
from .outbox import Outbox
from .registry import Registry


@dataclass(frozen=True)
class Endpoint:
    host: str
    port: int
    uart_port: int = 0


@dataclass(frozen=True)
class Slot:
    station: str
    fixture: str
    index: int
    fc: Endpoint
    pmu: Endpoint
    orin: Endpoint

    @property
    def name(self) -> str:
        return f"{self.fixture}/{self.index}"


@dataclass(frozen=True)
class Unit:
    serial: str
    calibration: dict[str, list[int]]  # from the calibration station, through MES
    kit: dict[str, str] = field(default_factory=dict)  # lots and batches from the kit labels scanned into MES


@dataclass
class Outcome:
    unit: str
    status: str  # released | held
    code: str | None = None
    step: str | None = None
    owner: str | None = None
    certificate: dict[str, Any] | None = None
    started: dt.datetime | None = None
    finished: dt.datetime | None = None
    first_pass: bool = True


@dataclass
class _Run:
    passed: set[str] = field(default_factory=set)
    attempts: dict[str, int] = field(default_factory=dict)
    identity: dict[str, Any] = field(default_factory=dict)
    installed: dict[str, Any] = field(default_factory=dict)
    module: ModuleId | None = None
    boot: dict[str, Any] = field(default_factory=dict)
    mcus: dict[str, McuTarget] = field(default_factory=dict)
    retried: bool = False


class Runner:
    def __init__(
        self,
        slot: Slot,
        release: Release,
        recipe: dict[str, Any],
        codes: dict[str, dict[str, Any]],
        layouts: dict[str, Any],
        artifacts: Path,
        registry: Registry,
        outbox: Outbox,
        station_key: Ed25519PrivateKey,
        clock: Clock,
        durations: dict[str, Any],
        operator: str,
        mode: str = "production",
    ) -> None:
        self.slot, self.release, self.recipe, self.codes = slot, release, recipe, codes
        self.layouts, self.artifacts, self.registry, self.outbox = layouts, artifacts, registry, outbox
        self.key, self.clock, self.durations, self.operator, self.mode = station_key, clock, durations, operator, mode
        self.steps = recipe["steps"]
        self.index = {s["id"]: i for i, s in enumerate(self.steps)}
        self.orin = OrinTarget(slot.orin.host, slot.orin.port, layouts["orin"])

    # ------------------------------------------------------------------ the loop

    def run(self, unit: Unit) -> Outcome:
        head = self.registry.head(unit.serial)
        chain = Chain(unit.serial, self.slot.station, self.key)
        if head:
            chain.seq, chain.head = head
        run = _Run()
        out = Outcome(unit.serial, "held", started=self.clock.now())
        self._event(
            chain,
            "start",
            release=self.release.id,
            release_sha256=self.release.digest,
            recipe=f"{self.recipe['recipe']}@{self.recipe['version']}",
            operator=self.operator,
            mode=self.mode,
        )
        i = 0
        try:
            while i < len(self.steps):
                step = self.steps[i]
                sid = step["id"]
                run.attempts[sid] = run.attempts.get(sid, 0) + 1
                attempt = run.attempts[sid]
                self._event(chain, "intent", step=sid, attempt=attempt)
                before_orin = self.orin.seconds
                try:
                    evidence = getattr(self, f"_{step['kind']}")(step, unit, run, chain)
                    seconds = self._seconds(step, evidence, self.orin.seconds - before_orin)
                    self.clock.spend(seconds)
                    run.passed.add(sid)
                    self._event(
                        chain,
                        "result",
                        step=sid,
                        attempt=attempt,
                        ok=True,
                        seconds=round(seconds, 1),
                        evidence=evidence,
                    )
                    i += 1
                except TargetError as e:
                    seconds = self._seconds(step, {}, self.orin.seconds - before_orin)
                    self.clock.spend(seconds)
                    self._event(
                        chain,
                        "result",
                        step=sid,
                        attempt=attempt,
                        ok=False,
                        seconds=round(seconds, 1),
                        code=e.code,
                        detail=e.detail,
                        evidence=_jsonable(e.evidence),
                    )
                    policy = self.codes.get(e.code, {"retry": 1, "owner": "engineering"})
                    run.retried = True
                    if attempt < int(policy.get("retry", 1)):
                        action = policy.get("recover", "retry")
                        back = str(policy.get("from", sid)).format(target=step.get("target", ""))
                        self._recover(run, step, action)
                        cost = float(self.durations["recover"].get(action, 0))
                        self.clock.spend(cost)
                        self._event(
                            chain, "recovery", step=sid, code=e.code, action=action, restart_at=back, seconds=cost
                        )
                        i = self.index.get(back, i)
                        for later in self.steps[i:]:
                            run.passed.discard(later["id"])
                        continue
                    owner = policy.get("owner", "engineering")
                    hold = float(self.durations["hold"])
                    self.clock.spend(hold)
                    self._event(chain, "hold", step=sid, code=e.code, owner=owner, detail=e.detail, seconds=hold)
                    out.code, out.step, out.owner = e.code, sid, owner
                    break
            else:
                out.status = "released"
                out.certificate = run.installed.get("certificate")
        finally:
            for t in run.mcus.values():
                t.close()
        out.finished = self.clock.now()
        out.first_pass = out.status == "released" and not run.retried
        return out

    # ------------------------------------------------------------------ bookkeeping

    def _event(self, chain: Chain, kind: str, **data: Any) -> dict[str, Any]:
        e = chain.append(kind, self.clock.now().isoformat(), slot=self.slot.name, fixture=self.slot.fixture, **data)
        self.outbox.put(e)  # committed before the action it announces
        return e

    def _seconds(self, step: dict[str, Any], evidence: dict[str, Any], orin_seconds: float) -> float:
        d = self.durations
        kind = step["kind"]
        if kind.startswith("orin_"):
            return orin_seconds
        if kind == "mcu_program":
            return float(d["mcu_program_base"]) + evidence.get("bytes", 0) / 1024 / float(d["mcu_program_kb_per_s"])
        return float(d.get(kind, d.get(kind.removeprefix("mcu_"), 2)))

    def _recover(self, run: _Run, step: dict[str, Any], action: str) -> None:
        target = step.get("target")
        if target in run.mcus and action in ("reseat", "reattach"):
            run.mcus.pop(target).close()

    # ------------------------------------------------------------------ steps

    def _scan(self, step: dict[str, Any], unit: Unit, run: _Run, chain: Chain) -> dict[str, Any]:
        return {"unit": unit.serial, "operator": self.operator, "kit": unit.kit}

    def _mcu(self, run: _Run, target: str) -> McuTarget:
        if target not in run.mcus:
            ep: Endpoint = getattr(self.slot, target)
            t = McuTarget(target, self.layouts[target], RspClient(ep.host, ep.port, timeout=3.0))
            t.connect()
            run.mcus[target] = t
        return run.mcus[target]

    def _mcu_attach(self, step: dict[str, Any], unit: Unit, run: _Run, chain: Chain) -> dict[str, Any]:
        target = step["target"]
        if target in run.mcus:
            run.mcus.pop(target).close()
        probe = self._mcu(run, target).probe
        return {"probe": f"{probe.host}:{probe.port}", "flash_packets": probe.supports_flash_packets}

    def _mcu_identify(self, step: dict[str, Any], unit: Unit, run: _Run, chain: Chain) -> dict[str, Any]:
        target = step["target"]
        ident = self._mcu(run, target).identify()
        evidence = {"uid": ident.uid, "board_rev": ident.board_rev, "lot": ident.lot}
        if ident.board_rev not in self.release.spec["compatible"][target]:
            raise TargetError(
                "board_rev_unsupported", f"revision {ident.board_rev} is not in {self.release.id}", **evidence
            )
        owner = self.registry.claim(f"{target}_uid", ident.uid, unit.serial)
        if owner:
            raise TargetError("uid_already_registered", f"this board belongs to {owner}", owner=owner, **evidence)
        run.identity[target] = evidence
        return evidence

    def _mcu_program(self, step: dict[str, Any], unit: Unit, run: _Run, chain: Chain) -> dict[str, Any]:
        target = step["target"]
        path = self.release.artifact(self.artifacts, target)
        image = path.read_bytes()
        expected = self.release.spec["artifacts"][target]["sha256"]
        if sha256_file(path) != expected:
            raise TargetError("release_unverified", f"{path.name} changed on the station since the release was loaded")
        readback = self._mcu(run, target).program(image)
        run.installed[target] = {"version": self.release.version(target), "sha256": readback}
        return {"version": self.release.version(target), "sha256": readback, "bytes": len(image)}

    def _mcu_config(self, step: dict[str, Any], unit: Unit, run: _Run, chain: Chain) -> dict[str, Any]:
        target = step["target"]
        record = pack_config(unit.serial, unit.calibration[target])
        readback = self._mcu(run, target).write_config(record)
        run.installed[f"{target}_config"] = {"crc": config_crc(record), "sha256": readback}
        return {"crc": config_crc(record), "calibration": unit.calibration[target]}

    def _mcu_boot(self, step: dict[str, Any], unit: Unit, run: _Run, chain: Chain) -> dict[str, Any]:
        target = step["target"]
        ep: Endpoint = getattr(self.slot, target)
        uart = TcpUart(ep.host, ep.uart_port)
        try:
            boot = self._mcu(run, target).boot(uart)
        finally:
            uart.close()
            if target in run.mcus:
                run.mcus.pop(target).close()  # the part runs on its own now
        evidence = {"banner": boot.fields, "selftest": boot.selftest}
        if not boot.passed:
            failed = [k for k, v in boot.selftest.items() if v != "ok"]
            raise TargetError("selftest_fail", "self-test failed: " + ", ".join(failed), failed=failed, **evidence)
        if boot.fields.get("fw") != self.release.version(target):
            raise TargetError(
                "version_mismatch", f"runs {boot.fields.get('fw')}, released {self.release.version(target)}", **evidence
            )
        if boot.fields.get("uid") != run.identity[target]["uid"] or boot.fields.get("unit") != unit.serial:
            raise TargetError("identity_mismatch", "the booted board is not the one identified", **evidence)
        if boot.fields.get("cfg") != run.installed[f"{target}_config"]["crc"]:
            raise TargetError("identity_mismatch", "the booted board reports another configuration", **evidence)
        return evidence

    def _orin_enumerate(self, step: dict[str, Any], unit: Unit, run: _Run, chain: Chain) -> dict[str, Any]:
        found = self.orin.enumerate()
        return {**found, "slow_link": found.get("speed") != "usb3"}

    def _orin_identify(self, step: dict[str, Any], unit: Unit, run: _Run, chain: Chain) -> dict[str, Any]:
        m = self.orin.identify()
        allowed = self.release.spec["compatible"]["orin"]
        evidence = {"board_id": m.board_id, "sku": m.sku, "fab": m.fab, "serial": m.serial, "batch": m.batch}
        if m.board_id != allowed["board_id"] or m.sku not in allowed["sku"] or m.fab not in allowed["fab"]:
            raise TargetError(
                "module_unsupported", f"{m.board_id}-{m.sku} FAB {m.fab} is not in {self.release.id}", **evidence
            )
        owner = self.registry.claim("orin_serial", m.serial, unit.serial)
        if owner:
            raise TargetError("uid_already_registered", f"this module belongs to {owner}", owner=owner, **evidence)
        run.module = m
        return evidence

    def _bundle(self) -> tuple[Path, dict[str, Any]]:
        manifest_path = self.release.artifact(self.artifacts, "orin")
        if sha256_file(manifest_path) != self.release.spec["artifacts"]["orin"]["sha256"]:
            raise TargetError("bundle_mismatch", "the image bundle changed since the release was loaded")
        return manifest_path.parent, json.loads(manifest_path.read_text())

    def _orin_flash(self, step: dict[str, Any], unit: Unit, run: _Run, chain: Chain) -> dict[str, Any]:
        bundle, manifest = self._bundle()
        result = self.orin.flash(bundle)
        return {"bundle": manifest["version"], **result}

    def _orin_verify(self, step: dict[str, Any], unit: Unit, run: _Run, chain: Chain) -> dict[str, Any]:
        _, manifest = self._bundle()
        back = self.orin.read_back()
        wrong = [p["name"] for p in manifest["partitions"] if back.get(p["name"]) != p["sha256"]]
        if wrong:
            raise TargetError("partition_mismatch", "read back differs: " + ", ".join(wrong), partitions=wrong)
        run.installed["orin"] = {"version": manifest["version"], "partitions": back}
        return {"partitions": len(back)}

    def _orin_first_boot(self, step: dict[str, Any], unit: Unit, run: _Run, chain: Chain) -> dict[str, Any]:
        rep = self.orin.first_boot()
        spec = self.release.spec["artifacts"]["orin"]
        evidence = {
            "l4t": rep["l4t"],
            "image_version": rep["image_version"],
            "services": rep["services"],
            "machine_id": rep["machine_id"],
            "device_key_sha256": rep["device_key_sha256"],
        }
        if rep["l4t"] != spec["l4t"] or rep["image_version"] != spec["version"]:
            raise TargetError("l4t_mismatch", f"runs {rep['image_version']} on L4T {rep['l4t']}", **evidence)
        failed = sorted(s for s, state in rep["services"].items() if state != "active")
        missing = sorted(set(spec["services"]) - set(rep["services"]))
        if failed or missing:
            raise TargetError(
                "service_failed", "not running: " + ", ".join(failed + missing), failed=failed + missing, **evidence
            )
        owner = self.registry.claim("machine_id", rep["machine_id"], unit.serial)
        if owner:
            raise TargetError("machine_id_duplicate", f"machine-id already used by {owner}", owner=owner, **evidence)
        run.boot = evidence
        return evidence

    def _orin_fuse(self, step: dict[str, Any], unit: Unit, run: _Run, chain: Chain) -> dict[str, Any]:
        wanted = dict(self.release.spec.get("fuses") or {})
        ctx = guards.FuseContext(
            release_fuses=wanted,
            mode=self.mode,
            passed_this_run=set(run.passed),
            module_supported=run.module is not None,
            current_fuses=self.orin.fuses(),
            trail_persisted=self.outbox.has(unit.serial, chain.head),
        )
        if guards.already_done(ctx):
            return {"burnt": False, "already": wanted}
        problems = guards.unmet(ctx)
        if problems:
            raise TargetError("fuse_precondition", "; ".join(problems), unmet=problems)
        self.orin.burn_fuses(wanted)
        after = self.orin.fuses()
        if after != wanted:
            raise TargetError("fuse_conflict", "the fuses read back differ from what was burnt", read=after)
        return {"burnt": True, "fuses": after}

    def _release_unit(self, step: dict[str, Any], unit: Unit, run: _Run, chain: Chain) -> dict[str, Any]:
        cert = {
            "unit": unit.serial,
            "product": self.release.spec["product"],
            "release": self.release.id,
            "release_sha256": self.release.digest,
            "station": self.slot.station,
            "slot": self.slot.name,
            "operator": self.operator,
            "released_at": self.clock.now().isoformat(),
            "boards": run.identity,
            "module": run.module.__dict__ if run.module else None,
            "installed": run.installed | {"orin_boot": run.boot},
            "fuses": self.release.spec.get("fuses"),
            "trail_head": chain.head,
        }
        body = canonical(cert)
        signed = {"certificate": cert, "signature": keys.sign(self.key, body), "station_key": keys.public_hex(self.key)}
        run.installed["certificate"] = signed
        return {"certificate_sha256": hashlib.sha256(body).hexdigest(), "certificate": signed}


def _jsonable(x: Any) -> Any:
    return json.loads(json.dumps(x, default=str))
