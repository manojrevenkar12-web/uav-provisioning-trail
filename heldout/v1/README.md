# Held-out set v1

Five shifts written from `heldout/WRITING_CAMPAIGNS.md` only, without seeing the analysis or the simulator.
Expected counts below are rough estimates from the shares (a slot sees about a twelfth of the shift).

**s1-midshift-release** (120 airframes, R2026.09 for units 1-60, R2026.10 from unit 61, two operators per station).
Systemic: worn FC pogo pins on slot FX-B/2 (`fixture_contact`, p 0.7, about 7 airframes); corrupted identity
EEPROMs in Orin batch B26W41 (`supplier_eeprom_crc`, p 0.25 on 40% of modules, about 12); `payload-bridge.service`
failing on SKU 0001 under image 3.2.0 (`service_on_sku`, only the R2026.10 half, about 18). One-off: `random_link`
(0.03) and `nvme_defect` (0.02). What makes it hard: the service failure appears only after the mid-shift release
switch, so it must be placed on the SKU rather than blamed on the release or on the time of day, and the random link
noise produces some `link_refused` outside FX-B/2 that should not pull the slot finding apart or be called systemic.

**s2-same-symptom** (180 airframes, R2026.10 all shift, three operators on ST-1 and two on ST-2, FC revision D at 15%).
Systemic: operator OP-09 disturbing the PMU cable (`operator_handling`, p 0.2, about 8 of the roughly 40 airframes
they handle); worn PMU pins on slot FX-A/3 (`fixture_contact`, p 0.6, about 9); FC firmware 1.15.0 lacking the
sensor driver for revision D (`firmware_board_gap`, about 27); blank PMU OTP in lot P2609-07, which only 20% of
airframes use (`supplier_otp_blank`, p 0.3, about 11). One-off: `random_link` (0.05), `calibration_outlier` on FC
(0.03), `board_swap` (0.02). What makes it hard: three link problems sit on top of each other on the same station
(an operator dropping links mid-write, a slot refusing attaches, and random link noise that also drops links and
refuses attaches), OP-09 works across all of ST-1's slots so the drops must be placed on the operator not a slot,
and the OTP fault is in a minority lot shared with two clean PMU lots.

**s3-usb-trouble** (90 airframes, R2026.09 only, a single operator on ST-1, small shift).
Systemic: a bad USB cable on FX-A/4 (`usb_cable`, enumeration fails with p 0.7 and every module links at USB2,
about 7-8 airframes); USB resets during the mission-computer flash on FX-B/1 (`usb_drop`, p 0.8, about 6); blank FC
OTP in lot L2609-140 (`supplier_otp_blank`, p 0.35 on 25% of boards, about 8); FC firmware 1.14.2 lacking the driver
for revision C, which is only 10% of the mix (`firmware_board_gap`, about 9). One-off: `nvme_defect` (0.04) and
`board_swap` (0.03). What makes it hard: the shift is small, so the slot faults touch only a handful of airframes
each and two different USB problems sit on neighbouring fixtures of the same station; the slow-linking symptom on
FX-A/4 shows as flash time rather than a hard failure; NVMe defects also hit the mission-computer flash and must not
be confused with the USB slots; and the revision C gap is a low but steady count.

**s4-late-switch** (200 airframes, R2026.09 for units 1-140, R2026.10 from unit 141, FC revision D at 6%).
Systemic: worn PMU pins on FX-A/1 that only start at unit 80 (`fixture_contact`, p 0.7, `from_unit: 80`, about 7);
worn FC pins on FX-C/3 at a lower rate across the whole shift (`fixture_contact`, p 0.4, about 7); image 3.2.0 built
with a fixed machine-id (`baked_machine_id` on R2026.10, about 59 duplicates in the last 60 airframes); corrupted
EEPROMs in the small Orin batch B26W44 (`supplier_eeprom_crc`, p 0.2 on 15%, about 6). In addition the revision D
boards built under R2026.09 (about 8) are refused by the station, which the answer key counts as systemic at
`fc_rev = D`. One-off: `random_link` (0.04), `calibration_outlier` on PMU (0.03), `nvme_defect` (0.02). What makes
it hard: the FX-A/1 fault is clean for the first part of the shift, so a whole-shift rate dilutes it; two worn slots
on different stations hit different targets; the late release switch makes the machine-id duplicates appear only
in the last 30% of the shift, together with revision D boards suddenly being accepted; and the EEPROM batch is small.

**s5-night-shift** (84 airframes, night start, R2026.10 only, two operators on ST-1, one on ST-2, single FC lot).
Systemic: operator OP-02 disturbing the PMU cable (`operator_handling`, p 0.3, about 8); a bad USB cable on FX-C/2
(`usb_cable`, enumeration p 0.5, USB2 links, about 7 airframes); `uav-link.service` failing on SKU 0001 under image
3.2.0 (`service_on_sku`, half the modules, about 42); FC firmware 1.15.0 lacking the driver for revision B
(`firmware_board_gap`, 20% of boards, about 17). One-off: `random_link` at a higher rate (0.06) and `board_swap`
(0.02). What makes it hard: the random link noise is close in rate to the operator fault, so OP-02's drops have to
stand out against roughly five random link events; FX-C/2 is on the station with a single operator, so the slot
fault must not be pinned on OP-05; and revision D is 30% of the mix and must not be blamed while revision B fails.
