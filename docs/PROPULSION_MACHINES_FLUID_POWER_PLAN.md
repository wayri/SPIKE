<!-- SPDX-License-Identifier: Apache-2.0 -->
# Propulsion, power machines and fluid-power application targets

Owner request and explicit scope decision, 21 October 2026: add complete
jet-engine studies, including small gas turbines up to the5 kN thrust class;
electric generators, turbines, wind generators, industrial electric motors,
hydraulics and pneumatics. The owner explicitly approved **propulsion combustion
only** as an exception to the prior combustion exclusion. General chemical
process/reactor, electrochemical and unrelated reacting-flow expansion remains
paused. This is development authorization and a roadmap, not available or
qualified full-engine capability. Existing PI/SI and CFD prerequisites remain.

## Fidelity and physical scope

Support three separately declared levels, not one ambiguous "full" button:

1. Fast whole-system0D/1D models: maps, equivalent circuits, thermodynamic
   volumes, shafts, lines, controls and component matching. Every map, empirical
   loss and supplied property retains its provenance and valid operating range.
2. Component field studies: admitted EM, fluid, thermal and mechanical domains,
   with actual boundary and interface data rather than invented performance maps.
3. Coupled resolved3D studies: rotor/stator or moving interfaces, turbulent
   compressible/reacting flow where applicable, CHT, electrical fields/circuits,
   mechanical deformation/dynamics and controls. Each participant and the
   coupling itself require separate verification and validation.

The5 kN figure is thrust in newtons, not shaft power, electrical power or a
guaranteed mesh/compute limit. Declare net versus gross thrust, static versus
flight conditions, ambient state, mass/fuel flow, shaft speeds and the actual
operating envelope. Engine size alone does not establish Reynolds/Mach regimes,
material suitability, flame stability, numerical accuracy or certification.

## Application stages and acceptance evidence

| Track | Bounded development stages | Evidence before promotion |
|---|---|---|
| Propulsion system cycle | Inlet, compressor, combustor model, turbine, nozzle, shaft and controls; design/off-design map matching; explicit heat-addition cycle before reacting CFD | Independent ideal-cycle/isentropic nozzle oracles, corrected-map conventions and no extrapolation, shaft/mass/enthalpy closure, pressure thrust and fuel-mass accounting, matched independent cycle and measured operating points |
| Compressor/turbine components | Compressible nonreacting flow, boundary layers/tip clearances, rotating frames, then rotor/stator sliding or ALE interfaces and stage coupling | Manufactured compressible conservation, shock/nozzle and rotating references; torque/angular momentum/shaft power; mesh/time/interface/domain studies and actual component maps. Stall/surge require explicit unsteady models and evidence |
| Propulsion combustion | First reviewed thermochemistry/species/energy verification, then matched combustor mixing/reacting cases, then engine integration | Mechanism/property/version/rights; elemental and species/total-energy closure; formation-enthalpy consistency; stiff chemistry integration and positivity; matched ignition/extinction/flame and gas-turbine combustor references. Turbulence–chemistry closure, liquid injection/atomization/evaporation, radiation and emissions need their own applicability and data |
| Complete small jet engine | Coupled inlet/compressor/combustor/turbine/nozzle/shaft/controls, with CHT/cooling and structural participants at declared fidelity | Consistent accepted component states and pressure/flow/shaft matching; total thrust/fuel/power/heat ledger; startup/load transients and failure boundaries only if modeled; independent engine data and uncertainty at specified points up to the requested class |
| Electric machines and industrial drives | Bounded PM DC/BLDC/PMSM drive/generator first; induction, synchronous/wound-field, reluctance and other classes separately; voltage-driven field/circuit coupling and moving interfaces | Reciprocal torque/back-EMF, electrical/mechanical/thermal energy, commutation/inverter time resolution, saturation/hysteresis/eddy/core losses with applicable material data, mesh/time convergence and measured torque-speed-loss-efficiency curves |
| Wind generation | Qualified aero maps or bounded blade-element model, rotor inertia, pitch/yaw, shaft/gearbox, generator/converter, controller and grid/load | Aero/mechanical/electrical power and thrust/torque conventions, rotor and generator operating ranges, measured aero/drive references; wake, dynamic stall, flexible blades/tower, fatigue and coupled aeroelasticity qualified separately |
| Other turbines and turbine-generators | Air/gas, hydraulic and steam machines through explicit medium/regime models; shaft/gear/bearing/generator coupling | Component and overall head/enthalpy/torque/power balance, EOS/phase/loss applicability, speed/load transients, independent maps and measured performance. Steam/phase change and cavitation are not implied by a generic turbine label |
| Hydraulic systems | Conservative networks of reservoirs, pumps/motors, valves, lines, accumulators, cylinders and loads; local3D studies where needed | Pressure-flow/force-displacement references, bulk-modulus/storage and pump/valve maps, reversible flow, actuator work, leakage/friction/heating; water hammer, cavitation and fluid/structure response only with the corresponding verified models |
| Pneumatic systems | Gas networks, compressors, receivers, valves, lines, cylinders and controls with explicit EOS and thermal boundaries | Isothermal/adiabatic filling/blowdown references, mass and total-energy storage, choked/unchoked nozzle/valve behavior, reversible flow, actuator work and measured component transients; do not substitute incompressible pressure-flow laws |

