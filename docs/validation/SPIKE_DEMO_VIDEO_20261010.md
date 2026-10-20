<!-- SPDX-License-Identifier: Apache-2.0 -->
# SPIKE capabilities demo — 10 October 2026

Deliverables are unbundled local records under `demo-video-20261010`. The
captioned MP4 uses
native desktop captures and retained executed analysis artifacts. The edit
manifest identifies each source, its SHA-256, timestamps and scope.

The current 111.5-second edit includes animated title cards, a live native
thermal setup/solve, the native results map and colored solved cells directly
over the real PCB in both main viewport modes. The 3D view includes a
49.706 °C top-surface cell probe, source coordinates and an orbit. The 2D
view overlays the same solved field on pads, references and board geometry.
The exact raw capture is `viewport-overlay.mp4`; markers identify UI actions.
These new close-ups replace the earlier probe-only chapter. Public screenshots
are `docs/tutorial-assets/demo-board-thermal-{2d,3d}.jpg`.
The edit also includes the executed transient animation and qualified PI/SI/EM
artifact views. The PI/SI/EM scenes are not new native board-overlay recordings.
No failed loading footage is included. Raw restart captures are not shareable
deliverables.

Final media verification: full FFmpeg decode passed. Frames at 64 s and
78 s were inspected and show the colored main 3D and 2D board overlays,
respectively, with readable captions and the native 3D probe.

## Live thermal demonstration

The ESP32 board is imported from
`examples/esp32/source/iot-esp-eth-ind.kicad_pcb`, source SHA-256
`3199ce0a25f8987020e716d82a4a35d9b6b04541d33b2f2e46406376713eab33`.
The native thermal setup executes a layered board model with U41 at 0.5 W,
ambient 25 °C, 2 mm cells and 1.586 mm thickness. Filled zones are excluded;
tracks, pads, vias and copper layers are included. Inputs are retained in
`demo-inputs.json`; `live-simulation-result.json` is an independent execution
of the same request, matching the recorded native result.

Board temperatures are 27.524742–54.757960 °C; estimated maximum junction
temperature is 56.869107 °C. Outward heat is 0.4999999999996523 W.
These are approximate results with assumed power, materials and cooling.
The 2 mm grid underresolves some U41 pad contacts. They are not hardware
measurements or a thermal qualification. Unresolved CAD model references
are represented by footprint placeholders.

The `.spike` package is prepared through the existing package writer and
retains the real board source, inputs and computed result. Native Save As
and result export encountered existing source/entity-ID validation failures;
native persistence is not claimed as verified by this demo.

## Viewport rendering correction

Thermal cells use `InstancedMesh.setColorAt`. The plane geometry has no
per-vertex color attribute. Enabling `vertexColors` on its material multiplied
the instance colors by an absent attribute and produced black cells. Removing
that flag preserves the real instance colors and does not alter solver data.

`app/scripts/test-thermal-instance-colors.mjs` renders real WebGL pixels:
the previous material produces two black cells; the corrected material
produces distinct blue and red cells. The fixture uses local Three.js and
an optional Playwright runtime. It is a regression test, not demo footage.

Verification: production TypeScript/Vite build, Rust release build, actual
WebGL pixel check, board thermal viewport/probe checks, board parser,
architecture checker and button-standard checker passed.

Other PI, SI, EM and transient examples carry their own model-scope captions.
Still artifact views must not be interpreted as native UI execution footage.

## Product promo teaser

The separate unbundled local `SPIKE-product-teaser.mp4` is a
29-second, 1920 × 1080, 30 fps motion edit. It uses recorded native board
orbits, thermal setup and execution, colored 3D layers, a saved-cell probe,
result hovering and a 2D PCB zoom. Animated typography, short transitions,
gentle editorial pushes and an original synthesized stereo score accompany
the footage. The closing lockup carries **SI, PI, Thermal, EM** over a moving
board. The longer captioned demonstration is preserved separately.

`build_teaser.py` retains the edit, and `teaser-manifest.json` records source
digests, native capture timestamps, crops and playback rates. The board
rotations are native camera interactions; no fabricated simulation overlays
are introduced. This teaser demonstrates the approximate thermal case above,
not native PI, SI or EM board-field execution.

Full video and audio decoding passed. Selected frames were inspected for
board motion, readable probe and hover values, and the closing lockup.
`teaser-verification.json` retains the stream and audio checks. The prepared
recordings and teaser are local outputs; this record does not establish a
GitHub media upload or public release.
