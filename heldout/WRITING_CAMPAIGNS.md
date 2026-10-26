# Writing a held-out set of production shifts

You are writing test shifts for an analysis you have never seen. **Read only this file.** Do not open, list, search
or run anything else in the repository, and do not look at other held-out sets. The point is that the shifts are
written by someone who does not know how the analysis decides, so its score on them is honest.

## What is being tested

A UAV production line flashes the software of every airframe: a flight controller (FC) and a power module (PMU),
two microcontrollers, and a mission computer (a Jetson Orin-class module). Things go wrong on such a line, and a
production-support lead must tell, from the line's records alone, which problems are **systemic** (they live in
one place: a fixture slot, a supplier lot, a software release, a board revision, an operator...) and which are
**one-off** bad luck. The analysis under test gets the records of a shift and names systemic issues with the place
it thinks they live. It does not see your file.

You describe shifts. The line simulator turns each into airframes, runs them through the real station software and
records what happens. The answer key is derived from your faults (see "What counts as the right answer").

## The line (fixed)

- Station `ST-1` has fixtures `FX-A` and `FX-B`; station `ST-2` has fixture `FX-C`. Each fixture has 4 slots, so
  the slots are `FX-A/1` ... `FX-A/4`, `FX-B/1` ... `FX-B/4`, `FX-C/1` ... `FX-C/4` (12 in all).
- Each airframe goes to whichever slot frees up first, so every slot sees roughly a twelfth of the shift.
- Production-owned failures get one rework run at the end of the shift; all other holds stay held.

## The releases (fixed)

| Release | FC | PMU | Mission computer image | FC board revisions it supports | PMU revisions | Module SKUs |
| --- | --- | --- | --- | --- | --- | --- |
| R2026.09 | 1.14.2 | 2.3.1 | 3.1.4 | B, C | A, B | 0000, 0001 |
| R2026.10 | 1.15.0 | 2.3.1 | 3.2.0 | B, C, D | A, B | 0000, 0001 |

Mission computer services in both images: `uav-link.service`, `uav-telemetry.service`, `payload-bridge.service`.
An airframe whose FC is revision D, built while R2026.09 is active, is refused by the station (that is expected
behaviour, and the answer key counts it as a systemic finding at `fc_rev = D` automatically).

## The file format

One YAML file per shift in `heldout/<set>/campaigns/<name>.yaml`:

```yaml
campaign: <name, same as the file name without .yaml>
seed: <any integer>
start: "2026-11-03T06:00:00+01:00"      # when the shift starts
units: 120                               # airframes in the shift, 60 to 200
operators: {ST-1: [OP-07, OP-12], ST-2: [OP-03, OP-21]}   # 1 to 3 per station, any names like OP-nn
releases:                                # which release is active from which airframe (1-based) on
  - {release: R2026.09, from_unit: 1}
  - {release: R2026.10, from_unit: 61}  # optional; a shift may run one release only
mix:                                     # what the airframes are made of: value -> share (shares sum to 1)
  fc_rev: {B: 0.3, C: 0.7}               # B, C, D
  pmu_rev: {A: 0.5, B: 0.5}              # A, B
  orin_sku: {"0000": 0.7, "0001": 0.3}   # "0000", "0001" (quote them)
  fc_lot: {L2609-114: 0.5, L2610-021: 0.5}     # any lot names, 1 to 4 of them
  pmu_lot: {P2608-33: 1.0}
  orin_batch: {B26W38: 0.5, B26W41: 0.5}
faults:
  - {id: <unique short id>, kind: <kind>, ...parameters}
```

Operators are assigned to airframes at random among their station's operators.

## Fault kinds

Systemic (they live in one place):

