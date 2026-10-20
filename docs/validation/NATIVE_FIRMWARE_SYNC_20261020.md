<!-- SPDX-License-Identifier: Apache-2.0 -->
# Native firmware instruction rendezvous - 20 October 2026

## Bounded claim

`firmware_sync_transport.py` and the original internal
`renode_sync_hook.py` add an experimental, blocking, one-instruction transport
to the separately installed Renode 1.17.0 process. Python transports native
digital state only; all electrical calculations remain in the native C++
plant. This is not cycle-accurate hardware, continuous-time pin coupling,
general peripheral emulation, or SI/PI qualification.

At a committed plant/firmware time `t`, the caller supplies receiver levels,
executes exactly one native instruction, receives GPIO events, advances the
native electrical plant to `t + 10 ns`, and only then supplies the next inputs.
The installed CPU is explicitly configured for 100 MIPS and one-instruction
translation blocks. Its blocking `Step(1)` reports exactly one retired
instruction and a 10 ns advance. `SyncTime()` runs on the native CPU thread
at block entry, not from the monitor thread. GPIO register reads therefore
see the supplied instruction-start levels; later firmware reads never run
ahead through a held-input acquisition window.

`step()` returns `start_ns`, `end_ns`, and ordered events in the existing pad
event schema. Native GPIO `AddStateChangedHook(Action[bool])` callbacks retain
output transitions. Additional instruction-boundary register observations
retain configuration changes; they do not substitute for native output
callbacks or claim to recover a hidden peripheral pulse. Equal timestamps
preserve native callback order.

## Sources and clean-room boundary

Reviewed on 2026-10-20:

