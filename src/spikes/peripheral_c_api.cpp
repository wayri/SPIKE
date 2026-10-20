// SPDX-License-Identifier: Apache-2.0
#include "spikes/peripheral_c_api.h"
#include "spikes/peripheral_timing.hpp"
#include "spikes/peripheral_registers.hpp"
#include <limits>
#include <stdexcept>
#include <string>

struct spikes_peripheral {
  spikes::PeripheralTiming timing;
  spikes::PeripheralRegisters registers;
  spikes_peripheral(uint64_t a,uint64_t b,uint64_t c):registers(timing,a,b,c) {}
};
namespace {
thread_local std::string error;
template<class F> int protect(F&& action) noexcept {
  try { action();error.clear();return 0; }
  catch(const std::exception& e) {error=e.what();return 1;}
  catch(...) {error="unknown peripheral service failure";return 1;}
}
uint32_t u32(uint64_t n) {
  if(n>std::numeric_limits<uint32_t>::max())throw std::invalid_argument("integer exceeds uint32 range");
  return uint32_t(n);
}
uint8_t byte(uint64_t n) {
  if(n>255)throw std::invalid_argument("byte outside0..255");
  return uint8_t(n);
}
bool boolean(uint64_t n) {
  if(n>1)throw std::invalid_argument("Boolean must be0or1");
  return n!=0;
}
void handle(const spikes_peripheral* p) {
  if(!p)throw std::invalid_argument("peripheral handle required");
}
}
extern "C" {
int spikes_peripheral_create(uint64_t a,uint64_t b,uint64_t c,spikes_peripheral** out) {
  if(out)*out=nullptr;
  return protect([&]{if(!out)throw std::invalid_argument("output handle required");
    *out=new spikes_peripheral(a,b,c);});
}
void spikes_peripheral_destroy(spikes_peripheral* p) {delete p;}
const char* spikes_peripheral_last_error() {return error.c_str();}
int spikes_peripheral_command(spikes_peripheral* p,uint32_t op,uint64_t a,uint64_t b,
                              uint64_t c,uint64_t d,uint32_t* out) {
  if(out)*out=0;
  return protect([&]{handle(p);if(!out)throw std::invalid_argument("command result required");
    auto& t=p->timing;
    switch(op) {
    case 1:t.configure_timer(a,u32(b),u32(c),u32(d));break;
    case 2:t.enable_timer(boolean(a));break;
    case 3:t.configure_spi(a);break;
    case 4:t.start_spi(byte(a));break;
    case 5:*out=t.read_spi();break;
    case 6:t.configure_i2c(a,b);break;
    case 7:t.i2c_start();break;
    case 8:t.i2c_write(byte(a));break;
    case 9:t.i2c_read(boolean(a));break;
    case 10:t.i2c_stop();break;
    case 11:*out=t.read_i2c();break;
    default:throw std::invalid_argument("unsupported peripheral operation");
    }
  });
}
int spikes_peripheral_next(spikes_peripheral* p,uint64_t deadline,
                          spikes_peripheral_event* event,uint32_t* present) {
  if(present)*present=0;
  if(event)*event={};
  return protect([&]{handle(p);if(!event||!present)throw std::invalid_argument("event outputs required");
    const auto e=p->timing.next_event(deadline);
    if(e){*present=1;*event={e->time_ns,e->drive_mask,e->high_mask,e->release_mask,e->sample_mask};}
  });
}
int spikes_peripheral_resolve(spikes_peripheral* p,uint32_t high) {
  return protect([&]{handle(p);p->timing.resolve_event(high);});
}
int spikes_peripheral_write(spikes_peripheral* p,uint32_t device,uint32_t offset,uint32_t value,uint32_t width) {
  return protect([&]{handle(p);p->registers.write(device,offset,value,width);});
}
int spikes_peripheral_read(spikes_peripheral* p,uint32_t device,uint32_t offset,uint32_t width,uint32_t* out) {
  if(out)*out=0;
  return protect([&]{handle(p);if(!out)throw std::invalid_argument("read result required");
    *out=p->registers.read(device,offset,width);});
}
int spikes_peripheral_gpio_inputs(spikes_peripheral* p,uint32_t port,uint32_t mask,uint32_t high) {
  return protect([&]{handle(p);p->registers.gpio_inputs(port,mask,high);});
}
}