| kind | parameters | what happens on the line |
| --- | --- | --- |
| `fixture_contact` | `slot`, `target` (fc or pmu), `p`, optional `from_unit`, `to_unit` | worn pogo pins: each time the station attaches its probe to that target on that slot, the attach fails with probability `p` (only for airframes numbered from_unit..to_unit if given) |
| `usb_cable` | `slot`, `enumerate_fail_p`, `usb2` (true/false) | a bad USB cable: the mission computer fails to enumerate with that probability per try; if `usb2`, it links at USB2 speed (slower flashes) |
| `usb_drop` | `slot`, `p` | the USB link resets during the mission-computer flash with probability `p` per flash |
| `supplier_eeprom_crc` | `orin_batch`, `p` | modules of that batch have a corrupted identity EEPROM with probability `p` |
| `supplier_otp_blank` | `target` (fc or pmu), `lot`, `p` | boards of that lot arrive without their programmed identity with probability `p` |
| `firmware_board_gap` | `target` (fc), `version` (an FC version from the table), `missing_rev` | that firmware version has no sensor driver for that board revision, although the release claims to support it: the self-test fails on every such board under a release shipping that version |
| `baked_machine_id` | `version` (a mission computer image), `release` (the release shipping it) | the image was built with a fixed machine-id: the second and later airframes on that release get a duplicate |
| `service_on_sku` | `version` (image), `service`, `sku` | that service fails at first boot on modules of that SKU running that image |
| `operator_handling` | `operator`, `target` (fc or pmu), `p` | the operator disturbs the cable during programming: with probability `p` per airframe they handle, the probe link drops mid-write |

One-off (random, nowhere in particular):

| kind | parameters | what happens |
| --- | --- | --- |
| `random_link` | `p` | with probability `p` per airframe, one probe attach is refused, drops mid-write, or one written byte arrives corrupted |
| `nvme_defect` | `p` | with probability `p` per airframe, the module has a bad storage block |
| `calibration_outlier` | `target`, `p` | the upstream calibration station sends an out-of-range value |
| `board_swap` | `p` | a board already used in an earlier airframe turns up again |

Probabilities are between 0 and 1. A fault may appear more than once with different ids (two bad slots, say).

## What counts as the right answer

The answer is derived from your faults, so you do not write it:

- every systemic fault must be named by the analysis as systemic, with its failure code and its place:

| kind | code it shows as | place |
| --- | --- | --- |
| fixture_contact | link_refused | slot = your slot |
| usb_cable | usb_enumeration_failed, or modules linking slowly | slot = your slot |
| usb_drop | usb_reset_during_flash | slot = your slot |
| supplier_eeprom_crc | eeprom_crc | orin_batch = your batch |
| supplier_otp_blank | otp_blank | fc_lot or pmu_lot = your lot |
| firmware_board_gap | selftest_fail | fc_rev = missing_rev |
| baked_machine_id | machine_id_duplicate | release = your release |
| service_on_sku | service_failed | orin_sku = your sku |
| operator_handling | link_dropped | operator = your operator |

- nothing else may be called systemic: one-off faults must stay one-off.

## How to write a good set

- Write **5 shifts**. Make them different from each other: different sizes, release timing, mixes, operators.
- Each shift should carry **2 to 5 systemic faults** and **1 to 3 one-off kinds**.
- Make them realistic and fair: a systemic fault should affect **at least 5 airframes** over the shift, so a careful
  lead with the records could see it. Rates on real lines range from a few percent to a third or more.
- Make some of them hard in ways that happen on real lines: two problems with the same symptom in different places
  (a worn slot and a careless operator both drop links), a lot that only some airframes use, a release switched
  mid-shift, a fault that starts part-way through (`from_unit`), a low but steady rate, one-off noise on top.
- Use only the kinds, parameters, slots, releases, versions and SKUs above, and keep every file valid YAML.

## Deliverables

- `heldout/<set>/campaigns/*.yaml`, one per shift
- `heldout/<set>/README.md`: one paragraph per shift saying what you put in it and what you think makes it hard

Do not write anything else, and do not run the simulator or the analysis.
