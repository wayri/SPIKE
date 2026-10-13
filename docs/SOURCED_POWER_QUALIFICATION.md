<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright (c) 2026 SigHarmonic -->
# Sourced power circuit qualification

The local developer workflow binds circuit/model bytes, runs supported native
operating-point and transient decks, retains waveform evidence and separates
numerical regression PASS from hardware qualification. It is experimental and
does not claim complete vendor SPICE dialect or device coverage.

## Native deck workflow

Run the original analytical examples into a new directory:

```powershell
.venv/Scripts/python.exe -W error examples/sas_qualification/run_reference.py --output build/power-reference-new
```

The divider produces 1.65 V. The independent RC fixture crosses 0.5 V near
0.694 ms, compared with the exact `RC log(2)` value of 0.693147 ms. It runs at
three declared steps, 10, 5 and 2.5 microseconds, with explicit numerical and
observable acceptance tolerances. These are ideal numerical fixtures, not SAS
device models. Each case exports JSON, full waveform CSV, decimated SVG plots
and a final SHA-256 artifact manifest. Existing output directories are rejected.
Vendor model payloads are not redistributed by the exporter.

`python.spikes.sourced_qualification.qualify_sourced_deck(request, source_root)`
accepts the strict `spikes/sourced-qualification-request/v1` dictionary; the
companion test shows every required field. Specify one deck, a complete hashed
source/model inventory, origin/revision/operating conditions/value basis,
explicit caller pin mappings and observable checks. Includes must be normalized
relative paths to admitted files; symlinks, reparse points and traversal fail.
The parser consumes admitted include snapshots instead of rereading model bytes.
The native runner receives an actual saved-step cap, accounting for source-event
steps and node/current/power vectors, not only nominal `.tran` output intervals.

Available checks are last/minimum/maximum value and first rising threshold
crossing. Missing crossings cannot pass. Transients compare measurements across
two finer steps; this is not a full waveform error estimator or exhaustive event
phase/width sweep. Numerical tolerances are separate from physical acceptance
ranges. Compatibility errors return BLOCKED without substituting ideal parts.
Actual solve failures return FAIL; malformed admission raises a coded ValueError.

This API runs bounded native calls in process and is not an OS-isolated vendor
execution service. It adds no timeout/process-tree guarantees. Existing trusted
worker supervision remains necessary for untrusted jobs. Source checks establish
content integrity, not publisher authenticity, license rights or applicable
min/typ/max corners. Pin mappings are caller declarations, not CAD equivalence.

## Thermal transient with electrical feedback

`python.spike_core.transient_resistive_electrothermal.run_transient_resistive_electrothermal`
accepts `spike/transient-resistive-electrothermal-request/v1`. Supply exactly:
`circuit`, `thermal`, `loss_mappings`, `loss_ledger`, `time`, `iteration` and
`contract`. See the companion tests for a complete reproducible request.

The circuit contains resistors and constant ideal sources only. Every resistor
requires a thermal-node mapping and `R(T)=Rref*(1+alpha*(T-Tref))` validity.
Every element requires an explicit loss-ledger entry. Thermal nodes require
heat capacities, initial temperatures and Kelvin limits; thermal links require
explicit K/W resistances. No cooling, copper/contact resistance or source losses
are inferred. Supplied contact/copper resistors use the same reviewed mapping.

Each thermal backward-Euler step iterates electrical operating point, Joule loss
and thermal temperature. Admission checks include finite positive R(T), unrelaxed
temperature/power residuals, electrical power balance and independent nodal/global
thermal energy balance. Failed/cancelled/oversized results withhold all samples.
Control/result JSON is capped at 8 MiB. Limits and time budgets apply between
kernel calls, not as an OS watchdog.

This is a thermal transient with quasi-static electrical balance. It is not an
electrical C/L transient, switching semiconductor solver or airflow simulation.
It is distinct from the native resistor/WBG electrothermal device models; their
embedded ambient leakage cannot simply be reinterpreted as a shared sink link.
The eight-branch shared-sink test is synthetic, not installed SAS hardware.

To export that independent synthetic thermal reference as JSON, CSV and plots:

```powershell
.venv/Scripts/python.exe -W error examples/sas_qualification/run_thermal_reference.py --output build/thermal-reference-new
```

All eight branches converge toward 321.951219510 K, and the synthetic sink
toward 314.634146341 K. The 200 s example agrees with its independently derived
steady oracle within 2.1e-9 K. None of these assumed capacities or resistances
is asserted to describe actual blade cooling.

## SAS applicability

Use the read-only inventory with the owner's SAS source tree:

