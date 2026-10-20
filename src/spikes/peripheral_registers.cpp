// SPDX-License-Identifier: Apache-2.0
#include "spikes/peripheral_registers.hpp"

#include <limits>
#include <stdexcept>

namespace spikes {
namespace {
constexpr std::uint32_t tim_cr1 = 0x00;
constexpr std::uint32_t tim_dier = 0x0c;
constexpr std::uint32_t tim_sr = 0x10;
constexpr std::uint32_t tim_ccmr1 = 0x18;
constexpr std::uint32_t tim_ccer = 0x20;
constexpr std::uint32_t tim_cnt = 0x24;
constexpr std::uint32_t tim_psc = 0x28;
constexpr std::uint32_t tim_arr = 0x2c;
constexpr std::uint32_t tim_ccr1 = 0x34;
constexpr std::uint32_t tim_cen = 1u;
constexpr std::uint32_t tim_uif = 1u;

constexpr std::uint32_t spi_cr1 = 0x00;
constexpr std::uint32_t spi_cr2 = 0x04;
constexpr std::uint32_t spi_sr = 0x08;
constexpr std::uint32_t spi_dr = 0x0c;
constexpr std::uint32_t spi_mstr = 1u << 2;
constexpr std::uint32_t spi_br = 7u << 3;
constexpr std::uint32_t spi_spe = 1u << 6;
constexpr std::uint32_t spi_ssi = 1u << 8;
constexpr std::uint32_t spi_ssm = 1u << 9;
constexpr std::uint32_t spi_allowed = spi_mstr | spi_br | spi_spe | spi_ssi | spi_ssm;
constexpr std::uint32_t spi_rxne = 1u;
constexpr std::uint32_t spi_txe = 1u << 1;
constexpr std::uint32_t spi_bsy = 1u << 7;

constexpr std::uint32_t i2c_cr1 = 0x00;
constexpr std::uint32_t i2c_cr2 = 0x04;
constexpr std::uint32_t i2c_dr = 0x10;
constexpr std::uint32_t i2c_sr1 = 0x14;
constexpr std::uint32_t i2c_sr2 = 0x18;
constexpr std::uint32_t i2c_ccr = 0x1c;
constexpr std::uint32_t i2c_pe = 1u;
constexpr std::uint32_t i2c_start = 1u << 8;
constexpr std::uint32_t i2c_stop = 1u << 9;
constexpr std::uint32_t i2c_ack = 1u << 10;
constexpr std::uint32_t i2c_cr1_allowed = i2c_pe | i2c_start | i2c_stop | i2c_ack;
constexpr std::uint32_t i2c_sb = 1u;
constexpr std::uint32_t i2c_addr = 1u << 1;
constexpr std::uint32_t i2c_btf = 1u << 2;
constexpr std::uint32_t i2c_rxne = 1u << 6;
constexpr std::uint32_t i2c_txe = 1u << 7;
constexpr std::uint32_t i2c_af = 1u << 10;
constexpr std::uint32_t i2c_sr1_known =
    i2c_sb | i2c_addr | i2c_btf | i2c_rxne | i2c_txe | i2c_af;
constexpr std::uint32_t i2c_msl = 1u;
constexpr std::uint32_t i2c_busy = 1u << 1;
constexpr std::uint32_t i2c_tra = 1u << 2;

constexpr std::uint32_t gpio_mode = 0x00;
constexpr std::uint32_t gpio_output_type = 0x04;
constexpr std::uint32_t gpio_speed = 0x08;
constexpr std::uint32_t gpio_pull = 0x0c;
constexpr std::uint32_t gpio_input = 0x10;
constexpr std::uint32_t gpio_output = 0x14;
constexpr std::uint32_t gpio_set_reset = 0x18;
constexpr std::uint32_t gpio_alternate_low = 0x20;
constexpr std::uint32_t gpio_alternate_high = 0x24;

void require(bool condition, const char* message) {
  if (!condition) throw std::invalid_argument(message);
}

void require_word(std::uint32_t width) {
  require(width == 4, "only 32-bit access is supported for this register");
}

void require_data_width(std::uint32_t width) {
  require(width == 1 || width == 2 || width == 4,
          "data register access width must be 1, 2, or 4 bytes");
}
} // namespace

PeripheralRegisters::PeripheralRegisters(PeripheralTiming& timing,
                                         std::uint64_t timer_input_hz,
                                         std::uint64_t spi_input_hz,
                                         std::uint64_t i2c_input_hz)
    : timing_(timing), timer_input_hz_(timer_input_hz),
      spi_input_hz_(spi_input_hz), i2c_input_hz_(i2c_input_hz) {
  require(timer_input_hz_ > 0 && spi_input_hz_ > 0 && i2c_input_hz_ > 0,
          "peripheral input clocks must be positive");
  gpio_[0].mode = 0xa8000000u;
  gpio_[0].speed = 0x0c000000u;
  gpio_[0].pull = 0x64000000u;
  gpio_[1].mode = 0x00000280u;
  gpio_[1].speed = 0x000000c0u;
  gpio_[1].pull = 0x00000100u;
}

void PeripheralRegisters::refresh() {
  timing_.require_resolved();
  if (tim_cr1_ & tim_cen) {
    const auto tick_numerator = 1'000'000'000ull * (std::uint64_t(tim_psc_) + 1);
    if (tick_numerator % timer_input_hz_ == 0) {
      const auto tick = tick_numerator / timer_input_hz_;
      const auto counts = std::uint64_t(tim_arr_) + 1;
      if (tick && counts <= std::numeric_limits<std::uint64_t>::max() / tick) {
        const auto period = tick * counts;
        const auto wraps = (timing_.time_ns() - tim_started_ns_) / period;
        if (wraps > tim_seen_wraps_) {
          tim_sr_ |= tim_uif;
          tim_seen_wraps_ = wraps;
        }
      }
    }
  }

  if (i2c_pending_ != I2cPending::none && !timing_.i2c_busy()) {
    const auto completed = i2c_pending_;
    i2c_pending_ = I2cPending::none;
    i2c_cr1_ &= ~(i2c_start | i2c_stop);
    switch (completed) {
      case I2cPending::start:
        i2c_sr1_ &= ~(i2c_addr | i2c_btf | i2c_rxne | i2c_txe | i2c_af);
        i2c_sr1_ |= i2c_sb;
        i2c_expect_address_ = true;
        i2c_receiver_ = false;
        break;
      case I2cPending::address:
        if (timing_.i2c_acknowledged()) {
          i2c_sr1_ |= i2c_addr;
          i2c_receiver_ = i2c_address_read_;
        } else {
          i2c_sr1_ |= i2c_af;
          i2c_receiver_ = false;
        }
        break;
      case I2cPending::transmit:
        if (timing_.i2c_acknowledged()) i2c_sr1_ |= i2c_txe | i2c_btf;
        else i2c_sr1_ |= i2c_af;
        break;
      case I2cPending::receive:
        require(timing_.i2c_ready(), "I2C receive completed without data");
        i2c_sr1_ |= i2c_rxne;
        break;
      case I2cPending::stop:
        i2c_expect_address_ = false;
        i2c_receiver_ = false;
        i2c_addr_sr1_read_ = false;
        i2c_sr1_ &= ~(i2c_sb | i2c_addr | i2c_btf | i2c_txe);
        break;
      case I2cPending::none: break;
    }
  }
}

void PeripheralRegisters::configure_timer() {
  require(tim_ccmr1_ == 0x60, "TIM2 requires channel 1 PWM mode 1");
  require(tim_ccer_ == 1, "TIM2 requires channel 1 output enabled");
  timing_.configure_timer(timer_input_hz_, tim_psc_, tim_arr_, tim_ccr1_);
}

void PeripheralRegisters::configure_spi() {
  const auto br = (spi_cr1_ & spi_br) >> 3;
  const auto divisor = std::uint64_t{1} << (br + 1);
  require(spi_input_hz_ % divisor == 0,
          "SPI1 input clock is not exactly divisible by BR");
  timing_.configure_spi(spi_input_hz_ / divisor);
}

void PeripheralRegisters::configure_i2c() {
  require(i2c_input_hz_ % 1'000'000 == 0,
          "I2C1 input clock must be an integer number of MHz");
  const auto mhz = i2c_input_hz_ / 1'000'000;
  require(mhz >= 2 && mhz <= 63 && i2c_cr2_ == mhz,
          "I2C1 CR2 FREQ does not match the declared input clock");
  require(i2c_ccr_ >= 4 && i2c_ccr_ <= 0xfff,
          "I2C1 supports only standard-mode CCR values of at least 4");
  const auto divisor = std::uint64_t{2} * i2c_ccr_;
  require(i2c_input_hz_ % divisor == 0,
          "I2C1 input clock is not exactly divisible by 2*CCR");
  timing_.configure_i2c(i2c_input_hz_ / divisor);
}

std::uint32_t PeripheralRegisters::timer_count() const {
  if (!(tim_cr1_ & tim_cen)) return 0;
  const auto numerator = 1'000'000'000ull * (std::uint64_t(tim_psc_) + 1);
  require(numerator % timer_input_hz_ == 0,
          "TIM2 tick is not an exact integer nanosecond");
  const auto tick = numerator / timer_input_hz_;
  const auto counts = std::uint64_t(tim_arr_) + 1;
  return static_cast<std::uint32_t>(((timing_.time_ns() - tim_started_ns_) / tick) % counts);
}

void PeripheralRegisters::write(std::uint32_t device, std::uint32_t offset,
                                std::uint32_t value, std::uint32_t width) {
  refresh();
  switch (device) {
    case timer_device: write_timer(offset, value, width); break;
    case spi_device: write_spi(offset, value, width); break;
    case i2c_device: write_i2c(offset, value, width); break;
    default:
      if (device >= gpio_a_device && device <= gpio_i_device)
        write_gpio(device - gpio_a_device, offset, value, width);
      else throw std::invalid_argument("unsupported peripheral device");
  }
}

std::uint32_t PeripheralRegisters::read(std::uint32_t device,
                                       std::uint32_t offset,
                                       std::uint32_t width) {
  refresh();
  switch (device) {
    case timer_device: return read_timer(offset, width);
    case spi_device: return read_spi(offset, width);
    case i2c_device: return read_i2c(offset, width);
    default:
      if (device >= gpio_a_device && device <= gpio_i_device)
        return read_gpio(device - gpio_a_device, offset, width);
      throw std::invalid_argument("unsupported peripheral device");
  }
}

void PeripheralRegisters::gpio_inputs(std::uint32_t port, std::uint32_t mask,
                                      std::uint32_t high) {
  refresh();
  require(port < gpio_.size(), "unsupported GPIO port index");
  require((mask & ~0xffffu) == 0, "GPIO input mask exceeds 16 pads");
  require((high & ~mask) == 0, "GPIO high levels must be a subset of the input mask");
  gpio_[port].input = (gpio_[port].input & ~mask) | high;
}

void PeripheralRegisters::write_gpio(std::uint32_t port, std::uint32_t offset,
                                     std::uint32_t value, std::uint32_t width) {
  require_word(width);
  auto& gpio = gpio_[port];
  switch (offset) {
    case gpio_mode: gpio.mode = value; break;
    case gpio_output_type:
      require((value & ~0xffffu) == 0, "GPIO OTYPER exceeds 16 pads");
      gpio.output_type = value;
      break;
    case gpio_speed: gpio.speed = value; break;
    case gpio_pull: gpio.pull = value; break;
    case gpio_input: throw std::invalid_argument("GPIO IDR is read-only");
    case gpio_output:
      require((value & ~0xffffu) == 0, "GPIO ODR exceeds 16 pads");
      gpio.output = value;
      break;
    case gpio_set_reset: {
      const auto set = value & 0xffffu;
      const auto reset = value >> 16;
      require((set & reset) == 0,
              "GPIO BSRR simultaneous set/reset of one pad is unsupported");
      gpio.output = (gpio.output | set) & ~reset;
      break;
    }
    case gpio_alternate_low: gpio.alternate_low = value; break;
    case gpio_alternate_high: gpio.alternate_high = value; break;
    default: throw std::invalid_argument("unsupported GPIO register offset");
  }
}

std::uint32_t PeripheralRegisters::read_gpio(std::uint32_t port,
                                            std::uint32_t offset,
                                            std::uint32_t width) {
  require_word(width);
  const auto& gpio = gpio_[port];
  switch (offset) {
    case gpio_mode: return gpio.mode;
    case gpio_output_type: return gpio.output_type;
    case gpio_speed: return gpio.speed;
    case gpio_pull: return gpio.pull;
    case gpio_input: return gpio.input;
    case gpio_output: return gpio.output;
    case gpio_set_reset: return 0;
    case gpio_alternate_low: return gpio.alternate_low;
    case gpio_alternate_high: return gpio.alternate_high;
    default: throw std::invalid_argument("unsupported GPIO register offset");
  }
}

void PeripheralRegisters::write_timer(std::uint32_t offset, std::uint32_t value,
                                      std::uint32_t width) {
  require_word(width);
  switch (offset) {
    case tim_cr1: {
      require((value & ~tim_cen) == 0,
              "unsupported TIM2 CR1 mode (only edge-aligned upcounting CEN)");
      const bool was_enabled = tim_cr1_ & tim_cen;
      const bool enable = value & tim_cen;
      if (was_enabled != enable) {
        if (enable) {
          configure_timer();
          timing_.enable_timer(true);
          tim_started_ns_ = timing_.time_ns();
          tim_seen_wraps_ = 0;
        } else timing_.enable_timer(false);
      }
      tim_cr1_ = value;
      break;
    }
    case tim_dier:
      require(value == 0, "TIM2 interrupt and DMA requests are unsupported");
      break;
    case tim_sr:
      require((value & ~tim_uif) == 0, "unsupported TIM2 status flag write");
      if (!(value & tim_uif)) tim_sr_ &= ~tim_uif;
      break;
    case tim_ccmr1:
      require(!(tim_cr1_ & tim_cen) || value == tim_ccmr1_,
              "stop TIM2 before changing CCMR1");
      require(value == 0 || value == 0x60,
              "TIM2 supports only reset or PWM1 channel 1 CCMR1");
      tim_ccmr1_ = value;
      break;
    case tim_ccer:
      require(!(tim_cr1_ & tim_cen) || value == tim_ccer_,
              "stop TIM2 before changing CCER");
      require(value <= 1, "TIM2 supports only CC1E with active-high polarity");
      tim_ccer_ = value;
      break;
    case tim_cnt:
      throw std::invalid_argument("TIM2 CNT writes are unsupported");
    case tim_psc:
      require(!(tim_cr1_ & tim_cen) || value == tim_psc_,
              "stop TIM2 before changing PSC");
      require(value <= 0xffff, "TIM2 PSC exceeds 16 bits");
      tim_psc_ = value;
      break;
    case tim_arr:
      require(!(tim_cr1_ & tim_cen) || value == tim_arr_,
              "stop TIM2 before changing ARR");
      tim_arr_ = value;
      break;
    case tim_ccr1:
      require(!(tim_cr1_ & tim_cen) || value == tim_ccr1_,
              "stop TIM2 before changing CCR1");
      tim_ccr1_ = value;
      break;
    default: throw std::invalid_argument("unsupported TIM2 register offset");
  }
}

std::uint32_t PeripheralRegisters::read_timer(std::uint32_t offset,
                                             std::uint32_t width) {
  require_word(width);
  switch (offset) {
    case tim_cr1: return tim_cr1_;
    case tim_dier: return 0;
    case tim_sr: return tim_sr_;
    case tim_ccmr1: return tim_ccmr1_;
    case tim_ccer: return tim_ccer_;
    case tim_cnt: return timer_count();
    case tim_psc: return tim_psc_;
    case tim_arr: return tim_arr_;
    case tim_ccr1: return tim_ccr1_;
    default: throw std::invalid_argument("unsupported TIM2 register offset");
  }
}

void PeripheralRegisters::write_spi(std::uint32_t offset, std::uint32_t value,
                                    std::uint32_t width) {
  if (offset == spi_dr) {
    require_data_width(width);
    require(value <= 0xff, "SPI1 is limited to 8-bit data frames");
    require(spi_cr1_ & spi_spe, "SPI1 DR write requires SPE");
    require(!timing_.spi_busy() && !timing_.spi_ready(),
            "SPI1 is busy or received data is unread");
    timing_.start_spi(static_cast<std::uint8_t>(value));
    return;
  }
  require_word(width);
  switch (offset) {
    case spi_cr1: {
      require((value & ~spi_allowed) == 0,
              "unsupported SPI1 CR1 mode (8-bit MSB-first mode 0 only)");
      const bool was_enabled = spi_cr1_ & spi_spe;
      const bool enable = value & spi_spe;
      if (was_enabled) {
        require(!timing_.spi_busy(), "cannot change or disable busy SPI1");
        require((value & ~spi_spe) == (spi_cr1_ & ~spi_spe),
                "disable SPI1 before changing its configuration");
      }
      if (enable) {
        require((value & (spi_mstr | spi_ssm | spi_ssi)) ==
                    (spi_mstr | spi_ssm | spi_ssi),
                "SPI1 requires master mode and software NSS high");
        if (!was_enabled) {
          const auto previous = spi_cr1_;
          spi_cr1_ = value;
          try { configure_spi(); }
          catch (...) { spi_cr1_ = previous; throw; }
        }
      }
      spi_cr1_ = value;
      break;
    }
    case spi_cr2:
      require(value == 0, "SPI1 CR2 interrupt, DMA, and frame options are unsupported");
      break;
    default: throw std::invalid_argument("unsupported or read-only SPI1 register offset");
  }
}

std::uint32_t PeripheralRegisters::read_spi(std::uint32_t offset,
                                           std::uint32_t width) {
  if (offset == spi_dr) {
    require_data_width(width);
    require(timing_.spi_ready(), "SPI1 RXNE is not set");
    return timing_.read_spi();
  }
  require_word(width);
  switch (offset) {
    case spi_cr1: return spi_cr1_;
    case spi_cr2: return 0;
    case spi_sr:
      return (timing_.spi_ready() ? spi_rxne : 0u) |
             (timing_.spi_busy() ? spi_bsy : spi_txe);
    default: throw std::invalid_argument("unsupported SPI1 register offset");
  }
}

void PeripheralRegisters::write_i2c(std::uint32_t offset, std::uint32_t value,
                                    std::uint32_t width) {
  if (offset == i2c_dr) {
    require_data_width(width);
    require(value <= 0xff, "I2C1 DR accepts one byte");
    require(i2c_cr1_ & i2c_pe, "I2C1 DR write requires PE");
    require(i2c_pending_ == I2cPending::none && !timing_.i2c_busy(),
            "I2C1 command already in progress");
    if (i2c_expect_address_) {
      const bool address_read = value & 1u;
      require(!address_read || !(i2c_cr1_ & i2c_ack),
              "I2C1 supports a single receive byte with ACK cleared");
      timing_.i2c_write(static_cast<std::uint8_t>(value));
      i2c_address_read_ = address_read;
      i2c_expect_address_ = false;
      i2c_addr_sr1_read_ = false;
      i2c_sr1_ &= ~(i2c_sb | i2c_addr | i2c_btf | i2c_rxne | i2c_txe | i2c_af);
      i2c_pending_ = I2cPending::address;
    } else {
      require(!i2c_receiver_, "I2C1 DR writes are unavailable in receiver mode");
      require(timing_.i2c_active() && !(i2c_sr1_ & i2c_addr) &&
                  (i2c_sr1_ & i2c_txe) && !(i2c_sr1_ & i2c_af),
              "I2C1 data write requires an acknowledged, cleared write address");
      timing_.i2c_write(static_cast<std::uint8_t>(value));
      i2c_sr1_ &= ~(i2c_btf | i2c_txe | i2c_af);
      i2c_pending_ = I2cPending::transmit;
    }
    return;
  }
  require_word(width);
  switch (offset) {
    case i2c_cr1: {
      require((value & ~i2c_cr1_allowed) == 0,
              "unsupported I2C1 CR1 option");
      require((value & (i2c_start | i2c_stop)) != (i2c_start | i2c_stop),
              "I2C1 START and STOP cannot be requested together");
      const bool was_enabled = i2c_cr1_ & i2c_pe;
      const bool enable = value & i2c_pe;
      const auto stable = value & (i2c_pe | i2c_ack);
      if (value & i2c_start) {
        require(enable && i2c_pending_ == I2cPending::none &&
                    !timing_.i2c_busy() && !(i2c_sr1_ & i2c_rxne),
                "I2C1 START requires enabled idle state with no unread data");
      } else if (value & i2c_stop) {
        require(enable && i2c_pending_ == I2cPending::none &&
                    !timing_.i2c_busy() && timing_.i2c_active(),
                "I2C1 STOP requires an active, idle bus command state");
      }
      if (was_enabled != enable) {
        require(i2c_pending_ == I2cPending::none && !timing_.i2c_busy() &&
                    !timing_.i2c_active(),
                "I2C1 PE can change only while the bus is idle");
        if (enable) {
          const auto previous = i2c_cr1_;
          i2c_cr1_ = stable;
          try { configure_i2c(); }
          catch (...) { i2c_cr1_ = previous; throw; }
        }
      }
      if (value & i2c_start) {
        timing_.i2c_start();
        i2c_cr1_ = stable | i2c_start;
        i2c_pending_ = I2cPending::start;
      } else if (value & i2c_stop) {
        timing_.i2c_stop();
        i2c_cr1_ = stable | i2c_stop;
        i2c_pending_ = I2cPending::stop;
      } else i2c_cr1_ = stable;
      break;
    }
    case i2c_cr2:
      require(!(i2c_cr1_ & i2c_pe), "disable I2C1 before changing CR2");
      require((value & ~0x3fu) == 0,
              "I2C1 CR2 interrupt and DMA options are unsupported");
      i2c_cr2_ = value;
      break;
    case i2c_ccr:
      require(!(i2c_cr1_ & i2c_pe), "disable I2C1 before changing CCR");
      require((value & ~0xfffu) == 0,
              "I2C1 fast mode and nonstandard duty are unsupported");
      i2c_ccr_ = value;
      break;
    case i2c_sr1:
      require((value & ~i2c_af) == 0, "only I2C1 AF status clearing is supported");
      if (!(value & i2c_af)) i2c_sr1_ &= ~i2c_af;
      break;
    default: throw std::invalid_argument("unsupported or read-only I2C1 register offset");
  }
}

std::uint32_t PeripheralRegisters::read_i2c(std::uint32_t offset,
                                           std::uint32_t width) {
  if (offset == i2c_dr) {
    require_data_width(width);
    require(i2c_sr1_ & i2c_rxne, "I2C1 RXNE is not set");
    const auto value = timing_.read_i2c();
    i2c_sr1_ &= ~(i2c_rxne | i2c_btf);
    return value;
  }
  require_word(width);
  switch (offset) {
    case i2c_cr1: return i2c_cr1_;
    case i2c_cr2: return i2c_cr2_;
    case i2c_sr1:
      if (i2c_sr1_ & i2c_addr) i2c_addr_sr1_read_ = true;
      return i2c_sr1_ & i2c_sr1_known;
    case i2c_sr2: {
      const auto status = timing_.i2c_active()
                              ? (i2c_msl | i2c_busy | (i2c_receiver_ ? 0u : i2c_tra))
                              : 0u;
      if (i2c_addr_sr1_read_ && (i2c_sr1_ & i2c_addr)) {
        if (i2c_receiver_) {
          require(i2c_pending_ == I2cPending::none && !timing_.i2c_busy(),
                  "I2C1 receive cannot begin while another command is active");
          timing_.i2c_read(false);
          i2c_pending_ = I2cPending::receive;
        }
        i2c_sr1_ &= ~i2c_addr;
        i2c_addr_sr1_read_ = false;
        if (!i2c_receiver_) i2c_sr1_ |= i2c_txe;
      }
      return status;
    }
    case i2c_ccr: return i2c_ccr_;
    default: throw std::invalid_argument("unsupported I2C1 register offset");
  }
}

} // namespace spikes
