# Solver Plugin Result Contract

SPIKE solver plugins consume `DesignIR` plus `AnalysisSpec` and return an
`AnalysisResult`. External plugins use `solver-plugin.json` and exchange JSON
through the isolated process adapter. The UI does not import solver-specific
libraries.

## Renderer envelope

Visualization data belongs in `AnalysisResult.fields.visualization`:

```json
{
  "schema": "spike/result-visualization/v1",
  "scalar_fields": {
    "voltage_drop_v": [
      {
        "x_mm": 12.5,
        "y_mm": 4.0,
        "z_mm": 0.8,
        "layer": "F.Cu",
        "net": "VCC",
        "element_id": "track-42",
        "value": 0.018
      }
    ],
    "current_density_a_mm2": []
  },
  "vector_fields": {
    "electric_field": [
      {
        "x_mm": 12.5,
        "y_mm": 4.0,
        "z_mm": 1.2,
        "net": "CLK",
        "value": 320.0,
        "magnitude": 320.0,
        "vector": [0.8, 0.1, 0.0]
      }
    ],
    "magnetic_field": [],
    "current_density": []
  },
  "mesh": [
    {
      "id": "cell-1",
      "layer": "F.Cu",
      "net": "VCC",
      "vertices_mm": [[0, 0, 0.8], [1, 0, 0.8], [0, 1, 0.8]]
    }
  ]
}
```

All coordinates use the DesignIR millimeter coordinate reference. Scalar
`value` uses the field name's SI-derived unit. Vector direction and magnitude
must come from the solver, not from the UI.

Long time-domain runs should use `spike/compact-field-series/v1` inside the
visualization envelope. `layouts` stores immutable sample coordinates and
metadata once, `field_layouts`/`vector_layouts` select those samples, and each
frame stores only `scalar_values`/`vector_values` numeric arrays. Array order
must match the named layout exactly. Plugins should also publish time-global
field ranges so color and height mappings do not rescale between frames.

Plugins remain responsible for output bounding. Report requested/effective
timestep, frame decimation, visual sample decimation, stored numeric bytes,
estimated peak memory, actual solver allocations where measurable, and wall
time. Exceeding a declared budget must fail or deterministically increase an
explicitly automatic output decimation setting; silently dropping numerical
integration steps is not allowed.

## Power analytics summaries

Solvers that compute conductor loss should publish exact, non-decimated totals
in `AnalysisResult.summary`:

- `total_network_loss_w`: sum of every active solved resistive branch,
  including reviewed equivalent component branches.
- `total_copper_loss_w`: sum of physical copper-geometry branch loss only.
- `series_component_loss_w`: sum of reviewed equivalent series-component
  branch loss.
- `net_power_loss_w`: loss grouped by electrical net or isolated domain.
- `layer_power_loss_w`: loss grouped by physical copper layer; through-layer
  elements use an explicit label such as `through`.
- `geometry_power_loss_w`: loss grouped by branch kind, for example track,
  zone, pad, via, contact, or `series_component`.
- `component_power_loss_w`: equivalent-branch loss grouped by component
  reference.

For a resistive conductor graph, each total is derived from
`P_loss = sum(I_k^2 R_k)` over the applicable active solved branches.
`total_network_loss_w` must equal `total_copper_loss_w +
series_component_loss_w` within numerical tolerance. The net and layer maps
sum to `total_copper_loss_w`; the component map sums to
`series_component_loss_w`; and the geometry-kind map sums to
`total_network_loss_w`. These values are solver-owned evidence and must not be
reconstructed from decimated renderer samples.

Report-level board or batch totals aggregate the latest result for each
analysis scope. Reports must state that unanalyzed nets, converter efficiency,
active-component dissipation, and thermal losses are excluded unless a coupled
solver explicitly returns them.

## Series-component visualization

Reviewed cross-net PI paths expose equivalent component branches separately
from physical conductor mesh cells in `fields.visualization.component_bridges`
using `spike/pi-path-interface-elements/v1`. Each `line2` record contains exact
pad-center endpoints in `vertices_mm`, source and destination nets/layers,
component and pad identities, resistance/model provenance, solved branch
current, voltage drop, and loss.

These records are circuit-topology evidence, not package volume meshes. They
must declare `current_density_supported: false` and
`spatial_material_model: unavailable_without_package_and_bond_geometry` until
an importer or reviewed user model supplies package, lead, solder-bond, and
contact material geometry. Renderers must not synthesize a component volume or
current-density field from this equivalent branch.

## Network results

Extracted models belong in `AnalysisResult.networks`:

- `parasitics`: per-net R, L, C, and frequency-indexed complex impedance.
- `coupling_risks`: victim/aggressor pairs, limit status, NEXT/FEXT, and peak
  coupled voltage where computed.
- S-parameters and terminal matrices may use their established Touchstone or
  matrix metadata alongside the normalized summary.

## Capability names

Plugins must declare every result they can produce. Current standard names are:

- `voltage_drop`, `current_density`
- `rlc_extraction`, `capacitance_extraction`, `partial_inductance`
- `impedance`, `frequency_dependent_impedance`
- `coupled_line_extraction`
- `electric_field_coupling`, `magnetic_field_coupling`
- `surface_currents`, `volume_fields`
- `s_parameters`, `touchstone`, `spice_subcircuit`

Omitted datasets mean unsupported or not requested. A plugin must return an
explicit issue for invalid geometry, validity-limit violations, or convergence
failure. Empty arrays must never be interpreted as a zero physical field.
