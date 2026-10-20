<!-- SPDX-License-Identifier: Apache-2.0 -->
# SPIKE progress and remaining goals — 21 October 2026

**38 bounded PI/SI stages verified; 0 of 14 PI/SI families at full parity.** These are different measures: a passed supplied-model stage does not qualify arbitrary geometry, measured predictions or a board. The full roadmap covers 68 capability families; this is not a completion-percentage estimate. The latest stage adds offline verification, not a new runtime solver.

[Source ledger](parity-capability-backlog-v1.json) · [execution roadmap](PI_SI_PARITY_EXECUTION.md) · [solver validity](SOLVER_STATUS.md)

| Family | Family state | Verified stages | Current bounded coverage | Remaining goal |
| --- | --- | ---: | --- | --- |
| SI01: Pre-layout topology exploration and constraints | in_progress | 1 | Finite supplied candidate/corner comparison | Actual topology and constraint workflows; geometry-backed references and family benchmark |
| SI02: General post-layout channel extraction | in_progress | 13 | Supplied scalar/coupled lines, fields, cascades/stars and physical RLC loads | General post-layout extraction, asymmetric/general topology, physical returns/discontinuities and board correlation |
| SI03: Vias, launches, connectors and package discontinuities | planned | 0 | No verified parity stage; baseline approximations remain separate | Qualified vias, launches, connectors, packages and return discontinuities |
| SI04: Nonlinear IBIS driver and receiver behavior | planned | 0 | No verified parity stage; bounded IBIS-related baseline only | Nonlinear driver/receiver behavior, applicable model coverage and validation |
| SI05: SerDes statistical analysis and IBIS-AMI | planned | 0 | No verified parity stage | Statistical SerDes, jitter/equalization and IBIS-AMI with reference suites |
| SI06: DDR full-interface SI and timing verification | planned | 0 | No verified parity stage | Complete DDR topology, timing and protocol/model qualification |
| SI07: Crosstalk, waveform, eye and TDR diagnostics | in_progress | 10 | Bounded transients, RLC states/work/heat, crosstalk, timing corners and TDR | Broader channel/model validity, complete waveform/eye coverage and benchmark closure |
| SI08: Network quality and interoperability | in_progress | 4 | Mixed modes, fixture removal, resampling and supplied stable-pole fitting | Broader causal/passive fitting and interoperable quality qualification |
| PI01: Board DC drop, current density and via loading | in_progress | 2 | Bounded drilled/custom-pad DC; rotated precision benchmark; rectangular and axisymmetric annular land fields; native circular-pad authentication and fresh passive barrel/circuit ports | General board contact mapping, pointwise interfaces, vector/unique-volume full-board density, full rails, EBrake/Marble acceptance and measurements |
| PI02: Broadband AC PDN extraction | in_progress | 4 | Dielectric AC admittance, reduction, conservative heat and conductivity feedback | General broadband plane/via/package/return extraction, causal reduction and physical validation |
| PI03: Physical decap selection and placement optimization | in_progress | 2 | Supplied decap operating corners and bounded BOM-constrained selection | Geometry-backed placement/selection and measured target closure |
| PI04: Switching loads, SSN and circuit/field interaction | in_progress | 2 | Inductive-cutset consistency and simultaneous supplied loads | General SSN and switching circuit/field interaction with applicable references |
| PI05: SI/PI/EMI/safety electrical DRC | planned | 0 | No verified parity stage | Traceable SI/PI/EMI/safety electrical DRC and coverage benchmarks |
| PI06: Power-circuit and converter model completeness | planned | 0 | No verified parity stage; circuit/converter baselines remain separate | Complete power-circuit/converter model, load/fault and validation coverage |

## Actual-board readiness

**EBrake is not qualified.** The original owned-mode CLI and four mesh levels execute approximately, but density remains `failed_to_converge`, `can_sign_off=false`. Original EBrake AC and other PEEC gates remain open. Marble has bounded DC evidence but unresolved AC/SI qualification. Neither is made fully qualified by supplied-line tests. See [board follow-up](validation/PEEC_REPAIR_FOLLOWUP_20261019.md) and [current stage evidence](validation/SI02_LOADED_STAR_20261021.md).

## Work completed in this continuation

