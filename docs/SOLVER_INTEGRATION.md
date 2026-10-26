<!-- SPDX-License-Identifier: Apache-2.0 -->
# Integrated solver capabilities

This is a generated index of the development source, not an installed-release qualification statement. Regenerate with `node app/scripts/generate-solver-integration.mjs`.

## 1. Find the capability

Open **Solver manager → Capabilities and evidence**, or search the command bar for the capability name. The index contains **60 capability scopes** across PI, SI, circuits/SPIKES, thermal/CFD, EM, structural mechanics and execution/coupling. Blocks and install groups describe dependencies; they do not install or qualify solvers.

## 2. Open its exact setup

- Dedicated workflows open their existing setup panel. Propulsion opens the coupled benchmark; multiport fixture removal opens its dedicated SI tool and uses the common guided Run/Tutor checks.
- **Open reviewed runner** stages the named Python template as a new unsaved script. Choose a reviewed request JSON file, inspect requirements, then Run. Merely opening a capability or running an unset template launches no numerical job.
- External engine workflows retain runtime registration, trust, setup and execution admission. A missing requested extension is reported; another extension is not silently substituted.
- **Source/API evidence only** identifies implemented reference code without an admitted desktop runner. Use its documented source workflow. Planned entries have no execution route.

## 3. Review results and limits

The owning workflow retains its existing result viewer, provenance checks and export contracts. Request runners print evidence and can export complete records to a new file; only a matching spike/v1 result can be published to the active design. Typed study records are not mislabeled as generic field results. Main-viewport geometry/field views remain dependent on supported result formats.

Automatic backups and normal project saving retain project-owned states. An unsaved Python script or a result exported outside the project needs its own save. Numerical failure, unavailable runtime and incompatible installed-worker errors remain visible.

## Current integration boundaries

Ten additional guarded runners connect already implemented worker methods: resistor CHT, EM/SPICE coupling, EM body heating, generic PAM3, tetrahedral CHT, PDN electrostatic extraction, dielectric AC, admittance reduction, structural and thermomechanical studies. No numerical kernel, constitutive law, solver tolerance, source authority or validation gate was changed.

Board-volume RT0/full-board production dispatch, the trusted development AMI DLL host, the native CDR reference, arbitrary full-wave/MoM, full-speed actual-air propulsion closure and general reacting flow are not promoted by these links. Source experiments, installed runtime availability, executed transport tests, physical validation and release qualification remain separate.

## Capability map

### Circuits and SPIKES Studio

| Capability | State | Destination | Evidence |
| --- | --- | --- | --- |
| Native circuit OP, AC and transient (`circuit-native`) | experimental | spice | [Scope and limits](SPIKES_BOARD_STUDIO.md) |
| Adaptive BDF2 and trapezoidal transient (`circuit-adaptive`) | experimental | spice | [Scope and limits](SPIKES_ADAPTIVE_SWITCHING_FOUNDATION.md) |
| Electrical I/Q equations and package parasitics (`circuit-equations`) | experimental | spice | [Scope and limits](SPIKES_EQUATION_DEVICES.md) |
| Supplied multi-terminal physics parts (`circuit-physics-parts`) | experimental | spice | [Scope and limits](SPIKES_LUMPED_PHYSICS_PARTS.md) |
| Ideal CCM SMPS and control-loop stability (`circuit-smps`) | experimental | spice | [Scope and limits](SPIKES_SMPS_STABILITY.md) |
| One-RC battery reference study (`circuit-battery`) | experimental | spice | [Scope and limits](SPIKES_BATTERY_MODEL.md) |
| Passive, digital and compiled controller models (`circuit-libraries`) | experimental | spice | [Scope and limits](SPIKES_ACTIVE_LIBRARY_COVERAGE.md) |
| Open-PDK inventory and ngspice circuit studies (`circuit-pdk`) | external | Source/API reference | [Scope and limits](SPIKES_OPEN_PDK_WORKFLOW.md) |
| IC/ASIC preflight and KLayout inspection (`circuit-asic`) | external | Source/API reference | [Scope and limits](SPIKES_ASIC_TWO_APPLICATION_FLOW.md) |
| Native 1D equilibrium semiconductor field (`circuit-tcad`) | experimental | Source/API reference | [Scope and limits](SPIKES_TCAD_EQUILIBRIUM.md) |
| Xyce bounded circuit workbench (`circuit-xyce`) | external | extensions / spike.xyce-suite | [Scope and limits](PALACE_XYCE_WORKBENCHES.md) |
| Full TCAD and ASIC physical closure (`planned-tcad`) | planned | Unavailable | [Scope and limits](SPIKES_ASIC_TWO_APPLICATION_FLOW.md) |

