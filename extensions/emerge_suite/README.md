# EMerge Suite for SPIKE

This extension takes the current imported SPIKE board, builds a bounded PCB
model through Robert Fennis's [EMerge](https://github.com/FennisRobert/EMerge)
Python FEM API, runs a frequency sweep, and returns solved S-parameters and
optional far-field cuts and a sampled full-sphere pattern to SPIKE. No EMerge
model script is required. SPIKE keeps the computed arrays in an `AnalysisResult`,
displays interactive 3D radiation, 2D cuts, S-parameter magnitude and phase
plots in the Extension Manager, and records the result in
the normal analysis history.

## Use in SPIKE

1. Import a board with a physical F.Cu / dielectric / B.Cu stackup and
   verified filled copper geometry.
2. Open **Settings -> Extension manager -> EMerge Suite**.
3. Use **Check EMerge runtime** to see whether the selected Python environment
   exposes the SI and radiation adapters. Select a signal and return net. Choose an F.Cu signal pad and an aligned
   B.Cu return pad for the first vertical lumped port. A second pad pair is
   optional; add it for two-port S21/S12 data.
4. Enter start and stop frequency, sweep points, and mesh resolution. Select
   **EMerge SI port sweep** or **EMerge radiation pattern**, then **Run**.
5. Inspect the returned plots, model information, and warnings in SPIKE. Radiation
   results have S-parameters, a phi=0, theta=0..180 degree cut, and a sampled
   full-sphere pattern at each solved frequency. Rotate and zoom the 3D plot.

Install a compatible EMerge distribution in a Python 3.10-3.13 environment.
The Extension Manager's optional **EMerge Python executable** selects that
environment's interpreter. If blank, SPIKE checks a project-local
`.venv-emerge3`, its worker interpreter, then `.venv-emerge`. This
extension does not download or bundle EMerge. The tested adapter target is the
published EMerge 2.8 API and EMerge 3.0.0a19 prerelease; the runtime version is
recorded with every result. A separate `.venv-emerge3` environment can be
selected explicitly in the setup form. Other 3.0 prereleases require API review.

## Supported geometry and limits

The adapter currently exports only selected signal and return nets on a rigid
two-layer board, using straight tracks, undrilled supported pad contours, and
source-verified filled zones without holes. It uses the imported rectangular
board bounds, one dielectric relative permittivity, and surface PEC copper.
It requires vertically aligned F.Cu/B.Cu pad pairs for ports. Selected-net
vias are rejected by default. A bounded explicit `shorting_via_ids` list can
admit source-identified return-net through vias as **solid PEC cylinders**;
barrels, drills and antipads remain unresolved. Attributed unnetted copper
graphics and idealized reference planes require documented source fields and
generate warnings. `fragment_copper: false` is an explicit diagnostic
fallback for overlapping polygons and requires mesh inspection. The
[ESP32 two-conductor example](../../examples/esp32/README.md) records these
assumptions and a limited mesh comparison. Non-rectangular outlines, copper
cutouts, unfilled zones, additional copper layers, flex regions, and bends
are not represented. Cases containing
known unsupported selected-net geometry fail before launching EMerge. Other
board nets, components, copper thickness, solder mask, and dielectric loss
tangent are omitted; the result records those model limits. The absorbing-air
region is bounded and needs a spacing/convergence study.

Input admission limits: 4,096 polygons, 200,000 vertices, 40,000 mm2 board
bounds, a 200,000-cell planar preflight estimate, two ports, 2-64 solved
frequency points, 100 MHz-100 GHz, and 0.05-10 mm requested trace mesh size.
The extension process has a 3,600 s cap;
the contained EMerge runner stops after 3,300 s. Its result must fit in 8 MiB.
Malformed or missing arrays are rejected rather than rendered.

The EMI ribbon also opens an EMerge panel. Its runtime probe gates SI and
radiation buttons by reported capability; results use the same plots, 3D
pattern, sample probing, warnings, and analysis history as the Extension
Manager. The [KiCad antenna walkthrough](../../docs/EMERGE_ANTENNA_WALKTHROUGH.md)
contains a reproducible EMerge 3 run and its saved, unvalidated output.

