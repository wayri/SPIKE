<!-- SPDX-License-Identifier: Apache-2.0 -->
# Finite SI/PI execution queue — 25 October 2026

## Scope and status rule

This queue covers the 14 primary parity families, SI01–SI08 and PI01–PI06.
On 25 October, a direct ID comparison found 63 capability-family rows in both
the current [capability backlog](parity-capability-backlog-v1.json) and the
capability tables in the current
[roadmap](HYPERLYNX_PARITY_AND_MULTIPHYSICS_PLAN.md), with no ID difference.
The roadmap's narrative references to 68 broad rows are therefore stale counts,
not five additional current family rows. Six `Start01`–`Start06` milestones are
separate from the family IDs. This count finding does not alter the 14-family
SI/PI queue. A verified bounded stage is
evidence for that stage only. Family parity requires every original target and
open gap to have an accepted family benchmark and applicable external physical
evidence. Release readiness is evaluated separately against human review and
the exact installed candidate; it is not an implementation prerequisite.

Evidence was read from the backlog, the [parity execution record](PI_SI_PARITY_EXECUTION.md),
the [subsystem index](SUBSYSTEM_INDEX.md), [solver status](SOLVER_STATUS.md), and
the linked dated validation records. Existing status words are reported as
ledger state, not recomputed completion claims.

Dependency labels used below are:

- **Independent**: useful bounded work can proceed without SI08 family closure.
- **Uses SI08 kernel**: may use an already verified bounded SI08 interface, but
  does not depend on physical SI08 closure.
- **SI08 physical dependency**: the family claim needs calibrated, measured
  network evidence from SI08 even though software work can proceed.
- **External**: requires evidence, rights, equipment or operating information
  that the repository cannot manufacture.
- **Release**: requires human review, packaging or installed-runtime evidence;
  it is not an implementation dependency.

## SI08 finite closure lane

SI08 remains `in_progress`. Its current bounded evidence comprises explicit
mixed-mode pairing; supplied two-port and coupled 2N-port fixture removal;
explicit resampling/DC; supplied stable-pole fits; native multiport workflow
evidence; one-port calibration; and port-separable 2–4-port known-standard
calibration with supplied joint covariance. See the
[family checklist](SI08_FAMILY_CLOSURE.md),
[multiport integration record](validation/SI08_MULTIPORT_INTEGRATION_20261024.md),
[one-port record](validation/SI08_CALIBRATION_FOUNDATION_20261024.md), and
[multiport calibration record](validation/SI08_MULTIPORT_CALIBRATION_20261024.md).
These stages do not establish source causality, general broadband passivity,
measured accuracy, or installed-release qualification.

The authoritative finite work and IDs are frozen in
[`si08-closure-checklist-v1.json`](si08-closure-checklist-v1.json). This queue
does not redefine them. Their roles are:

| Checklist IDs | Role | Blocking boundary |
| --- | --- | --- |
| I01–I04 | Named interoperability/pairing, causality/resampling/DC policy, operational calibration, and joint calibration/fixture uncertainty. | Internal implementation. I01, I02 and I04 are verified by current source-bound campaigns. I03 remains open. None establishes measurement validity. |
| I05–I06 | Automatic passive causal broadband fitting and its loaded transient use. | Internal numerical work; I06 depends on I05. Existing supplied-pole and SI07 stages are prerequisites, not closure. |
| I07–I08 | Complete desktop/saved workflow and one machine-checked integrated implementation manifest. | Internal integration. `implementation_complete` requires every I01–I08 receipt current and passing. |
| E01–E02 | Characterized standards/measurement corpus, followed by independent measured correlation and applicability review. | **External blocker:** suitable measurements, instrument/standard state, uncertainty budgets and source rights are not established by synthetic fixtures. `full_family_complete` requires both gates. |
| R01–R02 | Knowledgeable human numerical review, followed by exact installed-candidate qualification. | **Release blocker:** agent review cannot satisfy R01; the recorded installer predates current calibration work. `release_ready` requires both gates for the exact candidate. |

The checklist distinguishes `implementation_complete` (I01–I08),
`full_family_complete` (I01–I08 plus E01–E02), and `release_ready` (all earlier
gates plus R01–R02). Until E01 exists, internal completion must retain the
external gates as pending rather than substituting synthetic data.

## All-family execution queue

