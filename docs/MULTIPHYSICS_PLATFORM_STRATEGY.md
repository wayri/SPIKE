<!-- SPDX-License-Identifier: Apache-2.0 -->
# SPIKE general multiphysics platform strategy

Research snapshot: 18 October 2026. Product direction: **multiphysics simulation**,
with PCB/electronics as an initial application and import domain. Chemical
engineering is outside the active expansion. This is a recommended coverage and
architecture assessment; it does not promote runtime capabilities, establish
commercial parity or supersede the existing execution gates.

Read [current solver status](SOLVER_STATUS.md), the
[parity and expansion backlog](HYPERLYNX_PARITY_AND_MULTIPHYSICS_PLAN.md),
[coupled mechanics/magnetics/devices](COUPLED_MECHANICS_MAGNETICS_DEVICES_PLAN.md)
and [vibration/vehicle/mechanism stages](VIBRATION_VEHICLES_AND_MECHANISMS_PLAN.md)
for implemented bounds and authorized delivery order.

## Product boundary

The central objects are a physical study, admitted domains/interfaces, governing
equations, materials, initial/boundary conditions, discretizations, solver state,
coupling contracts and engineering observables. ECAD, MCAD, scans and mesh files
are sources of geometry/identity. A PCB is one study class, not the universal
physical domain or project schema.

Include simulation geometry preparation: topology/region repair, units/frames,
defeaturing, midsurfaces, symmetry, periodic sectors, boundary layers, moving
interfaces, parameterized reference domains and durable source/entity bindings.
Geometry changes used in optimization must be traceable and remeshed/requalified.
A general mechanical drafting, feature-history, assembly-authoring or manufacturing
drawing environment is outside the product goal. Imported mechanical joints and
interfaces become physical constraints only through an explicit simulation model.

## What leading platforms suggest

These are official public descriptions, not independently tested accuracy or
market-share rankings. Pin version/module/licensing and matched test cases before
any parity claim. Different suites emphasize different levels of fidelity.

