/* STM32F100 (QEMU stm32vldiscovery): 128 KiB flash, 8 KiB RAM. The image may use the first 64 KiB. */
MEMORY {
  FLASH (rx) : ORIGIN = 0x08000000, LENGTH = 64K
  RAM (rwx)  : ORIGIN = 0x20000000, LENGTH = 8K
}
INCLUDE sections.ld
