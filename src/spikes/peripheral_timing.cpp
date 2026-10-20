// SPDX-License-Identifier: Apache-2.0
#include "spikes/peripheral_timing.hpp"
#include <stdexcept>

namespace spikes {
namespace {
void require(bool value, const char* message) {
  if (!value) throw std::invalid_argument(message);
}
}
std::uint64_t PeripheralTiming::add(std::uint64_t a, std::uint64_t b) {
  require(a <= maximum_time_ns && b <= maximum_time_ns - a,
          "peripheral virtual time exceeds admitted range");
  return a + b;
}
std::uint64_t PeripheralTiming::half_period(std::uint64_t hz) {
  require(hz > 0 && hz <= 500'000'000 && 500'000'000 % hz == 0,
          "clock half-period must be an exact positive integer nanosecond");
  return 500'000'000 / hz;
}
void PeripheralTiming::mutable_check() const {
  require(!pending_, "resolve the pending electrical event first");
}
void PeripheralTiming::require_resolved() const {
  mutable_check();
}
void PeripheralTiming::configure_timer(std::uint64_t hz, std::uint32_t psc,
                                       std::uint32_t arr, std::uint32_t ccr) {
  mutable_check();
  require(!timer_enabled_, "stop timer before changing its configuration");
  require(hz > 0 && hz <= 1'000'000'000 && psc <= 65535,
          "unsupported timer input frequency or prescaler");
  const auto numerator = 1'000'000'000ull * (std::uint64_t(psc) + 1);
  require(numerator % hz == 0, "timer tick must be exact integer nanoseconds");
  const auto tick = numerator / hz;
  const auto counts = std::uint64_t(arr) + 1;
  require(tick <= maximum_time_ns / counts, "timer period overflows time range");
  require(ccr <= counts, "compare outside admitted PWM range");
  timer_tick_ = tick;
  timer_period_ = tick * counts;
  timer_high_ = tick * ccr;
}
void PeripheralTiming::enable_timer(bool enabled) {
  mutable_check();
  require(!enabled || timer_tick_, "configure timer before enabling");
  if (enabled && !timer_enabled_) {
    add(now_, timer_period_);
    timer_next_ = now_;
    timer_initial_ = true;
  }
  timer_enabled_ = enabled;
}
void PeripheralTiming::configure_spi(std::uint64_t hz) {
  mutable_check();
  require(!spi_busy() && !spi_ready_, "SPI must be idle with received data consumed");
  spi_half_ = half_period(hz);
}
void PeripheralTiming::start_spi(std::uint8_t transmit) {
  mutable_check();
  require(spi_half_ && !spi_busy() && !spi_ready_,
          "SPI unconfigured, busy, or unread received data");
  add(now_, spi_half_ * 16);
  spi_tx_ = transmit;
  spi_rx_ = 0;
  spi_phase_ = 0;
  spi_next_ = now_;
}
std::uint8_t PeripheralTiming::read_spi() {
  mutable_check();
  require(spi_ready_, "SPI receive data not ready");
  spi_ready_ = false;
  return spi_rx_;
}
void PeripheralTiming::configure_i2c(std::uint64_t hz, std::uint64_t timeout) {
  mutable_check();
  require(!i2c_busy() && !i2c_active_, "I2C configuration requires idle bus");
  require(hz <= 100'000 && timeout > 0 && timeout <= 1'000'000,
          "only bounded standard-mode I2C timing is admitted");
  const auto half = half_period(hz);
  i2c_half_ = half;
  i2c_timeout_ = timeout;
}
void PeripheralTiming::i2c_command_check(bool active) const {
  mutable_check();
  require(i2c_half_ && !i2c_busy(), "I2C unconfigured or command in progress");
  require(!active || i2c_active_, "I2C requires a completed START");
  // One operation has at most nine bit periods, plus start/stop overhead.
  add(now_, i2c_half_ * 20 + 20);
}
void PeripheralTiming::i2c_start() {
  i2c_command_check(false);
  require(!i2c_ready_, "consume I2C receive data before START");
  i2c_op_ = Operation::start;
  i2c_stage_ = Stage::setup;
  i2c_next_ = now_;
}
void PeripheralTiming::i2c_write(std::uint8_t transmit) {
  i2c_command_check(true);
  require(!i2c_ready_, "consume I2C receive data before write");
  i2c_tx_ = transmit;
  i2c_bit_ = 0;
  i2c_ack_ = false;
  i2c_op_ = Operation::write;
  i2c_stage_ = Stage::setup;
  i2c_next_ = now_;
}
void PeripheralTiming::i2c_read(bool acknowledge) {
  i2c_command_check(true);
  require(!i2c_ready_, "consume I2C receive data before another read");
  i2c_rx_ = 0;
  i2c_bit_ = 0;
  i2c_send_ack_ = acknowledge;
  i2c_op_ = Operation::read;
  i2c_stage_ = Stage::setup;
  i2c_next_ = now_;
}
void PeripheralTiming::i2c_stop() {
  i2c_command_check(true);
  i2c_op_ = Operation::stop;
  i2c_stage_ = Stage::setup;
  i2c_next_ = now_;
}
std::uint8_t PeripheralTiming::read_i2c() {
  mutable_check();
  require(i2c_ready_, "I2C receive data not ready");
  i2c_ready_ = false;
  return i2c_rx_;
}
PeripheralEvent PeripheralTiming::timer_event() const {
  const bool high = timer_initial_ ? timer_high_ > 0 : !timer_output_;
  return {timer_next_, timer_ch1, high ? timer_ch1 : 0u, 0, 0};
}
PeripheralEvent PeripheralTiming::spi_event() const {
  if (spi_phase_ == 0)
    return {spi_next_, spi_sck | spi_mosi, (spi_tx_ & 128) ? spi_mosi : 0u, 0, 0};
  if (spi_phase_ % 2)
    return {spi_next_, spi_sck, spi_sck, 0, spi_miso};
  const auto bit = unsigned(spi_phase_ / 2);
  if (bit == 8) return {spi_next_, spi_sck, 0, 0, 0};
  return {spi_next_, spi_sck | spi_mosi,
          (spi_tx_ & (128u >> bit)) ? spi_mosi : 0u, 0, 0};
}
PeripheralEvent PeripheralTiming::i2c_event() const {
  PeripheralEvent e{i2c_next_, 0, 0, 0, 0};
  switch (i2c_stage_) {
    case Stage::setup: {
      e.drive_mask = i2c_scl | i2c_sda;
      if (i2c_op_ == Operation::start)
        e.release_mask = i2c_sda | (i2c_active_ ? 0u : i2c_scl);
      else if (i2c_op_ == Operation::write)
        e.release_mask = (i2c_bit_ == 8 || (i2c_tx_ & (128u >> i2c_bit_)))
                         ? i2c_sda : 0u;
      else if (i2c_op_ == Operation::read)
        e.release_mask = (i2c_bit_ < 8 || !i2c_send_ack_) ? i2c_sda : 0u;
      break;
    }
    case Stage::raise: e.drive_mask = e.release_mask = i2c_scl; break;
    case Stage::wait_high:
      e.sample_mask = i2c_scl | (i2c_op_ == Operation::start ? i2c_sda : 0u);
      break;
    case Stage::sample: e.sample_mask = i2c_scl | i2c_sda; break;
    case Stage::fall: e.drive_mask = i2c_scl; break;
    case Stage::start_edge: e.drive_mask = i2c_sda; break;
    case Stage::start_hold: e.drive_mask = i2c_scl; break;
    case Stage::stop_edge: e.drive_mask = e.release_mask = i2c_sda; break;
    case Stage::stop_hold: e.sample_mask = i2c_scl | i2c_sda; break;
    case Stage::idle: throw std::logic_error("idle I2C has no event");
  }
  return e;
}
std::optional<PeripheralEvent> PeripheralTiming::next_event(std::uint64_t deadline) {
  mutable_check();
  require(deadline >= now_ && deadline <= maximum_time_ns, "invalid peripheral deadline");
  std::optional<PeripheralEvent> next;
  auto candidate = [&](PeripheralEvent e, Owner owner) {
    if (e.time_ns <= deadline && (!next || e.time_ns < next->time_ns)) {
      next = e;
      owner_ = owner;
    }
  };
  if (timer_enabled_ && (timer_initial_ || (timer_high_ && timer_high_ < timer_period_)))
    candidate(timer_event(), Owner::timer);
  if (spi_busy()) candidate(spi_event(), Owner::spi);
  if (i2c_busy()) candidate(i2c_event(), Owner::i2c);
  now_ = next ? next->time_ns : deadline;
  pending_ = next;
  return next;
}
void PeripheralTiming::resolve_timer() {
  timer_output_ = bool(pending_->high_mask & timer_ch1);
  timer_initial_ = false;
  if (timer_high_ && timer_high_ < timer_period_)
    timer_next_ = add(now_, timer_output_ ? timer_high_ : timer_period_ - timer_high_);
}
void PeripheralTiming::resolve_spi(std::uint32_t high) {
  if (spi_phase_ % 2 == 1)
    spi_rx_ = std::uint8_t((spi_rx_ << 1) | ((high & spi_miso) ? 1 : 0));
  if (spi_phase_ == 16) {
    spi_phase_ = -1;
    spi_ready_ = true;
  } else {
    ++spi_phase_;
    spi_next_ = add(now_, spi_half_);
  }
}
void PeripheralTiming::resolve_i2c(std::uint32_t high) {
  switch (i2c_stage_) {
    case Stage::setup:
      if (i2c_op_ == Operation::start && !i2c_active_) {
        i2c_stage_ = Stage::wait_high;
        i2c_wait_since_ = now_;
        i2c_next_ = add(now_, 1);
      } else {
        i2c_stage_ = Stage::raise;
        i2c_next_ = add(now_, i2c_half_);
      }
      break;
    case Stage::raise:
      i2c_stage_ = Stage::wait_high;
      i2c_wait_since_ = now_;
      i2c_next_ = add(now_, 1);
      break;
    case Stage::wait_high:
      if (!(high & i2c_scl)) {
        require(now_ - i2c_wait_since_ < i2c_timeout_, "I2C clock stretch timeout");
        i2c_next_ = add(now_, 1);
        break;
      }
      if (i2c_op_ == Operation::start) {
        require(high & i2c_sda, "I2C bus busy: SDA low before START");
        i2c_stage_ = Stage::start_edge;
      } else if (i2c_op_ == Operation::stop) {
        i2c_stage_ = Stage::stop_edge;
      } else i2c_stage_ = Stage::sample;
      i2c_next_ = add(now_, i2c_half_);
      break;
    case Stage::sample:
      require(high & i2c_scl, "I2C SCL fell during high phase; unsupported bus contention");
      if (i2c_op_ == Operation::read && i2c_bit_ < 8)
        i2c_rx_ = std::uint8_t((i2c_rx_ << 1) | ((high & i2c_sda) ? 1 : 0));
      if (i2c_op_ == Operation::write) {
        if (i2c_bit_ == 8) i2c_ack_ = !(high & i2c_sda);
        else require(bool(high & i2c_sda) == bool(i2c_tx_ & (128u >> i2c_bit_)),
                     "I2C transmitted data differs from receiver: bus contention");
      }
      i2c_stage_ = Stage::fall;
      break;
    case Stage::fall:
      if (++i2c_bit_ == 9) {
        i2c_ready_ = i2c_op_ == Operation::read;
        i2c_stage_ = Stage::idle;
      } else i2c_stage_ = Stage::setup;
      break;
    case Stage::start_edge:
      i2c_stage_ = Stage::start_hold;
      i2c_next_ = add(now_, i2c_half_);
      break;
    case Stage::start_hold:
      i2c_active_ = true;
      i2c_stage_ = Stage::idle;
      break;
    case Stage::stop_edge:
      i2c_stage_ = Stage::stop_hold;
      i2c_next_ = add(now_, i2c_half_);
      break;
    case Stage::stop_hold:
      require((high & (i2c_scl | i2c_sda)) == (i2c_scl | i2c_sda),
              "I2C STOP did not release the electrical bus");
      i2c_active_ = false;
      i2c_stage_ = Stage::idle;
      break;
    case Stage::idle: throw std::logic_error("no I2C operation to resolve");
  }
}
void PeripheralTiming::resolve_event(std::uint32_t high) {
  require(pending_.has_value(), "no pending peripheral event");
  require((high & ~pending_->sample_mask) == 0, "unexpected sampled signal bits");
  // Validation failures leave the same causal barrier pending, never partial state.
  auto updated = *this;
  switch (owner_) {
    case Owner::timer: updated.resolve_timer(); break;
    case Owner::spi: updated.resolve_spi(high); break;
    case Owner::i2c: updated.resolve_i2c(high); break;
  }
  updated.pending_.reset();
  *this = updated;
}
}
