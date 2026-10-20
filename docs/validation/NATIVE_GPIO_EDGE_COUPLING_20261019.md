<!-- SPDX-License-Identifier: Apache-2.0 -->
# Timestamped native GPIO edges: independent coupling formulation

Review date: 2026-10-19. Status: experimental prescribed-edge coupling;
execution evidence pending integration. This note is independently authored
from the event-queue implementation. It extends, rather than replaces, the
[native finite-pad evidence](NATIVE_GPIO_PAD_20261019.md). Supplied pad
parameters remain uncalibrated. This is not MCU cycle-timing, IBIS, SI/PI,
closed-loop causality, or hardware qualification.

## Claim and ownership

The bounded claim is that every admitted backend timestamped pad-state change
is retained and applied to the owned finite-resistance MNA network at its
declared absolute virtual time, even when multiple opposite transitions lie
between two requested output samples. C++ owns electrical integration, stored
energy state and the pending-edge queue. Python transports validated events;
the optional instruction backend remains separately owned software.

An event selects the four existing strong/weak branch resistances. It does not
create an ideal voltage step at the pad, replace a capacitor voltage, change
an inductor current, or infer a physical transition slew. C/L topology and
parameters are fixed during this operation. Diode, rail, receiver and package
assumptions remain those of the finite-pad record. Time is seconds internally
for numerical integration and absolute integer nanoseconds at event admission;
electrical units are V, A, ohm, F, H, C, W and J.

## Primary sources actually reviewed

No external implementation source, model data, figures, examples or test
fixtures were used. The following source portions were read on 2026-10-19;
the equations and fixtures below are independently derived in project notation.

