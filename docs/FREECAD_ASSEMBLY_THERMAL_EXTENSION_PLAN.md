# FreeCAD assembly and thermal extension

Status: proposed extension design, 2026-09-07. This document adds a development
plan; it does not enable interactive synchronization or a FreeCAD thermal solver.

Implementation update: [companion 0.2.0](FREECAD_COLLABORATION.md) now provides
explicit assembly sessions, reviewed label/placement feedback and pairwise solid
clearance measurements. Structural synchronization, harness route exchange and
the thermal milestones below remain planned.

SPIKE should offer an optional FreeCAD companion for interactive mechanical
assembly, board positioning, enclosure/package design, STEP integration and
harness routing. SPIKE establishes the engineering scenario; FreeCAD handles
mechanical editing and optional simulation preparation/execution; SPIKE receives
reviewable assembly changes and numerical results for visualization and probing.
SPIKE's internal simulation and rendering remain independently usable.

## Existing foundation and remaining work

| Foundation | What the extension adds |
| --- | --- |
| [FreeCAD workbench](../integrations/freecad/README.md): primitive import, envelope export and selected assembly STEP export | Import a complete SPIKE assembly into an editable session, retain occurrence identities, publish changes back |
| [MCAD extension](../extensions/mcad-export/spike-extension.json): STEP/FCStd/BREP export and metadata | Interactive handoff and durable collaboration sessions |
| [Assembly and harness workflow](MULTIBOARD_HARNESS_ASSEMBLIES.md): board occurrences, connector mappings, routes and `.spikeassembly` import | Update existing occurrences, reconcile edits, return harness route changes |
| [Thermal workflow](THERMAL_WORKFLOW.md) and [field result contract](../schemas/thermal-field-result-v1.schema.json) | Equivalent PCB material generation, FreeCAD FEM adapter, mapped external field import |

The current assembly importer remaps incoming IDs into a destination project.
That is useful for adding an assembly, but is not an update/synchronization
protocol. The current FreeCAD assembly exporter also uses document object names
and does not export the full SPIKE thermal or harness scenario.

## User workflow

1. In SPIKE, select **Open assembly in FreeCAD**. Choose boards, components,
   mechanical parts and harnesses; review unavailable geometry. Save an immutable
   project snapshot and create a durable collaboration session.
2. Open the companion workbench. Arrange board instances, assemble STEP parts,
   create or modify the package, and edit cable paths and connector exit frames.
   Native FreeCAD constraints and feature history stay in the FCStd document.
3. Choose **Send assembly changes to SPIKE**. SPIKE displays moved/added/deleted
   occurrences, changed geometry and routes, and unresolved references. Apply
   selected changes as one undoable project transaction.
4. In SPIKE thermal setup, choose board fidelity, component power, thermal
   contacts, enclosure materials, ambient conditions, boundary conditions,
   steady/transient mode and resource budget. Preview the simplified model.
5. Choose **Prepare in FreeCAD**. The workbench creates the simulation geometry,
   material assignments, source/contact mappings and supported FEM setup. The
   user can inspect and adjust the setup there. Such edits create a new scenario
   revision that returns with the results; they cannot silently reuse the old one.
6. Choose **Run thermal analysis** in the FreeCAD companion. It executes the
   selected, qualified backend and publishes progress, logs and result artifacts.
   A later SPIKE command may dispatch the same prepared job through the host.
7. Import results into SPIKE for temperature/heat-flux overlays, section views,
   component inspection, point probes, time histories and scenario comparison.
   Associate each result with the exact assembly and thermal-model revision.

File exchange is the first transport. A later local live connection can offer
change notifications and explicit refresh using the same contracts. Closing
either application must not lose the saved session or a completed result.

## Ownership and round-trip contract

SPIKE owns electrical board identity, connectivity, source component placement,
analysis intent and accepted project revisions. FreeCAD owns mechanical feature
history, mates and the editable assembly document. Export solved rigid placements
and neutral geometry; SPIKE need not implement FreeCAD's constraint solver.

Moving an entire board occurrence changes its assembly transform. Moving a
component relative to its PCB is a proposed ECAD change requiring reconciliation
with its source design; it cannot silently change copper connectivity. STEP-only
boards remain mechanical proxies unless explicitly bound to electrical sources.

Introduce a separately versioned session/change-set contract around existing
geometry and assembly assets. Do not insert new fields into strict v1 contracts.
Proposed records include:

