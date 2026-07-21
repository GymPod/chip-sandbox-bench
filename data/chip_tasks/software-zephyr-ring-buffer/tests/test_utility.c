#include <assert.h>
#include <string.h>
#include "utility.h"
int main(void){uint8_t s[4],out[6],a[]={1,2,3,4},b[]={5,6};ring_buffer_t r;rb_init(&r,s,4);
 assert(rb_put(&r,a,4)==4&&rb_put(&r,b,2)==0);assert(rb_get(&r,out,2)==2);
 assert(rb_put(&r,b,2)==2);assert(rb_get(&r,out+2,4)==4);
 uint8_t expected[]={1,2,3,4,5,6};assert(!memcmp(out,expected,6));
 rb_init(&r,s,0);assert(rb_put(&r,a,1)==0&&rb_get(&r,out,1)==0);return 0;}