```powershell
.venv/Scripts/python.exe -W error examples/sas_qualification/audit_inputs.py --sas-root D:/PROJECTS-DEV/SAS/SAS_GSE --output build/sas-audit-new.json
```

Do not execute the supplied controller models by stripping unsupported source
constructs or silently replacing them. The October 6 inventory records native
parser blockers for all 15 supplied decks; independent SAS task run records are
not proof these native jobs executed. Original model bytes remain external.
See [validation and remaining work](validation/SAS_ENGINE_20261006.md).

The assembly has four blades downstream in fan airflow. The owner subsequently
permitted thin low-profile heatsinks, superseding the earlier bare-blade-only
constraint. Sink/TIM/isolation paths remain explicit conditional inputs, not
installed or measured properties. Local air must remain at most 40 C normally
and 50 C absolutely, including downstream warming.
Eight paths per blade at 3.602526 W give 28.820208 W per blade and 115.280832 W
across four blades, before Base heat. These sums use the rounded per-path input;
the retained handoff separately states 28.820209 W per blade. At 4.034829 W/path,
the corresponding sums are 32.278632 and 129.114528 W. These are heat-load
budgets, not temperatures or installed cooling predictions.

For a declared temperature target and ambient, `(Ttarget-Tambient)/P` is an
allowable effective thermal-resistance budget for that explicitly defined
path/load. It does not identify the actual copper/via/convection network.
Downstream air rise additionally needs installed mass flow and heat capacity;
free-air fan CFM is not a guaranteed enclosure operating point. Board spacing,
orientation, ambient, pressure losses, Base heat and measured correlation remain
required. Raw-pulse capture, guaranteed hot DC-SOA and full device-loss coverage
remain open; no numerical PASS in this workflow closes them.

## Native copper replay

Replay the saved Blade case without modifying its CAD or cached workspace:

```powershell
.venv/Scripts/python.exe -W error examples/sas_qualification/run_board_reference.py --case D:/PROJECTS-DEV/SAS/SAS_GSE/simulations/spike_board_thermal --output build/copper-replay-new
```

The replay imports source-filled copper afresh, includes all admitted zones,
retains prescribed losses/contact/convection, and runs steady 5/2.5/2 mm grids.
It exports raw requests/results, source and engine digests, component comparison
errors and a final artifact manifest into a new directory. A small comparison
error does not itself establish convergence; copper sampling and contact
representation require independent stability checks. No installed desktop
executable is updated by this developer workflow.

## Method and evidence policy

### Native coupled transient reference (2026-10-09)

`tests/test_spikes_electrothermal_reference.cpp` qualifies a bounded synthetic
native electrothermal resistor/thermal-RC fixture, not a switching converter.
It uses the existing simultaneously coupled native device equations and
persistent sessions; no second coupling solver was added. Explicit values are
I=1 A, R0=2 ohms, alpha=0.02/K, Cthermal=2 J/K, Rthermal=1 K/W and ambient=300 K.
The native thermal node is temperature **rise**, not absolute temperature.
Independent energy balance gives `theta'=1-0.48*theta`, hence
`theta(t)=2/0.96*(1-exp(-0.48*t))` for a cold start.

Reproduce with a configured native CMake build:

```powershell
cmake --build build-peec-native --target test_spikes_electrothermal_reference
ctest --test-dir build-peec-native -R '^test_spikes_electrothermal_reference$' --output-on-failure -V
```

The test uses release-safe exceptions and target-scoped warnings-as-errors.
It checks every-step BE/BDF2 scalar recurrences, electrical source/Joule signs
and power closure, discrete thermal storage/ambient/loss balance, cumulative
physical BE energy, alpha=0 feedback comparison, persistent/batch equivalence,
checkpoint integration history and a changed current source. BDF2 companion
history is not mislabeled as physical stored energy. Constant-step refinement
at 0.2/0.1/0.05 seconds yields BE end errors 0.0353223/0.0180115/0.00909647 K
and BDF2 errors 0.00342798/0.000818061/0.000200731 K. Error ratios are
0.510/0.505 and 0.239/0.245 respectively, passing the predeclared order gates.
Maximum measured nodal balance residual was 2.34e-13 W; BE cumulative balance
was at most 2.31e-14 J for this two-second fixture. Feedback raised the finest
BE end temperature by 0.0214046 K versus the alpha=0 model.

