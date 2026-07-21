#!/bin/sh
cat > /workspace/min_heap.c <<'C'
#include "min_heap.h"

#include <string.h>

static unsigned char *element(const struct min_heap *heap, size_t index) {
  return (unsigned char *)heap->storage + index * heap->elem_size;
}

static void swap(struct min_heap *heap, size_t left, size_t right) {
  unsigned char *a = element(heap, left);
  unsigned char *b = element(heap, right);
  for (size_t index = 0; index < heap->elem_size; ++index) {
    unsigned char temporary = a[index];
    a[index] = b[index];
    b[index] = temporary;
  }
}

static void sift_up(struct min_heap *heap, size_t index) {
  while (index > 0) {
    size_t parent = (index - 1) / 2;
    if (heap->cmp(element(heap, parent), element(heap, index)) <= 0) {
      break;
    }
    swap(heap, parent, index);
    index = parent;
  }
}

static void sift_down(struct min_heap *heap, size_t index) {
  for (;;) {
    size_t left = index * 2 + 1;
    if (left >= heap->size) {
      return;
    }
    size_t right = left + 1;
    size_t best = left;
    if (right < heap->size &&
        heap->cmp(element(heap, right), element(heap, left)) < 0) {
      best = right;
    }
    if (heap->cmp(element(heap, index), element(heap, best)) <= 0) {
      return;
    }
    swap(heap, index, best);
    index = best;
  }
}

void min_heap_init(struct min_heap *heap, void *storage, size_t capacity,
                   size_t elem_size, min_heap_cmp_t cmp) {
  heap->storage = storage;
  heap->capacity = capacity;
  heap->elem_size = elem_size;
  heap->size = 0;
  heap->cmp = cmp;
}

int min_heap_push(struct min_heap *heap, const void *item) {
  if (heap->size == heap->capacity) {
    return -1;
  }
  memcpy(element(heap, heap->size), item, heap->elem_size);
  sift_up(heap, heap->size);
  ++heap->size;
  return 0;
}

void *min_heap_peek(const struct min_heap *heap) {
  return heap->size == 0 ? NULL : element(heap, 0);
}

bool min_heap_remove(struct min_heap *heap, size_t index, void *out) {
  if (index >= heap->size) {
    return false;
  }
  memcpy(out, element(heap, index), heap->elem_size);
  --heap->size;
  if (index == heap->size) {
    return true;
  }
  memcpy(element(heap, index), element(heap, heap->size), heap->elem_size);
  if (index > 0 &&
      heap->cmp(element(heap, index), element(heap, (index - 1) / 2)) < 0) {
    sift_up(heap, index);
  } else {
    sift_down(heap, index);
  }
  return true;
}

bool min_heap_pop(struct min_heap *heap, void *out) {
  return min_heap_remove(heap, 0, out);
}

void *min_heap_find(struct min_heap *heap, min_heap_eq_t eq, const void *key,
                    size_t *out_index) {
  for (size_t index = 0; index < heap->size; ++index) {
    void *candidate = element(heap, index);
    if (eq(candidate, key)) {
      if (out_index != NULL) {
        *out_index = index;
      }
      return candidate;
    }
  }
  return NULL;
}
C