The **HF / SI** ribbon has an **S-parameter solver** selector. SPIKE probes the
trusted EMerge runtime when the SI tab opens and enables EMerge only when the
adapter reports `si_s_parameters`. Selecting it routes **S-parameters** and
**Ports** to EMerge's two-port setup and result plots. Impedance, NEXT/FEXT,
eye, PAM4, and Touchstone workflows continue through their existing SI tools;
the EMerge adapter does not declare those analyses. If the runtime or extension
becomes unavailable, the selector returns to SPIKE internal.

For a dielectric cover in front of the antenna, enable **Model dielectric
cover** in the EMerge setup. SPIKE positions its default box around the
imported board bounds; edit the X/Y origin, gap above F.Cu, width, depth,
thickness, and relative permittivity before solving. The backend also accepts
`parameters.surrounding_geometry` using the bounded
`spike/emerge-surroundings/v1` contract with up to eight non-overlapping
`dielectric_box` objects. It meshes those volumes before the air region is
created. Total surrounding dielectric volume is capped at 100,000 mm³. Boxes
begin at least 0.5 mm above top copper and must overlap the
board in XY. Their material is ideal, constant relative permittivity; material
loss and dispersion are omitted. Other surrounding geometry, including curved
radomes, metal enclosures, imported STEP solids, cables, and complex assemblies,
is not yet translated into the EMerge case. The [paired radome example](../../examples/emerge/radome/README.md)
records completed bare and covered EMerge 3 runs on the same board.

The result view offers the original 13 × 25 solved angular grid and a 5°
display surface interpolated bilinearly in relative linear amplitude. The
same interpolated relative shape can be shown around the DUT in the EMI
chamber after **View radiation on bench**. The chamber's bench display can be
visible, translucent, or hidden. Interpolation and bench visibility affect
only rendering; neither changes solver data or an EMI compliance claim.

S-parameter values are complex `[real, imaginary]` pairs ordered as
`[frequency][receive_port][excited_port]` at an explicit 50 ohm reference.
The radiation array contains complex spherical `E_theta`/`E_phi`, a
per-frequency 2D cut, and a 13 by 25 theta/phi grid for the 3D plot. Each
cut and sphere is independently normalized to a 0 dB peak. The 3D radius is
proportional to relative field amplitude, while color displays relative dB.
The 3D grid is a coarse solved sample set, and the surface between samples is
display interpolation. The UI plots only returned samples. S-parameter phase
is wrapped to ±180 degrees. This is an experimental integration: an admitted result remains
`unvalidated` until geometry, ports, mesh convergence, radiation boundary,
and independent correlation are reviewed. A far-field pattern is not a
calibrated EMI compliance prediction.

## Developer notes and method provenance

`board_adapter.py` admits DesignIR and constructs `spike/emerge-board-case/v1`.
`runner.py` calls EMerge's PCB geometry, mesher, frequency sweep, lumped port,
and absorbing boundary APIs in a separate interpreter. `capture.py` reads
direct solved `grid.S` arrays and projects Cartesian far fields onto the
standard right-handed spherical theta/phi basis. `normalize.py` checks units,
shape, ordering, finiteness, and resource limits. `extension.py` binds results
to the exact board digest and case SHA-256. The implementation is independently
authored from [EMerge's public PCB demo](https://github.com/FennisRobert/EMerge/blob/main/examples/demo6_striplines_with_vias.py),
[patch antenna demo](https://github.com/FennisRobert/EMerge/blob/main/examples/demo4_patch_antenna.py),
and [microwave data API](https://github.com/FennisRobert/EMerge/blob/main/src/emerge/_emerge/physics/microwave/microwave_data.py).
No upstream code, meshes, models, or datasets are copied into SPIKE.

The focused tests use deterministic EMerge API doubles to verify geometry
handoff, port units, result binding, numerical projection, and failure gates.
A two-frequency, two-port fixture completed with EMerge 2.8.9 on Windows, and
a seven-frequency KiCad antenna fixture completed with EMerge 3.0.0a19;
those runs establish execution, not physical accuracy. A knowledgeable human
must review numerical behavior before release. EMerge's license and runtime
dependencies require separate review before redistribution.
