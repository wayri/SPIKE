// SPDX-License-Identifier: Apache-2.0
#pragma once

#include "spikes/peripheral_timing.hpp"
#include <array>
#include <cstdint>

namespace spikes {

// Experimental, deliberately small STM32-style polled-register facade.
// Device numbers are stable at this boundary: 0=TIM2, 1=SPI1, 2=I2C1.
class PeripheralRegisters {
public:
  static constexpr std::uint32_t timer_device = 0;
  static constexpr std::uint32_t spi_device = 1;
  static constexpr std::uint32_t i2c_device = 2;
  static constexpr std::uint32_t gpio_a_device = 3;
  static constexpr std::uint32_t gpio_i_device = 11;

  PeripheralRegisters(PeripheralTiming& timing,
                      std::uint64_t timer_input_hz = 10'000'000,
                      std::uint64_t spi_input_hz = 80'000'000,
                      std::uint64_t i2c_input_hz = 8'000'000);

  void write(std::uint32_t device, std::uint32_t offset,
             std::uint32_t value, std::uint32_t width = 4);
  [[nodiscard]] std::uint32_t read(std::uint32_t device,
                                   std::uint32_t offset,
                                   std::uint32_t width = 4);

  // Latches externally solved pad levels; outputs are never self-echoed.
  void gpio_inputs(std::uint32_t port_index, std::uint32_t mask,
                   std::uint32_t high);

  // Synchronizes completion flags from the timing service without advancing it.
  void refresh();

private:
  enum class I2cPending { none, start, address, transmit, receive, stop };

  void write_timer(std::uint32_t offset, std::uint32_t value,
                   std::uint32_t width);
  void write_spi(std::uint32_t offset, std::uint32_t value,
                 std::uint32_t width);
  void write_i2c(std::uint32_t offset, std::uint32_t value,
                 std::uint32_t width);
  std::uint32_t read_timer(std::uint32_t offset, std::uint32_t width);
  std::uint32_t read_spi(std::uint32_t offset, std::uint32_t width);
  std::uint32_t read_i2c(std::uint32_t offset, std::uint32_t width);
  void write_gpio(std::uint32_t port, std::uint32_t offset,
                  std::uint32_t value, std::uint32_t width);
  std::uint32_t read_gpio(std::uint32_t port, std::uint32_t offset,
                          std::uint32_t width);
  void configure_timer();
  void configure_spi();
  void configure_i2c();
  [[nodiscard]] std::uint32_t timer_count() const;

  PeripheralTiming& timing_;
  std::uint64_t timer_input_hz_;
  std::uint64_t spi_input_hz_;
  std::uint64_t i2c_input_hz_;

  std::uint32_t tim_cr1_{}, tim_sr_{}, tim_ccmr1_{}, tim_ccer_{};
  std::uint32_t tim_psc_{}, tim_arr_{0xffffffffu}, tim_ccr1_{};
  std::uint64_t tim_started_ns_{};
  std::uint64_t tim_seen_wraps_{};

  std::uint32_t spi_cr1_{};

  std::uint32_t i2c_cr1_{}, i2c_cr2_{}, i2c_ccr_{};
  I2cPending i2c_pending_{I2cPending::none};
  bool i2c_expect_address_{}, i2c_receiver_{}, i2c_address_read_{};
  bool i2c_addr_sr1_read_{};
  std::uint32_t i2c_sr1_{};

  struct GpioPort {
    std::uint32_t mode{}, output_type{}, speed{}, pull{}, input{}, output{};
    std::uint32_t alternate_low{}, alternate_high{};
  };
  std::array<GpioPort, 9> gpio_{};
};

} // namespace spikes
