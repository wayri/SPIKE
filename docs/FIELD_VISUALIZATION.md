<!-- SPDX-License-Identifier: Apache-2.0 -->

# Volume, airflow and transient visualization

Field volumes render inside the main Three viewport, in the same scene and
camera as the board or assembly. Use the compact **Fields** control beside the
viewport. Its label expands on hover or keyboard focus; click it for display,
quantity, cut, curve and import/export settings. When a dataset has saved
frames, play/pause, the frame scrubber and current time remain inline beside the
control. The command palette's **Volume and airflow visualizer** action opens
the same main-viewport workflow. It does not start a solver.

## What is available

- **Voxels:** physical cell centers and supplied XYZ dimensions render as a
  single bounded WebGL triangle mesh. Unequal cell sizes are supported. These
  are axis-aligned cells, not arbitrary polyhedra or reconstructed CAD solids.
- **Sample points:** used when the result lacks cell dimensions. No volume or
  interpolation is inferred from a point cloud.
- **Velocity arrows:** returned XYZ velocity vectors in m/s control direction
  and relative length. Arrow lengths use one maximum across the saved history.
  They are glyphs, not computed streamlines or particle trajectories.
- **Streamlines / streamtubes:** supplied connected CFD curves can be displayed
  as colored lines or tubes. A complete, explicitly declared 3D fluid grid can
  also produce renderer-generated preview streamtubes, with seed-plane, density
  and width controls. See the distinction below.
- **Temperature and scalar fields:** select a supplied quantity. Kelvin data can
  display in Celsius; stored values stay unchanged. The color range is fixed
  across all saved frames, including while using a cut.
- **Reveal cuts:** choose X, Y or Z and move the cut position. Cells are included
  by center position; this reveals complete cells, not a reconstructed cut face.
- **Bounded detail:** 500, 2,500 or 8,000 displayed cells and at most 1,500 vector
  glyphs. Deterministic thinning changes display only, never solver data.
- **Import/export:** local JSON retains all admitted samples and frames, rather
  than only the thinned view. Imported data is presentation data, not an accepted
  solver result. Exports do not yet retain the camera or display preferences.

Native cavity results remain **2D**; the voxel sheet's Z thickness is explicitly
display-only. Assembly airflow previews provide fluid cell centers and vectors
but no cell sizes, so their voxel option stays disabled. This work does not add
a solver, mesh acceleration, arbitrary CAD CFD, turbulence or new qualification.

## Connected flow curves

Select **Streamlines** or **Streamtubes** in Volume display.
Supplied curves use their original points and pointwise scalar values, so they
can be colored by temperature, speed or another supplied quantity. Tube width
is cosmetic. Separate curves are never spliced together; excessive paths are
omitted whole under the display budget.

Without supplied curves, Streamtubes is enabled only when
`cells.flowDomain: "complete-cartesian-fluid"` explicitly declares an
obstacle-free fluid domain and the coordinates form a full Cartesian product
with at least two samples on each axis. Duplicates, missing grid points, 2D
sheets, more than 40,000 input samples and absent velocity disable this route.
Do not declare a point cloud, solid-containing grid or a masked/holed domain
complete merely to enable it. Existing sparse assembly CFD samples stay arrows
unless the exporter supplies actual curves.

Generated paths use the selected axis's center plane with 2×2 through 8×8 seed
positions. Each seed traces forward and backward through the selected saved
velocity field. The bounded presentation tracer uses trilinear interpolation
and fixed-step midpoint integration; it does not thin, fill or extrapolate the
grid. Zero or unsupported fields produce no paths. Tube color uses velocity
magnitude with a fixed history-wide range; arbitrary temperature is not mapped
onto generated paths. Tube radius and line width are cosmetic. The display is
bounded to 256 steps per direction and apportioned by its segment budget. See
the [derivation, limits and executed checks](validation/FIELD_STREAM_PRESENTATION_20261021.md).

