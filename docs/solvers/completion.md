<!-- SPDX-License-Identifier: Apache-2.0 -->
# Solver completion states

This generated inventory covers every capability in the development catalog, including
support workflows. It is not a count of independent physics engines. Regenerate with
`node app/scripts/generate-solver-integration.mjs`.

## How to read completion

| State | Meaning |
| --- | --- |
| Implemented within documented scope | Catalog marks the bounded workflow implemented; this does not close all physics or release gates. |
| Partial / experimental family | Executable reference or experimental implementation exists; the broader family remains incomplete or approximate. |
| External integration; runtime-dependent | SPIKE integration exists; the exact external runtime and model need separate admission and qualification. |
| Planned / no admitted solver | No admitted execution route for the requested family; supporting groundwork may exist. |

Completion is derived from the catalog's existing status, not a new promotion.
Source/API and desktop integration are shown separately. The remaining-work column
retains each capability's declared limits. No capability is marked universally
physically validated or release-complete by this inventory. Accuracy has no universal
percentage. Use the linked scope/evidence and [dated solver status](../SOLVER_STATUS.md).
Domain READMEs additionally label internal numerical owners, meshing and execution
subgroups that do not have independent desktop capability IDs.

The [source-layout verification](../validation/SOLVER_SOURCE_LAYOUT_20261025.md)
records the failed full-suite result, historical receipt requalification needs and
concurrent source drift after the retained frozen-worker snapshot. Those remain
separate gates even for an implemented workflow. Research excluded from publication
is intentionally absent; the existing public Optycal RF extension remains included.

## Capability completion inventory

### Circuits and SPIKES Studio

| Solver / capability | Completion state | Integration | Remaining work / validity boundary | Evidence |
| --- | --- | --- | --- | --- |
| Native circuit OP, AC and transient (`circuit-native`) | Partial / experimental family | Workflow available | Supported model subset only; connectivity drawings are not automatic compact-model extraction or ngspice parity. | [Scope/evidence](../SPIKES_BOARD_STUDIO.md) |
| Adaptive BDF2 and trapezoidal transient (`circuit-adaptive`) | Partial / experimental family | Workflow available | Configure these controls in Studio or SPIKES CLI; known switching/conditioning limits; no universal LTE, converter qualification or ngspice parity. | [Scope/evidence](../SPIKES_ADAPTIVE_SWITCHING_FOUNDATION.md) |
| Electrical I/Q equations and package parasitics (`circuit-equations`) | Partial / experimental family | Workflow available | Use Studio or device-build for authoring; no arbitrary-state DAE, owned K-element support or manufacturer qualification. | [Scope/evidence](../SPIKES_EQUATION_DEVICES.md) |
| Supplied multi-terminal physics parts (`circuit-physics-parts`) | Partial / experimental family | Workflow available | Supplied equations and parameters; symbol availability is not semiconductor/process qualification. | [Scope/evidence](../SPIKES_LUMPED_PHYSICS_PARTS.md) |
| Ideal CCM SMPS and control-loop stability (`circuit-smps`) | Partial / experimental family | Workflow available | Supplied-parameter voltage-mode analytical model; excludes DCM, current-mode, delays, parasitics and schematic extraction. | [Scope/evidence](../SPIKES_SMPS_STABILITY.md) |
| One-RC battery reference study (`circuit-battery`) | Partial / experimental family | Workflow available | Synthetic chemistry defaults; not native battery MNA stamping or manufacturer qualification. | [Scope/evidence](../SPIKES_BATTERY_MODEL.md) |
| Passive, digital and compiled controller models (`circuit-libraries`) | Partial / experimental family | Workflow available | Acquisition metadata is separate from runnable models; full 54/74 coverage and electrical/timing qualification remain open. | [Scope/evidence](../SPIKES_ACTIVE_LIBRARY_COVERAGE.md) |
| Open-PDK inventory and ngspice circuit studies (`circuit-pdk`) | External integration; runtime-dependent | Source/API only | CLI workflow only here. Current execution evidence uses an original synthetic NMOS; no foundry qualification or complete owned-engine PDK compatibility. | [Scope/evidence](../SPIKES_OPEN_PDK_WORKFLOW.md) |
| IC/ASIC preflight and KLayout inspection (`circuit-asic`) | External integration; runtime-dependent | Source/API only | CLI workflow only here. No technology-mapped physical closure, executed PDK DRC/LVS, PEX or end-to-end ASIC qualification. | [Scope/evidence](../SPIKES_ASIC_TWO_APPLICATION_FLOW.md) |
| Native 1D equilibrium semiconductor field (`circuit-tcad`) | Partial / experimental family | Source/API only | Console/source workflow only; no biased carrier transport, I-V, process simulation, heterostructures or full TCAD. | [Scope/evidence](../SPIKES_TCAD_EQUILIBRIUM.md) |
| Xyce bounded circuit workbench (`circuit-xyce`) | External integration; runtime-dependent | Workflow available | Requires separately installed runtime; adapter/UI tests do not establish native accuracy or arbitrary plugins. | [Scope/evidence](../PALACE_XYCE_WORKBENCHES.md) |
| Full TCAD and ASIC physical closure (`planned-tcad`) | Planned / no admitted solver | No execution route | Unavailable; equilibrium electrostatics, PDK circuit studies and KLayout inspection retain their separate bounded scopes. | [Scope/evidence](../SPIKES_ASIC_TWO_APPLICATION_FLOW.md) |

