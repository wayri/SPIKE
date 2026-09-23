# Transient, Thermal, and Viewport Contracts

## Viewport behavior

- Camera inertia is disabled by default. The toolbar activity button enables OrbitControls damping for users who prefer it.
- The setting is part of project history and is saved as `analysis.navigation_inertia`.
- Result overlays can be hidden independently of geometry.
- `sceneMode` selects an opaque board, translucent board, or analyzed-net-only scene. Component-model visibility is independent from copper-layer visibility.
- Result geometry can use a flat scalar overlay or a height-map overlay driven by the active frame while retaining the imported board coordinate transform.
- Probe geometry uses a non-depth-tested top render order in 3D. The 2D layout draws a final probe overlay after mesh and scalar-result geometry.

## Time-series result envelope

Solver result bundles may include:

```json
{
  "time_series": {
    "contract": "spike/compact-field-series/v1",
    "times_s": [0.0, 0.000001],
    "layouts": {
      "nodes": [{"x_mm": 12.5, "y_mm": 4.0, "z_mm": 0.8, "layer": "F.Cu", "net": "VCC"}]
    },
    "field_layouts": {"voltage_v": "nodes"},
    "frames": [
      {
        "time_s": 0.0,
        "scalar_values": {"voltage_v": [12.0]},
        "vector_values": {}
      }
    ]
  }
}
```

The desktop materializes only the selected compact frame. It does not
interpolate or invent missing physics. Solver-supplied global ranges keep the
2D color map and 3D color/height map stable across time. GIF export uses a
bundled offline encoder, captures at most 180 frames, and preserves the source
timing through the GIF frame delay.

## ngspice board overlay bindings

The ngspice adapter still requires an explicit, self-contained netlist. Geometry-derived parasitics are not silently inferred. A transient request can map output vectors to board coordinates through `AnalysisSpec.options.spice_overlay_bindings`:

```json
{
  "spice_netlist": "...",
  "spice_overlay_bindings": [
    {
      "vector": "v(vout)",
      "quantity": "voltage_v",
      "x_mm": 42.1,
      "y_mm": 17.8,
      "layer": "F.Cu",
      "net": "VOUT",
      "element_id": "U1.3"
    }
  ]
}
```

Supported overlay quantities are `voltage_v`, `voltage_drop_v`, `current_a`, and `current_density_a_mm2`.

## Component stress and derating

`AnalysisSpec.options.component_stress_bindings` maps voltage/current/power vectors to component ratings:

```json
{
  "component_stress_bindings": [
    {
      "component_id": "Q1",
      "reference": "Q1",
      "voltage_vector": "v(q1_drain)",
      "current_vector": "i(vq1sense)",
      "power_vector": "p(q1)",
      "ratings": {
        "voltage_v": 80,
        "current_a": 40,
        "power_w": 120
      }
    }
  ]
}
```

The adapter reports peak voltage/current/power, RMS current, average power, utilization percentages, and an assigned-limit status. Junction temperature and lifetime are not calculated until a validated electro-thermal model supplies thermal impedance or a coupled thermal result.

## Thermal scenario contract

`spike/thermal/v1` now records:

- Application environment: domestic, industrial, marine, aerospace, or custom.
- Medium: air, vacuum, or potting.
- Enclosure: open, sealed, or vented cabinet.
- Convection: none, natural, or forced.
- Fans, flow channels, openings, cabinet airflow direction, virtual heatsinks, potting properties, radiation, heat sources, and bounding volume.

Only open-air board heat-source cases are currently solver-ready. Vacuum radiation, potted conjugate conduction, cabinet boundary models, virtual heatsink geometry, and surface-to-surface radiation are accepted as project intent but return `capability.status = unsupported`. `prepare_case` returns `prepared_physics_unsupported` for those scenarios and never labels them solver-ready.

## Required validation before release

- Compare animated electrical frames against raw ngspice vectors point by point.
- Verify GIF timing and color mapping on 2D and 3D viewports.
- Add thermal analytical fixtures for pure conduction, natural convection, forced duct flow, and radiation view factors before enabling each physics gate.
- Couple component power to the thermal mesh only after coordinate transforms and energy conservation are tested.
- Require assigned model provenance and datasheet-rating provenance in any component stress report presented as validated.
