#!/bin/sh
cat > /workspace/saturating_counter.h <<'CPP'
#pragma once

#include <algorithm>
#include <cstdint>

template <unsigned Bits>
class SaturatingCounter {
 public:
  static_assert(Bits >= 1 && Bits <= 16);
  static constexpr std::uint32_t minimum = 0;
  static constexpr std::uint32_t maximum = (std::uint32_t{1} << Bits) - 1;

  explicit SaturatingCounter(long long initial = 0) { set(initial); }

  std::uint32_t value() const { return value_; }
  bool is_min() const { return value_ == minimum; }
  bool is_max() const { return value_ == maximum; }

  SaturatingCounter& operator++() { return *this += 1; }
  SaturatingCounter operator++(int) {
    SaturatingCounter old(*this);
    ++*this;
    return old;
  }
  SaturatingCounter& operator--() { return *this -= 1; }
  SaturatingCounter operator--(int) {
    SaturatingCounter old(*this);
    --*this;
    return old;
  }
  SaturatingCounter& operator+=(long long delta) {
    set(static_cast<long long>(value_) + delta);
    return *this;
  }
  SaturatingCounter& operator-=(long long delta) {
    set(static_cast<long long>(value_) - delta);
    return *this;
  }

 private:
  void set(long long next) {
    value_ = static_cast<std::uint32_t>(
        std::clamp(next, 0LL, static_cast<long long>(maximum)));
  }

  std::uint32_t value_ = 0;
};
CPP