### Power integrity

| Solver / capability | Completion state | Integration | Remaining work / validity boundary | Evidence |
| --- | --- | --- | --- | --- |
| Retained-volume 3D DC conduction (`pi-solid-dc`) | Partial / experimental family | Source/API only | Source API solve_assembly_tetra_electrical; no standalone worker route, full-wave AC or automatic arbitrary CAD extraction. | [Scope/evidence](../SOLVER_MATHEMATICS.md) |
| Geometry PEEC RLC transient (`pi-transient`) | Partial / experimental family | Workflow available | Approximate reduced circuit geometry; native runtime admission required, no arbitrary full-wave or nonlinear regulator qualification. | [Scope/evidence](../SOLVER_STATUS.md) |
| Board DC resistance and source-capacity screening (`pi-dc`) | Partial / experimental family | Workflow available | Approximate reduced network; current capacity does not implement CV/CC regulation or foldback. | [Scope/evidence](../SOURCE_CURRENT_LIMITS.md) |
| PEEC R/L and approximate RLCG extraction (`pi-peec`) | Partial / experimental family | Workflow available | Shared-reference C/G approximation; no arbitrary-PCB full-wave, qualified multiport placement or measured-board correlation. | [Scope/evidence](../SOLVER_STATUS.md) |
| Explicit PDN/filter and simultaneous load transients (`pi-pdn`) | Partial / experimental family | Workflow available | Explicit passive models; excludes automatic board extraction, dispersive/saturating magnetics and nonlinear regulator control. | [Scope/evidence](../PDN_SIMULTANEOUS_LOADS.md) |
| Finite-dielectric electrostatic capacitance (`pi-capacitance`) | Partial / experimental family | Guarded request runner | Worker extraction from a reviewed request; finite retained domain and electrodes only, with no arbitrary open-boundary PCB qualification. | [Scope/evidence](../PDN_SCREENING.md) |
| Finite-dielectric AC admittance (`pi-dielectric-ac`) | Partial / experimental family | Guarded request runner | Worker extraction from a reviewed request; sampled experimental admittance has no causal transient or general board-extraction qualification. | [Scope/evidence](../PDN_DIELECTRIC_AC.md) |
| Passive sampled port reduction (`pi-reduction`) | Partial / experimental family | Guarded request runner | Worker reduction from a reviewed request; sample passivity does not qualify a causal broadband or transient macromodel. | [Scope/evidence](../PDN_ADMITTANCE_REDUCTION.md) |
| Converter, copper and capacitor screening (`pi-engineering`) | Partial / experimental family | Workflow available | No switching-loop solve, continuous placement optimum or automatic addition of capacitor voltage ratings. | [Scope/evidence](../PI_ENGINEERING_TOOLS.md) |
| Authenticated board-volume tetrahedral DC (`pi-board-volume-dc`) | Partial / experimental family | Source/API only | Source/API reference only; current full-board meshes exceed declared budgets and there is no production dispatch, convergence closure or board qualification. | [Scope/evidence](../validation/PI01_BOARD_VOLUME_20261023.md) |

