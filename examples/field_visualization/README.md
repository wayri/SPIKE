<!-- SPDX-License-Identifier: Apache-2.0 -->

# Illustrative volume and playback fixture

`illustrative-volume.json` is an original, synthetic UI fixture: 72 axis-aligned
cells, four unevenly spaced saved frames, temperature and velocity samples.
**No flow or heat equation was solved. These values have no validation meaning.**
The source is SPIKE-authored under Apache-2.0.

`illustrative-curves.json` supplies eight authored connected curves with
temperature/speed values. It exercises thin Streamlines and thicker Streamtubes
without pretending that a CFD solver generated those curves.

1. Click the compact **Fields** control beside the main Three viewport, or open
   **Volume and airflow visualizer** through Ctrl+K. The field shares the board
   scene and camera.
2. Click the Fields control for settings, choose **Import field**, then this JSON
   file. The control expands on hover or keyboard focus.
3. Switch Voxels / Sample points; toggle Velocity arrows; select Temperature or
   Velocity magnitude. Use an X cut to reveal the interior.
4. Use the inline play/pause and frame scrubber; open settings for stepping,
   speed and looping. The color range stays fixed; the time label follows the
   saved times 0, 0.2, 1 and 2 seconds.
5. Export the field to retain all source cells and frames. No display thinning
   is applied to that exported data.

For the connected “strings” view, import `illustrative-curves.json` and select
**Streamlines · supplied curves** or **Streamtubes**. Adjust Curve width and
opacity, then select the scalar used for color. The volume fixture also declares
a complete synthetic 3D fluid grid, so its Streamtubes mode exercises bounded
forward/backward tracing from the selected axis's center seed plane. The path is
an approximate frozen-field speed visualization, not a particle trajectory or
solver output. It is a visualization test only; see the
[presentation evidence](../../docs/validation/FIELD_STREAM_PRESENTATION_20261021.md).

The main workflow does not open an independent Plotly viewport. Developer
preview: serve `app` with Vite and open
`/scripts/fixtures/field-volume.html`. This uses the main BoardViewport harness
with the labeled synthetic curve dataset, not a separate renderer or mock
implementation. Import the volume fixture to switch to voxels and saved-frame
grid playback.

See [format and limitations](../../docs/FIELD_VISUALIZATION.md) and the
[Blender plan](../../docs/BLENDER_RENDER_PLAN.md).