| Source and exact locator | Reviewed extent and source fact | Application boundary |
| --- | --- | --- |
| Ho, Ruehli and Brennan, *The Modified Nodal Approach to Network Analysis*, IEEE TCAS 22(6), June 1975, DOI [10.1109/TCS.1975.1084079](https://doi.org/10.1109/TCS.1975.1084079), [university-hosted paper](https://web.engr.oregonstate.edu/~karti/ece521/mna.pdf) | Section II, printed pp. 504-505, equations (1)-(3) and capacitor/inductor discussion: KCL plus additional branch-current equations, with time-history terms from storage constitutive relations. | Foundation for the independently formulated switched finite-R circuit; neither event ordering nor MCU timing is established by this paper. No implementation or example was reproduced. |
| Antmicro, *Renode documentation: Time framework*, official live documentation, page last updated 2026-10-13, [official page](https://renode.readthedocs.io/en/latest/advanced/time_framework.html) | Sections "Time and performance units", "Synchronization" and "Time domain": virtual-time resolution is 1 ns; configured CPU performance is expressed in MIPS; quanta organize synchronization; different time domains are not automatically comparable. | Supports distinguishing emulator time from hardware timing and requiring a common epoch/domain. This live documentation was not established as a frozen specification for the locally installed Renode version. No claim that peripheral callbacks have physical cycle accuracy follows. |

## Independent derivation

Let `m_k` be the complete pad mode on `[t_k,t_(k+1))`. With fixed branch
incidence and constant storage parameters, KCL and branch constitutive laws
give, on a linear interval,

```text
E*x'(t) + G(m_k)*x(t) = b(t).
q_C = C*(v_a-v_b),       i_C = dq_C/dt.
phi_L = L*i_L,          v_L = dphi_L/dt.
G_R(m) = sum_r [1/R_r(m)]*a_r*a_r^T.
```

Nonlinear static clamps add `f(x)` to the left side; their pre-existing
admission and solver limits are unchanged. Every selected resistance is
strictly positive and finite, so each resistive branch dissipates
`(v_a-v_b)^2/R >= 0`. Switching can change that instantaneous loss and rail
current but cannot itself inject a charge or flux impulse. Integrate the
storage equations over an interval shrinking around `t_k`. Provided the
admitted solution has bounded capacitor current and inductor voltage,

```text
q_C(t_k+) = q_C(t_k-),    phi_L(t_k+) = phi_L(t_k-).
```

Thus constant positive C and L preserve capacitor voltage differences and
inductor currents. This does NOT require all MNA unknowns to be continuous:
algebraic currents and unconstrained algebraic node voltages can jump.
Incompatible ideal-source/storage constraints or singular switched DAEs need
separate rejection/qualification; finite pad resistance does not cure every
singularity elsewhere in an arbitrary circuit. With unchanged C/L and bounded
storage states, stored energy `sum(C*v_C^2/2)+sum(L*i_L^2/2)` is continuous at
the mode change. Subsequent source work, dissipation and integration error
are distinct from this zero-duration continuity assertion.

For requested endpoint `T`, split at every event time in `(t_now,T]`.
Integrate the old mode to each edge, then apply its new resistances without
advancing time or resetting storage. Apply events at `t_now` before the first
positive-duration segment. Events after `T` remain pending. A reporting sample
is not an event grid and must not quantize, merge or discard distinct times.

At an edge exactly on `T`, an accepted solver point is the left-limit point
obtained with the old mode; the mode selected for the next interval is the
right-limit mode. Storage observations agree on both sides, but algebraic
current observations need an explicit left/right convention. Do not label a
cached left-limit branch current as a freshly solved right-limit current.
An event at time zero similarly does not invent an accepted electrical point.

## Discrete consistency, ordering and failure contract

For a constant scalar RC interval, backward Euler yields
`(C/h+G)*v_(n+1)=C*v_n/h+B`. Its positive denominator makes the update a
convex combination of `v_n` and `B/G`, with first-order global error on smooth
intervals. Event alignment removes timing smearing, not this discretization
error. Other integration methods retain their own documented assumptions.
Multistep or derivative history across a conductance jump is not smooth:
restart the relevant history while retaining physical storage state. Changing
resistance must invalidate stale factorization/history as required by the
existing native discontinuity mechanism. Do not initialize again from a new
DC operating point after an edge.

The queue contract must state and test all of the following:

- Timestamps are validated integer nanoseconds in a documented finite range;
  reject negative, fractional, boolean-as-integer, nonfinite, overflowed,
  wrong-domain and past timestamps at the relevant boundary. Do not silently
  round malformed transport values or wrap conversion to an unsigned ABI type.
- Integer event ordering and a monotone stable sequence number resolve equal
  timestamps. Distinct-pad updates at one instant receive no intermediate
  integration. Repeated updates of one pad at that instant use declared order,
  with the last complete state governing the next positive interval. This
  deterministic convention is not a model of physical races or sub-ns pulses.
- Converting absolute time to binary64 seconds must not collapse distinct
  admitted times or create zero/negative integration intervals. Cap the time
  domain or reject unrepresentable separation. Ordinary binary64 addition
  drift must not turn a valid current-boundary edge into a past event or
  permit a materially past event; specify a bounded clock alignment rule.
- Bound pending-event count, admitted batch size and work per advance; reject
  overflow before mutation rather than decimating events. Sorting and retained
  storage require at least explicit `O(N log N)` and `O(N)` accounting if that
  implementation is selected. Include backup/checkpoint storage in the bound.
- Validate complete pad identity/state before insertion. A failed batch must
  not enqueue a prefix. A failed outer advance must restore pre-call physical
  state, accepted time, mode caches and the entire pending queue, or expose an
  explicit terminal partial-progress contract instead of reporting success.
- Checkpoints bind to their creating session and capture queued states,
  event ordering, integration history, pad caches and clock state together.
  Restore must not replay consumed edges twice or lose future edges. Electrical
  rollback alone is not an instruction-backend or coupled-system checkpoint.

These are review requirements, not assertions that all paths have passed.
No unbounded recursive callback or zero-time event cascade is admitted by the
finite externally supplied queue. Any future autonomous feedback/event loop
requires a separate termination and causality contract.

## Predeclared independent verification

Use fixed rails `U=3.3 V`, `L=0 V`, two drive branches of active resistance
`10 kohm`, off resistance `1e12 ohm`, and two disabled weak branches each at
`1e12 ohm`. Set total rail-referenced die capacitance `C=1 nF`; omit package
and clamp elements for this linear oracle. Include all leakage conductances.
For any constant mode, define

```text
G_k = g_upper,k + g_lower,k
B_k = g_upper,k*U + g_lower,k*L
v_inf,k = B_k/G_k;       tau_k = C/G_k
F_k(d,v) = v_inf,k + (v-v_inf,k)*exp(-d/tau_k).
```

Start at the low-mode equilibrium. Queue high at `1237 ns` and low at
`1789 ns`. For any requested time, compose `F_k` in chronological order
using the actual elapsed duration in each mode. This continuous-time
exponential oracle does not duplicate the solver's finite-difference update.

| Case | Acceptance before execution |
| --- | --- |
| Both opposite edges inside one outer interval | With 1 us outer steps, both edges lie in `(1,2) us`; compare at 2 us and 10 us to the piecewise exponential. For BE, absolute error <= `0.005*U + 1e-12 V`. A final-low-only reduction must fail the 2 us comparison. |
| Refinement and non-grid timing | Repeat with 100, 50 and 25 ns outer steps; neither edge lies on any grid. Maximum voltage error over common requested times through 10 us must decrease, with finest error <= `0.001*U + 1e-12 V`. Ratios alone are not an order claim because event-aligned segment patterns vary. |
| No instantaneous storage reset | Stop exactly at a mode event, compare the capacitor voltage and any package-inductor current immediately before/after mode application; use `1e-12 V + 1e-10*abs(v)` and `1e-15 A + 1e-10*abs(i)`. Also run a nonzero-current RL fixture. Cached point equality alone is insufficient: subsequent decay must match the preserved-state analytic continuation. |
| Equal-time semantics | Two updates to one pad at the same timestamp produce no intervening integration and the last state controls subsequent evolution; swapping distinct-pad insertion order produces the same coupled result within solver tolerance. |
| Checkpoint replay | Checkpoint with both pending and already-consumed events; advance, restore, then replay. Accepted time, observable state, queue and modes agree. Include queue insertion after checkpoint and owner-token mismatch rejection. |
| Failure atomicity | Invalid state/identity and over-capacity batch leave queue/modes unchanged. Force solver failure after one internal segment and verify complete outer-call rollback, including already-applied events and time; preserve a failure diagnostic. |
| Timestamp rejection | Negative, fractional, bool, NaN/inf, overflow, past and unresolvable timestamps fail at the proper API boundary. Exercise time zero, endpoint events, nearby distinct ns values, non-grid current time and long-run floating-point clock drift. |

All rows above are planned, not executed by this independent reviewer.
Integrator-specific tolerances and method selection must be bound to retained
results. Record source revision, native binary hash, exact fixture/configuration,
commands, errors, diagnostics and failures before marking an individual row
passed. Full matrix tests, conservation checks, human review and physical
measurements must not be inferred from a smaller passing smoke test.

An independent arithmetic preflight (Python binary64, not a native solver
execution) compared the scalar BE recurrence with the continuous exponential
oracle. Maximum errors at the requested samples for outer steps 100, 50 and
25 ns were respectively `8.0419564e-4`, `4.1483853e-4` and `2.0995421e-4 V`.
For the 1 us outer grid, the exact 2 us voltage was `0.173523449770 V`
and the BE recurrence was `0.169063604136 V`. This checks that the declared
synthetic fixture and budgets discriminate a discarded pulse; it is not
implementation verification and does not replace executing the native tests.

## Initial source-review findings

Inspection of `src/spikes/io_pad_events.*` and its C ABI integration found a
65536-event bound, integer `(time_ns, sequence)` ordering, a `2^48 ns` timestamp
horizon and session-bound checkpoint copies of queue and pad bindings.
`2^48 ns` is approximately 3.26 days; binary64 seconds still distinguish
adjacent 1 ns event times at that horizon. The observed comparison tolerance
`max(1e-18, 8*epsilon*abs(t))` approaches 0.5 ns there and must not be confused
with a physical timing accuracy claim.

The initial review sent these concrete findings to the integration owner:

- The first `time <= end+tolerance(end)` test can admit an edge after the
  requested endpoint and advance the solver beyond that endpoint. A future
  event must not be consumed by an earlier request; arbitrary output steps
  need not lie on the integer-ns event grid.
- Initial C ABI advance did not restore earlier accepted internal segments,
  consumed edges or pad modes on later failure. Full outer rollback or a
  clearly terminal partial-progress contract is required.
- Native `step_index` counts internal `TransientSession.step` calls. The
  existing firmware/plant clock guard treated it as the outer output index;
  event splitting therefore requires explicit outer-index bookkeeping or a
  revised, equally strict time/duplicate-call guard.

These describe the initial source revision, not necessarily the final one.
Each correction requires re-review and executed regression evidence before
the corresponding finding is marked resolved. The accepted endpoint's
left-limit observation convention is intentional and must remain explicit.

Subsequent source-only re-review found that strict `time > end` exclusion
replaces the tolerance-expanded endpoint check, resolving the identified
future-edge overshoot in the inspected source. Eventful multi-segment advance
now saves the native checkpoint, pad bindings and event queue and restores
them on exception or failed segment; the exception preserves a failure message
through the C ABI. No events are inserted during advance, so its sequence
counter is unchanged. Python `schedule_pad_edge` rejects bool, fractional,
negative and above-horizon timestamps before ABI conversion. These are source
corrections, not executed rollback/timestamp test evidence. The outer-index
integration finding remains open in this review snapshot.

## Timestamped-controller follow-up review

The separate `firmware_timestamped.py` controller now avoids the sampled
controller's `step_index` convention. It derives the electrical boundary from
absolute time, requires the same integer-ns quantum as the backend and rejects
boundary disagreement; the inherited admission requires an integer number of
reporting steps per firmware quantum. The original sampled controller is not
used for timestamped edges. This resolves the identified internal-step-index
coupling in the new route, by source inspection.

This route samples receivers at each lookahead start, runs the firmware with
those inputs held, and schedules the returned software-write events. It is
consistent with the declared held-input approximation, not with continuously
coupled receiver transitions. Startup currently requires an operating point
and rejects UIC; a separate operating-point solve supplies the first receiver
samples. That alone does not initialize the transient session's storage.
If a zero-time edge changes mode before the session's first positive step,
its operating-point initialization can use the new mode and erase pre-edge
charge/current. This initial source review requests either explicit rejection
of that startup case or a native initialization preserving the pre-edge state,
plus a nonzero-charge zero-time-edge regression. An initial operating point
and a later mode-dependent operating point are not interchangeable states.

Follow-up source inspection found explicit rejection of `time_ns == 0` when
the native session has no accepted point and operating-point initialization
is enabled, with a matching Python regression in
`tests/python/test_spikes_pad_edges.py`. This resolves the identified startup
case by excluding it, not by qualifying zero-time OP-mode switching. Explicit
storage-initialized native sessions retain their separate time-zero contract;
the timestamped Studio controller still rejects UIC. Execution of the new
rejection fixture is pending the integration owner's recorded results.

### Queue invariant and finite-precision timing

The reviewed queue stores `(absolute_ns, submission_sequence)` keys. By
induction, assume the current accepted storage state corresponds to all
previously consumed events. Its least key selects the next change; strict
`event_time > requested_end` leaves future events untouched. Advancing to that
key with the old mode gives the left-limit storage state. Updating only the
existing resistive branches preserves C/L state, and erasing that key consumes
it exactly once. Equal-time keys cause no positive-duration intermediate
evolution. Repeating establishes the piecewise-mode construction, subject to
solver accuracy and the clock-coincidence convention below. Snapshot restoration
reinstates the induction base if an eventful outer advance fails.

The latest conversion is `double(time_ns)/1e9`, consistent with the transport's
seconds conversion. This avoids the observed multiply-versus-divide one-ULP
disagreement at 100 ns, but does not make all seconds exactly representable.
The wrapper now omits positive segment/residual durations below `1e-18 s`,
the admitted solver minimum. A mode can therefore be applied less than one
attosecond early, and a successful endpoint can undershoot the requested
endpoint by less than one attosecond. This is an explicit numerical coincidence
policy, not exact real-valued event time. Existing past-time tolerance can
likewise treat a recently passed event as coincident; at the maximum horizon
its bound approaches 0.5 ns. Traceable integer ordering survives both policies.

There is no universal electrical error bound from a timing bound alone:
arbitrary admitted small C/L or stiff forcing can make derivatives large.
For the declared RC fixture, switching high/low changes the forcing derivative
by less than `3.3e5 V/s`, and passive exponential propagation is contractive.
Consequently a sub-`1e-18 s` displacement contributes at most `3.3e-13 V` per
edge, with the same bound for one omitted endpoint residual while voltage stays
between the rails. The two-edge fixture's combined conservative allowance is
`9.9e-13 V`, negligible relative to its predeclared discretization budgets.
This calculation does not qualify arbitrary circuits or the much larger
long-horizon past-time allowance. Tests must retain the 100 ns regression,
strict future exclusion, nearby distinct ns ordering and startup rejection.

## Causality and qualification limits

An instruction backend run ahead from `t` to `T` with receiver inputs held at
their values at `t` can return precise backend event times within that window.
Replaying those events into the electrical plant preserves that prescribed
output trace. It does not let an electrical threshold crossing at an interior
time influence firmware that has already run past that time. This is an
explicit held-input/lookahead approximation, not event-synchronous closed-loop
simulation. The approximation needs an admitted feedback interval and separate
convergence tests; causal rollback or interruptible lockstep would be a new
coupling design. On electrical failure, stop or restore both sides under a
qualified coupled checkpoint before continuing.

Backend nanosecond resolution is not measured pin delay, instruction timing,
bus timing, metastability, or vendor output-waveform accuracy. Capturing output
logic transitions also does not automatically capture every direction, pull,
drive-strength or mux change that affects the electrical mode. The event
producer must explicitly admit those changes or retain a stated sampling gap.

Knowledgeable human numerical/device review before release remains required.
No physical measurements, hardware uncertainty bounds or vendor calibration
are admitted by this record.

## Integration-owner execution record - 2026-10-19

The following results were reported by the integration owner, not executed
by this independent reviewer. The reviewer inspected the corresponding final
test source and independently read the current native DLL SHA256:
`8e0937c753a79815304bd4ebca15d6d62821b737a2ffb729f9448320acca4841`
at `build-spikes-io-pad-20261019/Release/spikes_c_api.dll`. Bind these results
to the retained working-source/test revision and integration logs; this note
does not claim a clean committed-tree revision or a released installer.

- `tests/python/test_spikes_pad_edges.py`: 9/9 passed against the final DLL.
  The cases cover both opposite edges within a 100 ns request, queue checkpoint
  replay, stable equal-time updates with explicitly initialized storage,
  malformed/past/unknown-pad rejection, endpoint charge continuity, time-zero
  OP-startup rejection, failure rollback, strict future exclusion and continuous
  RC-oracle refinement.
- The nonlinear failure fixture adds a diode, permits one Newton iteration,
  advances a valid initial segment, then forces the post-edge final segment to
  fail. Assertions restore the exact pre-call accepted time, capacitor-node
  voltage and native step count, and reinstate the pending edge at 30 ns.
  Pad-binding restoration is established by source inspection; this fixture
  does not independently assert every cached mode field or replay after failure.
- The long-horizon fixture places an edge at `2^48 ns` and requests an endpoint
  approximately 0.1 ns earlier. It asserts that the edge remains pending and
  the accepted time remains before the edge. This closes the reproduced
  tolerance-expanded future-edge consumption case.
- Continuous-oracle refinement uses a separate 1 V, 100 ohm, 1 nF fixture,
  with high/low edges at 23 and 67 ns and comparison at 100 ns. The continuous
  exponential composition includes all inactive leakage conductances. Reporting
  steps of 1, 0.5 and 0.25 ns pass the largest-error `<0.005 V` assertion and
  error-ratio range 1.8-2.2. These particular edges align with those refinement
  grids; the separate 100 ns outer-step case demonstrates preservation of
  events inside an output interval. This is not execution of the distinct
  1237/1789 ns, 3.3 V predeclared fixture above.
- `standalone/spikes_project/tests/python/test_firmware_edge_transport.py`:
  10/10 passed with the actual optional Renode runtime in 126.239 s, as reported
  by the integration owner. The original STM firmware produces configuration
  and output events at 20, 50 and 100 ns, including a 50 ns high pulse hidden
  inside one reporting interval. The coupled native-plant test checks
  `1.60975609756 V` at 100 ns within `1e-7 V`, continues through later intervals,
  and asserts native internal step count exceeds the outer reporting count.
  This executes the corrected timestamped controller clock route. Additional
  cases cover capture partitioning, bounded overflow/reaping, unsupported DMA
  rejection and nRF configuration/output capture.

These results close the named bounded software regressions, not the full
predeclared matrix: extended queue-capacity stress, simultaneous coupled pads,
package-inductor state at queued edges, arbitrary stiff circuits and measured
device validation remain separate evidence. The sub-attosecond coincidence
policy, long-horizon past-time tolerance, held-input lookahead and explicit
time-zero OP rejection remain limitations. Building an installer candidate
does not supply knowledgeable human numerical/device release approval, physical
validation or hardware timing qualification.
