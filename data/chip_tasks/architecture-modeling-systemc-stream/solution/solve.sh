#!/bin/sh
cat > /workspace/stream_accumulator.h <<'CPP'
#pragma once

#include <systemc>

SC_MODULE(stream_accumulator) {
  sc_core::sc_fifo_in<int> in;
  sc_core::sc_fifo_out<int> out;

  SC_CTOR(stream_accumulator) { SC_THREAD(run); }

  void run() {
    while (true) {
      int sum = 0;
      for (int index = 0; index < 4; ++index) {
        sum += in.read();
      }
      out.write(sum);
    }
  }
};
CPP