The actual MSVC Release build and execution passed locally, along with the
existing native transient and persistent-session targets (3/3 CTest targets).
This resolves the missing native resistor refinement/energy/checkpoint evidence,
not full closed-loop PWM/SPICE semiconductor or spatial transient electrothermal
qualification. Converter-study temperature-to-ngspice feedback, realistic
switching-loss bindings, transient volume/airflow coupling, arbitrary device
coverage, E/H feedback, measured correlation and platform/package qualification
remain separate work. Native single-step calls are bounded; orchestration must
poll cancellation between calls and use owned process supervision for watchdogs.
No new cancellation checkpoint promise is inferred from this numerical test.

The same target additionally exercises a closed-loop **cycle-averaged** buck
through native persistent sessions, not PWM transistor switching. An explicit
sampled PI sets the ideal average source; a native temperature-dependent series
resistor couples current/loss back to thermal state. Values: Vin=12 V, Vref=5 V,
L=100 uH, C=100 uF, external load=5 ohms, winding R0=0.2 ohms, alpha=0.02/K,
Cthermal=0.01 J/K and Rthermal=10 K/W. Duty is
`clamp(5/12+0.04*(5-Vout)+10*integral(5-Vout),0,1)` with forward-Euler integral,
sample/hold average source and native BE electrical/thermal steps. It starts
with zero electrical energy and zero temperature rise, with a 300 K ambient.

All electrical element powers enter the ledger: ideal source delivery, winding
Joule heat deposited into its thermal node, external load dissipation and L/C
storage. BE numerical dissipation is separately accounted as
`0.5*L*(delta I)^2 + 0.5*C*(delta V)^2`; it is not labeled as physical device heat.
Thermal storage and ambient rejection close their own ledger. The combined
ledger counts winding heat once rather than adding it to both physical sinks.

An independently written continuous PI/physical ODE RK4 oracle, resolved at
0.1/0.05 us, supplies a reference limit. Native sampled-BE steps at 20/10/5 us
have normalized endpoint errors 0.0239336/0.0147511/0.00831719, decreasing toward
first order (sampling and integration both contribute). The norm scales I/V/
temperature by 1 A/1 V/1 K and controller integral by 0.1 V*s; it is not a
percent hardware accuracy claim. The finest case gives Vout=4.974746 V and
temperature rise=0.432728 K at 20 ms. The alpha=0 counterfactual gives
4.975238 V/0.430809 K, demonstrating electrical/thermal feedback. Duty stayed
unsaturated and the declared 30 mV endpoint tracking gate passed.

Maximum observed per-step electrical and thermal energy defects were 9.70e-17 J
and 6.07e-16 J. Cumulative electrical, thermal and combined ledgers passed their
predeclared tolerances. The extended target rebuilt with MSVC `/W4 /WX`, passed
standalone and CTest, and was independently rerun by the integrating owner.
This is an original synthetic averaged benchmark and a reproducible native
controller/session example. It does not establish transistor switching losses,
IBIS/SPICE semiconductor model validity, board geometry, installed cooling,
EMI fields or measured converter correlation.

Code, equations, synthetic data and analytical oracles were independently authored.
No external solver implementation or vendor model source was adapted/copied into
the repository. The power-electronics evidence-review procedure keeps model
compatibility, numerical convergence and physical applicability separate.
Knowledgeable human numerical review and wider release checks remain required.

## Actual native PWM with winding thermal feedback (2026-10-09)

`python/spike_core/pwm_electrothermal.py` adds `validate_pwm_electrothermal`
(strict preflight only) and `run_pwm_electrothermal` (actual native execution).
The request/result schemas are `schemas/pwm-electrothermal-*-v1.schema.json`.
PI and Thermal consumers can share this worker-callable API without owning a
second numerical implementation. Transport/UI registration is a separate
integration task; successful backend execution does not establish UI deployment.

The supported circuit is a synchronous buck with ideal complementary 0/1 V
gate commands, finite smooth behavioral switches (Ron=0.02 ohm, Roff=1 Mohm,
threshold=0.5 V, transition=0.01 V), 100 uH/100 uF, 5 ohm external load,
and a 0.2 ohm winding with temperature coefficient 0.02/K and lumped
0.01 J/K, 10 K/W thermal dynamics at 300 K ambient. Only winding Joule power
enters the thermal node; both switch and load losses remain explicit external
sinks. There is no inferred semiconductor switching heat or thermal mapping.
The winding constitutive envelope allows 1 K below ambient for Newton trial
states, while accepted self-heating output must not undershoot ambient.

At 20 kHz, PI samples the previous cycle endpoint. Duty is
`clamp(5/12 + 0.04*(5-Vout) + 10*q, 0.05, 0.95)`, then
`q += period*(5-Vout)`. Each high/low interval is split into
`ceil(interval/maximum_step)` equal BE steps, so no step crosses a gate edge.
Controller saturation is reported through duty; no anti-windup or arbitrary
controller stability qualification is implied. Native electrical/thermal
unknowns remain in the same persistent MNA session through all windows.