### Power integrity

| Capability | State | Destination | Evidence |
| --- | --- | --- | --- |
| Retained-volume 3D DC conduction (`pi-solid-dc`) | experimental | Source/API reference | [Scope and limits](SOLVER_MATHEMATICS.md) |
| Geometry PEEC RLC transient (`pi-transient`) | experimental | pi | [Scope and limits](SOLVER_STATUS.md) |
| Board DC resistance and source-capacity screening (`pi-dc`) | experimental | pi | [Scope and limits](SOURCE_CURRENT_LIMITS.md) |
| PEEC R/L and approximate RLCG extraction (`pi-peec`) | experimental | pi | [Scope and limits](SOLVER_STATUS.md) |
| Explicit PDN/filter and simultaneous load transients (`pi-pdn`) | experimental | pi | [Scope and limits](PDN_SIMULTANEOUS_LOADS.md) |
| Finite-dielectric electrostatic capacitance (`pi-capacitance`) | experimental | Python: run-pdn-electrostatic | [Scope and limits](PDN_SCREENING.md) |
| Finite-dielectric AC admittance (`pi-dielectric-ac`) | experimental | Python: run-pdn-dielectric-ac | [Scope and limits](PDN_DIELECTRIC_AC.md) |
| Passive sampled port reduction (`pi-reduction`) | experimental | Python: run-pdn-admittance | [Scope and limits](PDN_ADMITTANCE_REDUCTION.md) |
| Converter, copper and capacitor screening (`pi-engineering`) | experimental | pi | [Scope and limits](PI_ENGINEERING_TOOLS.md) |
| Authenticated board-volume tetrahedral DC (`pi-board-volume-dc`) | experimental | Source/API reference | [Scope and limits](validation/PI01_BOARD_VOLUME_20261023.md) |

### Signal integrity

| Capability | State | Destination | Evidence |
| --- | --- | --- | --- |
| Touchstone and sampled network processing (`si-networks`) | implemented | si | [Scope and limits](PI_SI_PARITY_EXECUTION.md) |
| Single and coupled quasi-TEM channel extraction (`si-channels`) | experimental | si | [Scope and limits](GEOMETRY_DERIVED_SI_CHANNEL.md) |
| Eye masks and protocol suite input review (`si-eye`) | experimental | si | [Scope and limits](SI_EYE_MASK_TESTING.md) |
| Coupled multiport fixture de-embedding (`si-multiport-deembedding`) | experimental | si-multiport | [Scope and limits](MULTIPORT_DEEMBEDDING.md) |
| Generic sampled-FIR PAM3 eye and SER (`si-pam3`) | experimental | Python: run-si-pam3 | [Scope and limits](validation/SI_EXECUTION_20261023.md) |

### Thermal and airflow

| Capability | State | Destination | Evidence |
| --- | --- | --- | --- |
| Object networks and layered board thermal (`thermal-board`) | experimental | thermal | [Scope and limits](ASSEMBLY_ELECTROTHERMAL.md) |
| Retained tetrahedral solid thermal (`thermal-solids`) | experimental | thermal | [Scope and limits](ASSEMBLY_THERMAL_TRANSIENT.md) |
| Assembly and multiboard electrothermal feedback (`thermal-electrothermal`) | experimental | thermal | [Scope and limits](MULTIBOARD_VOLUME_ELECTROTHERMAL.md) |
| Native PWM and retained-volume electrothermal (`thermal-pwm`) | experimental | pi | [Scope and limits](PWM_VOLUME_ELECTROTHERMAL.md) |
| Laminar channel and fan-system screening (`thermal-channel`) | experimental | thermal | [Scope and limits](INTERNAL_AIRFLOW.md) |
| Native laminar 2D CFD cavity (`cfd-native`) | experimental | native-cfd | [Scope and limits](validation/NATIVE_SU2_CFD_20261011.md) |
| SU2 cavity and three-zone CHT references (`cfd-su2`) | external | extensions / spike.su2-suite | [Scope and limits](SU2_CHT.md) |
| CalculiX solid thermal and OpenFOAM cooling (`thermal-external`) | external | workers | [Scope and limits](validation/THERMAL_COOLING_ENVIRONMENTS_20261009.md) |
| CalculiX thermal extension workflow (`thermal-calculix`) | external | extensions / spike.calculix-suite | [Scope and limits](validation/THERMAL_COOLING_ENVIRONMENTS_20261009.md) |
| Retained tetrahedral creeping-flow CHT (`cfd-tetra-cht`) | experimental | Python: run-cfd-tetra-cht | [Scope and limits](validation/CFD_CHT_RELEASE_20261023.md) |

