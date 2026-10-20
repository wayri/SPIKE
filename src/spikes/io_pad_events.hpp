// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "spikes/io_pad.hpp"
#include <map>
#include <unordered_map>

namespace spikes {
/** Bounded, stable timestamp scheduling; never derives time from host clocks. */
class IoPadEventQueue {
public:
  using Bindings = std::unordered_map<std::string,IoPadBinding>;
  static constexpr std::size_t capacity = 65536;
  static constexpr std::uint64_t maximum_time_ns = (std::uint64_t{1}<<48);
  void schedule(const TransientSession &session,const Bindings &pads,
                std::string prefix,std::uint64_t time_ns,IoPadState state);
  bool advance(TransientSession &session,Bindings &pads,double step_s);
  [[nodiscard]] std::size_t size() const noexcept { return events_.size(); }
  [[nodiscard]] std::uint64_t next_time_ns() const noexcept {
    return events_.empty()?0:events_.begin()->first.first;
  }
private:
  struct Event { std::string prefix; IoPadState state; };
  std::map<std::pair<std::uint64_t,std::uint64_t>,Event> events_;
  std::uint64_t sequence_{0};
};
}
