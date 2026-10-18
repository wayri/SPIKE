# SPIKE Solver Status

Experimental [shunt-capacitive fitted-network boundaries](CAPACITIVE_NETWORK_TRANSIENT.md)
add zero-initial-state capacitor voltage/derivative and distinguish source from
network current. Actual resistor loss uses source current; capacitor energy and
KCL evidence retain units/provenance. The bounded regular stable model has
independent RC/parallel-RLC references. General descriptor/nonlinear/combined-RLC
boundaries, integrated thermal handoff and measured qualification remain open.

Experimental [series-inductive fitted-network boundaries](INDUCTIVE_NETWORK_TRANSIENT.md)
now augment zero-initial-state transients with supplied R/L source/load states,
actual boundary derivatives, resistor power and inductor energy. Independent RLC
and coupled multiport references cover the bounded regular stable model. General
descriptor/capacitive/nonlinear boundaries, integrated thermal handoff and measured
broadband qualification remain open; this does not complete SI07 or PI/SI parity.

Requested [vibration, solder reliability, satellite/launcher, complete drone and
watch/geared mechanism studies](VIBRATION_VEHICLES_AND_MECHANISMS_PLAN.md) now
have tracked planned stages and validation gates. Dynamic environmental response,
calibrated joint fatigue, executable flight-controller/propulsion/aerodynamics
coupling and moving gear/watch contact are not established by current static
mechanics or scalar replay/gain co-simulation. No capability is promoted by this
scope expansion.

Experimental [3D static thermoelasticity](COUPLED_MECHANICS_MAGNETICS_DEVICES_PLAN.md)
now provides bounded isotropic P1 tetra stress, displacement, reactions and
elastic energy, plus executed same-mesh steady thermal-to-mechanical coupling.
Independent patches, thermal/traction references and manufactured refinement
cover this first stage. Worker APIs are available; mechanical UI, contact,
dynamics, failure/lifetime, general moving 3D machines and Hall transport remain
planned. This does not establish production qualification or complete parity.

[Requested active-part library work](library/REQUESTED_LIBRARY_CAMPAIGN.md) adds
20 functional logic families, an owned C++ four-state digital SDK and two
original compiled sampled controller models. Manufacturer acquisition metadata
is separate from runnable models. Full 54/74 coverage, 100 qualified variants
per active category, electrical/timing qualification and native Studio logic
binding remain open.

[SPIKES/KLayout IC/ASIC foundations](SPIKES_ASIC_TWO_APPLICATION_FLOW.md) now
include revision-bound flow preflight and actual native read-only layout
inspection. No technology-mapped physical closure, PDK DRC/LVS execution,
parasitic extraction or end-to-end ASIC qualification is established by them.

The [native 1D equilibrium semiconductor-field kernel](SPIKES_TCAD_EQUILIBRIUM.md)
solves homogeneous-material Poisson-Boltzmann electrostatics with prescribed
doping. Native analytical/manufactured-solution and Gauss-law tests establish
bounded mathematical behavior, not device qualification. Biased carrier
transport, I-V, device geometry/process simulation and full TCAD remain open.

Experimental [open-PDK profiles and circuit workflow](SPIKES_OPEN_PDK_WORKFLOW.md)
now inspect local SKY130/GF180/IHP installations, prepare corner/temperature
decks and execute them through explicitly selected ngspice after run-digest
approval. Actual execution evidence currently uses an original synthetic NMOS
fixture, not qualified foundry models. No full owned-engine PDK compatibility,
compiled-model loader, layout extraction or TCAD is established.

Experimental [user-defined electrical I/Q models and arbitrary-pin package
parasitics](SPIKES_EQUATION_DEVICES.md) now compose native-ready subcircuits.
Four-quadrant/NDR current and nonlinear conservative charge have native BE/BDF2
oracles. Package R/L/C/leakage works around user-supplied cores including HEMT
interfaces. This is not complete semiconductor parasitic physics, manufacturer
qualification, arbitrary-state DAE support or owned `K`-element execution.

The [native ideal CCM SMPS analytical model](SPIKES_SMPS_STABILITY.md), with
an explicitly selectable Python test reference, supports
supplied-parameter buck/boost/inverting buck-boost/flyback plants and rational
PI/Type-II/Type-III voltage-mode loops. It reports model crossings, poles and CCM
screening, not schematic extraction, native switching-loop stability or power-
level/hardware qualification. DCM, current-mode, delays and parasitics are
excluded. [Full SMPS coverage remains a roadmap](SPIKES_SMPS_ROADMAP.md).
See [native execution boundaries and measured acceleration](SPIKES_NATIVE_EXECUTION.md).

