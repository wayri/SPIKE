<!-- SPDX-License-Identifier: Apache-2.0 -->
# Native GPIO pad: independent formulation and bounded evidence

Review date: 2026-10-19. Status: experimental, supplied-parameter electrical
foundation. This record is independently authored by the review agent, separate
from the native composition implementation. It does not establish vendor pad
accuracy, IBIS conformance, instruction timing accuracy, or hardware safety.

## Claim, ownership and assumptions

The intended observable is the voltage and current response of a three-terminal
pad network (external signal, VDD, VSS) embedded in the native circuit. VDD and
VSS are actual circuit nodes, not numerical constants. The optional package
series R/L connects the external signal to a die-pad node. Four independent
finite resistive branches connect the die pad to its rails: strong high, strong
low, weak pull-up, weak pull-down. Each branch uses its active resistance when
enabled and its finite off resistance otherwise. Off leakage is therefore
**replaced**, not added in parallel, when that branch becomes active. There are
two inactive leakage branches per rail in the fully disabled state.

Each rail may have its own supplied, constant die-pad capacitance. Optional
generic static junctions connect die pad (anode) to VDD (cathode), and VSS
(anode) to die pad (cathode). These are not a vendor ESD protection model.
Package mutual coupling, distributed propagation, voltage-dependent charge,
thermal self-heating, breakdown, latch-up and damage are excluded.

All parameters are SI: V, A, ohm, F, H, s and K. Resistances must be positive and
finite; absent R/L/C is represented by topology omission, not an illegal zero
resistor or zero inductor. C and L must be nonnegative and finite. Generic diode
Is, emission coefficient and absolute temperature must be positive and finite.
Parameter limits do not imply process/voltage/temperature characterization.
The implementation additionally restricts each mutable resistance (and nonzero
package R) to `[1e-6,1e15]` ohm, requires weak drive R not below strong drive R,
and requires off R not below any active drive/pull R. Profile defaults are
synthetic numerical examples, not hardware characterization.

Renode is an optional, separately installed instruction/peripheral backend.
SPIKE owns this circuit composition and its native solve; it does not thereby
own or reproduce Renode's CPU implementation. A register value selects a
logical branch state, not a calibrated resistance, current limit or slew rate.
Receiver thresholds, alternate-function routing, GPIO sampling and instruction
event timing remain separately admitted contracts.

## Primary-source ledger and access extent

All source accesses below occurred on 2026-10-19. No external implementation
code, model data, figures, fixtures or prose were copied or adapted. The
equations, topology notation and analytical oracles below are original
derivations from the identified circuit laws and declared assumptions.

