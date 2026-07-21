#include <stdint.h>
uint16_t load_le16(const void *p); uint32_t load_le32(const void *p); uint32_t load_be32(const void *p);
void store_le16(void *p,uint16_t v); void store_le32(void *p,uint32_t v); void store_be32(void *p,uint32_t v);
