/*
 * Firmware stand-in for the flight controller (TARGET_FC) and the power module (TARGET_PMU).
 *
 * It does what the production line needs to see from real firmware: it boots, prints a banner with its version,
 * the board identity and the unit configuration, checks its own image and configuration, runs a sensor self-test
 * and prints one verdict line. The station reads that over the UART.
 */
#include "layout.h"

#define REG(a) (*(volatile uint32_t *)(a))
#define SR (USART_BASE + 0x00)
#define DR (USART_BASE + 0x04)
#define CR1 (USART_BASE + 0x0C)

#ifndef FW_VERSION
#error "FW_VERSION is set by the build"
#endif
#define STR2(x) #x
#define STR(x) STR2(x)

extern uint32_t _sidata, _sdata, _edata, _sbss, _ebss, _estack, _image_start, _image_end;

static void uart_init(void) { REG(CR1) = (1u << 13) | (1u << 3); /* UE, TE */ }

static void putc_(char c) {
  for (uint32_t spin = 0; spin < 100000u && !(REG(SR) & (1u << 7)); spin++) {
  }
  REG(DR) = (uint32_t)c;
}

static void puts_(const char *s) {
  while (*s) putc_(*s++);
}

static void puthex(const uint8_t *p, uint32_t n) {
  static const char digits[] = "0123456789abcdef";
  for (uint32_t i = 0; i < n; i++) {
    putc_(digits[p[i] >> 4]);
    putc_(digits[p[i] & 15]);
  }
}

static void putword(uint32_t w) {
  uint8_t b[4] = {(uint8_t)(w >> 24), (uint8_t)(w >> 16), (uint8_t)(w >> 8), (uint8_t)w};
  puthex(b, 4);
}

static uint32_t crc32(const uint8_t *p, uint32_t n) {
  uint32_t c = 0xFFFFFFFFu;
  for (uint32_t i = 0; i < n; i++) {
    c ^= p[i];
    for (int k = 0; k < 8; k++) c = (c >> 1) ^ (0xEDB88320u & (uint32_t)-(int32_t)(c & 1u));
  }
  return ~c;
}

static int otp_ok(const otp_t *o) { return o->magic == OTP_MAGIC && o->crc == crc32((const uint8_t *)o, sizeof(*o) - 4); }

static int cfg_ok(const config_t *c) {
  return c->magic == CFG_MAGIC && c->layout == 1u && c->crc == crc32((const uint8_t *)c, sizeof(*c) - 4);
}

static int image_ok(void) {
  const uint8_t *start = (const uint8_t *)&_image_start;
  uint32_t n = (uint32_t)((const uint8_t *)&_image_end - start);
  const uint32_t trailer = *(const uint32_t *)(start + n);
  return trailer == crc32(start, n);
}

/* Sensor self-test. A board revision the build does not know gets no sensor driver (FW_KNOWN_REVS). */
static int sensors_ok(char rev) {
  const char *known = FW_KNOWN_REVS;
  for (; *known; known++)
    if (*known == rev) return 1;
  return 0;
}

static int bounded_cal(const config_t *c) {
  for (int i = 0; i < 6; i++)
    if (c->cal[i] > 500000 || c->cal[i] < -500000) return 0;
  return 1;
}

/* Waits for interrupts instead of spinning: on the bench it saves power, on the emulated line it frees the host. */
static void idle(void) {
  for (;;) __asm__ volatile("wfi");
}

void main_(void) {
  const otp_t *otp = (const otp_t *)OTP_ADDR;
  const config_t *cfg = (const config_t *)CFG_ADDR;
  uart_init();
  int o = otp_ok(otp), c = cfg_ok(cfg), img = image_ok();
  char rev = o ? otp->board_rev : '?';
#if defined(TARGET_FC)
  puts_("BOOT fc fw=");
#else
  puts_("BOOT pmu fw=");
#endif
  puts_(STR(FW_VERSION));
  puts_(" board=");
  putc_(rev);
  puts_(" uid=");
  if (o)
    puthex(otp->uid, 12);
  else
    puts_("none");
  puts_(" unit=");
  if (c) {
    for (int i = 0; i < 16 && cfg->unit_serial[i]; i++) putc_(cfg->unit_serial[i]);
  } else {
    puts_("none");
  }
  puts_(" cfg=");
  putword(c ? cfg->crc : 0);
  puts_("\r\n");

  int sens = o && sensors_ok(rev);
  int cal = c && bounded_cal(cfg);
  puts_("SELFTEST img=");
  puts_(img ? "ok" : "bad");
  puts_(" otp=");
  puts_(o ? "ok" : "bad");
  puts_(" cfg=");
  puts_(c ? "ok" : "bad");
  puts_(" cal=");
  puts_(cal ? "ok" : "bad");
  puts_(" sensors=");
  puts_(sens ? "ok" : "fail");
  puts_("\r\n");
  puts_(img && o && c && cal && sens ? "SELFTEST PASS\r\n" : "SELFTEST FAIL\r\n");
  idle();
}

void reset_handler(void) {
  uint32_t *src = &_sidata, *dst = &_sdata;
  while (dst < &_edata) *dst++ = *src++;
  for (dst = &_sbss; dst < &_ebss;) *dst++ = 0;
  main_();
}

void default_handler(void) { idle(); }

__attribute__((section(".vectors"), used)) const void *const vectors[] = {
    &_estack, reset_handler, default_handler, default_handler,
};
