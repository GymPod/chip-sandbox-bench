#!/bin/sh
set -eu
gcc -std=c11 -Wall -Wextra -Werror -pedantic -I/workspace   /workspace/utility.c /tests/test_utility.c -o /tmp/software-zephyr-fixed-point
/tmp/software-zephyr-fixed-point
