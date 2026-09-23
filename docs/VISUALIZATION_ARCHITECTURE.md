# SPIKE Visualization Architecture

## Objective

SPIKE must render the design that was imported, not a visual approximation based on its bounding box. Geometry, selections, probes, and analysis overlays share one normalized coordinate system so that 2D, 3D, reports, and KiCad cross-selection refer to the same objects.

## Reference Evaluation

KiCAD-Prism is a useful product and workflow reference. Its current viewer is based on vendored ECAD-Viewer/KiCanvas assets, with a separate Three.js 3D path. KiCAD-Prism is Apache-2.0 licensed, ECAD-Viewer is MIT licensed, and KiCanvas has its own upstream project. SPIKE does not copy their vendored bundles. It uses the architectural ideas of dedicated renderers, stable object metadata, cross-probing, and viewer-specific validation.

KiCad Monkey is an MIT-licensed Python parser, round-trip model, and IR-backed 2D renderer. It is a strong candidate for the supported KiCad ingestion layer because it separates low-level format handling from application orchestration. Adoption requires a pinned version, corpus comparison against SPIKE's DesignIR, and dependency/provenance review.

References:

- https://github.com/krishna-swaroop/KiCAD-Prism
- https://github.com/Huaqiu-Electronics/ecad-viewer
- https://pypi.org/project/kicad-monkey/
- https://www.kicad.org/discover/3dviewer/

## Current Pipeline

```text
.kicad_pcb
  -> s-expression parser
  -> normalized browser preview geometry
  -> board outline and cutout loops
  -> copper layers, zones, tracks, pads, vias
  -> footprint and model metadata
  -> orthographic 2D renderer
  -> native Three.js 3D renderer
```

The browser parser exists for the offline development preview. The packaged application should obtain the authoritative DesignIR from the local worker and use the same rendering contracts. The browser parser and worker importer must be compared against the same fixture corpus until their outputs agree.

For KiCad sources, the local worker prepares a `spike/visual-bundle/v1` cache
with KiCad CLI. It contains a board-only binary glTF scene, a component-only
binary glTF scene, aligned SVG views for every copper layer, and a quality
manifest. The scenes and vectors are project-cache artifacts and require no
network access after export.

## Rendering Contract

- Board substrate is extruded from `Edge.Cuts`; disconnected inner loops become cutouts.
- Copper zones use filled polygons from the source file.
- Tracks preserve width, layer, net, and stable source UUID.
- Pads preserve shape, size, rotation, drill, layers, net, component, and UUID.
- Vias preserve annulus, drill, layer span, net, and UUID.
- Footprint artwork is batched by layer.
- 2D uses aligned KiCad vector plots with a dedicated pan/zoom controller.
- One copper layer is active at full contrast by default; `All` is an explicit
  low-opacity composite rather than the default view.
- Vector plots preserve source tracks, filled zones, pads, drills, text,
  silkscreen, and `Edge.Cuts` at arbitrary zoom.
- 2D click selection maps the SVG coordinate back into normalized DesignIR
  coordinates and returns the same object metadata used by 3D and KiCad.
- 3D uses a perspective camera with pan, orbit, zoom-to-cursor, environment lighting, and soft shadows.
- 3D uses a permanent Z-up basis. Preset views must never change `camera.up`;
  TOP uses a small polar offset to avoid the pole singularity.
- The camera selector exposes top, bottom, front, back, left, right, and
  isometric views. Top and bottom use opposite small polar offsets so both
  board faces remain reachable without an unstable exact-pole camera.
- Left drag orbits, middle or right drag pans, and wheel input zooms.
  Middle/right-button release and drag gestures cannot trigger selection or
  change the orbit pivot.
- 3D orbit permits the full upper and lower hemispheres; only a 0.001-radian
  numerical guard remains at each pole.
- 2D maps both left and right drag to pan and never updates the disabled 3D
  controller. Pointer deltas are coalesced to one view update per animation
  frame. Both controllers use restrained damping for smooth, deterministic
  settling without changing the selected orbit target.
