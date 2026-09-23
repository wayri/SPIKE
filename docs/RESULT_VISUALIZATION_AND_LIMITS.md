# Result Visualization and Engineering Limits

## Numerical versus display data

SPIKE keeps solver samples and display interpolation separate:

- `Raw cells` displays the solver-owned scalar sample locations.
- `Smooth field` is a derived visual interpolation. It does not add samples, change extrema, or alter report values.
- `3D contour` builds an elevated, layer-aware display surface with quantized color bands and marching isolines. Surfaces are split by net and copper layer, and unsupported grid vertices remain empty so the renderer does not intentionally bridge large conductor voids.
- Direction arrows use solver-owned vector fields. The arrow visibility and scale controls affect display only.
- Layer overview cards use the same scalar range as the active viewport so colors remain comparable across layers.
- Layer visibility, selected result scope, isolated nets, and analysis-net filtering apply before scalar or vector overlays are rendered.

Reports and analytics always calculate statistics from the normalized solver result bundle, never from rendered or decimated screen objects.

Live smooth fields reconstruct values on supplied face geometry. Shared vertex values are averaged only within edge-connected faces of the same net, layer, and physical position; touching corners alone do not join conductors. The 2D view subdivides these faces into bounded colored triangles without Gaussian blur. The 3D view interpolates vertex colors and contour heights on the same topology. Raw cells retain their original face values.

When face topology is absent, a bounded, deterministic subset supports a local weighted affine fit. Coordinates are normalized around the query, a 3-by-3 normal system is solved, and ill-conditioned neighborhoods fall back to inverse-distance weighting. Exact sample coordinates preserve their values; reconstructed values are clamped to the contributing range. Net/layer grouping, distance limits, and conductor masks restrict support. This independently authored display reconstruction reproduces an affine field inside its supported sample range, but is not a converged field solve and cannot recover missing geometry. Tests use independently constructed constant/affine/degenerate fixtures and do not establish solver accuracy.

Cursor readouts identify original solver samples. Exact faces map the ray-hit triangle to its source sample; instanced glyphs map the hit instance. Reconstructed surfaces select the nearest original sample. Visible opaque depth-writing geometry blocks hits behind it; explicitly translucent geometry permits inspection through it. Cursor markers and labels also participate in depth testing. Neither cursor values nor report statistics use reconstructed display values.

Surface subdivision has a hard 100,000-item output budget including fallback points. Large or invalid faces and vertical faces with no 2D area use bounded glyph fallbacks. Geometry may be thinned for interactive display; full solver data remains authoritative. The HTML report has a separate bounded presentation renderer. Report 2D uses top-left board coordinates; report 3D applies board-Y-to-world-Y inversion, including rotated pad and component corners.

Vertical via/barrel faces have zero projected area in a 2D layout. SPIKE therefore renders their solver-owned centre as a bounded display glyph instead of emitting an invisible filled path. Admitted scalar records whose face topology cannot be triangulated use the same fallback in 2D and 3D; this preserves the sample without pretending that an invalid polygon is an exact surface.

## Reported analytics

The Results viewer and engineering report share `app/src/resultAnalytics.ts`. It reports:

- minimum, mean, 95th percentile, and maximum for every scalar field;
- probe voltage, voltage-drop, current, and current-density extrema;
- via current-density ranking by solver element ID, net, and layer span;
- utilization of the user current-density limit;
- utilization of the optional copper-fusing screen.

The via table preserves the highest sample for each via element when a via produces multiple solver branches.

## DC source to board review

Open a completed DC result in the PI Results viewer and select a net and copper
layer. The DC review shows the solver's declared maximum source voltage and the
lowest voltage, largest drop, largest current density, and largest via density
among original returned samples in that scope. Each extreme retains its element,
net, layer, and source object identifier where the result supplied one. The
drop and density screens compare these scoped samples with the current setup
limits; changing a limit after a run changes the screen, not the solved values.
An unset, invalid, or absent value is shown as unavailable rather than passed.

When the solver returns `networks.source_to_load`, the viewer shows each
anchored source/load pair, its terminal voltages, supply drop, optional explicit
return-loop drop, load current, and configured drop-limit state. The terminal
geometry status is separate from overall model status: an exact pad anchor does
not establish mesh convergence. Older or unanchored results continue to show
only original board samples; the lowest sample is not called a load measurement.
Failed and `solved=false` results cannot populate either review; their raw
diagnostics remain available elsewhere.

## Copper-fusing screen

SPIKE uses the short-duration Onderdonk copper equation in the form published by NASA:

```text
I_fuse = A_cmil * sqrt(
  log10((T_melt - T_initial) / (233 + T_initial) + 1)
  / (34 * t_seconds)
)
```

The displayed threshold is current density, obtained by converting one square millimeter to circular mils. SPIKE uses a copper melting temperature of 1084.62 C. The user supplies initial ambient temperature and fault duration.

Primary reference: NASA NTRS, *Evaluation of Magnet Configurations for Magnetohydrodynamic Aerocapture*, equation 13, document 20240015387:
https://ntrs.nasa.gov/api/citations/20240015387/downloads/Magnet_Systems_Analysis_FINAL.pdf

### Validity boundary

This result is always marked `Approximate`. It is a short-duration adiabatic fusing screen, not any of the following:

- a continuous-current ampacity;
- an IPC trace-temperature-rise calculation;
- a board or enclosure thermal simulation;
- a manufacturing-tolerance guarantee;
- a qualification of via plating, solder joints, or copper neck-downs.

The screen excludes PCB heat spreading, solder mask, copper and plating tolerance, solder fill, adjacent copper, convection, radiation, enclosure conditions, and temperature-dependent material properties. Continuous operation and product qualification require mesh-converged electro-thermal analysis with defined boundary conditions.

## Project persistence

The following display and screening settings are stored in the SPIKE project package under `analysis.result_visualization`:

- raw versus smooth field style;
- flat, raw-height, or 3D-contour plot style and plot-height scale;
- vector visibility and scale;
- board/result scene mode;
- component-model visibility;
- fusing ambient temperature;
- fusing event duration.

The selected stored result is persisted separately under `analysis.result_display`. Reopening a solved project restores that selection when it still exists, otherwise the latest retained result is selected. A network-only broadband `Z(f)` sweep remains available to the graph/results panel but does not activate a fabricated spatial impedance overlay.

When a spatial result has no admitted samples on the currently selected 2D copper layer but does have samples on another visible layer, the layout switches to the aggregate `All` layer. It preserves an explicit layer whenever that layer can display at least one result sample.

Older project packages receive conservative defaults when loaded.
