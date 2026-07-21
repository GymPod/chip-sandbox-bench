#!/bin/sh
set -eu
cat > /workspace/utility.c <<'C'
#include "utility.h"
void rb_init(ring_buffer_t*r,uint8_t*s,size_t c){r->data=s;r->capacity=c;r->head=r->tail=r->size=0;}
size_t rb_put(ring_buffer_t*r,const uint8_t*s,size_t n){size_t done=0;while(done<n&&r->size<r->capacity){r->data[r->tail]=s[done++];r->tail=(r->tail+1)%r->capacity;r->size++;}return done;}
size_t rb_get(ring_buffer_t*r,uint8_t*d,size_t n){size_t done=0;while(done<n&&r->size){d[done++]=r->data[r->head];r->head=(r->head+1)%r->capacity;r->size--;}return done;}
C
