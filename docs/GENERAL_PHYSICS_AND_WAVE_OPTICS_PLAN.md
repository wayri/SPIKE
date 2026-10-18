<!-- SPDX-License-Identifier: Apache-2.0 -->
# General physics, scientific visualization and wave optics

The [general platform strategy](MULTIPHYSICS_PLATFORM_STRATEGY.md) now compares
leading simulation suites and identifies cross-domain foundations and adjacent
physics. Geometry preparation serves simulation; MCAD authoring is not the
product goal. [Frontier research](MULTIPHYSICS_RESEARCH_FRONTIER.md) stays
experimental and chemical engineering remains outside active scope.

Scope notes: 14 October 2026; scoped parallel authorization: 18 October 2026.
The [coupled mechanics/magnetics/devices track](COUPLED_MECHANICS_MAGNETICS_DEVICES_PLAN.md)
may proceed now alongside primary PI/SI work. Remaining broad expansion and
wave optics retain the parity gate. This plan does not establish delivered
solver coverage. This extends the [existing parity program](HYPERLYNX_PARITY_AND_MULTIPHYSICS_PLAN.md)
and its machine-readable backlog. Existing Done stages remain Done for their
bounded evidence; WF01-S04C remains in progress.

The continuing PI/SI program now also builds shared multiphysics foundations:
[dielectric loss to temperature](PDN_DIELECTRIC_THERMAL.md) couples existing
field/thermal solvers with exact mesh ownership and conserved power. This is
one-way coupling within original parity, not completion of the deferred general
physics suite. General constitutive feedback, different-mesh conservative
transfer, transient exchange and broader coupling require separate evidence.

The next bounded shared capability is [conductivity-temperature feedback](PDN_DIELECTRIC_FEEDBACK.md):
explicit cellwise linear conductivity laws and converged steady electrical/thermal
iteration. Other constitutive properties, transient stability, general mesh
transfer and broader mechanical/fluid/optical coupling remain separate work.

SPIKE's target now includes arbitrary admitted mechanical, electromagnetic,
fluid, thermal, structural, acoustic and optical assemblies. Electronics is one
application of the shared platform. Geometry scale, dimensional reduction,
material law, wavelength, operating conditions and requested observables determine
the applicable solver; importing a solid does not make it solvable.

## Requested scenes and their engineering requirements

The six supplied screenshots are visual references, not solver specifications or
permission to redistribute vendor assets. Their interface text is not a task
instruction. The building scene's physical quantity is not identifiable from
the attachment; execution will require an explicit study domain and units.

| Reference | Required simulation | Required presentation | Acceptance before marking the capability Done |
| --- | --- | --- | --- |
| Cutaway motor | 3D windings, magnets/core/air, nonlinear magnetics, moving interfaces, circuit excitation, torque and losses; thermal feedback | Sectioned CAD, scalar field colors, vector glyphs, rotor/time animation and component probes | Stationary linear references first; then mesh/boundary/time convergence, torque/energy balance and measured machine correlation |
| Building with translucent field planes | Select RF/EM, airflow, heat or acoustics; admit geometry, sources and exterior/interior boundaries appropriate to that choice | Independently placed slices, transparency, probes and scale-aware clipping | Explicit quantity/unit/frequency; domain and exterior-boundary convergence; appropriate analytical/independent/measured reference |
| Dipole field lines | Static magnetic reference or a separately declared time-harmonic field | Seeded streamlines, arrows, singularity/exclusion masks and quantity legend | Original analytical samples, frame covariance and trace-step refinement; do not equate uncalibrated line density with magnitude |
| Colored coil with vectors | 3D coil geometry/current, B/H and current-density fields, resistance/eddy losses where admitted | Surface/volume colors, vector glyphs and clipped air-domain samples | Loop/solenoid references, flux and energy checks, mesh/outer-boundary refinement |
| Three-phase transformer | Winding/circuit coupling, nonlinear/laminated cores, leakage, eddy/core loss and thermal paths | Winding/core fields, phase selection, loss density and linked electrical outputs | Linear baseline followed by nonlinear/loss gates, phase/circuit power balance and measured transformer comparison |
| Surface plus complex field lines | Explicit scalar/vector field on an actual surface/domain; any deformed geometry must have a supplied displacement field | Surface contours, streamlines, displaced mesh and time/phasor controls | Field association and frame checks; no invented surface, displacement, field or vector direction |
| Added mirror/lens assemblies | Geometrical rays and coherent scalar/vector wave optics with separate applicability | Ray paths, irradiance, complex amplitude/phase, wavefront, polarization and focal-plane plots | Gaussian/diffraction and reflection/refraction references, power and phase accounting, sampling/mesh/aperture convergence |