The source [AC PDN/filter workbench](PDN_SCREENING.md#explicit-ac-pdn-and-filter-workflow)
supports explicitly modeled R/L/C, ESR/ESL, signed coupled CM chokes, DM chokes,
ground/mutual capacitors, multiport/node transfer impedance and finite-rise
load-spike voltage histories. Its finite retained-dielectric P1 extractor derives
Maxwell C from electrode charge and independently checked field energy. Series
capacitor sharing review retains intermediate-node and leakage/balancing limits;
it never automatically adds voltage ratings. These are bounded approximate or
experimental source capabilities, not automatic arbitrary-PCB/full-wave PI,
dispersive/saturating magnetics, VRM control or deployed release qualification.

SPIKES now has an unqualified prescribed-current one-RC battery reference study
with configurable thermal response, self-discharge and empirical degradation.
Chemistry labels have synthetic defaults; no native battery MNA stamping or
manufacturer qualification is established. See [equations and validation](SPIKES_BATTERY_MODEL.md)
and [Studio workflow](SPIKES_POWER_BATTERY_WORKFLOW.md).

Original native laminar CFD and native Windows SU2 8.5.0 now share an executed
Re=100 square-cavity reference. Both converged on 16/32/64 grids; finest
centerline maximum differences were 0.016001 and 0.015698 times lid speed,
decreasing with refinement and meeting the predeclared 0.03 gate. See
[recorded validation](validation/NATIVE_SU2_CFD_20261011.md). This is experimental
isothermal 2D evidence, not general assembly CFD, turbulence or CHT qualification.
The isothermal cavity adapters do not advertise thermal or CAD support.
The separate SU2 CHT adapter now executes a three-zone fluid cavity between
hot and cold solid slabs through the bundled SU2 extension. Its 16/32-cell
stationary and moving-flow checks passed: conduction agrees with the analytical
series resistance to 0.000048 K; the finer moving case has 0.05853% global
heat-balance mismatch and 7.0718% heat-rate change from the coarser mesh.
These are experimental reference-case checks, not general assembly CHT or
mesh independence. The earlier two-zone moving case failed temperature
admission; a 64-cell three-zone conduction attempt timed out. Both remain
explicitly excluded from passed evidence. See [CHT evidence](SU2_CHT.md) and
[extension selection](EXTENSION_WORKSPACE_ENGINES.md#su2-cfd-and-cht).
Existing channel and OpenFOAM assembly results retain their own distinct scopes.

Geometry-based machine and actuator work now has an experimental planar
nonlinear P1 FEM workflow with Maxwell-stress force/torque, prescribed-current
quasi-static motion, stationary eddy-current diffusion and conservative planar
thermal coupling. See [machine study workflow](MAGNETIC_MACHINE_STUDIES.md),
[magnetic derivation](MAGNETIC_FEM.md) and [thermal derivation](MAGNETIC_THERMAL.md).
This does not qualify 3D STEP machines, conforming sliding interfaces,
moving-conductor losses, hysteresis, field/circuit drives or CFD coupling.

SPIKES native transient now exposes opt-in adaptive BDF2/trapezoidal controls,
bounded Newton-failure retries, source-corner history restart and sparse BE
companion cache reuse. Ordinary C/L nonlinear residuals use stable accepted-state
differences. [Validation and known switching limits](SPIKES_ADAPTIVE_SWITCHING_FOUNDATION.md)
include a buck conditioning repair that completes at the default 1-fs minimum
but rejects an insufficient 1-ps floor; these changes do not establish
ngspice parity, universal LTE or converter qualification.

Experimental [EM machine models](EM_MACHINES.md) execute reciprocal PM DC
motor/generator dynamics and a linear single-gap electromagnet. Independent
analytical/refinement and energy checks cover these supplied-parameter models.
They do not solve rotating CAD, nonlinear magnetic materials or spatial fields.

Experimental scalar co-simulation provides fixed-grid explicit-lag orchestration
with replay/gain adapters. Digital twin support compares recorded predictions
and telemetry at exact timestamps. These verify scheduling and residual
calculation only; they do not qualify physics, integrate FMI, acquire live
measurements or control hardware. Existing field/circuit and electrothermal
capabilities retain their separate limits.
See [workflow, evidence and staged plan](COSIMULATION_DIGITAL_TWIN.md).

Experimental [PALACE and Xyce workbenches](PALACE_XYCE_WORKBENCHES.md) provide
native configuration, bounded serial execution, diagnostics and native output
inspection through separately installed engines. PALACE supports six native
problem modes and optional sampled VTU field previews; Xyce accepts a deliberately
bounded circuit/netlist subset and CSV waveforms. Adapter and UI regression tests
do not establish native solver accuracy: neither runtime was available for live
qualification during this integration. These applications do not automatically
map board geometry, assign materials/ports or admit results as canonical SPIKE
PI/SI/EM fields. MPI, arbitrary plugins and automatic multiphysics coupling remain
unsupported. Platform and packaged-runtime limits are documented in each adapter.

Independent-job parallel execution is available in the source worker runtime
and local Solver manager panel, with explicit mutual-TLS remote enrollment.
This schedules existing bounded models; it does not provide single-solve MPI
or additional AMD/Intel GPU support. See
[worker pool capabilities and acceptance limits](PARALLEL_WORKER_MANAGER.md).

The experimental [PI engineering tools](PI_ENGINEERING_TOOLS.md) provide a
steady CCM converter loss estimate, approximate copper resistance routes, and
single-capacitor comparison on supplied passive sampled impedance networks.
Their analytical/circuit regression checks establish bounded software behavior.
They do not establish closed-loop switching transients, converter thermal
feedback, a continuous capacitor-placement optimum or HV hardware qualification.

A separate [native PWM electrothermal path](SOURCED_POWER_QUALIFICATION.md#actual-native-pwm-with-winding-thermal-feedback-2026-10-09)
now executes a synchronous behavioral-switch buck with persistent switching MNA,
cycle-sampled PI and winding-only lumped thermal feedback. Strict contracts,
cycle frames, explicit external switch/load losses, energy ledgers and
build-bound deterministic-replay restart are implemented. Independent switched
ODE/refinement and actual Python/native integration checks passed. This does not
upgrade the steady estimator above or establish vendor transistor switching
losses, semiconductor thermal feedback, deadtime, spatial cooling or hardware
correlation. Numerical human release review remains required.

A separate [retained-volume PWM mode](PWM_VOLUME_ELECTROTHERMAL.md) removes
embedded thermal RCs, conservatively maps all four device losses to explicit
tetrahedral cells and returns volume histories. It reuses prepared sparse solid
operators and native snapshots for window rollback, midpoint winding R(T)
feedback and unrelaxed temperature/energy convergence checks. Analytical,
switched-ODE refinement and actual uniform CalculiX history comparisons pass
within the [declared numerical fixtures](validation/PWM_VOLUME_CORRELATION_20261010.md).
General semiconductor temperature feedback, automatically mapped PCB devices,
airflow, measured correlation and release qualification are not implied.

The internal [laminar channel screen](INTERNAL_AIRFLOW.md) now returns conservative
wall-heated fluid temperatures, prescribed fully developed velocity and pressure
drop, with analytical and mesh-refinement regression checks. It is experimental,
not a general geometry Navier-Stokes, turbulence or solid-fluid CHT solver.
Retained solid transient studies also expose a [time-refinement check](THERMAL_ACCURACY_CHECKS.md).
Fresh [CalculiX and OpenFOAM cooling evidence](validation/THERMAL_COOLING_ENVIRONMENTS_20261009.md)
states the exact synthetic cases and untested interfaces.

The approximate DC resistive-network solver supports optional per-source
current-capacity feasibility using solved branch KCL. Over-capacity multi-sink
setups fail without regulated operating-point fields. This does not implement
CV/CC or foldback; other engines and modes reject the setting. See
[derivation, evidence and recovery](SOURCE_CURRENT_LIMITS.md).

Experimental native multiboard PI DC and SI single-frequency AC circuits can
deposit every explicitly mapped resistor/contact loss into retained tetra
volumes and iterate temperature-dependent resistance with the internal thermal
kernel or CalculiX. Analytical two-board and mechanical-part fixtures cover
DC/AC losses, RMS/peak conventions, feedback, contacts and saved-result admission.
This is steady reduced-circuit electrothermal coupling. See
[scope and evidence](MULTIBOARD_VOLUME_ELECTROTHERMAL.md).

The layered board thermal path now supports bounded manually specified local
rectilinear refinement and prescribed per-cell air/convection boundaries.
Physical-cell result plots/probes and an analytical parallel-passage fan-system
worker are integrated; see [inputs and evidence](ASSEMBLY_ELECTROTHERMAL.md).
Selective thermal pad numbers retain all copper artwork. Direct board losses
can now run without fabricated package resistances or junction temperatures.
Six native-board-bound estimated loss cases executed with explicit omissions;
the unlocated auxiliary loss and physical package/cooling qualification remain open.
The real single-Blade local-refinement replay conserves energy but **fails** its
0.1 K temperature comparison gate. Neither it nor the synthetic fan fixture
qualifies installed assembly cooling, package bodies or arbitrary enclosure CFD.

The [sourced power developer workflow](SOURCED_POWER_QUALIFICATION.md) adds
hash-admitted native OP/transient regression checks, source snapshots, actual
event-step caps and waveform evidence export. The separate resistor-feedback
thermal transient reuses MNA OP and thermal RC kernels; it is not an electrical
or semiconductor switching transient, airflow or hardware qualification.

The [coupled assembly electrothermal worker](ASSEMBLY_ELECTROTHERMAL.md) adds
experimental steady DC tetrahedral current/temperature feedback, matched-bond
Joule heating and supplied waveform, RMS spectral and semiconductor-table
averaged losses. Stored-energy-aware multi-terminal heat, rectangular
temperature/voltage/current loss tensors and a generated-PCB-mesh occurrence
binding are also executable, without arbitrary device or CAD inference.
A two-board ownership fixture, analytical energy balance and
four-grid electrical convergence are tested. General PCB extraction, arbitrary
device subcircuits, transient switching and measured qualification remain open.

The [retained thermal meshing workflow](ASSEMBLY_THERMAL_MESHING.md) now generates
project-bound tetrahedra for explicitly reviewed effective board layers and
single closed STEP mechanical solids. It requires the separately admitted local
Gmsh development runtime. [Reviewed component STEP promotion](THERMAL_COMPONENT_SOLIDS.md)
retains package volumes with explicit material and mounting transforms. Joint
OCC meshing gives touching occurrences conforming interfaces; automatic linking
uses reviewed retained resistance and rejects gaps, overlaps and conflicting
boundaries. Package volumes can receive existing board-circuit losses through
explicit thermal-only declarations without duplicating electrical devices.
Ambient convection and nonlinear Stefan-Boltzmann
radiation may act together on exterior faces; solid conduction and explicit
matched thermal contacts remain experimental. The desktop previews actual
mesh surfaces and saved nodal temperatures. The new retained-assembly airflow
compiler prepares conforming CHT cases and imports native fields, but native
execution and acceptance are pending because WSL is unresponsive. Box coating,
potting subtraction and larger solid mesh admission are described with their
actual evidence and remaining gaps in [capability integration](ASSEMBLY_CAPABILITY_INTEGRATION.md).
Arbitrary compound CAD remains unsupported. Experimental transient solid solves now add explicit material heat capacity and time-dependent heat loads; see [transient workflow](ASSEMBLY_THERMAL_TRANSIENT.md).

The [retained-volume EM adapter](RETAINED_ASSEMBLY_EM.md) executes explicit
conductor-resolved polyhedra with face-bound ports and E/H capture. It remains
unvalidated; mechanical board solids without copper/stack/excitations cannot
establish a device EM result.

The [retained assembly field reference](ASSEMBLY_FIELD_HANDOFF.md) adds bounded
experimental steady 3-D tetrahedral solid conduction, anisotropic material
rotation, matched thermal contacts and offline result bindings. Original
analytical/manufactured tests and geometric view-factor checks are recorded in
[validation](validation/ASSEMBLY_FIELD_20261004.md). This is not arbitrary CAD
extraction, airflow, coupled radiosity or a general assembly
Maxwell/SI backend. EM/SI handoffs retain ports but explicitly reject execution.

The assembly desktop workspace now imports these supplied volume studies,
edits thermal boundary values, executes the admitted steady thermal path and
reviews occurrence extrema and conservation evidence. `.spike` and standalone
records retain setup and optional results with stale-assembly withholding; see
[desktop integration checks](validation/ASSEMBLY_FIELD_DESKTOP_20261004.md).
The volume electrothermal editor integrates the separate native circuit coupling
contract, including CalculiX selection and saved temperature results. The viewer
offers occurrence filtering, Celsius/kelvin, exterior/interior mesh inspection
and a temperature scale shared across occurrences.

This file describes executable behavior. Catalog entries marked unavailable are
architecture contracts, not implemented physics.

The [loaded-design MCP conversation](LOCAL_LLM_MCP.md) can prepare, revise,
preflight and run the existing PI, SI/NEXT/FEXT, thermal, EMI-screening, trusted
extension and reduced multiboard worker paths. It reports missing inputs,
design/revision binding, asynchronous job status and actual solver evidence.
These tools add orchestration, not new numerical capability. Structural-ready
paths still require worker validation at execution; extension previews do not
qualify physics. Unsupported, partial and unvalidated results retain their
statuses. Eye diagrams require supported channels and explicit timing/models.

The main viewport EM results manager displays admitted spatial E/H samples,
time-average Poynting vectors, angular radiation, Optycal structure/interference
and linked returned-data graphs. Candidate amplitude nodes/antinodes and
display contours are visualization products, not additional solved samples or
proof of standing waves. Angular display spheres do not imply spatial fields.

The [SPIKE-owned internal tetra engine](INTERNAL_MESH_ENGINE.md) executes bounded
convex point-cloud generation, indicator/size/manual adaptive refinement and
interior quality optimization through a versioned worker method. Scalar nodal
and cell fields transfer on refinement-only passes. It remains experimental;
general constrained PCB geometry, moving-mesh remap and large/distributed
meshing are unsupported. Geometry tests do not establish SI/PI/EMI convergence.

The separate [whole-board focused volume path](PCB_FOCUSED_VOLUME_MESHING.md)
compiles normalized planar outlines/cutouts, layer slabs, copper with antipads
and explicit via spans into conforming tetrahedra through the admitted external
Gmsh OCC development process. Net/source/manual selections change sizing without
discarding background geometry. Its worker probe distinguishes preparation from
runtime availability. Four actual native examples retain all sources; this does
not qualify automatic EDA conversion, arbitrary PCB geometry or SI/EM/thermal
accuracy. Curved-source volume error and low cell quality remain reported.

The [external analysis extension path](EXTENSION_ANALYSIS_API.md) now admits
design-bound, finite `spike/v1` results into the desktop viewer and reports.
This is an integration capability. The host does not qualify an external
solver's physical method or turn imported field samples into validated data.

The optional [Optycal Suite](../extensions/optycal_suite/README.md) imports bounded,
closed STEP solids as PEC surfaces through the separately installed Gmsh runtime.
It uses complex, design-bound EMerge radiation samples as an assumed outgoing
far-zone source for one-way physical optics. Explicit source convention and
antenna aperture are required; proximity and observation-radius guards reject
nearby assembly cases. Direct and scattered complex fields share one reference
for pattern differences and coherent interference. This beta integration is
unvalidated, with no absolute field calibration, antenna input-matching feedback,
diffraction, shadowing, dielectric structures or multiple scattering. STEP
antenna solids alone do not specify feeds or an electromagnetic antenna model.
FreeCAD/KiCad/Kikakuka neutral STEP exports can provide the structure geometry;
an independently solved EMerge antenna result provides the excitation.

The [native Gerber route](EMERGE_GERBER.md) retains original copper files for
EMerge's `FileBasedPCB` loader alongside the KiCad/polygon adapter. EMerge
3.0.0a19 loaded original millimetre clear-polarity and inch flash/trace fixtures
and generated a 539-node, 2,622-tetrahedron mesh on October 4, 2026. This is
loader and mesh execution evidence, not RF solution or convergence validation.
Ports remain manual annotations, copper is surface PEC, dielectric extents are
declared rectangles, and Excellon execution is blocked while files are retained.

The optional [EMerge Suite](../extensions/emerge_suite/README.md) constructs
a bounded 2-16 copper-layer PCB model from imported SpiDeR, runs explicit pad-pair
ports and a frequency sweep, then imports S-parameters, angular far-field
cuts, and a coarse full-sphere sample grid for an interactive 3D pattern.
Its selected-net surface-PEC geometry, rectangular substrate, omitted
losses and air boundary need convergence and physical correlation. It has no
EMI compliance qualification. Adapter contract tests use API doubles. The
[four-layer ESP32 board surrogate](../examples/esp32/README.md) reduces the
source to F.Cu antenna copper, an ideal B.Cu reference plane, equivalent
dielectric and one explicit PEC short. EMerge 3.0.0a19 completed a three-point
2.30–2.60 GHz radiation run and a 1.0/1.5 mm mesh comparison; its generated
3D pattern and cuts are unvalidated and do not represent full-board RF
performance. A two-frequency, two-port fixture completed SI and radiation solves with EMerge
2.8.9 on Windows. A seven-frequency KiCad antenna fixture completed with the
EMerge 3.0.0a19 prerelease, including SPIKE result admission and sample probes.
Paired seven-frequency bare and ideal dielectric-cover cases also completed
on the same KiCad board; the [radome fixture](../examples/emerge/radome/README.md)
records their differing S11 and peak-normalized pattern samples. The cover is
one bounded dielectric box in the FEM geometry; the 5° surface and EM chamber
overlay are display interpolation. Curved radomes and imported complex
surroundings remain unsupported.
These are execution evidence, not mesh convergence or physical validation.
An original [four-layer regression fixture](../examples/emerge/multilayer/README.md)
also completed a two-frequency SI sweep with EMerge 3.0.0a19 and optional
EMCAD 0.1.0 copper unions. Unequal 0.2/0.5/0.3 mm dielectrics have independent
permittivities and a top-to-inner-layer port. Multilayer vias remain unsupported;
surface PEC, omitted dielectric loss and rectangular bounds remain explicit.
The [antenna walkthrough](EMERGE_ANTENNA_WALKTHROUGH.md) records the setup,
saved plots, numerical samples, and remaining qualification work.
The [expanded GUI examples](../examples/emerge/gui_workflow/README.md) record
four fresh EMerge 3.0.0a19 runs on September 30, 2026. Their saved readable
Python source hashes match executed-source provenance and all results pass
SPIKE admission. The lossy patch case returned 242 valid complex E/H XY-plane
samples at two frequencies. GUI controls now expose constant dielectric loss,
reference impedance, air margin, auto/SuperLU solving, parallel workers,
angular sampling and field port excitation. S-parameter and field CSV export,
Touchstone, explicit samples/probes and report evidence use actual returned data.
E/H amplitudes retain the solver port coefficient convention and require power
calibration for absolute interpretation. A full feature inventory explicitly
marks non-integrated EMerge studies and boundaries as pending adapters.

The [Marble/White Rabbit SI experiments](../examples/emerge/board_si/README.md)
completed source-derived four-port coupled-route sweeps with EMerge 3.0.0a19 and
EMCAD 0.1.0: 64 frequencies from 100 MHz to 6.4 GHz and 7,744 valid E/H samples
per model. The adapter now accepts explicitly mapped 2–8 ports across up to four
signal nets. These examples idealize the reference planes and terminals and omit
the rest of the boards. Marble passed sampled passivity; an independent two-point
SuperLU/automatic-backend comparison agreed within 1.20e-11 in complex S.
Both models exceeded a strict 1e-6 reciprocity residual tolerance. White Rabbit
also exceeded the eye passivity gate (maximum singular value 1.001609); a finer
mesh and doubled air margin did not remove this failure. Its eyes are blocked.
Marble's 500 Mb/s differential and single-ended diagnostic eyes use a separately
disclosed ideal-through DC assumption, 150 ps edges and matched ideal endpoints.
They are finite-bandwidth scenarios, not source-device or link qualifications.
The offline report, raw Touchstone/CSV, source/script bindings and probes reside
under local `build/emerge-si`; source boards are not redistributed by this example.

For governing equations, implementation links and evidence interpretation, see
the [solver handbook](SOLVER_HANDBOOK.md). The [annotated research references](SOLVER_REFERENCES.md)
distinguish recorded method lineage from external tools, datasets and future candidates.

## Loaded SI workflow (experimental)

Optional [NRZ transition-PI recovery](SI_CLOCK_RECOVERY.md) now processes the
full loaded receiver waveform and reports recovered samples separately from
fixed-clock eyes. The [linear voice-coil drive](VOICE_COIL_DRIVE.md) couples
current, reciprocal back EMF and motion with a discrete energy audit. These
bounded behavioral models do not establish protocol or field qualification.

The [10.3125 GBd reference checks](SERDES_REFERENCE_QUALIFICATION.md) exercise
analytic loaded transfers and a matched NRZ eye. They do not establish KR/SFI
compliance or implement the BASE-T PHY. The all-interface delivery plan
separates those remaining requirements from actuator work.

The new [actuator force-map reviewer](ACTUATOR_FORCE_MAP.md) checks supplied
force/coenergy consistency for three actuator classes. It does not generate
fields, simulate motion or expose private force kernels as a product solver.

The separate [fixed-excitation actuator motion module](ACTUATOR_MOTION.md) now
integrates a supplied, admitted force map with mass, damping and a linear spring.
It stops at stroke boundaries and reports work/energy balance; geometry-to-field
extraction and drive-circuit/back-EMF coupling are not implemented by this module.
The loaded SI workflow now preserves exact physical NRZ symbol timing rather
than rounding the requested rate to its FFT grid; see [clock correction](SI_WORKFLOW.md#physical-clock-correction).

The [source-to-receiver workflow](SI_WORKFLOW.md) connects RLGC/Touchstone or
bounded board extraction to configurable endpoints, deterministic aggressors,
graded passives, port edits, loaded transfer, waveform/eye/TDR and noise reports.
IBIS support is inventory plus explicit DC-slope/ramp reduction, not nonlinear
switching or AMI simulation. Results and exports retain these limitations.
The SI workflow returns matched per-port reflection/VSWR with
finite/infinite/non-passive sample status, plots returned TDR reflection, and
requires actual finite E/H vectors for field plots. Network-only SI results
explicitly report spatial field maps as unsupported. Bounded four-port
NEXT/FEXT and eye execution evidence is in
[the SI capability record](validation/SI_CAPABILITY_VOLUME_PEEC_20260928.md).

The reliability checks
cover finite-record PAM4 sampling and controlled cross-board
mesh refinement with fixed PML interfaces. These corrections do not promote
the experimental workflow to protocol or general field qualification.

## Operational

### Multi-board analysis scope

PI, SI, thermal, and EMI can plan independent board occurrences with stable
assembly identities, separate direct connector mates and cable harnesses, and
reject pin reuse across those links. Desktop PI, thermal, and EMI requests bind the selected
active-design board occurrence; EMI preflight/screening and component thermal
also validate that scope before execution and retain it in result provenance.
An occurrence of another design is not silently substituted. Independent
planning is a dispatch contract, not a coupled solve. The assembly editor now
executes explicit reduced coupled models: shared PI DC/AC and SI AC circuits
with harness/mate/contact RLC, shared thermal RC networks with inter-board
contact conductance, and reciprocal magnetic RL loop coupling for EM screening.
Analytical fixtures check remote-load/contact sensitivity, heat sharing,
induced currents, reciprocity and conservation. These models remain
experimental/approximate; artwork is not automatically extracted into them.
General coupled field qualification and radiation/EMI compliance remain open.
The reduced models now require explicit coverage of physical casings and other
mechanical parts. Thermal admits part RC nodes, contacts and reciprocal
radiosity surfaces; PI/SI admits passive part RLC and retained bond R/L; EM
admits part-owned magnetic loops. One board plus a physical structure is
supported. Model-less hierarchy containers are explicitly excluded. Imported
STEP/material data does not infer numerical properties or produce full-field
geometry. [Structure study evidence](validation/ASSEMBLY_STRUCTURE_STUDIES_20261004.md)
records analytical checks, portable save/reopen and the remaining solver-suite
field integration requirements.
See [coupled studies](MULTIBOARD_COUPLED_ANALYSIS.md) and
[assembly workflow](MULTIBOARD_HARNESS_ASSEMBLIES.md).

### Authored harness DC PI (`spike/harness-pi-request/v1`)

- State: executable experimental lumped DC, not board-field coupling.
- Explicit connector-pin/splice sources, loads, ground and mated-contact R;
  native MNA returns terminal voltage/current and wire/contact losses.
- GUI/text pin matching and CLI `harness-pi --request` share the existing harness
  document. Connector catalog estimates are metadata, not implicit circuit values.
- Analytical loop and retained Marble connector/placement smoke checks pass;
  no Marble copper or measured multiboard correlation is claimed.
- See [Harness PI](HARNESS_PI.md) for limits and remaining coupled PI/SI work.

### Authored harness SI and EM preparation

- State: executable experimental supplied uniform two-port RLGC SI. Explicit
  differential pairs or signal/return wires preserve physical endpoint identity.
- DC supports an explicit power/return subset in a mixed harness. Parallel
  conductors remain distinct elements; no resistance is inferred from roles.
- SI reuses the owned uniform-line network kernel. A matched 100-ohm, 10 ns
  lossless-line oracle checks complex transmission and zero reflection.
- Saved SI results are bound to their complete request. A separate experimental
  Python multi-conductor backend now supports exact sampled matrix RLGC,
  branches/parallel paths, explicit contact/load models, mode conversion and
  crosstalk. A bounded approximate straight round-wire/ideal-plane extractor
  supplies frequency-dependent skin-effect RLGC. Twelve network and twelve
  geometry analytical/refining-oracle tests pass; desktop integration is separate.
  Arbitrary shielded/twisted cable extraction, PCB field coupling, independent
  external-solver/measured qualification and radiation fields remain pending.
- EM preparation returns unsupported requirements, never a field result.
  See [harness engineering](HARNESS_ENGINEERING.md) for contracts and recovery.

### Copper Geometry DC (`spike.routed_dc`)

- State: available
- Geometry: tracks, through vias, pads, polygonal copper zones
- Excitation: multiple voltage sources and current sinks
- Models: explicit source/load contact and package resistance
- Results: voltage, voltage drop, branch current, current density, solved probes
- Numerics: sparse resistive network; finite-volume zone spreading; policy-
  controlled NumPy/Numba assembly and SuperLU/PETSc-MUMPS sparse solve
- Limit: zone sign-off requires a mesh-convergence comparison

### Native PEEC RLCG (`spike.peec_2_5d`)

The source finite-volume matrix bindings are available. On two provisional local slices, the bounded common-volume
path passes the energy gate where the legacy line kernel fails. AC now retries
that path by default after legacy nonpassivity; explicit `disabled` preserves
the fail-closed legacy behavior. Results remain approximate driving-point
networks and are not calibrated SI S matrices; see
[the volume PEEC record](validation/SI_CAPABILITY_VOLUME_PEEC_20260928.md).

Local checks found real-board nonpassivity and tested a finite-volume
rectangular/annular implementation. Earlier routed Marble matrices passed the
energy gate without projection, but an independent support audit found current
bases outside filled copper. The current opt-in runtime fails that Marble AC
request with `PEEC_ZONE_BASIS_OUTSIDE_COPPER` before native integration;
historical positive-energy matrices are not qualified board results. The
original C383.1 terminal is physically disconnected. Geometry, contact,
capacitance, mesh-refinement and deployment gates remain open. The earlier
zone/pad C estimator returns `unsupported`/0 F for ambiguous Marble copper.
The newer opt-in volume dispatcher uses an experimental unique-source-area
surrogate instead; its direct Marble sparse-DC audit reports about 3.82 pF,
but source/via coverage is incomplete and the AC request still fails the
zone-support gate before native integration. Neither value is a measured or
field-derived capacitance. The conforming geometry prototype is not wired
into production: its 32k–38k branches exceed the 8,192-pair dense field cap,
its current two-point DC refinement does not converge monotonically, and the
native pair kernel does not handle spatially separate annular via barrels.
An isolated hybridized RT0 sparse-DC experiment passes finite-contact,
conservation and affine patch fixtures but is not registered. Pinned Marble
1/0.5/0.25 mm resistance is 4.8841/4.4545/4.2806 mOhm, so its final
refinement change is still 4.06% against the 2% gate. Fixed-copper contact
refinement changes less than 0.1%, while a bounded interior-cell diagnostic
changes the result materially; neither is a qualified solution.
An isolated spectral-energy prototype passes small mixed-geometry tests but is
not integrated: finite-domain quadrature has no certified error bound and
Marble-scale work remains unmeasured.
See [the refinement repair record](validation/PEEC_REFINEMENT_REPAIR.md).
Transient rejects negative-energy modes instead of projecting the matrix. Do
not infer readiness from preflight alone.
The [PEEC safety policy](PEEC_SAFETY_POLICY.md) records native admission,
capacitance, MNA, failed-result/export and reviewed-port checks plus local rollout.

- State: experimental when `spike_peec_native` is packaged
- Geometry: routed tracks, polygonal copper zones, SMD/THT pads, plated vias,
  and through-pad barrels in one connected hybrid mesh
- Results: port-referred frequency-dependent resistance, partial inductance,
  approximate single-reference capacitance/dielectric conductance, complex
  impedance sweeps, and branch-current magnitude
- Models: smooth isolated-slab skin effect, optional Hammerstad RMS roughness,
  imported stackup permittivity, and loss tangent where supplied
- Numerics: native C++/Eigen partial-element matrices plus branch-incidence
  modified nodal analysis; planar copper uses a finite-volume grid
- Resource admission: dense PEEC derives its branch capacity from the configured
  solver-memory allowance and detected physical RAM. The default allowance is
  2 GB; users may set a stricter explicit branch cap. Admission is recorded in
  result provenance and does not change the solver's experimental validity tier.
- Limits: proximity effect, arbitrary-geometry/multiconductor capacitance,
  via/antipad capacitance, Huray/gradient roughness, geometry-derived
  S-parameters, and full-wave radiation are not included
- Validity: quasi-static wavelength limit is checked and reported

### Geometry PEEC transient (`spike.peec_rl_transient`)

- State: experimental and executable when `spike_peec_native` is packaged
- Excitation: constant, step, pulse, and piecewise-linear voltage/current
  terminal profiles with explicit timing, timestep, frame, wall-time, and
  memory budgets
- Numerics: backward-Euler integration over conductor R, the mutual partial-L
  matrix, and optional single-reference stackup shunt capacitance
- Results: timestamped voltage, drop, current, density, loss, via stress,
  probes, and bounded 2D/3D visualization frames
- Limits: no nonlinear device equations, dielectric loss/dispersion, via
  capacitance, radiation, or transmission-line/full-wave propagation
- Validation: analytical waveform and topology regressions pass; measured
  time-domain and independent field-solver correlation remain required

### Native linear MNA (`spike/native-mna-request/v1`)

- State: implemented, experimental, and not eligible for PI release promotion
- Elements: linear resistor, capacitor, inductor, independent voltage/current
  sources, and VCCS, VCVS, CCCS, and CCVS dependent sources
- Analyses: DC operating point, linear AC sweep, and bounded fixed-step
  backward-Euler transient analysis
- Results: `spike/native-mna-result/v1` with node and element values plus
  structured diagnostics and explicit `experimental` model status
- Verification: focused analytical tests cover resistor dividers, current
  sources, all four dependent-source classes, RC AC response, RC transient
  response, source waveforms, nonlinear rejection, and singular diagnostics
- Integration boundary: the service and CLI expose direct request validation and
  execution plus reviewed SPICE-workspace compilation/execution. A reviewed
  field/circuit package can invoke the native PEEC reduction provider and this
  MNA core through a deterministic fixed-point loop.
- Limits: nonlinear semiconductor and behavioral devices, adaptive timesteps,
  sparse/iterative linear systems, general automatic PEEC-to-circuit
  compilation, and electrothermal feedback are unsupported and must fail
  closed. The fixed-point field/circuit route is experimental, requires an
  explicit reviewed package, and is not a general FEA or electrothermal path.
- Release status: the integrated core remains experimental and cannot satisfy
  the native SPICE-compatible workflow gate until independently validated under
  the native PI qualification tests.

### SPIKES owned circuit kernel and CLI

- Native SIN increment (2026-10-12): analytic voltage/current sources execute
  at internal adaptive solve times, preserve phase-dependent predelay values,
  force the delay breakpoint and retain persistent-session global time.
  Equal-model source/RC ngspice checks pass; EXP/SFFM remain sampled PWL.
  See [scope and numerical checks](validation/NATIVE_SIN_PARITY_2026-10-12.md).

- State: experimental circuit and integration foundation; not performance-qualified
- Native parity increment (2026-10-10): owned `native-run` now orchestrates the
  bounded `.step` and `.measure` subset without backend substitution. Transient
  measurements integrate the piecewise-linear samples in time; DC statistics
  remain sample-weighted. Behavioral tangent/inverse-hyperbolic-tangent values
  and Jacobians execute in the C++ DAG. Fourteen small equal-model fixtures
  pass native/ngspice common absolute-error gates; this is not matched internal
  tolerance, complete compatibility, manufacturer, or performance evidence.
  See [deck qualification](../standalone/spikes_project/studio/docs/NATIVE_DECK_QUALIFICATION.md).
- Native kernel: strict-floating-point C++ modified nodal analysis for linear
  R/C/L elements and independent DC current/voltage sources, plus DC
  Shockley-diode, three-terminal Ebers-Moll BJT, and four-terminal Level-1
  Shichman-Hodges MOSFET residual/Jacobian paths. The MOSFET includes body
  effect, channel-length modulation, reverse terminal operation, and finite
  off conductance. The nonlinear solve provides damped Newton, limiting where
  applicable, overflow-safe exponential continuation, and explicit
  nonconvergence
- Linear backend: pivoted dense LU remains the general MNA reference. The
  native DC path assembles a compressed sparse matrix directly and reserves
  the complete nonlinear Jacobian pattern before Newton iteration. It provides
  COLAMD-ordered sparse LU and rank-revealing sparse QR with symbolic-pattern
  reuse across Newton numeric factorizations, plus row-equilibrated
  ILUT-preconditioned sparse GMRES with an
  original-system residual gate. It additionally provides diagonally preconditioned conjugate
  gradient for symmetric positive-definite systems, strict symmetry/positive-
  definiteness failure gates, automatic LU fallback, configurable iteration
  tolerances, and opt-in OpenMP matrix-vector/dot execution. Row-equilibrated
  restarted GMRES adds a bounded general-MNA path with two-pass modified
  Gram-Schmidt, Givens updates, and final unscaled-residual verification. The
  legacy restarted-GMRES path remains available as a dense reference. Automatic
  dispatch uses dense LU for small systems, sparse LU for larger systems, and
  attempts ILU-GMRES before sparse LU at the largest current threshold. Sparse
  DC factorization is currently single-worker. Linear and nonlinear transient systems at the
  configured size threshold now assemble directly into sparse triplets, reuse
  COLAMD symbolic analysis for an unchanged pattern, and perform numeric-only
  SparseLU refactorization when companion or nonlinear Jacobian values change.
  Dense nonlinear assembly remains the small-system reference; stronger
  preconditioners and parallel sparse factorization remain required for
  production scale.
- Native transient: bounded dense backward Euler, event-aware hybrid
  trapezoidal, and variable-step BDF2 integration support ideal
  capacitors/inductors, explicit C/L initial conditions or DC initialization,
  nonlinear Newton/backtracking, shortened final steps, periodic PULSE and PWL
  current/voltage sources, and per-sample node/element voltage, current, and
  power. The requested timestep is a maximum: every PULSE phase boundary and
  PWL knot forces an exact solve point and remains subject to the hard step
  bound. Hybrid mode uses BE at startup/source events and trapezoidal companion
  models between events. BDF2 uses unequal-step coefficients, retains two-step
  C/L history across persistent calls and checkpoints, and restarts with BE at
  startup/source events. An opt-in embedded BDF2/BE or trapezoidal/BE defect
  controller rejects and retries candidate steps, enforces a minimum timestep
  and rejection budget, and reports accepted-step bounds. Diode,
  charge-storage dynamic-diode, and smooth controlled-switch systems now use
  a genuine second Newton solve for the BE
  companion at the same endpoint; failure of that companion is treated as an
  infinite defect and reduces the timestep. The startup/event BE step itself
  has no embedded estimate; nonlinear companion solves use the sparse path at
  the configured threshold.
  The bounded qualification is recorded in
  `docs/validation/NONLINEAR_EMBEDDED_LTE.md`.
  Exact-matrix dense LU caching reuses
  linear companion matrices and exact nonlinear Jacobians under bounded
  entry/memory limits. A native two-terminal dynamic diode adds one implicit
  diffusion-charge state, junction capacitance, reverse-recovery terminal
  current, BE/BDF2 residuals, and analytic Jacobians. Hybrid trapezoidal mode
  rejects this device until a charge-consistent companion is implemented. A
  coupled electrothermal resistor stamps temperature-dependent conductance,
  Joule heat, Rth, and Cth on an explicit temperature-rise node. A smooth
  saturating inductor stamps an energy-consistent flux-linkage law with
  positive differential inductance through the saturation knee. Both support
  BE/BDF2 and embedded LTE and currently reject hybrid trapezoidal mode.
  The bounded five-terminal GaN/SiC WBG model integrates conservative terminal
  charge and its electrothermal `Rth-Cth` state under BE/BDF2, including
  reverse conduction and avalanche. Level-1 MOSFET and Ebers-Moll BJT charge
  storage supports conservative lumped CGS/CGD/CDS and CBE/CBC/TF/TR companion
  stamps under backward Euler/BDF2; hybrid trapezoidal is explicitly rejected.
  These are bounded original charge models, not full production compact physics. The
  transient engine remains a correctness reference, not production SPICE.
- Native switching: a four-terminal voltage-controlled switch provides finite
  Ron/Roff, a smooth threshold transition, an analytic control Jacobian, and
  bidirectional terminal current. This enables initial PWM-driven converter
  circuits but is not a semiconductor compact model or converter validation.
- Diagnostics: singular/numerical/nonconverged status, residual, pivot,
  nonlinear-iteration, damping, junction-limit, breakpoint,
  BE/trapezoidal/BDF2, dense and sparse factorization/reuse/cache counters,
  symbolic analysis, numeric-only refactorization, embedded-LTE rejection/ratio
  and accepted-step bounds, node voltages, and per-element
  current/power
- Embedding: versioned opaque-handle C ABI (`SPIKES_ABI_VERSION == 1`) with
  exception containment and explicit ownership. Additive transient API v1
  exposes C/L construction, PULSE/PWL sources, the controlled switch, the
  charge-storage dynamic diode, electrothermal resistor, saturating inductor,
  DC Level-1 MOSFET and Ebers-Moll BJT construction, adaptive-controller
  options,
  versioned/size-guarded options, immutable sample results, and diagnostics. An
  explicit-path Python `ctypes` bridge verifies ABI compatibility and owns
  native circuit/result lifetimes.
- CLI: `spikes check|compile|run` accepts a fail-closed R/C/L/V/I/D/E/G/F/H
  subset plus affine single-control B sources with
  one `.op`, linear single-source `.dc`, or strict bounded `.tran TSTEP TSTOP`
  analysis and V/I/P probe descriptors. The ordinary CLI transient executes
  through the Python native-MNA reference engine and records that boundary.
  `spikes native-run --library PATH` is the explicit owned-kernel route for
  `.op`, independent-source `.dc`, and `.tran`, including PULSE/PWL sources, inline native controlled
  switches, hierarchy, V/I/P probes, selectable `trap|be|bdf2` integration,
  breakpoint/factorization diagnostics, and owned-engine provenance. It never
  searches for a library. Standard diode instances and top-level
  `.model NAME D(IS=... N=... TNOM=...)` cards execute through the owned diode
  ABI; unsupported diode options and standard switch `.model` cards remain
  blocked.
- Compiled console/dashboard: `spikes_console` loads a bounded native `.spkc`
  project or a built-in demo and runs directly on a persistent C++ transient
  session. It supports live and runtime-attached node/element V/I/P,
  electrothermal temperature, dissipation, and aggregate failure-margin
  probes; bounded rolling histories and CSV export; ASCII trends; source
  set/toggle controls; checkpoint/restore; scripted execution; and best-effort
  wall-clock pacing. The same implementation is reusable through the
  `spikes_dashboard` static library. This is not complete SPICE syntax, a
  deterministic hard-real-time scheduler, or physical-HIL qualification. See
  the separate circuit engine tests.
- Linear analysis wave 3: versioned executable Python-reference contracts add
  uncorrelated resistor Johnson-Nyquist noise propagated through the exact AC
  MNA system, central-difference complex AC sensitivities for R/L/C values, and
  generalized-descriptor pole/SISO-zero extraction. Analytical resistor-noise
  and RC sensitivity/pole fixtures pass. This does not include semiconductor
  noise, nonlinear operating-point linearization, adjoint sensitivity,
  Volterra/distortion analysis, or pole-zero cancellation reduction; see
  the separate circuit engine's tests.
- Nonlinear language/analysis waves 4-6: a safe differentiable AST supports
  bounded memoryless multi-control B voltage/current expressions with analytic
  gradients and hierarchical scoping. A dense reference Newton engine executes
  R/V/I/E/G/F/H/B/diode operating points, bias-linearized memoryless small
  signal, resistor-plus-diode biased noise, nonlinear adjoint sensitivities,
  and local third-order one-tone distortion. Wave 6 adds SPICE-style `TABLE`,
  `URAMP`, `U`, `SGN`, `FLOOR`, `CEIL`, `INT`, and modulo semantics with
  analytic gradients away from explicitly rejected discontinuities. Diode
  `.model` cards accept `KF`/`AF`, and biased noise reports the white
  shot/thermal plus frequency-dependent 1/f spectrum and integrated variance.
  These are analytical correctness fixtures, not native production
  implementations. Bounded complex source-correlation matrices and a
  frequency-dependent one-source/one-tone third-order Volterra reference are
  executable. Device-internal BSIM correlated noise, arbitrary multi-tone
  Volterra grids, harmonic balance, and complete SPICE3 expression/deck
  semantics remain absent.
- Hierarchy: bounded `.subckt`/`.ends` definitions and positional `X` instances
  support forward references, nested deterministic flattening, private local
  nodes, hierarchical probes, and hierarchical DC-source sweep paths. Recursive
  definitions and expansion overflow fail closed. Bounded arithmetic `.param`
  scopes, subcircuit defaults/overrides, top-level `.global`, and root-confined
  UTF-8 `.include` / selected `.lib` sections are implemented with explicit
  expression, path, cycle, depth, file-count, byte, and line limits. Parameter
  functions/conditionals and scoped model cards remain unsupported.
- Step/measure slice: ordinary `spikes run` executes bounded linear
  `.step param` Cartesian variants (eight axes, 10,000 variants, and two
  million variant-by-analysis work points) in deterministic leftmost-outermost
  order. Scalar OP/DC/transient `MAX`, `MIN`, `AVG`, `RMS`, and `FIND`
  measurements execute with explicit sample windows/interpolation and
  per-measure failure records. This is a bounded reference-runner feature;
  `native-run` rejects it, and full SPICE stepping/measurement syntax is not
  claimed.
- Archetypes: the versioned built-in registry remains a separate ideal-model
  catalog. The owned C++ ABI now exposes DC diode, Ebers-Moll BJT, and Level-1
  MOSFET construction, but these have not been promoted into a qualified
  redistributable part library because dynamic charge, electrothermal behavior,
  parameter-card compatibility, and vendor qualification remain absent.
- Persistent execution foundation: immutable content-addressed compiled-block
  metadata, stable numeric signal/control IDs, checkpoint/restore, bounded
  event history, deterministic lockstep, best-effort wall-clock pacing, safe
  trip/re-arm, and typed momentary/toggle/pulse/set/increment/ramp controls are
  implemented in Python. An additive native session now copies a circuit once,
  updates constant sources, advances stateful backward-Euler, hybrid-
  trapezoidal, or BDF2 steps, reports
  cumulative diagnostics, and supports owner-bound native checkpoint/restore
  through C and Python. Persistent global PULSE/PWL time, exact internal source
  breakpoints, PWL interpolation, and waveform-position checkpoint restore are
  implemented. A bounded full-matrix-keyed workspace reuses LU factors across
  session calls and exposes factorization/reuse/cache diagnostics. Persistent
  capacitor-current/inductor-voltage and two-step C/L history enables hybrid or
  BDF2 stepping and is rewound by checkpoints; actual source events restart
  with BE. Large nonlinear steps can use the sparse assembly path, but the
  session is not preallocated, deterministic WCET, or hard HIL.
- Digital foundation: an experimental bounded four-state event kernel provides
  `0/1/X/Z` resolution, deterministic integer ticks and delta cycles, primitive
  gates, tri-state drivers, and D flip-flops. It is not a Verilog/VHDL compiler,
  timing sign-off engine, MCU/FPGA emulator, or analog/digital bridge.
- Model-builder foundation: versioned content-addressed sources, parameters,
  datasets, validity envelopes, deterministic fits, black-box descriptors, and
  qualification records are implemented with a Shockley-diode reference fitter.
  LLM extraction is always unreviewed evidence; named review, independent data,
  metric gates, digest verification, and a rechecked export safety floor are
  required before a model can become runnable.
- Dynamic-diode path: an executable bounded Python constitutive model
  provides temperature-scaled Shockley conduction, analytic conductance,
  continuous depletion charge/capacitance, implicit-Euler transport charge,
  reverse recovery, and an analytic transient Jacobian. The native C++ MNA
  path now provides a smaller charge-control form with an implicit diffusion
  state, junction capacitance, BE/BDF2 stamping, reverse-recovery current, and
  additive C/Python ABI construction. Neither path is vendor-qualified; see
  the diode model tests and
  `docs/validation/NATIVE_DYNAMIC_DIODE_DAE.md`.
- Complex-device extension foundation: immutable metadata declares electrical,
  thermal, rotational, translational, magnetic, and acoustic power ports;
  parameters/states/observables; residual/Jacobian/event capabilities; validity
  envelopes; runtime provenance; and explicit four-quadrant, NDR, passivity,
  and reciprocity behavior. Bounded registration validates exact host
  capabilities and rejects untrusted native runtimes. Registration is metadata
  only: arbitrary extension code is not loaded or executed.
- Reviewed compiled-control boundary: exact executable/manifest/evidence
  digests admit trusted local JSON-subprocess control blocks with fixed argv,
  strict finite port/state schemas, timeout and I/O limits, a fresh working
  directory, and stable failure codes. This is not hostile-code isolation, a
  solver callback ABI, or Verilog-A/OSDI/HDL compilation; see
  the separate circuit engine tests.
- OSDI 0.3 DC boundary: trusted digest-reviewed modules can register directly
  as first-class C++ MNA elements. On Windows, hostile-marked OSDI DC requests
  instead use a digest-bound zero-capability AppContainer worker; real-model,
  forbidden-file, and denied-network probes pass. Transient/reactive, noise,
  limiting, OSDI 0.4, non-Windows hostile isolation, and general compiled-block
  sandboxing remain open; see the separate circuit engine tests.
- Signed I/V references: bounded tabulated and analytic polynomial evaluators
  preserve negative voltage/current, generated versus absorbed power, exact
  small-signal slope, and explicitly authorized negative differential
  resistance. No positive-slope clamp or passive-only assumption is applied.
- Virtual instruments: bounded, calibrated waveform/response contracts feed an
  edge-triggered scope, DMM mean/RMS/frequency, windowed radix-2 spectrum
  analysis, one-port S11/Z conversion, and Smith coordinates. Active and
  negative-resistance responses with reflection magnitude greater than one are
  preserved. Native transient and persistent-session waveform bridges enforce
  explicit uniform timebases before scope/FFT use.
- Streaming results: fixed-capacity multi-channel rings overwrite and count old
  samples; trigger engines retain only bounded pre/post windows with hysteresis,
  holdoff, queue limits, and drop accounting. The experimental `.spkw` writer
  uses independently decodable CRC-protected chunks, a hard file-size limit,
  recoverable torn tails, and lossless raw/zlib/XOR-zlib/LZMA codecs. Compression
  and disk I/O are not permitted to imply hard-real-time qualification; see
  the separate circuit engine tests.
- Qualified local model-index foundation: exact-digest model records and KiCad
  `Library:Symbol` mappings require explicit redistribution approval,
  license-evidence digests, reviewed qualification, complete one-to-one pin
  binding, and immutable parameter overrides. This is a fail-closed format,
  not a populated vendor library; see the separate circuit engine tests.
- Limits: no production compact semiconductor library,
  complete deck-syntax AC/noise/pole-zero/sensitivity coverage, complete SPICE
  behavioral semantics, production arbitrary-multitone frequency-dependent
  distortion analysis,
  event-state hysteresis, qualified switching-specialized solver, multiport
  VNA/de-embedding, rendered instrument UI, adaptive native event queues, KiCad
  schematic adapter, executable extension loader, HDL/C/C++ block compiler,
  native lock-free capture ring, asynchronous disk writer, rotating archives,
  virtual MCU/FPGA, mixed-signal bridge, multimodal LLM runtime, or HIL
  qualification yet
- Competitive claim gate: whole-product ngspice parity/superiority is blocked.
  Current development adds bounded SIN/EXP/SFFM source parsing/reference evaluation and
  owned-kernel analytic SIN evaluation plus EXP/SFFM PWL lowering on the requested
  transient grid, with analytical native tests. The bounded SIN/RC ngspice checks
  do not qualify all source families. See [analytic source limits](INTERNAL_SPICE_SOURCE_WAVEFORMS.md)
  and [remaining development milestones](INTERNAL_SPICE_DEVELOPMENT.md).
  The ten fail-closed gates and current machine-readable status are documented
  in the separate circuit engine tests and
  `docs/validation/spikes-ngspice-competitive-gate.json`.
- Compiled board preview: an internal-engine-only exporter generates a native
  shared library with C/C++ object APIs and explicit Python loading. Independent
  instances accept finite-resistance voltage drives, bounded steps and named
  voltage/current observations, with save/restore/reset. The exporter admits RLC,
  constant independent sources, static Shockley diodes and static Level-1 NMOS.
  Explicit finite-resistance fault bridges and VTO edits retain accepted dynamic
  state and are restored by checkpoints. A linked host C++ firmware example
  exercises RC settling, loading drops, ADC quantization and sampled threshold
  polling; broader engine device support is not automatically admitted. No MCU
  instruction execution, FMI conformance, external-engine board libraries or
  automatic PCB parasitic/multiphysics extraction is established. See
  [package contract and numerical evidence](COMPILED_BOARD_LIBRARY.md) and
  [research/adapter boundaries](BOARD_LIBRARY_RESEARCH.md).
- Fault co-simulation: native resistor/VTO setters and compiled-board fault
  descriptors support finite gate-source, drain-source/body-diode shunts,
  degraded shunts and threshold shifts. Scheduled events split integration
  steps, preserve capacitor/inductor state and replay with checkpoints. Supplied
  FIT plus early-life/wear-out Weibull hazards can select event times; supplied
  environmental coefficients map Kelvin, rad(Si), humidity and vibration into
  explicit fault parameters. These are conditional scenarios, not calibrated
  failure mechanisms, SEE prediction or hardware qualification. See
  [fault/reliability scope](SPICE_FAULT_RELIABILITY.md).
- Transient deck controls: `.tran TSTEP TSTOP [TSTART [TMAX]] [UIC]` now
  distinguishes integration from retained output, enforces bounded TMAX and
  retains the final stop point. An actual ngspice 46 RC comparison is covered in
  [control evidence](INTERNAL_SPICE_TRANSIENT_CONTROLS.md).
- Benchmarks: a bounded accuracy-first harness supplies analytical cases,
  warmups/repeats, hashes, explicit timing scope, and a no-shell external JSON
  adapter; speed is withheld whenever any measured repeat fails accuracy.
- Qualification corpus: fourteen native/interactive scenarios exercise a balanced
  bridge, direct and two-worker CG 200-section ladders, sparse-LU/ILU-GMRES on
  a 1000-section general-MNA ladder, a GMRES/LU controlled-
  switch cross-check, Shockley diode,
  analytical underdamped RLC, a 50 MHz-class resonator, a fixed-back-EMF
  motor-armature electrical model,
  breakpoint PWM, synchronous buck, native stepwise user controls,
  checkpoint/replay, continuous pacing, and deadline-safe trip behavior. The
  report includes cold/warm timings, native-library digest, and host binding;
  hard-real-time, HIL, and competitive claims remain false. See
  the separate circuit engine tests and
  `artifacts/spikes-qualification-report-0.3.0-alpha.3-2026-08-31.json`.
- Performance claims: none. Comparisons with QucsStudio, ngspice, PSIM,
  SIMPLIS, PSpice, and other engines require equal-model/equal-tolerance
  accuracy gates before timing results can be published.

The following Studio behavior belongs to the separate SPIKES application, whose
source is shared in this repository but whose interface is not included in the
SPIKE desktop package. SPIKES Studio's engineering-preview run profile selects the owned C++
backend or the process-isolated ngspice compatibility adapter explicitly.
Legacy profiles remain native. The ngspice Studio route is self-contained and
batch-only; it maps only complete real transient voltage vectors to plots, while
retaining raw vectors and solver-dependent status. It is not general vendor
model qualification, full dialect parity, or a release-ready desktop workflow.

### Parallel-diode electrothermal sharing reference

- State: implemented as `reference_qualification_only`; it is not general MNA
  integration or a production device model
- Behavior: common-voltage parallel Shockley-plus-series-resistance diodes,
  individual temperature-dependent parameters, backward-Euler compact thermal
  RCs, symmetric mutual thermal coupling, exact matching, explicit mismatch,
  and reproducible seeded log-normal sampling
- Results: per-device current share, loss, junction temperature, local runaway
  margin, and source-localized warning/trip events
- Purpose: permanent qualification fixtures for current hogging, matched
  sharing, thermal divergence, and later production DAE electrothermal models

### Native fixed-point field/circuit co-simulation

- State: implemented as an experimental reviewed-package workflow through the
  service and `field-circuit-validate` / `field-circuit-run` CLI commands
- Coupling: deterministic fixed-point updates between a native PEEC reduction
  provider and either the compiled linear-reference MNA workspace or the
  SPIKES C++ circuit backend. The selected circuit engine is
  explicit in the request and result provenance.
- Owned-kernel boundary: `spike/owned-spice-workspace-request/v1` accepts only a
  reviewed structured workspace and bounded probes, composes the netlist
  internally, binds the engine result to its SHA-256, hashes the adjacent owned
  DLL, and strips host paths. Raw netlist text and caller-selected libraries are
  rejected.
- Dedicated process: `python -m python.spike_core.owned_spice_process` exposes
  only capabilities and the fixed `--request <job>/request.json --result
  <job>/result.json` interface. Controls are strict UTF-8 JSON capped at 8 MiB;
  request/result paths share one non-reparse job directory and publication is
  atomic. The hash-locked Windows x64 circuit-only recipe now produces and
  smoke-tests `spike-circuit-worker.exe` without importing the unrelated
  PyArrow/scientific desktop runtime. The trusted host supervisor admits the
  exact worker and owned-DLL SHA-256 identities before launch, creates the
  process suspended, assigns a memory-bounded kill-on-close Windows Job Object,
  then resumes it. Timeout, cancellation, memory denial, tamper rejection, and
  a packaged structured solve pass locally. The POSIX implementation uses a
  new process group plus address-space/core limits and complete-group
  termination, but still requires Linux execution evidence. Both routes remain
  `experimental`; clean-machine installation and private-CI evidence remain
  release gates.
- Validation: focused resistive fixed-point and provider-mapping fixtures pass
  in the current qualification evidence; the workflow is still blocked from
  release promotion because its validation state is `experimental`
- Limits: no automatic arbitrary-geometry PEEC network compiler, iterative
  electrothermal feedback, production-scale circuit qualification, or
  independent/measured-board correlation. The owned kernel has bounded
  nonlinear devices, but not every parser vocabulary element has a typed native
  runner binding and its C++ kernel has no native AC/phasor solve. Those gaps
  must fail closed rather
  than be represented as a validated PI/FEA co-simulation.

### PEEC plus ngspice staged hybrid

- State: operational for explicitly reviewed PEEC-network-to-circuit-node
  mappings and explicit component/subcircuit models
- Execution: deterministic R/L/C/G netlist composition followed by the
  process-isolated ngspice 46 adapter
- Security: unsafe include, library, control, shell, and source directives are
  rejected; runtime and raw-result size are bounded
- Coupling: one-way staged extraction/circuit execution; it is not iterative
  field/circuit feedback and does not silently fit PEEC Z(f)
- Validity: the combined result inherits the weakest PEEC/device-model status
  and remains approximate when the source RLCG network is approximate
- Detail: see `docs/PEEC_NGSPICE_HYBRID.md`

### PWM converter staged study (`spike/converter-study/v1`)

- State: operational orchestration for reviewed explicit device models and
  waveform bindings; physical validity remains solver/model dependent
- Inputs: structured PWM source timing and levels, a transient SPICE workspace,
  explicit input/output vectors, a measurement window, optional reviewed PEEC
  mappings, explicit device-loss bindings, and an optional compact thermal case
- Results: input/output power, efficiency, loss, ripple, inrush, component loss
  and stress records, waveforms, and optional compact thermal temperatures
- Execution: structured controls are compiled into SPICE `PULSE` sources before
  process-isolated ngspice execution; missing vectors fail instead of being
  inferred
- Coupling: one-way PEEC to ngspice to compact thermal. No iterative
  electrothermal feedback, CFD, controller-code co-simulation, or validated
  Bode extraction is claimed
- Detail: see `docs/CONVERTER_STUDY.md`

### AC PDN multiport candidate review (`spike/pdn-multiport/v1`)

- State: operational interface and placement-review workflow; numerical status
  remains approximate
- Inputs: explicitly placed user probes on the analysed net. SPIKE forwards
  their reviewed coordinates, layers, and anchor identity as candidate ports;
  it does not infer physical capacitor locations from nearby geometry.
- Results: candidate-port local, transfer, and reverse-transfer impedance data
  when returned by the selected solver, plus a placement review in the desktop
  UI.
- Physics limit: the current PEEC path retains a shared-reference capacitance
  approximation. It does not yet provide a validated arbitrary-geometry,
  multiconductor return-path extraction or signoff-qualified physical capacitor
  placement recommendation.
- Validity: `spike/pdn-multiport/v1` is a stable result contract, not evidence
  that the underlying PEEC result is validated. Reports and UI must preserve
  the solver's approximate status.

### PDN target and candidate review (`spike/pdn-review/v1`)

- State: operational screening contract
- Inputs: a solver-produced driving-point impedance sweep, target impedance,
  and explicit capacitor-bank candidates
- Placement models: direct-port shunt, supplied lumped mounting/spreading
  path, or reviewed two-port local/transfer-impedance loading
- Numerics: deterministic complex impedance reduction on the source frequency
  grid; no hidden spatial inference or interpolation
- Validity: direct-port and series-path screens remain approximate. A two-port
  candidate can only inherit validation already present in its source network.
- Remaining gate: independently correlated multiport extraction and measured
  board confirmation are required before claiming optimal physical placement.

### Reviewed multi-net PI path composition (`spike/pi-path-circuit-compile/v1`)

The Power Tree also supports an explicit **screening budget** for a series LDO
or buck stage. A selected LDO uses the user-specified input/output voltages
and downstream output current for `(Vin - Vout) * Iout` loss, neglecting
quiescent current. A buck uses a user-supplied efficiency for
`Pout * (1/efficiency - 1)` loss and input-current estimate. The optional
output/input voltage ratio propagates an output voltage when none is assigned;
an inconsistent ratio or physically impossible LDO step-up is flagged. These
algebraic budgets do not constitute a PCB circuit or switching solve. A
physical inductor/MOSFET/IC model still needs the reviewed SPICE path below.

- State: operational experimental composition for ordered, reviewed linear
  paths; not release-qualified
- Geometry stage: each conductor segment is preflighted and extracted
  independently at its exact reviewed input/output pad anchors. One matching
  `spike/rlgc-network/v1` network is required for every segment.
- Component stage: intervening reviewed linear resistor, inductor, and capacitor
  models are stamped between their explicit component pads. Missing, duplicate,
  mismatched, unreviewed, ideal-zero, and nonlinear transitions fail closed.
- Solve stage: the combined network executes in native MNA for AC or fixed-step
  transient analysis. Constant, step, pulse, and PWL source/load profiles use
  the same bounded native source contracts.
- Result truth: all extracted segment networks and endpoint bindings remain in
  provenance. SPIKE does not fabricate a circuit-wide spatial field from the
  lumped solve; spatial fields remain the responsibility of the segment
  extraction results.
- Remaining gate: package/contact-volume geometry, nonlinear semiconductor and
  behavioral model composition through reviewed ngspice, whole-path convergence,
  independent cross-solver agreement, and measured-board correlation.

## Optional Acceleration

Acceleration changes execution only. It does not add geometry, physics,
accuracy, or validation status.

| Backend | State | Implemented scope | Important limit |
|---|---|---|---|
| NumPy assembly | Available | Hybrid DC graph-Laplacian triplets | Baseline path |
| Numba assembly | Optional | JIT acceleration of the same assembly kernel | Does not mesh or solve matrices |
| SciPy SuperLU | Available | Tested real/complex hybrid DC reduced sparse system | Single-process baseline |
| PETSc/MUMPS | Optional, Linux-first | Hybrid DC reduced sparse direct solve through `COMM_SELF` | No distributed or out-of-core orchestration |

Automatic policy selects Numba at 50,000 branches and PETSc/MUMPS at 100,000
unknowns when those backends are available. The thresholds are configurable and
the actual requested/selected backend, fallback, matrix size, residual, and
timings are recorded in result provenance. Explicitly requested unavailable
backends fail rather than silently changing policy.

Numba accelerates assembly kernels only. PETSc/MUMPS is optional and
Linux-first. Neither backend accelerates dense PEEC partial-inductance or
transient factorizations. See `docs/ACCELERATION_ARCHITECTURE.md`.

The SuperLU regression path includes a complex matrix with a real right-hand
side and verifies that the complex solution is preserved. PETSc/MUMPS catalog
capabilities are limited to the implemented single-process `COMM_SELF` adapter
and the scalar type of the local PETSc build. Use `spike accelerators` to inspect
the effective backend catalog and policy.

## Pre-Solve Workflow

The desktop worker and CLI expose:

- `preflight_analysis`: validates nets, solver capabilities, frequency setup,
  dielectric availability, source/load presence, and mesh generation.
- `preview_mesh`: creates a bounded renderer-neutral mesh before matrix assembly.
- `run_analysis`: selects a compatible solver only after the request is valid.

Mesh previews use the same hybrid topology as the PEEC adapter and include
selected-net track surfaces, zone cells, pad cells, and layer-by-layer
via barrel surfaces. A preview is not a solved field and never contains
inferred voltage, electric-field, or magnetic-field data.

Preview size is admitted against a memory budget, not a fixed global cell cap.
The desktop derives the budget from detected RAM and the user's solver-memory
policy; the worker independently reports the requested cells, admitted cells,
estimated resident bytes per cell, and effective budget. This only scales mesh
inspection. Dense PEEC, full-wave, CFD, and other engines retain their own
solver-specific limits and must not infer readiness from preview admission.

## Network Data Workbench

[Supplied conductivity-temperature feedback](PDN_DIELECTRIC_FEEDBACK.md)
iterates the dielectric/thermal workflow with per-cell conductivity updates,
bounded material ranges and raw temperature/power residuals. It remains
experimental; convergence does not establish transient stability, general
material behavior or measured-board validity.

[One-way dielectric-to-thermal execution](PDN_DIELECTRIC_THERMAL.md) combines
actual complex AC fields into per-cell heat, checks terminal/volume power and
executes the retained steady thermal solver on an identical mesh. This shared
PI/multiphysics foundation remains experimental; it has no temperature feedback
into electrical materials, general mesh transfer or measured-board qualification.

[Explicit passive sampled admittance reduction](PDN_ADMITTANCE_REDUCTION.md)
retains selected ports with floating or passive auxiliary loads and independent
power accounting. It preserves approximate/experimental status; sample
passivity does not qualify a causal broadband or transient model.

The separate [finite-dielectric AC path](PDN_DIELECTRIC_AC.md) solves supplied
conductivity/loss-tangent and permittivity fields at positive frequencies. It
retains complex electrode currents and independent field-power evidence with
experimental status. Finite plate references do not qualify general board
extraction, open boundaries or causal transient coupling.

The explicit passive PDN engine also admits [simultaneous supplied PWL
loads](PDN_SIMULTANEOUS_LOADS.md), with exact event union, ordered per-load
currents and shared-return voltage/energy accounting. This does not establish
nonlinear regulator or general board-extraction validity.

The [explicit mixed-mode API](PI_SI_PARITY_EXECUTION.md)
additionally supports arbitrary ordered pairs, different real references between
pairs and retained unpaired ports, with independent impedance/power checks.
Unequal within-pair references and causality qualification remain unsupported.

Touchstone network ingestion and post-processing are operational and independent
of the field-solver catalog. Available functions include S/Z/Y ingestion,
S/Z/Y conversion, real-reference renormalization, adjacent-pair mixed-mode
conversion, passivity and reciprocity checks, group delay, matched-port input
impedance, trace plotting, and Touchstone export.

This does not mean SPIKE can generate validated S-parameters from general PCB
geometry. The PEEC adapter emits an RLCG driving-point model. R and partial L
come from the hybrid conductor PEEC mesh. C and dielectric G remain explicitly
`approximate`: they use a single-reference Hammerstad/Jensen stackup estimate
for supported planar branches.

A separate bounded `geometry_uniform_channel` analysis accepts either one
straight constant-width SpiDeR v2 path, two straight parallel coextensive
paths, or the explicit `piecewise_planar` connected same-layer constant-width
approximation over one simple fully covering reference zone and homogeneous
dielectric. The single path produces experimental scalar RLGC and reciprocal
two-port S. The pair uses a sparse finite-difference cross-section Maxwell
capacitance matrix, its vacuum-matrix-derived quasi-TEM L, and multiconductor
propagation to produce matrix RLGC, four-port S, and bounded geometry-derived
NEXT/FEXT. The piecewise pair requires matched parallel segments and explicit
skew/separation tolerances and uses the minimum separation conservatively. P/N
selection adds an orthonormal mixed-mode transform, differential two-port,
TDR/TDT, and normalized deterministic NRZ eye. Bends are recorded but their
discontinuity physics is omitted. Their shared request/result contracts are
`spike/si-uniform-channel-request/v1` and `spike/si-channel-result/v1`.
Field-sensitive return-path proof, accepted cross-section/frequency convergence,
frequency-dependent conductor physics, general coplanar/multiconductor
electrostatics, vias/antipads, bends, launches, connectors, arbitrary coupled
lines, IBIS/source/receiver models, statistical eyes, rare-event BER, isolated
packaged-SPIKES parity, independent correlation, and measured two/four-port
VNA/TDR evidence remain required. See `GEOMETRY_DERIVED_SI_CHANNEL.md`.

Causality checking for arbitrary imported networks remains unavailable until
DC extrapolation, resampling, window, and delay-removal policies are explicit.
The bounded channel's required DC-starting uniform grid and recorded no-window,
no-padding policy make its transform reproducible but do not establish general
causality or production validity.

## Executable Benchmarks

Run `spike benchmark` to execute the permanent analytical corpus. It currently
checks straight-trace resistance, annular via-barrel resistance, square-sheet
mesh convergence, hybrid trace/zone/pad/via connectivity, native rectangular
conductor self-inductance, the hybrid PEEC MNA path, AC-loss monotonicity, and
the wide-microstrip parallel-plate capacitance limit. It also verifies a
closed-form shared-reference two-port resistor matrix and the PDN two-port
capacitor-loading identity against an independent nodal re-solve.

The latest machine-readable run is committed at
`docs/validation/solver-benchmarks.json`.

These fixtures validate bounded units, extraction, topology, matrix assembly,
network reduction, and numerical convergence properties. The matrix/network
cases do not validate PCB multiport field extraction. None of the fixtures
replace correlation against measured boards or a trusted commercial/full-wave
solver.

## Packaged Windows Worker

The Windows desktop package is built offline-first with PyInstaller 6.21.0.
The worker bundle includes the native PEEC extension for the packaged Python
ABI and is accompanied by a SHA-256 manifest covering every bundled file.
Tauri tries this packaged worker before the repository Python development
fallback.

The worker build is rejected unless all three smoke gates pass:

1. worker health response;
2. capability-catalog response confirming the required native PEEC extension;
3. the permanent 15-case analytical benchmark corpus with zero failures and
   zero skipped cases.

These are packaging-integrity and bounded-regression gates. They do not make
the PEEC solver signoff validated, change the approximate multiport physics
boundary, or replace independent measured-board correlation.

## External Engine Adapters

The solver manager exposes workload-based recommendations, local registrations,
and allowlisted tuning through `spike solver-manager`, `solver-recommend`,
`solver-register`, `solver-unregister`, and `solver-tune`. Registration never
installs or executes software; unregistering never deletes third-party files.
Managed downloads remain disabled. See `docs/SOLVER_MANAGER.md`.

| Integration | Current executable state | Validation boundary |
|---|---|---|
| SPIKE object thermal network | Built-in local worker solves steady and transient object temperatures from explicit power, heat capacity, top/bottom paths, and per-object or named-face conduction, convection, and radiation boundaries; BOM CSV/TSV and ODB++ named property mapping are available in the GUI. The transient UI overlays solved part-node samples on board locations and reports per-part peak, peak time, time to 90% of steady rise, and final gap. A [board-linked eBrake1 example](validation/EBRAKE1_OBJECT_THERMAL_20260928.md) retains assumptions, result JSON, and object-temperature plots. | Approximate lumped nodes, including explicit interobject conduction; face labels do not resolve spatial gradients. The marker overlay is not a board temperature field. No geometry-derived path, board spreading, airflow, radiation view factors, CFD, or spatial temperature field; the eBrake1 assumptions and analytical checks do not establish measured-board correlation. |
| SPIKE board thermal grids | Local worker supports the prior uniform 2D plate and an optional structured layered board volume. Imported pad lands locate heat injection; the layered mode samples track/pad/filled-zone/via-land copper coverage per physical copper stackup row, couples dielectric rows and plated barrels, and can blur each layer's copper occupancy. It solves lateral and vertical conduction across the physical stackup. Optional transient steps add per-cell copper/dielectric heat capacity, saved temperature frames, stored-energy and balance diagnostics, a peak history, and fixed-scale layer playback. Optional virtual board heatsinks add a shared isothermal top/bottom contact node with explicit interface and sink-to-ambient K/W; result heat flow is included in conservation. Layer temperature and coverage maps, pad heat paths, case/junction and sink temperatures, and toggles are available in Thermal setup. The [plate](validation/EBRAKE1_BOARD_THERMAL_20260928.md), [layered](validation/EBRAKE1_LAYERED_THERMAL_20260928.md), [transient](validation/EBRAKE1_LAYERED_TRANSIENT_20260928.md), and [virtual-sink](validation/EBRAKE1_VIRTUAL_HEATSINK_20260928.md) records retain results and assumptions. | Experimental bounding-rectangle model with sampled effective copper and one depth cell per stackup row; no conforming outline/cutouts, tetrahedra, 3D package/heatsink blocks, solder/lead/die field, airflow, measured calibration, or production qualification. Board-field transient assumes ambient initial state and constant losses; reported case/junction resistance-chain temperatures are steady. Virtual sink resistances are prescribed rather than derived from fin geometry and are not coupled to separate assembly/CFD heatsink shapes. Fuzzy copper changes connectivity, and mesh refinement remains incomplete. Results remain `approximate`. |
| openEMS | Runnable through the isolated desktop adapter when discovery, preflight, and final-grid/time-window admission pass | Local three-level simple-patch rerun passed for current adapter 1.3.4, but packaged evidence still binds 1.1.0. The installed pair remains experimental pending evidence promotion; arbitrary PCB and compliance remain unvalidated. |
| OpenFOAM | v2606 is installed in Ubuntu 24.04 WSL; original single-region and separate multiregion solid/fluid cases execute through bounded processes and import fields; synthetic one/two-board fan CHT and solid-only radiation records exist | Experimental; general imported assembly CHT, paired CFD interface-flow histories, independent CFD comparison and measured correlation remain open. See [fan evidence](FAN_CHT_QUALIFICATION.md) and [fresh cooling checks](validation/THERMAL_COOLING_ENVIRONMENTS_20261009.md) for exact scopes |
| Siemens FloTHERM | No adapter is present | Future connector only; SPIKE cannot bundle or activate the customer-provided runtime without permitted automation rights |
| FreeCAD | ECAD/MCAD workbench and inert exchange contracts are implemented; local FreeCAD kernel smoke passes | Geometry exchange is not solver or product validation |
| sparseLizard | Native Windows self-test runtime compiled without WSL; SpiDeR translation for DC, AC/RLCG, thermal, and field case contracts, process isolation/cancellation, strict result conversion, and qualification reporting are implemented | The installed executable is not the production PCB adapter. Its legacy manifest is unsigned, PETSc does not expose MUMPS, and no PCB fixture evidence is installed, so arbitrary PCB execution remains disabled |
| PETSc/MUMPS | Native Windows PETSc/SLEPc and standalone MUMPS libraries are packaged for the sparseLizard development runtime, but that PETSc build does not register MUMPS as a factorization backend | PETSc LU runs the bounded DC fixture; a PETSc build configured with MUMPS plus equivalence/performance qualification is still required |

### openEMS (`external.openems`)

The adapter implementation and reference evidence are owned by the bundled
`extensions/openems_suite` package. Its extension menu exposes explicit
high-frequency PI and SI port-sweep workflows. The existing worker and CLI
methods remain compatibility entry points into that package. OpenEMS is an
electromagnetic solver and the extension does not advertise thermal analysis.

- State: `reference_validated` only when the isolated native-object probe passes
  and the openEMS/adapter versions match the packaged three-level patch-antenna
  convergence record; otherwise experimental, unavailable, or interface-missing
- Preparation: operational for selected rigid-board nets after preflight checks
  finite increasing frequencies, bounded frequency points, selected conductor
  geometry, copper/layer mapping, physical stackup, dielectric permittivity, and
  bounded mesh/runtime/thread options
- Final-grid admission: the isolated worker reads actual CSXCAD axis lines,
  checks cell/memory budgets and an explicit conservative one-cycle screening
  policy using a vacuum CFL reference timestep before FDTD execution. That
  reference is not openEMS's actual nonuniform-grid timestep. Curved-pad facet lines
  are no longer automatically pinned; this changes rasterized copper and must
  be rechecked by mesh convergence. See [the executed grid record](validation/OPENEMS_ACTUAL_GRID_20260928.md).
- Execution: requires explicit 3D lumped ports and exactly one excited port;
  coordinates and impedance must be finite, and ports are never inferred from
  pads, probes, or source/load terminals; both endpoints must intersect distinct
  exported selected-net conductors
- Desktop workflow: the EMI workbench has an explicit port editor, preflight,
  case preparation, run controls, and structured result import. A full run is
  enabled only when the runtime is runnable and geometry, stackup, NF2FF request,
  resource limits, and ports pass preflight
- RE reference metadata: the EMI setup can retain CISPR 32 A/B, CISPR 25
  classes 1–5, and MIL-STD-461H/G RE102 platform selections with exact edition
  and source; unknown/mismatched selections fail preflight. Numeric limits,
  qualified receiver/fixture evidence, and pass/fail comparison are absent.
  Selecting a profile does not promote solver readiness or compliance status;
  see [EMI workflow](EMI_WORKFLOW.md#radiated-emissions-reference-profiles)
- Geometry: straight tracks, filled zone outer polygons without cutouts,
  rotated undrilled rectangular pads, and faceted circle/oval/roundrect surface
  pads, conducting sheets, and dielectric boxes. The worker contains a plated
  via shell primitive, but geometry admission blocks via and drilled-pad
  solves until bore, lands, antipads, and layer connectivity are qualified.
- Results: setup XML, normalized S-parameter columns, shape-checked NF2FF
  electric-field components, directivity, radiated power, and raw artifacts.
  The desktop far-field view shows frequency-selectable polar cuts, metrics,
  angular sampling, observation radius, and the result validity boundary; the
  engineering report can retain the same structured NF2FF evidence
- Model status: the current 1.3.4 adapter remains `experimental` because
  packaged simple-patch evidence is version-bound to 1.1.0. A local 1.3.4
  three-mesh rerun passed that fixture's gate but is not packaged release
  evidence; arbitrary-board results remain unvalidated and never imply
  regulatory compliance
- Limits: no rigid-flex translation, production multiport calibration,
  measured-board/chamber correlation, immunity workflow, or compliance signoff
- Installation: optional local/signed-offline engine only; no implicit downloads
- Process boundary: authenticated job and geometry snapshots plus trusted
  adapter source are sent to `python -I -` over stdin; the child never reopens
  mutable case inputs and the exported driver is never executed
- Result binding: imported data must match the exact random run ID, job/input
  digest, frequency grid, and mesh declaration; contained artifacts must exist
- Integrity storage: case signing keys live only in SPIKE's private application
  state, while bounded reads reject oversized job, geometry, and result JSON
- Resource bounds: 8 MiB log cap, 16 GiB engine-output quota, bounded timeout,
  and process-tree termination on timeout/quota; explicit user cancellation and
  Windows Job Object hard memory controls remain pending
- CLI: `spike external-engines`, `spike openems-prepare`, and
  `spike openems-run` expose the implemented catalog/prepare/run workflow

The validation record and numerical results are documented in
`docs/validation/OPENEMS_REFERENCE_VALIDATION.md`. This is not product-class or
compliance validation for arbitrary boards.
The separate board admission and provisional HForsten slice runs are recorded
in `docs/validation/OPENEMS_BOARD_COMPARISON_20260927.md`; that completed
board-derived FDTD run uses assumed materials, ground plane, and port, so its
S11 is integration evidence only.
The two-excitation HForsten provisional S matrix, native DC mesh
sweeps, PEEC nonpassivity diagnosis, and Marble openEMS timeout are recorded in
`docs/validation/PROVISIONAL_PI_SI_OPENEMS_INTERNAL_20260928.md`. No matched
cross-solver S-parameter accuracy benchmark or full-board PI/SI solve has
been established.

The implemented NF2FF path is: define selected/return nets and explicit ports in
the EMI workbench; request bounded frequencies, theta/phi sampling, radius, and
phase center; preflight and prepare the authenticated case; create the openEMS
NF2FF box after final mesh construction; execute FDTD and `CalcNF2FF`; then
validate result shape, finite values, run binding, frequency grid, mesh
declaration, and contained artifacts before display. Successful execution is a
computed solver result, not automatic validation of that PCB.

External-engine catalog capabilities are adapter-level claims and list only the
surface SPIKE implements, not every feature present in the external engine.
Contract tests cover catalog gating, preflight, private UUID jobs, path
containment, isolated trusted-source execution, and unavailable-engine recovery;
this description intentionally does not depend on an exact test count.

FastHenry and FastCap are catalog/discovery entries with exporters and result
importers still pending. OpenFOAM discovery exists, but the validated
multi-region case generator remains gated. ngspice retains its separate
explicit-netlist circuit adapter.

### Elmer FEM (`external.elmer`)

- State: discovery and explicit local registration only; no runnable SPIKE
  adapter exists
- Discovery: registered `external.elmer` path, `SPIKE_ELMER_HOME`, `PATH`, or
  SPIKE's optional local runtime directory may provide `ElmerSolver`; discovery
  never installs, probes, or executes it
- Implemented capabilities: none
- Candidate upstream scope: DC conduction, electrostatic capacitance,
  magnetostatic and harmonic electromagnetic fields, solid thermal,
  electrothermal, and lumped-circuit coupling
- Required gate: a bounded case translator, fixed process adapter, normalized
  result contract, resource limits, validation fixtures, and independent
  correlation before any PI, SI, thermal, or EMI workload can become runnable
- Overclaim guard: a detected `ElmerSolver` remains
  `installed_adapter_pending`, `model_status=unsupported`, and exposes no
  `run` action or validated claim

### sparseLizard (`external.sparselizard`)

- State: deterministic SpiDeR translation, bounded exact-name process launch,
  cancellation, Windows Job Object memory enforcement, strict result import,
  and a five-class qualification report are implemented; no production
  `spike-sparselizard-adapter` executable is installed on the current machine
- Interface: process-isolated `spike-sparselizard-adapter`, never a
  project-supplied executable or in-process linked library
- Implemented adapter surface: `spike/sparselizard-case/v1` exports hybrid PCB
  mesh cells, copper/dielectric materials, selected conductors, explicit
  terminals, resource limits, and workload-specific DC, AC/RLCG, thermal, or
  field requests. `spike/sparselizard-result/v1` imports digest-bound mesh,
  scalar, vector, matrix, and convergence data only after strict validation
- CLI: `spike sparselizard-prepare REQUEST --case-dir DIR` is operational;
  `spike sparselizard-run CASE_DIR` remains unavailable until an exact adapter
  executable is installed or explicitly registered
- Downstream use: accepted results normalize to `AnalysisResult`, including
  scalar and vector field samples, mesh metadata, impedance matrices, RLCG,
  warnings, and provenance without promoting the source model status
- Candidate upstream scope: DC conduction, solid electrothermal coupling,
  electrostatic capacitance, harmonic magnetodynamics/Maxwell fields, and
  lumped-circuit coupling
- Current trust: exact executable name, fixed invocation, case/result digest
  binding, bounded streams/files/time, POSIX quotas, Windows Job Object process
  and memory limits, cancellation, and strict result validation. Production
  activation additionally requires a CMS-signed manifest, pinned artifacts,
  signed PETSc/MUMPS readiness, staging, self-test, and rollback
- License: sparseLizard is GPL-2.0-or-later; any linked adapter must use
  GPL-compatible terms and satisfy redistribution obligations
- Validation: the permanent plan contains analytical PCB DC, AC/RLCG, thermal,
  electrostatic, and harmonic-field fixtures with explicit tolerances. The
  current report is `blocked`: zero fixture evidence files are installed, the
  runtime manifest is unsigned, and PETSc has not registered MUMPS. The catalog
  therefore advertises no executable PCB physics capability and no validated
  sparseLizard result
- Overclaim guard: source/library detection and case preparation do not enable
  S-parameters, closed-loop SPICE, PCB far field, airflow, or EMI compliance

### Parallel SPIKES generic FEM runtime handoff

`D:\PROJECTS-DEV\SPIKES` is the separately developed native generic solver
suite. Its current Milestone 0 process boundary now declares deterministic 1D
diffusion and 2D triangular stationary/transient FEM verification workloads in
addition to capability probing and self-tests. It also declares two explicitly
prepared verification routes: compact frequency-domain Maxwell solves with
reused immutable system storage, and bounded rational-network conditioning.
Neither prepared route accepts general PCB geometry or advertises product
physics. The 2D core includes mixed
Dirichlet/Neumann/Robin boundaries, pure-Neumann gauge handling, adaptive
red-green refinement, backward Euler and BDF2 reference paths, and bounded
process/C-ABI execution. These are manufactured-solution verification
capabilities, not executable PCB PI, AC/RLCG, thermal, or coupled-field
backends. SPIKE therefore keeps `spike.spikes-native-process/v0.1` fail-closed
for product physics.

SPIKE can discover an installed runtime from an explicit path, the
`SPIKES_NATIVE_SOLVER` environment variable, or `PATH`, then invoke only
`--capabilities` through a bounded no-shell probe. A source checkout path is
never embedded. The probe accepts ABI v1 and records the runtime as
`discovery_only`; even a successful `verification_only` handshake cannot make
PCB product physics eligible.

A local integration check built and probed
`spike-native-solver.exe` with MSVC. The private runtime capability document
validated against `spike/native-capability/v1`, the runtime DLL retained its
four-function C ABI, and the refreshed private Release corpus passed 308/308
tests. Seven focused AddressSanitizer tests passed for the rectangular-TE modal
scattering path, strict prepared modal-DtN process route, and conforming via
volume lineage compiler. The earlier affine-P2 H(curl), de-embedding, and
conditioned-network verification slices remain part of the passing corpus.
The prepared modal route accepts only canonical, hash-bound complex-symmetric
CSR operators and modal traces; it does not reconstruct or prove a PML model.
This is local verification evidence only: PETSc, hypre and MPI remain false in
the probed manifest, all prepared routes remain `verification_only`, and no
portable package or private CI evidence exists. The public adapter continues
to advertise only probe and self-test as runnable capabilities while listing
the prepared routes as verification capabilities.

The audit also detected an external change to the protected private artifact
`quasi_result.egres`: it is now 11,878 bytes with SHA-256
`D5734DD5BFDB12FD50F425CF4C257B5A33AAB97DE6EF906DC19613078DDAE155`, rather
than the recorded 11,877-byte `34A1F67D...` baseline. The solver tranches did
not modify or rebaseline it. Artifact-integrity acceptance therefore remains
failed until the owner confirms the new file or restores an authoritative
copy.

The next PCB-capable handoff must add a versioned model/mesh contract that
preserves canonical source object IDs, net IDs, copper layer IDs and spans,
materials, boundary classes, terminal selections, and result provenance. The
SPIKE-side reference contract now supplies exact capsule pad/slot boundaries,
explicit routed-via and plated through-pad barrel conductor volumes, and annular
ownership checks. The native suite must consume those shapes without converting
them back to ellipses or collapsing barrel spans. It must also represent zone
holes and antipads, castellations, blind/buried/microvias, and conformal
stitched-layer interfaces. Scalar/vector results must retain source ownership and layer
identity so an invalid or out-of-owner field cannot be rendered as a valid PCB
result.

The current geometry-handoff evidence is 593 passing canonical backend tests
with one opt-in external KiCad fixture skipped, plus 32 passing root integration
contract tests. Those tests establish deterministic transport and rejection
behavior only; they are not measured validation of current density, via stress,
impedance, or thermal fields.

SPIKES must remain unavailable for arbitrary PCB execution until its
capability manifest names the supported formulation and geometry, process
cancellation/resource bounds pass, result conversion is qualified, and the
relevant analytical, independent, and measured validation evidence passes.
This requirement is feedback to the parallel solver program; it does not
promote the current adapter or replace SPIKE's existing PI solvers.

## Unavailable

### Surface MoM (`spike.mom_surface`)

No executable or validated MoM implementation is packaged.
An internal oriented-RWG basis, singular triangular-source Green-moment kernel,
and supplied-current free-space far-field/RCS postprocessor have bounded
analytic/invariance tests. They do not assemble or solve the EFIE, compute a
PCB/antenna current distribution, or qualify scattering accuracy. Unresolved
quadrature withholds RCS; the public solver capability remains unavailable.

### Full-Wave 3D (`spike.fullwave_3d`)

No executable or validated native FEM/FDTD solver is packaged, so this solver
ID remains unavailable. The optional openEMS process adapter is a separate,
executable path and does not enable `spike.fullwave_3d`. A matching openEMS
runtime may be `reference_validated` and runnable for the simple-patch fixture,
while an arbitrary-PCB NF2FF result remains `not_validated`. Gmsh, Elmer,
openEMS, and GetDP are not downloaded implicitly. Native full-wave status and
product-class PCB validation cannot advance until deterministic bundles,
additional fixtures, explicit applicability limits, material and boundary
validation, and external/measurement correlation are complete.

## Environment Profiles

`spike/environment-profile/v1` profiles cover standard lab air, sealed/potted,
automotive, marine, aerospace altitude, vacuum/space, and user-defined inputs.
Domain readiness checks only whether required PI, SI, thermal, or EMI metadata
is present and internally consistent. A ready profile does not validate a
solver, represent a complete enclosure or flow domain, qualify hardware for an
environment, or assess compliance. Certification remains explicitly
`not_assessed`.

## Required Next Gates

1. Add a convergent panel/BEM capacitance matrix with via/antipad geometry and
   independent FastCap/FEM/measurement correlation.
2. Add proximity-effect current redistribution and validated Huray/gradient
   roughness models.
3. Add automatic production-run mesh-convergence execution and error thresholds.
4. Validate PDN impedance against RLC/SPICE fixtures and measured boards.
5. Correlate the implemented target/candidate review against measured PDN
   fixtures, add bias/temperature/tolerance-aware component models, and feed it
   validated location-specific multiport extraction before calling it physical
   capacitor optimization.
6. Replace dense partial-inductance assembly for motherboard-scale execution;
   current Numba and PETSc/MUMPS support does not address this matrix.
7. Qualify Numba and Linux PETSc/MUMPS bundles against baseline numerical and
   memory/performance fixtures.
8. Extend the existing simple-patch openEMS reference gate with representative
   PCB, enclosure, cable/connector, and measured chamber fixtures; require board-
   specific mesh convergence and correlation before promoting a PCB result.
9. Promote SI beyond the bounded experimental single/pair extractors only after
   analytical modal, four-port S/NEXT/FEXT, independent-field, and measured
   coupled-line fixtures pass with accepted convergence and uncertainty.

## Optional CalculiX and Gmsh extensions

`spike.calculix-suite` executes separately installed CalculiX for experimental
steady tetrahedral conduction, volumetric heating, prescribed temperature/flux,
ambient convection/radiation and congruent matched thermal contacts. Actual
CCX 2.23 analytical checks cover slab conduction, convection, radiation,
volume-source refinement and separately indexed contact bodies. This is not
production qualification. The dedicated `spike/calculix-thermal-result/v1`
records external execution evidence; internal CG/Newton diagnostics and global
heat balance are not fabricated. See [scope and checks](CALCULIX_THERMAL.md).

`spike.gmsh-suite` generates complete bounded OCC tetrahedral geometry, including
explicit normalized copper, dielectric, plated vias/drills, or reviewed retained
assembly solids. It provides native mesher choices in all five analysis setup
docks. Geometry admission does not establish PI/SI/EM translation, physics
validation, or cross-engine reuse. Runtime prerequisites and source-geometry
limits are described in [the extension](../extensions/gmsh_suite/README.md).

## High-frequency loss update

Bounded single/coupled SI now includes isolated slab complex skin impedance
and optional empirical RMS roughness resistance. Explicit AC PI adds RMS
roughness and opt-in internal reactance with external-only L. EMerge PEC
board/Gerber generation rejects unsupported conductor loss requests.
See [High-frequency conductor loss](HIGH_FREQUENCY_LOSSES.md) for controls,
numerical evidence and limits; proximity redistribution, dispersive materials
and arbitrary full-wave finite-conductor losses remain unvalidated.

## Protocol eye-mask evaluation

Retained NRZ polylines support strict polygon PASS/FAIL with boundary and
segment-crossing checks, explicit units and source metadata. USB HS Template
1/2 inner-opening profiles are selectable; outer and fixture conditions remain
unassessed. PAM4 statistics and legacy records without phase coordinates are
blocked. See [Eye-mask testing](SI_EYE_MASK_TESTING.md). Overall protocol
compliance remains not_evaluated.

## Retained assembly EM execution and saved fields

Explicit copper/dielectric/connector tetrahedral volumes and conductor-face
ports execute through the experimental OpenEMS retained-volume route. Saved
studies bind geometry and results, persist in `.spike` and activate normalized
E/H samples through the assembly EM workbench. The independent finite-cavity
fixture reports 2.36% capacitance and 4.91% maximum gap-field discrepancy;
Arduino qualification and dissipative-loss validation remain separate gates.
See [retained assembly EM](RETAINED_ASSEMBLY_EM.md) and
[independent reference](RETAINED_EM_INDEPENDENT_REFERENCE.md).

## Supplied decap corner assessment

PI03-S01 adds experimental evaluation of explicitly supplied C/ESR/ESL values
at named bias/temperature corners. The existing full supplied PDN is solved
at every corner, preserving failed sampled targets and generated requests.
Independent scalar and multiport regression evidence is retained; see
[PDN decap corners](PDN_DECAP_CORNERS.md). Automatic constitutive models,
location extraction, BOM optimization and measured qualification remain open.
This development stage does not establish PI03 family parity or release readiness.

## Bounded decap BOM selection

PI03-S02 adds experimental exhaustive selection within explicit supplied sites,
parts, operating corners and sampled targets. Cost, quantity and population
limits preserve rejection evidence and deterministic ranking. The service
composes existing corner solves and introduces no new electrical formulation.
See [selection scope and evidence](PDN_DECAP_SELECTION.md). General physical
placement, automatic component data and measured qualification remain open;
this does not close PI03 or establish full PI/SI parity.

## Supplied two-port fixture removal

SI08-S02 adds experimental algebraic removal of explicit left/right two-port
fixtures with exact grids, common real references, oriented named ports and
conditioned wave-chain solves. Source snapshots and active/nonreciprocal DUT
data are retained. See [scope and evidence](TWO_PORT_DEEMBEDDING.md).
Automatic calibration, uncertainty, arbitrary multiport fixture removal and
causality qualification remain open; this does not close SI08 or SI/PI parity.

## Explicit network resampling and DC

SI08-S03 adds experimental Cartesian-linear interpolation onto an explicit
grid with source or supplied real DC. It preserves exact support samples,
source identity, named ports and target weights, and rejects extrapolation.
Independent affine and delayed-line refinement checks establish bounded
behavior; see [scope and evidence](SPARAMETER_RESAMPLING.md). Active data
remains active. Causality, arbitrary broadband accuracy, calibrated uncertainty
and passive causal fitting remain open; SI08 and full parity remain incomplete.

## Supplied stable-pole rational network fit

SI08-S04 adds experimental real proper rational model construction at supplied
negative real poles, with an enforced sample-error limit and conditioning/
optimality checks. The realization is stable and causal by construction;
this does not certify source causality or physical broadband accuracy.
See [scope and evidence](SPARAMETER_RATIONAL_FIT.md). Active/nonreciprocal
models remain permitted, with diagnostic sampled SVD and a conservative norm
bound. Automatic pole selection, general passive fitting and measured or
transient qualification remain open; SI08 and full parity remain incomplete.

## Rational network prescribed-wave transients

SI07-S01 adds experimental simultaneous incident-wave execution of the actual
supplied-pole fitted network. Analytic PWL integration retains all input
corners and returns outgoing waves, port V/I and final model memory.
See [scope and evidence](RATIONAL_NETWORK_TRANSIENT.md). This is model
execution under prescribed incident boundaries; general source/load feedback,
out-of-band accuracy, nonlinear devices and measured transient validation
remain open. SI07 and the full PI/SI parity program remain incomplete.

## Resistively terminated rational network transients

SI07-S02 adds experimental finite-resistance Thevenin source/load feedback
around the actual fitted network. Algebraic singularities and unresolved
unstable connections fail explicitly; returned wave/V/I histories retain
the boundary evidence. See [scope and verification](TERMINATED_NETWORK_TRANSIENT.md).
Open/reactive/nonlinear connections, physical out-of-band accuracy, measured
correlation and full SI07/PI-SI parity remain open.
