// SPDX-License-Identifier: Apache-2.0
#include "spikes/peripheral_timing.hpp"
#include <array>
#include <iostream>
#include <stdexcept>
#include <vector>

using namespace spikes;
namespace {
void check(bool value, const char* message) {
  if (!value) throw std::runtime_error(message);
}
template<class F> void rejects(F operation) {
  bool rejected = false;
  try { operation(); } catch (const std::invalid_argument&) { rejected = true; }
  check(rejected, "invalid operation was not rejected");
}
void timer_oracle() {
  PeripheralTiming engine;
  engine.configure_timer(10'000'000, 0, 3, 2);
  engine.enable_timer(true);
  // Independently enumerate CNT 0,1,2,3,0,1,2,3,0 at 100 ns/tick.
  const std::array<std::uint64_t, 5> times{0, 200, 400, 600, 800};
  for (unsigned i = 0; i < times.size(); ++i) {
    auto event = engine.next_event(800);
    check(event && event->time_ns == times[i], "ARR=3 must give 400 ns, not 300 ns");
    check(bool(event->high_mask) == (i % 2 == 0), "PWM compare state");
    rejects([&] { engine.next_event(800); });
    rejects([&] { engine.configure_spi(20'000'000); });
    rejects([&] { engine.resolve_event(spi_miso); });
    engine.resolve_event(0);
  }
  check(!engine.next_event(999), "no premature compare edge");
  engine.enable_timer(false);
  engine.configure_timer(10'000'000, 1, 0, 1);
  engine.enable_timer(true);
  auto full = engine.next_event(1000);
  check(full && full->high_mask == timer_ch1, "ARR=0 full duty");
  engine.resolve_event(0);
  check(!engine.next_event(5000), "full-duty PWM has no spurious edge");
  engine.enable_timer(false);
  engine.configure_timer(10'000'000, 0, 3, 0);
  engine.enable_timer(true);
  auto zero = engine.next_event(5000);
  check(zero && !zero->high_mask, "zero-duty PWM");
  engine.resolve_event(0);
  check(!engine.next_event(6000), "zero-duty PWM has no spurious edge");
}
void spi_oracle() {
  PeripheralTiming engine;
  engine.next_event(5); // Not aligned to a hypothetical 10 ns CPU instruction.
  engine.configure_spi(100'000'000); // 5 ns half-period.
  engine.start_spi(0xa6);
  const std::array<unsigned, 8> tx{1,0,1,0,0,1,1,0};
  const std::array<unsigned, 8> rx{0,1,0,1,1,0,0,1};
  unsigned bit = 0;
  unsigned setup = 0;
  for (unsigned event_index = 0; event_index != 17; ++event_index) {
    auto event = engine.next_event(100);
    check(event && event->time_ns == 5 + event_index * 5, "sub-instruction SPI edge");
    if (event->drive_mask & spi_mosi) {
      check(bool(event->high_mask & spi_mosi) == bool(tx[setup++]), "MSB-first MOSI");
    }
    const auto input = event->sample_mask ? (rx[bit++] ? spi_miso : 0u) : 0u;
    engine.resolve_event(input);
  }
  check(bit == 8 && setup == 8 && !engine.spi_busy() && engine.spi_ready(), "SPI completion");
  rejects([&] { engine.start_spi(0); });
  check(engine.read_spi() == 0x59, "SPI receiver-derived byte");
  rejects([&] { engine.read_spi(); });
  check(!engine.next_event(100), "SPI stops after eight clocks");
}

// Independent wire harness, not a protocol model: pull-up on released lines,
// optional one-bit external pull-down for ACK/data and finite SCL-low hold.
struct Wires {
  std::uint32_t released = i2c_scl | i2c_sda;
  unsigned data_samples = 0;
  unsigned wait_samples = 0;
  std::vector<std::uint64_t> sampled_at;
  void run(PeripheralTiming& engine, int receive = -1, bool ack = true,
           unsigned stretch_probes = 0) {
    unsigned budget = 1000;
    while (engine.i2c_busy()) {
      check(budget-- > 0, "I2C test event budget");
      auto event = engine.next_event(1'000'000);
      check(bool(event), "I2C operation must schedule event");
      check(event->high_mask == 0, "I2C must never drive high");
      released = (released & ~event->drive_mask) | event->release_mask;
      auto high = released & event->sample_mask;
      if (event->sample_mask == i2c_scl) {
        ++wait_samples;
        if (wait_samples <= stretch_probes) high = 0;
      }
      if (event->sample_mask == (i2c_scl | i2c_sda)) {
        if (receive >= 0 && data_samples < 8)
          high = i2c_scl | ((receive & (128 >> data_samples)) ? i2c_sda : 0u);
        if (data_samples == 8 && receive < 0)
          high = i2c_scl | (ack ? 0u : i2c_sda);
        sampled_at.push_back(event->time_ns);
        ++data_samples;
      }
      engine.resolve_event(high);
    }
  }
};
void i2c_oracle() {
  PeripheralTiming engine;
  engine.configure_i2c(100'000, 100);
  Wires wires;
  engine.i2c_start();
  wires.run(engine);
  check(engine.i2c_active(), "START completes only after electrical check");
  check(engine.time_ns() == 10001, "START hold timing");
  wires.data_samples = wires.wait_samples = 0;
  wires.sampled_at.clear();
  engine.i2c_write(0xa6);
  wires.run(engine, -1, true, 3);
  check(wires.data_samples == 9, "eight data samples plus ACK");
  check(wires.sampled_at.front() == 20005, "stretch delays first sample by 3 ns");
  check(wires.sampled_at.back() == 100013, "all ninth-clock high phases retained");
  check(engine.i2c_acknowledged(), "observed low ACK");
  wires.data_samples = wires.wait_samples = 0;
  engine.i2c_write(0);
  wires.run(engine, -1, false);
  check(!engine.i2c_acknowledged(), "observed high NACK must not become success");
  wires.data_samples = wires.wait_samples = 0;
  engine.i2c_read(false);
  wires.run(engine, 0x93);
  check(engine.i2c_ready() && engine.read_i2c() == 0x93, "I2C receiver-derived byte");
  check(wires.released & i2c_sda, "controller NACK is release, not high drive");
  wires.data_samples = wires.wait_samples = 0;
  engine.i2c_read(true);
  wires.run(engine, 0x12);
  check(engine.read_i2c() == 0x12, "second I2C received byte");
  check(!(wires.released & i2c_sda), "controller ACK must pull low");
  wires.data_samples = wires.wait_samples = 0;
  engine.i2c_start();
  wires.run(engine);
  check(engine.i2c_active(), "repeated START");
  wires.data_samples = wires.wait_samples = 0;
  engine.i2c_stop();
  wires.run(engine);
  check(!engine.i2c_active(), "STOP verifies released bus");
  rejects([&] { engine.i2c_write(0); });
}
void rejected_states() {
  PeripheralTiming engine;
  rejects([&] { engine.enable_timer(true); });
  rejects([&] { engine.configure_timer(3, 0, 3, 2); });
  rejects([&] { engine.configure_timer(1, 65535, 0xffffffffu, 1); });
  rejects([&] { engine.configure_timer(10'000'000, 0, 3, 5); });
  rejects([&] { engine.configure_spi(0); });
  rejects([&] { engine.configure_spi(3); });
  rejects([&] { engine.configure_i2c(400'000); });
  rejects([&] { engine.configure_i2c(100'000, 0); });
  rejects([&] { engine.configure_i2c(100'000, 1'000'001); });
  rejects([&] { engine.resolve_event(0); });
  engine.next_event(9);
  rejects([&] { engine.next_event(8); });
  engine.configure_i2c(100'000, 3);
  engine.i2c_start();
  auto event = engine.next_event(100);
  engine.resolve_event(0); // release outputs
  for (unsigned i = 1; i < 3; ++i) {
    event = engine.next_event(100);
    check(event->time_ns == 9 + i, "stretch retry retains ns granularity");
    engine.resolve_event(0);
  }
  event = engine.next_event(100);
  rejects([&] { engine.resolve_event(0); });
  rejects([&] { engine.next_event(100); }); // timeout leaves barrier unresolved
  PeripheralTiming end;
  end.next_event(PeripheralTiming::maximum_time_ns);
  end.configure_spi(100'000'000);
  rejects([&] { end.start_spi(0); });
  rejects([&] { end.next_event(PeripheralTiming::maximum_time_ns + 1); });
  PeripheralTiming occupied;
  occupied.configure_i2c(100'000);
  occupied.i2c_start();
  occupied.next_event(100);
  occupied.resolve_event(0);
  occupied.next_event(100);
  rejects([&] { occupied.resolve_event(i2c_scl); }); // SDA held low.
  occupied.resolve_event(i2c_scl | i2c_sda); // Retry is transactional.
}
void concurrent_clocks() {
  PeripheralTiming engine;
  engine.configure_timer(100'000'000, 0, 1, 1);
  engine.configure_spi(100'000'000);
  engine.enable_timer(true);
  engine.start_spi(0xff);
  std::uint64_t previous = 0;
  unsigned count = 0;
  while (auto event = engine.next_event(80)) {
    check(event->time_ns >= previous, "global clock event order");
    previous = event->time_ns;
    engine.resolve_event(0);
    ++count;
  }
  check(count == 26 && engine.read_spi() == 0, "coincident timer/SPI events preserved");
}
}
int main() {
  try {
    timer_oracle();
    spi_oracle();
    i2c_oracle();
    rejected_states();
    concurrent_clocks();
    std::cout << "peripheral timing tests passed\n";
  } catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
}