[PI01-S02 3-D land fields](validation/PI01_LAND_TRANSITION_20261021.md) now retain
independent finite face patches, all three current components and conservative
Joule heat in a supplied rectangular land. Twenty-three source-bound tests pass,
including 14 new physics/oracle/adversarial/CLI checks and nine earlier axial
checks actually rerun. Independent continuum resistance error falls to 0.113%.
PI01-S02 remains in progress; full-board and general annular/circuit conditions
are not closed by this reference.

[PI01-S02 geometry/ownership](validation/PI01_GEOMETRY_OWNERSHIP_20261021.md)
now admits the actual rotated-polygon example through an explicit measured
precision model and creates fresh face-to-face branches for supplied coaxial
annular ownership. Eighteen strengthened finite-contact/geometry tests, nine
axial/integration tests and 47 unchanged DC/Marble regressions pass. PI01-S02
remains in progress; no additional whole stage or family completion is claimed.

[PI01-S02A](validation/PI01_FINITE_CONTACT_20261021.md) adds an executable offline
finite-contact DC acceptance benchmark: four three-level analytical ladders,
raw report replay, conserved Joule/terminal work, rotated-mesh covariance,
conductivity scaling and retained inactive volume. Nine new tests and 38 existing
focused tests pass. Independent review findings were repaired and retested.
Full PI01-S02 remains open. The original default-precision rotated-polygon
rejection remains a regression; the opt-in measured precision path now solves
that example and preserves the original error thresholds.

SI02-S13 adds complete physical RLC source/load voltages on 4–16 exterior ports of coupled branches, retaining actual branch fields and separate terminal/branch heat W, mean J and reactive var. It also corrects a demonstrated near-zero boundary-integrity false rejection with a limited roundoff allowance; raw currents, power checks and board gates are unchanged. The empirical allowance is not a universal numerical error guarantee.

## Remaining work in priority order

Latest verified increment: [annular source contacts and barrel/circuit ports](validation/PI01_ANNULAR_CONTACT_20261021.md).
Thirty new source-bound tests and 47 unchanged DC/Marble regressions pass.
Explicit circular-pad authentication, annular spreading and fresh coupled
current/heat recovery are verified within the documented axisymmetric patch
model. PI01-S02 remains in progress; the stage/family counts above are unchanged.

1. **Board PI closure:** PI01-S02 conservative vector current/unique-volume density and finite contacts; resolve original EBrake convergence and EBrake/Marble AC/SI blockers with unchanged gates and source identities.
2. **Geometry-backed SI/PI:** general layouts, returns, vias/launches/connectors/packages, asymmetric channels and broadband plane/via/package PDNs; bind actual materials, ownership and uncertainty.
3. **Complete electrical workflows:** nonlinear IBIS, statistical/AMI and DDR, switching/SSN field interaction, physical decap optimization, rule coverage and power-converter model completeness.
4. **Family qualification:** define and accept representative independent benchmarks, convergence/measurement evidence and uncertainties for each family; then perform required human numerical and installed/release qualification.
5. **Qualified multiphysics expansion:** shared geometry/material/field identities and conservative transfers; thermal, mechanical stress/deformation, modal/vibration/shock, solder/fatigue, magnetics/motion, motors/actuators/gears and Hall/semiconductor behavior. Existing bounded foundations do not close these full workflows.
6. **Broader planned directions:** full fluids/aerodynamics and control/code-to-performance vehicle studies, RF/HVDC system scales, PEC boundary-element radiation without exterior volume meshes, wave optics for mirror/lens assemblies, material libraries and measured-error acceleration. Each has its own plan and numerical/physical gates; chemical engineering remains outside active scope.

## Parallel multiphysics work

A mechanical foundation stage is recorded in the ledger. The separate CFD track reports bounded enclosure/CHT and selected-cut momentum verification plus research stress/SA/rotation primitives; engineering turbulence, rotating propellers and general local AMR are not thereby qualified. Its [current benchmark record](validation/ENCLOSURE_FLOW_BENCHMARKS_20261020.md) distinguishes synthetic mathematical tests from physical qualification. That work was not requalified by this PI/SI stage. See [platform strategy](MULTIPHYSICS_PLATFORM_STRATEGY.md), [coupled mechanics/magnetics/devices](COUPLED_MECHANICS_MAGNETICS_DEVICES_PLAN.md), [vibration/vehicles/mechanisms](VIBRATION_VEHICLES_AND_MECHANISMS_PLAN.md), and the deferred optical/general-physics gates in the ledger.