| Reference platform | Observed public coverage | SPIKE implication — engineering judgment |
| --- | --- | --- |
| [COMSOL suite](https://www.comsol.com/products) and [6.4 solver release notes](https://www.comsol.com/release/6.4/studies-and-solvers) | Coupled equation-based domain modeling, materials, optimization/UQ and specialized physics; GPU sparse solving and explicit dynamics are documented. | A shared study/constitutive/equation core matters as much as individual solver names; measure whole-workflow acceleration. |
| [Ansys portfolio](https://www.ansys.com/en-in/products) and [Workbench](https://www.ansys.com/products/ansys-workbench) | Electronics/EM, thermal/fluids, structures, optics, embedded/system tools and coordinated analysis workflows. | Couple field, circuit, control and mission models with revision-bound transfers and solver-specific fidelity. |
| [SIMULIA portfolio](https://www.3ds.com/products/simulia/all-products) | Abaqus/fe-safe, CST, PowerFLOW/XFlow, Simpack and integration/optimization products span structures, durability, EM, flow and motion. | Nonlinear failure, contact, fatigue and multibody motion require substantial domain methods and validation. |
| [STAR-CCM+](https://www.siemens.com/en-gb/products/simcenter/fluids-thermal-simulation/star-ccm/) and [HEEDS](https://www.siemens.com/en-gb/products/simcenter/integration-solutions/heeds/) | Multiphysics CFD includes FSI, aeroacoustics and multiphase/particles; HEEDS addresses multidisciplinary exploration and execution workflows. | Flow fidelity, moving domains and automation/optimization must share data and evidence. |
| [Simscape Multibody](https://www.mathworks.com/help/sm/) | Mechanical equations of motion interact with electrical/hydraulic/pneumatic systems and Simulink controls; code-generation deployment is documented. | Add system/plant/controller composition and executable-code integration alongside spatial field solvers. |
| [MOOSE](https://mooseframework.inl.gov/) and [MFEM capabilities](https://mfem.org/features/) | Public numerical frameworks emphasize reusable discretizations, nonlinear/coupled solving, adaptivity and scalable execution. | Study numerical architecture independently of commercial UI; no framework/dependency is selected by this assessment. |

## Additions and depth still needed

Priority here is a recommendation: **foundation** serves every current domain;
**adjacent** extends authorized applications after prerequisites; **horizon** is
separate future scope. Existing optics, general CFD/acoustics and other deferred
families retain their explicit execution policy. Research experiments never
become a production capability merely by appearing in this table.

| Coverage | What SPIKE should include | Mathematical and validation boundary | Existing owner/scope |
| --- | --- | --- | --- |
| Foundation: general PDE and constitutive core | Expert equation/weak-form extension points, scalar/vector/tensor unknowns, constraints, Jacobians, nonlinear material state and initialization. | Governing/weak forms, compatible spaces, constitutive tangents, well-posed boundaries, dimensional checks, nullspaces and energy/dissipation. User equations need the same evidence as built-ins. | GP01/02, LB01; new numerical changes follow the evidence policy. |
| Foundation: strong multiphysics coupling | Monolithic and partitioned methods; thermal/electrical/mechanical/EM/flow coupling, nonmatching meshes, events, multirate stepping, checkpoints and rollback. | Interface force/flux conservation, virtual work, added-mass/stiff-feedback stability and coupled convergence. File exchange alone is insufficient. | GP09/WF04; extend bounded existing handoffs. |
| Foundation: discretization and error control | Physics-specific FEM/FVM/FDTD/DG/BEM; adaptive h/p refinement, boundary layers, singular/exterior treatment, mesh motion and goal-oriented error estimates. | Maxwell curl/divergence structure, saddle-point stability, incompressibility, locking, positivity and problem-dependent asymptotic checks. Surface BEM avoids air-volume meshing only within its formulation's envelope. | GP02/EM, AX01; mesh generation remains simulation infrastructure. |
| Foundation: uncertainty and inverse problems | DOE/sensitivity, correlated uncertain inputs, calibration/identifiability, parameter estimation, reliability, robust/Pareto optimization and adjoints. | Distinguish measurement, parameter, discretization, coupling, model-form and surrogate error. Validate gradients and hold out calibration/validation data. An optimizer cannot validate its forward model. | WF05/06 and cross-domain strategy; dedicated stages still need definition. |
| Foundation: material and physical-model libraries | Temperature/frequency/strain-rate/field-dependent tensors, surface/contact/coating laws, uncertainty/ranges; common versioned part, sensor and reduced-model catalog. | Orientation, passivity, thermodynamic consistency, extrapolation rules, source rights and missing-property diagnostics. An appearance asset is not a constitutive model. | LB01/02, WF02. |
| Foundation: scalable execution and model hierarchy | Sparse/block/preconditioned and matrix-free solves, CPU/GPU/MPI, profiled ensembles, full-order/reduced-order models and field streaming. | Equal-error CPU/reference comparisons; setup/meshing/transfer/preconditioner/I/O included in timing. Preserve conservative/passive/stable reduced states where applicable. | AX01/02, VF01/02; existing deferrals remain. |
| Adjacent: acoustics and vibration | Pressure/elastic waves, acoustic-structure coupling, thermoviscous losses, ultrasound, transducers, aeroacoustics and radiated noise. | Wave/impedance/PML or boundary-integral references, energy/radiation balance, mesh-per-wavelength and temporal convergence; avoid unresolved high-frequency brute force. | GP08, GP12; general acoustics is still deferred. |
| Adjacent: smart materials and MEMS | Piezoelectric, magnetostrictive and electrostatic actuation, pull-in, resonators/gyros, squeeze-film damping and electrothermal sensors. | Coupled momentum/charge and constitutive laws, material frames, stability/bifurcation, rarefaction where needed and independent device references. | Extend GP03/07/10 and LB01; not yet a complete MEMS suite. |
| Adjacent: advanced nonreacting fluids | Compressibility/shocks, RANS/LES/hybrid turbulence, rotating machinery, free surfaces, cavitation, capillarity, boiling/condensation and non-Newtonian behavior. | Conservation/EOS/entropy and interface jump conditions; turbulence and phase-change closures need applicability and measurements. No chemical kinetics is implied. | GP05/06; currently only authorized subsets may advance. |
| Adjacent: FSI and aeroelasticity | Moving/deforming propellers, flutter, flexible wings, pumps, structures in wind/water and thermal deformation feedback. | Consistent traction/displacement work, geometric conservation, contact/free-boundary behavior and mesh/time/coupling refinement. | GP09, GP15/16; separate flutter evidence required. |
| Adjacent: hydraulics, pneumatics and tribology | Pumps/valves/lines/accumulators, hydraulic actuators, seals, lubricating films, elastohydrodynamic bearings/gears and wear. | Mass/momentum/energy network DAEs plus local flow/contact models; cavitation, leakage, friction/heating and wear laws need calibrated bounds. | GP14/05/06; additional application stages proposed. |
| Adjacent: nonlinear/multiscale materials | Composites, visco/hyperelasticity, plasticity/creep, cohesive interfaces, fracture/damage, homogenized lattices and metamaterials. | Frame objectivity, dissipation, tangent checks, length-scale/mesh dependence, irreversibility and measurements; microstructure-to-continuum transfer needs uncertainty. | GP07/11/13, LB01; distinguish constitutive physics from material appearance. |
| Adjacent/later: particles and large-deformation methods | DEM grain/contact dynamics, SPH fluids and MPM solid/particle-grid formulations for selected impact, granular and free-surface problems. | Conservation, particle/kernel consistency, contact calibration, boundary support, stress integration, instability and resolution/convergence checks. BEM surface discretization and particle methods have different equations and applicability. | New bounded method stages proposed under GP02/05/07/14; not a generic meshless-solver claim. |
| Adjacent/later: optics and photonics | Ray and wave optics, polarization/coatings, coherent propagation, optical resonators, optomechanics and structural-thermal-optical performance. | Maxwell/scalar-wave approximations, diffraction, aperture/sampling and energy/phase references. Semiconductor optics is a distinct coupled device model. | OP01-05 remain under their previous gate. |
| Horizon: vacuum, charged particles and radiation | Rarefied/molecular flow, collisionless particle/beam tracking, PIC where applicable, spacecraft charging and radiation-to-heat/device effects. | Knudsen/regime checks, particle noise, charge/energy balance, cross-section/environment provenance and measured dose/device evidence. Collisional/reactive plasma chemistry is separate paused scope. | New scope evaluation, reusing EM/GP10/16; no capability claim. |
| Horizon: manufacturing physics | Nonreactive laser/weld heat transfer, melting/solidification, residual stress, forming, machining/contact and distortion. | Process/material applicability, phase-change/strain history, mesh/time and measured distortion; reaction-dependent curing is excluded for now. | Shared GP06/07/11; process stages proposed. |
| Horizon: biomechanical, civil and geophysical physics | Bioheat/ultrasound/implants, porous flow/poroelasticity, soil/rock and seismic waves, renewable/ocean/atmospheric applications. | Separate constitutive laws, boundary scales, physical validation and use-specific acceptance; generic PDE availability does not qualify an application. | Future scope after the common core and relevant references. |

Useful mathematical starting points include
[SU2's documented governing equations](https://su2code.github.io/docs_v7/Theory/)
for nonreacting compressible flow,
[piezoelectric theory](https://doc.comsol.com/6.4/doc/com.comsol.help.sme/sme_ug_theory.06.043.html)
for constitutive momentum/charge coupling, and
[Modelica fluid balance equations](https://doc.modelica.org/om/Modelica.Fluid.UsersGuide.ComponentDefinition.BalanceEquations.html)
for network mass/momentum/energy. These are **design references**, not assertions
that their implementations or data were used in existing SPIKE code. Every
selected method still needs a precise source/section, independent derivation and
application-specific evidence.

Particle methods are also a current industry direction: COMSOL's
[6.4 release description](https://www.comsol.com/release/6.4?wvideo=lgxi7wwe74)
documents a DEM-based granular-flow module. That establishes advertised product
scope; it does not validate a future SPIKE particle formulation or select a
particular method for every impact/flow problem.

## Cross-domain platform requirements

Use one dependency-aware physical study graph with explicit terminal, interface,
effort/flow and field associations. Preserve units, frame transforms, geometry,
mesh/material/model/code revisions, clocks and accepted state. Scalar replay/gain
co-simulation remains a bounded foundation, not a general coupled PDE master.
FMI is a potential interoperability contract, not a guarantee of coupling accuracy:
the [FMI 3.0.2 specification](https://fmi-standard.org/docs/3.0.2/) leaves the
co-simulation algorithm to the importer. Strong coupling also needs methods such
as [implicit interface acceleration](https://precice.org/configuration-acceleration)
and appropriately [conservative/consistent mappings](https://precice.org/configuration-mapping).
Conserving a global force sum alone does not establish moment or virtual-work
preservation; test the actual paired transfer operators.

Expose scientific results independently of the viewport: scalar/vector/tensor
fields, frequency/phase/mode/time/spectrum semantics, probes, integrals, budgets,
convergence/error plots and raw result export. Provide reusable study templates,
parameter studies, reproducible batch scripting, provenance reports and recorded
test-data comparison. AI can help prepare and explain a study; solver-produced
fields and numerical acceptance remain deterministic, traceable outputs.

## Established methods and frontier research

Maintain two delivery paths using the same reference problems:

1. Established governing physics and independently implemented numerical methods
   provide the reference solution and declared validity envelope.
2. Research candidates are isolated opt-in experiments with explicit citation,
   maturity, additional assumptions and comparison against that reference.
   Promotion requires measured error/cost and validated failure behavior.

The [frontier ledger](MULTIPHYSICS_RESEARCH_FRONTIER.md) covers differentiable
solvers/adjoints, GPU matrix-free/preconditioning, multirate conservative coupling,
uncertainty-aware learned operators, unfitted discretizations and coupled
fracture/contact. The [method-evidence policy](NUMERICAL_METHOD_EVIDENCE.md)
requires referenced mathematics and subject-matter review for future numerical
work; older provenance gaps remain explicit rather than being retroactively erased.

## Chemical engineering expansion directions — paused

Retain these as a separate future branch: reaction kinetics/transport and
reactors; reactive multiphase flow/combustion; electrochemistry and detailed
battery/fuel-cell/electrolyzer models; corrosion/electrodeposition; separations,
membranes, catalysis and process-flow networks. These align with identifiable
families in the [COMSOL product taxonomy](https://www.comsol.com/products), but
are not selected for active SPIKE implementation.

Current electrical battery equivalent circuits, supplied aging laws and thermal
cooling do not imply an electrochemical cell solver. Physical latent heat,
nonreacting multiphase transport, hydraulic working fluids and material creep
may support present goals without adding reaction chemistry. State this boundary
per model; a reactive plasma/combustion/process model cannot be admitted merely
by relabeling it as electrical or fluid physics.

## Recommended execution order

Continue PI/SI and already authorized mechanics/vibration/machine/device/vehicle
stages. In parallel, make their study contracts, materials, numerical evidence,
coupling/session semantics and benchmark corpus reusable across domains.
Prioritize verified sparse/preconditioned solves, conservative coupling and
error estimates before chasing large domain counts. Add DOE/UQ and sensitivities
to bounded validated solvers first; add inverse design after forward and gradient
verification. Extend FSI, smart-material devices, fluid power, advanced flow and
acoustics incrementally under their existing or newly agreed gates. Keep optics,
unrelated broad expansion and chemistry sequencing explicit.

For any added target, first identify the governing problem, existing family,
observable, independent reference, units/tolerances, owner, material/data rights
and failure envelope. Define a bounded stage before implementation. A simulation
platform's breadth is useful only when each advertised task has defensible evidence.
