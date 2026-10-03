# Shared plot interface

`app/src/PlotlyChart.tsx` is the compatibility entry point for
`InteractivePlot.tsx`. Result traces, impedance, near-field, radiation,
extension plots and SI workflow/channel charts use the same interaction shell.
The renderer is loaded on demand. Existing domain adapters continue to own
samples, units, gaps, cursor measurements, result status and export reports.

## Navigation and clipboard

- Ordinary wheel movement scrolls the containing panel. Ctrl+wheel zooms
  around the pointer; Shift+wheel pans a Cartesian plot horizontally.
  **Wheel zoom** optionally enables unmodified wheel zoom for a focused task.
- Select **Pan** or **Box zoom** before dragging. Spatial plots offer **Orbit**
  and **Pan 3D**. **Fit**, zoom buttons, and double-click restore navigation.
- **Axes** opens per-coordinate linear/log scale and automatic/fixed bounds,
  major/minor grid and hover-crosshair controls. Bounds are entered in the
  displayed units; the renderer converts log bounds to Plotly exponent ranges.
  Non-positive samples prevent switching to log rather than being hidden.
  Solid axis lines and outward ticks remain distinct from the grid.
- Focus the canvas for arrow-key pan, `+`/`-` zoom and `0` fit. Right-click or
  Shift+F10 opens a bounded, keyboard-accessible context menu. Escape closes
  the menu and returns focus to the graph.
- **Copy image** / Ctrl+C places a PNG on the image clipboard. **Download PNG**
  is available when the host does not support image clipboard writes.
- **Copy data** / Ctrl+Shift+C copies tab-separated Series/X/Y samples with
  axis labels for spreadsheet use. Field grids and spatial samples use a
  versioned JSON packet retaining X/Y/Z coordinates and labels.
- **Paste traces** / Ctrl+V adds dashed comparison traces to compatible 2D
  line or bar views. Two-column X/Y tables may have a header; three-column
  input requires a Series/X/Y header. Use **Paste X/Y table…** in the context
  menu for manual entry. Empty or unavailable clipboard reads open that editor.
  A later paste replaces the previous clipboard comparison set; **Clear pasted**
  removes it. Changing the domain view revision also clears comparisons.

Pasted data is presentation-only and is never admitted to `AnalysisResult`,
saved projects, numerical calculations or domain reports. Declared units must
match when both sides declare them; the interface performs no unit conversion.
Log coordinates must be positive. Null/blank samples remain gaps, non-finite
numbers are rejected, and imported labels cannot inject Plotly HTML. Exchange
is bounded to 2 MB, 50,000 samples and 24 pasted traces. Spatial and field maps
can be copied but cannot accept line overlays. Missing coordinate labels are
not evidence of compatible physical quantities; check them before comparison.

## Integration and verification

Pass owned display traces and a layout to `PlotlyChart`, plus a stable `revision`
identifying the metric/net/view. Rendering clones inputs before Plotly annotates
them and serializes renders so rapid view changes cannot leave a stale graph.
`PlotAxisEditor.tsx` and `plotAxisSettings.ts` own reversible axis presentation.
`plotLayout.ts` normalizes legacy title strings and enables axis margins so
units remain visible. `plotInteraction.ts` supplies anchored range operations;
logarithmic axes use Plotly's exponent-space ranges without changing samples.
`plotClipboard.ts` owns the bounded exchange contract. `onPointClick` reports
source points only, preserving SI cursor ownership.

The toolbar uses `CommandStrip`, and controls/menu use the shared table theme
palette. Narrow panels retain scroll controls and keyboard reachability.
Loading, failed rendering with Retry, disabled actions and clipboard errors
are visible states. Native clipboard behavior depends on WebView support.

Run `npm run test:plot-interaction`, `test:si-workflow-plots`,
`test:si-channel-results`, `test:trace-plots`, TypeScript/build and the
architecture check. Serve `scripts/fixtures/plot-interface.html` with Vite
for synthetic line/gap, log, 3D and field-map cases; test 1366×768 and 900×620,
a 420 px panel, long names, themes, focus, context menus and clipboard recovery.
For the same fixture in the native host, start Vite on 5173 and run
`npm exec tauri -- dev --no-watch --config scripts/fixtures/plot-native.config.json`.
The fixture labels its samples as synthetic and does not establish solver validity.

API references: [Plotly configuration](https://plotly.com/javascript/configuration-options/)
and [axis reference](https://plotly.com/javascript/reference/layout/xaxis/),
[function reference](https://plotly.com/javascript/plotlyjs-function-reference/)
and [Matplotlib tick concepts](https://matplotlib.org/stable/users/explain/axes/axes_ticks.html).
SPIKE owns the interaction/exchange implementation; no external example code
was copied.
