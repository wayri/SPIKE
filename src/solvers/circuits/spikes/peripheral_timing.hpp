// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <cstdint>
#include <optional>

namespace spikes {

// Explicit signal-to-pad mapping belongs to the integrating application.
enum PeripheralSignal : std::uint32_t {
  timer_ch1 = 1u, spi_sck = 2u, spi_mosi = 4u, spi_miso = 8u,
  i2c_scl = 16u, i2c_sda = 32u
};
struct PeripheralEvent {
  std::uint64_t time_ns{};
  std::uint32_t drive_mask{};   // Only these output signals change.
  std::uint32_t high_mask{};    // Push-pull high; I2C never drives high.
  std::uint32_t release_mask{}; // High impedance, requiring external pull-ups.
  std::uint32_t sample_mask{};  // Receiver values required before proceeding.
};

// Experimental exact integer-ns behavioral peripheral service, not a CPU.
// Every event is a causal barrier: advance the plant to the event, sample its
// accepted pre-edge (left-limit) receivers, apply outputs, then resolve_event.
// Positive-delay input probes observe the accepted electrical response to old
// drive changes. Even output-only events require acknowledgement.
class PeripheralTiming {
public:
  static constexpr std::uint64_t maximum_time_ns = std::uint64_t{1} << 48;
  void configure_timer(std::uint64_t input_hz, std::uint32_t psc,
                       std::uint32_t arr, std::uint32_t ccr);
  void enable_timer(bool enabled);
  void configure_spi(std::uint64_t clock_hz);
  void start_spi(std::uint8_t transmit);
  [[nodiscard]] bool spi_busy() const noexcept { return spi_phase_ >= 0; }
  [[nodiscard]] bool spi_ready() const noexcept { return spi_ready_; }
  std::uint8_t read_spi();
  void configure_i2c(std::uint64_t clock_hz,
                     std::uint64_t stretch_timeout_ns = 1'000'000);
  void i2c_start();
  void i2c_write(std::uint8_t transmit);
  void i2c_read(bool acknowledge);
  void i2c_stop();
  // Register and host adapters use this to fail closed at a causal barrier.
  void require_resolved() const;
  [[nodiscard]] bool i2c_busy() const noexcept { return i2c_stage_ != Stage::idle; }
  [[nodiscard]] bool i2c_active() const noexcept { return i2c_active_; }
  [[nodiscard]] bool i2c_ready() const noexcept { return i2c_ready_; }
  [[nodiscard]] bool i2c_acknowledged() const noexcept { return i2c_ack_; }
  std::uint8_t read_i2c();
  // Advances to at most one event, or to deadline if no event precedes it.
  std::optional<PeripheralEvent> next_event(std::uint64_t deadline_ns);
  void resolve_event(std::uint32_t sampled_high_mask);
  [[nodiscard]] std::uint64_t time_ns() const noexcept { return now_; }
private:
  enum class Owner { timer, spi, i2c };
  enum class Operation { start, write, read, stop };
  enum class Stage { idle, setup, raise, wait_high, sample, fall, start_edge,
                     start_hold, stop_edge, stop_hold };
  void mutable_check() const;
  void i2c_command_check(bool active) const;
  PeripheralEvent timer_event() const;
  PeripheralEvent spi_event() const;
  PeripheralEvent i2c_event() const;
  void resolve_timer();
  void resolve_spi(std::uint32_t high);
  void resolve_i2c(std::uint32_t high);
  static std::uint64_t add(std::uint64_t a, std::uint64_t b);
  static std::uint64_t half_period(std::uint64_t hz);
  std::uint64_t now_{};
  std::optional<PeripheralEvent> pending_;
  Owner owner_{Owner::timer};
  std::uint64_t timer_tick_{}, timer_period_{}, timer_high_{}, timer_next_{};
  bool timer_enabled_{}, timer_initial_{}, timer_output_{};
  std::uint64_t spi_half_{}, spi_next_{};
  int spi_phase_{-1};
  std::uint8_t spi_tx_{}, spi_rx_{};
  bool spi_ready_{};
  std::uint64_t i2c_half_{}, i2c_next_{}, i2c_timeout_{}, i2c_wait_since_{};
  Operation i2c_op_{Operation::start};
  Stage i2c_stage_{Stage::idle};
  unsigned i2c_bit_{};
  std::uint8_t i2c_tx_{}, i2c_rx_{};
  bool i2c_active_{}, i2c_ready_{}, i2c_ack_{}, i2c_send_ack_{};
};
}
