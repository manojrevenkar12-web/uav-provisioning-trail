/* STM32F405 (QEMU netduinoplus2): 1 MiB flash, 128 KiB RAM. The image may use the first 256 KiB. */
MEMORY {
  FLASH (rx) : ORIGIN = 0x08000000, LENGTH = 256K
  RAM (rwx)  : ORIGIN = 0x20000000, LENGTH = 128K
}
INCLUDE sections.ld
