<!-- SPDX-License-Identifier: Apache-2.0 -->
# Coupled mechanics, magnetics and semiconductor devices

The user requested this scope **now on 18 October 2026**. PI/SI remains the
primary parity program; this explicitly authorized parallel track supersedes
the earlier blanket deferral for the families listed in the backlog's
`parallel_expansion` policy. The follow-up adds [vibration, solder reliability,
satellites/launch vehicles, complete drone studies and watch/geared mechanisms](VIBRATION_VEHICLES_AND_MECHANISMS_PLAN.md).
GP05 vehicle aerodynamics is now specifically authorized; unrelated general
CFD/acoustics, wave optics, system radio and utility HVDC expansion retain their
existing gate. Parity is not established.

## Present evidence and delivery sequence

| Stage | Scope and present state | Exit evidence before Done |
| --- | --- | --- |
| GP07-S01 — Done | Experimental static 3D isotropic P1 tetra stress, deformation and thermal expansion; actual steady thermal solve feeds an identical mechanical mesh. | 16 executed numerical/worker/schema tests, zero skips; [source-bound receipt](validation/parity/GP07-S01.json) and [validation record](validation/ASSEMBLY_THERMOELASTICITY.md). Broader mechanics remains open. |
| GP07-S02 | Planned mechanical load and result workflow: surface traction/body acceleration, tensor/principal stress, displacement scene, deformation scale and linked probes. | Integrated face/body force and moment balance, pressure orientation, deformed geometry explicitly display-only, raw tensor/unit/sample binding; browser workflow tests and exported original results. |
| GP07-S03 | Planned modes, harmonic/transient mechanics and assembly supports. | Consistent/lumped mass declared, rigid modes identified, analytical frequencies, time/mesh convergence, damping applicability and energy balance. Supports, bearings, joints and small actuator assemblies retain explicit frames and constraints. |
| GP07-S04 | Planned contact, geometric/material nonlinearity and thermal expansion feedback. | Gap/friction/contact work references, nonlinear tangent checks, converged increments, plastic constitutive references and independently checked instability cases. No convergence means no successful result. |
| GP07-S05 | Planned beam/shell, layered/orthotropic and prestressed/buckling mechanics for PCBs and lightweight structures. | Patch/locking, laminate stiffness/thermal, mass/mode and independently refined buckling references; nonlinear post-buckling remains separate. See [vehicle and mechanism requirements](VIBRATION_VEHICLES_AND_MECHANISMS_PLAN.md). |
| GP03-S01 | Planned general 3D static coil/core/magnet solver. Existing planar magnetic FEM is a reusable foundation. | Flux/energy and analytical/independent mesh/exterior references, material law ranges, force/torque agreement between applicable virtual-work and stress methods; demagnetization and hysteresis require separate evidence. |
| GP04-S01 | Planned 3D stationary magnetic diffusion/eddy currents and circuit excitation. Existing experimental planar stationary eddy/thermal path is bounded. | Skin-depth/time refinement, complex or transient conventions, winding current/voltage and losses, positive dissipation and conservative thermal transfer. |
| GP04-S02 | Planned moving magnetodynamics and motor/actuator assemblies. Existing planar prescribed-current motion does not establish this stage. | Sliding/moving interfaces, applicable motional EMF and circuit back-EMF, moving-state transfer, force/torque and mechanical work, time convergence, stalls/end stops and rollback. Commutation, saturation, core losses and torque-speed maps need applicable references. |
| GP09-S01 | Planned electrical → magnetic → thermal → mechanical coupling and deformation feedback. First same-mesh thermal → mechanical link is GP07-S01. | Unit/frame and revision binding, conserved power/force/work, nonmatching-mesh transfer error, converged feedback and time-step synchronization with cancellation/rollback. Coil Joule/eddy/core losses, temperature laws and rotor/stator expansion remain separately traceable. |
| GP10-S01 | Planned compact Hall plate/sensor model and magnetic sampling. No Hall device capability is claimed yet. | Supplied signed sensitivity, bias, temperature, active area/orientation and saturation; offset/noise/bandwidth and electrical loading/Joule heat as declared model parameters. Uniform/nonuniform field averaging, polarity reversal, rotation and transfer tests. This is a compact model. |
| GP10-S02 | Planned classical Hall magnetotransport in admitted device geometry. | Electron/hole mobility and density, signed magnetic conductivity tensor, contacts and Hall voltage/current conservation; zero-field and polarity references, mesh refinement and parameter ranges. Actual field results must drive the device model. |
| GP10-S03 | Planned biased semiconductor transport beyond existing equilibrium TCAD. | Coupled Poisson and carrier continuity/drift-diffusion, contact/doping/interface admission, thermal laws and depletion/current references; nonlinear conservation/convergence checks. Traps, breakdown, quantum/process TCAD require independent scope and evidence. |
| GP11-S01 | Planned coupled failure-event screening. | Temperature-conditioned allowable stress/strain/field/current limits with source, range and uncertainty; threshold crossings and failed electrical/thermal/mechanical states propagate through the dependency graph. Screening margins are distinct from predicted lifetime. |
| GP11-S02 | Planned calibrated degradation, fatigue, fracture and fault transients. | Applicable material/device damage laws, load-cycle/mission history, irreversible state, calibrated failure references and uncertainty; electrical opens/shorts, thermal runaway, demagnetization, bearing/joint failure or insulation breakdown enabled only for implemented models. |

