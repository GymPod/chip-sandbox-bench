#!/bin/sh
cat > /workspace/crc32.c <<'C'
#include "crc32.h"

#include <stdint.h>

enum { kCrc32Polynomial = 0xedb88320u };

static uint32_t add_byte(uint32_t context, uint8_t byte) {
  context ^= byte;
  for (unsigned bit = 0; bit < 8; ++bit) {
    uint32_t mask = 0u - (context & 1u);
    context = (context >> 1) ^ (kCrc32Polynomial & mask);
  }
  return context;
}

void crc32_init(uint32_t *ctx) { *ctx = UINT32_MAX; }

void crc32_add8(uint32_t *ctx, uint8_t byte) { *ctx = add_byte(*ctx, byte); }

void crc32_add32(uint32_t *ctx, uint32_t word) {
  for (unsigned shift = 0; shift < 32; shift += 8) {
    *ctx = add_byte(*ctx, (uint8_t)(word >> shift));
  }
}

void crc32_add(uint32_t *ctx, const void *buf, size_t len) {
  const uint8_t *bytes = buf;
  for (size_t index = 0; index < len; ++index) {
    *ctx = add_byte(*ctx, bytes[index]);
  }
}

uint32_t crc32_finish(const uint32_t *ctx) { return *ctx ^ UINT32_MAX; }

uint32_t crc32(const void *buf, size_t len) {
  uint32_t context;
  crc32_init(&context);
  crc32_add(&context, buf, len);
  return crc32_finish(&context);
}
C
