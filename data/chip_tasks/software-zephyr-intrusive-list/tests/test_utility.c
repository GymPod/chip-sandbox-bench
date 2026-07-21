#include <assert.h>
#include "utility.h"
int main(void){list_node_t h,a,b,c;list_init(&h);assert(!list_pop_front(&h));list_append(&h,&a);list_append(&h,&b);list_prepend(&h,&c);
 assert(list_pop_front(&h)==&c&&c.next==&c&&c.prev==&c);list_remove(&a);assert(a.next==&a&&h.next==&b);
 assert(list_pop_back(&h)==&b);assert(h.next==&h&&h.prev==&h);return 0;}
