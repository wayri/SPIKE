# Orbit and harness rendering

## Interaction policy

`app/src/BoardViewport.tsx` renders active camera gestures on each display
refresh. A second FPS threshold previously rejected slightly early refreshes,
which could halve the effective camera refresh rate. Stationary views retain
the 5 FPS idle cadence. `viewportFrameCadence.ts` owns this decision and the
elapsed-time damping factor; the user's navigation inertia preference remains
in control.

Interactive pixel density and frozen shadows remain active during a gesture
and its damping tail. Full quality returns after 180 ms without camera changes.
Only the active 2D or 3D controls update in the render loop.

## Cable presentation and selection

`app/src/harnessScene.ts` constructs shaded, depth-tested tubes from the existing
conductor paths. It retains harness, conductor, differential-pair and endpoint
pin identities. Selection changes material color without rebuilding geometry.
Picking rejects cable intersections hidden behind opaque board or part geometry.
Assembly hiding and explode offsets continue to use the existing projection.

Tube radius is a display assumption, not a measured insulation diameter.
Curved tubes are presentation geometry and are excluded from solver geometry
snapshots. Saved routes and electrical inputs are unchanged by this rendering.
The scene is bounded to 2,048 cable meshes and 32,768 longitudinal segments,
with six radial segments per tube. Invalid paths are skipped and geometry
budget diagnostics are retained.

## Verification on 2026-10-09

- Production frontend build passed.
- Frame cadence, harness scene, harness engineering, large-scene resource,
  assembly handling, parser, button standard and architecture checks passed.
- Browser verification used two occurrences of the retained Sailor Hat board
  with actual CAD models and a synthetic six-conductor mixed harness. Orbiting,
  individual conductor selection, exploded placement, and endpoint-board
  hide/show were exercised. This is rendering evidence, not harness pinout
  qualification.
- During one orbit drag, scene telemetry reported approximately 34 FPS for
  1.58 million triangles. There is no measured before/after speed comparison
  or guarantee of 60 FPS for this scene.
- Native window capture returned desktop wallpaper and window activation
  failed. Native installed-app verification remains outstanding; these changes
  have not been installed by this task.

Reproduce the focused checks from `app` with `npm run test:viewport` and
`npm run test:harness-visualization`. The retained CAD preview is
`app/scripts/assembly-performance-preview.html?harness` on the development
server, when its local CAD fixture is available.
