#include <assert.h>
#include <stdint.h>
#include "utility.h"
int main(void){
 assert(bitfield_read32(0xdeadbeef,(bitfield_t){8,8})==0xbe);
 assert(bitfield_write32(0xffffffff,(bitfield_t){8,8},0x12)==0xffff12ff);
 assert(bitfield_read32(0x12345678,(bitfield_t){0,32})==0x12345678);
 assert(bitfield_write32(7,(bitfield_t){4,0},3)==7);
 assert(bitfield_read32(7,(bitfield_t){31,2})==0);
 assert(bitfield_write32(7,(bitfield_t){31,2},0)==7);
 return 0;
}
