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
