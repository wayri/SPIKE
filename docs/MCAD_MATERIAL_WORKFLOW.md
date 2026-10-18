# MCAD material workflow

SPIKE stores reviewed material evidence on an assembly occurrence without
rewriting imported electrical design data or MCAD geometry metadata. The
assignment is an immutable snapshot. Later catalog edits therefore do not
silently change a saved project.

## Workflow

1. Open a saved `.spike` project through the desktop file picker.
   Open **MCAD assembly > Material library**, search by material, family or
   property, select a part/board and optionally an existing board layer, inspect
   the evidence, then choose **Save material snapshot**. **Create editable
   project material** opens a JSON record editor for user-supplied grade data.
2. Call `list_material_catalog` through the project worker with
   `project_path`. Catalog values are SI evidence records and include status,
   provenance, applicability, and shape for every property.
3. Review a catalog record, or prepare a user record accepted by
   `validate_material`.
4. Call `assign_material_to_project` with the opened manifest digest, explicit
   `target_kind` (`part`, `board`, or `board_layer`), stable occurrence
   `target_id`, and exactly
   one of `catalog_material_id` or `material`.
5. Continue from the returned manifest. A second edit using an older manifest
   digest is rejected.

The saved occurrence extension is:

```json
{
  "spike.material": {
    "schema_version": 1,
    "material_id": "generic-aluminium",
    "revision": "1",
    "digest": "<sha256 of canonical record>",
    "record": { "schema_version": 1, "id": "generic-aluminium" }
  }
}
```

The complete validated record is present in an actual snapshot. The shortened
example only illustrates the envelope.

For `board_layer`, also provide the exact canonical `layer_id` from the
occurrence's retained SpiDeR design. SPIKE resolves `target_id` to its
`design_id`, verifies that the design is retained, and requires an exact layer
identity match. It stores the snapshot in
`board.extensions["spike.layer-materials"][layer_id]`. This supports explicit
records for substrates, metal cladding, and heater-film layers such as FR4,
generic copper, or Kapton candidates. Display names are not accepted as an
identity fallback because names can be duplicated or changed.

## Persistence and recovery

The operation edits only `assembly_ir.parts[].extensions` or
`assembly_ir.boards[].extensions`. It retains unknown occurrence fields and
existing extension keys, and leaves `design_ir`, layer ordering, and stackup
thickness unchanged. Missing targets,
stale manifests, malformed evidence, and snapshot digest mismatches fail before
the package is written.

Material changes can invalidate simulation outputs. SPIKE removes results from
the active context and records the preceding assembly and result context under
`extensions.spike.material-assignment-history`. The audit event records the
target, material ID, revision, digest, and whether active results were cleared.
Rerun affected studies before using results for engineering decisions.
Assigning the exact snapshot already present on the target is a no-op: the
package, audit log, and currently valid results are retained, and the response
reports `unchanged: true`.

## Scope and limits

Catalog records are evidence, not solver qualification or procurement data.
An `estimate` remains an estimate after assignment. Property applicability and
tensor/sample shapes are preserved; assignment does not interpolate curves,
reduce tensors, choose a constitutive model, or make an unsupported solver
available. Solvers must explicitly project the properties they support and
apply their own numerical and validation gates.

This does not automatically replace existing thermal/structural/EM input
materials. In particular, a retained non-copper layer assignment does not change
a PI engine that still requires its separately supported conductivity input.
Review and transfer supported constants into the relevant solver setup; sampled
and anisotropic laws require an adapter that explicitly supports them.

## Further integration gates

- Structural changes and three-way MCAD revision merge need their own proposal
  contract beyond the current reviewed placement feedback.
- A heater laminate needs explicit conductor, adhesive and substrate regions,
  their thickness/orientation and thermal/electrical boundaries. A Kapton or
  PTFE catalog entry alone is not a heater model.
- FR4 variants and metal-clad composites require grade-specific effective or
  resolved stackup data; no copper-fraction homogenization is inferred.
- RF laminates require frequency, measurement method, process/design Dk,
  anisotropy and conductor loss/roughness choices appropriate to the engine.
- Plastics, ceramics and metals can retain linear constants today; nonlinear,
  viscoelastic, plastic, phase-change and magnetic laws require separate
  constitutive implementations and validation.
