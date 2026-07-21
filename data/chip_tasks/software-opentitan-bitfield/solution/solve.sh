#!/bin/sh
set -eu
cat > /workspace/utility.c <<'C'
#include "utility.h"
static int valid(bitfield_t f){ return f.width<=32 && f.index<=31 && (unsigned)f.index+f.width<=32; }
static uint32_t mask(bitfield_t f){ return f.width==32?UINT32_MAX:(f.width==0?0:((UINT32_C(1)<<f.width)-1)); }
uint32_t bitfield_read32(uint32_t v, bitfield_t f){ return valid(f)?(v>>f.index)&mask(f):0; }
uint32_t bitfield_write32(uint32_t v, bitfield_t f, uint32_t x){ if(!valid(f))return v; uint32_t m=mask(f); return (v&~(m<<f.index))|((x&m)<<f.index); }
C
