# Multi-board workspace verification — 2026-10-03

## Changes

- Home → Multi-board, Project → Multi-board workspace and the viewport toolbar open a dedicated assembly workspace. The existing MCAD editor remains available.
- The workspace shows board occurrences, retained design IDs, component/net/layer counts and per-design visual diagnostics. It provides direct 2D/3D, layer, net and connector-table entry points.
- Pending project changes require a save before manifest-bound assembly mutation. Editor drafts survive section jumps and prop recreation; leaving a dirty draft is explicit.
- Duplicate and Add active design instance preserve source elevation and angles and use rotated board-envelope clearance (30 mm), rather than coincident starter placements.
- A compact assembly bar selects/hides boards and opens scoped managers; placement, angle, snap and exploded-view controls expand on demand.
- Layer/net managers start on the selected board occurrence. Equal net names are separate until explicitly linked.
- Duplicate/reversed Edge.Cuts drawings no longer produce a 1 × 1 mm Arduino display envelope. Display contour joining deduplicates coincident edges; all source drawing records remain retained and the envelope includes every outline drawing.
- Assembly SVG pages map back to source board coordinates using the normal viewport's centered page convention. Shelf layout and fit bounds include the full plotted page.
- The converted relay shield's 25 `UNDEFINED` graphical annotations are reassigned to `Dwgs.User` only in a temporary visual export copy. Electrical objects are rejected from this repair, and the retained source is unchanged. Per-board diagnostics disclose the repair.
- Local model staging preserves existing project-relative assets when another substitution requires a temporary copy. Missing standard KiCad VRML references may use an exact full-package STEP counterpart; uncertain basename matches still require a confirmed mapping.

## Automated evidence

Passed: assembly workspace actions/save gate/draft protection and selected-board manager rendering; 143.9 mm board duplication and rotated-envelope clearance; complete assembly 2D/3D geometry, 1004→5 copper draw-call batching with exact picks; placement, hole/edge snap, exploded display, visibility/result binding; net viewer; parser (32 copper layers); architecture; TypeScript and production frontend build.

- Rust library checks: 35 passed, 1 ignored. Embedded native debug build (`cargo build --offline --features custom-protocol`) succeeded after removing obsolete compiler incremental outputs to recover disk space.
- Independently rerun model/core/staging checks: 72 tests passed, 1 skipped, using the repository Python 3.12 virtual environment.
- Full Python discovery before the resolver corrections: 2,373 tests, 4 failures, 13 skips, 473.1 seconds. Three resolver failures were corrected and covered by the focused rerun above. The remaining release-policy test expects `PUBLIC_RELEASE_DEPENDENCY_APPROVAL_REQUIRED`, absent from the current release evidence. The full suite was not rerun after these corrections; it is not reported as green. Log: `build/multiboard-workspace-20261003/python-tests.log`.
- Real KiCad 10.0.6 shield export: 24 SVG layers (874,195 bytes) and board GLB (5,854,468 bytes), successful native exit codes, no stage errors, saved package SHA unchanged. Evidence: `build/multiboard-workspace-20261003/shield-export-diagnostic/ready-evidence.json`. The shield has 47 components and zero assigned source models; successful board export does not establish resolved component geometry.

## Runtime/build distinction

Native inspection found the installed executable at `AppData/Local/Programs/SPIKE/spike-desktop.exe` displaying version 0.2.13. It has neither the new model resolver nor the dedicated workspace. The repository frontend is 0.3.0. The current executable is `app/src-tauri/target/debug/spike-desktop.exe`, built with embedded frontend assets. Native inspection confirmed `http://tauri.localhost/` with the Vite server stopped. This is a checkout-dependent development build, not a new installer; the installed app and `.spike` file association remain unchanged.

Open the current executable, then Home → Open → `build/multiboard-workspace-20261003/arduino-r4-relay-demo.spike`, then Home → Multi-board.

## Native observations and pending visual acceptance

The real two-board Arduino project was reopened in the embedded native build. The workspace displayed both retained occurrences, the selected shield's net manager displayed its own nets, and the pin table displayed three explicit inter-board mappings. Actual captures: `workspace.png`, `shield-nets.png`, and `pin-links.png` in `build/multiboard-workspace-20261003/`. The workspace capture predates the shield export correction and retains its then-current diagnostic; it is historical evidence, not final visual acceptance.

Native 2D inspection exposed the SVG origin defect subsequently corrected above. The final rebuilt executable loaded the project and rendered the 3D assembly. Before final 2D/3D screenshots and a narrower-window check could be completed, Windows locked. No automation was attempted through the lock screen. Final native screenshots of the SVG correction and the narrow layout remain pending desktop unlock; automated layout checks do not replace those visual checks.

