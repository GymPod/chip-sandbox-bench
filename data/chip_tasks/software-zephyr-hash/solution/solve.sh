#!/bin/sh
set -eu
cat > /workspace/utility.c <<'C'
#include "utility.h"
uint32_t fnv1a32_update(uint32_t s,const void*d,size_t n){const uint8_t*p=d;for(size_t i=0;i<n;i++){s^=p[i];s*=UINT32_C(16777619);}return s;}
uint32_t fnv1a32(const void*d,size_t n){return fnv1a32_update(UINT32_C(2166136261),d,n);}
C
