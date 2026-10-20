# PI/SI parity execution

PI01–PI06 and SI01–SI08 remain the primary parity program. On 18 October 2026,
the user authorized the parallel [coupled mechanics/magnetics/devices track](COUPLED_MECHANICS_MAGNETICS_DEVICES_PLAN.md).
The follow-up [vibration/vehicle/mechanism scope](VIBRATION_VEHICLES_AND_MECHANISMS_PLAN.md)
extends this exception with explicit dependencies and validation gates.
Its exact machine-policy exception preserves the original full-parity gate.
Large HVDC infrastructure, full radio systems and wave optics retain that gate.
Completed placement evidence remains retained and its unfinished parents stay
open. No whole capability family becomes complete from one bounded stage.

Current steering also prioritizes reusable multiphysics handoffs within this
work: [conservative dielectric-to-thermal transfer](PDN_DIELECTRIC_THERMAL.md)
connects actual electrical loss and temperature while preserving the original
parity gate. General solver-suite expansion remains separately qualified.

| Order | Stage/work | Acceptance and remaining scope |
| --- | --- | --- |
| 1 | SI08-S01: explicit mixed-mode port pairing | Independent polarity, voltage/current, reference and power invariants; exact port partition, no input mutation. |
| 2 | PI04-S01: inductive-cutset transient consistency | Exact finite-rise RL voltages, slope-corner convention, refinement and retained RC/energy/failure checks. |
| 3 | PI04-S02: simultaneous load waveforms | [Independent loads](PDN_SIMULTANEOUS_LOADS.md), shared return and superposition/energy references. |
| 4a | PI02-S01: finite dielectric AC admittance | [Actual lossy complex fields](PDN_DIELECTRIC_AC.md), layered/multielectrode references, passive power and current conservation. |
| 4b | PI02-S02: passive sampled port reduction | [Explicit auxiliary loads](PDN_ADMITTANCE_REDUCTION.md), power identity and extraction-to-worker references. |
| 4b.1 | PI02-S03: dielectric loss to temperature | [Conservative same-mesh coupling](PDN_DIELECTRIC_THERMAL.md), coherent RMS drive, power balance and heated-slab temperature references. |
| 4b.2 | PI02-S04: conductivity-temperature feedback | [Cellwise supplied laws](PDN_DIELECTRIC_FEEDBACK.md), bounded iteration, raw residuals and an independent coupled discrete reference. |
| 4b.3 | PI03-S01: supplied decap operating corners | [Supplied C/ESR/ESL corners](PDN_DECAP_CORNERS.md), full network response and retained sampled target failures. |
| 4b.4 | PI03-S02: bounded BOM-constrained selection | [Finite supplied search](PDN_DECAP_SELECTION.md), inventory/cost/count admission, complete population evidence and independent ranking. |
| 4c | PI01–PI03 remaining | Board DC geometry/contact coverage; broadband plane/via/package and causal model reduction; physical decap studies and measured references. |
| 5 | SI01–SI03, SI07 | Topology/corners/constraints, transmission-line branches/returns/discontinuities, multiaggressor eyes/TDR and calibrated network composition. |
| 5a | SI08-S02: explicit two-port fixture removal | [Oriented supplied fixtures](TWO_PORT_DEEMBEDDING.md), exact grids/references, conditioned solves and independent wave-connection recovery. |
| 5b | SI08-S03: explicit sampled grids and DC | [Cartesian-linear preparation](SPARAMETER_RESAMPLING.md), source/supplied real DC, exact sample preservation and delayed-line refinement evidence. |
| 5c | SI08-S04: supplied stable-pole rational fit | [Real rational model](SPARAMETER_RATIONAL_FIT.md), explicit stable poles, enforced sample error and independent time/frequency references. |
| 5d | SI07-S01: prescribed-wave rational transients | [Executable PWL waveforms](RATIONAL_NETWORK_TRANSIENT.md), simultaneous ports, stable exact interval propagation and independent matrix-exponential references. |
| 5e | SI07-S02: resistively terminated transients | [Explicit Thevenin feedback](TERMINATED_NETWORK_TRANSIENT.md), loop/stability admission and physical RC/divider references. |
| 5f | SI07-S03: mixed resistive/series-inductive transients | [Referenced R/L state boundaries](INDUCTIVE_NETWORK_TRANSIENT.md), physical RLC/multiport and energy checks, actual derivative/loss/storage outputs and regular stable closure admission. |
| 5g | SI07-S04: mixed resistive/shunt-capacitive transients | [Referenced R/shunt-C boundaries](CAPACITIVE_NETWORK_TRANSIENT.md), distinct source/network current, KCL and actual resistor-loss/capacitor-energy checks with independent parallel-RLC references. |
| 5h | SI07-S05: combined series-R/L and shunt-C transients | [Referenced combined states](RLC_NETWORK_TRANSIENT.md), simultaneous KVL/KCL, independent loaded-RLC/coupled-port and energy checks. |
| 5i | SI07-S06: supplied initial states and continuation | [Referenced initial-value model](RLC_INITIAL_STATES.md), charged/energized physical references, nonzero fitted memory and explicitly resliced PWL split-run checks. |
| 5j | SI07-S07: continuous work/heat/storage ledger | [Referenced covariance integration](RLC_ENERGY_LEDGER.md), analytic heat/work, signed power, interval/total balance and split/refinement checks for future conservative coupling. |
| 5k | SI07-S08: sampled multi-aggressor crosstalk | [Biased linear attribution](MULTI_AGGRESSOR_CROSSTALK.md), finite signed-family voltage envelopes and two direct fixed-pattern witnesses; sampled-only coverage. |
| 5l | SI07-S09: supplied timing/skew corners | [Endpoint-held shifted PWL sources](CROSSTALK_TIMING_CORNERS.md), same-state finite corner/polarity envelopes and directly verified global witnesses; aggregate pre-fit budgets. |
| 5m | SI07-S10: initialized network-port reflectometry | [Actual port waves and current](NETWORK_REFLECTOMETRY.md), apparent reflection/impedance with explicit unresolved floors and signed transported power; analytic/physical references. |
| 5n | SI02-S01: distributed lossless TEM line transient | [Causal traveling waves](LOSSLESS_LINE_TRANSIENT.md), supplied uniform L/C/length, explicit resistive ends, repeated reflections and named interior V/I/power/energy probes. |
| 5o | SI02-S02: distortionless distributed line losses | [Explicit Heaviside model](DISTORTIONLESS_LINE_TRANSIENT.md), delayed attenuation, conductor/dielectric W/m loss channels, stored-energy distinction and independent PDE/energy checks. |
| 5p | SI02-S03: supplied uniform sampled RLGC network | [Independent R/G frequency samples](RLGC_LINE_NETWORK.md), stable two-port evaluation, explicit DC, sampled passivity/reciprocity and compatible network handoff. |
| 5q | SI02-S04: driven sampled RLGC fields and loss ledger | [Coherent RMS two-end fields](RLGC_LINE_FIELDS.md), named local V/I/storage/loss probes, analytic conductor/dielectric integrals and whole-line power balance. |
| 5r | SI02-S05: supplied piecewise RLGC cascade | [Ideal series junctions and coherent local fields](RLGC_LINE_CASCADE.md), interface continuity/flux, external two-port and section-resolved loss without double counting. |
| 5s | SI01-S01: finite pre-layout candidate/corner comparison | [Explicit supplied scalar lines](SI_CANDIDATE_STUDY.md), complete case coverage, sampled gain limits and exact witnesses; editor, geometry and layout constraints remain open. |
| 5t | SI02-S07: supplied symmetric coupled pair | [Orthogonal even/odd composition](RLGC_COUPLED_PAIR.md), four-port crosstalk, coherent conductor fields and conservative pair loss; geometric extraction and thermal ownership remain open. |
| 5u | SI02-S08: physical source/load termination of a supplied pair | [Conditioned resistive feedback](RLGC_TERMINATED_PAIR.md), loaded V/I and separate source/resistor/line power; reactive/ideal endpoints and physical thermal allocation remain open. |
| 5v | SI02-S09: physical reactive source/load termination of a supplied pair | [Sampled series-R/L and shunt-C closure](RLGC_REACTIVE_PAIR.md), independent physical-state/ABCD references and separate heat W, mean energy J and reactive var; general topology and physical thermal allocation remain open. |
| 5w | SI02-S10: supplied piecewise coupled-line cascades | [Physical conductor-continuous connection](RLGC_COUPLED_CASCADE.md), actual section fields and conservative section heat; independent spatial-chain/quadrature references. |
| 5x | SI02-S11: physical RLC loaded coupled cascades | [Explicit source/load voltage closure](RLGC_LOADED_CASCADE.md), actual section fields and separate terminal/section heat, mean energy and reactive power. |
| 5y | SI02-S12: ideal supplied coupled-line stars | [Two-conductor branch continuity](RLGC_COUPLED_STAR.md), coherent leg fields, separate branch heat and node power/KCL residuals. |
| 5z | SI02-S13: physical RLC loaded coupled stars | [Complete physical endpoint closure](RLGC_LOADED_STAR.md), branch fields, separate terminal/branch heat and mean/reactive energy, with a verified cancellation-integrity correction. |
| 6 | SI08 remaining network quality | Explicit frequency/DC policies, causality evidence, fixture removal and passive causal fitting. |
| 7 | SI04–SI06 | Nonlinear IBIS, statistical/AMI and complete DDR workflows with applicable model and normative evidence. |
| 8 | PI05–PI06 and stack closure | Close every declared gap and accept family benchmarks before calling the PI/SI stack complete. |

