#include <stddef.h>
#include <stdint.h>
typedef struct {uint8_t *data; size_t capacity,head,tail,size;} ring_buffer_t;
void rb_init(ring_buffer_t*r,uint8_t*storage,size_t capacity);
size_t rb_put(ring_buffer_t*r,const uint8_t*src,size_t count);
size_t rb_get(ring_buffer_t*r,uint8_t*dst,size_t count);
