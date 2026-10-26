# uav-provisioning-trail

Software production support for a serial UAV line: every airframe leaves with the right firmware, image,
configuration and documentation, and when something goes wrong the line lead can tell a one-off from a systemic
problem, and see where the systemic one lives.

It covers what a software production-support team owns on a drone line:

- **Flashing and compute-module installs, verified.** Two microcontrollers per airframe (flight controller and
  power module) are flashed through a debug probe's GDB server (the protocol OpenOCD, pyOCD and J-Link speak),
  read back in full and hash-compared. They are then booted and their self-test is read from the UART. The mission
  computer, a Jetson Orin-class module, is enumerated in recovery mode at an expected USB id and speed. Its EEPROM
  is checked against the CRC-8 in byte 255 and its board id, SKU and FAB against the release. It is then flashed,
  every partition is read back, and it is booted once to check its L4T release, services, machine-id and device
  key.
- **Recovery workflows from a vocabulary, not from code.** Every failure is a stable code in
  `config/codes.yaml` with its owner, its retry budget, what the operator does first (reseat, reattach, re-enter
  recovery) and the step to restart from. A unit that runs out of attempts is held for the owner of its code.
- **An irreversible step that cannot fire by accident.** Burning the module's fuses runs only when its guard finds
  nothing unmet: the release declares the values, the station is in production mode, identify, flash, read-back
  and first boot all passed in this run, the module is not fused differently, and the intent to burn is already
  stored in the trail.
- **A digital paper trail per airframe.** Each step is announced before it runs and recorded after, as a
  hash-chained event signed by the station's Ed25519 key. Events are committed to a local outbox first and shipped
  to the traceability server, which accepts a chain once and in order and refuses edits (a database trigger makes
  the trail append-only). A crash mid-step leaves an intent without a result, and the next run continues the
  chain. A released airframe gets a signed software certificate listing what is on it, read-back hashes included.
- **Only signed releases install.** Releases are signed by release engineering. A station refuses a release whose
  signature, artifact hashes or image-bundle partitions do not verify.
- **One-off or systemic.** For every failure code, the analysis asks whether one place stands out beyond chance:
  a slot, a fixture, a station, an operator, a release, a board revision, a supplier lot or a module batch. It
  uses Fisher's exact test per place, Bonferroni-corrected per code, and names the narrowest place that explains
  the failures (the slot, not its station). Leading signals are analysed the same way: a module linking at USB2
  shows a cable going bad before it starts failing.
- **KPIs.** Software first-pass yield, flash success, downtime (slot time lost to failures, recoveries and
  holds), final yield and cycle time, by slot and by hour. A fix marked on an issue reports whether it holds:
  the issue's rate in its place before and after.
- **Work instructions that match the station.** The work instruction the operator reads (as a digital
  work-instruction tool exports it) is checked against the recipe and release: missing or obsolete steps, wrong
  order, versions that are not the ones being installed, and an irreversible step without a warning.
- **Traceability for recalls.** Where-used gives every released airframe carrying a version, from the signed
  certificates.

![The line: fixtures, slots, systemic issues](docs/screenshots/line.png)

## The emulated line

There is no drone factory in this repository, so the line is emulated as faithfully as was practical:

- The microcontrollers are **real firmware in QEMU**: bare-metal C for an STM32F405 (flight controller) and an
  STM32F100 (power module), built with `arm-none-eabi-gcc`. The station flashes them over QEMU's GDB stub exactly
  as it would over a probe, reads them back, resets them and reads their console. The firmware checks its own CRC
  trailer, the supplier identity and the unit configuration, and runs a sensor self-test that fails on a board
  revision it has no driver for.
- Between the station and each emulated part sits a **fixture link** that misbehaves the way fixtures do. It
  refuses an attach (worn pogo pins), drops the link mid-write (a cable bumped) or corrupts a written byte
  (marginal SWD), which only the read-back catches.
- The mission computer is a **simulated recovery-mode device**. It has an EEPROM, NVMe partitions, a first boot
  and fuses that stay burnt wherever the module goes. Durations are modelled from partition sizes and the link
  speed, so a USB2 link really costs three times as long.
- A **campaign** describes a shift: airframes, releases and when they switch, what boards and modules are made of,
  and the faults the shift carries. The faults are the truth. Only `src/uavtrail/evaluate.py` reads it, and a test
  checks that the station, server and analysis never import the simulator.

