<!-- SPDX-License-Identifier: Apache-2.0 -->
# Bidirectional GPIO bus coupling: independent method and acceptance contract

Date: 2026-10-20. Status: independently derived design and proposed verification,
not an executed qualification report. This record was authored separately from
the transport and integration implementation. The implementation owner must
append exact executed evidence before claiming an acceptance row passed.
Knowledgeable human numerical review remains required before public release.

## Scope and evidence boundary

The intended observable is closed-loop firmware behavior responding to voltages
of finite electrical pads, together with pin/rail voltage, current, threshold
crossing time, and passive-network energy. C++ owns circuit integration and
numerical receiver/event localization; Python owns process transport and
orchestration. Renode remains a separately installed instruction emulator.

Source inspection on this date found:

- `standalone/spikes_project/studio/python/spikes_studio/firmware_timestamped.py`
  runs firmware ahead with inputs held at interval start, then schedules actual
  captured software-GPIO writes. Its own provenance excludes continuous input
  coupling and peripheral edges. Output timestamps do not remove input lag.
- `firmware_electrical.py` implements a different sampled endpoint contract,
  not an instruction/event-synchronous method.
- `src/spikes/io_pad_events.cpp` advances under the old pad configuration to an
  edge before applying the new configuration. Its checkpoint restores circuit,
  pad bindings and pending events, not an external emulator process.
- `src/spikes/io_pad.cpp` classifies the die voltage using rail-relative
  thresholds and prior-state hysteresis. It does not localize roots.

Keep these existing contracts separate from the new contract below. A smaller
held-input interval is convergence evidence for a sampled approximation, not
proof of instruction/event synchronization.

Three example categories must stay distinct:

1. An original host-side functional protocol controller attached to finite
   pads verifies circuit/protocol integration; it is not MCU firmware execution.
2. An original binary executed by Renode that bit-bangs GPIO verifies that
   binary's instruction-level feedback through admitted pads.
3. An actual emulated SPI/I2C peripheral needs independently verified alternate
   function routing, input sampling and output-event timing. Neither category
   1 nor 2 establishes category 3.

These are lumped, generic, experimental models. No vendor pad fit, package/PCB
extraction, distributed transmission-line accuracy, metastability, EMI,
cycle-accurate silicon execution or physical SI/PI qualification is established.

## Reviewed primary-source ledger

Access and section review date for all entries: 2026-10-20. Review concerns
published method/documentation only; no upstream implementation source, test
fixture, example program, figure or prose was copied.

