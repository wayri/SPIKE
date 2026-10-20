<!-- SPDX-License-Identifier: Apache-2.0 -->
# 0119: Owned native peripheral MMIO and finite-pad routing

Status: experimental implementation with bounded live Renode evidence,
2026-10-20.

## Decision

Add a separately selected `owned_native_peripheral_mmio` firmware mode for the
admitted STM32F407 target. Replace the inactive Renode TIM2, SPI1, I2C1 and
GPIOA--GPIOI system-bus blocks with transport-only Python peripherals backed by
SPIKE-owned C++ timing and register state. The electrical plant still owns
finite pad drive, receiver classification and stored circuit energy. Python
transports bounded integers and register snapshots; it does not calculate
peripheral timing, acknowledge a byte or synthesize received data.

The initial mode has explicit 10 MHz timer, 80 MHz SPI input and 8 MHz I2C
input clocks. They are configuration, not an inferred RCC/PLL tree. The CPU
runs at a functional one-instruction-per-microsecond cadence while peripheral
events retain their independent exact integer-nanosecond schedule. An
unresolved electrical event is a causal barrier: MMIO, configuration and input
latch changes fail until its physical receivers have been supplied.

Admit only these STM32F407 routes:

| Peripheral signal | Route | Electrical constraint |
| --- | --- | --- |
| TIM2 channel 1 PWM1 | PA0 AF1 | Active-high edge-aligned up-counter subset |
| SPI1 SCK/MISO/MOSI | PA5/PA6/PA7 AF5 | Eight-bit MSB-first master, mode 0, software NSS high |
| I2C1 SCL/SDA | PB6/PB7 AF4 | Both pins must be open drain |

GPIO input state comes only from accepted physical receiver levels. ODR is a
separate output latch and is not echoed into IDR. The owned register subset is
polled: TIM2 channel 1, one in-flight SPI byte, and an explicitly bounded
single-byte I2C receive. I2C ACK/NACK and received bits are sampled from the
finite electrical bus. No successful address, acknowledgement or return byte
is manufactured by the transport.

## Causal ordering

At a timed peripheral event, requested receiver values are taken from the
accepted **left limit immediately before** the event's output changes. The
coordinator then applies the event's drive/release changes without resetting
capacitor voltage or inductor current, and resolves the event using those saved
receiver values. The resulting right-limit electrical state governs the next
interval. This is especially material for SPI sampling edges; sampling after
applying the clock edge would be a different, unsupported contract.

The complete event derivation, primary references, arithmetic bounds and
synthetic native verification are in the
[owned peripheral timing record](../validation/NATIVE_PERIPHERAL_TIMING_20261020.md).

## Exclusions and compatibility

All RCC writes are rejected, including enable/gate writes: fixed clock frequency
does not imply that firmware-driven clock gating is modeled. This mode does not
implement RCC/PLL programming, APB peripheral resets, reset
propagation, IRQ,
DMA, timer preload/center/down-counting, SPI FIFO/overrun behavior, I2C target
mode, autonomous address devices, fast-mode I2C, arbitrary alternate-function
routing, physical setup/hold qualification or cycle-accurate silicon.
Unsupported register bits, widths, routes and overlapping BSRR set/reset masks
fail closed.

The older instruction-boundary GPIO mode and its narrowly admitted DMA2
stream-0 immediate BSRR subset remain unchanged under
[ADR 0114](0114-instruction-boundary-firmware-feedback.md). That older DMA
admission is not imported into this new mode. The five separately documented
manufacturer-identity executable approximations are also independent; they do
not provide MCU-peripheral evidence or pad parameters.

## Evidence state

Native timing/register tests use enumerated PWM edges, independent SPI bit
arrays, an electrical I2C wire harness, physical NACK/RX assertions, GPIO
input/output separation and unresolved-event rejection.

The four-test run from
`standalone/spikes_project/tests/python/test_firmware_peripheral.py`, using the
admitted separately installed Renode 1.17.0 runtime, passed in 61.551 s:

- actual firmware produced at least five TIM2 rising edges over 27 instructions
  with the required 400 ns recurrence;
- an 18-instruction SPI1 transfer crossed eight electrical receiver barriers
  and returned physical MOSI/MISO loopback byte `0xa5`;
- a 180-instruction I2C1 transaction on a bus with no target set `AF` from the
  observed NACK rather than inventing an ACK; and
- the native ABI retained the timer period and unresolved-event barrier.

The functional emulator can skip an idle terminal branch, so live fixtures put
32 NOPs before that branch while retaining the strict one-retired-instruction
guard. Initial pad configuration is obtained through a dedicated hook rather
than construction-time MMIO. APB reset attempts fail closed. These details are
bounded transport evidence, not CPU-cycle accuracy or general firmware support.

Generic pad values remain assumptions rather than STM32F407 characterization.
Knowledgeable human numerical and firmware review, physical validation and
release qualification remain pending.
