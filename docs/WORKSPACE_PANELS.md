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

One tool is visible in the shared panel slot. Opening another tool changes the
visible panel while retaining mounted inputs and drafts. **Hide** returns the
space to the viewport without closing the editor. **Tools > Open panels** restores
hidden editors. Each tool's own Close/Apply/Discard controls keep their existing
behavior and draft checks. Background jobs continue when their panel is hidden.

**Expand** fills the workspace for larger editors, tables and plots. **Restore**
returns the viewport beside the tool. Drag the panel's left edge to resize it,
or focus its resize control and use Left/Right. Width is bounded and remembered.
At narrow window widths the panel stays in a bounded right column instead of
covering geometry. Closed panels have no rail, tabs or reserved width.

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
