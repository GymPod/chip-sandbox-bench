#!/bin/sh
set -eu
cat > /workspace/utility.c <<'C'
#include "utility.h"
uint16_t load_le16(const void*p){const uint8_t*b=p;return (uint16_t)b[0]|((uint16_t)b[1]<<8);}
uint32_t load_le32(const void*p){const uint8_t*b=p;return (uint32_t)b[0]|((uint32_t)b[1]<<8)|((uint32_t)b[2]<<16)|((uint32_t)b[3]<<24);}
uint32_t load_be32(const void*p){const uint8_t*b=p;return ((uint32_t)b[0]<<24)|((uint32_t)b[1]<<16)|((uint32_t)b[2]<<8)|b[3];}
void store_le16(void*p,uint16_t v){uint8_t*b=p;b[0]=v;b[1]=v>>8;}
void store_le32(void*p,uint32_t v){uint8_t*b=p;for(int i=0;i<4;i++)b[i]=v>>(8*i);}
void store_be32(void*p,uint32_t v){uint8_t*b=p;for(int i=0;i<4;i++)b[i]=v>>(8*(3-i));}
C
