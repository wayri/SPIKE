<!-- SPDX-License-Identifier: Apache-2.0 -->
# Thermal research and verification roadmap

Research checkpoint: 2026-10-09. This document proposes work and acceptance
criteria; it does not enable capabilities or certify results. Implementation
status belongs in [SOLVER_STATUS.md](SOLVER_STATUS.md). Numerical changes need
knowledgeable human review before release under [CONTRIBUTING.md](../CONTRIBUTING.md).

## Evidence at this checkpoint

| Path | Implemented evidence | Scope that remains open |
| --- | --- | --- |
| Internal retained solid thermal | P1 tetrahedral anisotropic conduction, prescribed convection and heat flux, exact nonlinear ambient-radiation integration, reciprocal matched finite-conductance contacts; transient consistent capacity and backward Euler. Analytical, manufactured, spatial/time refinement and actual CalculiX comparisons exist. | Temperature-dependent thermal properties, enclosure radiosity coupled to volume temperatures, nonmatching contacts, internal fluid momentum/energy and general CAD extraction. |
| Internal layered board and reduced networks | Effective layer conductivity, explicit heat sources, localized grid refinement, prescribed local air boundaries, reduced passage/fan operating points. | Solved 3-D flow, geometry-resolved copper/package accuracy and arbitrary enclosure cooling. The documented real-board refinement failure remains a failure. |
| Optional OpenFOAM multiregion | Runnable solid/fluid region translator and importer; actual synthetic board/package/contact case, one/two-board forced-flow ducts, conservation and refinement records; separate solid-only ambient-radiation vacuum execution. | General imported-assembly CHT qualification, independent flow-solver comparison and measured correlation. A region role or emitted dictionary is not proof of physical accuracy. |
| Retained board/STEP geometry | Reviewed closed STEP component promotion, material/placement ownership, joint conformal Gmsh meshes and explicit contact discovery. | A decorative package does not reveal die, leads, TIM, voids or heat generation. Compound CAD, thin-layer and coolant-domain construction need their own admission evidence. |

Evidence: [solid handoff](ASSEMBLY_FIELD_HANDOFF.md),
[transients](ASSEMBLY_THERMAL_TRANSIENT.md),
[actual CalculiX comparisons](validation/ASSEMBLY_THERMAL_TRANSIENT_20261008.md),
[STEP solids](THERMAL_COMPONENT_SOLIDS.md),
[external multiregion workflow](THERMAL_WORKFLOW.md), and
[executed fan CHT](FAN_CHT_QUALIFICATION.md). These records were inspected for
this roadmap; their numerical runs were not repeated. The fan record also
identifies a subsequent bounded buoyancy/SST increment; its existence does not
qualify arbitrary natural-convection or turbulent cases.

Some older overview text describes only the original single-region OpenFOAM
surrogate. Use the separate multiregion evidence above when assessing that
adapter. Keep external executable evidence distinct from internal capability.

## Recommended sequence

### 1. Extend the verified solid reference before adding new physics

The smallest useful immediate increment is a stronger, reproducible qualification
suite and bounded improvement to time integration. Preserve the existing exact
P1 radiation weak load and tangent; these are already implemented, including
nonuniform-face and manufactured-source tests. Replacing them with a scalar
coefficient evaluated at mean face temperature would reduce fidelity.

Add independently derived transient fixtures with time-varying heat, nonuniform
initial temperature and nonlinear radiation. Run mesh and time refinements
separately, compare physically relevant functionals, and retain failure records.
The acceptance matrix below supplies proposed new gates, not retrospective
claims about old cases. Report discretization evidence separately from algebraic
residuals and energy balance.

An opt-in, bounded time integrator can subsequently reduce time error. Candidate
methods are variable-step BDF2 with a documented startup/restart policy, or
backward-Euler step doubling that accepts the two-half-step solution and estimates
local error. Neither a successful step nor a local estimate establishes global
accuracy. Align integration to every source discontinuity, preserve fixed
temperature constraints, cap rejected steps and growth factors, and test
conservation across accepted steps only. Keep existing fixed BE settings and
saved-result identity stable; a new algorithm requires explicit settings,
provenance, schema and result-admission coverage.

For BDF2, record energy according to the actual multistep equation and independently
audit physical storage over the reported interval. Do not relabel the BE
right-endpoint integrated balance as a BDF2 identity. Consistent P1 capacity and
high-order time integration do not guarantee a discrete maximum principle on
arbitrary meshes. Temperature bounds, monotonicity diagnostics and refinement
must remain visible.

