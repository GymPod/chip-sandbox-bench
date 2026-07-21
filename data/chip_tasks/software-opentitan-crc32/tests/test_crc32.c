#include "crc32.h"

#include <assert.h>
#include <stdint.h>
#include <string.h>

static void check(const void *data, size_t length, uint32_t expected) {
  assert(crc32(data, length) == expected);

  const uint8_t *bytes = data;
  uint32_t context;
  crc32_init(&context);
  for (size_t index = 0; index < length; ++index) {
    crc32_add8(&context, bytes[index]);
  }
  assert(crc32_finish(&context) == expected);

  crc32_init(&context);
  size_t split = length / 3;
  crc32_add(&context, bytes, split);
  crc32_add(&context, bytes + split, length - split);
  assert(crc32_finish(&context) == expected);
}

int main(void) {
  check("", 0, 0x00000000u);
  check("123456789", 9, 0xcbf43926u);
  check("The quick brown fox jumps over the lazy dog", 43, 0x414fa339u);

  uint8_t unaligned[] = {
      0xff, 0xfe, 0xca, 0xfe, 0xca, 0x02, 0xb0, 0xad, 0x1b, 0xee};
  check(&unaligned[1], 8, 0x9508ac14u);

  uint32_t context;
  crc32_init(&context);
  crc32_add32(&context, 0xcafecafeu);
  crc32_add32(&context, 0x1badb002u);
  assert(crc32_finish(&context) == 0x9508ac14u);

  crc32_init(&context);
  crc32_add(&context, NULL, 0);
  assert(crc32_finish(&context) == 0);
  return 0;
}