- Fit and camera presets use the loaded assembly bounds, not the PCB origin or a hard-coded distance.
- The orientation helper renders after the board with explicit clear control and only updates while its camera animation is active.
- Selection focuses the camera target and uses the same UUID used for KiCad cross-selection.

## Electrical Selection And Isolation

Selection is an electrical-domain operation, not only a renderer effect.
`spike/net-geometry/v1` contains every track segment, filled zone island, via,
pad, participating copper layer, and stackup row for one named net. The browser
and worker implementations must produce equivalent bundles.

- 2D and 3D use transparent picking geometry that retains stable source IDs,
  layer, and net metadata even when the authoritative fused GLB is displayed.
- Selecting one conductor cross-highlights the complete net across all layers.
- Isolate mode suppresses unrelated board and model geometry and displays the
  complete extracted net, including filled copper and through-layer connections.
- The isolated geometry is persisted in the SPIKE project and is the input
  boundary for PI/SI extraction, probes, reports, and KiCad cross-selection.
- The copper Overview presents every imported copper-layer vector as a page and
  reports selected-net feature counts on each page.
- Zone islands remain separate polygons. They must never be concatenated into a
  self-crossing display polygon or solver region.

## Component Models

The current scene prefers separate KiCad board and component GLBs. This keeps
the board visible when component models are hidden and avoids the transparent
surface sorting problems caused by a fused export. Parametric bodies are used
only when no authoritative scene is available or an explicit separable layer
view is active. They are not source-accurate 3D models and remain
distinguishable in provenance and UI state.

The production model pipeline is:

1. Discover a locally installed `kicad-cli`; do not download executables.
2. Export board geometry with `--board-only`, including tracks, pads, zones,
   inner copper, silkscreen, and soldermask.
3. Export component models with `--no-board-body`.
4. Export one fitted SVG per detected copper layer with common silkscreen,
   drills, and `Edge.Cuts`.
5. Verify both GLB signatures and the shared SVG viewbox, then retain every
   generator exit code.
6. Parse unresolved component references into the bundle quality manifest.
7. Store the bundle and relative manifest paths in the SPIKE project cache/package.
8. Load both GLBs asynchronously under one normalized assembly transform.
9. Consolidate static geometry by material to reduce draw calls.
10. Retain parametric geometry only as an explicit fallback when scene export fails.
11. Validate position, rotation, scale, board side, and origin against fixture screenshots and KiCad.

Authoritative KiCad component models and procedural package proxies are mutually
exclusive. The procedural root must remain disabled after a visual bundle is
ready. In a separable layer view, the normalized board layers may be combined
with the separate KiCad component scene, but procedural component bodies remain
hidden so duplicate or conflicting package geometry cannot appear.

Remote model fetching is disabled by default. Model files have size, triangle-count, and parse-time limits. Untrusted model content cannot add scripts, remote textures, or custom shaders.

Worker-side model provenance expands `${KIPRJMOD}` relative to the imported
board and discovers installed KiCad 10, 9, and 8 model roots. The KiCad CLI
visual-bundle manifest remains authoritative for final render availability
because KiCad may apply additional configured path substitutions.

The offline global model library indexes STEP, STP, WRL, VRML, glTF, and GLB
files from installed KiCad roots, the SPIKE user model folder, and a directory
explicitly selected by the user. Search is bounded, ignores unreadable paths,
and does not fetch remote content. Assignments are stored by component reference
inside the SPIKE project. Rendering an assigned STEP model still requires the
documented local conversion stage.

## Layer Management

`ParsedBoard.layers` is the ordered copper stack used by solver and Z-placement
logic. `ParsedBoard.layerDefinitions` is the complete source layer table,
including copper, mask, paste, adhesive, silkscreen, fabrication, courtyard,
mechanical, and user layers. The two fields must not be conflated.

Layer visibility and opacity are saved in the SPIKE project package. The UI
groups source layers without renaming their canonical KiCad identifiers and
supports search, explicit show/hide actions, show-only, opacity, and restoration
to imported defaults.

