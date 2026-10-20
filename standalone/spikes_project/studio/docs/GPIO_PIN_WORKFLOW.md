# Electrical pins and timestamped firmware coupling

## Owned fixed-clock PWM, SPI and I2C (experimental)

Choose **Owned PWM / SPI / I2C — fixed-clock test profile** only for the
admitted STM32F407 target. This mode replaces selected emulator MMIO blocks
with SPIKE-owned TIM2, SPI1, I2C1 and GPIO state, then routes their timed events
through the same finite native pads used by the circuit. It is a bounded test
profile, not a general STM32 HAL or whole-MCU model.

1. Open **Electrical pin properties...** and connect every used pad to explicit
   signal, VDD and VSS nets. Leave output state under **firmware** control.
2. Select the owned fixed-clock profile. Use a non-UIC transient and a reporting
   interval on a whole 1 us boundary. Each report contains 1 to 1000 functional
   CPU instructions; this cadence is not a silicon cycle model.
3. Configure only the supported routes in firmware: PA0 AF1 for TIM2 channel 1;
   PA5/PA6/PA7 AF5 for SPI1 SCK/MISO/MOSI; and PB6/PB7 AF4 for I2C1 SCL/SDA.
   Both I2C pins must select open-drain output type.
4. Run with the circuit. At each timed receiver barrier SPIKE samples the
   accepted electrical **left limit before** applying that event's outputs.
   The saved provenance records the fixed clocks, functional CPU cadence,
   peripheral events and sampled receiver masks.
5. On an unsupported MMIO bit, pin route, unknown receiver, event overflow or
   transport error, restart firmware and plant together. The emulator process
   cannot be rolled back with a native electrical checkpoint.

The clocks are fixed at 10 MHz TIM2 input, 80 MHz SPI1 input and 8 MHz I2C1
input. All RCC writes are rejected, including clock enables/gates and resets;
the profile does not implement their lifecycle. TIM2 is edge-aligned PWM1 channel 1.
SPI1 is an eight-bit MSB-first master-mode-0, software-NSS-high, single-byte
polled path. I2C1 is standard-mode, polled and single-byte receive only. ACK,
NACK and received bits come from the physical finite-pad receivers: a missing
target produces NACK/`AF`, never a synthetic success or invented byte.

RCC reconfiguration, APB peripheral reset, reset propagation, IRQ, DMA,
preload/center/down-counting, SPI FIFO/overrun behavior, I2C target mode,
autonomous target devices and other alternate-function routes are rejected.
The DMA2 subset described under instruction-boundary feedback below belongs to
that older mode only. Generic pad strengths, pulls, thresholds and parasitics
remain user-supplied and unqualified.

The bounded live suite passed four tests: 400 ns firmware PWM recurrence,
physical SPI loopback `0xa5` across eight receiver barriers, an actual no-target
I2C NACK setting `AF`, and native ABI timer/barrier behavior. These are software
execution checks, not vendor-pad characterization, physical timing compliance,
SI/PI qualification or knowledgeable human review. See
[ADR 0119](../../../../docs/adr/0119-owned-native-peripheral-mmio-and-pads.md)
and the [timing evidence](../../../../docs/validation/NATIVE_PERIPHERAL_TIMING_20261020.md).

## Instruction-boundary feedback (experimental)

Choose **Instruction feedback — experimental** to refresh electrical receiver
inputs before every native CPU instruction rather than hold them over a long
lookahead interval. The owned C++ plant catches up before another instruction
executes. Reporting steps must be multiples of 10 ns, from 10 ns to 10 us.
The firmware interval field must still be an integer multiple of the reporting
step. This mode is much slower than free-running emulation and stops after
100,000 instructions; it is for bounded development tests, not real-time runs.
Pause/stop are cooperative between aligned CPU/plant steps.
Manual source edits drive the next electrical integration interval. They are
visible to firmware at the next accepted instruction boundary (10 ns later),
not as an unsolved instantaneous right-limit value at the edit timestamp.
Control-event records include that earliest input-observation timestamp.

