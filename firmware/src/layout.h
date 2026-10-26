/*
 * Where things live in the microcontroller's flash. The station writes the same addresses (config/targets.yaml);
 * a test checks the two agree.
 *
 *   IMAGE   the firmware, with a 4-byte CRC-32 trailer the build appends
 *   OTP     identity the PCBA supplier programs: board revision, lot, unique id (one-time on real parts; a
 *           flash sector in the emulator)
 *   CONFIG  what the station writes per unit: unit serial and sensor calibration, with its own CRC-32
 */
#ifndef LAYOUT_H
#define LAYOUT_H
#include <stdint.h>

#define OTP_MAGIC 0x3150544Fu  /* "OTP1" */
#define CFG_MAGIC 0x47464355u  /* "UCFG" */

typedef struct {
  uint32_t magic;
  uint8_t uid[12];
  char board_rev;
  char lot[11];
  uint32_t crc;           /* CRC-32 of the bytes before it */
} otp_t;

typedef struct {
  uint32_t magic;
  uint32_t layout;        /* 1 */
  char unit_serial[16];   /* NUL padded */
  int32_t cal[6];         /* sensor offsets, micro-units */
  uint32_t crc;           /* CRC-32 of the bytes before it */
} config_t;

#if defined(TARGET_FC)
#define USART_BASE 0x40011000u /* STM32F405 USART1 */
#define OTP_ADDR 0x080C0000u
#define CFG_ADDR 0x080E0000u
#elif defined(TARGET_PMU)
#define USART_BASE 0x40013800u /* STM32F100 USART1 */
#define OTP_ADDR 0x0801F000u
#define CFG_ADDR 0x0801F800u
#else
#error "define TARGET_FC or TARGET_PMU"
#endif

#endif
