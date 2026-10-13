<!-- SPDX-License-Identifier: Apache-2.0 -->
# Firmware emulation admission boundary

SPIKE does not currently execute Arduino, Raspberry Pi Pico, ESP32, or STM32
firmware. `python/spikes/firmware_targets.py` is a fail-closed manifest and
admission contract for future adapters; it is not an emulator integration.

## What the contract establishes

The manifest binds a SHA-256 digest to one board-level target, CPU architecture,
and loading format. Generic labels such as "Arduino" are intentionally rejected:
Arduino products use different MCUs and board peripherals.

| Target ID | Candidate engine | Admitted artifact metadata |
| --- | --- | --- |
| `arduino-uno-r3-atmega328p` | simavr | ELF |
| `arduino-nano-33-ble` | Renode | ELF; raw BIN with explicit load address |
| `stm32f103-blue-pill` | Renode | ELF; raw BIN with explicit load address |
| `stm32f4-discovery` | Renode | ELF; raw BIN with explicit load address |
| `esp32` | Espressif QEMU | complete ESP-IDF flash BIN, including bootloader and partition table, with configured flash size |
| `raspberry-pi-pico-rp2040` | none established | ELF/UF2/raw metadata only; execution rejected |

ELF carries loadable segments and entry information. A raw BIN does not, so its
load address is mandatory. UF2 is a block-oriented deployment container; SPIKE
has no reviewed extractor and rejects it for execution. An ESP32 application BIN
alone is not the QEMU flash image: the complete flash layout is required.

Renode documents ELF loading plus separate raw binary loading and board models
for STM32F103 and STM32F4 Discovery. Its Arduino IDE integration currently names
Arduino Nano 33 BLE specifically, not all Arduino boards. Espressif documents a
QEMU flash image containing the bootloader, partition table, and application at
their build offsets. These sources inform the manifest only; SPIKE does not copy
or redistribute either runtime.

- Renode: https://renode.readthedocs.io/en/latest/basic/machines.html
- Renode supported boards: https://renode.readthedocs.io/en/latest/introduction/supported-boards.html
- Renode Arduino integration: https://renode.readthedocs.io/en/latest/host-integration/arduino.html
- Espressif QEMU guide: https://docs.espressif.com/projects/esp-idf/en/stable/esp32/api-guides/tools/qemu.html
- simavr project (ATmega328 family and ELF loading): https://github.com/buserror/simavr

## Capability boundaries

Instruction execution, modeled MCU peripherals, and electrical/SI simulation are
three separate claims. Even a reviewed emulator adapter would initially be only
a `backend-candidate`; even instruction emulation remains false until an actual
run produces reviewed evidence. The contract also reports peripheral and
electrical co-simulation as false. SPI GPIO/SPI events do not establish pad drive strength,
slew, package parasitics, transmission-line loss, receiver thresholds, jitter,
or analog contention.

A real SPI co-simulation adapter would additionally need a versioned event/time
protocol, deterministic clock ownership, pin/alternate-function mapping, voltage
and impedance models with units, bidirectional contention handling, rollback or
step rejection semantics, timeout/cancellation limits, and comparison against
logic-analyzer and oscilloscope fixtures. SI validity would require the existing
board geometry/material stack and a solver-specific evidence envelope. Emulator
success alone cannot validate electrical timing or hardware safety behavior.

No emulator runtime is bundled or installed. Before enabling execution, the
project needs an approved redistributable dependency plan, exact runtime and
platform-model identity, digest-bound adapter approval, sandbox/process limits,
per-target peripheral coverage tests, and license/third-party notice updates.
