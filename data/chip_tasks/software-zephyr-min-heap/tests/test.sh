#!/bin/sh
set -eu
gcc -std=c11 -Wall -Wextra -Werror -I/workspace \
  /workspace/min_heap.c /tests/test_min_heap.c -o /tmp/test_min_heap
/tmp/test_min_heap