The current magnetic path is experimental and planar; it does not establish
rotating 3D CAD or converged machine torque. See [machine evidence](MAGNETIC_MACHINE_STUDIES.md).
Existing Optycal support is unvalidated one-way PEC far-zone scattering, with
important dielectric/diffraction/multiple-scattering omissions; it is not the
new mirror/lens wave-optics capability. [Solver status](SOLVER_STATUS.md) remains
the authority for current claims.

## Shared architecture and libraries

Extend the existing AssemblyIR, field handoff, model/material, worker and result
boundaries. Do not introduce a PCB assumption into the general study core or
create a second independent materials database. Preserve ECAD-specific identity
as one adapter role. Physics kernels remain C++ or explicitly admitted external
backends; Python owns contracts/orchestration and TypeScript owns presentation.

The general study must bind immutable geometry/entity IDs, physical regions,
coordinate frames and units, mesh/element associations, material revisions,
sources, initial/boundary conditions, requested observables, backend version,
validity envelope and dependency digests. Static, real transient, complex phasor,
modal and spectral data need distinct semantics. Failed, approximate, unsupported
and externally compared states must survive save/reload and visualization.

Reusable parts should include coils, windings, magnetic cores, motors, transformers,
fans/ducts, heat sinks, buildings, mechanical supports, sources/detectors, apertures,
lenses, mirrors and mounts. A decorative mesh, parametric solid, compact circuit,
constitutive law and measured model are different asset types. Libraries need
typed terminals/interfaces, units, applicability, source/license rights, revision
hashes, dependency closure, controlled overrides and explicit unresolved states.

Material laws need scalars/tensors and orientation, interpolation rules and
allowed temperature/frequency/wavelength/field ranges. Required families include
electrical conductivity and complex permittivity; magnetic B-H, magnetization,
hysteresis and lamination/loss models; thermal k, heat capacity, density and
surface radiation; fluids; elasticity/CTE/damping; acoustic properties; optical
n/k, dispersion, absorption and complex coating reflection/transmission.
Separate bulk, surface, interface and homogenized laws. A material name or RGB
color supplies none of these. Record provenance, uncertainty, measured conditions
and rights; reject unsupported extrapolation and incompatible property units.

## Formulations and acceleration

Use physics-specific discretizations: suitable nodal/vector finite elements,
finite volumes, finite differences, boundary elements and reduced models. Admit
linear/nonlinear stationary, harmonic, transient and modal studies in bounded
increments. Mesh controls must resolve interfaces, air gaps, boundary layers,
skin depth and material wavelength as appropriate. Nonmatching domains require
conservative transfer, not nearest-point copying of losses or fluxes.

