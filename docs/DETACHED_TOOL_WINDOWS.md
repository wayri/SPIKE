<!-- SPDX-License-Identifier: Apache-2.0 -->

# Detached Results and Probe Windows

SPIKE can present Results controls/analytics and the Probe table in separate
operating-system windows. A native Tauri build creates decorated resizable
webview windows that can move across displays. Browser development opens a
same-origin popup; the browser may require the user to allow popups.
Native and document titles identify the SPIKE tool. A browser's origin or
security strip (for example `127.0.0.1` in development) belongs to browser
chrome and cannot be removed by the tool's theme.

The main workspace remains the state authority. `detachedToolWindows.tsx`
transports bounded presentation snapshots and user actions. Results controls
such as field, layer, scene, and PI/SI selection are actions for the main
workspace to apply. Probe formula edits and add/delete operations follow the
same route. The detached view changes only after the main workspace publishes
an updated snapshot, which keeps saving and project recovery on the existing
application path.

`resultsToolSnapshots.ts` is the pure presentation adapter. Probe snapshots use
the same `buildProbeRows` and formula evaluator as the docked table. Results
snapshots expose only modes supported by the supplied result and include scalar
minimum, mean, P95, and maximum summaries from `resultAnalytics`.

For probe snapshots, formula rows can mark the name and expression cells with
`editActions` (for example `rename-formula` and `edit-formula`). Editing is
committed on Enter or focus loss. Toolbar controls support `formula-add` and
`export`, while row actions support probe/formula deletion and other stable-ID
operations. These names are application action IDs rather than native commands.

Each snapshot is limited to 2,000 rows, 32 columns, 64 controls, 12 row actions,
and 512 characters per text value. Larger datasets remain available in the
authoritative project and should use the existing export workflow. Closing or
redocking a window does not delete data. The detached bootstrap does not mount
`App`, so it does not start a worker or own solver state.

The three child labels have only Tauri event permissions. Window creation,
focus, and close permissions belong to `main`. The event payload is not a
domain or solver contract and must contain only display values and stable IDs.
Each child receives a random per-window token. Native event envelopes with a
wrong token are rejected; browser fallback uses a token-scoped
`BroadcastChannel`, so separate SPIKE tabs cannot exchange tool state.

Current scope does not duplicate the WebGL board viewport. The Results window
provides result selection controls, status, and tabular analytics while the
main workspace owns the 2D/3D scene.

Trace graphs use the separate `trace-plots` child kind and lazily render the
checked-in `TraceResultsWorkbench`. Its display-only payload is capped at
100,000 field samples, 5,000 mesh cells, and 50,000 impedance points. Sampling
is deterministic and preserves source order, endpoints, and the complete
vertex topology of each retained face (items above the per-face 256-vertex
display limit are omitted). The child reports exact shown/total counts; project
saves and exports continue to use the full authoritative result.
