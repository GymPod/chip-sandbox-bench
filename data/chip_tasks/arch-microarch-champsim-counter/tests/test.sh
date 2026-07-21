#!/bin/sh
set -eu
g++ -std=c++20 -Wall -Wextra -Werror -I/workspace /tests/test_counter.cpp -o /tmp/test_counter
/tmp/test_counter
