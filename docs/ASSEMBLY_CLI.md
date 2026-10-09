# Assembly command line workflows

Run from the repository root with the project Python environment activated.
On Windows, use `.venv\Scripts\python.exe` in place of `python` below when the
environment is not activated. The examples use the source-checkout launcher.

The headless CLI can inspect a saved assembly and apply the same manifest-bound
structure update used by the desktop. Structure updates cover board occurrence
placement, harnesses, connector mappings, and rigid-flex links. The worker
validates the complete replacement arrays, checks rigid transforms and retained
design references, writes the package atomically, records an audit event, and
invalidates affected saved results.

Presentation controls have a different boundary. Board visibility and exploded
distance are saved display state under
`analysis.assembly_display`; they do not change `assembly_ir` and never alter
solver coordinates. There is currently no narrow headless mutation command for
that display state. Set visibility and explode controls in the Assembly viewport and save the
project. Do not use `write_project_package` merely to imitate a visibility,
explode, or section action: it is a complete project-save operation, not a
presentation-state patch.

## Inspect without changing the project

The concise inspection returns the package identity and manifest digest:

```powershell
python -m python.spike_cli --output project-inspection.json `
  project-inspect C:\work\assembly.spike
```

Use the registered read operation when an automation needs the complete
canonical `assembly_ir` arrays:

```json
{
  "method": "read_project_package",
  "params": {"path": "C:/work/assembly.spike"}
}
```

```powershell
python -m python.spike_cli --output project-open.json `
  worker-call read-assembly.json
```

The full worker envelope contains the inputs needed for an edit:

- `result.manifest.manifest_payload_sha256` is the concurrency token.
- `result.canonical.assembly_ir.boards` contains occurrence frames.
- `result.canonical.assembly_ir.harnesses` contains harness definitions.
- `result.canonical.assembly_ir.connector_mappings` contains explicit pin links.
- `result.canonical.assembly_ir.rigid_flex_links` contains retained flex links.

Keep all four arrays in an update, including arrays that are unchanged. IDs are
occurrence IDs; equal net names on different boards do not create a connection.

## Move an occurrence or edit a harness

Create a reviewed worker request from the inspected values. Replace the example
digest and arrays with the exact current values from `project-open.json`:

```json
{
  "method": "update_assembly_structure_in_project",
  "params": {
    "project_path": "C:/work/assembly.spike",
    "expected_manifest_payload_sha256": "CURRENT_MANIFEST_DIGEST",
    "boards": [
      {
        "id": "controller-board",
        "design_id": "controller-design",
        "active": true,
        "frame": {
          "frame_id": "controller-board",
          "parent_frame_id": "assembly",
          "transform": [1, 0, 0, 25, 0, 1, 0, 5, 0, 0, 1, 10, 0, 0, 0, 1]
        }
      }
    ],
    "harnesses": [],
    "connector_mappings": [],
    "rigid_flex_links": []
  }
}
```

The 16 transform values are a row-major proper-rigid 4 by 4 matrix in
millimetres. The translation above is `(25, 5, 10)` mm. Copy every additional
field from the inspected occurrence; the abbreviated object is illustrative.
For a harness edit, retain its identity and endpoints and change only reviewed
fields such as `length_mm`, `pin_map`, or an admitted conductor extension.

Run the mutation and retain its response as evidence:

```powershell
python -m python.spike_cli --output assembly-update-result.json `
  worker-call update-assembly.json --timeout-seconds 120
```

A successful response has `ok: true`, result contract
`spike/assembly-structure-update-result/v1`, and a new manifest. Re-read the
project before another edit. Reusing the old digest fails because the project
changed. A nonzero process exit or `ok: false` means the change was not
accepted.

## View-only operations

The Assembly viewport provides these presentation operations:

| Operation | Saved field | Effect |
| --- | --- | --- |
| Hide or show a board | `analysis.assembly_display.visibility[occurrence_id]` | Filters that occurrence and its harness endpoints from the view. |
| Explode | `analysis.assembly_display.exploded_distance_mm` | Applies display-only occurrence offsets, including aligned overlays and harness endpoints. |
| Section | Temporary current-view state | Clips displayed board, component, harness and result geometry with one axis plane or a box; it is not saved in this release. |

These operations do not modify occurrence frames, harness definitions, source
geometry, or solver inputs. Use a placement edit when the physical assembly
position must change. Reset explode to zero and disable sectioning when checking
the authored physical arrangement.

## Failure and recovery

- A manifest mismatch means another save won the race. Re-read, reapply the
  intended edit to the new arrays, and submit the new digest.
- A transform rejection means the matrix is not a finite right-handed rigid
  transform or violates a retained placement policy.
- A harness rejection means its endpoints, pins, or conductor extension do not
  match retained occurrences and connectors.
- Removing an occurrence prunes dependent references and can invalidate saved
  studies. Review `removed_board_ids`, `reconciled_reference_counts`, and
  `results_invalidated` in the response.
- Result bundles reject structure changes. Save an editable portable project
  before changing the assembly.
