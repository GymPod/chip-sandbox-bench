#include <assert.h>
#include <string.h>
#include "utility.h"
int main(void){const uint8_t*s=(const uint8_t*)"123456789";assert(crc16_ccitt(0xffff,s,9)==0x29b1);
 uint16_t a=crc16_ccitt(0xffff,s,4);a=crc16_ccitt(a,s+4,5);assert(a==0x29b1);
 assert(crc16_ccitt(0x1234,s,0)==0x1234);return 0;}
