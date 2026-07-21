#include <stdint.h>
typedef struct { uint8_t index; uint8_t width; } bitfield_t;
uint32_t bitfield_read32(uint32_t value, bitfield_t field);
uint32_t bitfield_write32(uint32_t value, bitfield_t field, uint32_t field_value);