The imported default visibility follows a PCB 3D workflow: copper, solder mask,
silkscreen, and `Edge.Cuts` are visible. Paste, adhesive, courtyard,
fabrication, margin, and user-documentation layers remain available but start
hidden so footprint construction artwork cannot be mistaken for board geometry.

Layer View supports an exploded stack with a physical spacing value in
millimeters. Copper and side-specific surface artwork move with their source
layer, the separate authoritative component assembly follows its mounted side,
and plated via barrels terminate at the separated outer copper surfaces. Vias
have an independent visibility control and can be isolated without the
substrate.

KiCad's board-only GLB still groups physical board materials rather than
individual electrical layers. When a 3D layer filter, non-default opacity, or
stack separation is active, the viewport switches to separable normalized
geometry and labels the result `LAYER VIEW`. Restoring defaults returns to the
authoritative KiCad assembly. The 2D layout does not have this limitation
because each copper layer is a separate aligned source-vector asset.

Transparent meshes from the KiCad board scene preserve source draw order and
are not merged into opaque material batches. Component meshes cast lightweight
soft shadows onto the board; transparent soldermask does not write depth.
Semantic material tuning keeps copper metallic, soldermask translucent, the
substrate dark, and silkscreen legible. Neutral tone mapping, a neutral charcoal
background, restrained image-based lighting, and non-emissive via plating avoid
the bright-line artifacts produced by overexposed metallic geometry.

## WebView Boundary

Current profiling found serialized JavaScript geometry filtering, object
allocation, SVG reconciliation, and draw-call submission bottlenecks. It did
not prove that WebView/WebGL itself is the limiting component. Three.js still
uses the native WebGL GPU path, and the authoritative board and component
scenes remain separately loadable. Keep this architecture while the measured
data-path bottlenecks can meet the published budgets.

Move only the viewport to a native renderer when measured fixtures exceed those
budgets or require capabilities WebGL cannot deliver, such as very large
full-wave meshes, compute-heavy field visualization, or a platform-specific
graphics feature. A native viewport must still consume the same DesignIR,
selection, camera, and result contracts; it must not fork the engineering model.

## Performance Strategy

- Use the shared net/layer-aware spatial conductor index for result masking.
  Preserve exact geometry predicates after candidate lookup, and cache bounded
  datum validity across transient frames.
- Evaluate result containment once per datum. Interactive result displays use
  deterministic spatial thinning and bounded primitive budgets; retained
  solver values, statistics, limits, probes, exports, and reports remain full
  fidelity.
- Batch 2D scalar cells into a bounded number of SVG paths. Do not create one
  DOM node per solver sample.
- Merge large procedural copper displays by compatible layer/material/kind.
  Semantic picking remains separate until an indexed/BVH or ID-buffer picking
  path replaces per-feature proxies.
- Batch silkscreen and non-selectable linework by layer.
- Consolidate the ebrake fixture's 24,692 board meshes to 6 display meshes and
  6,487 component meshes to 27 display meshes, while separately tracking the
  material groups that still expand GPU draw calls.
- Lower device-pixel ratio and freeze shadow-map refresh only while the user is
  manipulating the camera; restore full quality 120 ms after input, with a
  timeout recovery for interrupted pointer sequences.
- Coalesce hover picking and 2D pan updates to at most once per display frame.
- Stop WebGL board rendering while the authoritative 2D vector layout covers
  the canvas.
- Use level of detail for large assemblies.
- Introduce instancing for repeated vias and common pad shapes.
- Frustum-cull board regions and component models.
- Load model assets on demand and release GPU resources when projects close.
- Keep renderer dependencies in a separately cached production chunk.
- Publish SPIKE process-tree CPU/RSS, host RSS, process count, worker activity,
  JavaScript heap fallback, FPS, frame time, draw calls, triangles, GPU object
  counts, render scale, and source feature counts in the status-bar resource
  monitor. One fully occupied logical CPU is reported as 100%; total-machine
  CPU capacity is shown separately.