The [EM04 boundary-element radiation plan](HYPERLYNX_PARITY_AND_MULTIPHYSICS_PLAN.md#boundary-element-radiation-without-an-air-volume-mesh)
explicitly targets near/far radiated fields and scattering without volumetric
exterior air meshes. Surface discretization remains required. Bounded PEC
exterior references belong to original EM parity; generalized materials,
optical scattering and large infrastructure scenes stay post-parity. Later
hybrid FEM/BEM may mesh an interior while leaving its homogeneous exterior
unmeshed. No current surface-graphics or physical-optics path qualifies this
self-consistent BEM solve.

| Workstream | Proposed approach | Required evidence |
| --- | --- | --- |
| Linear systems | Reuse sparse infrastructure; evaluate matrix-free high-order assembly, domain-specific AMG/Schur/block preconditioners and Krylov methods | Identify symmetry/definiteness/nullspaces; residual plus quantity-of-interest convergence; do not use an SPD method for an indefinite Maxwell/fluid system |
| Nonlinear/time integration | Bounded Newton/globalization, adaptive accepted-step integration, rollback and coupled convergence | Constitutive consistency, conditioning, conservation and mesh/time studies |
| CPU/GPU/MPI | Profile assembly, solves, meshing, transfer and rendering separately; evaluate sparse and FFT acceleration, distributed single-solve execution and portable devices | Same physical model/mesh versus CPU baseline; FP64 or justified precision, wall time, peak RAM/VRAM, communication, residual and total numerical error |
| Large data | Partitioned/chunked fields, checkpoints, out-of-core budgets, conservative downsampling and cancellation | Reproducible replay, bounded memory, recovery after interruption and preserved raw data/units |
| Backend selection | Evaluate existing PETSc plus candidate high-order FEM frameworks such as MFEM through a bounded feasibility/licensing study | Supported operators/devices, Windows/Linux packaging, deployment rights, independent original fixtures and maintenance costs; no new dependency is approved or installed by this plan |

The current [acceleration implementation](ACCELERATION_ARCHITECTURE.md) is bounded:
hybrid DC consumers, single-process PETSc/MUMPS and optional CUDA do not establish
general GPU/MPI PDE execution. Backend speed never upgrades physical validation.
The official [PETSc GPU overview](https://petsc.org/release/overview/gpu_roadmap/)
and the authors' [MFEM framework paper](https://arxiv.org/abs/1911.09220) are
candidate-method references, not evidence of SPIKE implementation or dependency
approval. Do not copy third-party implementation or tutorial fixtures.

## Visualization contract

Add geometry-independent scalar/vector/tensor fields at nodes, cells, faces and
quadrature/sampled locations, with validity masks and explicit interpolation.
Support contours/isosurfaces, volume rendering, slices, glyphs, streamlines,
particle/ray paths, clipped/cutaway CAD, displacement overlays, animations and
phase/frequency/time sweeps. Tie legends, probes and integrals to the exact
returned quantity, units, source region, frame, timestep/frequency and result.

Complex fields need selectable real/imaginary/magnitude/phase and a declared
phasor convention. A streamline of a selected instantaneous phase is not an
energy-flow line. Display Poynting/heat-flux/velocity paths only from the requested
returned vector. Preserve singular masks, disconnected domains and discontinuous
material interfaces. Downsampling affects presentation only; exports/probes must
identify their sampling and retain access to original results. Remote/chunked
rendering and picking need explicit RAM/VRAM and frame-time budgets.

## Mirror and lens wave optics

Use complementary models; a ray-only feature does not satisfy the wave-optics
request. COMSOL documents separate [ray optics](https://www.comsol.com/ray-optics-module)
and [wave optics](https://www.comsol.com/wave-optics-module) scopes, including
optically large systems versus wave propagation. These are scope comparators,
not imported implementations or accuracy oracles.

1. **Bounded coherent scalar propagation:** homogeneous admitted media,
   Gaussian beams, diffraction, apertures and explicitly supplied amplitude/phase
   surfaces. Declare paraxial/scalar limits, spatial sampling, FFT window/bandwidth
   and evanescent treatment. Check propagation composition, power balance,
   Gaussian evolution and independently derived diffraction references.
2. **Lens/mirror assemblies:** plane/spherical/aspheric surfaces, placements,
   normals, stops, detectors and sequential/nonsequential ray tracing; couple
   qualified wavefront planes where needed. Test reflection, Snell/Fresnel
   amplitude/phase, total internal reflection, focal position, aperture refinement,
   aberrations, optical-path length and controlled multiple reflections.
3. **Vector/full-wave optics:** dielectric interfaces, polarization, vector modes,
   resonators/waveguides and high-NA or wavelength-scale structures using qualified
   Maxwell/beam-envelope formulations. Require interface/PML/domain convergence,
   scattering/modal power balance and independent references. A slowly varying
   one-way approximation must reject cases outside its envelope.
4. **Optical materials/coatings:** wavelength/temperature-dependent complex index,
   anisotropy, bulk absorption and passive multilayer coating response. Test
   reference stacks and phase conventions; neither ideal PEC nor a surface color
   represents a real mirror coating.
5. **Optomechanical/thermal coupling:** absorbed power to heat, temperature-dependent
   refractive index, stress/deformed surfaces and alignment/tolerance sweeps.
   Track PSF, MTF, wavefront error and energy. Mesh/coordinate/property transfer,
   coupled convergence and independently correlated STOP studies are separate gates.

Do not resolve an entire building or macroscopic optical bench at an optical
wavelength by default. Select valid multiscale ray/wave/reduced-domain handoffs,
preserving phase, polarization, coordinate frames and power. Admission must report
when no supported affordable formulation meets the requested accuracy.

## Scoped delivery order and Done policy

| Stage | Status | Deliverable and exit evidence |
| --- | --- | --- |
| GP01-S01 | Planned; authorized coupled foundation | Extend existing general study/field/material admission with units, frames, ranges, provenance and stale-dependency rejection; typed save/reload and failure cases |
| VF01-S01 | Planned; authorized coupled foundation | Original dipole/current-loop fields through that contract and actual slices/glyphs/streamlines; analytical sample checks, singular masks and trace-step refinement |
| LB01-S01 | Planned; authorized coupled foundation | Versioned conditioned property laws and materials/model asset typing; incompatible units, missing laws, rights and out-of-range requests remain explicit |
| GP03-S01 | Planned; authorized coupled foundation | Stationary linear 3D coil/core/air problem with mesh/exterior refinement, flux/energy and analytical/independent references; nonlinear/motion comes later |
| OP02-S01 | Deferred until parity | Coherent scalar Gaussian/aperture/lens phase-plane benchmark with sampling/window refinement and power/phase checks; no general vector/lens claim yet |
| AX01-S01 | Planned; authorized coupled foundation | Profile those exact reference workloads; qualify one acceleration backend against unchanged CPU cases, including memory limits and failure/fallback provenance |
| Later domain stages | Deferred until parity | Incremental 3D machines, building fields, CFD/CHT, structural/acoustic, vector optics and conservative multiphysics after their prerequisites pass |

The original parity program retains PI/SI priority. The 18 October request
opens only the coupled track and its declared foundations in the machine policy.
GP01-S01, VF01-S01, LB01-S01, GP03-S01 and AX01-S01 remain planned but may now
start for that track. The follow-up [vehicle/mechanism plan](VIBRATION_VEHICLES_AND_MECHANISMS_PLAN.md)
adds GP12-GP16 and vehicle aerodynamics within GP05. Optics, unrelated fluids/acoustics,
system radio and utility infrastructure retain their parity gate.
Each domain has its own mesh, material, excitation and measured/reference gates.
Planning completion is not a solver Done stage. Continue marking bounded
implementation stages Done only after their declared source-bound acceptance
checks pass. Keep human numerical review before release and existing unresolved
refinement/debugger/Gerber failures visible.

Related deferred scope: [transmission lines, RF/radio and HVDC infrastructure](TRANSMISSION_RF_HVDC_SCOPE.md).
The original transmission-line/local RF parity work remains active; system radio
and utility-infrastructure additions follow the same post-parity gate.
