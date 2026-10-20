<!-- SPDX-License-Identifier: Apache-2.0 -->
# Solver improvement feedback and action plan

SPIKE should first strengthen error control and comparison semantics, then
expand predictive coverage, and finally optimize runtime at fixed accuracy.
The benchmark evidence supports useful bounded thermal, PI, SI, EM and coupled
solutions. It does not support a general hardware accuracy percentage or
arbitrary full-wave EM plus SPICE plus thermal feedback.

This plan responds to the 12 October 2026 accuracy work and the question about
mV, mA and smaller signals. It defines implementation work, accountable owner
roles and checkable completion gates. New targets below are engineering
acceptance proposals fixed before their first run, not achieved results or
universal physical tolerances. Calendar estimates are omitted until resources
and reference-tool availability are known.

Evidence: [accuracy program](SOLVER_ACCURACY_PROGRAM.md),
[initial baseline](validation/SOLVER_ACCURACY_BASELINE_20261012.md), and the
[historical comprehensive report](validation/RELEASE_040_LOCAL_EVIDENCE.md) was a
local generated artifact and is not shipped. Its claims remain provisional until
the checked-in benchmark commands are rerun and reviewed.
The [action backlog](solver-improvement-actions-v1.json) is the execution
register. Its IDs are engineering task references, not capability flags.

## Feedback from the established results

| Finding | Engineering interpretation | Required response |
| --- | --- | --- |
| RC/RL endpoint error falls from 36.404 to 2.276 uV when the step falls from 1 to 0.25 us | Near-second-order temporal error for these linear fixtures; no proof of proportional error at small amplitudes | Add amplitude and timestep sweeps before changing defaults; expose achieved error evidence |
| Nonuniform SPIKE/CalculiX transient disagreement is 0.351567 K | Different consistent-P1 and centroid capacity rules; not proof that either kernel is universally wrong | Bind each comparison to capacity semantics and separate temporal, spatial and cross-code errors |
| Coarse thermal spatial comparison fails while finer cases pass | Resolution matters; uniform/steady precision cannot represent general transient accuracy | Add error-driven refinement and explicit unresolved discretization status |
| EM fine capacitance error is 2.3227%; sampled maximum complex E error is 4.9639% | The field result is close to its 5% gate; field error convergence has not been established | Improve field/mesh/normalization convergence evidence; keep scope local to the plate case |
| EM duration case hits 80000 steps near -81.74 dB instead of -90 dB | Response stability passes while the requested decay criterion fails | Return separate execution, stopping and observable-sensitivity status; do not silently increase caps |
| An inherited EM metric says time refined but only duration was changed | Evidence-label defect, not a demonstrated numerical defect | Correct the label and add a genuinely independent timestep sweep |
| SI lossless-line S21 error is near floating-point precision | Network algebra works for supplied RLGC; geometry prediction is unqualified | Add independent geometry extraction and measured-coupon comparison |
| PI DC loss error is near floating-point precision but capacitance and sheet approximations have percent errors | Formula and circuit consistency do not certify extracted geometry physics | Validate spatial extraction and full matrices independently |
| PWM finest errors are 0.734 mV, 1.97 mA and 0.00336 K | Bounded switched model converges; only winding resistance has temperature feedback | Extend waveform/event/error coverage and device-loss feedback with energy checks |
| PI/SI volume coupling executed Python MNA with SciPy SuperLU | API naming does not identify the actual numerical backend | Always retain requested and executed backend, artifact identity and fallback reason |
| Retained STEP run initially could not import NumPy in its isolated child | Runtime environment contract failure, resolved locally by a path override | Make declared mesher environments self-sufficient without weakening isolation |

## Execution order and stage exits

Use one integrating owner. Numerical ownership follows SUBSYSTEM_INDEX;
independent work can run in parallel only when file ownership is disjoint.
Keep existing benchmark thresholds and failed artifacts. Open one bounded
change per action or a tightly related pair, with derivation and validation.

