#!/bin/sh
set -eu
cat > /workspace/utility.c <<'C'
#include <limits.h>
#include <stdint.h>
#include "utility.h"
static int32_t clamp(int64_t x){return x>INT32_MAX?INT32_MAX:x<INT32_MIN?INT32_MIN:(int32_t)x;}
int32_t q16_mul(int32_t a,int32_t b){int64_t p=(int64_t)a*b; p+=p>=0?32768:-32768; return clamp(p/65536);}
int32_t q16_div(int32_t a,int32_t b){if(!b)return a>0?INT32_MAX:a<0?INT32_MIN:0;return clamp(((int64_t)a*65536)/b);}
C