### Signal integrity

| Solver / capability | Completion state | Integration | Remaining work / validity boundary | Evidence |
| --- | --- | --- | --- | --- |
| Touchstone and sampled network processing (`si-networks`) | Implemented within documented scope | Workflow available | Network processing does not validate geometry extraction; arbitrary imported-network causality is unavailable. | [Scope/evidence](../PI_SI_PARITY_EXECUTION.md) |
| Single and coupled quasi-TEM channel extraction (`si-channels`) | Partial / experimental family | Workflow available | Explicit reference and homogeneous dielectric; bends omit discontinuity physics. No arbitrary vias, launches, statistical eyes or measured qualification. | [Scope/evidence](../GEOMETRY_DERIVED_SI_CHANNEL.md) |
| Eye masks and protocol suite input review (`si-eye`) | Partial / experimental family | Workflow available | Overall protocol compliance remains blocked; configuration and deterministic eye screens do not establish BER or signoff. | [Scope/evidence](../SI_EYE_MASK_TESTING.md) |
| Coupled multiport fixture de-embedding (`si-multiport-deembedding`) | Partial / experimental family | Workflow available | Offline supplied-network workflow; calibration uncertainty, general passive causal fitting, measurement correlation and release qualification remain open. | [Scope/evidence](../MULTIPORT_DEEMBEDDING.md) |
| Generic sampled-FIR PAM3 eye and SER (`si-pam3`) | Partial / experimental family | Guarded request runner | Generic development model only; it is not USB4 encoding, training, clock recovery, receiver behavior, BER signoff or protocol compliance. | [Scope/evidence](../validation/SI_EXECUTION_20261023.md) |

### Thermal and airflow

| Solver / capability | Completion state | Integration | Remaining work / validity boundary | Evidence |
| --- | --- | --- | --- | --- |
| Object networks and layered board thermal (`thermal-board`) | Partial / experimental family | Workflow available | Prescribed effective materials/cooling and bounded geometry; physical package and installed cooling qualification remain open. | [Scope/evidence](../ASSEMBLY_ELECTROTHERMAL.md) |
| Retained tetrahedral solid thermal (`thermal-solids`) | Partial / experimental family | Workflow available | Explicit materials and admitted meshes; arbitrary compound CAD, measured correlation and release qualification remain open. | [Scope/evidence](../ASSEMBLY_THERMAL_TRANSIENT.md) |
| Assembly and multiboard electrothermal feedback (`thermal-electrothermal`) | Partial / experimental family | Workflow available | Reduced circuits/explicit bindings; no inferred arbitrary device models, automatic PCB extraction or general switching physics. | [Scope/evidence](../MULTIBOARD_VOLUME_ELECTROTHERMAL.md) |
| Native PWM and retained-volume electrothermal (`thermal-pwm`) | Partial / experimental family | Workflow available | Bounded fixtures; no semiconductor thermal feedback, vendor switching losses, deadtime, airflow or hardware correlation. | [Scope/evidence](../PWM_VOLUME_ELECTROTHERMAL.md) |
| Laminar channel and fan-system screening (`thermal-channel`) | Partial / experimental family | Workflow available | Channel approximation; not general geometry Navier-Stokes, turbulence or solid-fluid CHT. | [Scope/evidence](../INTERNAL_AIRFLOW.md) |
| Native laminar 2D CFD cavity (`cfd-native`) | Partial / experimental family | Workflow available | Isothermal square cavity reference; no thermal/CAD support, general assembly CFD or turbulence qualification. | [Scope/evidence](../validation/NATIVE_SU2_CFD_20261011.md) |
| SU2 cavity and three-zone CHT references (`cfd-su2`) | External integration; runtime-dependent | Workflow available | Experimental reference cases; not general assembly CHT or mesh independence. Failed and timed-out cases remain excluded. | [Scope/evidence](../SU2_CHT.md) |
| CalculiX solid thermal and OpenFOAM cooling (`thermal-external`) | External integration; runtime-dependent | Workflow available | Runtime and platform admission required; general imported assembly CHT and measured cooling correlation remain open. | [Scope/evidence](../validation/THERMAL_COOLING_ENVIRONMENTS_20261009.md) |
| CalculiX thermal extension workflow (`thermal-calculix`) | External integration; runtime-dependent | Workflow available | Requires a separately admitted runtime and explicit materials and boundaries; adapter execution does not establish arbitrary assembly or measured cooling qualification. | [Scope/evidence](../validation/THERMAL_COOLING_ENVIRONMENTS_20261009.md) |
| Retained tetrahedral creeping-flow CHT (`cfd-tetra-cht`) | Partial / experimental family | Guarded request runner | Bounded worker workflow on admitted tetrahedra; no caller-fabricated flux, turbulence, general CAD assembly closure or packaged qualification. | [Scope/evidence](../validation/CFD_CHT_RELEASE_20261023.md) |

