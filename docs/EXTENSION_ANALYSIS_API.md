# External analysis and Python automation

SPIKE uses the same versioned board and result contracts for built-in workers
and process extensions. An adapter can read the normalized board, call its own
solver or data service, and return values for the normal result viewer, history,
analysis tools, and reports. The adapter owns the physical method and evidence;
SPIKE checks the exchange contract, board identity, and numeric bounds.

## Board input

Declare an `analyses` contribution with `output_contract: "spike/v1"` and
`design.read` plus `results.write` permissions in `spike-extension.json`. When
run, the host passes `context.design`, a
[DesignIR v1](../schemas/design-ir-v1.schema.json) object. It contains a stable
`design_id`, millimetre coordinates, nets, copper layers, tracks, vias, pads,
zones, components, stackup, and import issues. Keep source object IDs and layer
names in solver output so probes and fields can be mapped back to the board.
Optional `parameters` carry solver configuration. With `results.read`, the host
may also pass a bounded summary of the current result.

## Mesh and solver input handoff

An analysis extension can declare `mesh.read` (which requires `design.read`).
SPIKE then constructs the mesh in the worker before launching the extension.
In **Settings → Extension manager**, the mesh controls select analysis mode,
nets, target size, and a 2.5D surface or 3D conductor-volume display preview.
Advanced JSON options can override those controls with `mesh_spec`, using
ordinary `AnalysisSpec` fields. For example:

```json
{"mesh_spec":{"mode":"si","net_names":["DATA_P","DATA_N"],
  "mesh":{"target_size_mm":0.5,"dimension":"volume_3d",
          "max_conductors":4096,"max_preview_cells":1000}}}
```

The request includes these host-generated `context` members:

| Member | Contract and meaning |
| --- | --- |
| `analysis_spec` | Normalized `spike/v1` AnalysisSpec with admitted mesh settings. |
| `solver_geometry` | `spike/solver-geometry/v1`: selected nets, conductors, stackup/materials, components, excitations, ports, frequency settings, and source metadata. |
| `mesh` | `spike/hybrid-mesh-exchange/v1`: complete admitted copper nodes, branches, and cells with source IDs and layer/net ownership. Truncated or erroneous topology is rejected before execution. |
| `mesh_preview` | `spike/mesh/v3` display cells. It may be sampled and must not be used as the complete solve mesh. |
| `mesh_binding` | `spike/mesh-binding/v1` with the design digest and SHA-256 digests of the exact full mesh and normalized analysis setup sent to the adapter. |

The host bounds full topology to 8,192 branches and 32 MB, and the complete
request to 64 MB. Select fewer nets or a coarser target when admission fails.
These are transport and resource bounds, not mesh-convergence criteria. An
adapter may instead discretize `solver_geometry`; record that choice in result
provenance and validate its mesh. The SDK's `mesh_exchange(request)` checks
the input shape. Its `analysis_result(...)` helper copies the mesh digest to
`provenance.input_mesh_sha256` and the setup digest to
`provenance.input_analysis_spec_sha256`; the host rejects missing or mismatched
digests.
This establishes lineage, not physical correctness.

The host also passes `context.design_binding`:

```json
{"design_id":"board-123","digest_sha256":"<64 lowercase hex characters>"}
```

The digest covers the exact DesignIR sent in the request, serialized as UTF-8
JSON with sorted object keys, no extra spaces, non-ASCII characters preserved,
and no non-finite numbers. Copy the binding into the returned provenance. Do
not recompute it from a modified design. A mismatched binding is rejected.

## Result output

Write `spike/extension-result/v1` with `status: "completed"` and
`data.analysis_result` following [AnalysisResult v1](../schemas/analysis-result-v1.schema.json).
The host requires a nonempty `analysis_id`, `mode`, `model_status`, `summary`,
`fields`, `networks`, `probes`, `issues`, and `provenance`. Provenance includes
`design_id`, `design_digest_sha256`, and `solver`. The host adds `extension_id`.
Set `model_status` to `experimental`, `approximate`, or `unvalidated` unless
there is actual qualification evidence; `validated` and `reference_validated`
require `provenance.validation_evidence`. Admission is not physics validation.

