#include <assert.h>
#include <stdint.h>
#include <string.h>
#include "utility.h"
int main(void){uint8_t b[9]={0}; store_le16(b+1,0x1234); assert(b[1]==0x34&&b[2]==0x12&&load_le16(b+1)==0x1234);
 store_le32(b+1,0x89abcdef); assert(load_le32(b+1)==0x89abcdef); assert(b[1]==0xef&&b[4]==0x89);
 store_be32(b+3,0x10203040); assert(load_be32(b+3)==0x10203040); assert(b[3]==0x10&&b[6]==0x40); return 0;}
