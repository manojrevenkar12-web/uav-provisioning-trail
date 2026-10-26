# make TARGET=fc VERSION=1.14.2 KNOWN_REVS=BC OUT=build/fc-1.14.2
# Writes $(OUT).elf and $(OUT).bin; the .bin carries a CRC-32 trailer the firmware checks at boot.
CC = arm-none-eabi-gcc
OBJCOPY = arm-none-eabi-objcopy
TARGET ?= fc
VERSION ?= 0.0.0
KNOWN_REVS ?= BC
OUT ?= build/$(TARGET)-$(VERSION)
CPU_fc = cortex-m4
CPU_pmu = cortex-m3
DEF_fc = TARGET_FC
DEF_pmu = TARGET_PMU
CFLAGS = -mcpu=$(CPU_$(TARGET)) -mthumb -Os -nostdlib -ffreestanding -fno-builtin -Wall -Wextra -Werror \
  -D$(DEF_$(TARGET)) -DFW_VERSION=$(VERSION) -DFW_KNOWN_REVS='"$(KNOWN_REVS)"' -Isrc

all: $(OUT).bin

$(OUT).elf: src/main.c src/layout.h boards/$(TARGET).ld boards/sections.ld
	@mkdir -p $(dir $(OUT))
	$(CC) $(CFLAGS) -Wl,-L,boards -T boards/$(TARGET).ld src/main.c -o $@

$(OUT).bin: $(OUT).elf
	$(OBJCOPY) -O binary $< $@
	python3 trailer.py $@

clean:
	rm -rf build
.PHONY: all clean
