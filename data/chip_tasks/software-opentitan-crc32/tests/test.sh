#!/bin/sh
set -eu
gcc -std=c11 -Wall -Wextra -Werror -I/workspace \
  /workspace/crc32.c /tests/test_crc32.c -o /tmp/test_crc32
/tmp/test_crc32