`uavsim run campaigns/dev/shift-a.yaml` runs a 160-airframe shift on 12 slots through the real station software
and the real server in about 30 seconds.

## Measured

On the dev shift (`campaigns/dev/shift-a.yaml`, written alongside the code), the analysis named 6 of 6 systemic
causes and raised no false alarm. Every trail and certificate verified, and every fuse burn was guarded.

The held-out set was written by an agent that read only `heldout/WRITING_CAMPAIGNS.md` and never saw the code:
five shifts, 674 airframes. Its first run is recorded once in `reports/heldout/v1/first_run.json`, and CI fails
if it changes.

| Held-out v1, first run | |
| --- | --- |
| Systemic causes named, with the right code and place | 18 of 20 |
| Systemic issues the truth does not explain (false alarms) | 2 |
| Trails or certificates that failed to verify | 0 |
| Fuse burns without their guard | 0 |

The analysis has not been changed since that run. If it is changed using what v1 shows, v1 becomes a
regression set and a new set is written blind.

Statistically, on pure noise the analysis calls something systemic in at most 5% of shifts per failure code (a
test checks it over 200 noise shifts).

## Tests

- `pytest -q`: 70 tests. Real firmware is flashed, read back and booted in QEMU. Fixture faults surface as their
  own codes, and re-attaching to a running part works. The GDB protocol is tested against a scripted probe,
  including NAKs, garbled replies and the vFlash packets of a probe with a flash driver. Also covered: the guard
  under every combination of unmet preconditions, a crash mid-step, an offline server, chain tampering, release
  tampering, the server's refusals and append-only trail, and a whole shift against its truth.
- `cd web && npm run check`: TypeScript, ESLint, Prettier and 23 Vitest tests on API answers captured from a
  shift. `npx playwright test`: 5 flows on desktop and phone against the running server.

## Run it

```sh
docker compose up        # PostgreSQL, one emulated shift, then http://localhost:8000
```

Or by hand, with PostgreSQL, `qemu-system-arm` and `gcc-arm-none-eabi` installed:

```sh
pip install -e ".[dev]"
export UAV_DATABASE_URL=postgresql+psycopg://uav:uav@localhost:5432/uav
uavsim run campaigns/dev/shift-a.yaml     # build firmware, sign releases, run the shift
uavtrail evaluate data/runs/shift-a        # against the truth
uavtrail issues | uavtrail kpis            # what the lead sees, as JSON
uavtrail instructions check R2026.10       # the work instruction against a release
(cd web && npm ci && npm run build) && uavtrail serve
```

## The console

React 19, TanStack Query and Framer Motion, in feature folders over shared design tokens. One type family
(Archivo) is used across its width axis, and colour is kept for state. Every view has a skeleton, an error with a
retry and an empty state.

- **Line**: the fixture board. Every slot shows the airframe on it and its place in the recipe on a step rail,
  with the irreversible fuse step notched in orange. It also shows the slot's last airframes and its numbers.
  Slots a systemic issue points at are ringed.
- **Issues**: systemic, widespread and one-off, with the odds of chance, the place, the owner and what to do.
  The lead, engineering or quality act on them (acknowledge, mark fixed from a time, note).
- **Airframes**: the hash-linked trail as stored, the verification result, and the signed certificate to
  download.
- **Releases**: rollout per release and the where-used recall list.
- **Work instruction**: where it disagrees with the release.

| | |
| --- | --- |
| ![Issues](docs/screenshots/issues.png) | ![A paper trail](docs/screenshots/trail.png) |

## Limits

- No real hardware has been through it. The GDB-protocol flasher speaks what OpenOCD and J-Link speak (memory
  writes, and vFlash when a probe announces a flash driver), but it has only been run against QEMU and a scripted
  probe.
- On hardware, the mission computer would be flashed with NVIDIA's `l4t_initrd_flash.sh`. The station builds that
  command (`targets/orin.py`) but here talks to a simulator.
- The work instruction is a YAML export, not the API of a real work-instruction tool.
- The firmware is a stand-in that does what production needs to see (boot, identity, self-test), not flight
  software.
- Statistics need volume: a systemic fault that shows on two or three airframes in a shift is called one-off, and
  the watch list is there for that.
