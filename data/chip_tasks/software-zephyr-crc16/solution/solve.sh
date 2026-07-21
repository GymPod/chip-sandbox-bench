#!/bin/sh
set -eu
cat > /workspace/utility.c <<'C'
#include "utility.h"
uint16_t crc16_ccitt(uint16_t crc,const uint8_t*d,size_t n){for(size_t i=0;i<n;i++){crc^=(uint16_t)d[i]<<8;for(int b=0;b<8;b++)crc=(crc&0x8000)?(uint16_t)((crc<<1)^0x1021):(uint16_t)(crc<<1);}return crc;}
C
