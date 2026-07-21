#!/bin/sh
set -eu
cat > /workspace/utility.c <<'C'
#include "utility.h"
void list_init(list_node_t*h){h->next=h->prev=h;}
static void between(list_node_t*a,list_node_t*b,list_node_t*n){n->prev=a;n->next=b;a->next=n;b->prev=n;}
void list_append(list_node_t*h,list_node_t*n){between(h->prev,h,n);} void list_prepend(list_node_t*h,list_node_t*n){between(h,h->next,n);}
void list_remove(list_node_t*n){n->prev->next=n->next;n->next->prev=n->prev;n->next=n->prev=n;}
list_node_t*list_pop_front(list_node_t*h){if(h->next==h)return 0;list_node_t*n=h->next;list_remove(n);return n;}
list_node_t*list_pop_back(list_node_t*h){if(h->prev==h)return 0;list_node_t*n=h->prev;list_remove(n);return n;}
C
