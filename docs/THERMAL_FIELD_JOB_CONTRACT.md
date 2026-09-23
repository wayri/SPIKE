# Thermal Field Job Contract

`spike/thermal-field-job-request/v1` is the fail-closed planning boundary for
field-thermal plugins. A user selects one concrete solver ID; SPIKE never
substitutes another engine. The plan records solid/transient conduction,
contacts, material/coating, heat-source, package/MCAD, enclosure/heatsink/fan,
potting, radiation/vacuum, airflow/CHT, and electro-thermal requests together
with geometry evidence, resource limits, and cancellation polling.

The planner is not a solver. It emits no temperature field and permits
execution only when the selected plugin is runnable, declares every requested
capability, receives qualified geometry/contact evidence, and supplies valid
`spike/thermal-solver-qualification-evidence/v1`. That evidence binds the exact
solver ID/version and fixture/result digests and must cover the requested
physics, conservation, mesh convergence, independent-solver correlation,
measured correlation, and Windows/Linux release packages. A self-declared
`validated` label is insufficient. Existing OpenFOAM and lumped-network routes
remain separately bounded experimental/approximate capabilities.

Every eventual adapter must consume the exact plan digest, honor the CPU/RAM,
cell, and output-sample budgets, poll cancellation, and return a strict
`spike/thermal-field-result/v1` result with solver, mesh, geometry, and
qualification provenance. A failed or cancelled adapter must not return a
partial field result.

## Execution boundary

The worker-owned host calls
`execute_thermal_field_job(request, adapter_registry=..., solver_catalog=...)`.
The selected registry entry must expose `probe()` and `run(invocation)`; the
fixed-argv runtime probe must return `spike/solver-plugin-probe-result/v1` with
`status: passed`. The invocation contains the plan digest, admitted scenario,
geometry evidence, requested physics, and resource budget. Neither an IPC
client nor a project file may provide the adapter or modify its capability
claims.

For large results, `fields.*.samples` is a bounded render preview. Each field
also records `preview_samples` and `total_samples`; when these differ, a
digest-bound `{id, sha256, bytes, contract}` artifact record is mandatory. The
result-level `resource_usage` distinguishes total field samples from rendered
preview samples. Failed, blocked, cancelled, over-budget, or non-converged
adapter calls return an empty `fields` object.

Electro-thermal operation is an explicit bounded fixed-point loop. It requires
an enabled scenario, a thermal adapter supplying component temperatures, and a
host-owned electrical-step adapter returning every admitted heat-source power.
There is no implicit power update or inferred device loss; absent, malformed,
or non-convergent coupling fails closed without a partial field result.

## OpenFOAM v2606 multi-region boundary

The OpenFOAM CHT route is a separately admitted implementation of this
contract, not an implicit fallback. It accepts only a
`spike/openfoam-multiregion-runnable-case/v1` manifest whose input-file digests,
neutral-to-`polyMesh` materialization digests, region identities, and patch
ownership all verify. The host probes the exact v2606 `checkMesh`,
`chtMultiRegionFoam`, and `postProcess` commands before launch, plus
`faceAgglomerate` and `viewFactorsGen` for view-factor regions, then runs
`checkMesh -allRegions -allTopology -allGeometry` before CHT.

After a completed CHT process, SPIKE obtains cell centres, cell volumes,
`grad(T)` through a safe case-owned `gradT` alias, and declared external-patch
`wallHeatFlux` records for every
region, derives heat flux only from declared region conductivity, and requires
aligned T/q arrays for solids and aligned C/T/q/U/p arrays for fluids. Source
terms are bound to materialized `cellZones`. Enclosure exchange uses explicit
`viewFactorWall` mesh groups and both v2606 preprocessors. Vacuum heat rejection
uses a solid-only `externalWallHeatFluxTemperature` boundary with zero
convection, explicit background temperature, emissivity, and exact mesh-bound
surface evidence; pseudo-fluid vacuum regions are rejected.

For WSL transports the Windows Job allows the finite helper-process set needed
by `wsl.exe`, while fixed-argument Linux `prlimit` applies the requested solver
address-space, CPU-time, and file-size budgets. This avoids the former false
startup failure caused by imposing a one-process Windows Job limit on WSL and
does not remove cancellation or hard resource bounds.
The normalized result remains `experimental`, binds the runnable manifest and
field-export digests, and returns no fields on a failed, cancelled, partial, or
malformed import. Passing this execution/import boundary neither establishes
independent/measured correlation nor satisfies Windows/Linux package identity
qualification.

## Public technical basis

The adapter boundary follows published solver concepts without copying solver
implementation code. OpenFOAM documents `chtMultiRegionFoam` as a transient
multi-region fluid/solid conjugate-heat-transfer solver with separate required
fluid and solid temperature fields:
<https://doc.openfoam.com/2306/tools/processing/solvers/rtm/heat-transfer/chtMultiRegionFoam/>.
Elmer FEM's current public 26.2 release and `HeatSolver`/`HeatSolveVec` sources
remain the authoritative basis for any future Elmer adapter:
<https://github.com/ElmerCSC/elmerfem/releases/tag/release-26.2> and
<https://github.com/ElmerCSC/elmerfem/blob/devel/fem/src/modules/HeatSolve.F90>.
These references establish available upstream concepts only; SPIKE still
requires its own case translator, result importer, fixtures, correlation, and
license review before enabling either workflow.

OpenFOAM v2606 is the current runtime basis used by the local probe. Its
official release record and preprocessing notes document the June 2026 release
and the multi-region `splitMeshRegions` workflow:
<https://www.openfoam.com/download/release-history> and
<https://www.openfoam.com/news/main-news/openfoam-v2606/pre-processing>.
SPIKE's translator and evidence gate are clean-room integration code; no
third-party solver implementation is copied into SPIKE.