### Electromagnetics

| Capability | State | Destination | Evidence |
| --- | --- | --- | --- |
| Surface method of moments (`planned-mom`) | planned | Unavailable | [Scope and limits](SOLVER_STATUS.md) |
| Planar nonlinear magnetic FEM machines (`em-magnetic`) | experimental | machines | [Scope and limits](MAGNETIC_MACHINE_STUDIES.md) |
| Lumped PM DC motor and electromagnet (`em-lumped`) | experimental | machines | [Scope and limits](EM_MACHINES.md) |
| openEMS board and retained-volume fields (`em-openems`) | external | em / spike.openems-suite | [Scope and limits](RETAINED_ASSEMBLY_EM.md) |
| PALACE native configuration and field inspection (`em-palace`) | external | extensions / spike.palace-suite | [Scope and limits](PALACE_XYCE_WORKBENCHES.md) |
| EMerge multilayer SI and radiation FEM (`em-emerge`) | external | em / spike.emerge-suite | [Scope and limits](EMERGE_ANTENNA_WALKTHROUGH.md) |
| Owned arbitrary-PCB full-wave solver (`planned-fullwave`) | planned | Unavailable | [Scope and limits](SOLVER_STATUS.md) |

### Structural mechanics

| Capability | State | Destination | Evidence |
| --- | --- | --- | --- |
| Static tetrahedral structural mechanics (`mechanics-static`) | experimental | Python: run-assembly-structural | [Scope and limits](COUPLED_MECHANICS_MAGNETICS_DEVICES_PLAN.md) |
| Same-mesh thermal-to-mechanical coupling (`mechanics-thermoelastic`) | experimental | Python: run-assembly-thermomechanical | [Scope and limits](COUPLED_MECHANICS_MAGNETICS_DEVICES_PLAN.md) |

### Execution and coupling

| Capability | State | Destination | Evidence |
| --- | --- | --- | --- |
| Scalar co-simulation and recorded digital twins (`execution-cosim`) | experimental | Python: run-cosimulation-request | [Scope and limits](COSIMULATION_DIGITAL_TWIN.md) |
| Parallel jobs and enrolled remote workers (`execution-workers`) | implemented | workers | [Scope and limits](PARALLEL_WORKER_MANAGER.md) |
| Meshing, optional engines and acceleration (`execution-extensions`) | implemented | extensions | [Scope and limits](EXTENSION_WORKSPACE_ENGINES.md) |
| Gmsh PCB and retained assembly volume meshes (`execution-gmsh`) | external | extensions / spike.gmsh-suite | [Scope and limits](EXTENSION_WORKSPACE_ENGINES.md) |
| sparseLizard case preparation and qualification gates (`execution-sparselizard`) | external | Source/API reference | [Scope and limits](SOLVER_STATUS.md) |
| Controller, FEM and propeller coupled benchmark (`execution-propulsion-pod`) | experimental | propulsion-pod | [Scope and limits](validation/PROPULSION_POD_COUPLING_DERIVATION_20261023.md) |
| Explicit-geometry propulsion port loop (`execution-propulsion-geometry`) | experimental | propulsion-pod | [Scope and limits](adr/0136-explicit-geometry-propulsion-ports.md) |
| Sampled EM network and circuit boundaries (`em-network-cosimulation`) | experimental | Python: run-em-network-ac | [Scope and limits](EMERGE_COSIMULATION.md) |
| EM circuit-resistor thermal coupling (`em-resistor-thermal`) | experimental | Python: run-em-resistor-thermal | [Scope and limits](EMERGE_COSIMULATION.md) |
| AC network resistor to creeping CHT (`em-resistor-cht`) | experimental | Python: run-em-resistor-cht | [Scope and limits](validation/AC_NETWORK_CHT_20261023.md) |
| Live linear sampled-network SPICE coupling (`em-spice-coupling`) | experimental | Python: run-em-spice-coupling | [Scope and limits](validation/EM_SPICE_COUPLING_20261023.md) |
| Supplied-field electromagnetic body heating (`em-body-heating`) | experimental | Python: run-em-body-heating | [Scope and limits](validation/EM_BODY_HEATING_20261023.md) |
| Same-mesh AC loss, thermal and elastic chain (`pi-ac-thermal-elastic`) | experimental | Python: run-dielectric-thermomechanical | [Scope and limits](validation/AC_THERMAL_ELASTIC_20261023.md) |
| Elmer FEM solver integration (`planned-elmer`) | planned | Unavailable | [Scope and limits](SOLVER_STATUS.md) |

