#pragma once

#include <cstdint>

template <unsigned Bits>
class SaturatingCounter {
 public:
  static_assert(Bits >= 1 && Bits <= 16);
  static constexpr std::uint32_t minimum = 0;
  static constexpr std::uint32_t maximum = (std::uint32_t{1} << Bits) - 1;

  explicit SaturatingCounter(long long initial = 0);

  std::uint32_t value() const;
  bool is_min() const;
  bool is_max() const;

  SaturatingCounter& operator++();
  SaturatingCounter operator++(int);
  SaturatingCounter& operator--();
  SaturatingCounter operator--(int);
  SaturatingCounter& operator+=(long long delta);
  SaturatingCounter& operator-=(long long delta);

 private:
  std::uint32_t value_ = 0;
};
