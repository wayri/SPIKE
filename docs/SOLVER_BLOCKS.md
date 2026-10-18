<!-- SPDX-License-Identifier: Apache-2.0 -->
# Solver blocks and bulk selection

SPIKE exposes individual logical solver/workflow blocks through the Python
worker method `solver_blocks`. Desktop clients present its dependency graph and
bulk domain selections. The catalog is authoritative in
`python/spike_core/solver_blocks.py`; the suite presentation index is checked for
complete one-to-one capability mapping by `tests/python/test_solver_blocks.py`.

## Current behavior

All implemented first-party solver, support and external-adapter code remains
included by default in the current monolithic payload. These logical blocks are
not independently downloadable or removable packages. Selecting blocks previews
a composition; it changes no files, registrations, enabled solvers or project
settings. Existing solver status, licenses, runtime admission, case limits and
validation gates remain authoritative. No numerical implementation changes here.

The domain sections are PCB, Harness, MCAD collaboration, Circuits, PI, SI, CFD,
CHT, Thermal, Electromagnetics, Structural mechanics, Execution and shared base.
The catalog contains 70 logical blocks. A block may belong to several sections. Domain bulk selection includes all
members, including visibly unresolved external or planned blocks; dependency
closure deduplicates overlaps. MCAD denotes simulation geometry collaboration,
not a general mechanical authoring application.

Required edges compose workflow prerequisites; optional edges describe useful
integration and never expand a selection. They are logical workflow boundaries,
not proof that Python imports or installer files have been physically isolated.
For example, assembly CHT requires solid thermal, shared mesh/material geometry
and the OpenFOAM cooling adapter with its separately admitted runtime.
The external thermal index offers optional CalculiX and OpenFOAM adapters; select
each concrete backend independently. CalculiX solid thermal does not require
OpenFOAM or imply CFD. FreeCAD export has its own bundled adapter and separate
external application/runtime requirement; generic MCAD exchange keeps it optional. The native isothermal cavity block
cannot substitute for a general solid/fluid CHT engine. Same-mesh thermoelastic
coupling requires both static mechanics and solid thermal. Mesh admission does
not automatically require a mesh generator when a reviewed mesh is supplied.

A generated `app/src/solverBlockCatalogSnapshot.json` makes the index available
before a desktop worker connects. It is a bundled, unprobed metadata snapshot;
selection plans still come from the Python worker. The snapshot must equal the
Python default catalog in tests. Regenerate it in a UTF-8 shell with
`.venv/Scripts/python.exe -m python.spike_core.solver_blocks > app/src/solverBlockCatalogSnapshot.json`
(or write the JSON using Python to avoid legacy shell output encodings).

## Worker contract and recovery

Request example:

```json
{"method":"solver_blocks","params":{"selected_groups":["harness","thermal"],"selected_blocks":["mechanics-thermoelastic"]}}
```

The result has contract `spike/solver-blocks/v1`, `packaging_mode: bundled_all`,
`managed_downloads: false`, `catalog_version`, `groups`, `blocks` and `plan`.
`catalog_version` is `spike_core.__version__`: all logical blocks version together
with the shared SPIKE release today. It is not an independent per-block binary
version. Future individually shipped packages must pin their own versions and ABI
compatibility separately. The solver-manager
catalog also exposes this complete result under `blocks`.

Every block declares `id`, `name`, `groups`, `requires`, `optional`,
`capability_ids`, `delivery` and `description`. External runtime descriptors add
`external_requirements`. Delivery means bundled first-party code, a separately
obtained external runtime, or planned/unavailable work. An adapter can be bundled
while its required engine is external. Neither state asserts local readiness.

Omitting both selection fields selects every bundled first-party block. Passing
an explicit empty array selects only mandatory `core`. Providing either field
uses the union of explicit IDs and group members, then adds mandatory base and
transitive required dependencies. Order is deterministic and dependencies precede
their consumers. `requested_blocks` records the union, `required_blocks` the
added closure and `ordered_blocks` the whole plan. `blocked_blocks` includes
external/planned entries and consumers of blocked required prerequisites.

This is a conservative composition preview: external runtimes remain unresolved
even if installed locally because this method performs no availability probe.
Use the existing engine manager and workflow-specific admission for readiness.
`warnings` explains these limits and `action` is always `preview_only`. There
is no download, installation, uninstall or automatic execution operation.

Unknown IDs, unknown parameters, malformed selection arrays, duplicate catalog
IDs, unknown dependencies and graph cycles fail closed. Worker validation errors
use the canonical IPC error envelope; correct the selection and retry. Both
required and optional edges are checked for cycles across the entire catalog.

## Future distribution boundary (not implemented)

A future minimal base plus optional solver downloads can reuse these IDs only
after real archive/import boundaries and installer/in-app management exist.
Each independently shipped block needs its own version, dependency version
constraints, base-program compatibility and ABI/API contract, platform and
architecture adapters, entry points, capabilities, and exact file ownership.
Python/native/library compatibility must be resolved together before staging.

Each archive manifest must identify immutable contents, sizes, cryptographic
hashes, signed publisher/provenance metadata and trusted verification keys. It
must include an SBOM, licenses, notices and redistribution permissions for all
payloads. First-party adapters do not grant engine redistribution rights;
external engines remain separately licensed and separately admitted. Planned
blocks must remain noninstallable until implemented and accepted.

