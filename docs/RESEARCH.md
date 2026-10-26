# What this was built against

The project answers Quantum Systems' advertisement for a Team Lead Software Production Support in Gilching. This
file records what the advertisement and public sources say, and where each point shows up in the platform.
Nothing here claims knowledge of Quantum Systems' internal tools; the airframe (HX-2), its boards and its line
are fictional.

## The role, point by point

| The advertisement asks for | Where it is |
| --- | --- |
| Robust processes for microcontroller flashing, Orin installation, firmware updates, diagnostics and recovery | `targets/mcu.py` (flash over a probe's GDB server, full read-back, boot and self-test), `targets/orin.py` (recovery-mode enumeration, EEPROM CRC, initrd-flash command, partition read-back, first boot), recovery per failure code in `config/codes.yaml` |
| Production tools that are reliable, versioned, documented, maintainable | signed releases (`releases.py`), recipe and codes as config, a test suite that flashes real firmware, CI |
| Requirements for traceability and a digital paper trail | hash-chained, station-signed trail with an outbox; append-only server; signed software certificates; where-used |
| Bottlenecks, recurring issues, process weaknesses; telling one-off issues from systemic ones | `analysis/issues.py`: per failure code, the place that stands out beyond chance, narrowed to the slot rather than the station; leading signals (USB2 links) |
| Work instructions that are technically correct and reflect the real process | `analysis/instructions.py`: the work-instruction export against recipe and release |
| KPIs: downtime, flashing success rate, recurring issues, software first-pass yield | `analysis/kpi.py`, the console's line view, by slot and by hour |
| Turning production issues into sustainable improvements | issue actions (acknowledge, fixed from a time, note) and whether a fix holds, before against after |
| Coordinating escalations with Engineering, Quality, Industrialization | every code has an owner; a held unit goes to its code's owner; issues carry owner and recommended action |
| Leading and developing the team | the console's roles (operator, lead, engineering, quality) and what each may do |

## Facts the design leans on

- Quantum Systems builds eVTOL UAS (Trinity, Vector, Twister and others) in Gilching and is scaling serial
  production, with government orders in the hundreds of systems ([Wikipedia][qs]).
- A related Quantum Systems production-software posting names firmware flashing and verification for
  microcontrollers, Linux image deployment for compute modules (boot media, recovery modes, partitioning), flashing
  stations, traceability of software versions, device identities and calibration data per unit, and the
  interfaces SWD, JTAG and USB on iMX8 and NVIDIA Orin ([posting][qs-prod]).
- NVIDIA's flashing guide for Jetson Linux: initrd flash (`l4t_initrd_flash.sh`, `--flash-only --network usb0`,
  `--massflash`) is the production method for Orin NX and Nano. Modules must be in force recovery. A low-quality
  cable can make flashing fail, and USB3 is checked with `lsusb -t`. The module EEPROM carries a CRC-8 in byte 255;
  a CRC fault alone can be repaired, while any other EEPROM fault is an RMA. Fuse burns are irreversible
  ([NVIDIA][flash]). These are the station's enumeration, EEPROM and fuse checks, and the USB2 watch signal.
- Cloned Jetson images can carry the same `/etc/machine-id` on every device ([NVIDIA forum][machineid]). Hence
  the first-boot machine-id uniqueness check and the `baked_machine_id` fault.
- The GDB Remote Serial Protocol is what OpenOCD, pyOCD and J-Link GDB servers expose. Flash writes go through
  the `vFlashErase`, `vFlashWrite` and `vFlashDone` packets on a probe with a flash driver ([GDB manual][rsp]).

## Sources

[qs]: https://en.wikipedia.org/wiki/Quantum-Systems
[qs-prod]: https://jobs.dukecapitalpartners.duke.edu/companies/quantum-systems-2/jobs/72194772-software-engineer-production-m-f-d
[flash]: https://docs.nvidia.com/jetson/archives/r36.2/DeveloperGuide/SD/FlashingSupport.html
[machineid]: https://forums.developer.nvidia.com/t/l4t-initrd-flash-sh-and-l4t-backup-restore-sh-generate-identical-etc-machine-id-on-cloned-jetson-devices/371659
[rsp]: https://sourceware.org/gdb/current/onlinedocs/gdb.html/Remote-Protocol.html

- [Quantum-Systems (Wikipedia)][qs]
- [Quantum Systems: Software Engineer Production (posting)][qs-prod]
- [NVIDIA Jetson Linux Developer Guide: Flashing Support][flash]
- [NVIDIA forum: identical machine-id on cloned Jetson devices][machineid]
- [GDB manual: Remote Serial Protocol][rsp]
