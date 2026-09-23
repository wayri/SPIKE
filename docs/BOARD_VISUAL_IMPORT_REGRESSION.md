# Board visual import regression — 2026-09-05

The native import payload disabled layout export, leaving non-demo boards without
KiCad SVGs for text, mask, paste, fabrication and documentation layers. The 3D
fallback sampled tracks/pads/vias above 40,000 features and drew each through-hole
pad only on its primary layer. These display omissions did not alter solver data.

Changes:

- Include the complete drawable layer inventory in native/source visual payloads.
  Export all layers in one KiCad process; map display aliases to canonical layer
  names, with bounded single-layer fallback for unrecognized filenames.
- Use STEP substitution for legacy VRML references, including installed STEP
  counterparts when the VRML file is absent. Cache reference resolutions and
  build the basename fallback index once per export.
- Avoid CAD boolean fusion for display exports. Three.js merges render geometry
  after loading, retaining all triangles without the CAD fusion cost.
- Preserve every procedural track, pad, via and component; dense boards reduce
  curve tessellation. Draw pads on every declared physical copper layer.
- Allow up to 256 display artifacts while retaining the 96 MiB byte limit,
  SHA-256 verification and self-contained GLB requirement.

Validation:

- Local `arts-1_irca.kicad_pcb`: two GLBs plus all 29 drawable layers exported in
  31.2 seconds. The earlier per-layer process approach took 118.6 seconds.
- The real Three.js GLTF loader and production scene preparation loaded the board
  (9,163 source meshes → 7 batches) and components (15,559 → 52), preserving bounds.
- The rebuilt frozen worker repeated the actual import in 33.1 seconds. Its
  20,374,603-byte payload passed desktop SHA-256/Blob materialization, both GLTF
  loads, and all 29 SVG coordinate-frame checks.
- Synthetic 2,000-component preparation preserved all 24,000 triangles and both
  board sides, producing eight batches in approximately 50 ms. This is a geometry
  preparation test, not an interactive FPS benchmark or qualification of every
  2,000-component design.
- Regression coverage includes 32-layer copper selectors, 100-artifact layer
  payloads, missing legacy STEP counterparts, and 2,000 missing model references
  using one library traversal.

The real board still reports legacy model failures for J1, L1 and U4. Their exact
old library filenames were absent from the checked project model directory and
installed KiCad 10 model library. J1 and L1 also contain separate local STEP model
references. The exporter retains these warnings; it does not invent replacements.

The initial installed-desktop inspection was not completed because app approval
timed out. The follow-up below verifies the production rendering components in a
local browser fixture; it does not claim an installed-desktop end-to-end test.

Run `node app/scripts/test-dense-board-scenes.mjs [board.glb components.glb]` to
exercise the production Three.js preparation functions with optional local GLBs.

## Automatic staged import — 2026-09-06 / 0.2.9

The JTYU-TSMC-Ki10 example has 873 components, 2,852 pads, 1,127 vias, 7,333
tracks, 192 zones, six copper layers and 28 drawable layers. Its 18,427,491-byte
source parses in approximately 0.8 seconds. The detailed CAD board GLB alone was
171,103,892 bytes, exceeding the 96 MiB artifact budget. Encoding the combined
bundle also exceeded the native host's 256 MiB stdout limit.

Import now parses off the UI thread, then requests layout, board and component
stages separately. Each verified stage becomes usable immediately. A nonblocking
progress panel reports completed stages, elapsed time, cancellation and retry.
Clean imports dismiss the panel automatically. Failures retain completed stages
and do not prevent later stages from loading.

Sources of at least 8 MiB, or designs with at least 25,000 tracks/pads/vias, use
native copper geometry automatically. Smaller designs retry this mode if the
detailed board export fails. KiCad supplies the lightweight board coordinate
frame and the real component models; the production layer renderer preserves
source tracks, pads, zones, vias and independent layer controls. Byte limits,
hash checks and the self-contained GLB boundary remain enforced per stage.

The missing-model wizard groups unresolved paths across all affected references.
A native file selection grants access to one replacement and reruns only the
component stage. Overrides apply to a temporary export board; the user's source
board is not rewritten. Missing or unconvertible models remain identified and
use footprint placeholders. JTYU's F1–F8 share the absent
`${KIPRJMOD}/packages3D/3-122-717.stp`; selecting one actual replacement repairs
all eight. No substitute has been invented or selected for that missing asset.

Validation:

- JTYU staged payloads total 41,762,958 artifact bytes: 21,204,606 bytes of layer
  SVGs, a 2,108,624-byte board shell and 18,449,728 bytes of component models.
  Initial source-worker stage times were approximately 7.3, 4.8 and 32 seconds.
- All 28 SVGs passed coordinate-frame checks. Both GLBs passed the real
  SHA-256/Blob materializer and Three.js loader. The component scene's 59,929
  meshes merge to 24 display batches with unchanged bounds.
- The production BoardViewport mounted in a local browser fixture displays the
  real board and models, reporting both scenes ready and 79 draw calls. Its
  stationary 5 FPS is the viewer's explicit idle cap, not an interactive FPS
  measurement. The actual inner copper SVG was inspected in 2D.
- That visual check caught another blank-view cause: the 2D copper tab remained
  on a layer hidden through the layer manager. It now follows a remaining
  visible copper layer while preserving All/Overview modes and all-hidden intent.
- 46 focused Python tests, 31 Rust tests, TypeScript/production build, staged
  workflow tests, payload tests, layer inventory and scene policy checks pass.
  Workflow coverage includes automatic copper recovery, missing-file grouping,
  replacement-only retry, unrelated-stage failure retention, resource disposal,
  cancellation and late-response races.
- The rebuilt 0.2.9 frozen worker repeated all three stages for both boards.
  Its outputs passed the production payload materializer, both GLTF loads and
  every SVG coordinate-frame check: IRCA 29 layers / 20,374,491 bytes; JTYU 28
  layers / 41,762,958 bytes. Captures are in local `artifacts/irca-0.2.9` and
  `artifacts/jtyu-0.2.9`. Concurrent packaging and verification increased timings;
  these concurrent runs are correctness checks, not import-speed benchmarks.

Developer fixtures: `app/scripts/import-preview.html` checks the real progress
panel. `app/scripts/board-visual-preview.html` accepts a local board and captured
stage response JSONs to mount the production renderer. These are development
entry points and are not included in the production application bundle.