Installer and in-app bulk workflows must call one dependency resolver and expose
required versus optional edges and unsupported platform combinations before
execution. Download to bounded staging, verify signatures/hashes and archive
paths, validate compatibility and licenses, then atomically activate the whole
resolved set with rollback to the previous known complete state. Keep interrupted
or rejected staging inert; prevent concurrent activation conflicts. Uninstall
must refuse removal of required dependencies or explicitly include dependents.
Test clean-machine/offline, interrupted downloads, corruption, failed activation,
upgrade, rollback and uninstall on each supported platform before enabling
managed downloads. No such release readiness is claimed by this preview.

## Catalog edges

`-` means no additional edge. All bundled entries describe code inclusion only.
Existing bounded capability descriptions remain in the solver suite and
[SOLVER_STATUS.md](SOLVER_STATUS.md).

| Block ID | Delivery | Required blocks | Optional blocks |
| --- | --- | --- | --- |
| core | bundled | - | - |
| geometry | bundled | core | - |
| materials | bundled | core | - |
| mesh | bundled | geometry | - |
| pcb-adapter | bundled | geometry | - |
| harness-adapter | bundled | geometry, materials, si-networks | pi-dc |
| mcad-adapter | bundled | geometry | mesh, mcad-freecad |
| mcad-freecad | bundled | geometry, external-freecad | - |
| thermal-calculix | bundled | mesh, materials, external-calculix | - |
| thermal-openfoam | bundled | mesh, materials, external-openfoam | - |
| cht-assembly | bundled | thermal-solids, mesh, materials, thermal-openfoam | - |
| pi-solid-dc | bundled | mesh, materials | - |
| pi-transient | bundled | pi-peec, circuit-native | - |
| mechanics-static | bundled | mesh, materials | - |
| mechanics-thermoelastic | bundled | mechanics-static, thermal-solids | - |
| planned-mom | planned | core | - |
| circuit-native | bundled | core | - |
| circuit-adaptive | bundled | circuit-native | - |
| circuit-equations | bundled | circuit-native | - |
| circuit-physics-parts | bundled | circuit-equations | - |
| circuit-smps | bundled | core | - |
| circuit-battery | bundled | core | - |
| circuit-libraries | bundled | circuit-native | - |
| circuit-pdk | bundled | core, external-ngspice | - |
| circuit-asic | bundled | core, external-klayout | - |
| circuit-tcad | bundled | core | - |
| pi-dc | bundled | pcb-adapter, materials | - |
| pi-peec | bundled | pi-dc | - |
| pi-pdn | bundled | core | - |
| pi-capacitance | bundled | mesh, materials | - |
| pi-dielectric-ac | bundled | pi-capacitance | - |
| pi-reduction | bundled | pi-dielectric-ac | - |
| pi-engineering | bundled | core | - |
| si-networks | bundled | core | - |
| si-channels | bundled | pcb-adapter, si-networks, materials | thermal-board |
| si-eye | bundled | si-networks | - |
| thermal-board | bundled | pcb-adapter, materials | - |
| thermal-solids | bundled | mesh, materials | - |
| thermal-electrothermal | bundled | thermal-solids, pi-solid-dc, pi-pdn | - |
| thermal-pwm | bundled | thermal-solids, circuit-native | - |
| thermal-channel | bundled | materials | - |
| cfd-native | bundled | core | - |
| cfd-su2 | bundled | core, external-su2, mesh, materials | - |
| thermal-external | bundled | core | thermal-calculix, thermal-openfoam |
| em-magnetic | bundled | mesh, materials | - |
| em-lumped | bundled | materials | - |
| em-openems | bundled | core, external-openems, mesh, materials | - |
| em-palace | bundled | core, external-palace, mesh, materials | - |
| circuit-xyce | bundled | core, external-xyce | - |
| execution-cosim | bundled | core | circuit-native, thermal-solids, cfd-native |
| execution-workers | bundled | core | - |
| execution-extensions | bundled | core | - |
| em-emerge | bundled | core, external-emerge, mesh, materials | - |
| execution-gmsh | bundled | core, external-gmsh, mesh, materials | - |
| execution-sparselizard | bundled | core, external-sparselizard, mesh, materials | - |
| planned-elmer | planned | core | - |
| planned-fullwave | planned | core | - |
| planned-tcad | planned | core | - |
| external-calculix | external | core | - |
| external-emerge | external | core | - |
| external-freecad | external | core | - |
| external-gmsh | external | core | - |
| external-klayout | external | core | - |
| external-ngspice | external | core | - |
| external-openems | external | core | - |
| external-openfoam | external | core | - |
| external-palace | external | core | - |
| external-sparselizard | external | core | - |
| external-su2 | external | core | - |
| external-xyce | external | core | - |

## Verification

Run `.venv/Scripts/python.exe -m unittest tests.python.test_solver_blocks -v`.
The checks cover default/all and empty/base selection, group unions, dependency
ordering, optional exclusion, CHT cross-domain dependencies, unresolved engines,
planned blocks, invalid graphs/IDs, presentation mapping and worker dispatch.
