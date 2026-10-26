<!-- SPDX-License-Identifier: Apache-2.0 -->
# Solver code and documentation directory

This directory organizes SPIKE's solver implementation by physical domain and
shared responsibility. Implementations now live under
[`python/spike_core/solvers/`](../../python/spike_core/solvers/README.md) and
[`src/solvers/`](../../src/solvers/README.md), with domain/subgroup packages.
Application services and command entry points remain at their existing boundary.
Worker contracts, mathematical laws and numerical tolerances are unchanged.

## Completion states

[Every catalog capability: completion, integration and remaining work](completion.md)
contains all 60 entries. Each domain guide also labels its internal solver and
supporting subgroups. States are bounded implementation assessments; physical
validation, case convergence and release acceptance remain separate. No completion
percentage or universal accuracy claim is inferred.

## Domains and subgroups

| General heading | Subgroups | Implementation guide |
| --- | --- | --- |
| Circuits and semiconductor reference | MNA; nonlinear devices; transient/switching; controllers; reduced parts; equilibrium TCAD | [Circuits](circuits/README.md) |
| Power integrity | Graph DC; conservative contacts/volumes; PEEC; dielectric fields; PDN screening | [Power integrity](power-integrity/README.md) |
| Signal integrity | Geometry extraction; distributed lines; sampled networks; transients; eyes and receiver references | [Signal integrity](signal-integrity/README.md) |
| Thermal and fluid flow | Lumped/structured/tetrahedral heat; channels; cavity/enclosure; creeping-flow CHT | [Thermal and CFD](thermal-fluid/README.md) |
| Electromagnetics and machines | Reduced machines; planar FEM; radiation operators; propulsion research | [EM and machines](electromagnetics/README.md) |
| Solid mechanics | Static elasticity; same-mesh thermoelasticity | [Mechanics](mechanics/README.md) |
| Geometry and discretization | Topology; current bases; structured/unstructured mesh preparation and admission | [Geometry and meshes](geometry-meshing/README.md) |
| Execution and coupling | Setup; worker boundaries; multiphysics exchange; pools; CPU/GPU acceleration | [Execution](execution/README.md) |
| External engines | Circuit, EM, thermal/CFD runtimes; mesh/CAD tools; unavailable connectors | [External engines](external-engines/README.md) |

## Find a setup, method or evidence record

- [Generated capability map](../SOLVER_INTEGRATION.md): exact capability IDs,
  current desktop destinations and source/API-only or unavailable routes.
- [Solver status](../SOLVER_STATUS.md): executable scope and dated validation limits.
- [Solver mathematics](../SOLVER_MATHEMATICS.md): equations, units, discrete
  operators, boundary conditions and detailed method owners.
- [Solver handbook](../SOLVER_HANDBOOK.md): interpretation and verification.
- [Block catalog](../SOLVER_BLOCKS.md): dependencies; grouping is not a dependency graph.
- [Numerical evidence policy](../NUMERICAL_METHOD_EVIDENCE.md): independently
  authored derivations, reviewed primary references and required acceptance evidence.
- [Subsystem index](../SUBSYSTEM_INDEX.md): additional ownership and recent increments.

The capability map includes supporting workflows and plans as well as numerical
solvers. Its entry count is not a count of independent qualified physics engines.
These guides also include public internal references that have no desktop capability.
Unpublished research is excluded from the public tree by a separate publication gate.

## Source layers

| Layer | Responsibility |
| --- | --- |
| `src/solvers/` | Native numerical kernels grouped by domain and subgroup |
| `python/spike_core/solvers/` | Numerical/reference modules, model preparation, adapters and coupling grouped by domain and subgroup |
| `python/spike_core/` | Stable application contracts, services, registries and command entry points |
| `extensions/` | Separately admitted external engine workflows |
| `schemas/` | Versioned request/result contracts |
| `app/src/` | Setup, capability discovery and result presentation |
| `tests/python/`, `tests/`, `docs/validation/` | Regression owners and retained executed evidence |

Start at the domain guide, follow its source link, then inspect the corresponding
service/contract and test before changing behavior. UI availability, adapter
registration, engine installation and physical qualification are separate states.

## Accuracy and resource interpretation

An algebraic residual measures the discrete solve. Mesh/timestep/domain/bandwidth
refinement measures sensitivity to discretization. Independent comparisons and
measured correlation address different model errors. No family has a universal
accuracy percentage; tolerances and validity must come from the specific study.
Historical validation links do not assert a fresh execution or qualify later edits.

Lumped graphs and analytic lines avoid a volume mesh but still have topology,
parameter and sampling assumptions. PEEC uses a finite current basis. Spatial
FEM/FV/mixed methods require admitted geometry and resolution studies. These are
not evidence of a general meshfree PDE solver.

CPU threading, independent local/LAN jobs, optional CUDA sparse solves and future
single-domain MPI execution have distinct coverage; consult the execution guide.

## Maintaining this organization

Add new owners to the appropriate subgroup, linking code, setup and evidence.
Preserve experimental, approximate, unsupported and failed-to-converge states.
Update the existing capability/block catalogs through their established sources;
do not manually edit generated indexes or promote a plan into a working solver.
The [source-layout manifest](source-layout.json) records the exact former and
canonical paths. Read [the migration decision](../adr/0145-solver-source-layout.md)
for verification, source-identity consequences and publication exclusions.
Run `python scripts/verify_solver_layout.py` after further moves. Old source-bound
receipts and frozen workers are historical evidence, not proof of the new layout.
