#include "min_heap.h"

#include <assert.h>
#include <stdbool.h>
#include <stddef.h>

struct item {
  int key;
  unsigned char payload[3];
};

static int ascending(const void *left, const void *right) {
  const struct item *a = left;
  const struct item *b = right;
  return (a->key > b->key) - (a->key < b->key);
}

static int descending(const void *left, const void *right) {
  return -ascending(left, right);
}

static bool key_matches(const void *item, const void *key) {
  return ((const struct item *)item)->key == *(const int *)key;
}

static void push_all(struct min_heap *heap, const int *keys, size_t count) {
  for (size_t index = 0; index < count; ++index) {
    struct item item = {.key = keys[index], .payload = {1, 2, 3}};
    assert(min_heap_push(heap, &item) == 0);
  }
}

int main(void) {
  const int keys[] = {10, 5, 30, 2, 3, 4, 6, 22};
  struct item storage[8];
  struct min_heap heap;
  min_heap_init(&heap, storage, 8, sizeof(struct item), ascending);
  assert(min_heap_peek(&heap) == NULL);
  push_all(&heap, keys, 8);
  assert(((struct item *)min_heap_peek(&heap))->key == 2);
  struct item extra = {.key = 1};
  assert(min_heap_push(&heap, &extra) == -1);

  int previous = -1000;
  while (heap.size != 0) {
    struct item out;
    assert(min_heap_pop(&heap, &out));
    assert(out.key >= previous);
    previous = out.key;
    assert(out.payload[0] == 1);
  }
  assert(!min_heap_pop(&heap, &extra));

  min_heap_init(&heap, storage, 8, sizeof(struct item), ascending);
  push_all(&heap, keys, 8);
  int target = 5;
  size_t target_index = 99;
  struct item *found = min_heap_find(&heap, key_matches, &target, &target_index);
  assert(found != NULL && found->key == 5 && target_index < heap.size);
  struct item removed;
  assert(min_heap_remove(&heap, target_index, &removed));
  assert(removed.key == 5);
  assert(min_heap_find(&heap, key_matches, &target, NULL) == NULL);
  assert(!min_heap_remove(&heap, heap.size, &removed));

  previous = -1000;
  while (min_heap_pop(&heap, &removed)) {
    assert(removed.key >= previous);
    previous = removed.key;
  }

  min_heap_init(&heap, storage, 8, sizeof(struct item), descending);
  push_all(&heap, keys, 8);
  previous = 1000;
  while (min_heap_pop(&heap, &removed)) {
    assert(removed.key <= previous);
    previous = removed.key;
  }
  return 0;
}
