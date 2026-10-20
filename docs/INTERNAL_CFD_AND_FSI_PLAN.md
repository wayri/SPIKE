<!-- SPDX-License-Identifier: Apache-2.0 -->
# Internal fluids, conjugate heat transfer and mechanics

The later21October2026 [propulsion/machine/fluid-power request](PROPULSION_MACHINES_FLUID_POWER_PLAN.md)
adds complete small jet-engine studies, rotating power machines and hydraulic/
pneumatic systems as targets. The owner explicitly authorized propulsion
combustion only. This narrow exception supersedes the older nonreacting-only
scope below for that application, not its prerequisites, validation or release
gates; general chemical-process expansion remains excluded.

The [21 October capability target](CFD_CHT_CAPABILITY_TARGET.md) adds explicit
complex internal/external-flow mesh and analysis requirements, delivery order
and a [current primary-research queue](validation/CFD_CHT_RESEARCH_REVIEW_20261021.md).
Reference imagery is a product target, not physical validation or enabled parity.

Scope authorized 20 October 2026: develop an internal CFD family for liquids
and gases, enclosed cooling, heat exchangers, external aerodynamics, rotating
machines and fluid/structure/mechanical interaction. This expands active CFD
development; it does not remove numerical, material, licensing or release gates.
That original authorization did not add reactive chemistry; only the later
explicit propulsion exception above does so. Existing unfinished PI/SI work
stays open.

## Implemented first increment

The native MAC cavity now has a separate `spike_native_cht` executable and
`run_native_cht` worker route. A single conservative finite-volume thermal
system covers the fluid and two solid strips. Temperature and normal heat
flux match at the two material interfaces. Momentum supplies actual accepted
MAC face fluxes to the energy operator, rather than interpolating a field
that might violate mass conservation. Fourier resistances, upwind advection,
discrete residuals and global heat flow have independent checks.

Inputs are supplied constant positive density, viscosity, heat capacity and
conductivity. Both liquid-like and low-Mach gas-like numerical examples execute
the same incompressible Newtonian equations. This does **not** provide an EOS,
automatic material validity, compressible gases, cavitation or phase change.
Flow is isothermal in its material laws; energy does not feed back through
density/viscosity or buoyancy. Thermal storage and startup are not implemented.

The separate `run_coupled_surface_exchange` route admits explicit overlap maps
and transfers heat flux or vector traction to integrated face heat/force.
An adjoint reverse map preserves the declared work/power pairing. It is useful
coupling infrastructure, not an executing two-way FSI master. See
[surface exchange](COUPLED_SURFACE_EXCHANGE.md), [native method](validation/NATIVE_CHT_METHOD_20261020.md)
and [runnable examples](../examples/internal_cfd/README.md).

## Delivery stages and acceptance

The [opt-in v2 increment](ENCLOSURE_CHT_REFINED.md) now supplies stationary
voxel obstacle inertia, pressure gauges per component and actual momentum
re-solving after selected tensor cuts. It closes those bounded CFD-01 pieces,
not the full stage: confined AMR, curved/nonorthogonal topology and general flow
boundaries remain. The [turbulence/rotor prerequisite record](validation/TURBULENCE_ROTOR_REQUIREMENTS_20261020.md)
defines variable symmetric stress/transported closure and rotating-frame/ALE
requirements and benchmark candidates. The separate
[research increment](ENCLOSURE_FLOW_RESEARCH.md) now implements prescribed
symmetric stress, fixed-velocity SA-noft2 transport and whole-frame rotating
momentum. CFD-04/05 workflows remain incomplete and unqualified: no coupled
engineering turbulence, blade/stator interface or propeller model is inferred
from those equation prerequisites.

The next [3-D reference increment](ENCLOSURE_CHT_3D.md) supplies a rectangular
steady inertial MAC region, retained creeping voxel obstacles, conservative
nested thermal cuts, and shared steady/backward-Euler energy. It implements
bounded portions of CFD-01/02 only: thermal startup and manual thermal cuts are
now executable, but momentum AMR, obstacle inertia, general boundaries and
temperature feedback are not. The earlier statement about missing storage
applies to the separate native two-dimensional executable, not this new route.
Turbulence and rotating propellers remain CFD-04/05, with unchanged acceptance.

These stages describe work still required, not enabled capabilities. Existing
GP05/06/07/09/12/14/15/16 plans remain the parent physics and application stages.