For board overlays, put `fields.visualization.schema` at
`spike/result-visualization/v1`. `scalar_fields` maps quantity names to sample
arrays. Each scalar sample has finite `x_mm`, `y_mm`, and `value`, and may have `z_mm`,
`layer`, or object references. Supported viewer quantities include
`voltage_v`, `voltage_drop_v`, `current_a`, `current_density_a_mm2`,
`power_loss_w`, `via_current_density_a_mm2`, and
`operating_point_impedance_ohm`. `vector_fields` supports
`current_density`, `electric_field`, and `magnetic_field`; each vector sample
has finite `x_mm` and `y_mm`, a three-component `vector`, and finite
`magnitude`. Declare units and
assumptions in the result summary or provenance. The total field sample count
is limited to 250,000; the extension manifest also limits time and response
bytes. Mesh cells and time frames use the normal result visualization format
documented in [result visualization](RESULT_VISUALIZATION_AND_LIMITS.md).
An adapter can return `fields.visualization.mesh` as bounded 2D/3D cells with
stable IDs and finite XYZ vertices alongside computed scalar/vector samples.
The viewer displays those cells and the admitted fields/probes, and reports
retain the result. The host does not infer a field from a mesh.
Only publish quantities the solver actually computed. In particular, do not
turn voltage samples into a claimed current density or via stress field.

The Python helper [spike_extension_sdk.py](../extension_sdk/python/spike_extension_sdk.py)
offers `read_request`, `mesh_exchange`, `analysis_result`, `analysis_envelope`, and
`write_result`. A runnable [field data adapter](../extension_sdk/examples/field-data-adapter/extension.py)
shows the exchange without asserting a physical solve. It accepts real
voltage samples in `context.parameters.samples`, then returns an explicitly
unvalidated voltage field. Copy or package the helper alongside your adapter
when distributing it outside this source tree.
The [mesh-aware adapter](../extension_sdk/examples/mesh-field-adapter/extension.py)
also receives full host topology and returns a sampled mesh overlay with
externally supplied voltage samples. It demonstrates the interface; it does
not calculate voltage or qualify the mesh for SI, PI, or thermal physics.

## Running adapters and scripts

Place a package directory containing `spike-extension.json` beneath a root in
`SPIKE_EXTENSION_PATH`, or beneath a workspace `extensions` directory. Open
**Settings → Extension manager**, review the package and permissions, and use
**Trust for session** before running an external package. Trust permits its
local process to execute; process separation is not an OS sandbox. Bundled
extensions are trusted by distribution.

Python scripts can use [SpikeAutomation](../python/spike_core/automation.py)
to call the same worker methods as the desktop, including import, preflight,
analysis, extension catalog, and extension invocation. `run_steps` composes
named calls in order and stops on an error. For example, from the repository
root with the SPIKE Python environment:

```python
import json
from pathlib import Path
from python.spike_core.automation import SpikeAutomation

worker = SpikeAutomation()
design = json.loads(Path("board.spike-design.json").read_text(encoding="utf-8"))
catalog = worker.extension_catalog()
worker.call("trust_extension", {"extension_id": "org.example.field-data-adapter"})
envelope = worker.invoke_extension(
    "org.example.field-data-adapter", "import-voltage-field",
    design=design,
    parameters={"solver": "my-solver/1.0", "samples": [
        {"x_mm": 12.0, "y_mm": 8.0, "layer": "F.Cu", "value": 11.92}
    ]},
)
result = envelope["data"]["analysis_result"]
print(result["provenance"], result["fields"]["visualization"])
```

The example point is an illustration of the interface, not a computed board
result. `SPIKE_EXTENSION_PATH` must include `extension_sdk/examples` before
the worker starts for this package to appear. `trust_extension` applies only
to the current worker session and a currently discovered package. Scripts
may call any registered worker method through `call`; each method retains its
own validation and return contract. Use `context` for additional declared
extension inputs and `parameters` for engine-specific settings. In the app,
run an analysis contribution from the Extension manager to send its admitted
result into the standard viewer and reporting workflow.

For interactive editing and execution inside the desktop app, use the
[Python workspace](PYTHON_WORKSPACE.md). It passes the current board and a
bounded result context to an isolated Python child and can publish fields
through the same admission boundary.
