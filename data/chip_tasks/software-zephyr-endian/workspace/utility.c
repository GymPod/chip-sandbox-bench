#include "utility.h"
uint16_t load_le16(const void*p){(void)p;return 0;} uint32_t load_le32(const void*p){(void)p;return 0;} uint32_t load_be32(const void*p){(void)p;return 0;}
void store_le16(void*p,uint16_t v){(void)p;(void)v;} void store_le32(void*p,uint32_t v){(void)p;(void)v;} void store_be32(void*p,uint32_t v){(void)p;(void)v;}
