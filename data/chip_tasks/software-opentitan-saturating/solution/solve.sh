#!/bin/sh
set -eu
cat > /workspace/utility.c <<'C'
#include <stdint.h>
#include "utility.h"
uint32_t sat_add_u32(uint32_t a,uint32_t b){return UINT32_MAX-a<b?UINT32_MAX:a+b;}
uint32_t sat_sub_u32(uint32_t a,uint32_t b){return a<b?0:a-b;}
uint32_t sat_mul_u32(uint32_t a,uint32_t b){return b&&a>UINT32_MAX/b?UINT32_MAX:a*b;}
C
