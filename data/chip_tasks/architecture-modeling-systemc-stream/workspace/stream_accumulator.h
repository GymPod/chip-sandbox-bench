#pragma once

#include <systemc>

SC_MODULE(stream_accumulator) {
  sc_core::sc_fifo_in<int> in;
  sc_core::sc_fifo_out<int> out;

  SC_CTOR(stream_accumulator) {
    // Register the process here.
  }

  void run() {
    // Consume non-overlapping groups of four values and emit their sums.
  }
};
