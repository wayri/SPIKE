<!-- SPDX-License-Identifier: Apache-2.0 -->
# Owned peripheral timing: bounded behavioral evidence

Review date: 2026-10-20. Status: experimental, independently authored,
synthetically verified behavioral timer/SPI/I2C service. This is an explicit
replacement execution path, not a parameter correction to Renode. It does not
qualify an MCU, a circuit board, instruction timing, physical setup/hold
margins, or hardware-in-the-loop execution.

## Primary references actually reviewed

Only manufacturer protocol/timing descriptions were used, not external
implementation code, examples, firmware, or test vectors. The implementation,
derivation, harness and numeric examples are original SPIKE-owned material.

| Primary source | Exact reviewed scope | Bounded application |
| --- | --- | --- |
| STMicroelectronics, [AN4013, Introduction to timers for STM32 MCUs](https://www.st.com/resource/en/application_note/an4013-introduction-to-timers-for-stm32-mcus-stmicroelectronics.pdf), Rev 14, February 2026 | Section 2.2, printed pp. 12-14, update frequency; section 2.5, pp. 16-17, PWM1 comparison and edge-aligned modes | Prescaled inclusive counter period and active-high PWM1 comparison. No RCC inference or broad register compatibility follows. |
| Motorola, [AN991/D, Using the Serial Peripheral Interface to Communicate Between Multiple Microcomputers](https://www.nxp.com/docs/en/application-note/AN991.pdf), Rev 1, January 2002; authoritative NXP-hosted copy | Printed pp. 2-4, signal descriptions, CPOL/CPHA definitions, Figure 2 timing | Eight MSB-first bits, idle-low clock and first-edge sampling. Device-specific register values, examples and firmware were not used. |
| NXP, [UM10204, I2C-bus specification and user manual](https://www.nxp.com/docs/en/user-guide/UM10204.pdf), Rev 7.0, 1 October 2021 | Sections 3.1.1-3.1.9, printed pp. 8-12 | Released/open-drain wires, START/STOP, eight data bits plus ACK, and waiting for observed SCL-high. This does not establish electrical compliance or multi-controller support. |

The official RM0090 PDF could not be read in this review: the web reader
rejected its size and a direct official download failed. These references
establish the selected behaviors, not a claim that the whole STM32F407
register map was verified here. Register-facade evidence is a separate gate.

## Independent discrete formulation

The service owns its state in `src/spikes/peripheral_timing.hpp/.cpp`.
Time is a common-epoch unsigned integer number of nanoseconds, bounded by
`2^48`. Frequencies are positive integer Hz; unsupported fractional-ns
intervals are rejected, never rounded.

For an up-counter, let `P = PSC+1` and `A = ARR+1`. Enumerating the admitted
counter states gives `0,1,...,ARR,0`, hence there are `A`, not `ARR`, input
tick intervals per period. With explicit input frequency `f`,

```text
tick_ns = 10^9 * P / f
period_ns = A * tick_ns
active(CNT) = (CNT < CCR)
```

The example `f=10 MHz, PSC=0, ARR=3, CCR=2` enumerates counter values
`0,1,2,3,0` at `0,100,200,300,400 ns`. Thus the edges are high at 0,
low at 200, high at 400 ns. A 300 ns recurrence fails the explicit counter
enumeration. A zero compare is always inactive; compare `ARR+1` is always
active. Enabling starts phase zero; disabling retains the last emitted
output and re-enabling restarts phase zero. Dynamic preload, retained-counter
resume, inversions, down-counting and center-aligned modes are not implemented.

For SPI mode 0, with `h=10^9/(2*f_SPI)` nanoseconds, byte start `t0` places
the MSB on MOSI with SCK low. Rising edges at `t0+(2*k+1)*h`, `k=0..7`,
sample MISO. Falling edges at `t0+(2*k+2)*h` place the next bit, except
the last falling edge, which completes the byte. Each bit sample updates
`receive_next=2*receive_previous+sample`. A completed unread byte must be
consumed before another transfer; this is a bounded single-byte service,
not an emulation of hardware FIFOs/overrun flags. Chip-select is controlled
separately by the integrating firmware/GPIO path.

For I2C, each bit begins with SCL low and SDA driven low or released.
After `h` low nanoseconds, SCL is released. The service samples its receiver
after 1 ns, then every 1 ns until high; only that observed high begins the
`h`-nanosecond high phase. The data/ACK receiver is sampled at the end of
the high phase, before a separate same-time SCL-falling event. Thus

```text
observed_high = first admitted 1 ns receiver probe reporting SCL high
data_sample_time = observed_high + h
next_bit_low_start = data_sample_time
```

SDA is released during a transmitted byte's ninth clock. Low ACK and high
NACK are recorded distinctly; no address/device success is manufactured.
Read bytes come from eight SDA samples, then the requested controller ACK
pulls SDA low or NACK leaves it released. START, repeated START and STOP
have explicit wire events and receiver checks. Writes with observed data
different from the intended bit fail closed; this is contention rejection,
not multi-controller arbitration.

## Causal integration contract and limitations

`next_event(deadline_ns)` yields at most one event, or advances only to that
deadline if no earlier event exists. Each event contains changed output
signals, push-pull high bits, released bits, and required input sample bits.
No output event drives I2C high. Stable ordering of simultaneous independent
events is timer, SPI, I2C; all are retained.

Every event is a barrier. The caller must advance the electrical model to
the event time and obtain requested receiver values from the accepted
**left limit immediately before** applying that event's output changes. It
then applies drive/release changes without resetting stored energy and calls
`resolve_event` with the saved receiver values. Sampling after the event's
outputs have been applied is a different and unsupported ordering. No advance,
MMIO access, command or configuration is allowed while an event remains pending.
SPI MISO must already be valid at the sampling edge; an externally modeled
mode-0 target prepares its output before that edge. I2C's SCL probe follows
release by positive time. A binary mask is not permission to guess an
undefined receiver: the integration must reject invalid/floating/ambiguous
electrical inputs according to its receiver contract.

The engine can process sub-instruction events because it is not clocked by
CPU-step boundaries. This alone does not prove that a CPU adapter prevents
execution past an unresolved MMIO/input barrier. That must be verified in
the integration tests. Neither these tests nor an instruction-start timestamp
establish physical CPU cycle accuracy.

The 1 ns I2C polling grid deliberately delays recognition by up to 1 ns
after an asynchronous SCL crossing, plus the mandatory first 1 ns probe.
Even an ideal instantaneously released clock therefore adds 1 ns per bit
period. This is a documented sampled-receiver model, not exact continuous
threshold-root location or exact nominal I2C baud rate. Standard-mode rates
up to 100 kHz only are admitted. Analog rise time, pull-up sizing, setup/hold
qualification, filter delays, fast/high-speed modes, DMA, interrupts, slave
mode, SMBus, automatic addressing and autonomous target devices are absent.

Arithmetic checks precede configuration or command state changes. Failed
event resolution leaves the same barrier and state pending, permitting a
diagnostic/recovery decision without partial byte progress. Each call does
constant bounded work and retains no event history. Clock-stretch timeout is
an explicit simulation guard (1 to 1,000,000 ns), not a protocol-required
timeout. The caller must additionally limit total events/runtime and provide
cancellation: a free-running timer or repeated commands do not terminate
themselves.

## Owned register and pin integration

`peripheral_registers.hpp/.cpp` owns a deliberately narrow STM32-style polled
facade around this timing service. The integration declares fixed 10 MHz TIM2,
80 MHz SPI1 input and 8 MHz I2C1 input clocks rather than inferring RCC/PLL
state. Its Renode CPU cadence is a separate functional 1 us per instruction;
sub-instruction peripheral events keep the exact integer-nanosecond schedule
derived above.

The only admitted routes are PA0 AF1 for TIM2 channel 1, PA5/PA6/PA7 AF5 for
SPI1 SCK/MISO/MOSI, and open-drain PB6/PB7 AF4 for I2C1 SCL/SDA. GPIOA--GPIOI
configuration/output registers and physical input latches are owned by the
facade. ODR does not self-echo into IDR. SPI and I2C are bounded single-byte
polled paths: MISO/SDA samples supply returned bytes and the observed I2C ninth
bit supplies ACK/NACK. The transport never inserts a successful target.

RCC programming, APB reset, reset propagation, IRQ, DMA and other pin routes
are rejected in this mode. The older instruction-boundary GPIO mode retains
its separately evidenced DMA2 subset; it is not part of this register facade.
See [ADR 0119](../adr/0119-owned-native-peripheral-mmio-and-pads.md) for the
integration decision and complete scope boundary. Full RM0090/manual and
physical-pad qualification remain pending.

## Executed independent verification

`tests/cpp/test_spikes_peripheral_timing.cpp` uses literal enumerated PWM
edges, explicit MOSI/MISO bit arrays and a separate wire/pull-up harness.
The harness is not an I2C device model and does not validate a real target.
It checks:

- 400 ns versus 300 ns recurrence, compare timing, zero/full duty and ARR=0.
- SPI edges every 5 ns beginning at a non-10-ns-aligned epoch; exact
  transmitted bit order and receiver-derived `0x59`; final clock completion.
- I2C START/repeated START/STOP, nine-clock ACK/NACK, receiver-derived
  `0x93` and `0x12`, controller ACK/NACK drive modes and a 3 ns stretch.
- Missing acknowledgement barriers, invalid sample masks, unread-data
  protection, nonrepresentable clocks, unsupported rate, overflow,
  reversed time, occupied SDA and bounded stretch timeout.
- Concurrent timer/SPI events, including equal timestamps without merging.

`tests/cpp/test_spikes_peripheral_registers.cpp` separately checks supported
reset snapshots, strict mode/width masks, `ARR+1`, CNT/UIF, SPI status and
receiver bytes, physical I2C ACK/NACK and single-byte receive, GPIO IDR/ODR
separation, BSRR behavior, and transactional rejection across unresolved
electrical barriers.

On 2026-10-20 the standalone MSVC x64 C++20 `/W4` compilation and executable
passed. Reproduce from a Visual Studio developer shell:

```powershell
cl /nologo /std:c++20 /EHsc /W4 /I src src/spikes/peripheral_timing.cpp tests/cpp/test_spikes_peripheral_timing.cpp /Fe:.tmp/test_spikes_peripheral_timing.exe /Fo:.tmp/
& .tmp/test_spikes_peripheral_timing.exe
```

Integer timestamps and byte values use exact assertions, not adjustable
tolerances. These are synthetic behavioral verification results. Physical
validation, calibrated receiver/pad parameters, MCU register breadth,
broader firmware integration and knowledgeable human review remain separate.

The bounded live Renode suite later passed four tests in 61.551 s: at least
five firmware TIM2 rises over 27 instructions with 400 ns recurrence; SPI1
loopback `0xa5` over 18 instructions and eight receiver barriers; an I2C1
no-target NACK setting `AF` over 180 instructions; and a native ABI timer/
barrier check. The fixture retains a strict one-retired-instruction guard and
places 32 NOPs before its terminal idle branch because the functional emulator
can skip that branch. This is execution evidence for the bounded adapter, not
cycle-accurate silicon, vendor-pad validation or physical qualification.