Temperature-dependent materials are a separate increment: author bounded,
provenance-bearing `k(T)`, `rho` and specific enthalpy `h(T)` with
`dh/dT=cp(T)>0`. Discretize storage from enthalpy differences so that changing
capacity does not create spurious energy. Reassemble the nonlinear residual and
tangent consistently. Temperature-dependent conductivity can produce a
nonsymmetric Jacobian; the current SPD/CG assumption cannot automatically carry
over. A safeguarded Picard iteration may retain SPD subproblems but must pass the
full nonlinear residual. Reject extrapolation outside the reviewed material
range. Phase change requires a separately reviewed enthalpy/phase contract.

### 2. Couple enclosure radiation to retained solid temperatures

Use diffuse-gray, opaque, nonparticipating-medium radiosity as the first scope.
For each radiation patch, solve
`J_i = eps_i sigma <T^4>_i + (1-eps_i) G_i`,
`G_i = sum_j F_ij J_j + F_i,ambient J_ambient`, and
`Q_i = A_i (J_i-G_i)`. Patch emission must integrate the actual surface field;
`<T^4>` is not generally `<T>^4`. Conservatively return each patch's heat to the
owning solid faces with a consistent nonlinear linearization.

Reuse the existing geometric exchange-area work where its assumptions hold.
Require nonnegative factors, reciprocal `A_i F_ij=A_j F_ji`, and explained
closure. Unresolved or occluded view cannot be silently assigned to ambient.
Refine both the solid surface and radiation quadrature/patch partition. A closed
reflecting cavity can have a radiosity nullspace; treat the gauge and zero net
exchange explicitly. No absorbing surface and no sink cannot sustain a
positive-power steady state.

