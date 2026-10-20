// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "spikes/c_api.h"
#ifdef __cplusplus
extern "C" {
#endif
typedef struct spikes_peripheral spikes_peripheral;
typedef struct spikes_peripheral_event {
  uint64_t time_ns;
  uint32_t drive_mask, high_mask, release_mask, sample_mask;
} spikes_peripheral_event;
// Explicit clocks; no implicit RCC/PLL or CPU-cycle timing qualification.
SPIKES_API int spikes_peripheral_create(uint64_t timer_hz,uint64_t spi_hz,
  uint64_t i2c_hz,spikes_peripheral** out);
SPIKES_API void spikes_peripheral_destroy(spikes_peripheral* handle);
SPIKES_API const char* spikes_peripheral_last_error(void);
// All commands require no unacknowledged event. Operations:
// 1 configure timer(hz,psc,arr,ccr),2 enable timer(bool),3 configure SPI(hz),
// 4 start SPI(byte),5 read SPI,6 configure I2C(hz,timeout_ns),7 START,
// 8 I2C write(byte),9 I2C read(ack),10 STOP,11 consume I2C received byte.
SPIKES_API int spikes_peripheral_command(spikes_peripheral*,uint32_t operation,
  uint64_t a,uint64_t b,uint64_t c,uint64_t d,uint32_t* result);
SPIKES_API int spikes_peripheral_next(spikes_peripheral*,uint64_t deadline_ns,
  spikes_peripheral_event* event,uint32_t* present);
SPIKES_API int spikes_peripheral_resolve(spikes_peripheral*,uint32_t high_mask);
// devices:0 TIM2,1 SPI1,2 I2C1. Unsupported widths/registers/modes fail.
SPIKES_API int spikes_peripheral_write(spikes_peripheral*,uint32_t device,
  uint32_t offset,uint32_t value,uint32_t width);
SPIKES_API int spikes_peripheral_read(spikes_peripheral*,uint32_t device,
  uint32_t offset,uint32_t width,uint32_t* value);
SPIKES_API int spikes_peripheral_gpio_inputs(spikes_peripheral*,uint32_t port,
  uint32_t mask,uint32_t high);
#ifdef __cplusplus
}
#endif
