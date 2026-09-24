# SPIKE Error Code Catalog

This is the issued-code catalog for contract `spike/error/v1`. Code grammar,
handling policy, and contribution rules are defined in `ERROR_HANDLING.md`.
Catalog metadata is immutable after publication; event-specific data belongs
in the envelope message and safe context.

## Use the catalog

1. Search this page for the complete code, including its four-digit sequence.
2. Read the issued title and recovery action from the matching row.
3. Use the domain index below for the longer symptom-first task sequence.
4. Preserve the code, operation ID, versions, and model status when escalating.

Do not infer numerical validity from the classification. `I`, `W`, `P`, `E`,
`C`, and `S` classify operational diagnostics; result model status and
convergence remain separate fields.

### Code anatomy

`SPIKE-BE-SOLVER-E-0002` reads as:

| Segment | Meaning |
|---|---|
| `SPIKE` | Product namespace |
| `BE` | Backend/local worker origin (`FE` is frontend/interface) |
| `SOLVER` | Remedy-owning domain |
| `E` | Recoverable or terminal error classification |
| `0002` | Immutable sequence within the origin/domain/class group |

### Domain recovery index

| Domain | Detailed recovery | Preserve before retry |
|---|---|---|
| `APP` | [Application operation fails](../TROUBLESHOOTING.md#application-operation-fails), [critical failure](../TROUBLESHOOTING.md#unexpected-critical-failure) | Code, operation ID, safe detail, application/worker version |
| `IPC` | [Worker unavailable or busy](../TROUBLESHOOTING.md#worker-unavailable-or-busy) | Request method, operation ID, desktop/worker versions |
| `PROJECT`, `PACKAGE` | [Project will not open or save](../TROUBLESHOOTING.md#project-will-not-open-or-save) | Package path, integrity diagnostic, approved destination |
| `IMPORT` | [Import fails or quality is low](../TROUBLESHOOTING.md#import-fails-or-import-quality-is-low) | Source path, format hint, import diagnostics |
| `VIEW` | [Viewport recovery](../TROUBLESHOOTING.md#viewport-is-slow-blank-or-misaligned) | View mode, visible detail, GPU/WebView information |
| `MESH` | [Mesh warning or budget failure](../TROUBLESHOOTING.md#mesh-warning-or-resource-budget-failure) | Geometry issue, mesh policy, terminal mapping, limits |
| `SOLVER` | [Solver availability](../TROUBLESHOOTING.md#solver-is-unavailable), [execution/convergence](../TROUBLESHOOTING.md#solver-fails-to-converge-or-exceeds-a-budget) | Request, solver descriptor, residual/convergence detail, limits |
| `PI` | [PI candidate and loop extraction](../TROUBLESHOOTING.md#pi-candidate-and-loop-extraction-fails) | Endpoint/return mapping, candidates, frequency grid, provenance |
| `SPICE` | [SPICE recovery](../TROUBLESHOOTING.md#spice-workspace-or-model-is-rejected) | Workspace/model identity, anchor mappings, resource limits |
| `EXT` | [External engines](../TROUBLESHOOTING.md#external-engine-cannot-run) | Registration, trusted runtime identity, process diagnostics |
| `REPORT` | [Report recovery](../TROUBLESHOOTING.md#report-generation-or-export-fails) | Result/provenance identity, preview state, approved destination |

### Maintainer ownership index

The domain identifies the subsystem that owns diagnosis and remediation. Use
this index to reach the primary emission and boundary code; individual catalog
entries remain the stable public interface and source line numbers may change.

| Code prefix | Primary implementation owner |
|---|---|
| `SPIKE-FE-APP-*` | [`app/src/App.tsx`](../app/src/App.tsx) and the feature component that initiated the operation |
| `SPIKE-FE-IPC-*` | [`app/src/workerBridge.ts`](../app/src/workerBridge.ts) and [`app/src-tauri/src/lib.rs`](../app/src-tauri/src/lib.rs) |
| `SPIKE-FE-VIEW-*` | [`app/src/BoardViewport.tsx`](../app/src/BoardViewport.tsx) |
| `SPIKE-BE-PI-*` | [`python/spike_core/dc_solver.py`](../python/spike_core/dc_solver.py) and [`python/spike_core/hybrid_dc_solver.py`](../python/spike_core/hybrid_dc_solver.py) |
| `SPIKE-BE-MESH-*` | [`python/spike_core/preflight.py`](../python/spike_core/preflight.py) and [`python/spike_core/hybrid_mesh.py`](../python/spike_core/hybrid_mesh.py) |
| `SPIKE-BE-SOLVER-*` | The selected solver module under [`python/spike_core`](../python/spike_core) plus the process boundary in [`python/spike_worker.py`](../python/spike_worker.py) |
| `SPIKE-BE-SPICE-*` | SPICE request, model, and coupling modules under [`python/spike_core`](../python/spike_core) |
| `SPIKE-BE-EXT-*` | External-engine adapters under [`python/spike_core`](../python/spike_core) and native launch policy in [`app/src-tauri/src/lib.rs`](../app/src-tauri/src/lib.rs) |

Every new emitted code must be registered in
[`python/spike_core/errors.py`](../python/spike_core/errors.py), covered by a
focused test, and linked to a recovery procedure before merge.

Domains defined by the grammar but absent below have no issued codes in this
catalog revision. A syntactically valid code is not actionable unless it has an
issued entry.

### Catalog sections

- [Frontend codes](#frontend-codes)
- [Backend codes](#backend-codes)
- [Classification index](#classification-index)
- [Reserved policy](#reserved-policy)

## Frontend Codes

| Code | Title | Recovery |
|---|---|---|
| `SPIKE-FE-APP-I-0001` | Operation status | No action is required. |
| `SPIKE-FE-APP-W-0001` | Frontend operation warning | Review the associated object and suggested recovery before continuing. |
| `SPIKE-FE-APP-E-0001` | Frontend operation failed | Review the operation details, correct the input, and retry. |
| `SPIKE-FE-APP-C-9999` | Unexpected frontend failure | Preserve the diagnostic record and restart SPIKE. |
| `SPIKE-FE-IPC-E-0001` | Worker unavailable | Restart the worker or application, then retry. |
| `SPIKE-FE-IPC-E-0002` | Malformed worker response | Preserve diagnostics and verify component versions. |
| `SPIKE-FE-VIEW-P-0001` | Viewport performance degraded | Reduce visible detail or use a lower rendering quality preset. |
| `SPIKE-FE-PROJECT-E-0001` | Project open failed | Check package path and integrity, then retry. |
| `SPIKE-FE-SPICE-E-0001` | SPICE assistant input invalid | Correct highlighted model, pin, or analysis fields. |

## Backend Codes

| Code | Title | Recovery |
|---|---|---|
| `SPIKE-BE-APP-C-9999` | Unexpected backend failure | Preserve diagnostics and restart the affected worker. |
| `SPIKE-BE-IPC-E-0001` | Invalid worker request | Correct the request payload and retry. |
| `SPIKE-BE-IPC-E-0002` | Unknown worker method | Verify component versions and use a supported method. |
| `SPIKE-BE-IMPORT-W-0001` | Import quality warning | Review import-quality diagnostics before analysis. |
| `SPIKE-BE-IMPORT-E-0001` | Design import failed | Review the source path, format hint, and importer diagnostics, then retry. |
| `SPIKE-BE-IMPORT-E-0002` | MCAD assembly import failed | Save the project, verify the STEP or glTF artifact and embedded resources, then retry. |
| `SPIKE-BE-MESH-W-0001` | Mesh validity warning | Inspect diagnostics and refine geometry or settings. |
| `SPIKE-BE-MESH-W-0002` | Copper polygon is unusable | Repair or refill the identified copper zone, re-import it, and inspect the mesh preview. |
| `SPIKE-BE-MESH-W-0003` | Pad geometry approximated | Inspect the pad and use a polygon-preserving import path when exact geometry is required. |
| `SPIKE-BE-MESH-W-0004` | Copper geometry skipped | Repair the identified copper primitive dimensions and re-import before solving. |
| `SPIKE-BE-MESH-E-0001` | Conductor mesh escaped source geometry | Inspect the identified source geometry and mesh settings; do not solve until ownership validation passes. |
| `SPIKE-BE-MESH-E-0002` | Pad drill consumes copper land | Correct the pad or drill dimensions in the source design and re-import before meshing. |
| `SPIKE-BE-MESH-E-0003` | Via transition geometry is unsupported | Provide supported circular source geometry and explicit reference-plane antipads, then rebuild the transition. |
| `SPIKE-BE-MESH-E-0004` | Via transition discrete topology is invalid | Inspect the source-bound transition and use a supported bounded radial tessellation before solver handoff. |
| `SPIKE-BE-MESH-E-0005` | Native via transition handoff was rejected | Rebuild and validate the transition geometry and mesh before native handoff. |
| `SPIKE-BE-MESH-E-0006` | Via transition mesh quality gate failed | Inspect the per-level geometry errors and conditioning warnings, then refine or repair the source transition. |
| `SPIKE-BE-MESH-E-0007` | Reference plane antipad geometry is unsupported | Repair the source zone or antipad ownership and use an admitted bounded topology before meshing. |
| `SPIKE-BE-MESH-E-0008` | Reference plane antipad mesh is invalid | Inspect the source-bound plane and rebuild it with an admitted deterministic tessellation policy. |
| `SPIKE-BE-MESH-E-0009` | Native reference plane antipad handoff was rejected | Rebuild and validate the complete reference-plane geometry and mesh before native handoff. |
| `SPIKE-BE-MESH-E-0010` | Reference plane antipad mesh quality gate failed | Inspect per-level geometry discrepancies, clearance, and conditioning, then refine or repair the source plane. |
| `SPIKE-BE-MESH-E-0011` | General reference plane topology is invalid | Repair touching, crossing, nested, off-grid, or unsupported curved source boundaries before meshing. |
| `SPIKE-BE-MESH-E-0012` | Bounded curve plane topology is invalid | Repair the source curve or increase physical separation; fixed production geometry limits are not silently relaxed. |
| `SPIKE-BE-MESH-E-0013` | General reference plane mesh is invalid | Repair the source constraints or use an admitted bounded tessellation and resource policy before native handoff. |
| `SPIKE-BE-MESH-E-0014` | Native generalized plane handoff was rejected | Regenerate the generalized mesh and repair incomplete loops or provenance before native handoff. |
| `SPIKE-BE-MESH-E-0015` | Generalized plane mesh quality gate failed | Inspect the refinement series and repair source constraints or conditioning before field qualification. |
| `SPIKE-BE-MESH-E-0016` | Custom pad resolved geometry is unsupported | Use an admitted filled boundary with no drill or one centered contained plated circle/oval drill. |
| `SPIKE-BE-MESH-E-0017` | Board mesh ownership accounting failed | Inspect source/net-scope accounting and resource limits; do not hand the mesh to a solver until the ownership sidecar passes. |
| `SPIKE-BE-MESH-E-0018` | Zone-pad connection evidence failed | Repair retained connection policy or source-filled geometry; do not infer or regenerate thermal spokes. |
| `SPIKE-BE-MESH-E-0019` | Thermal boundary-contact evidence failed | Repair source-filled component provenance or pad geometry; do not label boundary intervals as thermal spokes. |
| `SPIKE-BE-MESH-E-0020` | Observed thermal topology failed | Repair controlled fixture geometry or retained thermal parameters; do not treat observed topology as refill provenance. |
| `SPIKE-BE-MESH-P-0001` | Mesh resource budget exceeded | Increase the approved budget or use a coarser validated policy. |
| `SPIKE-BE-SOLVER-I-0001` | Solver progress | No action is required. |
| `SPIKE-BE-SOLVER-E-0001` | Solver unavailable | Select or install an eligible solver and validate again. |
| `SPIKE-BE-SOLVER-E-0002` | Solver failed to converge | Review conditioning and mesh diagnostics before changing limits. |
| `SPIKE-BE-SOLVER-E-0003` | Solver execution cancelled | Review partial diagnostics, then run the analysis again when ready. |
| `SPIKE-BE-SOLVER-P-0004` | Solver time budget exceeded | Increase the approved time budget or reduce validated model complexity. |
| `SPIKE-BE-SOLVER-W-0005` | Linear residual is elevated | Review connectivity, resistance ratios, terminal placement, and convergence. |
| `SPIKE-BE-SOLVER-P-0005` | Interactive result data decimated | Raise the result-detail budget for complete export, or retain decimation for responsiveness. |
| `SPIKE-BE-PI-E-0001` | Terminal is not mapped to copper | Select an exact copper object on the analyzed net and assign it as the terminal anchor. |
| `SPIKE-BE-PI-E-0002` | PI formulation is unsupported | Select a formulation supported by the chosen solver. |
| `SPIKE-BE-PI-E-0003` | PI terminals are incomplete | Assign at least one exact source and load terminal. |
| `SPIKE-BE-PI-E-0004` | Analyzed copper geometry is empty | Review managed nets, import coverage, and mesh preview. |
| `SPIKE-BE-PI-E-0005` | Load is disconnected from its source | Correct terminal anchors or define missing series-component bridges. |
| `SPIKE-BE-PI-E-0006` | Source boundary conflict | Remove conflicting source assignments or separate conductor domains. |
| `SPIKE-BE-PI-W-0001` | Floating copper excluded | Inspect excluded copper and restore intended connectivity. |
| `SPIKE-BE-PI-W-0002` | Voltage-drop limit exceeded | Inspect the highest-drop path before changing the design limit. |
| `SPIKE-BE-PI-W-0003` | Current-density limit exceeded | Increase conductor cross-section or reduce current. |
| `SPIKE-BE-PI-W-0004` | Copper discretization requires convergence review | Run the configured coarse-to-fine convergence study. |
| `SPIKE-BE-PI-W-0005` | Ideal terminal package model used | Assign reviewed contact and package resistance models. |
| `SPIKE-BE-PI-W-0006` | Isolated secondary simplified | Assign a transformer/circuit model for magnetic behavior. |
| `SPIKE-BE-PI-I-0001` | Explicit return path solved | No action is required. |
| `SPIKE-BE-PI-E-0100` | PDN candidate invalid | Review candidate values, endpoint mapping, frequency grid, and extraction provenance. |
| `SPIKE-BE-PI-W-0101` | PDN multiport approximation | Use for screening only; obtain a validated power/return extraction for return-path or differential analysis. |
| `SPIKE-BE-PI-E-0102` | PDN candidate port extraction failed | Review explicit terminals, correct their mesh mapping, and retry. |
| `SPIKE-BE-PI-P-0103` | PDN candidate port limit exceeded | Reduce candidates, run bounded batches, or raise the approved limit up to the hard maximum. |
| `SPIKE-BE-PI-E-0200` | Loop extraction contract invalid | Correct the loop request shape and resubmit it. |
| `SPIKE-BE-PI-E-0201` | Loop endpoint or connectivity invalid | Select explicit connected pad endpoints on distinct forward and return nets. |
| `SPIKE-BE-PI-W-0202` | Loop capacitance approximation | Treat the single-reference dielectric estimate as screening data until independently correlated. |
| `SPIKE-BE-PI-W-0203` | Loop capacitance reference mismatch | Run each distinct return net in its own extraction or use a multiconductor electrostatic solver. |
| `SPIKE-BE-PI-E-0204` | Loop component model unreviewed | Review component pins, value or operating-point linearization before extraction. |
| `SPIKE-BE-PI-W-0205` | Shunt model excluded from series loop | Solve the shunt branch through the linked circuit workspace. |
| `SPIKE-BE-PI-W-0206` | Nonlinear loop model linearized | Use the linked ngspice study for switching and large-signal behavior. |
| `SPIKE-BE-SPICE-E-0001` | SPICE workspace contract invalid | Correct the workspace contract and validate again. |
| `SPIKE-BE-SPICE-S-0001` | Unsafe SPICE content blocked | Remove prohibited content or import a reviewed immutable model. |
| `SPIKE-BE-SPICE-E-0010` | SPICE model invalid | Correct the model definition and validate again. |
| `SPIKE-BE-SPICE-E-0020` | SPICE assignment invalid | Map every required model pin to an explicit design anchor. |
| `SPIKE-BE-SPICE-E-0030` | SPICE parasitic mapping invalid | Review terminal mapping, units, and provenance. |
| `SPIKE-BE-SPICE-W-0031` | SPICE parasitic model unvalidated | Use validated extraction or limit the requested analysis. |
| `SPIKE-BE-SPICE-P-0040` | SPICE transient budget exceeded | Adjust duration, step size, outputs, or resource budget. |
| `SPIKE-BE-SPICE-E-0041` | Field/circuit coupling request invalid | Review the circuit workspace, coupling controls, and explicit terminal mappings. |
| `SPIKE-BE-SPICE-E-0042` | Field reduction response invalid | Inspect the field adapter and preserve reviewed parasitic IDs and endpoints. |
| `SPIKE-BE-SPICE-E-0043` | PEEC field mapping invalid | Re-extract the PEEC network and review its explicit circuit endpoint mapping before rerunning co-simulation. |
| `SPIKE-BE-SPICE-E-0050` | Owned SPICE request invalid | Supply only the strict structured-workspace request fields and bounded probes. |
| `SPIKE-BE-SPICE-E-0051` | Owned SPICE resource bound invalid | Reduce netlist, result, or probe limits to the admitted range. |
| `SPIKE-BE-SPICE-E-0052` | Owned SPICE workspace composition failed | Correct the reviewed visual workspace; raw netlist text is not accepted. |
| `SPIKE-BE-SPICE-E-0053` | Owned SPICE engine unavailable | Restore the release-owned circuit engine installation. |
| `SPIKE-BE-SPICE-E-0054` | Owned SPICE bridge execution failed | Inspect owned-engine status, workspace validation, and bounded execution diagnostics. |
| `SPIKE-BE-SPICE-E-0055` | Owned circuit worker cancelled | Inspect the caller cancellation request; the supervisor terminated the complete admitted OS container. |
| `SPIKE-BE-SPICE-E-0056` | Owned circuit worker wall-time limit exceeded | Reduce the workload or request a larger admitted timeout; the supervisor terminated the complete admitted OS container. |
| `SPIKE-BE-EXT-E-0001` | External engine launch failed | Review discovery and process diagnostics before retrying. |
| `SPIKE-BE-EXT-S-0001` | External engine trust failure | Do not execute; restore a trusted signed installation. |
| `SPIKE-BE-PACKAGE-E-0001` | Project package invalid | Open a verified backup or re-import the source design. |
| `SPIKE-BE-PACKAGE-E-0002` | Project package write failed | Choose a writable destination, verify available space, and retry. |
| `SPIKE-BE-PACKAGE-S-0001` | Package signature contract or algorithm unsupported | Open the package with a compatible SPIKE release or have an authorized signer issue a supported Ed25519 envelope. |
| `SPIKE-BE-PACKAGE-S-0002` | Signed package payload or digest invalid | Treat the package as modified; restore a trusted backup or obtain a freshly signed package. |
| `SPIKE-BE-PACKAGE-S-0003` | Package signature malformed or verification failed | Do not open the package; obtain a fresh package from the trusted signer. |
| `SPIKE-BE-PACKAGE-S-0004` | Package signing key unavailable or untrusted | Use an official build that pins the signer key, or have the package re-signed by an authorized key. |
| `SPIKE-BE-REPORT-E-0001` | Report generation failed | Review diagnostics and retry with a writable destination. |

## Classification Index

| Classification | Currently issued examples |
|---|---|
| `I` Information | Frontend operation status, backend solver progress. |
| `W` Warning | Import quality, mesh validity, unvalidated SPICE parasitics. |
| `P` Performance | Viewport budget, mesh budget, transient budget. |
| `E` Error | Project, IPC, solver, SPICE, external engine, package, and report failures. |
| `C` Critical | Unexpected frontend/backend boundary failures. |
| `S` Security | Prohibited SPICE content and external-engine trust failures. |

## Reserved Policy

- `9999` is reserved for an unexpected boundary failure in the applicable
  origin/domain/class group.
- A syntactically valid but undocumented code is unregistered and cannot be
  emitted by the canonical helper.
- Codes are never renumbered or reused after release.
- Solver validity labels are not error classifications and must be preserved
  independently in results and reports.
- Never retry a `C` or `S` code unchanged. Critical errors require restart and
  reproduction; security errors require restoration of a trusted input or
  runtime. A `W` or `P` may permit continuation but never upgrades numerical
  validity.

## Related guidance

- [Troubleshooting](../TROUBLESHOOTING.md): symptom-first diagnosis and
  command sequences.
- [Error handling](ERROR_HANDLING.md): grammar, envelope contract, redaction,
  emission, and contribution policy.
- [User task guide](USER_TASK_SEQUENCES.md#diagnose-a-blocked-workflow): in-application
  recovery sequence.
- [Stability and recovery](STABILITY_AND_RECOVERY.md): process failure domains
  and maintainer incident workflow.
