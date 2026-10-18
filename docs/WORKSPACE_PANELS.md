# Focus workspace and on-demand tools

SPIKE starts with its board or assembly viewport filling the workspace. **Menu**
opens a reserved command panel; it never covers the board. Browse a category,
choose a submenu, then select a command. Back returns one level. Search matches
commands and their category paths, including disabled tools. Existing file,
analysis, extension and keyboard actions retain their original handlers.

**Menu > Analyze > Workspaces** exposes the complete tools for Home, PI, HF / SI, EM, Thermal,
Mesh, Solve, Probes, Results and Reports. **Viewport tools** contains camera,
selection and display controls. **Result display** contains controls for actual
saved fields. **Design & view > Workspace panels** opens the navigator, studies, analysis and
selection inspector, Issues, Probe table, Power tree, Console or Notifications.
**Tools > Windows & tools** restores existing tools and explicitly detached windows.

Setup forms, power/channel trees, circuit/SPICE workspaces, study editors,
model managers and other large tools open as full-width **workspace tabs**.
Their tabs appear beside **Board & results**. Switching tabs keeps existing
editors mounted and preserves local inputs, undo history and running jobs.
Menu overlays keep their current section, filter and scroll while hidden, and
leave the visible editor or viewport behind them intact. View and Menu toggle
them open again; docked tools also retain their per-tool expanded state.
Left/Right and Home/End navigate the editor tabs. Hide returns to the viewport;
it does not discard a draft. Each editor's own Close/Apply/Discard actions
retain their existing validation and confirmation behavior.

Spatial inspectors (selection, layers, result display and field controls),
navigation and the console remain docked beside the viewport. They retain
Expand/Restore and bounded resize controls. Setup documents use the full
workspace automatically. Detach and per-tool scale remain available for both
presentations; native secondary windows remain explicit user actions.

The power-tree toolbar keeps primary drawing and review controls compact.
Sources and Edit expose secondary commands on demand. Palette and properties
adapt to available editor width; the canvas uses the active Graphite + Teal,
light or high-contrast theme. **Circuit** opens the existing circuit workspace
as a separate tab for board-linked models, explicit pin bindings and Studio
feedback. This navigation does not convert an unreviewed power graph into a
SPICE circuit or infer missing model parameters. Existing reviewed model and
analysis admission rules remain authoritative.

The permanent chrome contains Menu, project identity, search, 2D/3D, Layers, Fit
and View. The ribbon, extra toolbars and persistent tool shelf are accessed on
demand. Alt menu mnemonics and F10 open commands; Ctrl+K retains universal search.
The professional-dark theme is Graphite + Teal. System and high-contrast themes
remain available. PCB layer colors and engineering result scales are unchanged.

Assembly workspace, placement and board layer/net/link managers use embedded
components and existing occurrence-scoped actions. Their connector-draft checks
remain owned by the manager. Explicit assistant, schematic, detached plot and
report windows retain their native window behavior.

## Saved studies and result provenance

The study tree groups cases and saved runs. Activating a case restores setup; a
capture without result data remains a setup capture, not a completed simulation.
Unsupported, approximate and validated capabilities remain separate. Search,
archived studies and keyboard navigation retain their existing behavior.

## Verification

The Focus command tests cover nested discovery, disabled actions, native file
pickers, toolbar controls and command handlers. Panel tests cover one visible
slot, hidden draft preservation and reactivation. Visual acceptance must use
the actual application at wide and narrow window sizes with long names and
open inspectors, plus a real saved assembly when assembly behavior changes.

## Clean chrome

Clean uses the header workspace dropdown without a duplicate workspace button
row. The large command ribbon and optional quick-tools bar start hidden; they
return only through explicit enable actions. The current chrome migration
clears old Clean always-expanded preferences once. Classic keeps its menus and
ribbon. Mesh/Solve use a compact stage/domain/net strip with a Setup disclosure
and a primary Extract, Run or Stop action. Detailed controls remain mounted.
Assembly placement uses a short board selector and icon controls; its overflow
actions open in a portal so viewport clipping cannot hide them.
