<!-- SPDX-License-Identifier: Apache-2.0 -->
# PI return-path assistant

The assistant traces a minimum series-resistance route between explicitly
selected return pads on one loaded board. The result is **approximate** routing
evidence. It does not solve current distribution, equivalent terminal resistance,
loop inductance, high-frequency return behavior, or layout qualification.

## Workflow

Select the board occurrence and forward net in PI setup, then open the return-path
assistant. Choose a different, explicit return net, one source return pad and
1 to 32 load return pads. Set a mesh target between 0.05 and 1000 mm and run the
planner. Review each returned route and all diagnostics before applying the
terminal selection. Applying a selection does not edit board copper.

`connected` means every requested load has a mesh route to the source.
`disconnected` preserves the result for every load, including connected loads;
unreachable loads have null resistance/length and no points. `blocked` contains
diagnostics and no route claims. After a block, repair the indicated source,
selection or resource issue and run again. Do not interpret a coarse-mesh
disconnection as proof that manufactured copper is disconnected.

## Worker API

`python.spike_core.pi_return_path.plan_pi_return_path(design, request)` takes a
SpiDeR v1 dictionary in millimetres and this exact request shape:

```json
{
  "contract": "spike/pi-return-path-request/v1",
  "occurrence_id": "board-1",
  "forward_net": "VCC",
  "return_net": "GND",
  "source_pad_id": "J1.2",
  "load_pad_ids": ["U1.3"],
  "mesh_target_mm": 1.0
}
```

The result contract is `spike/pi-return-path-result/v1`. Each path contains
`load_pad_id`, `connected`, `resistance_ohm`, `length_mm` and `points_mm`
(ordered x/y/z millimetres). Successful planning also retains the exact request
and `model_status: approximate`. Issues contain stable codes, severity and
messages; mesher diagnostics are retained. No copper bridge proposals are
generated in this version.

Pad IDs must be explicit and unique. Geometry IDs cannot collide across kinds.
Direct net names and `net_id` references must agree with the design's net table.
Unknown or foreign pads, wrong-net terminals, duplicate loads and source/load
identity reuse are blocked. The function checks `design.occurrence_id` when
provided. A plain SpiDeR v1 board has no assembly ownership: the caller must
bind the supplied design to the selected occurrence and discard stale results.
Forward-net identity provides context; its copper is not optimized or solved.

## Method, units and evidence

The service normalizes only net identity into a copied design and calls the
existing `hybrid_mesh.build_hybrid_mesh` for the return net. Terminal nodes must
have exact pad ownership from mesh branches or pad cells. Among owned nodes,
the nearest x/y node to the pad center is selected, breaking ties by node ID.
There is no snap to arbitrary nearby copper. Multi-layer pad anchoring uses
this same deterministic rule and is an approximation to physical contact area.

Every traversed edge already exists in the admitted mesh. Its modeled resistance
is calculated by the shared branch property:

```text
R [ohm] = (L_mm * 1e-3) / (sigma_S_per_m * width_mm * thickness_mm * 1e-6)
```

Dijkstra's algorithm minimizes the sum of these nonnegative edge resistances.
Length is the sum of the chosen branch lengths. Existing mesh attachment
resistances remain part of that sum; they are model links, not independently
qualified physical contacts. Copper conductivity is the shared mesh default
5.8e7 S/m. Missing stackup values inherit the mesh's documented thickness and
layer-spacing defaults. Values are finite-checked; positive cross sections and
conductivity are required. Accumulation overflow blocks the entire result.
Equal-cost choices use deterministic mesh/node order. No linear system or
condition-number claim is involved.

The implementation and fixtures are original SPIKE material and reuse the
repository's authoritative mesher. No external implementation, board, or dataset
was copied. The resistance derivation is the uniform-conductor relation
`J=sigma E`, `I=J A`, `V=E L`, giving `R=V/I=L/(sigma A)`.

`tests/python/test_pi_return_path.py` checks:

- An actual 10 mm x 1 mm x 0.035 mm copper trace against
  `0.010/(5.8e7*0.001*35e-6)` ohm at 2, 1, 0.5 and 0.25 mm targets,
  with absolute resistance and length tolerances of `1e-12`.
- A two-route analytical graph where a longer 2 ohm route beats a direct
  10 ohm route; the result must not become the parallel equivalent resistance.
- Actual isolated pads, mixed connected/disconnected loads, and a source-filled
  plane whose explicit `none` pad policy prevents attachment.
- Request, identity, net, geometry, nonfinite, resource, missing terminal and
  incomplete-mesh rejection.

The line refinement test establishes invariance for this simple graph. It does
not establish arbitrary plane convergence, field accuracy or measured hardware
correlation. Knowledgeable human numerical review remains required before release.

## Admission and resource limits

Only explicit copper layers and positions are admitted. Return zones need
retained `source_filled` geometry. Separate hole arrays, incomplete source-fill
provenance and pad shapes that the default mesher replaces by bounding boxes
(including roundrect) are blocked. Rectangular, circular, oval and mesher-admitted
custom pads are supported. Missing source-fill connectivity evidence can leave
a pad disconnected; the service does not invent a bridge to repair it.

Planning admits at most 5000 objects per copper collection, 250000 visited
input values, nesting depth 32, estimated meshing work of 250000 cells/segments,
50000 mesh branches, 100000 mesh nodes, and 100000 total returned points.
Position magnitudes and explicit dimensions are limited to 1e6 mm, and zone
polygons to 2048 points. The shared mesher targets at most 3000 zone/custom-pad
cells per object and applies its RAM
admission. Truncation or blocking mesher diagnostics block all route claims.
Automatic feature refinement is disabled so the explicit mesh target governs
this bounded planning pass; the normal mesher's per-object limits still apply.

The caller runs this synchronous operation in the existing supervised worker,
which supplies process cancellation. The service creates no threads, jobs,
external files, persistent state, or design mutations. Graph storage is O(V+E),
the route search is O((V+E) log V), and route output is explicitly bounded.
For large designs, isolate the intended return copper or increase the target.

Stable service diagnostics use the `PI_RETURN_` prefix, including
`REQUEST_CONTRACT`, `REQUEST_IDENTITY`, `LOAD_LIMIT`, `TERMINAL_IDENTITY`,
`MESH_TARGET`, `NET_IDENTITY`, `DESIGN_CONTRACT`, `INPUT_LIMIT`, `NONFINITE_INPUT`,
`OCCURRENCE_MISMATCH`, `NET_MAPPING`, `PAD_IDENTITY`, `GEOMETRY_IDENTITY`,
`LAYER_IDENTITY`, `DESIGN_GEOMETRY`, `ZONE_FILL_REQUIRED`,
`ZONE_GEOMETRY_UNSUPPORTED`, `PAD_SHAPE_UNSUPPORTED`, `MESH_LIMIT`, `UNKNOWN_NET`,
`UNKNOWN_PAD`, `PAD_NET_MISMATCH`, `INVALID_MESH`, `PAD_UNMESHED`,
`NUMERICAL_RANGE`, `OUTPUT_LIMIT`, `DESIGN_BLOCKED`, `MESH_BLOCKED`,
`INVALID_GEOMETRY`, `APPROXIMATE` and `DISCONNECTED`.
