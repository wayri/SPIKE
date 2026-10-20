<!-- SPDX-License-Identifier: Apache-2.0 -->
# General CFD/CHT capability target

The [tetrahedral CAD/open-flow workflow](CFD_TETRA_WORKFLOW.md) and
[execution record](validation/CFD_CAD_OPEN_BOUNDARY_20261021.md) now track the
first geometry/open-boundary increment. They retain single-material CAD bridge,
creeping vector-Laplacian/pseudo-traction and prescribed-flow thermal bounds;
the engineering turbulence and turbulent CHT stages below remain separate.

Owner direction recorded 21 October 2026: complex internal passages, adaptive
external-flow meshes, engineering aerodynamics, conjugate heat transfer and
their quantitative analysis are product targets. Visual appearance alone is
not acceptance evidence. This document extends the
[internal fluids/FSI stages](INTERNAL_CFD_AND_FSI_PLAN.md), not their runtime
admission or release gates. It does not enable an unsupported capability.

The supplied images are requirements references, not input geometry, measured
results, redistributable assets or evidence of a particular numerical method.
No image, external interface design or external implementation is incorporated.
The implementation and derivations must remain independently authored.

The [21 October bounded increment](validation/CFD_CAPABILITY_INCREMENT_20261021.md)
implements joint mean/SA equation verification and conservative supplied-field
interrogation with actual benchmark replays. It does not complete the general
geometry, engineering turbulence, aerodynamic or coupled-thermal targets below.

## Required workflows and observables

| Workflow target | Physical/numerical requirements | Quantitative outputs, not just pictures |
| --- | --- | --- |
| Branching internal passages and enclosed cooling | Connected fluid-volume extraction, manifolds/gaps, inlet/outlet/wall conditions, resolved boundary layers, admitted turbulence, fluid/solid interfaces | Branch mass split; static/total pressure loss; pumping/fan operating point; recirculation; temperature/heat-flux distributions; integrated energy closure |
| External body/vehicle/wing flow | Far-field/wind-tunnel domain, surface geometry, wake refinement, boundary layers, ground/wheel conditions where applicable, admitted separation/transition model | Pressure/shear separately; Cp/Cf; lift/drag/moments and reference quantities; separation/reattachment; wake profiles; domain/mesh/time sensitivity |
| Conjugate thermal assemblies and exchangers | Multiple solids/fluid circuits, heat loads/contact resistance, temperature laws and buoyancy within stated validity, consistent wall heat flux, admitted radiation/porous laws | Hot spots; temperature gradients; wall/interface heat rates; stored energy; enthalpy balance; pressure drop; thermal resistance/effectiveness with explicit definitions |
| Rotating blades and machinery | Blade surface/near-wall mesh, MRF operating envelope, then conservative moving/sliding/ALE interfaces and time integration | Thrust, torque, angular momentum and shaft work; CT/CP/J conventions; blade/wake loads; interface, mesh/time and operating-point refinement |
| Deformation and fluid/structure interaction | Actual structural participant, pressure-reference convention, conservative force/moment/work transfer, interface iteration and rollback | Displacement/stress/reactions; energy transfer; response frequency/damping and flutter boundary only after dynamic qualification |

Streamlines illustrate a steady reconstructed velocity field; pathlines require
time-resolved fields. They are not interchangeable. A steady RANS result is not
a resolved turbulent spectrum, mixing history, acoustic prediction or particle
trajectory model. A deformation overlay requires real structural results;
arbitrary visual displacement cannot establish FSI.

## Mesh engine requirements

1. Preserve units, frames, topology and persistent region/interface/patch IDs
   from supplied CAD/mesh through preparation and results. Admit watertight
   fluid volumes; expose leaks, overlaps, missing thin gaps and failed repairs.
2. General face/cell topology supports tetrahedral, polyhedral and suitable
   hexahedral regions plus prism boundary layers. Availability of a tetrahedral
   geometry generator does not establish solver support for that mesh.
3. Supply boundary-layer thickness/first-cell height and growth controls;
   demonstrate orthogonality, wall-distance and wall-resolution suitability.
   High aspect ratio is not alone an invalidity criterion for aligned layers.
4. Confined local h-refinement and coarse/fine face subdivision must preserve
   summed mass/energy fluxes. Re-solving global tensor planes is not octree AMR.
   Manual region locks, near-gap/wall and wake sizing must be retained during
   auto-optimization instead of silently discarded.
5. Refinement indicators combine geometry, residual/solution features and
   quantities of interest. Goal-oriented/anisotropic methods are candidates,
   not substitutes for actual convergence evidence. Report refinement cost
   and error, not merely cell count or a smooth plot.
