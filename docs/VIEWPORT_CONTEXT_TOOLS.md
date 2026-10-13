# Viewport context tools

Right-click a board object or a result point to open a context menu. Its header
shows the workspace, active analysis mode, clicked board occurrence, object,
net, layer, available result status and solver selection. Verified net geometry
adds routed length in millimetres and track, pad and via counts.

Suggested for this context offers actions for the clicked item and active domain.
Choose a group to open its tools, or search by action name and description.
Arrow keys navigate; Right opens a group and Left returns. Escape, Tab or an
outside click closes the menu. Disabled actions explain the missing input.

## Tools

- Inspect and select: focus the clicked object, isolate its net, add a probe,
  open linked schematic/connectivity views, or clear selection.
- View and layers: fit, set the 3D orbit center, switch 2D/3D, open layer controls,
  inspect the physical stackup and control model visibility.
- Power and signal integrity: configure DC drop, AC impedance, transient PI,
  return paths, channel extraction, crosstalk, eyes/masks and ports. The clicked
  net or object is passed into the existing setup workflow. SPICE opens with
  that selection for explicit model composition.
- Thermal and EM: configure the scenario, review contacts and model assignments,
  plot saved thermal history, or add a net to the EM domain for excitation setup.
- Results: show only fields actually present in the saved result, open plots,
  play/pause saved transient frames, cancel an active operation, browse studies
  and generate a project report.
- Assembly: open the assembly, connector links, harness and tetrahedral setup.
- Context and automation: copy a bounded context snapshot, open an unsaved Python
  draft, check readiness or open the local assistant with the clicked selection.

## Identity and result limits

Analysis edits require an object in the active board source. In an assembly,
a clicked occurrence of another design must be activated before configuring its
analysis. Saved result fields require an explicit occurrence match on multi-board
projects; an equal net name on a different board does not establish a match.

Configuring a workflow does not execute or validate a solver. Field display and
playback use saved data. Thermal history requires actual saved transient samples;
the popup reports missing data instead of inventing a time series. Context scripts
are drafts and do not execute automatically. Reports describe the project rather
than claiming a solve of only the clicked object.

The copied/script context also includes source dimensions, terminal voltage/current
settings and exact saved base-field samples with explicit units. These samples
are labelled as base-result values rather than interpolation at the current
playback time. Thermal-cell context retains its saved value, layer and model
status. Context scripts reject oversized snapshots without truncating data.

Run `npm run test:viewport-actions` in `app` for the focused menu and identity
checks. Native visual verification still requires the updated desktop frontend.

## Net focus and readable menus

Selecting a net keeps its saved copper routes vivid while other copper is gray
and subdued. This applies to single-board and assembly 2D/3D views. Clear the
selection to restore the original layer colors and opacity. Assembly selection
is occurrence-scoped; matching names alone never highlight another board.
Only saved connector links propagate net focus. Focus changes display materials,
not retained geometry, layer settings or simulation data.

Viewport context menus use an opaque theme surface so underlying board geometry
cannot obscure their text. All keyboard navigation and search remain available.

Retained assembly geometry also remains available when an active board snapshot
contains only its outline while visual assets are still loading. Existing model
and layer assets are preserved. A genuinely geometry-free design is not filled
with fabricated copper.
