#!/bin/sh
set -eu
export PKG_CONFIG_PATH="/usr/local/lib64/pkgconfig:/usr/local/lib/pkgconfig:${PKG_CONFIG_PATH:-}"
g++ -std=c++17 -Wall -Wextra -I/workspace /tests/test_systemc.cpp \
  $(pkg-config --cflags --libs systemc) -pthread -o /tmp/test_systemc
/tmp/test_systemc
