#pragma once

#include <stdbool.h>
#include <stddef.h>

typedef int (*min_heap_cmp_t)(const void *left, const void *right);
typedef bool (*min_heap_eq_t)(const void *node, const void *key);

struct min_heap {
  void *storage;
  size_t capacity;
  size_t elem_size;
  size_t size;
  min_heap_cmp_t cmp;
};

void min_heap_init(struct min_heap *heap, void *storage, size_t capacity,
                   size_t elem_size, min_heap_cmp_t cmp);
int min_heap_push(struct min_heap *heap, const void *item);
void *min_heap_peek(const struct min_heap *heap);
bool min_heap_pop(struct min_heap *heap, void *out);
bool min_heap_remove(struct min_heap *heap, size_t index, void *out);
void *min_heap_find(struct min_heap *heap, min_heap_eq_t eq, const void *key,
                    size_t *out_index);