These are frozen-time flow visualizations, not time-integrated particle
trajectories. Playback recomputes a view for each saved frame; it does not solve
advection. Cell cut controls are disabled for curve modes. Source curves and
renderer-generated tubes are labeled differently and neither becomes a solved
field. The generated tracer is a presentation method, not a CFD solver or
physical validation. Its synthetic analytical checks qualify only the stated
frozen-field drawing behavior; arbitrary-field convergence and source-solver
qualification remain outside this feature.

## Saved transient playback

When at least two frames exist, the inline transport provides play/pause and a
frame scrubber without covering the shared scene. The expanded settings also
provide first/previous/next, simulated-time speed and looping.
Looping is offered when this control owns playback; an externally managed PI
timeline retains its own scheduling. Existing exporters remain available only
where their owning renderer supplies an export callback.

Playback uses saved timestamps, including uneven intervals. It holds a saved
field until the next sample; it does not interpolate fields or fabricate missing
frames. Camera orientation remains stable across frame updates. Static fields
show a static notice. Pausing playback does not pause an active solver job.
Hiding the volume viewer pauses its playback.

## Exchange format

`spike/field-volume-view/v1` contains:

| Member | Meaning |
| --- | --- |
| `id`, `label`, `geometryNote` | Dataset identity, label and geometry/status limitations |
| `lengthUnit` | `m` or `mm`, used by every center and cell size |
| `cells.centers` | One XYZ triple per sample |
| `cells.sizes` | Optional positive XYZ dimensions, one per sample; omitted means no voxel geometry |
| `cells.flowDomain` | Optional `complete-cartesian-fluid` assertion for renderer-generated 3D streamtubes |
| `quantities` | Unique quantity IDs with labels and units |
| `frames[].timeS` | Finite, nonnegative, strictly increasing saved times in seconds |
| `frames[].scalars` | A scalar array per declared quantity, matching the sample count |
| `frames[].vectors` | Optional matching XYZ velocity triples in m/s |
| `frames[].streamlines` | Optional separate curves, each with `points` in coordinate units and matching `scalars` for every declared quantity |

The current interchange assumes fixed cell geometry across frames. Remeshed,
deformed, rotated-cell and moving-boundary sequences need a future topology-aware
contract. Unstructured original meshes cannot be losslessly represented by
inventing voxel boxes.

Import bounds: 64 MiB file, 200,000 samples, 16 quantities, 1,000 frames and four
million scalar/vector/curve numeric entries total. Curves are limited to 256 per
frame and 2–16,000 distinct consecutive points per curve. Invalid units, sizes, times,
nonfinite values or mismatched arrays are rejected; the previous view remains.
This exchange is not a substitute for the full `.spike` project provenance.

Try the [illustrative volume fixture](../examples/field_visualization/README.md).
It exercises visualization only and contains no simulated CFD or thermal result.

## Ownership and follow-up

`fieldVolumeModel.ts` owns presentation admission, voxel topology, glyphs and
bounded display selection. `mainFieldViewport.ts` owns main-workspace field
state, `MainFieldControls.tsx` owns the compact control and inline playback, and
`fieldVolumeScene.ts` adapts bounded traces to the shared BoardViewport Three
scene. `fieldVolumeAdapters.ts` maps already admitted CFD result shapes.
`fieldStreamPresentation.ts` owns source-curve presentation and complete-grid
admission; `fieldStreamTracing.ts` owns the bounded generated frozen-field
paths. The developer fixture exercises the same main BoardViewport harness.
`SavedFramePlaybackControls.tsx` and `transientPlayback.ts` own saved transports.
No solver fields are written back by this viewer.

Dense ray-marched volumes, obstacle-aware unstructured streamline tracing,
particle pathlines, moving meshes and direct enclosure-CHT result import remain
follow-up work. The
[Blender integration plan](BLENDER_RENDER_PLAN.md) covers photoreal output.
