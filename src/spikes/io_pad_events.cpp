// SPDX-License-Identifier: Apache-2.0
#include "spikes/io_pad_events.hpp"
#include "spikes/transient_session.hpp"
#include <algorithm>
#include <cmath>
#include <limits>
#include <stdexcept>

namespace spikes {
namespace {
double tolerance(double time) {
  return std::max(1e-18,8*std::numeric_limits<double>::epsilon()*std::abs(time));
}
void check_state(const IoPadState &s) {
  const auto mode=static_cast<unsigned>(s.mode);
  const auto output=static_cast<unsigned>(s.output);
  if (mode>3 || output>2 || static_cast<unsigned>(s.drive_level)>1 ||
      static_cast<unsigned>(s.pull)>2 ||
      (mode==0 && output!=2) || (mode==1 && output==2) ||
      (mode==2 && output==1) || (mode==3 && output==0))
    throw std::invalid_argument("invalid scheduled GPIO pad state");
}
}
void IoPadEventQueue::schedule(const TransientSession &session,const Bindings &pads,
                             std::string prefix,std::uint64_t ns,IoPadState state) {
  check_state(state);
  if (!pads.contains(prefix)) throw std::out_of_range("scheduled GPIO pad not in this session");
  if (ns>maximum_time_ns) throw std::invalid_argument("GPIO timestamp exceeds 2^48 ns horizon");
  if (ns==0 && !session.has_point() && session.initializes_from_operating_point())
    throw std::invalid_argument("time-zero GPIO mode change requires explicit storage initialization; OP startup is not yet accepted");
  const double time=static_cast<double>(ns)/1e9;
  if (time < session.time_s()-tolerance(session.time_s()))
    throw std::invalid_argument("cannot schedule a GPIO edge in the past");
  if (events_.size()>=capacity || sequence_==std::numeric_limits<std::uint64_t>::max())
    throw std::invalid_argument("GPIO event queue capacity exhausted");
  events_.emplace(std::make_pair(ns,sequence_),Event{std::move(prefix),state});
  ++sequence_;
}
bool IoPadEventQueue::advance(TransientSession &session,Bindings &pads,double step_s) {
  if (!std::isfinite(step_s) || step_s<1e-18)
    throw std::invalid_argument("GPIO scheduled step must be finite and positive");
  const double end=session.time_s()+step_s;
  if (!std::isfinite(end) || end<=session.time_s())
    throw std::invalid_argument("GPIO scheduled step cannot advance the clock");
  if (events_.empty() || static_cast<double>(events_.begin()->first.first)/1e9>end)
    return session.step(step_s);
  const auto checkpoint=session.checkpoint();
  auto saved_pads=pads;
  auto saved_events=events_;
  try {
  while (!events_.empty()) {
    auto first=events_.begin();
    const double time=static_cast<double>(first->first.first)/1e9;
    if (time>end) break; // Never consume a future edge or overshoot caller endpoint.
    const double remaining=time-session.time_s();
    if (remaining < -tolerance(session.time_s()))
      throw std::invalid_argument("GPIO event is stale; coupled clocks must be restored together");
    if (remaining>=1e-18 && !session.step(remaining))
      throw std::runtime_error("GPIO edge segment failed: "+std::string(session.message()));
    auto found=pads.find(first->second.prefix);
    if (found==pads.end()) throw std::out_of_range("scheduled GPIO binding missing");
    update_io_pad(session,found->second,first->second.state);
    events_.erase(first);
  }
  const double remaining=end-session.time_s();
  if (remaining>=1e-18 && !session.step(remaining))
    throw std::runtime_error("GPIO edge final segment failed: "+std::string(session.message()));
  return true;
  } catch (...) {
    session.restore(checkpoint);
    pads.swap(saved_pads);events_.swap(saved_events);
    throw;
  }
}
}