Integration cases progress from a heated constrained bar, to a supported coil
and magnetic actuator, then an actuator with a Hall feedback sensor and motor
assembly. Each case retains raw temperatures, currents, magnetic fields,
forces, displacement/stress, energy budgets and failure events on the same
revision. Semiconductor stress sensitivity requires a separately supplied and
validated law; importing a Hall sensor symbol does not supply that law.

## Current bounded mechanical interface

Worker methods `run_assembly_tetra_structural` and
`run_assembly_thermomechanical` accept exactly `{request: ...}`. Python callers
can use the same functions in `spike_core.assembly_tetra_structural` and
`spike_core.assembly_thermomechanical`. This stage provides solver APIs and worker
dispatch; a mechanical study editor and deformed result viewport are GP07-S02.

The structural request uses `spike/assembly-tetra-structural-request/v1`, the
existing `spike/solver-mesh/v1` conforming positive tetrahedra, isotropic
`young_modulus_pa`, `poisson_ratio`, `thermal_expansion_per_k` and
`reference_temperature_k` materials, exact per-node Kelvin temperatures or
null, prescribed component displacements, sparse nodal forces and a caller
context digest. Material IDs and source ownership must cover admitted cells.
Coordinates may be m or mm; displacement/force/stress results are m/N/Pa.
Null temperatures mean zero eigenstrain relative to each material's reference.

The thermo-mechanical request uses
`spike/assembly-thermomechanical-request/v1`, `thermal` and `structural` requests.
Both meshes must match exactly, including indexed connectivity and ownership.
Structural input temperatures must be null; the adapter executes the thermal
solver and transfers its actual nodal temperatures. Digests bind the original
coupled request, thermal request, generated structural request and mesh.
The caller's context digest is retained, not independently verified against CAD.

This is small-strain static linear isotropic elasticity; Poisson ratio is
restricted to (-1, 0.49]. Thermal eigenstrain uses mean nodal temperature in
each P1 cell. Stress order is xx, yy, zz, xy, yz, xz; reported strain shears are
engineering shear. Results contain nodal displacement, cell stress/von Mises,
elastic energy and fixed-DOF reactions. Elastic energy with thermal eigenstrain
is not generally half of external mechanical work. Shared nodes imply perfect
displacement continuity; omitted exterior tractions are zero.

Limits: 256 nodes, 1,024 tetrahedra, 192 free displacement DOFs, bounded work,
8 MiB request and 16 MiB result; constrained diagonal-equilibrated stiffness
condition at most 1e12, free equilibrium residual at most 1e-10 relative to the
declared algebraic scale. Rigid modes, unsupported materials and invalid meshes
fail explicitly. These small reference limits precede scalable sparse iterative
solvers/preconditioners and CPU/GPU qualification under AX01. Thermal validation
and linear algebra calls only poll cancellation around their bounded execution.

The current result does not establish mechanical contact, failure/lifetime,
modal/dynamic response, moving 3D motors, Hall transport or coupled deformation
feedback. All outputs remain experimental, `production_qualified: false`.

## Thermal bending, alloys and actuator requirements — 21 October 2026

The owner explicitly requested bimetallic strips, alloys, bending under heat,
thermal actuators and electrical actuators. These extend the existing material,
layered-mechanics, field/circuit and mechanism stages; they are not new enabled
capabilities. In particular, the current small-strain isotropic tetra interface
above is a foundation, not a qualified bimetal/SMA or general actuator workflow.

