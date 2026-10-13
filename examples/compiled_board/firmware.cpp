// SPDX-License-Identifier: Apache-2.0
// Original host-compiled firmware/HAL example; no MCU instruction emulation.
#include "board_library.hpp"
#include <cmath>
#include <iostream>
#include <stdexcept>
static unsigned adc12(spikes::Board &board) {
  return static_cast<unsigned>(std::lround(board.read("adc") / 3.3 * 4095));
}
int main() {
  try {
    spikes::Board device;
    spikes::Board independent;
    device.drive("dac",3.3);
    double crossing=-1;
    for(int i=0;i<1000;++i) {
      device.step(1e-5);
      if(crossing<0 && device.read("adc")>=1.0) crossing=device.time();
    }
    const auto voltage=device.read("adc");
    // Analytic DC oracle: 3.3 * 2k / (driver 1k + R1 1k + R2 2k).
    if(std::abs(voltage-1.65)>0.001 || independent.time()!=0 || crossing<=0)
      throw std::runtime_error("Board fixture did not match its electrical oracle");
    std::cout << "adc_voltage_v=" << voltage << " pin_voltage_v=" << device.read("pin_voltage")
              << " load_current_a=" << device.read("load_current") << " adc12=" << adc12(device)
              << " threshold_time_s=" << crossing << " independent_time_s=" << independent.time() << '\n';
    return 0;
  } catch(const std::exception &e) { std::cerr << e.what() << '\n'; return 1; }
}
