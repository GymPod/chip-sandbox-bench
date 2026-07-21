#include "utility.h"
void rb_init(ring_buffer_t*r,uint8_t*s,size_t c){(void)r;(void)s;(void)c;}
size_t rb_put(ring_buffer_t*r,const uint8_t*s,size_t n){(void)r;(void)s;(void)n;return 0;}
size_t rb_get(ring_buffer_t*r,uint8_t*d,size_t n){(void)r;(void)d;(void)n;return 0;}