| Stage | Actions | Exit condition |
| --- | --- | --- |
| 1 Establish trustworthy error evidence | ACC01, ACC02, ACC03, ACC04, ACC05 | Amplitude results, capacity semantics, EM stopping/labels, reproducible environment and executed-backend identity recorded; unresolved failures remain visible |
| 2 Improve accuracy in existing models | ACC06, ACC07, ACC08, ACC09, ACC10 | Timestep/mesh/coupling error budgets pass on declared fixture envelopes; error-controller changes have independent oracles |
| 3 Establish predictive coverage | ACC11, ACC12, ACC13 | Independent geometry, nonlinear device and measurement cases are executed or explicitly blocked; only passed operating strata can be promoted |
| 4 Improve usability and efficiency | ACC14, ACC15 | Guided setup works for supported routes; performance measured at equal accuracy with persistence and cancellation checks |
| 5 Extend coupled physics | ACC16 | A reviewed loss-transfer contract and bounded one-way prototype pass before any two-way full-wave claim |

ACC03 and ACC04 can proceed while ACC01 and ACC02 run. ACC05 precedes
publishing new benchmark claims. ACC14 may start with already supported routes;
it must not wait for ACC16 or suggest that ACC16 is implemented.

## Stage one actions

### ACC01 Verify amplitude proportionality and numerical floors

Owner: circuit numerics. Extend
`scripts/benchmark_circuit_timestep_accuracy.py` into an amplitude/timestep
matrix. Run original linear RC/RL cases at scales 1, 1e-3 and 1e-6 with steps
1, 0.5 and 0.25 us. Retain volts and amperes as separate observables, raw
waveforms and unit-correct normalized errors. Include zero input and sign
reversal. Do not subtract fitted delay or rescale output after execution.

For the finest linear fixture, propose
`abs(error) <= atol + 5e-6*abs(reference)`, with declared initial floors
`atol_V=1e-12 V` and `atol_I=1e-15 A`. These are tests of a proposed envelope,
not an assertion that SPIKE already meets it. Compare error divided by the
excitation scale; if it stops scaling, locate tolerances, conditioning,
integration, interpolation or serialization as separate causes. Change
solver tolerance handling only when the discriminating test identifies it.
Completion: publish the minimum verified amplitude and error floor per
observable; every failing stratum stays failed.

### ACC02 Resolve thermal comparison semantics before kernel changes

Owner: solid thermal. Record capacity matrix rule, integration rule, boundary
discretization, timestep and material identity in both internal and external
results. Preserve the 0.351567 K fixture and its two independent discrete
oracles. Add a continuous manufactured thermal field and matched
coarse-to-fine studies: spatial subdivisions 2, 4, 8 and temporal steps
0.04, 0.02, 0.01, 0.005 s, refining one axis while controlling the other.

First decision: determine whether both formulations converge to the same
continuum within the declared model. If yes, keep their native rules and
report discretization uncertainty; a comparison mode must not silently
replace production capacity. If no, isolate conservation, assembly,
boundary or integration defects before editing a kernel. Completion:
preserve the existing per-node cross-code gate, demonstrate decreasing
independent continuum error, and meet a proposed finest-field budget of
0.01 K plus 1% of the local reference temperature rise for the new fixture.
No near-zero temperature-rise point may be judged by relative error alone.

### ACC03 Make EM stopping and refinement claims exact

Owner: retained EM adapter. In `assembly_em.py` and the owned openEMS driver,
return execution status, requested/observed decay, final timestep, cap hit,
stopping reason and observable-sensitivity status independently. Use a
supported public runtime result when available; otherwise use a bounded,
tested log parser with runtime identity and an explicit unknown state.
Absence of the cap warning must not become proof of decay success.

Rename the duration-only metric without deleting its historical key meaning.
Add synthetic log/parser cases for reached decay, cap hit, timeout, malformed
and missing evidence. Re-run the retained plate study. Completion: the
80000-step case remains stopping-failed unless an actual changed run reaches
-90 dB; accepted S11 sensitivity remains a separate result. No automatic cap
increase, softened decay request or new production-qualified flag.

### ACC04 Make isolated numerical environments reproducible

Owner: runtime orchestration. Fix declared CAD/mesher environment selection
and dependency preflight in the existing bounded child-process route. The
isolated child must import its declared NumPy/native dependencies without
ad hoc injection from unrelated installations. Retain resolved interpreter,
dependency versions and error diagnostics. Preserve the original failed run.
Completion: the retained STEP transient workflow passes in a fresh process
with no manual package-path override; a deliberately incomplete environment
fails preflight with the missing dependency, while isolation and path admission
checks still pass.