This ordering is executable development priority, not a delivery estimate or
claim of commercial-tool parity. The capability ledger retains detailed gaps.

## SI08-S01 API and derivation

`python/spike_core/sparameter_modes.py` owns `mixed_mode_network`. A caller
supplies a `NetworkData`, ordered zero-based `(positive, negative)` pairs, an
ordered list of all unpaired ports and optional unique physical port names.
The result contains a separate derived network and ordered physical mapping.

```python
from python.spike_core.sparameters import read_touchstone
from python.spike_core.sparameter_modes import mixed_mode_network

source = read_touchstone("measured.s4p")
modes = mixed_mode_network(source, [(0, 2), (1, 3)])
# modes.network is independent; retain modes.port_mapping with any export.
```

Output ports are all differential modes, all common modes, then single-ended
ports. `S[receiver, source]` and frequency units Hz remain unchanged.

For equal real single-ended reference R within each pair, define
Vd=Vp−Vn, Id=(Ip−In)/2, Vc=(Vp+Vn)/2, Ic=Ip+In. Differential and common
references are respectively 2R and R/2. With real-reference power waves
a=(V+RI)/(2√R), the differential wave is (ap−an)/√2 and common wave is
(ap+an)/√2; outgoing waves obey the same basis change. Thus S'=U S Uᵀ,
where U is orthogonal, including identity rows for unpaired ports. This
preserves wave power, singular values and reciprocity to floating-point
roundoff. Its condition number is one; no inverse solve or convergence
iteration is introduced for S input.