### Electromagnetics

| Solver / capability | Completion state | Integration | Remaining work / validity boundary | Evidence |
| --- | --- | --- | --- | --- |
| Surface method of moments (`planned-mom`) | Planned / no admitted solver | No execution route | Unavailable: no executable validated MoM engine is packaged. A registered identity is not an implemented kernel. | [Scope/evidence](../SOLVER_STATUS.md) |
| Planar nonlinear magnetic FEM machines (`em-magnetic`) | Partial / experimental family | Workflow available | No 3D rotating CAD, conforming sliding interfaces, moving-conductor losses, hysteresis or field/circuit drives. | [Scope/evidence](../MAGNETIC_MACHINE_STUDIES.md) |
| Lumped PM DC motor and electromagnet (`em-lumped`) | Partial / experimental family | Workflow available | No spatial field, rotating CAD or nonlinear material solve. | [Scope/evidence](../EM_MACHINES.md) |
| openEMS board and retained-volume fields (`em-openems`) | External integration; runtime-dependent | Workflow available | Experimental PCB/assembly workflows; runtime probe does not establish arbitrary board accuracy or EMI compliance. | [Scope/evidence](../RETAINED_ASSEMBLY_EM.md) |
| PALACE native configuration and field inspection (`em-palace`) | External integration; runtime-dependent | Workflow available | Requires separately installed runtime; no live accuracy qualification, automatic geometry/ports or canonical SPIKE fields. | [Scope/evidence](../PALACE_XYCE_WORKBENCHES.md) |
| EMerge multilayer SI and radiation FEM (`em-emerge`) | External integration; runtime-dependent | Workflow available | Experimental rectangular substrates and idealized references; no arbitrary via physics or EMI compliance. Execution and backend agreement are not physical qualification. | [Scope/evidence](../EMERGE_ANTENNA_WALKTHROUGH.md) |
| Owned arbitrary-PCB full-wave solver (`planned-fullwave`) | Planned / no admitted solver | No execution route | Unavailable. Optional openEMS execution does not enable this solver identity. | [Scope/evidence](../SOLVER_STATUS.md) |

### Structural mechanics

| Solver / capability | Completion state | Integration | Remaining work / validity boundary | Evidence |
| --- | --- | --- | --- | --- |
| Static tetrahedral structural mechanics (`mechanics-static`) | Partial / experimental family | Guarded request runner | Explicit reviewed mesh, materials and loads; no contact, dynamics, fatigue, failure or general machine-motion qualification. | [Scope/evidence](../COUPLED_MECHANICS_MAGNETICS_DEVICES_PLAN.md) |
| Same-mesh thermal-to-mechanical coupling (`mechanics-thermoelastic`) | Partial / experimental family | Guarded request runner | One-way isotropic small-strain static coupling; no transient mechanics, feedback deformation, moving contact or lifetime qualification. | [Scope/evidence](../COUPLED_MECHANICS_MAGNETICS_DEVICES_PLAN.md) |

### Execution and coupling

