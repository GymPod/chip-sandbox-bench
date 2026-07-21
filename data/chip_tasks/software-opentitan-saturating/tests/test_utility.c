#include <assert.h>
#include <stdint.h>
#include "utility.h"
int main(void){assert(sat_add_u32(10,20)==30);assert(sat_add_u32(UINT32_MAX,1)==UINT32_MAX);
 assert(sat_sub_u32(4,9)==0&&sat_sub_u32(9,4)==5);
 assert(sat_mul_u32(0,UINT32_MAX)==0);assert(sat_mul_u32(65536,65536)==UINT32_MAX);assert(sat_mul_u32(12,11)==132);return 0;}