The impedance normalization agrees with the measurement convention in the
[Keysight balance conversion guide](https://helpfiles.keysight.com/csg/e5071c/measurement/fixture_simulator/evaluating_balanced_devices_balance_unbalance_conversion.htm)
and [instrument manual](https://www.keysight.com/ci/en/assets/9018-05241/user-manuals/9018-05241.pdf).
The derivation, implementation and synthetic tests are independently authored;
no external code, examples or fixtures were used.

Tests independently establish a five-port transfer's polarity and ordering,
the exact transformed impedance of two unequal device impedances, and retained
power/reciprocity/legacy behavior. Reference impedances may differ between
pairs. Unequal references within a pair, complex references, missing or reused
ports, nonfinite matrices and invalid frequency grids fail explicitly.
Bounds: 64 ports, 32769 samples and 4194304 matrix entries. Real nonnegative
strictly increasing grids can be nonuniform; no resampling is inferred.
Original warnings remain warnings; active networks are not repaired.

Use this Python API through the existing script workspace; automatic desktop
mixed-mode traces retain their existing adjacent-pair behavior. Save the
physical mapping alongside an exported derived network: Touchstone alone does
not retain this companion mapping. This stage does not qualify causality,
geometry extraction, nonlinear devices or measured signoff.

## PI04-S01 transient consistency

The supplied linear passive PDN descriptor solves E x'=−A x−B u. A zero
stored-energy initial state can still need nonzero algebraic voltage when the
load starts with a nonzero current slope. Previously setting every unknown to
zero produced a persistent alternating RL voltage error: with R=1 Ω,
L=T=1/1024 H and a 0→1 A ramp over T, the midpoint returned −0.5 V instead
of −1.5 V at four successive refinements, despite zero reported energy error.

`pdn_network.py` now finds constant voltage shifts K on R/C-connected islands
without an R/C path to reference. K spans the joint nullspace of nodal C and
G using topology, avoiding an SI-dependent numerical rank threshold. With coil
incidence F and positive-definite inductance block L, differentiated island KCL
gives H=Kᵀ F L⁻¹ Fᵀ K. A slope change Δs needs
Δv=−K H⁻¹ Kᵀ B Δs. The correction preserves capacitor voltage differences,
coil currents, stored energy and resistor dissipation. It is applied to the
initial slope and subsequent PWL corners; trapezoidal integration stays in use.
This derivation, code and synthetic fixtures are original SPIKE work.

Initial and interior-corner observations use the right derivative. The final
PWL endpoint uses its left derivative. Units remain seconds, amperes, volts
and joules. Nonzero initial current, arbitrary initial stored energy and
nonfinite slopes remain unsupported or rejected. Exactly one supplied load
waveform was supported at this stage; [PI04-S02](PDN_SIMULTANEOUS_LOADS.md)
adds independent simultaneous loads while retaining that original form.

Both consistency solves retain equilibrated conditioning limit 1e12 and
unscaled backward-error limit 1e-10. Admission reserves two additional
system-size cubic work allowances. No pseudoinverse, artificial damping or
passivity repair is introduced. Ill-conditioned/singular systems still fail.

Eight independent stage tests cover exact RL ramp/hold/fall at four refinements,
SI time scales, signed mutual inductance, series RLC charge/energy, floating
capacitor islands, RC convergence, damped RLC and invalid initial/slope input.
The damped parallel RLC reference independently integrates a two-state ODE
with a matrix exponential. Successive maximum voltage errors are
0.019416, 0.004866, 0.001217, 0.0003043 and 0.00007608 V, establishing
approximately second-order convergence. A floating-C fixture separately bounds
algebraic roundoff at 1e-8 V and dynamic error at 3e-6 V; refinement can increase
descriptor conditioning. Energy conservation alone is not waveform validation.
These fixtures do not qualify board extraction, nonlinear regulators, physical
load switching or measured-board behavior.

## Retained stage evidence

SI08-S01, PI04-S01 and [PI04-S02](PDN_SIMULTANEOUS_LOADS.md) are **Done**
for their stated bounded acceptance. PI/SI capability families remain open.
[PI02-S01](PDN_DIELECTRIC_AC.md) is also Done for its twelve finite-domain
complex-field and workflow acceptance checks. Remaining board-scale extraction,
plane/via/package and causal model-reduction gaps remain open.
[PI02-S02](PDN_ADMITTANCE_REDUCTION.md) is Done for explicit passive sampled
auxiliary-port reduction and its nine numerical/workflow checks. Causal fitting
and general board qualification remain separate open work.
[PI02-S03](PDN_DIELECTRIC_THERMAL.md) is Done for coherent loss-to-heat transfer
and actual thermal execution. Its one-way field coupling and computed example
advance the multiphysics foundation without closing the general physics gates.
[PI02-S04](PDN_DIELECTRIC_FEEDBACK.md) is Done for supplied cellwise
conductivity-temperature feedback and raw fixed-point convergence. General
constitutive models, transient stability and hardware correlation remain open.
Their retained receipts are [SI08-S01](validation/parity/SI08-S01.json) and
[PI04-S01](validation/parity/PI04-S01.json). Combined verification on
2026-10-14 passed 60 focused tests with zero skips (13.953 s), including the
PDN worker and SI graph/workflow regressions. Six changed documentation checks
and the 61-family backlog check passed.

The global architecture check remains blocked by unrelated direct native IPC
calls in `app/src/App.tsx` and `app/src/PanelPopupQualification.tsx`. Those files
were not changed for these stages. The full release suite was not rerun; earlier
unrelated broader-suite failures remain outside this bounded acceptance.

During PI04-S02 verification the architecture gate passed, along with
TypeScript compilation and actual desktop single/multi-load backend admission.
Earlier architecture failures above are retained historical results.

`scripts/parity_pisi_gate.py` executes each declared numerical test suite,
records exact test identities and zero-skip results, and binds implementation,
test and runner bytes plus the retained execution log. The backlog checker
rejects stale or incomplete records. These records establish bounded development
acceptance only. Knowledgeable human numerical review remains required before
release under `CONTRIBUTING.md`.

## PI03-S01 supplied decap corners

[Supplied decap operating-corner assessment](PDN_DECAP_CORNERS.md) is **Done**
for ten source-bound circuit, multiport, malformed-input, resource,
cancellation and actual worker/schema/example checks. All seven earlier PI/SI
stage suites were executed again and their canonical receipts refreshed.
The service uses the existing native decap stamp and preserves the supplied
population, source provenance, generated networks and failed target evidence.
Bias and temperature label explicit supplied values; no material law is inferred.
PI03 remains in progress for automatic component models, location extraction,
BOM-constrained optimization and measured validation. Broader multiphysics
remains behind parity, with the prior electrical/thermal foundations retained.

## PI03-S02 bounded decap BOM selection

[Supplied-domain BOM selection](PDN_DECAP_SELECTION.md) is **Done** for ten
source-bound independent circuit/site-effect, ranking, identity, resource,
cancellation and worker/schema checks. All eight earlier PI/SI suites were
executed again and their canonical receipts refreshed. Complete discrete
population evidence and the selected full corner result remain inspectable.
Physical extraction, automatic part models and measured qualification remain
open; the post-parity multiphysics gate remains closed.

## SI08-S02 explicit fixture removal

[Supplied two-port fixture removal](TWO_PORT_DEEMBEDDING.md) is **Done**
for ten source-bound independent wave, ideal-through, active/nonreciprocal,
admission/failure and worker/schema checks. All nine earlier PI/SI suites
were rerun and their canonical receipts refreshed. The derived network retains
explicit ports, references, source snapshots and numerical diagnostics.
Automatic calibration, uncertainty, arbitrary multiport fixture removal and
causality remain open. This stage does not close SI08 or the PI/SI stack.

## SI08-S03 explicit resampling and DC

[Explicit grid preparation](SPARAMETER_RESAMPLING.md) is **Done** for nine
source-bound independent affine/multiport, refinement, passive/active,
precision/resource/cancellation and worker/schema checks. All ten earlier
PI/SI stage suites were rerun and their canonical receipts refreshed. Exact
source samples, supplied DC and every target support/weight remain inspectable.
Causality, fitted broadband models, calibrated uncertainty and broader
qualification remain open; this stage does not close SI08 or the PI/SI stack.

## SI08-S04 supplied stable-pole models

[Supplied-pole rational modeling](SPARAMETER_RATIONAL_FIT.md) is **Done** for
eleven source-bound independent coefficient/state, units/scales, active data,
rank/error/precision/resource/cancellation and worker/schema checks. All eleven
earlier PI/SI stage suites were rerun and their canonical receipts refreshed.
The model is real, proper and stable by construction, with actual sample error
admission. It does not certify source causality, physical broadband accuracy
or general passive fitting. SI08 and the PI/SI stack remain incomplete.

## SI07-S01 prescribed-wave rational transients

[Rational-model waveform execution](RATIONAL_NETWORK_TRANSIENT.md) is **Done**
for eleven source-bound independent ramp/hold, simultaneous-port, V/I/power,
precision/resource/cancellation and worker/schema checks. All twelve earlier
PI/SI stage suites were rerun and their canonical receipts refreshed. The
actual fit result and final states remain part of the returned trajectory.
General source/load feedback, physical out-of-band accuracy, nonlinear models
and measured correlation remain open. SI07 and full PI/SI parity remain incomplete.

## SI07-S02 resistive source/load feedback

[Resistively terminated fitted models](TERMINATED_NETWORK_TRANSIENT.md) are
**Done** for eleven source-bound independent physical RC/divider,
matched/active/stability, precision/resource/cancellation and worker/schema
checks. All thirteen earlier PI/SI suites were rerun with refreshed canonical
receipts. Fit, boundaries and stability/loop residual evidence remain attached
to returned histories. Reactive/nonlinear boundaries, physical out-of-band
accuracy and measured correlation remain open; SI07 and full parity remain incomplete.

## SI07-S03 mixed resistive/series-inductive feedback

[Referenced inductive boundary transients](INDUCTIVE_NETWORK_TRANSIENT.md) are
**Done** for eleven source-bound analytic/PWL RLC, coupled multiport, unit/reference-
impedance, energy, failure and worker/schema/example checks. All fourteen earlier
PI/SI stage suites were executed again and canonical receipts refreshed.
[Verification evidence](validation/SI07_INDUCTIVE_NETWORK_TRANSIENT.md) retains
the mathematical references, measured numerical errors and review limits.
Typed current/derivative, resistor power and inductor energy preserve physical
port/source identity for future coupled studies. Thermal integration and general
capacitive/nonlinear/descriptor boundaries remain separate; SI07 and complete
PI/SI parity remain open.

## SI07-S04 mixed resistive/shunt-capacitive feedback

[Referenced capacitive boundary transients](CAPACITIVE_NETWORK_TRANSIENT.md) are
**Done** for eleven source-bound analytic RC/parallel-RLC, PWL, coupled multiport,
unit/reference, energy, failure and worker/schema/example checks. All fifteen
earlier PI/SI suites were executed again with refreshed canonical receipts;
247 broader focused regression tests passed without skips.
[Verification evidence](validation/SI07_CAPACITIVE_NETWORK_TRANSIENT.md) records
references, numerical errors and review limits. Distinct source/network currents
make supplied resistor heating and capacitor storage explicit for future coupling.
General combined RLC/descriptor/nonlinear boundaries, thermal execution and
measured qualification remain open; SI07 and complete PI/SI parity remain open.

## SI07-S05 combined series-R/L and shunt-C feedback

[Combined RLC boundary transients](RLC_NETWORK_TRANSIENT.md) are **Done** for ten
source-bound analytic damping, nonzero fitted-memory, coupled multiport, energy,
precision/resource/failure and worker/schema/example checks. All sixteen earlier
PI/SI suites were actually reexecuted; 258 broader focused regression tests passed
with zero skips. [Verification evidence](validation/SI07_RLC_NETWORK_TRANSIENT.md)
retains primary references, numerical errors and independent review limits.
Separate source/network currents, KVL/KCL, resistor watts and L/C joules preserve
physical ownership for future coupled studies. General topology/DAE, nonlinear
models, thermal transfer and measured qualification remain open. SI07 and full
PI/SI parity remain incomplete.

## SI07-S06 supplied initial states and continuation

[Initialized RLC transients](RLC_INITIAL_STATES.md) are **Done** for eleven
source-bound analytic free/forced damping, nonzero fitted-memory/energy, multiport,
genuine nonzero-ramp and knot continuation, admission and worker/schema/example
checks. All seventeen earlier PI/SI suites were actually reexecuted; 270 broader
focused regressions passed with zero skips.
[Verification evidence](validation/SI07_RLC_INITIAL_STATES.md) retains primary
references, numerical errors, corrected ramp coverage and independent review.
Typed fit-bound state enables stateless local-time handoffs with explicit source
slicing; final state is at source horizon. Managed sessions, general DAE, thermal
transfer and measured qualification remain open. SI07 and full parity remain open.

## SI07-S07 integrated work, heat and storage

[Continuous RLC energy ledgers](RLC_ENERGY_LEDGER.md) are **Done** for eleven
source-bound analytic/physical integration, mixed-boundary/reference/unit, stiff
doubling, signed-power, split/refinement, admission and worker/schema/example
checks. All eighteen earlier PI/SI suites were actually reexecuted; 282 broader
focused regressions passed with zero skips.
[Verification evidence](validation/SI07_RLC_ENERGY_LEDGER.md) retains reviewed
primary mathematics/physics, numerical errors and independent review. Resistor
heat, signed source/network work and supplied L/C storage keep ownership and
units for later coupling. Generic fitted-network heat, thermal transfer and
measured qualification remain open. SI07 and full PI/SI parity remain incomplete.

## SI07-S08 sampled multi-aggressor crosstalk

[Biased signed-waveform attribution](MULTI_AGGRESSOR_CROSSTALK.md) is **Done**
for nine source-bound analytic/physical, common-state/fixed-driver, finite-family
envelope, direct witness, reference/time-unit, admission and worker/schema/example
checks. All nineteen earlier PI/SI suites were actually reexecuted; 292 broader
focused regressions passed with zero skips. Independent review separately passed
31 numerical/contract checks without an actionable issue.
[Verification evidence](validation/SI07_MULTI_AGGRESSOR_CROSSTALK.md) retains
primary references, error probe, strict schema correction and bounded claims.
Source/state identity supports future coupling, but quadratic heat requires a
full pattern solve. Intersample peaks, timing/BER, nonlinear drivers, thermal
transfer and measured qualification remain open. SI07 and full parity remain open.

## SI07-S09 supplied timing/skew corners

[Explicit delayed aggressor waveforms](CROSSTALK_TIMING_CORNERS.md) are **Done**
for nine source-bound shifted-PWL, physical finite-corner/polarity enumeration,
common-state/fixed-driver, reference/time-unit, observation/set refinement,
admission and worker/schema/example checks. All twenty earlier PI/SI numerical
suites were actually rerun; 302 broader focused regressions passed with zero
skips. Independent review passed 29 numerical/contract checks with no actionable
issue. [Verification evidence](validation/SI07_CROSSTALK_TIMING_CORNERS.md)
retains primary references, numerical errors and exact bounded semantics.
Each corner preserves supplied local-zero state and explicit endpoint holds;
source prehistory is not inferred. Quadratic energy needs a full corner/pattern
solve. Continuous timing search, intersample peaks, probabilistic jitter/BER,
nonlinear drivers and physical correlation remain open. SI07 and full PI/SI
parity remain incomplete.

## SI07-S10 initialized network-port reflectometry

[Actual network-port wave diagnostics](NETWORK_REFLECTOMETRY.md) are **Done**
for nine source-bound analytic/physical V/I/power, source/network-current,
fitted-memory/multiport/state, floor/open/active, reference/time/refinement,
admission and worker/schema/example checks. All twenty-one earlier PI/SI
numerical suites were actually rerun; 312 broader focused regressions passed
with zero skips. Independent review passed 31 numerical/contract checks with no
actionable issue. [Verification evidence](validation/SI07_NETWORK_REFLECTOMETRY.md)
retains reviewed primary physics, numerical errors and exact bounded semantics.
Signed network power preserves the coupling plane but does not define heat.
Instantaneous loaded ratios are not isolated S11 or reconstructed spatial
impedance. Instrument calibration, measured correlation, uncertainty and thermal
deposition remain open. SI07 and full PI/SI parity remain incomplete.

## SI02-S01 causal distributed lossless line transients

[Uniform lossless TEM line execution](LOSSLESS_LINE_TRANSIENT.md) is **Done**
for ten source-bound matched delay, geometric multiple reflections, two-end
excitation/zero-R, local energy/injected-work, unit/refinement, admission and
worker/schema/example checks. All twenty-two earlier PI/SI numerical suites were
actually rerun; 323 broader focused regressions passed with zero skips.
[Verification evidence](validation/SI02_LOSSLESS_LINE_TRANSIENT.md) retains
reviewed primary equations, independently derived causal waves, numerical
errors and independent review. Distributed delay is executed without a fitted
rational approximation or time mesh. Supplied constitutive parameters and probe
positions preserve later coupling identity; stored field energy is not heat.
Lossy/dispersive/coupled/branched extraction, arbitrary initial line history and
physical correlation remain open. SI02 and full PI/SI parity remain incomplete.

## SI02-S02 distortionless distributed line losses

[Constant Heaviside lossy line execution](DISTORTIONLESS_LINE_TRANSIENT.md) is
**Done** for nine source-bound numerical and worker/schema/example checks.
All 23 earlier PI/SI numerical stages were actually rerun; 333 broader focused
regressions passed with zero skips. [Verification evidence](validation/SI02_DISTORTIONLESS_LINE_TRANSIENT.md)
retains primary equations, independent wave/PDE/energy references and numerical
review. Separate conductor/dielectric W/m channels preserve later coupling
identity; stored J/m and signed transported watts remain distinct. Thermal
deposition, temperature feedback, arbitrary/frequency-dependent RLGC, coupled
geometry extraction and measured qualification remain open. SI02 and full
PI/SI parity remain incomplete.

## SI02-S03 supplied uniform sampled RLGC networks

[Uniform sampled RLGC execution](RLGC_LINE_NETWORK.md) is **Done** for eighteen
source-bound numerical and worker/schema/example/handoff checks. All 24 earlier
PI/SI numerical stages were actually rerun; 352 broader focused regressions
passed with zero skips. [Verification evidence](validation/SI02_RLGC_LINE_NETWORK.md)
retains primary phasor telegrapher physics, the independent scaled two-port
derivation, spatial boundary-solve references, finite-ladder convergence and
independent numerical review. Explicit independent sampled R/G removes the
Heaviside constraint for this frequency-domain path. Original constitutive
tables remain attached for later material/coupling work. Sampled passivity is
not broadband causality; geometry extraction, general complex dispersion,
coupled topology, heat deposition and measured qualification remain open.
SI02 and full PI/SI parity remain incomplete.

## SI02-S04 driven sampled RLGC fields and loss ledger

[Coherent RMS field/loss execution](RLGC_LINE_FIELDS.md) is **Done** for fifteen
source-bound numerical and worker/schema/example checks. All 25 earlier PI/SI
numerical stages were actually rerun; 407 broader focused regressions passed
with zero skips. [Verification evidence](validation/SI02_RLGC_LINE_FIELDS.md)
retains primary telegrapher/RMS loss physics, independently derived coherent
waves and analytic spatial integrals, independent spatial/quadrature references,
refinement and numerical review. Probe density does not determine integrated
heat. Separate conductor/dielectric loss and nominal L/C storage retain later
coupling ownership; thermal deposition, feedback, causal material laws,
coupled geometry and measured qualification remain open. SI02 and full PI/SI
parity remain incomplete.

## SI02-S05 supplied piecewise RLGC cascades

[Piecewise supplied line execution](RLGC_LINE_CASCADE.md) is **Done** for
fourteen source-bound numerical and actual worker/CLI/schema/example checks.
All 26 earlier PI/SI numerical stages were actually rerun; 483 broader focused
checks passed with zero skips. The nine runnable SI/PI workflows passed both
before progression and after integration. [Verification evidence](validation/SI02_RLGC_LINE_CASCADE.md)
retains primary interface/phasor physics, the independent connection derivation,
spatial-chain/quadrature oracles, segmentation/impedance-step checks and numerical
review. Complete child fields and separate section heat preserve later thermal
ownership without counting internal transfer as dissipation. Physical branches,
launch/via/bend/return parasitics, geometry/material extraction, thermal mapping
and measured qualification remain open. SI02 and full parity remain incomplete.

## SI02-S06 supplied ideal RLGC star junctions

[Supplied scalar star execution](RLGC_LINE_JUNCTION.md) is **Done** for fifteen
source-bound numerical/worker/CLI/schema/example checks. All 27 earlier PI/SI
numerical stages were rerun, 99 broader regressions passed with zero skips,
and all nine runnable SI/PI cases passed before and after integration.
Independent numerical review ran 15 tests and found no actionable defect.
[Verification](validation/SI02_RLGC_LINE_JUNCTION.md) retains referenced math,
independent physical nodal/spatial and quadrature oracles, strong attenuation,
port/sign invariants and exact bounded scope. Each leg owns its conductor and
dielectric heat; the ideal node adds none. Geometry-derived junction/return
parasitics, arbitrary graphs, coupled conductors, broadband causal materials,
thermal mapping and measured qualification remain open. SI02 and full PI/SI
parity remain incomplete. [Actual-board evidence](validation/BOARD_PISI_READINESS_20261019.md)
retains separate EBrake/Marble limitations and the corrected current Marble DC audit.

## PI01-S01 owned pad DC geometry

[Conservative pad support](OWNED_DRILLED_PAD_DC.md) is **Done** for its
bounded opt-in DC geometry envelope: 28 source-bound numerical/native checks,
67 impacted regressions, and independent geometry/numerical review. Actual
full EBrake 3Vin now executes through the public CLI with all four refinement
levels. The retained source-stable report still fails required p95 density
convergence; original default EBrake density and AC tests also remain failed.
[Evidence](validation/PI01_OWNED_PAD_DC_20261019.md) distinguishes stage
verification from board sign-off. Defaults, thresholds, barrel law and AC
guards are unchanged. PI01-S02 is planned for conservative vector current and
unique-volume density evidence; PI01 and full-board SI/PI remain incomplete.

## SI02-S09: physical reactive source/load boundaries

[Series-R/L and node-shunt-C physical endpoints](RLGC_REACTIVE_PAIR.md) extend
the unchanged supplied symmetric pair. Real resistor/line heat W remains
separate from mean stored energy J, reactive var and signed source VA.
[Verification record](validation/SI02_REACTIVE_PAIR_20261020.md) binds independent
physical-state and scalar ABCD checks, actual worker/CLI/schema/example execution,
review and genuine affected prior replays. General endpoint topology, transient
and causal models, geometry extraction, thermal allocation and original-board
qualification remain open; SI02 and full PI/SI parity remain in progress.

## SI02-S10 supplied piecewise coupled propagation

[Ideal coupled-section composition](RLGC_COUPLED_CASCADE.md) connects supplied
symmetric sections with differing properties, conserving physical conductor
voltage/current and interface power while retaining actual fields and section heat.
[Verification](validation/SI02_COUPLED_CASCADE_20261020.md) records independent
physical spatial-chain/quadrature checks, actual worker/CLI/schema execution and
source-bound promotion. Geometric discontinuity/return parasitics, general
asymmetry/topology, external terminal feedback, causal/transient, thermal mapping
and board qualification remain open. SI02 and full PI/SI parity remain incomplete.

## SI02-S11 physically loaded piecewise coupled channels

[Physical RLC loaded cascades](RLGC_LOADED_CASCADE.md) accept exterior source
voltages and explicit loads around supplied coupled sections. Actual internal
fields, terminal/source currents and section/terminal heat remain distinct from
mean reactive energy. [Verification](validation/SI02_LOADED_CASCADE_20261020.md)
records independent physical RLC/spatial-chain equations, individual heat
quadrature, strict public execution, review and genuine source-bound replays.
General topology/asymmetry, geometric parasitics, ideal/nonlinear/lossy endpoints,
transient/causal, thermal mapping and original-board qualification remain open.
SI02 and full PI/SI parity remain incomplete.

## SI02-S12 supplied coupled star branches

[Ideal coupled stars](RLGC_COUPLED_STAR.md) extend supplied coupled propagation
to 2–8 uniform branches. Two distinct conductor nodes conserve voltage, current
and signed power; actual leg fields and separately owned loss remain explicit.
[Verification](validation/SI02_COUPLED_STAR_20261020.md) records independent
physical boundary/KCL equations, analytic matched stars, quadrature, strict
dimensions, review and genuine source-bound replays. General graphs, asymmetric
or piecewise legs, RLC star endpoints, geometric parasitics, transient/thermal
and original-board qualification remain open. SI02 and full parity are incomplete.

## SI02-S13 physical source/load closure on coupled branches

[Loaded coupled stars](RLGC_LOADED_STAR.md) assign explicit RLC sources/loads
to all exterior ports and retain actual branch fields and separate terminal/branch
heat, mean energy and reactive work. [Verification](validation/SI02_LOADED_STAR_20261021.md)
records physical RLC/node equations, quadratic heat references, strict dimensions,
independent review and genuine replays. A standing-wave false integrity rejection
was corrected with a limited operand roundoff allowance, without changing raw
fields, power checks or original-board gates. Full SI02/PI-SI parity remains open.

## PI01-S02A finite-contact planar DC acceptance

The [analytical benchmark](PI_FINITE_CONTACT_BENCHMARK.md) executes three fixed
refinement levels for four distributed-contact sheet cases, checking resistance,
physical-volume density percentiles and conserved Joule/terminal work. Its
[verification](validation/PI01_FINITE_CONTACT_20261021.md) marks this bounded
offline prerequisite done. Full PI01-S02 remains planned: general rotated
polygon-overlay admission, landing/barrel ownership, original board convergence
and EBrake's unspecified physical contact are unresolved. No new production
solver or board qualification is inferred.

The subsequent [PI01-S02 increment](validation/PI01_GEOMETRY_OWNERSHIP_20261021.md)
verifies explicit precision-grid admission of the actual rotated polygons,
preserving net/contact topology and geometry uncertainty. Supplied coaxial
land/gap ownership now creates fresh face-to-face barrel branches and is checked
with a new reduced DC solve. PI01-S02 is **in progress**, not done: transition
fields, general face patch mappings, physical EBrake electrodes and original
board density/AC qualification remain open.

The next [PI01-S02 land-field increment](validation/PI01_LAND_TRANSITION_20261021.md)
resolves a supplied 3-D rectangular land with independent finite current patches
on all six sides, vector fields, exact reconstructed Joule loss and distinct
conjugate potentials. Harmonic and cosine-series/Gauss references pass. Automatic
annular/source-backed geometry, external circuit coupling, full-board percentiles
and original board qualification still prevent whole-stage completion.
