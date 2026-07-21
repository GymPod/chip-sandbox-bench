#include "saturating_counter.h"

#include <cassert>
#include <cstdint>

int main() {
  SaturatingCounter<2> counter(1);
  assert(counter.value() == 1);
  assert(!counter.is_min() && !counter.is_max());

  auto before_increment = counter++;
  assert(before_increment.value() == 1);
  assert(counter.value() == 2);
  assert((++counter).value() == 3);
  assert(counter.is_max());
  ++counter;
  counter += 1000000;
  assert(counter.value() == 3);

  auto before_decrement = counter--;
  assert(before_decrement.value() == 3);
  assert(counter.value() == 2);
  counter -= 1000000;
  assert(counter.value() == 0);
  assert(counter.is_min());
  --counter;
  counter += -12;
  assert(counter.value() == 0);
  counter -= -2;
  assert(counter.value() == 2);

  SaturatingCounter<1> bit(-9);
  assert(bit.value() == 0);
  bit += 1;
  bit += 1;
  assert(bit.value() == 1);

  SaturatingCounter<16> wide(999999);
  assert(wide.value() == 65535);
  wide -= 65534;
  assert(wide.value() == 1);
  return 0;
}