| Order | Family and current bounded evidence | Next finite deliverable and verification | Real dependency or blocker |
| ---: | --- | --- | --- |
| 1 | **SI01 — `in_progress`.** SI01-S01 retains the complete finite supplied scalar line/corner population and sampled gain witnesses in [SI candidate study](SI_CANDIDATE_STUDY.md). | **SI01-S02 reviewed sampled-constraint manifest.** The isolated implementation in `python/spike_core/solvers/signal_integrity/networks/si_candidate_constraints.py` binds exact source/result digests, explicit accept/hold/reject review, original supplied limits and recomputed witnesses. `tests/python/test_si_candidate_constraints.py` supplies independent success/failure fixtures; `scripts/verify_si_candidate_constraints.py` checks stable sources and complete zero-skip inventory. Integration remains pending, so this is not yet a ledger stage or SI01 completion. Then define one topology contract and one geometry-backed constraint fixture as the next separate stage. | **Independent.** Native-layout application, geometry extraction, continuous-band validity and measurement remain open. Release needs human review. |
| 2 | **PI01 — `in_progress`.** Bounded pad, finite-contact, precision partition, land transition, annular contact and board-volume/scalable evidence exists. The [scalable record](validation/PI01_SCALABLE_20261024.md) reaches 39,675 tetrahedra but heat/p99 refinement is unstable; EBrake24V and full Marble+1V0 exceed current budgets. | Finish the already-defined PI01-S02 board acceptance: run unchanged frozen gates on scalable conforming volume/trace solves, retain vector current and unique-volume density, and resolve or explicitly bound contact/barrel ownership. Verification is source-pinned EBrake/Marble resistance, KCL, Joule/work, heat/p95/p99 refinement, resource and cross-method checks. | **Independent of SI08.** Internal blockers are convergence/resource scaling. **External:** representative operating terminals/materials and measured voltage/current/temperature correlation. Release needs numerical review. |
| 3 | **SI02 — `in_progress`.** Thirteen bounded stages cover supplied scalar/coupled lines, fields, cascades/stars and physical RLC terminations; the [execution record](PI_SI_PARITY_EXECUTION.md) keeps geometry, returns and discontinuities open. | Admit one source-bound post-layout channel class with explicit conductor pair, reference plane, bends/layer changes and unextracted intervals. Verify exact retained source geometry, modal/physical port identity, DC and analytic straight-section limits, mesh/refinement, interface power/loss, and fail-closed unsupported geometry. | **Independent** for geometry and field extraction. **Uses SI08 kernel** only for optional exported sampled networks. **External:** materials/stackup and measured channel correlation for qualification. |
| 4 | **SI04 — `planned`.** `python/spike_core/solvers/signal_integrity/receivers/si_ibis.py` inventories IBIS and performs an explicit single DC-slope/ramp reduction; nonlinear switching, clamps and waveform execution are absent. | SI04-S01: execute a bounded static nonlinear I/V endpoint with pullup, pulldown and clamp contributions at explicit typ/min/max conditions, without time-domain switching. Freeze the applicable IBIS specification sections and independent piecewise-interpolation/KCL fixtures first; verify duplicate axes, extrapolation rejection, power sign and retained unsupported keywords. | **Independent.** **External:** rights-reviewed vendor models and bench switching correlation. Nonlinear time-domain V/T behavior is a later stage. |
| 5 | **SI05 — ledger `planned`, later bounded baseline exists.** [SI execution evidence](validation/SI_EXECUTION_20261023.md) records a trusted-development Windows x64 AMI host, synthetic Init/GetWave/Close checks and generic sampled-FIR PAM3; it is not a generic sandbox, vendor qualification or protocol compliance. | Freeze SI05-S01 around a redistributable original reference model: parameter sweep, Init/GetWave partition invariance, CTLE/FFE/DFE state, deterministic jitter/noise injection, clock recovery and analytical BER/SER only where its assumptions apply. Verify native lifecycle, time units, impulse area, block invariance, crash/timeout/cancel and tail-relative errors. | **Independent** for original/synthetic reference work. **External:** verified isolated VM, vendor model terms/binaries, protocol fixtures and measured SerDes data. Installer inclusion is a release gate. |
| 6 | **PI03 — `in_progress`.** [Operating corners](PDN_DECAP_CORNERS.md) and [bounded BOM selection](PDN_DECAP_SELECTION.md) retain supplied C/ESR/ESL, costs, inventory, rejected populations and sampled target failures. | PI03-S03: supplied-site sensitivity on an explicit passive port network. Enumerate the bounded site/part population, retain every rejection, and verify independent nodal results, permutation invariance, port-distance sensitivity, sampled resonance witnesses and resource limits. Do not infer manufacturer bias laws or continuous-frequency closure. | **Independent** on supplied networks; physical placement depends on PI02 geometry extraction. **External:** rights-reviewed part bias/temperature/tolerance data and measured board impedance. |
| 7 | **PI04 — `in_progress`.** PI04-S01 verifies inductive-cutset PWL consistency; PI04-S02 verifies simultaneous supplied loads and shared return accounting in [the execution record](PI_SI_PARITY_EXECUTION.md). | PI04-S03: one bounded nonlinear switching-load subset with explicit state/event law and package/return network. Freeze equations and an independent analytic or high-accuracy ODE reference; verify event timing, charge/work, timestep convergence, simultaneous loads, cancellation and unsupported model rejection. | **Independent** for the bounded source/network reference. Broadband N-port coupling later **uses SI08 I05/I06**; measured SSN needs external package/board data. |
| 8 | **PI05 — `planned`.** [Engineering review](ENGINEERING_REVIEW.md) has contextual checks, return-path tools and evidence export, but no versioned electrical ruleset or coverage benchmark. | PI05-S01: versioned neutral geometric-rule inventory and coverage engine on original synthetic fixtures. Each finding must retain rule/version, geometry identity, evidence, severity, waiver state and cross-probe target; verify positive/negative/waived cases, unsupported coverage and deterministic export. | **Independent.** Actual EDA DRC/ERC comparison and proprietary commercial rules are **external**; do not call this HyperLynx-class coverage. |
| 9 | **PI06 — `planned`.** [Sourced power qualification](SOURCED_POWER_QUALIFICATION.md) bounds behavioral PWM electrothermal and sourced-model checks; real controller/device startup/protection and measured correlation remain open. | PI06-S01: one declared converter/controller subset with explicit deadtime, startup and protection state transitions plus semiconductor temperature feedback. Freeze governing equations/source versions and independent steady/transient oracles; verify event order, energy/loss balance, timestep/refinement, SOA rejection and failed startup. | **Independent of SI08.** **External:** rights-reviewed real controller/device data, parasitics and calorimetric/electrical measurements. Human numerical review required. |
| 10 | **SI07 — `in_progress`.** Ten stages cover initialized rational transients, R/L/C boundary states, continuous work/heat/storage, sampled multi-aggressor envelopes, finite skew corners and apparent port reflectometry. | SI07-S11: a finite timing/noise-budget ledger over supplied initialized networks. Retain individual aggressor, deterministic jitter and noise terms plus direct fixed-pattern witnesses; verify budget reconstruction, timing-grid refinement, state continuation and no pass from incomplete coverage. | **Uses SI08 kernel** for supplied fitted networks but does not require SI08 physical closure. Spatial TDR/VNA accuracy has an **SI08 physical dependency** and external measurement gate. |
| 11 | **SI03 — `planned`.** Only bounded optional EM/network workflows exist; no verified parity stage qualifies vias, launches, connectors or packages. | SI03-S01: compose one explicit analytic/supplied multiport discontinuity between named reference planes and adjacent channel ports. Verify port/sign/reference identity, cascade/de-embedding round trip, power/passivity diagnostics, permutation, and rejection of missing stitched-return identity. | Software stage **uses bounded SI08 kernels** and can proceed now. Calibrated fixture/package claims have an **SI08 physical dependency** plus external geometry and measurement data. |
| 12 | **PI02 — `in_progress`.** Four stages cover finite dielectric admittance, passive sampled reduction, conservative dielectric heat and bounded conductivity-temperature feedback. | PI02-S05: one bounded plane/via/package multiport extraction with explicit return geometry and a refinement family. Verify electrostatic/MQ or analytic references, matrix symmetry/passivity, terminal power, field-energy/loss, mesh refinement and retained source ownership. | Raw extraction is **independent**. Passivity-preserving causal broadband reduction depends on **SI08 I02/I05**. **External:** real stackup/material dispersion and measured PDN correlation. |
| 13 | **SI06 — `planned`.** The ledger has no qualified DDR interface stage; declarative setup entries do not establish read/write timing or protocol compliance. | SI06-S01: supplied-requirement DQ/DQS/clock timing ledger for one explicitly named mode, with read/write direction, byte-lane identity, ODT state and complete finite corners. Verify analytical edge placement, setup/hold accounting, unit conversions, missing-corner rejection and exact requirement provenance. | Can start on original synthetic waveforms, but useful channel behavior depends on SI02 and nonlinear model binding on SI04. **External:** licensed/versioned JEDEC requirements, controller/DRAM models and bench correlation. |
| 14 | **Family closure and release.** All 14 families remain open regardless of bounded-stage count. | For each family, freeze a manifest mapping every original backlog target/gap to an accepted benchmark, exact source version, observables, units, tolerances and evidence. Run required focused and full checks only after integration, then package/current-installer checks and knowledgeable human review. | **Release.** No family promotion from roadmap text, UI availability, source presence, synthetic stages, or another family's passing evidence. |

## Immediate work allocation

The current non-overlapping sequence is:

1. Integrate/review the isolated SI01-S02 candidate after its focused evidence is
   accepted; do not update the ledger merely because local tests pass.
2. Continue PI01-S02 with its frozen board gates and SI08-I04/checklist
   coordination in their existing owner tasks.
3. Start one independent bounded stage from SI04, PI03, PI04, PI05 or PI06.
   SI04-S01 and PI05-S01 have the least dependency on board data or SI08.
4. Start SI03/PI02 composition only with explicit reference-plane/return
   contracts; reserve physical promotion for SI08-E01 evidence.
5. Stop SI08 internal development at an explicit external-pending state after
   I01–I08 pass. Resume physical/release closure only when E01 evidence and the
   current release payload exist.

This ordering preserves the original targets while preventing SI08 equipment,
measurement and release gates from idling independent SI/PI development.
