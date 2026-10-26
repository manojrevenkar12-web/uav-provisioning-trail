# 1. Nothing written is trusted until it is read back

Status: accepted

A flash write can land wrong without any error on the link (marginal SWD, a bad NVMe block). The station reads
back every image, every configuration record and every mission-computer partition, and compares hashes with what
it wrote. The firmware also checks its own CRC trailer at boot. Cost: a few seconds per microcontroller, and a
minute for the module's partitions, which the line pays on every unit.
