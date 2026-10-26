# Unified viewport playback - 26 October 2026

## Scope

One main-viewport player for saved layered board thermal, spatial PI transient,
and admitted CFD field-volume frames. Physical timestamps are retained; the
default review spans eight seconds. Airflow markers follow displayed computed
curves at presentation speed and are not time-accurate particle trajectories.
See [the workflow](../VIEWPORT_TRANSIENT_PLAYBACK.md).

## Executed source checks

- Unified controller: pause, seek, restart, targeted source selection, source
  replacement, unchanged-source scope transition, RAF cleanup, and microsecond
  review timing passed.
- Layered thermal: source cell coordinates, thickness/layer order, exact saved
  temperatures, malformed frame rejection passed.
- PI: selected quantity must occur in returned transient frames; a static DC
  field cannot mask the changing transient quantity.
- CFD adapter: exact retained timestamps/scalars/vectors/native curves survive
  admission; failed results and malformed retained fields are rejected.
- Flow: zero velocity and sparse unsupported points do not enable motion;
  marker buffers follow existing eligible paths and are disposed normally.
- Full transient UI aggregate passed after routing old controls through the
  shared player. Thermal UI aggregate passed after replacing an obsolete
  literal button assertion with executed guided-run blocker checks.
- Architecture and bounded whitespace checks passed.
- Full Rust tests in the beta snapshot: 81 passed, one ignored.
- Final-r4 production frontend: TypeScript passed; Vite built 2,504 modules.
  Both field-volume and transient UI aggregates passed after integration.
- Backend geometry, stream export and service checks: 35 focused tests passed,
  including X/Y/Z inlet orientation and malformed native output. Python
  compilation passed.

The first full Python attempt was stopped because the sandbox temporary
directory denied nested writes and cleanup. A focused reproduction confirmed
the environment failure; the same tests passed with a dedicated D: temporary
directory. The full suite then ran 5,728 tests: two failures, five errors,
87 skips. Four timing-related failures passed their single sequential retry
under lighter load with unchanged budgets. Three parity-backlog errors remain:
the SI08-S05 receipt pins stale validator source hashes. This unrelated evidence
was not fabricated or silently refreshed. See
`artifacts/unified-python-tests-rerun-20261026.md`. The full suite is not green.

## Numerical evidence and limits

`artifacts/unified-transient-20261026/pi` retains the exact pinned ESP32 board,
request, raw native PEEC result, and verification. Twelve saved frames span
0--10 microseconds. This is the largest supported connected same-layer
`+3.3VMCU` track component, not a whole-board qualification. The existing
backward-Euler run heavily damps unresolved high-frequency dynamics; use it
for approximate playback review, not PI sign-off.

The former slab-only CFD example does not demonstrate flow around component
bodies. Rejected component meshes and their checkMesh diagnostics are retained
under `artifacts/unified-transient-20261026/cfd`. A prepared mesh alone does not
prove an admissible solve or flow deflection. The final declared-cuboid case
passed all five strict region mesh checks and completed ten steps to 0.02 s;
the board-only baseline passed both region checks and also completed. Five
saved field frames and 16 native tracks per frame are retained. No sampled
track point enters a component proxy. Comparison ratios are qualitative and
mesh-confounded, not isolated quantitative obstacle-effect evidence. Exact
package STEP quality failures remain open. A separate geometry-preserving
subdivision passes strict checks on the original unsnapped polygon-prism
proxies and returned recovered native fields after bounded postprocessing;
see [its evidence and limitations](ASSEMBLY_AIRFLOW_SUBDIVISION_20261026.md).
Its 22 focused tests and architecture check passed. See also
[the independent geometry review](RECTILINEAR_CHT_GEOMETRY_20261026.md).

The separate native layered-board thermal case retains seven frames from
0--600 s and 3,465 board cells per frame. It was reproduced with the staged
0.4.2-beta worker. The illustrative 1.35 W case warms from 25 to 80.497524 C;
maximum reported power-balance error is 4.82e-13 W. This approximate prescribed
convection model does not solve airflow or package-junction transients.

The frontend layout review moved the player into the viewport's existing flex
column, above the actual board canvas; it must not occupy an implicit cell of
the outer named workspace grid. PI activation selects its workspace, and old
keyboard, context and result-panel controls share the new clock.

## Installation status

Pending final worker/installer packaging and native installed-window checks.
Source tests and a production web bundle are not evidence of installation.

To obtain installation headroom, 3,150 inactive Rust incremental files were
preserved byte-for-byte under `D:/SPIKE-cleanup-preservation-20261026` before
exact-file removal from the old root debug cache. The manifest, receipts,
executor fixture tests and retained-source/binary guard checks are under
`artifacts/unified-transient-20261026/release`. Logical removed bytes were
3,013,652,135; observed C: free-space gain was 2,434,166,784 bytes. Source,
executables, libraries, debug symbols and project results were retained.
