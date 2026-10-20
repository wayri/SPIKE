// SPDX-License-Identifier: Apache-2.0
#include "spikes/peripheral_registers.hpp"

#include <array>
#include <cstdint>
#include <iostream>
#include <stdexcept>
#include <string>

using namespace spikes;
namespace {
void check(bool condition, const char* message) {
  if (!condition) throw std::runtime_error(message);
}

unsigned rejection_case = 0;
template<class F> void rejects(F operation) {
  ++rejection_case;
  bool rejected = false;
  try { operation(); } catch (const std::invalid_argument&) { rejected = true; }
  if (!rejected)
    throw std::runtime_error("invalid register operation was not rejected, case " +
                             std::to_string(rejection_case));
}

struct I2cWires {
  std::uint32_t released = i2c_scl | i2c_sda;

  void run(PeripheralTiming& timing, int receive = -1, bool acknowledge = true) {
    unsigned samples = 0;
    unsigned budget = 1000;
    while (timing.i2c_busy()) {
      check(budget-- != 0, "I2C event budget");
      const auto event = timing.next_event(1'000'000);
      check(event.has_value(), "I2C command lost its next event");
      released = (released & ~event->drive_mask) | event->release_mask;
      auto high = released & event->sample_mask;
      if (event->sample_mask == (i2c_scl | i2c_sda)) {
        if (receive >= 0 && samples < 8)
          high = i2c_scl | ((receive & (128 >> samples)) ? i2c_sda : 0u);
        else if (receive < 0 && samples == 8)
          high = i2c_scl | (acknowledge ? 0u : i2c_sda);
        ++samples;
      }
      timing.resolve_event(high);
    }
  }
};

void reset_and_rejection_contract() {
  PeripheralTiming timing;
  PeripheralRegisters regs(timing);
  check(regs.read(0, 0x00) == 0 && regs.read(0, 0x0c) == 0 &&
            regs.read(0, 0x10) == 0 && regs.read(0, 0x18) == 0 &&
            regs.read(0, 0x20) == 0 && regs.read(0, 0x24) == 0 &&
            regs.read(0, 0x28) == 0 && regs.read(0, 0x2c) == 0xffffffffu &&
            regs.read(0, 0x34) == 0,
        "TIM2 supported reset values");
  check(regs.read(1, 0x00) == 0 && regs.read(1, 0x04) == 0 &&
            regs.read(1, 0x08) == 2,
        "SPI1 supported reset values and TXE");
  check(regs.read(2, 0x00) == 0 && regs.read(2, 0x04) == 0 &&
            regs.read(2, 0x14) == 0 && regs.read(2, 0x18) == 0 &&
            regs.read(2, 0x1c) == 0,
        "I2C1 supported reset values");

  rejects([&] { (void)regs.read(12, 0); });
  rejects([&] { (void)regs.read(0, 0x04); });
  rejects([&] { (void)regs.read(0, 0, 2); });
  rejects([&] { regs.write(0, 0x0c, 1); });
  rejects([&] { regs.write(0, 0x00, 2); });
  rejects([&] { regs.write(0, 0x18, 0x68); });
  rejects([&] { regs.write(1, 0x04, 1); });
  rejects([&] { regs.write(2, 0x04, 1u << 8); });
  rejects([&] { (void)regs.read(1, 0x0c, 1); });
  rejects([&] { (void)regs.read(2, 0x10, 1); });
}

void pending_event_barrier_contract() {
  PeripheralTiming timing;
  PeripheralRegisters regs(timing);
  timing.configure_spi(20'000'000);
  timing.start_spi(0xa5);
  const auto event = timing.next_event(0);
  check(event.has_value(), "SPI setup creates an electrical causal barrier");
  rejects([&] { regs.refresh(); });
  rejects([&] { (void)regs.read(0, 0x2c); });
  rejects([&] { regs.write(0, 0x2c, 3); });
  timing.resolve_event(0);
  check(regs.read(0, 0x2c) == 0xffffffffu,
        "rejected MMIO write leaves register state unchanged after resolution");
}

void gpio_register_contract() {
  PeripheralTiming timing;
  PeripheralRegisters regs(timing);
  check(regs.read(3, 0x00) == 0xa8000000u &&
            regs.read(3, 0x08) == 0x0c000000u &&
            regs.read(3, 0x0c) == 0x64000000u,
        "GPIOA reset mode, speed, and pull snapshot");
  check(regs.read(4, 0x00) == 0x00000280u &&
            regs.read(4, 0x08) == 0x000000c0u &&
            regs.read(4, 0x0c) == 0x00000100u,
        "GPIOB reset mode, speed, and pull snapshot");
  for (std::uint32_t device = 5; device <= 11; ++device) {
    check(regs.read(device, 0x00) == 0 && regs.read(device, 0x04) == 0 &&
              regs.read(device, 0x08) == 0 && regs.read(device, 0x0c) == 0 &&
              regs.read(device, 0x10) == 0 && regs.read(device, 0x14) == 0 &&
              regs.read(device, 0x20) == 0 && regs.read(device, 0x24) == 0,
          "GPIOC-I selected reset registers are zero");
  }

  regs.write(3, 0x00, 0x00000001u);
  regs.write(3, 0x04, 0x00000001u);
  regs.write(3, 0x08, 0x00000002u);
  regs.write(3, 0x0c, 0x00000008u);
  regs.write(3, 0x20, 0x76543210u);
  regs.write(3, 0x24, 0xfedcba98u);
  check(regs.read(3, 0x00) == 1 && regs.read(3, 0x04) == 1 &&
            regs.read(3, 0x08) == 2 && regs.read(3, 0x0c) == 8 &&
            regs.read(3, 0x20) == 0x76543210u &&
            regs.read(3, 0x24) == 0xfedcba98u,
        "GPIO configuration words are owned by the facade");

  regs.write(3, 0x14, 1);
  check(regs.read(3, 0x14) == 1 && regs.read(3, 0x10) == 0,
        "GPIO output latch does not invent physical input self-echo");
  regs.gpio_inputs(0, 3, 2);
  check(regs.read(3, 0x10) == 2 && regs.read(3, 0x14) == 1,
        "GPIO IDR uses externally supplied pad levels only");
  regs.write(3, 0x18, 4);
  check(regs.read(3, 0x14) == 5, "GPIO BSRR lower half sets ODR bits");
  regs.write(3, 0x18, 1u << 16);
  check(regs.read(3, 0x14) == 4 && regs.read(3, 0x18) == 0,
        "GPIO BSRR upper half resets ODR bits and reads zero");

  rejects([&] { regs.write(3, 0x04, 1u << 16); });
  rejects([&] { regs.write(3, 0x14, 1u << 16); });
  rejects([&] { regs.write(3, 0x18, (1u << 2) | (1u << 18)); });
  check(regs.read(3, 0x14) == 4, "invalid GPIO writes are transactional");
  rejects([&] { regs.write(3, 0x10, 0); });
  rejects([&] { regs.write(3, 0x00, 0, 2); });
  rejects([&] { regs.write(3, 0x1c, 0); });
  rejects([&] { regs.gpio_inputs(9, 1, 1); });
  rejects([&] { regs.gpio_inputs(0, 1u << 16, 0); });
  rejects([&] { regs.gpio_inputs(0, 1, 2); });

  timing.configure_spi(20'000'000);
  timing.start_spi(0);
  const auto event = timing.next_event(timing.time_ns());
  check(event.has_value(), "GPIO barrier test creates an electrical event");
  rejects([&] { regs.gpio_inputs(0, 1, 1); });
  timing.resolve_event(0);
  check(regs.read(3, 0x10) == 2,
        "rejected GPIO input update preserves the physical latch");
}

void timer_register_contract() {
  PeripheralTiming timing;
  PeripheralRegisters regs(timing);
  regs.write(0, 0x18, 0x60);
  regs.write(0, 0x20, 1);
  regs.write(0, 0x28, 0);
  regs.write(0, 0x2c, 3);
  regs.write(0, 0x34, 2);
  regs.write(0, 0x00, 1);
  auto event = timing.next_event(0);
  check(event && event->high_mask == timer_ch1, "TIM2 PWM starts high at CNT=0");
  timing.resolve_event(0);
  check(!timing.next_event(150), "TIM2 has no edge before CCR1");
  check(regs.read(0, 0x24) == 1, "TIM2 CNT follows its owned 100 ns clock");
  rejects([&] { regs.write(0, 0x2c, 4); });
  event = timing.next_event(400);
  check(event && event->time_ns == 200 && !event->high_mask,
        "TIM2 CCR1 edge derives from two ticks");
  timing.resolve_event(0);
  event = timing.next_event(400);
  check(event && event->time_ns == 400 && event->high_mask,
        "TIM2 ARR=3 period is four ticks");
  timing.resolve_event(0);
  check(regs.read(0, 0x24) == 0 && regs.read(0, 0x10) == 1,
        "TIM2 wrap sets bounded UIF and resets CNT");
  regs.write(0, 0x10, 0);
  check(regs.read(0, 0x10) == 0, "TIM2 UIF write-zero clearing");
  regs.write(0, 0x00, 0);
  regs.write(0, 0x2c, 7);
  check(regs.read(0, 0x2c) == 7, "TIM2 configuration changes while stopped");
  rejects([&] { regs.write(0, 0x24, 0); });
}

void spi_register_contract() {
  constexpr std::uint32_t cr1_enabled_br1 =
      (1u << 2) | (1u << 3) | (1u << 6) | (1u << 8) | (1u << 9);
  PeripheralTiming timing;
  PeripheralRegisters regs(timing);
  // 80 MHz / 2 at BR=0 has a noninteger 12.5 ns half period.
  rejects([&] { regs.write(1, 0x00, cr1_enabled_br1 & ~(1u << 3)); });
  check(regs.read(1, 0x00) == 0, "failed SPI1 enable is transactional");
  regs.write(1, 0x00, cr1_enabled_br1);
  regs.write(1, 0x0c, 0xa5, 1);
  check(regs.read(1, 0x08) == (1u << 7), "SPI1 DR write sets BSY and clears TXE");
  rejects([&] { regs.write(1, 0x0c, 0, 1); });
  const std::array<unsigned, 8> receive{0, 0, 1, 1, 1, 1, 0, 0};
  unsigned sample = 0;
  for (unsigned edge = 0; edge != 17; ++edge) {
    const auto event = timing.next_event(1000);
    check(event.has_value(), "SPI1 byte must retain all clock edges");
    const auto high = event->sample_mask ? (receive[sample++] ? spi_miso : 0u) : 0u;
    timing.resolve_event(high);
  }
  check(sample == 8 && regs.read(1, 0x08) == 3,
        "SPI1 completion sets RXNE and TXE and clears BSY");
  check(regs.read(1, 0x0c, 1) == 0x3c && regs.read(1, 0x08) == 2,
        "SPI1 DR returns physical MISO data and clears RXNE");
  regs.write(1, 0x00, cr1_enabled_br1 & ~(1u << 6));
  rejects([&] { regs.write(1, 0x00, (1u << 6) | (1u << 2)); });
}

void i2c_write_and_nack_contract() {
  constexpr std::uint32_t pe = 1u;
  constexpr std::uint32_t start = 1u << 8;
  constexpr std::uint32_t stop = 1u << 9;
  constexpr std::uint32_t sb = 1u;
  constexpr std::uint32_t addr = 1u << 1;
  constexpr std::uint32_t btf = 1u << 2;
  constexpr std::uint32_t txe = 1u << 7;
  constexpr std::uint32_t af = 1u << 10;
  PeripheralTiming timing;
  PeripheralRegisters regs(timing);
  I2cWires wires;
  regs.write(2, 0x04, 8);
  regs.write(2, 0x1c, 40);
  regs.write(2, 0x00, pe);
  regs.write(2, 0x00, pe | start);
  rejects([&] { regs.write(2, 0x00, pe | start); });
  wires.run(timing);
  check(regs.read(2, 0x14) == sb, "I2C1 START completion sets SB");
  regs.write(2, 0x10, 0x50, 1);
  wires.run(timing, -1, true);
  check(regs.read(2, 0x14) == addr, "physical ACK sets ADDR");
  check(regs.read(2, 0x18) == 7, "SR1 then SR2 reports master transmitter");
  check(regs.read(2, 0x14) == txe, "SR1/SR2 sequence clears ADDR and sets TXE");
  regs.write(2, 0x10, 0xa6, 1);
  wires.run(timing, -1, true);
  check(regs.read(2, 0x14) == (btf | txe),
        "acknowledged I2C1 byte sets BTF and TXE");
  regs.write(2, 0x10, 0x5a, 1);
  wires.run(timing, -1, false);
  check(regs.read(2, 0x14) == af, "physical NACK sets AF, never success flags");
  rejects([&] { regs.write(2, 0x10, 0, 1); });
  regs.write(2, 0x14, 0);
  check(regs.read(2, 0x14) == 0, "I2C1 AF can be cleared by writing zero");
  regs.write(2, 0x00, pe | stop);
  wires.run(timing);
  check(regs.read(2, 0x18) == 0, "I2C1 STOP clears active bus status");
  rejects([&] { regs.write(2, 0x04, 8); });
  regs.write(2, 0x00, 0);
  regs.write(2, 0x04, 8);
}

void i2c_single_byte_receive_contract() {
  constexpr std::uint32_t pe = 1u;
  constexpr std::uint32_t start = 1u << 8;
  constexpr std::uint32_t stop = 1u << 9;
  constexpr std::uint32_t ack = 1u << 10;
  constexpr std::uint32_t addr = 1u << 1;
  constexpr std::uint32_t rxne = 1u << 6;
  PeripheralTiming timing;
  PeripheralRegisters regs(timing);
  I2cWires wires;
  regs.write(2, 0x04, 8);
  regs.write(2, 0x1c, 40);
  regs.write(2, 0x00, pe);
  regs.write(2, 0x00, pe | start);
  wires.run(timing);
  (void)regs.read(2, 0x14);
  rejects([&] { regs.write(2, 0x00, pe | ack); regs.write(2, 0x10, 0x51, 1); });
  // The rejected address did not reach the timing engine; clear ACK and retry.
  regs.write(2, 0x00, pe);
  regs.write(2, 0x10, 0x51, 1);
  wires.run(timing, -1, true);
  check(regs.read(2, 0x14) == addr, "read address ACK sets ADDR");
  check(regs.read(2, 0x18) == 3, "SR2 reports master receiver and schedules one byte");
  wires.run(timing, 0xa6);
  check(regs.read(2, 0x14) == rxne, "physical SDA samples set RXNE");
  regs.write(2, 0x00, pe | stop);
  wires.run(timing);
  check(regs.read(2, 0x10, 1) == 0xa6 && regs.read(2, 0x14) == 0,
        "I2C1 DR returns physical byte and clears RXNE");
}
} // namespace

int main() {
  try {
    reset_and_rejection_contract();
    pending_event_barrier_contract();
    gpio_register_contract();
    timer_register_contract();
    spi_register_contract();
    i2c_write_and_nack_contract();
    i2c_single_byte_receive_contract();
    std::cout << "peripheral register tests passed\n";
  } catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
}