| Source/version and locator | Actually reviewed portion | Supported source fact and limit |
| --- | --- | --- |
| Ho, Ruehli and Brennan, *The Modified Nodal Approach to Network Analysis*, IEEE TCAS 22(6), 1975, [DOI 10.1109/TCS.1975.1084079](https://doi.org/10.1109/TCS.1975.1084079), [author-uploaded paper mirror](https://spinningnumbers.org/assets/MNA75.pdf) | Section II, printed pp. 504-505, equations (1)-(3) and accompanying text | KCL nodal equations augmented by selected branch currents and constitutive equations; capacitor histories enter time-discrete equations. This is a formulation foundation, not proof of the proposed scheduling algorithm. |
| Antmicro/Renode, [Time framework](https://renode.readthedocs.io/en/latest/advanced/time_framework.html), rolling documentation, no immutable revision stated | Time/performance units, synchronization, configuration, pausing versus halting | Integer-nanosecond virtual-time resolution, MIPS-based CPU performance, quantum synchronization. A small quantum does not itself prove callback order or cycle accuracy. Record actual installed runtime version separately. |
| Antmicro/Renode, [Basic execution control](https://renode.readthedocs.io/en/latest/basic/control.html), rolling documentation | Instruction stepping; blocking versus non-blocking stepping | Blocking stepping stops after an instruction; non-blocking mode permits time progression between steps. This does not establish the exact time of every peripheral input read. |
| Antmicro/Renode, [External control client](https://renode.readthedocs.io/en/latest/api-description/external-control.html), rolling documentation | GPIO get/set and GPIO state-change callback API entries | Public APIs expose Boolean GPIO state and callbacks. They do not by themselves establish a continuously synchronized electrical boundary. |
| STMicroelectronics, [AN4899, *Guidelines for GPIO hardware settings and low-power consumption on STM32 MCUs*](https://www.st.com/resource/en/application_note/an4899-stm32-microcontroller-gpio-hardware-settings-and-lowpower-consumption-stmicroelectronics.pdf), Rev. 4, 21 May 2026 | Sections 3, 4.3.2-4.3.4, printed pp. 9, 13-14; revision history p. 32 | Output and alternate-function paths differ; open-drain releases its pull-down for high, and digital input state is sampled separately. Device-specific manuals/datasheets remain necessary; no generic resistance, threshold or clock timing is inferred for a named MCU. |
| NXP, [UM10204, *I2C-bus specification and user manual*](https://www.nxp.com/docs/en/user-guide/UM10204.pdf), Rev. 7.0, 1 October 2021 | Sections 3.1.1-3.1.6, 3.1.9 and 7.1, printed pp. 8-10, 12, 50 | Open-drain/wired bus behavior, ACK on the ninth clock, clock stretching, and RC pull-up timing motivate bounded protocol tests. This is not a whole-standard conformance assessment. |

The attempted ST RM0090 PDF fetch did not return readable content and is not
claimed as reviewed. Named MCU register/peripheral semantics need the separate
transport evidence record; AN4899 is insufficient to qualify them.

## Independently derived electrical formulation

Use SI units: time s, voltage V, current A, resistance ohm, capacitance F,
inductance H, charge C, energy J. Choose branch current positive from terminal
`a` to `b`; branch voltage is `v_a-v_b`. Ground is a mathematical datum, while
VSS can be a circuit node and must not silently become ideal ground.

For each fixed pad-mode interval, KCL with

`i_R = (v_a-v_b)/R`,
`i_C = C*d(v_a-v_b)/dt`,
`v_a-v_b = L*di_L/dt`

gives the descriptor system `E*x' + G(u)*x = b(t)`, where `x` includes node
voltages and selected branch currents and `u` is the discrete pad-mode vector.
Positive finite resistances model driven, pull and released branches; releasing
an open-drain pin changes its conductance, never inserts a high logic source.
Explicit capacitances and inductances retain their state across mode events.
Optional nonlinear clamps need their own convergence and energy checks; the
linear analytical fixtures below disable them.

Admit a uniquely solvable, supported-index circuit with consistent initial
storage. Reject floating/singular networks, incompatible ideal-source/storage
constraints and non-finite/non-positive component values as appropriate.
Large off/on resistance ratios can worsen conditioning; retain actual residuals
and refinement error rather than assuming a small residual proves accuracy.

With passive RLC branches, stored energy is

`W = sum(C*v_C^2/2) + sum(L*i_L^2/2)`.

Multiplying branch equations by branch currents and summing KCL yields

`W(t1)-W(t0) = integral(P_supplied - sum(R*i_R^2), t0, t1)`.

Here source-delivered power is the negative of its absorbed branch power.
This includes actual VDD/VSS and pad-network branches. Input classification
is an information transfer and adds no independent voltage/current source.
Capacitance/inductance values are fixed; resistance switching alone must not
reset stored energy. Omitted MCU core supply current is not zero chip power:
report pad-network rail power only unless a separate explicit load exists.

## Causal event contract

Let `T` be committed virtual time and `u(T+)` the drive vector for the next
interval. Let `B` be the next firmware/peripheral input-observing or output-
changing boundary whose timing the transport can guarantee. The coordinator
must not execute beyond `B` before delivering inputs due at or before `B`.
An event-discovery run that has already executed a dependent read cannot be
repaired by changing its timestamp afterward.

The following ordering is a proposed deterministic digital abstraction:

1. From `T` to `B`, advance the plant with the old `u`, splitting at all known
   exogenous source/pad events and receiver crossings. Commit no CPU operation
   that could have consumed a not-yet-delivered input.
2. Deliver receiver transitions through `B`, including transitions exactly at
   `B`, before the input read at that boundary.
3. Execute the bounded CPU/peripheral operation using those inputs. Apply its
   output changes at its documented operation timestamp, not retroactively
   at the previous plant point.
4. Batch genuinely simultaneous drive changes, preserve capacitor voltage and
   inductor current, then obtain consistent right-limit algebraic values.
   Reclassify affected receivers before the next operation. Retain left-limit
   versus right-limit samples explicitly.

If instruction operations are defined at instruction start, advance the plant
to that start, supply inputs, execute that instruction and apply writes there;
then advance under the new mode to the next instruction start. If the backend
reports completion-time events, use that contract instead. Do not mix
start-stamped writes with completion-sampled inputs. Blocking single stepping
alone does not settle which interpretation is correct.

If a transport cannot stop before asynchronous peripheral sampling, it cannot
claim peripheral-synchronous coupling. A justified software-GPIO-only subset
may reject alternate functions, DMA, timers driving pins, reset and unsupported
sleep/wake progression. Maintain fail-closed capability flags.

### Thresholds, root isolation and integer time

For rail span `s=vdd-vss>0`, define event functions

`g_H(t)=v_die(t)-vss(t)-r_H*s(t)`,
`g_L(t)=v_die(t)-vss(t)-r_L*s(t)`, with `0<=r_L<r_H<=1`.

A low receiver changes high when `g_H>=0`; a high receiver changes low when
`g_L<=0`. Inside the band, retain a known previous state. Unknown initial
in-band or unpowered state must not be invented as a Boolean. Rails are dynamic,
so a threshold event can occur even if the pad voltage is stationary.

Localize the earliest relevant crossing, not just the end-of-report-grid value.
Checkpoint/reintegration with bracketed bisection is a possible native method
for isolated transverse roots. A bracket sign test alone can miss two crossings
of a ringing waveform; require a demonstrated isolation bound, sufficiently
bounded substeps with supporting derivative/frequency bounds, or restrict the
admitted interval to proven monotonic behavior. Tangency, near-zero slopes and
unbounded event chatter need rejection/refinement limits, not guessed events.
Threshold-time sensitivity is approximately `abs(delta_g/g')`; shallow crossings
can therefore have large timing error despite small voltage error.

If the backend's tick is `q=1 ns`, retain the continuous bracket `[a,b]` in the
result and deliver at the earliest backend tick proved not earlier than the
crossing: nominally `ceil(t_cross/q)*q`. Refine a bracket spanning a tick until
the delivery tick is resolved, or report the additional conservative delay.
Nearest-integer rounding can deliver future information early and is unsuitable
for an unqualified causal event claim. If several crossings occur within one
tick, record them and specify whether only the final sampled level is visible;
do not claim sub-nanosecond pulse/interrupt capture.

If timestamps collapse different instructions into one tick, preserve instruction
sequence as a separate ordering key. Do not group sequential instruction writes
as an atomic hardware register update. Conversely, a single multi-pin register
write is one atomic event, not a sequence of physical intermediate pad states.
Define an event key such as `(time_tick, operation_sequence, phase)`; never
reorder by pad name. Same-time fixed-point iterations need a finite limit and
explicit oscillation failure.

Reporting times are independent of electrical integration and event times.
Changing only the report grid must not change firmware reads or bus results.
Use integer clock identity at the process boundary; floating conversion to
seconds is only for integration. Retain the existing finite time horizon and
queue bounds. Avoid tolerance rules that merge distinct adjacent ticks.

### Recovery and resource limits

Plant checkpoint rollback is safe during root search only while firmware and
all other external participants remain frozen. A combined rollback requires
CPU registers, RAM, peripheral state, event queues, clocks, hooks, protocol
target state and circuit/receiver histories at the same boundary. Without that
capability, any error after firmware advancement terminates the coupled run;
restart a fresh process for replay. Do not continue from a plant-only restore.

Declare maximum run ticks, instructions, electrical steps, queued events,
root refinements, same-time iterations, wall time and cancellation latency.
Overflow, stale/unordered events, clock mismatch, timeout and unresolved input
must return a failed/incomplete result with the last committed boundary.

## Original analytical fixtures and pre-execution acceptance budgets

All values below are deliberately synthetic assumptions, not vendor data.
These are proposed tests, unrun by this document's author. Freeze actual input,
solver method, steps and budgets before accepting results; do not relax a
budget after seeing a failure. Use three halved steps and include off-grid
events. Basic waveform budgets are `10 uV + 0.1%*abs(reference)` for voltage
and `10 nA + 0.1%*abs(reference)` for current. Tighten when needed to resolve
the stated event-time budget. Software-level event order and decoded bytes
must match exactly; analog uncertainty cannot be hidden by a byte-only pass.

| Case / original independent oracle | Observable and proposed acceptance | Essential adversarial control |
| --- | --- | --- |
| GPIO polling feedback: finite RC node rises; firmware polls until its receiver changes, then drives a separate acknowledgement pad | First high read occurs at first admitted read boundary at/after delivered crossing; never before. Acknowledgement must follow that read in instruction order. Repeat with two RC values shifting the read decision. | Put crossing inside a former lookahead interval; a held-input implementation must produce a detectably different decision or delay. |
| Open-drain RC release: `Rp=2.2 kohm`, `C=100 pF`, `V=3.3 V`, discharge resistance `Ron=30 ohm`, stiff rails | `v_inf=V`, `tau=Rp*C`, `v(t)=V+(v0-V)*exp(-t/tau)`; use exact finite-resistance DC `v0=V*Ron/(Rp+Ron)`. Crossing `t_H=t0+tau*ln((V-v0)/(V-0.7V))`, approximately 262 ns after release. Error <= 2 ns at finest step, with convergence toward oracle. | Retain leakage/off conductance in the oracle if non-negligible; assert no instantaneous logic-high on release and no delivery before crossing. |
| Two open-drain drivers plus pull-up | Static KCL gives `v=V*Gp/(Gp+G1+G2)` with `Gp=1/Rp`, each `Gi` actual active/off conductance; check both released, either low, both low, and current sharing. | One driver's release while another sinks must not raise the received level. Missing pull-up yields unknown/rejection, not high. |
| Original I2C functional target, distinct from MCU peripheral emulation | Decode address/data and ninth-clock ACK from electrical receiver events. Target sinks SDA through finite Ron for ACK and SCL for a deliberate stretch. Controller sees SCL high only after stretch release plus RC rise; low/high timing and transaction order exact under the declared tick model. | Remove target ACK, stretch beyond timeout, change capacitance to cause a timing violation, and attempt illegal push-pull-high drive. No out-of-band Boolean ACK or byte injection into firmware. |
| Original SPI mode-0 bit-bang firmware or explicitly labelled functional controller, one-byte full-duplex target | MOSI sampled on receiver SCK rising edge; target changes MISO on falling edge with declared delay and finite drive. Predetermined complementary bytes and CS framing must decode exactly; retain sample setup/hold margins in ns. | Slow/loaded MISO so it crosses after sampling and assert the resulting bit failure. A direct byte-return API cannot satisfy this electrical test. Other modes/peripherals remain unclaimed. |
| Series RLC step to shunt C: `R=20 ohm`, `L=100 nH`, `C=100 pF`, `V=3.3 V`, zero initial storage | For `alpha=R/(2L)`, `w0=1/sqrt(LC)`, `wd=sqrt(w0^2-alpha^2)`, `v_C=V*[1-exp(-alpha*t)*(cos(wd*t)+alpha/wd*sin(wd*t))]`; `i=V/(L*wd)*exp(-alpha*t)*sin(wd*t)`. Compare V/I and peak time within 0.1 ns at finest step; refine e.g. 0.1, 0.05, 0.025 ns. | Multiple threshold crossings, sign-changing current and decay envelope must survive reporting-grid changes. Do not assume 1 ns firmware resolution implies 1 ns electrical accuracy. |
| PDN load step: stiff source through `Rs=0.5 ohm`, shunt `C=1 uF`, load increment `dI=20 mA` | With initial equilibrium, droop `dV=dI*Rs*(1-exp(-t/(Rs*C)))`: final 10 mV, initial slope `dI/C=20000 V/s`. Compare voltage and source/capacitor currents. Separate no-C case reaches the resistive drop immediately. | Repeat with explicit ESR: initial terminal drop is `dI*(Rs||ESR)`, final drop remains `dI*Rs`, time constant `(Rs+ESR)*C`. Reject treating an absent decap as a large artificial shunt. |
| Push-pull contention: high branch `Rh=40 ohm`, low branch `Rl=60 ohm`, `V=3.3 V` | Static current `I=V/(Rh+Rl)=33 mA`, bus voltage `V*Rl/(Rh+Rl)=1.98 V`; branch dissipation `I^2*R`. Swapping drive strengths changes bus voltage and current predictably. | Mid-band unknown or prior hysteresis is explicit; no last-writer-wins logic resolution. Check release removes contention but preserves capacitor voltage. |
| RLC/RC energy ledger over complete transition | Integrate supplied power, resistor loss and storage independently from retained native V/I; balance residual <= `max(1 pJ,0.2%*energy_scale)` on finest grid and improves under refinement. Define energy scale from absolute supplied energy, loss and storage change, not a nearly-zero net cancellation. | Check signs, both rails, floating-VSS translation, and capacitor state continuity at mode changes. No invented core-power contribution. |

For the ESR fixture, KCL at the rail node plus capacitor continuity gives
`dV(0+)=dI*Rs*ESR/(Rs+ESR)` and the sole relaxation pole
`-1/((Rs+ESR)*C)`. This avoids incorrectly assigning the full `dI*ESR`
instantaneous drop when the source impedance is finite.

For RC release with leakage, combine every fixed conductance into
`G=sum(Gk)`, `v_inf=sum(Gk*Vk)/G`, `tau=C/G`. Solve the same scalar equation;
there is no crossing if the target threshold lies beyond the reachable
equilibrium. Include moving-rail threshold tests separately from this
stiff-rail oracle.

Invariance checks: translate all voltages including both rails by a common
constant; reverse a probe's orientation and current sign together; repeat a
run with different reporting grids; batch/unbatch simultaneous writes without
changing event semantics. Unsupported physical input, event overflow and
post-CPU plant failure must fail rather than return an apparently valid trace.

## Executed evidence and promotion checklist

This author reviewed the listed local contracts and primary-source sections;
no new circuit or emulator test was executed for this document. No synthetic
test above constitutes measured validation.

Before promotion, append: source revision/diff identity, native-library and
Renode binary digests/version, original firmware source/compiler flags/image
digest, admitted pad/profile/circuit hashes, backend timing probe results,
method/steps/root tolerances, event trace/read decisions, numerical error and
refinement tables, failure controls, raw report/log paths, reviewer scope and
remaining unsupported cases. Preserve failed attempts as evidence.

Any implemented subset should advertise only its passed rows and exact
firmware/functional/peripheral category. Physical SI/PI qualification and
human release review stay open irrespective of software regression results.

## Development execution, 2026-10-20

The independent author's section above records derivation-only review. The
following is subsequent implementation execution, not measured validation.

`test_firmware_bus_examples.py`: six actual owned-C++ tests passed with Python
3.14.2 and native DLL SHA256
`8e0937c753a79815304bd4ebca15d6d62821b737a2ffb729f9448320acca4841`.
The SPI/I2C participants are explicitly synthetic controllers, not MCU binaries
or native peripheral models. The RLC/PDN tests use their declared native Radau
integration and original closed-form references, not firmware instruction steps.

| Check | Executed result |
| --- | --- |
| SPI finite-pad loopback / overloaded MISO | 0xA5 received; 1 uF overload receives 0 |
| I2C finite open-drain ACK/NACK / stretch | Both decisions pass; 2 us stretch; release-to-high 270 ns |
| RC sampled crossing at finest grid | 0.106 ns after analytic crossing; no root localization claim |
| RLC voltage error on three refining grids | 1.70e-6, 2.13e-7, 2.67e-8 V |
| RLC finest source-loss-storage residual | 5.66e-15 J |
| PDN voltage error on three refining grids | 3.24e-9, 4.07e-10, 5.10e-11 V |
| Output contention | 33 mA, 1.98 V and corresponding branch dissipation |

`test_firmware_synchronous.py`: six checks passed in 59.282 s, including a
trusted native nRF52840 GPIO-only image and native electrical plant. Across 160
instructions / 1600 ns, the input was driven low, high and low again. The output
followed within the tested 300 ns window after each change, rather than waiting
for the configured 1 us firmware interval. The 3.3 V source / 500 ohm generic
weak pad / 1 kohm load independently predicts 2.2 V high; the test checks this
value, not an unloaded 3.3 V. An initial test incorrectly expected >2.9 V and
failed at 2.1999999989 V; its oracle was corrected from the stated divider,
without altering solver behavior. Protocol tests also verify receiver delivery
before each instruction, unknown-state rejection, fractional-grid rejection,
stop-before-next-instruction and permanent failure latching after CPU advance.

The implementation is an instruction-boundary subset. It does not satisfy the
continuous root-localization requirements for asynchronous peripheral receivers
or arbitrarily fast ringing. Those remain unsupported. Native PWM timing is
not inferred from these tests; see the separate native backend evidence record.
Human numerical review and physical validation remain required before promotion.

Final review additionally found accumulated-double clock drift and ambiguous
manual-source visibility. Absolute integer instruction endpoints now determine
each native step increment; a 31,000-step regression passes. Manual controls
explicitly drive the next integration interval, with firmware visibility at the
next accepted boundary. Control events record the earliest input-observation
timestamp; a real native-C++ test observes `[low, low, high]` across the edit.
An independent rereview found no remaining actionable issue in that narrowed
contract. Final focused suite: 9 tests passed in 55.329 s, including the real
MCU/plant case; full Studio suite: 649 tests, 16 explicit optional skips, no
failures, 143.047 s. The 9 real transport tests covering all three targets were
run separately (61.162 s). These remain development verification results.