- Project/session IDs, baseline project and asset digests, source and destination
  revisions, and an idempotent change-set ID.
- Persistent occurrence IDs independent of FreeCAD labels/object names;
  separate shared geometry IDs and board design IDs. Repeated boards have
  distinct occurrence IDs and occurrence-qualified component/connector IDs.
- Parent-relative proper rigid transforms: existing row-major 4x4 convention,
  millimetres, right-handed Z-up. Record the board-local frame explicitly.
- Explicit additions, updates, deletions, reparenting and geometry replacements;
  original and proposed values sufficient for a three-way comparison.
- Harness IDs, board/connector/pin endpoints, cable exit frames, path geometry,
  diameter and bend-radius intent, and separately recorded routed and cut lengths.
- Thermal region/contact IDs and mappings to source objects, including geometry
  digests. Face numbers alone are insufficient after CAD topology changes.

Match updates by persistent IDs. Resolve concurrent changes against the baseline;
show conflicts rather than letting the last writer silently win. An unchanged
reimport is a no-op. Validate the entire change set before atomic application.
Changing placement or topology invalidates affected routes, face references,
meshes and results. Preserve old results against their original snapshot.

Cable geometry does not establish connectivity, current rating or thermal
conductance. Preserve explicit pin maps. If cable heat transfer is requested,
require an admitted conductor/insulation model or explicit thermal network links.

## User-selectable thermal fidelity

| Option | Representation | Intended use and limitations |
| --- | --- | --- |
| Compact network | Board/component/package nodes with thermal resistance and capacitance | Fast temperature estimates; produces node values, not a resolved 3D field |
| Equivalent PCB solid | Board outline/thickness with effective directional conductivity and heat capacity; explicit component bodies and thermal links | First external field target; board-scale heat spreading with reduced mesh size |
| Layered or zoned PCB | Separate dielectric/copper-equivalent layers or spatial zones; selected via-rich regions | Captures regional copper variation; costs more to mesh and solve |
| Detailed selected geometry | Explicit copper/vias and selected package/contact detail | Local hotspot studies after geometry and mesh qualification; whole-board detail is optional |

Fidelity may differ by board or region in one assembly. Keep source geometry and
simulation geometry separate, with a visible mapping and omissions list. A
failed detailed mesh may offer a simpler model, but switching requires an
explicit user choice and creates a new analysis revision.

An equivalent PCB should normally be anisotropic: copper planes spread heat
along the board much more readily than through dielectric thickness. Start with
the following ideal laminate derivation, not an empirical promise of accuracy.
For continuous perfectly bonded layers of thickness `t_i`, total thickness `t`,
conductivity `k_i`, density `rho_i` and specific heat `cp_i`:

```text
f_i = t_i / t
k_parallel = sum(f_i * k_i)              # parallel heat-flow paths
k_through  = 1 / sum(f_i / k_i)          # series heat-flow path
rho_eff   = sum(f_i * rho_i)
(rho*cp)_eff = sum(f_i * rho_i * cp_i)
cp_eff = (rho*cp)_eff / rho_eff
K_local = diag(k_parallel, k_parallel, k_through)
K_assembly = R * K_local * transpose(R)
```

Use SI units for material calculations. Patterned copper cannot be assigned a
unique conductivity from coverage alone: disconnected islands and continuous
planes at the same fill fraction conduct differently. Record copper coverage,
connectivity assumptions, stackup sources and any manual overrides; use bounded
estimates/sensitivity studies or a qualified cell model when topology matters.
Via-enhanced through-thickness paths need an explicit equivalent model and must
not also be counted as separate conductors. Missing stackup/material information
requires a visible estimate or user input, not an undisclosed FR-4 default.

Retain component location, orientation, power and footprint/contact area.
Represent package-to-board, package-to-heatsink, TIM, fastener and enclosure
connections explicitly. Distinguish lumped resistance `R` in K/W from areal
resistance `R''` in m2 K/W (`R = R'' / A`). A package surface temperature is not a
junction temperature unless a corresponding internal package model exists.
Do not substitute datasheet junction-to-ambient resistance for a universal
package-to-board contact. Preserve total applied power when distributing sources.

The first field workflow uses solid conduction with prescribed-temperature or
specified convection-coefficient boundaries. A prescribed coefficient does not
solve airflow. Radiation, buoyancy, fans and conjugate heat transfer are separate
capabilities and follow only when the chosen adapter supports and qualifies them.

