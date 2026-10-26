# Viewport transient playback

Completed layered board thermal and spatial PI transient results share the
**Result / Play** bar above the main board viewport. A successful supported run
opens its saved fields in 3D at the first frame. Click **Play** to review the
saved sequence; use **Pause**, the time slider, **Restart**, **Speed**, or **Loop**
without reopening the solver setup. The Result selector switches between
available PI and field-volume results.

The default review takes eight seconds from first to last saved time. Displayed
timestamps remain solver time, including microsecond PI runs. The speed caption
states simulated seconds per playback second. Playback holds saved frames;
it does not solve again or interpolate missing numerical results. Restart and
scrubbing pause playback. A replacement result stops the old sequence and
selects the new result at its first frame.

Layered thermal playback uses the returned layer temperatures, source XY cell
coordinates, layer thicknesses, and timestamps. It does not assign board
temperatures to component bodies or infer air temperatures. A PI result needs
at least two returned spatial frames. Waveform-only circuit results and steady
results do not become board transients. The initial PI quantity is selected
from fields actually returned in the transient frames.

## Airflow

Velocity results with supported streamlines use the same Play button to move
direction markers along the displayed curves. The markers are a presentation
of direction along a frozen velocity field; their speed is not particle travel
time. For saved transient CFD frames, Play also advances the actual saved
velocity and temperature fields. Change the field quantity to inspect air
temperature when that scalar was returned by the solver.

Curves supplied by the solver are retained. Renderer-generated curves require
an explicitly admitted complete Cartesian fluid grid. An obstacle mesh with
missing fluid cells must not be relabeled as a complete grid or filled with
invented fluid values. Static E/H field lines are not animated as airflow.

Visible board parts alone do not create CFD obstacles. The simulation assembly
must contain the participating solid geometry and its material and thermal
conditions; the prepared fluid domain must exclude those solids and contain
the corresponding fluid/solid interfaces. Package bounding proxies must be
identified as proxies rather than exact STEP geometry. Failed mesh admission
must be corrected before presenting a successful flow result.

## Implementation and checks

`useViewportPlayback.ts` owns selection, the review clock, frame selection,
replacement, and cleanup. `ViewportPlaybackBar.tsx` renders controls outside
the canvas. `boardThermalFieldVolume.ts` adapts returned layer cells through
the existing field-volume admission contract. `fieldStreamAnimation.ts`
updates bounded marker buffers along existing displayed paths without
rebuilding the board scene on every animation tick.

Focused checks are included in `npm run test:transient-ui` and
`npm run test:field-volume`. They exercise saved-time mapping, pause/seek,
replacement and disposal, microsecond review speed, actual PI frame-field
selection, thermal cell identity, and flow-marker eligibility and motion.
Native installation and visual verification are recorded separately; unit
tests alone do not establish an installed viewport result or solver validity.