Vacuum mode removes continuum convection and fluid regions. It retains solid
conduction, contacts and radiation to declared surroundings. Background space
temperature alone does not define a spacecraft environment: incident solar,
planetary IR and reflected loads need separate orientation, spectrum and
absorptivity inputs. NASA distinguishes solar absorptivity from thermal IR
emissivity in its [thermal-control reference](https://www.nasa.gov/smallsat-institute/sst-soa/thermal-control/).
Residual-gas conduction needs pressure, length scale and a separately qualified
rarefied-gas law; it must not be represented by an invented small air coefficient.

### 3. Build an internal laminar fluid/solid reference

Create a separate solver module behind the existing neutral analysis contracts.
Python owns admission, orchestration and reference fixtures; introduce a C++
kernel only after profiling/numerical requirements justify it. Keep fluid cells,
solid cells, boundary patches and interface operators explicit. A fluid mesh is
the admitted connected free volume after subtracting all solids, not a bounding
box with invisible obstacles. Check leakage, disconnected pockets, overlap,
inlet/outlet orientation, gap resolution and complete boundary ownership.

Start with low-Mach, Newtonian, single-phase laminar flow. Solve continuity,
momentum and fluid energy together with solid conduction. A conservative
finite-volume formulation on conforming faces is a bounded first choice. Use a
documented pressure-velocity coupling with pressure gauge treatment and a
demonstrated absence of pressure checkerboarding. Advection must be bounded in
the admitted regime; diffusion corrections on skewed/nonorthogonal cells must
be covered by a manufactured solution. Do not advertise second-order accuracy
only because the interior stencil has that formal order.

Conjugate interfaces enforce temperature continuity and equal/opposite heat
transfer, or the explicitly authored finite contact resistance. Begin with
matching interfaces. For later nonmatching meshes, use intersection-based
integration or a reviewed mortar projection: the temperature interpolation and
force/heat transfer must be dual operators so total interface heat is conserved.
Nearest-node temperature copying is insufficient. A partitioned solve needs
bounded coupling iterations and convergence of interface temperature and heat
flux; separately converged region solves are not a converged coupled solve.

Natural convection first uses Boussinesq buoyancy within an explicit small
density-variation envelope. Record gravity and orientation, reference density,
expansion coefficient, viscosity and thermal diffusivity; characterize Rayleigh
and Prandtl numbers. Hydrostatic pressure initialization and pressure reference
must agree. Beyond that envelope, implement and verify a variable-density
low-Mach formulation before accepting those cases.

For forced flow, begin with prescribed mass/volume flow and compatible pressure
outlets with explicit backflow thermal data. Add fan pressure-jump/P-Q behavior
only with unit-consistent fan curves, supported operating range and stable
intersection checks. Recirculation, bypass and inlet development change cooling;
a free-air fan flow rating is not the installed flow. Existing reduced fan
networks remain useful approximations and independent limiting-case checks.

### 4. Add water blocks, potting and coatings as physical regions

Water blocks require solid wall/channel geometry, coolant inlets/outlets,
absolute pressure, flow and inlet temperature, fluid property provenance and
temperature range. Start with single-phase liquid water and include coolant
enthalpy transport and pressure drop in the energy/flow accounting. Pump curves
and loop losses are later explicit models. Boiling, cavitation, freezing and
two-phase behavior remain unsupported until independently implemented.
NIST documents [water property formulation provenance](https://www.nist.gov/srd/nist-standard-reference-database-10);
its [fluid property service](https://webbook.nist.gov/chemistry/fluid/)
can support independently requested reference values with recorded units and
state points. Do not silently redistribute external tables or code.

Potting is a retained solid volume with conductivity, capacity, void assumptions
and explicit interfaces. It displaces air; leaving both in the same volume
double-counts material. A homogeneous effective property must retain its
approximation and orientation. Cure heat, shrinkage and moisture are separate
physics.

A coating can be a resolved solid or a reviewed thin-layer model. The latter
must account for through-thickness resistance `R''=t/k` in m2 K/W, areal heat
capacity `rho cp t` in J/(m2 K), surface emissivity, and, where relevant,
in-plane sheet conductance `k t` in W/K. A contact resistance alone captures
neither coating heat storage nor lateral spreading. Avoid ultra-thin poor-quality
tetrahedra solely to make a coating visible. Geometry, electrical insulation and
thermal properties must have separate meanings.

### 5. Expand accuracy and scale only after the laminar gates pass

Introduce turbulence models only with a declared regime, wall treatment,
near-wall mesh requirement and appropriate benchmark. A validated laminar
channel does not validate SST, transition, fan swirl or impinging jets. LES or
DNS for complete electronics assemblies is a separate resource and validation
commitment, not an automatic accuracy upgrade.

For solid accuracy, consider higher-order elements and residual/goal-oriented
adaptive refinement once independent estimators are available. Refine to
observables such as package temperature rise, contact drop and heat rejection;
mesh around source discontinuities and material interfaces. For fluid accuracy,
boundary layers, narrow channels and wakes need targeted resolution. Preserve
mesh ownership and conservative heat deposition through refinement.

Keep sparse operators, bounded history, cancellation, progress and execution
budgets. Do not lift the present reference kernel's 5,000-cell/10,000-node limits
without a measured memory/time model and suitable linear solvers/preconditioners.
The current retained UI and preview buffers are not production CFD storage.

## Proposed acceptance matrix

All tolerances below are proposed development gates selected before running new
cases. They are not universal accuracy guarantees or existing passed results.
Use SI units. Define a nonzero characteristic temperature rise/flux/velocity for
each fixture, so near-zero quantities do not acquire meaningless relative error.
Conservation normalization uses the sum of magnitudes of all physical energy
terms, with an explicitly declared absolute floor for zero-load cases.

| Fixture family | Independent oracle and observations | Proposed gate |
| --- | --- | --- |
| Layered solid/contact | Independently derive `Q=DeltaT/(sum L/(k A)+sum R_contact)`; rotated anisotropic affine patch; insulated uniform heating. | Exact representable fields: temperature error <= 1e-8 K and normalized balance <= 1e-9 on well-conditioned original fixtures; document a separately bounded roundoff allowance. |
| Smooth manufactured solid | Independently differentiate a non-affine temperature field and its source/boundaries; do not call the production assembly for the oracle. | At least three mesh levels; P1 integrated L2 temperature order >= 1.8 in the smooth asymptotic case, with temporal/algebraic errors at least ten times smaller than spatial error. Flux order assessed separately. |
| Transient solid/radiation | Semidiscrete matrix exponential for linear decay; high-accuracy scalar integration/bisection for uniform nonlinear radiative cooling; independently integrated source history. | BE order 0.9-1.1; any proposed BDF2 order 1.8-2.2 on smooth fixtures after startup; nonlinear oracle error <= 0.01 K and cumulative energy defect <= 1e-6 for specified reference cases. |
| Gray enclosure/vacuum | Independently derive parallel-plate exchange and concentric-sphere limits; equal-temperature enclosure and occluded three-body cases. | Analytical exchange <= 0.2%; reciprocity/closure <= 1e-10 on exact-factor fixtures, total enclosure exchange <= 1e-8 of exchange scale. Geometric factors must show quadrature/patch refinement and <= 1% exchange error on the chosen geometry. |
| Isothermal laminar flow | Independently derive plane Poiseuille velocity and pressure drop; manufactured incompressible velocity/pressure field. | Velocity L2 and pressure-drop error <= 0.5% after refinement; boundary mass imbalance <= 1e-8 of throughput; expected spatial order demonstrated separately. |
| Heated channel | Independently derive fully developed channel temperature profile for a precisely stated wall condition; evaluate fluid enthalpy rise and conductive inlet/outlet terms. | Mean heat-transfer and pressure-drop error <= 1%; global energy defect <= 1e-5 on the analytical fixture. Demonstrate fully developed conditions before applying its oracle. |
| Natural convection | Original square cavity geometry/mesh and equations; compare observables to the de Vahl Davis publication and a separately executed established solver. | Ra=1e3, 1e4, 1e5, 1e6 at the reference Pr; mean wall Nusselt number <= 2%, velocity extrema <= 3%; three-grid/time evidence and global energy <= 1e-4. Obtain and record exact primary reference values before admitting the test. |
| CHT two-solid/shared-fluid | Original geometry with independent loads; retain all regional temperatures, interface fluxes and outlet enthalpy. Repeat with one source zero. | Global energy <= 1e-4; integrated interface mismatch <= 1e-6 of heat scale; established-solver temperature-rise difference <= 0.1 K + 2% and heat-transfer/pressure-drop difference <= 2%, subject to both solvers' refinement uncertainty. |
| Single-phase water block | Original straight-channel geometry before a serpentine/manifold; independent hydraulic/thermal limits and established solver. | Channel gates above first; then mass/energy/interface gates, three-grid evidence and <= 3% comparison for pressure drop/heat removal. Require coolant-property range checks and no unsupported phase regime. |
| Potting/coating | Original layered slab, finite-capacity transient and thin-layer-versus-resolved-layer convergence. | Steady resistance <= 0.1%; transient temperature rise <= 0.05 K + 1%; coating reduction error demonstrated over a declared thickness/time range. |

The [de Vahl Davis primary publication](https://doi.org/10.1002/fld.1650030305)
establishes a two-dimensional differentially heated cavity benchmark across
Ra=1e3-1e6. The accessible abstract confirms its scope; numerical tables were
not ingested in this research pass. Do not invent their values or substitute
unreviewed third-party transcriptions.

For engineering cases, retain at least three consistent mesh levels and vary
time step independently. Report observed order and an uncertainty estimate only
when the sequence supports their assumptions; retain nonmonotonic or
indeterminate results. Normalize temperature comparisons by temperature rise,
not absolute Kelvin. NASA's [grid-convergence guidance](https://www.grc.nasa.gov/www/wind/valid/tutorial/spatconv.html)
supports this separation of refinement evidence from physical validity. The
roadmap does not adopt NASA's example data, code or fixture.

## Independent verification and release evidence

Use existing CalculiX integration for the overlapping solid problem; it cannot
verify internal fluid momentum or convection. Preserve the documented
CalculiX DC3D4 versus SPIKE capacity-integration difference rather than tuning
one result to match the other. Compare each discretization against the
continuous or independently assembled semidiscrete oracle before inter-engine
comparison. Export precision belongs in the tolerance budget.

Use a separately executed established CFD engine for laminar flow/CHT (the
existing OpenCFD adapter is a practical candidate), with original independently
authored decks and geometry. A second engine must solve the same equations,
material laws, geometry, loads and boundary conditions. Different meshes are
acceptable when both are refined and conservative comparison observables are
defined. Shared input translation errors can make both engines agree; analytic
geometry, units, total source, volume and boundary audits remain independent.
OpenFOAM Foundation and OpenCFD are distinct distributions: research about
general CHT semantics does not prove compatibility with the installed v2606
adapter. Engine-specific behavior needs actual version-pinned execution.

Retain executable/version hashes, exact input and mesh digests, independently
known geometry checks, all numerical settings, physical assumptions, residual
histories, actual face fluxes, energy/mass histories from time zero, mesh/time
studies, comparison norms, resource use and failures. No mock external result,
successful process exit or visual agreement counts as solver verification.

Predictive hardware claims additionally need measurements with traceable sensor
placement, calibrated power and flow, ambient conditions, material/contact
uncertainty and a predeclared comparison metric. Report measured uncertainty
alongside discretization and model uncertainty. Calibration and validation
datasets must be separate. A fixed 2% numerical gate does not imply 2% PCB
temperature accuracy when contacts, losses or material data are uncertain.

All roadmap prose, proposed contracts, benchmark designs and derivations here
are original. Primary publications and official documentation guided physical
scope and verification principles only. No external implementation, example
deck, mesh or dataset was imported or adapted. No numerical implementation is
added by this document. Any future dependency or reference-data redistribution
requires its own provenance and licensing review.
