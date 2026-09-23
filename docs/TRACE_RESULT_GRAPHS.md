# PI and SI trace graphs

The results workbench offers a net overview, individual trace/element tabs and
comparison of up to 16 selections. Choose a returned metric and net, then open
an identifier or select its comparison checkbox. Search narrows long lists.
Only the active graph is mounted. The window can be detached for another screen.

- **3D spatial** places the returned samples and explicit solver faces in board
  coordinates. X, Y and Z are millimetres; samples lacking Z are shown at zero.
- **3D field height** uses X/Y board coordinates and the selected quantity for
  height. The vertical axis names the quantity and its units, not physical Z.
- **2D samples** plots returned sample order against the quantity. It does not
  invent path distance or connect samples into an inferred electrical route.
- Impedance sweeps use frequency in Hz and magnitude in ohms. A network sweep
  does not become a spatial field merely because the board is visible.

Trace ownership uses returned source identifiers, or an exact mesh element to
source mapping with matching net and layer. Where that mapping is absent, the
UI retains the solver element ID or explicitly marks the samples unassigned.
It never selects a nearby trace as a substitute.

Explicit faces are triangulated without filling gaps between conductors.
Shared face vertices reconstruct display colors within a net/layer. This is
presentation interpolation, not a new solve or accuracy claim. Hover values
remain the original source samples. Rendering does not modify the result.
The active plot admits at most 20,000 samples and 100,000 face vertices; the
shown/total count exposes display decimation, which retains scalar extrema.
Oversized or unsupported faces remain sample markers. Source results remain
available through the normal result export.

Plots load the installed Plotly bundle on demand, without a CDN. A failed plot
shows a retry action. Resize, camera retention and disposal use Plotly's
[documented lifecycle API](https://plotly.com/javascript/plotlyjs-function-reference/).
The native report exporter uses a separate self-contained runtime; see
[Engineering reports](ENGINEERING_REPORTS.md).

Validation: `node app/scripts/test-trace-result-plots.mjs` checks units, net and
layer separation, exact trace ownership, source immutability, continuous face
colors, exact hover samples and bounded rendering. The browser fixture at
`app/scripts/trace-results-preview.html` contains clearly labeled synthetic
rendering data; it is not an analysis of Marble or a solver qualification.

Failed, blocked, cancelled, unsupported and failed-to-converge bundles do not
provide trace plot fields, even when partial scalar or impedance arrays remain.
An explicit `solved: false` or failure stage also suppresses plotting. The
original status, partial evidence and numerical-quality provenance remain
unchanged for diagnostics; successful approximate results retain that label.

The visual comparison used the user's local wayriCAD documentation and
`quick_pi_plugin/help-results.png` (Marble Net-(R161-Pad1)): geometry-matched
field colors, clear units and source markers. No wayriCAD implementation code
or assets were copied into SPIKE.
