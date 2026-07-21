#include "stream_accumulator.h"

#include <cassert>
#include <systemc>

int sc_main(int, char**) {
  sc_core::sc_fifo<int> input_fifo(12);
  sc_core::sc_fifo<int> output_fifo(4);
  stream_accumulator model("model");
  model.in(input_fifo);
  model.out(output_fifo);

  for (int value : {1, 2, 3, 4, 10, -3, 8, 5, 99, 100}) {
    input_fifo.write(value);
  }

  sc_core::sc_start();
  assert(output_fifo.num_available() == 2);
  assert(output_fifo.read() == 10);
  assert(output_fifo.read() == 20);
  assert(output_fifo.num_available() == 0);
  return 0;
}