- Renode official [Basic execution control](https://renode.readthedocs.io/en/latest/basic/control.html),
  instruction stepping and blocking/nonblocking sections: the current docs use
  a newer enum spelling. The installed **1.17.0** public monitor instead
  reports `ExecutionMode SingleStep` with blocking enabled through
  `emulation SingleStepBlocking true`. Those installed APIs were executed.
- Renode official [Using Python](https://renode.readthedocs.io/en/latest/basic/using-python.html),
  monitor context, CPU hooks and system-bus hooks: Python can call exposed CLR
  objects and install hooks. Installed public callable inspection returned
  `AddStateChangedHook(self: GPIO, hook: Action[bool])`.
- Renode official [Time framework](https://renode.readthedocs.io/en/latest/advanced/time_framework.html),
  time/performance units and pausing: virtual time uses integer nanoseconds;
  blocking CPU execution prevents uncontrolled time progress between steps.
- STMicroelectronics, **AN4013 Rev 14, February 2026**, sections 2.2 and 2.5,
  printed pages 12-17, [Introduction to timers for STM32 MCUs](https://www.st.com/resource/en/application_note/an4013-stm32-crossseries-timer-overview-stmicroelectronics.pdf):
  the timer time-base equation includes `PSC + 1` and `ARR + 1`; PWM1
  up-counting is active below the compare count. These facts supply the
  independent timer probe oracle below, not an implementation copied from ST.

The transport, fixture encoder, Thumb programs, test oracles and this prose
are original SPIKE material. No Renode implementation source, upstream test,
SDK example, or external firmware was inspected or adapted. Public runtime
introspection and black-box execution establish the observed API behavior.
The attempted direct RM0090 web retrieval exceeded the reader's document
size limit; this turn does not claim a fresh full RM0090 review. Existing
GPIO register-decoder provenance remains in `firmware_pad_state.py`.

## Admission, ownership and resource limits

- Three existing targets: STM32F407 Discovery, nRF52840 DK, Arduino Nano 33
  BLE. This does not broaden the supported MCU families.
- GPIO electrical configuration is decoded by the existing reviewed decoder.
  STM32 alternate-function and analog modes remain rejected.
- Nordic peripheral pin ownership is not inferred from GPIO `PIN_CNF`.
  Writes to GPIOTE, PPI, serial/audio peripherals and watchdog are rejected
  in this mode. Ordinary GPIO is admitted; native UART register capture in
  other execution modes does not establish routed UART-pad behavior here.
- The only admitted peripheral-origin output write is STM32 DMA2 stream 0,
  immediate memory-to-memory word transfers from bounded SRAM into the BSRR
  of a captured GPIO port: control value `0x5281`, source increment, fixed
  destination, count 1..event capacity. Other streams, source peripherals,
  circular/double-buffer/triggered transfers and DMA1 fail closed. This is
  an exact black-box runtime subset, not full DMA hardware qualification.
- No autonomous GPIO event with a timestamp different from the current
  instruction start is silently rounded or accepted. General timer-driven
  GPIO, PWM, reset and WFI remain unsupported. Unexpected instruction count,
  clock advance, lockup, malformed output or overflow closes the process.
- Maximum 32 unique pins, 256 callback/configuration records per instruction,
  and 100000 instructions per transport lifetime. The existing process
  command watchdog and output byte/line caps also apply. On failure there
  is no combined CPU/plant rollback: restart the coupled run.
- Inputs are discrete instruction-boundary feedback, not asynchronous
  continuous electrical observations. Analog input capture between
  instructions, subinstruction pad switching and hardware bus timing have
  not been validated.

## Executed acceptance evidence

The native runtime executable SHA-256 is
`67c2c21eb977181a50a19acbf582c4204d8177d2b4ae0bac4c3d3d51da7a7b4e`
(Renode 1.17.0, separately installed Windows runtime). No runtime files were
changed. Tests create and reap isolated test processes.

Original firmware fixtures in `test_firmware_sync_transport.py`:

| Fixture | SHA-256 | Independent observable |
| --- | --- | --- |
| `feedback_firmware()` | `a1805fb339a3312b74a25831581a8005d36f133c10f01fc6ed2dd2eae43c97dc` | Native STM32 input reads at 70 and 80 ns receive high then low after two distinct host injections |
| `dma_firmware()` | `49807ebec6943e01cce4e42297bca7e7f91d7f6cbc7128af36ee956d28f9ac35` | Native DMA emits high then low at 200 ns although the final ODR is zero |
| `nordic_feedback_firmware()` | `3870f97c45f2b301795b64f11cb3891e087a067d290f8a33851264fce620ef1d` | Same consecutive-read feedback on both nRF52840-based admitted targets |

The DMA high/low pair has **zero duration in this emulator**. Capturing both
callbacks proves event retention, not a finite-width pulse, DMA throughput,
physical pulse energy, or hardware timing.

The first native run passed seven tests in 41.318 seconds: consecutive native
reads, DMA event retention, unsupported DMA-control failure, instruction-budget
process cleanup, malformed-event rejection, atomic input-batch validation and
same-timestamp event retention. Reproduction command:

```powershell
$env:SPIKES_TEST_FIRMWARE='1'
python -m unittest discover -s standalone/spikes_project/tests/python -p test_firmware_sync_transport.py -v
```

After adding Nordic peripheral-owner guards, both Nordic target fixtures, and
DMA source/range/stream rejection cases, the same command passed **nine tests
in 61.162 seconds**, with no skips. The executed adapter SHA-256 was
`bb58dcf863580fbeda6bd542e9dab51b343b4e86f53d05b88d4c71af25893717`;
the internal hook SHA-256 was
`f42ce96f5def749d5a27d8e79bf3b0bb9a471ffc2cdf24a160e053ca731da0cc`.

Native test processes must currently run serially. Concurrent Renode console
startup produced an upstream `System.IO.IOException` on the shared
`AppData/Roaming/renode/history` file inside `AntShell.CommandHistory.Load`.
The process exited before the actual test. Renode 1.17.0 `--help` exposes no
dedicated history-file option; an isolated config path alone does not isolate
that history. No user history file was modified or deleted to work around it.

## Failed PWM qualification probe - preserved, not promoted

Using the stock STM32F407 platform and an original `B .` Thumb loop, queried
native `sysbus.timer2 Frequency`: **10000000 Hz**. Configured TIM2:

| Register address | Value | Intended field |
| --- | --- | --- |
| `0x40000028` | `0` | PSC |
| `0x4000002c` | `3` | ARR |
| `0x40000034` | `2` | CCR1 |
| `0x40000018` | `0x60` | CCMR1 PWM1 |
| `0x40000020` | `1` | CCER channel 1 enabled |
| `0x40000000` | `1` | CR1 up-counter enabled |

Attached a native `timer2.Connections[0].AddStateChangedHook` callback which
recorded its Boolean value and
`machine.ElapsedVirtualTime.TimeElapsed.TotalNanoseconds`. Executed 250
native `cpu.Step(1)` calls with the same one-instruction/block configuration
and CPU-thread `SyncTime()` entry hook. Final time was exactly **2500 ns**.
Observed channel edges began:

```text
high 300, low 500, high 600, low 800, high 900, low 1100,
high 1200, low 1400, high 1500, low 1700, high 1800, low 2000,
high 2100, low 2300, high 2400  [all times ns]
```

Independent oracle: a counter visiting 0,1,2,3 contains four 100 ns ticks;
`T = (PSC+1)*(ARR+1)/f = 400 ns`. The native steady rising-edge separation
was **300 ns**, not 400 ns. This discrepancy is material and unresolved.
No adjustment of ARR, fabricated edge timing or replacement waveform was
introduced to hide it. The callback alone also does not prove PA0 AF1 pin-mux
ownership. PWM and alternate-function routing therefore remain unavailable.

An earlier halted-CPU `RunFor(2 us)` probe delivered several timer changes
all stamped 2000 ns, demonstrating why a final snapshot or a shorter
acquisition quantum is not sufficient evidence for causal peripheral timing.
The single-instruction probe improved observability but did not resolve the
timer-model discrepancy. Human review and independent hardware/reference
qualification remain open.