Reset/input/GPIO output modes and the explicitly tested STM32 DMA2 stream0
immediate SRAM-word burst to captured GPIO BSRR are admitted. Native output
hooks retain transitions even when the ending register value is unchanged.
Two DMA transitions at the same emulator timestamp have zero modeled pulse
width: this does not establish physical DMA timing or SI bandwidth.
Alternate-function PWM/SPI/I2C pin routing, triggered/circular DMA, reset,
WFI and Nordic PPI/GPIOTE/peripheral pin ownership are not admitted. Peripheral
use that could invalidate GPIO ownership stops rather than inventing edges.

Use `nrf52840_gpio_only_echo.bin` from the bundled controller firmware examples
for GPIO feedback tests. The older UART echo firmware initializes an unsupported
peripheral and must not be used in this mode. Asynchronous input crossings
inside a CPU instruction are not delivered; this is instruction-boundary
sampling, not an unrestricted continuous-time MCU model. Use small electrical
timesteps and assess convergence for ringing. Generic pad profiles remain
unqualified. On a coupled failure restart firmware and plant together; restoring
only a native checkpoint cannot undo executed CPU instructions.

The older modes below keep their saved semantics for compatibility.

Open firmware emulation from a placed supported controller board, then choose
**Electrical pin properties…**. Opening this editor does not execute firmware.

1. Enable each GPIO you intend to connect. Assign its signal, VDD and VSS nets
   from the circuit. Physical labels/GPIO identities are read-only; internal
   pulls are not substitutes for actual supply and return connections.
2. Select a pin to edit its labeled **Drive**, **Pulls**, **Parasitics**,
   **Receiver** and **Clamps** groups. Engineering notation such as `50k`, `5n`
   and `2p` is accepted; units are shown beside the field.
3. Leave output and pull state sources on **firmware** to follow decoded
   registers. **Static** is an explicit circuit-only override, not an emulator
   register write. Finite strong/weak drive resistance is user-supplied, not
   guessed from a drive/speed register.
4. Apply saves the board's settings as one undoable project transaction.
   Cancel leaves it unchanged. Save/reopen preserves the settings and mode.
5. In **Circuit coupling**, select **Native electrical — sampled** or
   **Timestamped software GPIO — held inputs**. Legacy ideal DI/DO is separate
   and is never substituted automatically when an electrical mode fails.
6. Inspect the exact firmware image and approve its hash and reviewed runtime.
   Set the firmware interval; then use **Run with circuit** and the main
   Pause/Resume/Stop controls. Plot the generated `.io_pad` branch currents and
   powers alongside the circuit node voltages.

Timestamped mode captures software GPIO writes at virtual instruction-start
times and splits the owned C++ solve at those times. It retains edge-time
accepted points in the rolling result buffer, so a pulse wholly inside a
reporting interval can affect and appear in the result. Between-edge ringing
still needs a suitable integration/reporting step.

Inputs are held at the start of a bounded lookahead interval; this is not
event-synchronous closed-loop CPU/analog execution. The interval must be an
integer multiple of the reporting step, at most 1 ms; reporting steps must be
integer nanoseconds. It supports at most 32 GPIOs and 256 changed records per
interval. Exceeding a bound stops rather than dropping events. Single-instruction
blocks trade performance for timestamp fidelity.

Use a non-UIC transient with a valid initial operating point. Reset
alternate-function/analog pins and unsupported peripheral-owned activity are
rejected. PWM, DMA, GPIOTE/PPI and reset coupling are not available here. Neither
mode includes manufacturer-calibrated pads, MCU power/brownout, metastability,
physical SI/PI qualification or hard-real-time/HIL certification. Firmware still
runs with user permissions; process isolation is not a hostile-code sandbox.

See [native electrical details](native-electrical-pads.md) for sign conventions,
profile assumptions, event endpoint semantics and remaining qualification gates.