- GPU utilization is not currently sampled. The UI must label it unavailable
  rather than inferring utilization from draw calls, geometry, or textures.
- Replace large full-JSON result responses with digest-bound binary/chunked,
  file-backed artifacts and viewport-aware LOD before qualifying million-point
  result interaction.

### Large-board acceptance budgets

- Interactive camera frame time: p95 at or below 33 ms on the reference GPU.
- Input-to-camera response: p95 at or below 50 ms during orbit, pan, and zoom.
- Recovery to full render quality: within 250 ms after normal pointer release.
- No unbounded growth after opening and closing the same project five times.
- Import and display a motherboard-class fixture with at least 10,000 routed
  segments, 2,000 vias, 1,000 footprints, and 12 copper layers.
- Draw-call, geometry, and memory regressions fail performance CI against the
  fixture baseline. Passing the import parser alone is not sufficient.
- Static 21,000-sample first-result construction is targeted below 200 ms on
  the reference machine; UI-only result-control changes are targeted below one
  16 ms frame and must not rebuild unchanged result topology.
- One-million and ten-million-point cases must retain bounded display, memory,
  transport, and picking work through chunking/LOD. An interactive display cap
  alone does not satisfy this gate.

## Validation Gates

- Parser counts match the source fixture and authoritative worker importer.
- Outer outline and every cutout are present.
- 2D cannot orbit and remains top-normal after selection.
- 3D produces nonblank pixels at supported desktop viewports.
- Fit, zoom, pan, orbit, layer visibility, model visibility, search selection, and external selection work.
- No unsupported model is silently replaced without a fallback/provenance flag.
- A screenshot baseline exists for each reference board in 2D and 3D.
- Large-board performance tests enforce frame-time and memory budgets.

## Result Fields

Scalar overlays expose two display modes without changing solver data:

- `Raw cells` renders normalized solver sample locations for audit and mesh review.
- `Smooth field` blends the same samples for spatial inspection. It is a derived display interpolation and never changes extrema, limits, probes, or report values.

The 3D viewport also exposes a `3D contour` plot style. It constructs separate regularized surfaces for each solved net/layer group, rejects unsupported vertices before triangulation, elevates the normalized scalar as height, and draws marching isolines over the colored surface. The contour mesh is a display product only. Cursor readout returns the nearest solver-owned sample, while report statistics continue to use the complete normalized result bundle. Engineering reports use the same visual contract and default to the interactive 3D contour view.

Current, current-density, electric-field, and magnetic-field views expose an independent vector-arrow toggle and scale. Layer visibility, isolated-net state, result scope, and analysis-net filtering apply to scalar and vector data before rendering. The 2D layer overview uses the same result range and synchronized camera state as the single-layer layout.

Engineering analytics are centralized in `app/src/resultAnalytics.ts`; the Results panel and HTML report therefore use the same field extrema, probe summary, via-stress ranking, and approximate short-duration copper-fusing screen. See `docs/RESULT_VISUALIZATION_AND_LIMITS.md` for equations and validity limits.

## Current Limitations

- A component model cannot be accurate when its source board references a missing
  local file. The ebrake fixture currently reports 19 unresolved references;
  SPIKE displays that count and does not label those components as modeled.
- Scene export currently requires a compatible local KiCad installation. Packaged
  project scenes remain viewable without KiCad after export.
- Custom pad primitives and polygon holes need additional fixture coverage.
- The browser preview parser is not yet the authoritative project importer.
- Layer-filtered 3D uses normalized electrical board geometry with the separate
  authoritative KiCad component scene. A single component GLB cannot yet move
  mixed top- and bottom-mounted components independently.
- Exploded stackup and layer isolation are implemented for normalized geometry;
  accurate per-layer 3D solids remain future worker work.
- Measurement tools, saved views, revision overlay, STEP conversion/preview, and
  writing assigned model paths back to KiCad remain future viewer work.