### ACC05 Bind benchmarks to actual execution and immutable evidence

Owner: qualification tooling. Record requested and executed backend, fallback
reason, semantic engine version, binary/input/source hashes, capacity/integration
settings, host and exact command. Verify relevant input/source identity before
and after a run; concurrent changes make its source binding inconclusive.
Separate original-run, rerun and historical results. Validate missing outputs,
NaN, unit/reference-plane mismatch, skips and incomplete cases as failures or
blocked states, never passes. Completion: replay the current report from its
manifest and detect tampering, version drift and backend substitution; every
table value can be traced to one observable in an accepted record.

## Stage two actions

### ACC06 Add unit aware transient error control

Owner: SPIKES native transient. After ACC01, evaluate the current adaptive LTE
controller across voltage and branch-current scales. Define tolerances for
each physical quantity and state group, preserving existing ABI behavior or
introducing an explicitly versioned option. Do not compare volts, amperes and
temperature in an unscaled norm. Distinguish internal stepping from output
sampling and keep event breakpoints exact.

Completion: independent RC/RL/RLC and supported diode/switch cases meet the
predeclared absolute-plus-relative budgets; rejected steps restore all state;
source breakpoints, persistent/batch equivalence and failure recovery pass.
The small-amplitude sweep must be re-run. Choose an adaptive preset only after
its achieved error and cost are measured; do not merely tighten all defaults.

### ACC07 Add solution based thermal mesh and time checks

Owner: thermal accuracy. Use the actual solved temperature rise, heat flux and
contact heat flow to drive convergence reports. Refine contacts, thin materials
and heated regions as well as bulk volume. Extend `thermal_accuracy.py` beyond
successive-value change when an independent oracle is available. Use
Richardson/GCI only with admissible smooth/asymptotic data; otherwise report
unresolved error. Completion: exact slab/contact and nonuniform transient
fixtures meet their frozen budgets, conserved watts/energy remain unchanged,
and unresolved contact/mesh error blocks accuracy-qualified presentation.

### ACC08 Establish EM field and loss accuracy with independent refinements

Owner: field qualification. Hold geometry, port reference planes and PML
location fixed while refining the interior grid. Change FDTD timestep
independently through a supported control, and test duration/PML separately.
If the installed runtime cannot support a controlled timestep study, record
that axis as blocked rather than relabel duration. Check complex fields at
fixed physical coordinates, not nearest-grid peaks alone.

Completion: retain current 5% field and capacitance gates and establish
decreasing field/reference discrepancy on a preselected sequence. A proposed
next field target is <=2% maximum on the original admitted interior samples;
failure remains a failed target. Add an independent finite-conductivity loss
case before using small real impedance as resolved physical dissipation.

### ACC09 Control electrical thermal coupling error independently

Owner: coupled orchestration. Extend PI/SI-volume and PWM-volume studies with
stronger feedback, source/load changes and nonuniform heat maps. Retain
unrelaxed temperature and per-device energy defects. Refine electrical step,
thermal window, spatial mesh and coupling iteration separately. Compare
against an independent monolithic ODE for a lumped case and a manufactured
spatial case; an internal fine-run reference is labeled accordingly.

Completion: existing finest PWM gates (0.005 A, 0.002 V, 0.005 K) and energy
ledgers remain passed; a new refined target is half each error budget on the
same synthetic fixture. Rollback/cancellation publish only committed windows.
Exhausted iterations fail without hidden timestep or tolerance changes.

### ACC10 Improve geometry based PI extraction in a bounded envelope

Owner: PEEC and geometry DC. Re-run sheet/contact/trace/via refinement and
compare full self/mutual matrices with independently derived compatible
conductor references. Diagnose geometry/terminal bias behind the 2.5% sheet
result before changing discretization. Add mesh-aware endpoint/area checks.

Completion: proposed <=1% resistance error for the existing sheet case within
a declared mesh/resource budget, while trace/via unit invariants remain passed.
For C/G, begin with homogeneous coaxial/plate/multiconductor limits and explicit
reference definitions. Do not promote single-reference capacitance to arbitrary
electrostatic accuracy. Independent field evidence is required by ACC11.

