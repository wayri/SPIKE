<!-- SPDX-License-Identifier: Apache-2.0 -->
# Harness engineering validation, 2026-10-09

## Scope

Shared connector/wire/splice editor, exact assembly pin-map conductor retention,
power/return subset DC, supplied uniform-mode SI, saved-result admission,
bounded 3D conductor presentation/picking and unsupported EM requirements.
See [workflow and limitations](../HARNESS_ENGINEERING.md).

## Checks completed

- Full Python discovery: 2936 tests completed in 1607.577 seconds, with 22
  skipped and no failures (2914 passed). Logs are retained locally at
  `.local/harness-full-python.log`.

- Focused Python integration: 39 tests passed across harness SI/EM, actual worker
  transport, PI, authoring, assembly conductor persistence and virtual-harness
  graph round-trip. Includes 100,000-point/16 MiB EM output rejection before
  repeated route copies.
- Six frontend harness checks passed: diagram/splice authoring, assembly bridge,
  actual backend SI result presentation, bounded 3D projection, PI failure
  states, and connector/pin editing. Regressions include Python-sorted saved
  JSON, failed/malformed numerical results and incomplete/duplicated pin maps.
- TypeScript and production frontend build passed after the final admission and
  individual-conductor selection changes. Vite reports existing large-chunk
  and mixed static/dynamic-import warnings; this is not a performance claim.
- Parser, button/control standard, architecture and scoped whitespace checks
  passed. Documentation links/format checks passed for the affected guides.
- Rust host: 41 tests passed, one ignored.

## Native interaction evidence

The owned Tauri debug window rendered the shared diagram at 1320-pixel and
700-pixel client widths. Wide-layout picking opened the differential wire
inspector with pair mate, ordered pair type and explicit pitch. Narrow layout
kept the inspector below the diagram, wrapped add-wire controls and retained
horizontal table/diagram scrolling.

The existing retained Sailor Hat source and KiCad models loaded as two board
occurrences. A separately authored synthetic six-wire visual fixture contains
power, return, signal, other and shield roles plus a pitched differential pair.
Picking returned wire `W1`, and the final selector highlights only that wire.
The net viewer minimized to the bottom tool shelf. Local evidence is retained
in `.local/harness-editor-wide.jpg`, `.local/harness-editor-narrow.jpg` and
`.local/harness-3d-picking.jpg`. These screenshots are visual evidence, not
electrical pinout or field validation. Desktop input interruptions were
re-observed before continuing with the user's permission.

The retained preview measured roughly 4.7-4.8 FPS and 56-59 ms per render on
this busy machine. No smooth-viewport or accelerated-rendering claim is made.
The fixture uses already retained board assets; no additional upstream board,
model or dataset was downloaded for this increment.

## Integration gate and limitations

The required full Python suite completed successfully. The run started before
the final bounded EM-output review change; its new cases and all affected
harness cases passed in the subsequent 39-test focused recheck. This retains
the full integration gate without repeating unchanged expensive numerical tests.
No installer, release or installed application update is produced by this step.

Uniform SI requires complete supplied loop/modal RLGC, exact conductor length
and provenance. Geometry-derived RLGC, branched-channel SI, common-mode
conversion, crosstalk, shield transfer and full-wave harness radiation remain
unimplemented. EM readiness never claims a solved field. Display pitch controls
turns but display radius/spacing do not establish physical cable geometry.
Numerical human review remains required before release.

The remaining geometry-derived multi-conductor SI and executable harness EM
requirements were sent to the existing **Build modern SPIKE solver suite**
chat under the user's standing handoff authorization. That work was accepted
and is in progress; it is not counted as implemented capability here.