## Extension and solver boundaries

Build on the existing MCAD export services and FreeCAD workbench, packaged as an
optional companion extension. Use the [extension architecture](EXTENSION_ARCHITECTURE.md)
for commands, preparation, exchange and structured panels. Use the
[solver boundary](SOLVER_PLUGIN_ARCHITECTURE.md) for numerical execution and
the existing thermal field job/result contracts wherever their semantics fit.

FreeCAD is the interactive model/setup host; the numerical backend has its own
identity and version. FreeCAD documents built-in assembly support and FEM support
for Elmer and CalculiX. Elmer is a candidate for the thermal adapter; installation
alone does not demonstrate that SPIKE can translate anisotropic materials,
contacts, sources and results correctly. Qualify those capabilities individually.
See [FreeCAD assembly documentation](https://github.com/FreeCAD/FreeCAD-documentation/blob/main/wiki/Assembly_Workbench.md)
and [FreeCAD FEM introduction](https://blog.freecad.org/2025/09/16/getting-started-with-fem/).

Keep the interactive FreeCAD application outside the extension invocation's
short-lived temporary directory and timeout. A trusted host launcher manages
session paths; bounded preparation/solve jobs have separate cancellation and
resource controls. Extension discovery must not launch FreeCAD. Do not add an
executable public package until the existing distribution/trust rules admit it.

Geometry fragments created for meshing must retain material and source ownership.
If a backend needs one conformal mesh, construct a simulation compound with
labeled interfaces; do not fuse away contact resistance or material boundaries.
Capability checks must reject an unsupported conductivity tensor rather than
silently replacing it with an isotropic scalar.

## Results returned to SPIKE

Normalize external results to the existing thermal field result envelope, with
adapter-specific validated data under its permitted fields. Add a new contract
version if required semantics cannot be represented without changing v1 meaning.
Retain full mesh/field artifacts and digest-bound provenance containing:

- Session, assembly, scenario, simplified-model, mesh and job identities/digests;
  FreeCAD, adapter, mesher and actual solver versions.
- Per-region source ownership and per-array location (node/cell/face), units,
  coordinate frame, vector basis and time values. Convert units exactly once.
- Temperature in K, heat flux in W/m2, explicitly defined component statistics
  and contact heat rates in W when supplied by the solver.
- Approximation parameters, omitted physics, material sources, convergence,
  energy-balance and mesh/time-refinement evidence, warnings and execution status.

Keep numerical convergence separate from physical-model fidelity: a converged
equivalent-board calculation remains approximate. Map nonconvergence to the
existing supported status/issue semantics, without inventing a new v1 enum.

Overlay only after identity, units, transforms and field ownership validate.
Unmapped results can remain inspectable artifacts. A result for an older assembly
opens on its saved geometry, not the current board positions. Rendering may use
a bounded preview, but numerical probes and statistics use the full result data;
label interpolation and return unavailable outside the solved domain. Compare
different meshes only through an explicit spatial/object mapping.

## Delivery order and acceptance

1. **Assembly round trip:** durable session and change-set schemas; stable IDs;
   full assembly import in the workbench; preview/apply in SPIKE. Demonstrate
   two instances of one board, nested rotated parts, one new STEP housing and a
   harness. Verify no-op reimport, rename, deletion, reparenting, concurrent edits
   and unchanged electrical sources. Declare qualified FreeCAD versions.
2. **Equivalent PCB preparation:** typed material/contact model, fidelity selector,
   simplification preview and source map. Verify ideal laminate limits, rotated
   tensors, heat-capacity and power conservation, plus rejection of invalid or
   missing properties. Export an inspectable FreeCAD analysis without claiming
   that preparation ran a solver.
3. **First thermal round trip:** a qualified steady conduction adapter and result
   importer. Solve analytic slab/contact fixtures and a two-board enclosure
   example; check energy balance, mesh refinement, units, field mapping, probing,
   cancellation and stale-result handling. Publish fixture-specific tolerances
   before accepting results. Test an installed FreeCAD/backend, not only mocks.
4. **Expanded physics and editing:** transient conduction, zoned copper/vias,
   richer harness geometry, supported radiation/airflow adapters and optional
   local change notifications, each with its own capability/validation evidence.

The first useful release is interactive assembly feedback followed by approximate
solid thermal results in SPIKE. General enclosure CFD and detailed PCB copper
meshing are subsequent capabilities, not prerequisites for the companion.
