#include <assert.h>
#include <limits.h>
#include "utility.h"
int main(void){assert(q16_mul(98304,131072)==196608);assert(q16_mul(-98304,131072)==-196608);
 assert(q16_div(196608,131072)==98304);assert(q16_div(-196608,131072)==-98304);
 assert(q16_mul(INT32_MAX,INT32_MAX)==INT32_MAX);assert(q16_div(1,0)==INT32_MAX);assert(q16_div(-1,0)==INT32_MIN);assert(q16_div(0,0)==0);return 0;}