Independent reference: eliminate the half-bridge using
`Vth=Vin*gH/(gH+gL)`, `Re=1/(gH+gL)`, then integrate
`L*i' = Vth - (Re+Rw(T))*i - v`, `C*v' = i-v/Rload`,
`Cth*theta' = Rw(T)*i^2-theta/Rth` with independently authored RK4 at exact
PWM edges and identical sampled controller policy. Reference step refinement
is checked separately from native BE. At 20 ms, native 2/1/0.5 us endpoint
errors against the independent switched reference are
0.00600835/0.00350091/0.00189303 (same dimensionless norm as above).
The finest result is 4.970910514 V, 0.529474353 K winding rise. Maximum
observed per-step energy residual is 6.36e-18 J in this fixture. These are
numerical/model-reference results, not percentage hardware accuracy.

Electrical energy sums source work, high/low switch loss, external load loss,
winding heat, physical L/C storage and separate BE numerical dissipation.
Thermal energy sums winding input, Cth storage and ambient removal. Both local
and cumulative balances fail closed. Returned cycle frames include actual gate
edge times, endpoint current/voltage/temperature, sampled within-cycle extrema
and per-window losses; they are not spatial fields or spectral EMI results.

Cancellation publishes only completed cycle windows and their last committed
checkpoint token. Mid-cycle state/losses are discarded from publication.
Portable restart is deterministic replay, bound to full normalized parameters,
native library digest and committed state/controller/energy digest. It never
loads user-supplied native memory. Tampered or changed-build tokens are rejected;
no replay speedup is claimed. Native in-process checkpoint/controller/source
restoration is independently exercised by the C++ benchmark.

A stiff gate-step startup defect required a narrow kernel predictor: only
degree-one grounded independent sources directly driving switch control nodes
seed their prescribed endpoint in the Newton guess, after dynamic history is
captured. Domain errors revert to the old guess. Predictor-only convergence
also reverts, preventing skipped rank checks in disconnected singular circuits.
Residual tolerances and the thermal ledger are unchanged. Reversed sources,
parallel contradictory/identical sources and a zero-residual singular subsystem
have regression coverage. The averaged model remains separately tested.
An explicitly forced sparse session matches the dense switching state and
energy ledger. This check also exposed missing sparse diagnostic accumulation
in persistent sessions; sparse assembly/factorization counters now propagate
from each native solve instead of incorrectly remaining zero.

Reproduce with the normal native build and an actual DLL/shared-library:

```powershell
cmake --build build-peec-native --target test_spikes_pwm_electrothermal spikes_c_api
ctest --test-dir build-peec-native -R '^test_spikes_' --output-on-failure
$env:SPIKE_PWM_TEST_LIBRARY = (Resolve-Path build-peec-native/spikes_c_api.dll).Path
.venv/Scripts/python.exe -W error -m unittest discover -s tests/python -p test_pwm_electrothermal.py -v
# Build the owned worker library as well before using the default adapter.
cmake --build build-spikes-hybrid --target spikes_c_api
.venv/Scripts/python.exe examples/converter/run_pwm_electrothermal.py --output-dir build/pwm-electrothermal-20261009-v2
```

The example retains original inputs, numerical outputs, independent native
reference output and source/binary/artifact hashes. No external implementation,
vendor model, dataset or fixture was copied. The method is independently derived
from circuit KCL/KVL, Joule heating and discrete BE energy identities, not claimed
as novel research. Deadtime, gate charge, vendor compact models, semiconductor
thermal feedback, spatial cooling, hardware correlation and knowledgeable human
numerical release review remain outside this qualification.

Final local verification for this slice: 8/8 Python-to-native integration tests
passed with warnings treated as errors; 10/10 native SPikes CTests passed;
architecture/documentation/whitespace checks passed. Three-resolution example
artifacts in `build/pwm-electrothermal-20261009-v2` have verified source and
artifact hashes. The earlier v1 bundle is retained historical evidence, not
current-source evidence after sparse diagnostic/regression changes.

The broader Python run executed 2,972 tests with one failure and 22 skips.
Its process-local temporary directory was inside this Git repository, making
the non-repository worktree fixture a real repository descendant. All five
worktree tests passed when rerun with the normal external temporary directory.
No product worktree behavior or assertions were changed to conceal this runner
error. Do not use a repository-local global temp directory for Git-boundary
fixtures. The complete suite was not rerun under the corrected temp setting;
these results are not a green full-suite or portable release claim.