## Stage three actions

### ACC11 Validate geometry derived SI and extraction against external fields

Owner: SI and field qualification. Independently author a uniform two-port and
coupled four-port coupon with exact material/geometry/port data. Compare against
an installed independent field solver and the analytical uniform limit.
Record reference impedance, calibration/de-embedding planes, wave convention
and frequency grid. Compare Cartesian complex S, delay, Z0, crosstalk and loaded
waveforms; phase near nulls needs a separate mask.

Before execution, propose fixture budgets of <=0.02 maximum complex-S absolute
error and <=2% delay/Z0 error across the declared band. These are numerical
targets, not signal-integrity compliance. Completion: match geometry and
reference planes, pass mesh/time convergence, and execute both coupons with
all required ports. Admitted Cambridge wire measurements cannot supply absent
four-port entries or substitute for a matched PCB prediction.

### ACC12 Expand nonlinear and switching circuit qualification

Owner: circuit models. Add same-model diode/BJT/MOS DC sweeps, AC poles/phase,
charge/transient and switching waveforms across voltages, currents, temperature
and stiffness. Use ngspice and LTspice where the admitted equations/dialect
match; include Xyce only when installed and the comparison is equivalent.
Publish max and RMS waveform error at common physical times, event timing,
KCL, source energy, dissipated heat and stored energy. Keep edge/model
approximation errors distinct from integration error.

Completion: all predeclared case-specific gates pass on the supported model
envelope, nonconvergence is explicit, and the small-signal floors from ACC01
are preserved. Extend PWM feedback beyond the winding only after bounded,
reviewed temperature-dependent switch/device loss laws are admitted and every
loss is counted once. No vendor/hardware model claim from ideal switches.

### ACC13 Establish held out measurement correlation

Owner: engineering validation. Select one reproducible resistive/thermal coupon
and one SI coupon with complete geometry, operating conditions, raw observations
and uncertainty. Review acquisition, calibration, permitted use and material
uncertainty before admission. Split parameter fitting from held-out validation;
report individual operating points and residual distributions.

Completion: predictions are executed without tuning to held-out data; acceptance
is frozen from the intended engineering error budget and measurement uncertainty
before seeing predictions. Budget-setting is a required acquisition milestone,
not a placeholder for a later pass. Unavailable physical data remain blocked;
analytical and external-code evidence cannot promote measurement maturity.

## Stages four and five actions

### ACC14 Provide a guided setup for supported coupling

Owner: desktop and worker admission. Offer supported physics selections for
DC PI thermal, single-frequency SI thermal, bounded native PWM thermal and
stationary planar magnetic thermal. Show one-way versus two-way feedback.
Require source/load, cooling/contact, material-law and reviewed loss mappings;
give ordinary forms for these instead of mandatory hand-edited JSON. Keep
advanced JSON as an explicit option. Do not expose arbitrary full-wave plus
SPICE thermal feedback as runnable.

Completion: prepare/run/save/reopen works on one actual case for each supported
route; missing mappings, stale geometry, unavailable engines and incompatible
models are actionable. Numerical results and qualification scope survive the
wizard unchanged. Verify actual wide/narrow native layouts, cancellation and
result invalidation, following the UI skill and project checks.

### ACC15 Optimize runtime at the same accuracy

Owner: numerical performance. After each numerical envelope is established,
measure matched cases with two warmups and at least seven runs, recording
median/p95 wall time, peak process memory, threads, hardware and accuracy.
Use small, medium and large declared problems and distinguish cold process
startup, assembly/factorization, stepping and postprocessing. Isolate benchmark
processes; the concurrent exploratory timings are not speed rankings.

Profile before optimizing. Reuse topology/sparsity and factorizations only when
temperature, nonlinear state, timestep and material dependencies permit it.
Proposed first optimization gate: >=20% median-time reduction on the explicitly
profiled bottleneck case, no weakened accuracy/conservation gate, no new memory
limit violation, and no >10% median regression on the frozen neighboring corpus.
If the target fails, retain the result instead of broadening the favorable case.

### ACC16 Build full field thermal coupling in bounded steps