6. Every accepted mesh passes positive-volume/orientation checks, interior-face
   pairing, boundary closure and geometric divergence tests. Skew/nonorthogonal
   correction, gradients and pressure coupling need manufactured verification.
7. Moving meshes require geometric conservation and conservative state transfer;
   adaptation/remapping must retain mass, momentum, thermal energy, identities
   and coupling checkpoints. Cell clipping/merging cannot hide lost energy.

Body-fitted layered meshes are the engineering baseline to qualify. Conservative
Cartesian cut-cell and shifted-boundary/octree methods are separate candidates
for geometry robustness and automation. They are not interchangeable, and no
automatic choice between them is currently advertised.

## Solver and analytical requirements

- Steady and transient conservative incompressible momentum/energy first;
  variable properties and buoyancy only with explicit constitutive validity.
  Compressible total energy/EOS remains a distinct stage, not an extension by
  changing density in the incompressible equations.
- Verify each exact RANS variant, wall distance and boundary treatment before
  widening the current Reynolds envelope. Add alternative closures and then
  LES/hybrid methods against matched references; no universal model is assumed.
- Assemble all returned certificates from the same accepted state. Momentum
  at yesterday's eddy viscosity and closure at today's velocity is not a joint
  nonlinear solution. Mean, closure, mass and thermal residuals remain separate.
- Pressure/shear surface integrals retain normals, reference pressure, force
  and moment origins. Nondimensional coefficients retain rho, U, area, length
  and averaging conventions. No coefficient is silently computed at U=0.
- Heat accounting retains volumetric/face/contact/boundary sources, storage
  and enthalpy transport. h/Nu/thermal resistance require declared area,
  reference/bulk temperature and length; near-zero denominators are not masked.
- Probe histories, cuts, vector glyphs, surface maps, volume fields and seeded
  traces retain source/mesh/frame/time identity, units and solved/derived status.
  Smooth rendering must not alter or replace solved fields.
- Parallel block/multigrid/Krylov backends, bounded memory, cancellation and
  replayable restart need actual builds and scaling studies. GPU or distributed
  availability is not inferred from a dependency or paper.

## Delivery order and evidence

| Priority / existing stage | Next complete increment | Acceptance before promotion |
| --- | --- | --- |
| 1 / CFD-01 | General conservative geometry/topology and open boundaries | Nonorthogonal/curved manufactured solutions; inlet/outlet mass balance; Poiseuille/Couette; pressure-nullspace and checkerboard controls; refinement |
| 2 / CFD-04 prerequisites | Joint mean/SA equations and analytical flow interrogation | Same-state joint residuals; molecular-Re admission; independently continuous coupled manufactured fields; exact probe/trace controls, wall rejection and bounded output |
| 3 / CFD-01/04 | Layered meshes and engineering turbulence | Exact model/BC match on NASA-style flat-plate and separated-flow references; wall/domain/mesh studies; independent-code limits and model-form uncertainty |
| 4 / CFD-02/03 | Internal-flow CHT and external aerodynamic workflows | Branching duct and conjugate solid/fluid references; energy/enthalpy balances; exchanger data; pressure/shear forces and wake/domain refinement |
| 5 / CFD-05 | Actual propeller/MRF then moving/sliding blades | Matched geometry and UIUC-type thrust/torque data; shaft-power closure; rotating-interface conservation; time/mesh/outer-domain studies |
| 6 / CFD-07/08 | Mechanical load transfer then strongly coupled FSI | Resultant/moment/virtual-work checks; structural references; complete rollback; added-mass and independently matched dynamic FSI/ flutter cases |

Priority is dependency-driven: the current bounded equation-verification work
can proceed while general geometry is developed, but cannot qualify the later
engineering flows. Predeclare tolerances from benchmark uncertainty, regime and
discretization before runs. Keep failures and prior evidence immutable; do not
promote a stage by deleting its failed cases or loosening its budgets.

## Established and recent research

The [21 October research review](validation/CFD_CHT_RESEARCH_REVIEW_20261021.md)
distinguishes established conservation/verification resources, 2025/2026 journal
methods and recent 2026 preprints. Each candidate must beat an established
baseline at matched error and whole-workflow cost before adoption. Novelty or
citations alone establish neither correctness nor speed. No external source
code, example mesh, measured data or figure is copied into the implementation.

Current executed bounds remain in [solver status](SOLVER_STATUS.md) and the
[flow research workflow](ENCLOSURE_FLOW_RESEARCH.md). This is a product target,
not a claim that the illustrated engineering workflows work today.
