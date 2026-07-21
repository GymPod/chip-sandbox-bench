#include <stddef.h>
#include <stdint.h>
uint32_t fnv1a32_update(uint32_t state,const void*data,size_t length); uint32_t fnv1a32(const void*data,size_t length);
