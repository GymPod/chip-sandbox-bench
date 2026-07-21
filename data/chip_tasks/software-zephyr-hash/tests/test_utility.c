#include <assert.h>
#include <string.h>
#include "utility.h"
int main(void){const char*s="hello";assert(fnv1a32(s,5)==0x4f9f2cab);assert(fnv1a32("",0)==2166136261u);
 uint32_t h=fnv1a32("he",2);h=fnv1a32_update(h,"llo",3);assert(h==fnv1a32(s,5));
 unsigned char b[]={0,255,1};assert(fnv1a32(b,3)==fnv1a32_update(2166136261u,b,3));return 0;}