Real Arduino UNO R4/relay-shield and Raspberry Pi CM4IO/Sailor HAT fixtures remain in ignored build directories. Source/model completeness differs by board; unresolved geometry remains reported. Reduced PI/SI, RC thermal and magnetic-loop models remain approximate. Full-wave assembly EM and numerical production qualification are not established by these UI changes.

## Net label presentation correction

Assembly net lists now show names without canonical or occurrence IDs. Connector
pin choices show pin numbers and net names without UUID suffixes. An unnamed net
has the label `Unnamed net`; its retained ID is never used as a display fallback.
Saved connector mappings, React keys and selection callbacks keep their original
identities, so identical names on separate boards remain independently selectable.

The assembly workspace render checks cover named, unnamed and unresolved pin
labels, absence of internal net IDs, and selecting `GND` on board B with its exact
canonical ID. Workspace/draft, board-manager and architecture checks passed.
No new native screenshot was captured for this label correction.

## Shared manager presentation

The assembly layer tab now embeds the same `LayerManager.tsx` as the main
viewport. The assembly net tab and original PI manager render the same
`NetCatalog.tsx`. This replaces the assembly checkbox/slider tile grid with
the standard grouped layer rows and restores the searchable, selectable net
table with geometry statistics. Physical stack rows and counts come from the
selected retained design. Layer group toggles, isolation and reset send one
atomic native action and preserve all other board occurrences.

Passed: workspace render/selection and board-scoped bulk actions; canonical
geometry statistics (arc tracks, reversed via spans, distinct pad components,
missing inventory); original PI roles/loop UI and selection after catalog
extraction; native action validation; layer inventory/stackup; unsaved project;
form/table contrast; architecture; generated Help checks; TypeScript/production
frontend and embedded native builds.

The updated native preview opened the real Arduino UNO R4/relay-shield fixture.
Native manager captures and narrow-window inspection are pending: concurrent
desktop input repeatedly changed focus and prevented the manager-open action.
This is not reported as visual acceptance of the updated manager screens.

## Graphical connector editor

Connector links now use paired board/connector cards with a connection glyph,
readable names, pin/net selectors, and applied/pending/incomplete status cues.
Search covers names and pins, incomplete/stale selections cannot be applied,
and saved pin edits can be discarded without changing the canonical mapping.
The endpoint layout stacks vertically at 640 px. Pagination bounds rendering
to 100 connections. Internal net IDs are still excluded from labels.

Focused workspace/card interaction checks passed for unchanged saved rows,
pin edits, save/apply callbacks and retained identities, invalid pins, disabled
pin selection, and empty search results. Board-manager and native session
regressions, TypeScript, architecture and generated Help checks also passed.
Native visual inspection was blocked when Windows locked; no input was sent
through the lock screen. Graphical-editor screenshots remain pending unlock.
Production frontend and embedded `spike-desktop` builds completed successfully.
The standard development executable contains the final graphical editor; the
already running preview executable still contains its earlier embedded assets.

## Actionable notifications

Model notification headings and **Resolve models** now open the resolver at the
active retained design and first missing component. Individual board diagnostics
open the same resolver scoped to their design. Import warnings reopen staged
import details, connector warnings open the link manager, and **Review all issues**
opens the Issues dock. Navigation closes the notification popover. Repair controls
are disabled before the board inventory is ready; failed scenes retain retry.
Raw timing and loader metrics are collapsed under **Load diagnostics**.

Passed: notification action callbacks and close-before-navigation order; warning,
error and unavailable-board states; resolver initial board/component targeting;
import workflow; assembly tool sessions; parser; TypeScript; architecture; generated
Help checks; production frontend and embedded native builds. Rust library checks:
35 passed, 1 ignored.

Native click and window-size checks remain unverified for this change. The Computer
Use helper reported an active request on launch and again on re-observation; no
notification screenshot or runtime action is claimed.

Full Python discovery: 2,375 tests in 438.749 seconds, 1 failure, 2 errors and
13 skips. The release-policy failure still expects
`PUBLIC_RELEASE_DEPENDENCY_APPROVAL_REQUIRED`. Both model-index errors report
`sqlite3.OperationalError: unable to open database file` at the default local
cache. Log: `build/notification-python-checks.log`. This suite is not green.
The two affected model checks passed when rerun with `SPIKE_MODEL_INDEX_PATH`
pointing to a writable, isolated index in `build/notification-test-model-index.sqlite3`.
No model-resolver backend changes were made for this notification fix.