Owner: coupling architecture and field adapters. Start with one-way EM-to-thermal
transfer for an independently authored stationary lossy coupon. Define physical
time-averaged watts, peak/RMS normalization, occurrence/cell identity, conservative
loss deposition and admissible materials. Require actually resolved conductor
and dielectric losses from ACC08; rendered E/H magnitude is not heat.

Completion for the first step: integrated field loss matches transferred thermal
watts within a proposed 0.1% mapping budget and passes the independent loss oracle.
Only then add temperature-dependent conductivity/permittivity and bounded
two-way iteration with rollback and mesh/field/thermal error checks. A general
full-wave plus nonlinear SPICE plus thermal route needs a separate reviewed
coupling contract and independent combined oracle before implementation.
Do not equate stationary planar magnetic heating with this capability.

## Review and delivery requirements

### First-batch execution checkpoint: 13 October 2026

- ACC01 now has a signed/zero amplitude mode preserving the historical v1
  default. Its conclusive 42-run owned-C++ evidence is
the unbundled local `acc01-20261013-rerun-1/report.json`. All 36 nonzero strata fail the
  frozen pointwise budgets; all six zero strata pass. Errors scale with
  excitation and peak at the ramp corner. No nonzero verified minimum amplitude
  is claimed. The initial run remains inconclusive because a bound source
  changed during execution. Startup/corner integration is the next discriminator;
  tolerances and solver defaults are unchanged. An independent scalar recurrence
  with backward Euler only at startup and the ramp corner reproduces the whole
  retained RC/RL traces within 1.27e-13/9.09e-14 respectively. At 0.25 us those
  two steps explain the 6.18188e-6 V RC corner defect. Breakpoint counters also
  omit events exactly on the regular grid even though the integrator uses BE;
  this diagnostics nuance must be addressed in the subsequent control review.
- ACC03 has fresh retained-plate stopping evidence under
the unbundled local `retained-assembly-em-acc03-20261013` record. The 80,000-step duration run
  remains stopping-failed (-81.74 dB observed versus -90 dB requested), while
  its S11 sensitivity passes independently. Parser edge-case review repairs are
  tested, with separate `stopping-reparse-v2.json` evidence preserving all actual
  statuses. Full integration qualification remains pending.