| Solver / capability | Completion state | Integration | Remaining work / validity boundary | Evidence |
| --- | --- | --- | --- | --- |
| Scalar co-simulation and recorded digital twins (`execution-cosim`) | Partial / experimental family | Guarded request runner | Worker/CLI workflow; scheduling evidence does not qualify physics, FMI, live acquisition or hardware control. | [Scope/evidence](../COSIMULATION_DIGITAL_TWIN.md) |
| Parallel jobs and enrolled remote workers (`execution-workers`) | Implemented within documented scope | Workflow available | Schedules existing models; no single-solve MPI or additional GPU solver support. | [Scope/evidence](../PARALLEL_WORKER_MANAGER.md) |
| Meshing, optional engines and acceleration (`execution-extensions`) | Implemented within documented scope | Workflow available | Runtime discovery and meshing never promote physics qualification; capabilities depend on admitted installed extensions. | [Scope/evidence](../EXTENSION_WORKSPACE_ENGINES.md) |
| Gmsh PCB and retained assembly volume meshes (`execution-gmsh`) | External integration; runtime-dependent | Workflow available | Geometry-only workflow; meshing does not establish solver translation, physics accuracy or production qualification. | [Scope/evidence](../EXTENSION_WORKSPACE_ENGINES.md) |
| sparseLizard case preparation and qualification gates (`execution-sparselizard`) | External integration; runtime-dependent | Source/API only | CLI preparation only here; no qualified adapter, signed manifest, MUMPS registration or installed fixture evidence. Preparation is not a solve. | [Scope/evidence](../SOLVER_STATUS.md) |
| Controller, FEM and propeller coupled benchmark (`execution-propulsion-pod`) | Partial / experimental family | Workflow available | Synthetic benchmark and source-worker workflow; it is not VESC firmware, product motor identity, blade-resolved CFD, flight qualification or packaged-runtime qualification. | [Scope/evidence](../validation/PROPULSION_POD_COUPLING_DERIVATION_20261023.md) |
| Explicit-geometry propulsion port loop (`execution-propulsion-geometry`) | Partial / experimental family | Workflow available | Requires retained admitted source tables; actual-air full-speed load, convergence, product identity and packaged-runtime qualification remain open. | [Scope/evidence](../adr/0136-explicit-geometry-propulsion-ports.md) |
| Sampled EM network and circuit boundaries (`em-network-cosimulation`) | Partial / experimental family | Guarded request runner | Linear sampled-network worker workflow; it does not run live SPICE, infer field calibration or qualify a general co-simulation environment. | [Scope/evidence](../EMERGE_COSIMULATION.md) |
| EM circuit-resistor thermal coupling (`em-resistor-thermal`) | Partial / experimental family | Guarded request runner | Explicit resistor bindings and thermal inputs only; no inferred radiation heat, live device feedback, arbitrary geometry mapping or packaged qualification. | [Scope/evidence](../EMERGE_COSIMULATION.md) |
| AC network resistor to creeping CHT (`em-resistor-cht`) | Partial / experimental family | Guarded request runner | Source-worker experimental route with explicit bindings; no live SPICE, temperature feedback, turbulence, production cooling or installer qualification. | [Scope/evidence](../validation/AC_NETWORK_CHT_20261023.md) |
| Live linear sampled-network SPICE coupling (`em-spice-coupling`) | Partial / experimental family | Guarded request runner | Supported linear subset with reviewed ports only; no arbitrary nonlinear co-simulation, field calibration, automatic extraction or packaged qualification. | [Scope/evidence](../validation/EM_SPICE_COUPLING_20261023.md) |
| Supplied-field electromagnetic body heating (`em-body-heating`) | Partial / experimental family | Guarded request runner | Requires raw Poynting closure and state-bound samples; it does not establish source field accuracy, arbitrary anatomy, safety compliance or packaged qualification. | [Scope/evidence](../validation/EM_BODY_HEATING_20261023.md) |
| Same-mesh AC loss, thermal and elastic chain (`pi-ac-thermal-elastic`) | Partial / experimental family | Guarded request runner | One-way in-process/worker experimental chain; no geometry inference, transient mechanics, feedback deformation, general PCB qualification or packaged release evidence. | [Scope/evidence](../validation/AC_THERMAL_ELASTIC_20261023.md) |
| Elmer FEM solver integration (`planned-elmer`) | Planned / no admitted solver | No execution route | Unavailable for physics execution even when ElmerSolver is detected; translation, process and independent validation gates remain open. | [Scope/evidence](../SOLVER_STATUS.md) |