| Family | Required model and observables | Verification/validation before promotion |
|---|---|---|
| Bimetallic and multilayer strips | Distinct bonded layers, thickness/orientation, stress-free reference state, layer-specific expansion/stiffness and actual temperature fields; curvature, tip displacement, stress, free stroke and blocked force | Independently derived bonded-beam/laminate reference, layer-reversal and equal-expansion controls, force/moment balance and thickness/length mesh convergence; measured curvature/temperature or force/stroke data |
| Thermal bending of ordinary alloys | Supplied alloy-specific temperature-dependent elasticity, expansion, conductivity, heat capacity and resistivity; gradients, constraints and residual stresses explicit | Free/constrained bar and through-thickness-gradient beam references; distinguish material mismatch from gradient-driven bending; check property interpolation/ranges and independent stress/displacement convergence |
| Thermal and electrothermal actuators | Expansion-driven beams, bimorphs, buckled structures and electrically heated elements, with cooling, preload, attached loads and mechanical constraints | Actual heating and thermal solve feeding mechanics, heat/storage/loss and mechanical work accounting, free-stroke/blocked-force curves and heating/cooling transients. Snap-through, contact/end stops and large rotations require their separately verified nonlinear models |
| Shape-memory alloys, when selected | Explicit phase/transformation state, heating/cooling hysteresis, stress dependence, transformation heat, history and calibration; not a large constant expansion coefficient | Independent material-point paths, major/minor thermal/load cycles, dissipation/energy and consistent tangent checks, rate/ambient sensitivity and measured device histories. Ordinary alloy support does not imply SMA support |
| Electrical actuators | Solenoids, voice coils and motor-driven mechanisms; electrostatic, piezoelectric and magnetostrictive families through their own constitutive/field models | Force/torque and reciprocal electrical response, stored field energy/coenergy, drive-circuit/back-EMF and motion consistency, stroke/pull-in/contact limits, mesh/time/coupling refinement and matched measurements |

Materials need supplied or admitted physical properties, reference temperature,
valid temperature/stress/rate ranges, units, tensor axes where applicable,
source/uncertainty and constitutive model identity. An alloy name or composition
does not supply those laws. Temperature-dependent expansion requires consistent
thermal-strain integration under the selected convention, not silently treating
the current constant-alpha law as universal. Plasticity, creep, fatigue and
transformation history need explicit state and applicability.

Bonding must be declared: the first laminate reference assumes a perfect bond;
finite thermal/contact resistance, slip, delamination and cohesive failure need
their own interfaces. Thin-layer mesh resolution/locking and beam/shell versus
solid assumptions require separate checks. A display-only deformation cannot
change electrical gaps, resistance, cooling geometry or contact automatically.

For electrothermal actuation, conserve every mapped electrical loss in the
retained heating volumes, including temperature-dependent resistance and any
qualified field/core losses. If motion changes electrical or thermal behavior,
solve the declared feedback at one accepted state with convergence and rollback.
One-way temperature-to-displacement output must remain labeled one-way.
For dynamic devices, retain mechanical inertia/damping, heating/cooling times,
drive timing and actual histories rather than extrapolating a static stroke.

The first benchmark should be an independently authored, constant-property,
perfectly bonded two-layer cantilever under uniform temperature change: check
zero change, identical-expansion zero-curvature control, layer-order reflection,
heating/cooling reversal, curvature and blocked-force equilibrium. Then add a
thermal gradient, actual Joule heating/cooling, and separately qualified
large-deflection/contact or SMA history. Predeclare case-specific tolerances
and reference applicability before running; no such new benchmark is claimed
as executed by this requirements update.

Native implementation follows [the C++/HPC roadmap](NATIVE_HPC_MIGRATION.md),
with independent reference oracles, reusable states and existing numerical/
release gates. Compact actuator laws, supplied-map motion and geometry-derived
coupled fields remain distinct fidelity levels.

Planning sources checked21October2026: Timoshenko's1925
[Analysis of Bi-Metal Thermostats, DOI10.1364/JOSA.11.000233](https://opg.optica.org/josa/abstract.cfm?uri=josa-11-3-233)
is a candidate classical reference; publisher metadata was checked, but no
full-text derivation is claimed reviewed/adopted here. NIST's2011
[SMA thermo-mechanical characterization abstract](https://www.nist.gov/publications/tips-and-tricks-characterizing-shape-memory-alloy-wire-part-4-150-thermo-mechanical)
was reviewed for its experimentally described coupling, loading-rate, ambient
and transformation-heat effects. Neither reference establishes an implemented
SPIKE material law. Future numerical changes still require the precise primary
method review, independent derivation, executed evidence and human review.

## Shared materials, libraries and evidence

LB01 must bind mechanical elasticity/expansion/yield/damage, temperature laws,
conductivity, permeability/remanence/loss and semiconductor mobility/carrier
properties to units, tensor frames, ranges, provenance, uncertainty and rights.
LB02 must keep CAD appearance distinct from physical parts: coils, magnets,
cores, bearings, springs, joints, Hall plates and electronic compact models.
VF01/VF02 must display signed vector and tensor results, principal directions,
time/rotor phase and deformation scale without changing authoritative geometry.

Boundary-element exterior fields remain in the existing roadmap: absence of an
air-volume mesh does not remove surface discretization, singular integration,
conditioning or method/material restrictions. Couple BEM/FEM only after flux,
energy, forces and interface conservation are validated for the declared case.

Done applies only to a bounded stage with executed source-bound evidence.
Full family completion still requires closed gaps and accepted benchmarks.
Knowledgeable numerical review remains required before release.
