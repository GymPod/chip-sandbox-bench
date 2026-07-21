#pragma once

#include <stddef.h>
#include <stdint.h>

void crc32_init(uint32_t *ctx);
void crc32_add8(uint32_t *ctx, uint8_t byte);
void crc32_add32(uint32_t *ctx, uint32_t word);
void crc32_add(uint32_t *ctx, const void *buf, size_t len);
uint32_t crc32_finish(const uint32_t *ctx);
uint32_t crc32(const void *buf, size_t len);