- ACC04's actual retained STEP/thermal/project workflow now runs without the
  historical path override. See [declared environment repair](ASSEMBLY_THERMAL_MESHING.md#declared-isolated-environment-repair-13-october-2026-acc04)
and the unbundled local `acc04-20261013/validation.json` record. Sources were unchanged and the
  288-node SPIKE/CalculiX comparison passes its existing gate. Fresh-process
  tests cover each missing dependency, `.pth`/`PYTHONPATH` isolation, venv
  precedence and poisoned executable-path environment variables.

These are separate implementation/measurement records, not universal accuracy
or release qualification. A concurrent `spider_v2.py` module-size violation was
reported earlier and is now resolved; the global architecture guard passes.
No guard was waived and this task did not change that unrelated module.
ACC02 continuum analysis and ACC05 full replay/tamper/backend-substitution
qualification remain open; new run identities do not replace historical ones.

Integrated checks: 24 focused circuit/parser tests passed, 26 benchmark/runtime
tests passed with five optional-runtime skips, and the actual CPython 3.11
mesher/extension checks passed 23 tests without those skips. The required broader
run completed 3,666 tests with one failure, one error and 65 skips. Its unrelated
Python-debug startup failure passed when isolated; import-stage receipt
qualification remains failed because WF01-S01/S02 receipts lack newly required
source bindings. Fresh actual imports under
the unbundled local `first-batch-parity-replay-20261013` S01 and S02 records pass, but this task did
not overwrite the other task's receipts or backlog. Full-suite qualification
is therefore not green. The architecture and solver-plan checks pass.

### Solver-suite queue adoption: 13 October 2026

The solver-suite integrating owner adopts this register without changing its
targets, dependencies or completion gates. The plan checker passed and all 13
retained report-manifest entries matched their SHA-256 hashes. This verifies
retained artifact integrity, not the report's current-source applicability or
ACC05 replay/backend-substitution gates. No ACC action is closed by this review.

Current source foundations are reconciled as follows:

- Explicit linear PDN AC/transient models and retained-dielectric P1 capacitance
  have analytical evidence. They support ACC10/ACC11 work but do not qualify
  automatic arbitrary-PCB extraction, fringing fields or measured correlation.
- Retained-volume thermal stepping, conservative per-device energy mapping and
  PWM rollback exist. They do not close ACC02 capacity/continuum analysis or
  ACC09 independent electrical-step/window/mesh/coupling error budgets.
- The local native DLL was rebuilt to resolve stale analytic sine-source ABI
  exports. Eleven sine-source tests passed (one skip), 496 SPIKES integration
  tests passed (24 skips), and 26 PWM-volume consumer tests passed. This is not
  ACC01 small-amplitude evidence or ACC06 unit-aware LTE qualification. The
  earlier full run's four stale-DLL errors remain recorded in
  [PDN development checks](PDN_SCREENING.md#reproduce-numerical-evidence).
- PDN setup currently provides advanced JSON authoring and worker/result
  lifecycle checks. ACC14 still requires ordinary forms, all named coupling
  routes, persistence and actual native visual acceptance.

Next implementation remains ACC01, ACC03 and ACC04. ACC01's current harness
still uses unit excitation and voltage-only endpoint observables; add signed,
zero and 1/1e-3/1e-6 excitation strata with independent current observables before
touching solver tolerances. ACC03's current adapter distinguishes detected
timestep-cap failure from unknown decay, but lacks the requested complete
stopping evidence; its duration-only `time_refined` label remains to be fixed.
ACC04 must inspect the actual `gmsh_occ_runtime.py` and
`gmsh_extension_runtime.py` child/environment admission as well as the injected
OCC compiler named in the register. ACC02 continuum analysis may proceed on
disjoint files, preserving consistent-P1 and centroid capacity semantics.

ACC05 is a publication prerequisite, including for this first batch. The newly
rebuilt native DLL is a different execution artifact from the retained report:
do not relabel historical results as its execution. Bind new circuit, Python
SuperLU, field and external thermal runs separately, check source/input identity
before and after execution, and retain inconclusive bindings and failed cases.
No solver defaults, capacity rules, production flags or benchmark thresholds
were changed during adoption.

For every completed action, retain the original failing evidence, exact
derivation or source, input/output identities, actual backend, units, gates,
convergence and validity limits. Update the action register with execution
evidence, not merely a merged implementation. Numerical changes follow
CONTRIBUTING and require knowledgeable human review before release.

Use the relevant focused tests during development, then all required project
checks for the affected boundaries. Run the architecture guard. UI work also
requires the specified button, parser, TypeScript and visual/persistence checks;
ABI/host changes need native/Rust checks. A report generator does not replace
solver tests. Performance optimization follows correctness, not the reverse.

The first implementation batch is ACC01, ACC03 and ACC04, with ACC02 analysis
in parallel if ownership is disjoint. Its deliverable is a small-signal accuracy
envelope, exact EM stopping evidence and a reproducible isolated environment.
Stage two starts only with those results available and the relevant discrete
model semantics documented. Existing independent capabilities remain usable
within their current experimental scope throughout this work.

### Startup/corner and importer refresh: 18 October 2026

The owner approved an explicitly named higher-order linear method rather than
silently changing legacy behavior. `radau_iia3` now passes all 42 frozen ACC01
signed/zero RC/RL cases with the same timestep grids and all-time pointwise
voltage/current budgets. Source, binary and input bindings are conclusive in
the unbundled local `acc01-radau-20261018/report.json`. The lowest tested input is 1e-6 V;
case-specific observed errors are not a universal accuracy floor. The October
13 trapezoidal failures remain retained, not relabeled. Eight native regression
executables passed; independent numerical review verified third-order sine
convergence and found a coincident full-duty PULSE boundary defect, now fixed
and rerun. See [derivation and limits](NUMERICAL_METHOD_EVIDENCE.md#native-linear-radau-iia3--18-october-2026).

Six actual pinned importer runs regenerated WF01-S01/S02/S03/S04A/S04B/S04C1
v2 receipts with exact importer-source, manifest and retained-import hashes.
Only their evidence pointers were refreshed; historical failed artifacts and
tamper/staleness rejection controls remain. Focused corpus/backlog checks passed.
The final local full-suite result is recorded below; it does not establish
release qualification. The package metadata helper extraction repairs an architecture
size violation without changing media-type/role behavior (82 project tests
passed, three optional skips).

The initial refreshed full run completed 4,235 tests with one failure, five
errors and 65 skips. Four errors came from component-admission code/receipt
bindings loaded before their refresh; a fresh combined parity run passed 32/32.
The remaining strict PWM schema error was repaired by explicitly admitting only
the additive optional nonnegative Radau counter (unknown keys remain rejected;
PWM remains BE); nine actual/native admission, energy and restart checks passed.
Studio discovery was reproduced failing after a metadata-free GUI stub was
installed by another test module. Conservative inert module discovery fixes
that case without launching/importing a GUI; the ordered regression passed
15 tests and neighboring board integration/coupling passed 18. The original
failed log remains an unbundled local record named `full-python-suite-20261018.log`.
A fresh full rerun is retained separately; no failed run is relabeled green.

That second run completed 4,250 tests with zero failures, four errors and 65
skips. All four errors rejected PI/SI evidence after another active task changed
the gate at 23:20 and regenerated receipts at 23:25, following module loading
at 23:18. The formerly failing native PWM and Studio discovery tests passed.
A fresh process passed all 42 affected parity tests. After that task completed
and became idle, a third full run started, recording gate/receipt and native
DLL SHA-256 identities before and after execution. Its log is
the unbundled local `full-python-suite-stable-20261018.log` record; input drift
must be reported inconclusive, not accepted as qualification.

The guarded third run completed 4,270 tests with one failure, zero errors and
65 skips. All recorded gate/receipt and native-library hashes were unchanged;
the repaired parity, native PWM and Studio checks passed. The sole failure was
the debugger still reporting `starting` beyond its existing four-second polling
budget despite a one-second configured deadline. Investigation found that its
child watchdog initializes only after package/API imports. A separate terminal
state read/exit race was reproduced deterministically, and Windows process
liveness also required an actual process-state probe. These findings are now
repaired without extending deadlines or weakening assertions. All 16 focused
debug tests pass, including a child stalled before its own watchdog starts,
original one-second deadline/four-second observation checks, actual child-death
checks before fixture cleanup, preserved terminal records, and rejected forged
identity/nonfinite deadlines. An actual descendant-tree Stop probe also passed.
The Windows probe uses a zero-time
[process wait](https://learn.microsoft.com/en-us/windows/win32/api/synchapi/nf-synchapi-waitforsingleobject)
with minimal SYNCHRONIZE rights and closes its
[OpenProcess handle](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-openprocess);
actual live-child and exit-259 probes verify liveness without signaling it.
The official [Python 3.14 os.kill contract](https://docs.python.org/3.14/library/os.html#os.kill)
does not justify treating Windows signals as POSIX liveness checks. These API
references were reviewed on 2026-10-18; implementation and tests are independently
authored, not copied from examples.

During startup the deadline fallback requires status polling until the child's
watchdog initializes; this is not an OS-enforced guarantee for an unobserved
startup or a security sandbox. The final fresh full run is retained at
the unbundled local `full-python-suite-post-timeout-fix-20261018.log` record,
with debugger implementation/tests/guide included in its before/after hash guard.
The final run completed on 19 October 2026: **4,293 tests, zero failures, zero
errors, 69 skips**, in 994.704 seconds. All 16 debugger tests passed in that full
run. The four additional skips relative to the prior run are newly added opt-in
native firmware-emulator tests, not formerly failing tests converted to skips.
The remaining optional skips are explicit limitations, not waived qualification.

The guarded input SHA-256 was identical before/after:
`5fc39942f0a21fc5cb310fb20724d903f355e57cb7875ba01ec394c4c60ceab6`.
The native DLL likewise remained
`9a2bd6745538483c38858642eab1eeef103fefe9121ef1cdc33085e661799447`.
The retained full-log SHA-256 is
`a823b67ab2325ba961cd94d074e078d7033184590ac0a8e791838ab8a5620c96`.
This closes the observed startup/corner, stale-receipt and integration failures
for the bounded local configuration without changing acceptance tolerances,
legacy numerical defaults or production gates. It does not close all ACC actions,
the 69 skipped cases, measured validation, platform matrices or knowledgeable
human numerical review before release. Earlier failed runs remain retained.