No engine fuel mechanism, efficiency, cooling load, compressor map or motor
material is invented from the5 kN label. Independently authored analytical
fixtures may verify equations; they cannot establish accuracy for a real engine.
Public benchmark data require review of operating conditions, uncertainty,
geometry rights and redistribution before admission. An independent solver
comparison is distinct from measured correlation.

## Reuse existing stages; preserve prerequisites

- CFD-01/02: CAD fluid regions, locally controlled/boundary-layer mesh,
  conservative momentum/energy and material-interface CHT.
- CFD-04/05/06: qualified turbulence, rotating interfaces and conservative
  compressible/EOS/shock/low-Mach formulations. Propulsion chemistry is an
  additional participant, not a relabeling of the current energy equation.
- GP machine/mechanism stages: field/circuit coupling, shafts, bearings,
  structural/thermal response and controls. Existing compact PM DC dynamics
  and experimental planar fields do not establish industrial-machine accuracy.
- CFD-07/08: moment- and work-preserving load transfer, flexible blades/shafts,
  vibration and strong FSI. Present surface-transfer evidence without spatial
  moments cannot qualify blade torque or flutter.
- [Native/HPC roadmap](NATIVE_HPC_MIGRATION.md): C++20 numerical state,
  prepared/reused operators, coherent multicore allocation, then actual MPI
  domain decomposition; Python specifications/orchestration and independent
  oracles. No new implementation language or dependency is selected here.

Implement fast system/component references first, alongside the currently
prioritized geometry/open-boundary and native-performance foundations. Do not
jump directly from a creeping-flow box to an enabled turbulent reacting engine.
Do not postpone basic conservation/coupling contracts until after adding many
component labels. A field solver is not mandatory for every system-level step,
but its approximation must be explicit and validated for its intended use.

## Common coupling and result requirements

Use one revision-bound study graph with materials, maps, ports, units, frames,
initial/boundary conditions, uncertainties and model-validity envelopes.
Separate fluid mass/enthalpy/species, electrical voltage/current, rotational
torque/angular speed, translational force/velocity and thermal heat-rate ports.
Do not equate thrust with power or use incompressible p*Q as the complete
energy ledger for arbitrary compressible gas transport.

Coupling owns trial/accepted states, common windows, events/subcycling,
convergence, complete rollback and same-state certificates. Retain fluid,
chemical, thermal, electrical and mechanical storage/work/loss terms without
double-counting energy transferred between participants. A failed participant
must prevent a successful whole-machine result. Restart preserves controls,
material/chemical state, rotating-interface identity and accepted histories.

Results include declared fidelity, mass/energy/shaft/electrical closure,
residuals, mesh/time/coupling convergence, operating limits and uncertainty.
Unsupported surge, ignition, emissions, fatigue, overspeed or other failure
modes are named, not inferred from an otherwise converged solution. Simulation
does not establish safe hardware operation, airworthiness or certification.

## Present state and next evidence

These application workflows are **requested targets**, not new executable
capabilities. [Solver status](SOLVER_STATUS.md), [EM machine bounds](EM_MACHINES.md),
[machine-field studies](MAGNETIC_MACHINE_STUDIES.md) and
[current CFD increment](validation/CFD_CAD_OPEN_BOUNDARY_20261021.md) remain
authoritative. No thrust-class, industrial-machine, full pneumatic/hydraulic
or reacting-combustion capability is advertised by this document.

Before implementation of each new model, select exact primary mathematical
sources, independently derive its equations, declare tolerances from the
reference/uncertainty, and execute analytical, independent-solver and measured
building blocks. Novel/learned closures remain experimental until they beat
an established matched-error baseline. Knowledgeable human numerical review
and existing release gates remain required.

## Primary sources reviewed for planning

- NASA Glenn [EngineSim scope](https://www1.grc.nasa.gov/beginners-guide-to-aeronautics/enginesim/)
  and [thrust equation](https://www1.grc.nasa.gov/beginners-guide-to-aeronautics/thrust-force/):
  whole-engine performance versus momentum/pressure thrust accounting. These
  introductory pages do not qualify a combustion model or real engine.
- OpenFAST5.0 [AeroDyn guide/theory index](https://openfast.readthedocs.io/en/main/source/user/aerodyn/index.html):
  reviewed index identifying model families, frames, dynamic inflow and
  discretization sections, not their detailed method derivations; planning
  scope only, no algorithms/data copied or adopted.
- Modelica Standard Library4.0 [fluid component balance/connection documentation](https://doc.modelica.org/Modelica%204.0.0/Resources/helpDymola/Modelica_Fluid_UsersGuide_ComponentDefinition.html)
  and [machine-library scope](https://doc.modelica.org/Modelica%204.0.0/Resources/helpDymola/Modelica_Electrical_Machines.html):
  reviewed conservation/interface and machine-family descriptions, not source
  implementation. No Modelica runtime or implementation language is added.
- NASA [gas-turbine combustor facilities](https://www.nasa.gov/centers-and-facilities/glenn/combustor-facilities/):
  public description identifies measured combustion/flow diagnostics as future
  reference candidates; no dataset is imported or claimed as validated here.

Reviewed21October2026. These are planning references, not the detailed adopted
method evidence required for future numerical implementations. All prose and
requirements here were independently authored; no external implementation,
example, geometry, image or dataset was copied.
