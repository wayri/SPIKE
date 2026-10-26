<!-- SPDX-License-Identifier: Apache-2.0 -->
# Field and conductor result presentation, 26 October 2026

This record covers presentation changes, not new numerical methods or release
qualification. See the [reference brief](../COMSOL_INSPIRED_FIELD_RESULTS.md).

## Implemented

- Explicit volume, half-volume cutaway and supplied-line presets; unsupported
  representations remain disabled. A cutaway is not a reconstructed plane.
- Fixed-history color ranges, optional explicit manual endpoints, reset, exact
  cell extrema/coordinates and a selected sample marker. Generated flow keeps
  a fixed saved velocity range; manual editing there remains disabled.
- Composite field import/export with explicit shared-source registration,
  identical coordinate units and exact matching saved times. Solid samples
  retain their own temperature values and independent legend.
- Geometry context opacity, adjustable sample size, and transient frame sync.
  Temporary CAD material overrides restore properties after each render,
  including exceptions, and do not clone or dispose shared materials.
- Actual cuboid cell sizes recovered from the retained native OpenFOAM mesh
  for all 1,256 solid cells in the example. Strict corner/face, cell-order
  center and region-volume checks preserve numerical arrays and timestamps.
  These are proxy-model volume cells, not imported STEP surface temperatures.
- Persistent labeled analyzed-net highlight/isolation controls and a layered
  transparency icon with an explicit Opaque/Transparent label. Normal-board
  isolation uses actual result nets; setup or selected nets are not added.
  Assembly highlighting uses explicit occurrence identity. Assembly analyzed
  isolation is disabled pending a complete occurrence-scoped implementation.
- Selection fill is reduced to preserve result colors only on nets that have
  scalar result samples. Unrelated nets no longer become 8%-opacity outlines.
  Translucent and analyzed-only inspection exposes filled result surfaces
  through CAD geometry; ordinary opaque display retains depth occlusion.

## Executed evidence

The focused field-volume, geometry-context, solid-overlay, viewport hook,
button-standard and TypeScript checks passed during implementation. The
native voxel scene accepted all 1,256 enriched solid cells. The reproducible
artifact helper has five tests and a source/output hash receipt beside the
[saved case](../../artifacts/unified-transient-20261026/cfd/README.md).

The additional result-inspection-depth check exercised actual Three materials
and preserved vertex colors while changing only inspection depth settings.
Copper selection, board-result geometry and viewport essential-control checks
passed. Architecture passed before the final net-control additions; final
candidate gates are recorded separately by the release owner.

A local Chrome source harness rendered the real board with fluid paths and
two independent legends. Playback was observed at frame 4/5 and then 5/5.
That initial observation exposed the occlusion problem and preceded the
ghosted context and exact voxel correction. It therefore does not establish
visual acceptance of the corrected view. Subsequent desktop control was
blocked by URL verification and then Windows cursor-access errors.

## Open acceptance and physics limits

Final native installed-window and narrow-window acceptance, installer payload
checks and release lifecycle evidence are not asserted here. The installation
from the earlier unified-playback work is a different binary identity.

The saved example is only 0.020 s of startup, with three prescribed package
loads and declared cuboid geometry. It does not contain board copper Joule
losses, detailed package internals, resolved STEP leads, measured material
qualification, or a complete mesh/time-convergence and energy-validation study.
Automatic pairing of assembly terminal temperatures with an air history is
withheld when authoritative solid timestamps/history are missing. Composite
import does not infer registration, resample times or compute new physics.