| Stage | Deliverable | Minimum acceptance evidence before promotion |
| --- | --- | --- |
| CFD-01: general laminar mesh and boundaries | 3-D conservative face/cell topology, polyhedral/tetrahedral support, boundary layers, nonorthogonal correction, local refinement/manual sizing, inlet/outlet/wall/symmetry/periodic conditions and pressure nullspaces. | Manufactured mass/momentum fields, Poiseuille/Couette and curved/nonorthogonal meshes, positive volumes, shared-face conservation, pressure checkerboard rejection, mesh/outer-domain refinement and bounded sparse/preconditioned execution. Tetrahedral geometry availability alone is not solver support. |
| CFD-02: enclosure and exchanger energy | Transient fluid/solid energy, admitted buoyancy/temperature laws, fans with explicit curves, porous pressure losses, inlets/outlets, conjugate walls/fins/contact interfaces, multiple fluid circuits and liquid cooling. | Startup stored-energy/enthalpy/work balance; forced and natural-convection references; exchanger conduction, pressure drop, effectiveness/energy balance; interface, grid, time and coupling refinement. Match fan/geometry/measurement uncertainty before an enclosure claim. |
| CFD-03: external laminar aerodynamics | Open domains, far-field conditions, body pressure/shear, integrated forces/moments, wake/probe fields and moving-ground options. | Independent cylinder/airfoil references in their admitted regimes; no-slip/shear and normal conventions, drag/lift/moment, wake/domain/refinement checks. A converged cavity is not evidence for a car, wing or aircraft. |
| CFD-04: turbulent engineering flow | Separately versioned RANS closures first; transition/roughness/wall treatment and then resolved LES/hybrid methods where justified. | Exact closure/version/equations, wall-distance and positivity checks, NASA-style verification grids and matched validation cases, y-plus/wall-resolution and model-form uncertainty. Never infer a resolved turbulent spectrum from a steady RANS field. |
| CFD-05: rotating machinery | Rotor frames/MRF for bounded steady cases, then conservative ALE/sliding interfaces, moving boundaries, wakes and rotor/body interference. | Rigid rotation and geometric conservation; angular momentum, thrust/torque/shaft power, mesh/interface/time refinement, measured propeller curves with stated conventions. Drone/helicopter collective/cyclic pitch, ground effect and blade/vortex interactions require their own operating envelopes. |
| CFD-06: broader fluid regimes | Compressible conservative mass/momentum/total energy with admitted EOS; shocks, low-Mach conditioning, non-Newtonian liquids, free surfaces and cavitation in separate stages. | Acoustic speed, thermodynamic positivity, entropy/shock and low-Mach references; closure-specific interface/cavitation data. Each liquid/gas/phase model has explicit bounds; no universal all-fluid claim. |
| CFD-07: structural and mechanical loads | Spatially resolved pressure/shear with moments, material/part identity, conservative load transfer, dynamic structural state, joints/contact/friction and thermal deformation. | Resultant **and moment**/virtual-work preservation, dynamic energy and reaction forces; beam/plate/modal/contact references and time/mesh convergence. Static stress does not establish flutter, fatigue or impact accuracy. |
| CFD-08: strongly coupled FSI/aeroelasticity | Actual fluid/structure participants, time windows, checkpoints, rollback, interface iteration/acceleration and deformation-dependent mesh motion. | Added-mass stability, complete-window rollback, geometric conservation, energy/work and interface residuals, mesh/time/coupling convergence; independent flexible-body and flutter onset/frequency/damping references. Distinguish numerical instability from physical flutter. |

Heat exchangers require CFD-01/02 and often CFD-04. Car aerodynamics requires
CFD-01/03/04 with the relevant ground/wheel/wind-tunnel model. Propellers and
helicopters require CFD-05 and, for relevant tip regimes, CFD-06. Flexible wings,
blades and flutter additionally require CFD-07/08. A study graph must reject
missing participants instead of replacing them with an unexplained scalar gain.

## Cross-solver operational boundary

Use versioned study/mesh/material/interface identities, SI units, common or
explicitly transformed frames, and field meaning (intensive versus integrated).
Geometry hashes bind supplied data; they do not authenticate an overlap map.
Each participant retains its own convergence and applicability status. Existing
SU2/OpenFOAM/thermal/structural adapters can be independent references or future
participants; merely detecting those executables is not an executed coupling.

The present surface operator preserves global loads and its adjoint pairing,
but has no spatial quadrature coordinates and therefore **no moment claim**.
It does not turn heat flux times temperature into physical mechanical power.
Pressure must be converted to traction using admitted normals and a physically
consistent reference pressure; a zero-mean cavity gauge is not an absolute load
on an arbitrary open structural surface.

Transient coupling must own trial/accepted states, events, common time windows,
subcycling, residual scales and complete rollback. A participant that fails
cannot leave another participant advanced. The existing explicit-lag scalar
co-simulation service remains separate; it is not silently promoted to FSI.

## Method selection and reference corpus

Established conservation laws and independently authored implementations are the
baseline. Higher-order bounded transport, goal-oriented adaptivity, multigrid/
block preconditioning, conservative ALE and interface quasi-Newton methods are
candidates to compare at equal error and whole-workflow cost, not claims of new
implemented capability. Do not introduce learned closures as substitutes for
unverified governing equations or missing material data.

Primary resources reviewed for planning on 20 October 2026:

- NASA NPARC [validation assessment](https://www.grc.nasa.gov/WWW/wind/valid/tutorial/valassess.html)
  and [spatial convergence](https://www.grc.nasa.gov/WWW/wind/valid/tutorial/spatconv.html):
  application-specific measurements and separated iterative/grid/time checks.
  Root reviewed the assessment/building-block sections and grid-study discussion;
  these do not validate SPIKE.
- [preCICE coupling](https://precice.org/configuration-coupling) and
  [acceleration](https://precice.org/configuration-acceleration): official
  coupling/acceleration documentation identifies implicit iteration and stability
  considerations. Planning-level scope review only; no preCICE source or library
  is imported, and no quasi-Newton method is implemented by this increment.
- [UIUC propeller database](https://m-selig.web.engr.illinois.edu/props/propDB.html):
  reviewed public description of measured small-UAV propeller data and dataset
  conventions. Candidate later validation source; no measurements, geometry or
  external implementation copied or distributed here.
- NASA [AGARD 445.6 flutter study record](https://ntrs.nasa.gov/citations/20220017824):
  metadata/scope review only, a candidate benchmark family. No paper-method or
  flutter qualification claim; actual datasets, boundary conditions and rights
  must be reviewed before use.

See the precise implemented-method review and independent derivations in the
native CHT and surface-exchange records. Frontier work follows
[the method evidence policy](NUMERICAL_METHOD_EVIDENCE.md), including knowledgeable
human numerical review before release. This plan creates no new certification,
hardware prediction, production-release or commercial-parity claim.