| Source and locator | Actually reviewed | Precise use and limits |
| --- | --- | --- |
| Ho, Ruehli and Brennan, *The Modified Nodal Approach to Network Analysis*, IEEE TCAS 22(6), 1975, DOI [10.1109/TCS.1975.1084079](https://doi.org/10.1109/TCS.1975.1084079); [university-hosted paper](https://web.engr.oregonstate.edu/~karti/ece521/mna.pdf) | Section II, printed pp. 504-505, equations (1)-(2) and associated discussion of KCL and added branch-current unknowns | Foundation for the nodal/branch formulation. This paper supplies no GPIO device parameters; its example implementation and performance results are not reproduced. |
| IBIS Open Forum, *I/O Buffer Information Specification*, version 7.2, ratified 2023-01-27, [official specification](https://ibis.org/~ibisorg/ver7.2/ver7_2.pdf) | Section 2 p. 11; section 6.1 pp. 60-62; buffer I-V keyword discussion pp. 89-90 (printed page numbers) | Architecture/scope guidance only: distinguish driver paths, rail-referenced die capacitance, clamp paths and open-sided outputs. This is neither an IBIS parser nor IBIS-conformant model. Supplied constant R/C and Shockley junctions do not replace characterized I-V/waveform tables. |
| MIT, *6.012 Microelectronic Devices and Circuits*, Spring 2009, Lecture 15, [official lecture](https://ocw.mit.edu/courses/6-012-microelectronic-devices-and-circuits-spring-2009/5075c569d72924227b6a36d40ca37898_MIT6_012S09_lec15.pdf) | Slides 9 and 12, ideal diode-current relation and thermal voltage | Static ideal-junction foundation. The supplied emission coefficient is a generic empirical extension; no claim is made that a real MCU clamp follows this law or these assumptions. |
| Nordic Semiconductor, nRF52840 Product Specification v1.1, [requested PDF](https://docs-be.nordicsemi.com/bundle/nRF52-Series-PS/raw/resource/enus/nRF52840_PS_v1.1.pdf); [official GPIO HTML](https://docs.nordicsemi.com/r/bundle/ps_nrf52840/page/gpio.html) | Exact PDF retrieval failed twice; historical infocenter URL redirected to the documentation home page. Official HTML GPIO introduction and register overview were accessible through indexed text; no version/page equivalence was established. | The reviewed HTML identifies separate direction, drive, pull and input-buffer controls. Exact v1.1 DRIVE encoding review remains open in this independent record; no register-derived electrical parameters are admitted. |

The nRF52840 v1.1 access gap must not be described as a completed version-bound
review. A separately recorded successful source review may close that narrow
gap without changing the generic circuit derivation.

## Independent equations and signs

Let `e`, `p`, `u`, `l` denote external pin, die pad, VDD and VSS potentials.
Let `j` flow from the external pin into the die pad through the series package
branch. The package equation, with omitted terms when their elements are absent,
is

```text
e - p = Rpkg*j + Lpkg*dj/dt.
```

With no series elements, `e=p`. Define `gu` and `gl` as the sums of the two
actual branch conductances to each rail, including off-state conductance.
Let `Cu` and `Cl` be separate die capacitances to the upper and lower rail.
For optional junction currents define

```text
D(v) = Is * (exp(v/a) - 1),  a = n*k*T/q > 0.
Fu = gu*(p-u) + Cu*d(p-u)/dt + Du(p-u).
Fl = gl*(p-l) + Cl*d(p-l)/dt - Dl(l-p).
die-pad KCL: j = Fu + Fl.
```

`Fu` and `Fl` are positive from die pad toward their respective rail. Terminal
currents are all positive **into** the owned pad network:

```text
Ipin = j;  Ivdd = -Fu;  Ivss = -Fl;
Ipin + Ivdd + Ivss = 0.
```

Negative `Ivdd` denotes injection back into the supply. A downstream current
probe must not silently reverse this convention. Its supply-source current may
have the opposite native branch orientation and needs an explicit conversion.
The terminal identity includes displacement current. Reporting only strong
driver current is not reporting total supply current.

In particular, the pad displacement contribution is

```text
(Cu+Cl)*dp/dt - Cu*du/dt - Cl*dl/dt.
```

Replacing `Cu` by extra capacitance to VSS loses the `-Cu*du/dt` forcing term
and gives incorrect supply injection. Moving capacitance must never reset its
stored charge. Total capacitance and separately specified split capacitances
must not be counted twice. With fixed rails the capacitive node time constant
depends on `Cu+Cl`; that special case cannot verify rail-current partition.

For incidence vector `a` (+1 at branch start, -1 at branch end), each resistor
adds `g*a*a^T` to the nodal conductance matrix and each capacitor adds
`C*a*a^T` to the charge matrix. A series inductor introduces its own current
unknown and branch equation. The resulting linear intervals have the MNA form
`E*x' + G*x = b`. Diodes add a nonlinear nodal residual and tangent
`gD = Is*exp(v/a)/a >= 0`. Their opposite endpoint stamps must be equal and
opposite. This composition uses existing primitives, not an independent pad
time integrator.

The existing generic diode primitive uses a C1 linear continuation beyond its
exponential argument cap (`src/spikes/dc_solver.cpp`, `diode_point`). Beyond
that cap the computed law is deliberately not Shockley. Overflow prevention is
not physical clamp validation; tests or results entering that regime require
an explicit numerical/model warning or an excluded validity envelope.

## Runtime modes and energy

Output enable gates only the strong paths. Weak pull control is independent.
In the API, strong/weak drive level selects a user-supplied output resistance
pair; it is distinct from the separately controlled pull-up/pull-down. The
logical table below uses low/high requests; the native API represents the
inactive side of open-drain/open-source with explicit `released` state and
represents disabled output with input/released state.

| Mode | Logic low | Logic high |
| --- | --- | --- |
| Push-pull, output enabled | Strong low active; strong high off | Strong high active; strong low off |
| Open-drain, output enabled | Strong low active; strong high off | Both strong paths off |
| Open-source, output enabled | Both strong paths off | Strong high active; strong low off |
| Input/high-Z or output disabled | Both strong paths off | Both strong paths off |

High-Z means finite specified leakage, not disconnection of capacitance, weak
pulls or clamps. Two pads driving opposite values form an ordinary dissipative
contention network. No digital winner or ideal output-voltage override exists.

The stored energy in the pad is

```text
W = 0.5*Lpkg*j^2 + 0.5*Cu*(p-u)^2 + 0.5*Cl*(p-l)^2.
```

Multiplying each branch law by its voltage and summing KCL gives

```text
e*Ipin + u*Ivdd + l*Ivss = dW/dt + P_R + P_D,
P_R = Rpkg*j^2 + sum_over_four_branches(gb*(p-rail_b)^2) >= 0,
P_D = (p-u)*Du(p-u) + (l-p)*Dl(l-p) >= 0.
```

Passivity holds for the assumed positive R/L/C and monotone zero-crossing diode
law, including the existing monotone continuation. Supply rails provide the
energy delivered to a load: the driven pad is not a passive one-port if its
power terminals are hidden. Switching a positive resistor changes dissipation
without resetting capacitor charge or inductor flux. This approximation omits
gate-drive power and overlap/shoot-through during finite transistor switching;
it must not be used to predict total MCU supply consumption.

## Numerical admission and time resolution

Finite off resistance improves DC anchoring but does not cure a floating rail
island, inconsistent ideal source loop or ill-conditioned enormous resistance
ratio. Large `Roff/Ron` and `C/h` to conductance ratios require residual/scaling
checks. Preserve the parent solver's convergence failures, resource limits,
state rollback and supported integration-method gates. A clamp-enabled circuit
is nonlinear and cannot inherit linear-only method qualification.

For backward Euler, a capacitor contributes `C/h` conductance and its previous
voltage history; an inductor contributes its previous current history. The
discrete energy balance has additional nonnegative terms
`C*(delta_v)^2/2` and `L*(delta_j)^2/2` per step. Consequently a coarse BE step
may dissipate too much despite being stable and charge-conservative. Trapezoid,
BDF2 and Radau need their own supported-route evidence; this document does not
extend those methods' existing qualification.

Changes in drive state must land on an electrical event boundary. Sampled
firmware batching can miss a complete pulse or delay a transition by one batch.
Making only the electrical time step smaller cannot recover a missing firmware
event. Demonstrate event transport, maximum timestamp error and independent
halving of both firmware quantum and electrical step before timing/SI claims.
RC slew from an abrupt conductance change is load-dependent, not characterized
internal slew. Shared return impedance and actual PDN connectivity are required
to study ground bounce, supply droop or simultaneous switching.

## Independent acceptance oracles (declared before execution)

These are planned tests, not executed claims. Synthetic values are original
fixtures, not Nordic or IBIS model data. Where an inactive branch remains finite,
include its conductance in the oracle; ignoring it is permitted only after its
error bound is shown to be below the stated tolerance.

DC voltage budget: `1e-9 V + 1e-8*abs(reference)`; DC current budget:
`1e-12 A + 1e-8*abs(reference)`. Terminal KCL budget:
`1e-12 A + 1e-8*max(abs(Ipin),abs(Ivdd),abs(Ivss))`.

| Case | Independent observable/oracle | Acceptance and refinement |
| --- | --- | --- |
| DC load divider | With fixed rails and total pad conductances `gu,gl`, external load `RL` to VSS, and no L/C/clamps: solve `j=(e-p)/Rp`, `j=gu*(p-u)+gl*(p-l)`, `(e-l)/RL=-j`; alternatively at `Rp=0`, `p=(gu*u+(gl+1/RL)*l)/(gu+gl+1/RL)` | DC budgets above; include nonzero VSS and both output states. |
| Contention | Two opposite active pads, fixed rails, no loading: series-chain result `I=(Vhigh-Vlow)/(Rhigh+Rpkg_high+Rpkg_low+Rlow)` in the negligible-leakage limit; verify any retained off conductance correction by independent nodal equations | Both rail current signs and midpoint voltage meet DC budgets; reject zero/nonfinite resistances. |
| Open-drain release | After low-side release and with fixed rails: `G=gu+gl+Gexternal`, `tau=(Cu+Cl)/G`, `p_inf=(gu*u+gl*l+Gexternal*Vexternal)/G`, `p(t)=p_inf+(p0-p_inf)*exp(-t/tau)` | At `h=tau/200`, BE endpoint error <= 0.005 of nonzero full-scale excursion. Runs with `h=tau/100,tau/200,tau/400` must decrease errors; ratios 1.8-2.2 at `t=tau` unless roundoff-limited. Preserve charge across release. |
| Series RL turn-on | Zero shunt C; fixed active resistive path and load: `j(t)=j_inf+(j0-j_inf)*exp(-t*Rtotal/Lpkg)` | Same BE normalized error/refinement budget; verify nonzero initial current preservation and package R included in `Rtotal`. |
| Finite supply impedance | Source `Vs` through `Rs` feeds actual VDD; high drive `Rh` feeds `RL` to VSS; negligible leakage gives `I=(Vs-VSS)/(Rs+Rh+Rp+RL)`, `VDD=Vs-I*Rs` | DC budgets; a clamped ideal VDD would fail droop oracle. Add a second simultaneous pad and compare independent coupled linear equations. |
| Split-cap rail forcing | Fix pad and VSS while VDD ramps with slope `s`: pure upper capacitor gives `Ivdd=Cu*s`, `Ipin=-Cu*s`, `Ivss=0`; separately ramp VSS and exchange roles | `1e-12 A + 1e-7*abs(reference)` after ramp corners; nonzero Cu and Cl separately. Check state continuity when drive mode changes. |
| Generic clamps | Current-limited upper overvoltage sends positive current pad->VDD; lower undervoltage sends positive current VSS->pad. At known junction current `I`, independent inverse `v=n*k*T/q*log1p(I/Is)` | Voltage `1e-7 V + 1e-6*abs(reference)` below exponential continuation; KCL budget above and nonnegative junction power. Include in-rail negligible-current case. |
| Whole-network work | For BE, source work on each step equals stored-energy increment + endpoint Joule/diode heat + discrete C/L dissipation terms | Residual <= `1e-15 J + 1e-7*max(abs(source work),abs(energy change),heat)` for finite well-scaled synthetic fixture; include both moving rails and package L. |
| Invalid/state cases | NaN/inf/negative parameters, invalid enum, missing/colliding identity, failed update, unsupported integration route | Fail closed without partial pad state change; maintain unrelated network components. |

Current/source attribution and initial conditions must be bound to every retained
result. For all transient comparisons use elapsed time since the actual event,
not an assumed sample index. A settled DC solution is not necessarily the desired
transient initial state.

## Executed evidence and review gates

At initial authorship, this independent agent has executed **no numerical pad
tests**. Implementation/source revision, native binary digest, fixture revision,
commands, outputs, actual errors and pass/fail fields are pending integration.
The acceptance table is a predeclared plan and must not be promoted wholesale
when only a subset is run. Retain failed evidence and identify unrun cases.

Source inspection of the existing generic diode primitive established the
continuation limitation above. Independent inspection of `src/spikes/io_pad.*`,
`tests/cpp/test_spikes_io_pad.cpp` and the session resistor setter found the
specified rail endpoints, capacitor split, clamp orientations, package-series
placement, state conductances and independent pull branches consistent with
this derivation. This was source review, not numerical execution. Initial test
coverage was missing moving-rail displacement, numerical package-L and enabled
clamp oracles; these findings were sent to the implementation owner.

The initial public C++ binding is mutable and its four resistor updates are
sequential. A wrong-session binding or mutated ID can fail after a prior setter
has succeeded; unchanged state also assumes the configuration has not been
mutated. These are explicit review findings, not accepted atomic-update
evidence. Encapsulation/session ownership or complete preflight is required
before claiming fail-closed updates. A later correction needs re-review.

The subsequent root integration source review covered `src/spikes/c_api.*`,
`python/spikes/native_io_pad.py`, Studio `firmware_electrical.py`, its
`FirmwareSession.pad_configuration` transport, and the `run_control.py`
configuration hook. The C ABI stores private pad bindings with each circuit
snapshot, copies them into a new session, and checkpoints/restores the state
cache with owner-token checks. This resolves cross-session binding substitution
for that public ABI; it does not make arbitrary direct C++ binding mutation
safe. Frozen Python profiles correctly express immutable run parameters.
The hook creates native branches before session construction and records their
currents, without adding an ideal pad source. Receiver sampling uses die-pad
voltage and actual rail voltages. The native receiver uses supplied threshold
ratios and retains known state in the hysteresis band; unknown initial state
and nonpositive rail span remain unknown rather than inventing a binary level.

Integration findings sent to the owner: clear receiver history when its input
buffer is disabled so later re-enabling in the dead band does not reuse stale
state; reject unimplemented nRF52840 P1.16-P1.31 pins; and guard the firmware/
electrical clock relationship against repeat callbacks or one-sided restore.
The normal run loop invokes the controller once before each accepted plant
step; electrical failure stops and closes firmware instead of retrying after
an unmatched firmware advance. A combined electrical checkpoint is **not** a
Renode checkpoint or a complete coupled-system rollback.

The bridge reports endpoint-sampled register states and explicitly omits
intra-quantum GPIO edges. Feedback sampled at plant time `t` drives the backend's
next catch-up interval; this is an explicit sampled coupling approximation,
not event-synchronous causality or cycle accuracy. Generic Schmitt memory is
not metastability, input-buffer delay, brownout behavior, or vendor hysteresis
validation. A strictly positive rail span alone does not establish valid MCU
operating voltage. Strong-driver and capacitor branch probes permit current
accounting, but no aggregated pad terminal-current export was established by
this source review. No live Renode electrical-loop execution was performed by
this reviewer.

Final integration re-review (source and test code only): the receiver history
is now cleared on both pre-tick and post-tick disconnected states, and the
nRF52840 pin check rejects P1.16-P1.31. Corresponding tests in
`standalone/spikes_project/tests/python/test_firmware_electrical.py` exercise
disable/re-enable dead-band rejection and the P1.15/P1.16 boundary. These two
source findings are resolved. A clock alignment check also now rejects an
incorrect first boundary. Its initial floating-point tolerance needs one
further correction: repeated addition of a 100 us double step exceeds its
1e-12 s threshold at step 25705 (2.5705 s), despite correct scheduling. This
was reproduced by an independent arithmetic loop, not by executing the native
pad. Integer plant-step/firmware-tick matching is the recommended fixed-grid
check; preserve explicit rejection of duplicate ticks and one-sided restores.

The added `observe_io_pad`/C ABI/`observe_pad` export resolves the earlier lack
of aggregate terminal observations. Independent inspection confirmed the
lower-clamp sign reversal, inclusion of both capacitor displacement currents,
upper/lower current negation at rail terminals, and external-to-die package
current orientation. The seven-field C ABI and ctypes order agree. With no
package branch, external current is reconstructed from the die branch sum,
so its terminal-current-sum test is an accounting identity, not an independent
solver residual check. Existing branch KCL and moving-rail fixtures provide
separate numerical checks. Package-L and clamp-polarity fixtures are now present
in the native test source; their execution and measured errors remain the
integration owner's evidence. The new applied-resistance cache also fixes the
earlier same-state/no-op issue for changed C++ resistance values; arbitrary
mutable C++ branch identity misuse remains outside the safe public ABI.

Knowledgeable human numerical/device review before release remains required.
There are no admitted physical measurements, calibrated vendor parameter sets,
held-out temperature/voltage/load data, uncertainty bounds, receiver-validation
fixtures, IBIS parser tests, or board-level SI/PI qualification in this record.
Those gaps remain open even if every synthetic test passes.

## Root integration execution — 2026-10-19

The integration owner built the canonical root project in
`build-spikes-io-pad-20261019` using MSVC 19.51.36256, Release x64, C++20,
Eigen 3.4.0, portable-build mode and strict floating point. No installed binary
was replaced. The final `Release/spikes_c_api.dll` SHA256 is
`891211e317ca14282b778d29101b4021f3eb348f7be5f8c119e3a5e47ab2a889`.

Executed successfully:

- Seven CTest targets: `test_spikes_core`, `test_spikes_c_api`,
  `test_spikes_transient`, `test_spikes_transient_c_api`,
  `test_spikes_transient_session`, `test_spikes_io_pad`,
  `test_spikes_transient_session_c_api` (1.74 s combined).
- Twenty-five Python tests, no skips (28.424 s combined):
  `tests/python/test_spikes_native_io_pad.py`, Studio
  `test_firmware_electrical.py` and `test_firmware_pad_state.py`, with
  `SPIKES_TEST_FIRMWARE=1`. This includes actual approved Renode execution of
  the original nRF52840 echo image coupled to native finite pads. A loaded
  standard-drive output meets the 2.2 V divider oracle; writing PIN_CNF `0x60d`
  releases its open-drain output with internal pull-up and meets the
  `3.3/51 V` loaded pull-up oracle. These are synthetic profile checks, not
  manufacturer measurements. The test runtime uses the approved executable hash
  checked in `renode_process.py` and closes the emulator on completion.
- Continuous-run acquisition of generated pad branches, bounded capture,
  pause/resume, source control and worker cleanup, using mocked register
  transport but the real C++ plant. This test does not establish live-emulator
  throughput or electrical event timing.
- Native ownership/snapshot isolation, checkpoint state-cache restoration,
  protected generated branches, invalid state/profile rejection, receiver
  unknown/hysteresis behavior and all eight Nordic DRIVE register encodings.
- `scripts/check_architecture.py` and scoped whitespace checks.

The native pad test contains nine fixture functions covering DC pull dividers,
open-drain release, contention, real-rail droop, RC refinement/charge, invalid
construction, receiver levels, moving-VDD displacement and package-RL/clamp
response. It passes its coded tolerances. This does **not** execute every case
in the broader predeclared oracle table: combined whole-network energy auditing,
held-out physical device data and extended simultaneous-switching qualification
remain open. The exported standalone SDK CMake/export recipe was updated for
the new source/test; a complete standalone archive/package build was not run.

The clock-review finding above was corrected using integer tick/step identity
plus a time cross-check with accumulated-roundoff allowance. A regression at
step 25705 accepts ordinary double-addition drift and rejects a duplicate tick.
Input-disconnect history reset and the P1.15/P1.16 boundary tests also pass.
These are software checks; no reviewer has supplied the required human
numerical/device release approval. No GUI installation/update, hardware test,
manufacturer qualification, event-synchronous coupling or SI/PI certification
is implied by this execution record.
