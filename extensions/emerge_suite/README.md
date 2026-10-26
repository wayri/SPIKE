# EMerge Suite for SPIKE

This extension takes the current imported SPIKE board, builds a bounded PCB
model through Robert Fennis's [EMerge](https://github.com/FennisRobert/EMerge)
Python FEM API, runs a frequency sweep, and returns solved S-parameters and
optional far-field cuts and a sampled full-sphere pattern to SPIKE. No EMerge
model script is required. SPIKE keeps the computed arrays in an `AnalysisResult`,
displays interactive 3D radiation, 2D cuts, S-parameter magnitude and phase
plots in the Extension Manager, and records the result in
the normal analysis history. The primary workflow is GUI setup, readable
Python preview, contained solve, result visualization, sample probing and
engineering-report export.

## Example project library

Open **EMerge example projects, fields and probes** from command search or the
setup's example button. The [illustrated guide](../../docs/EMERGE_EXAMPLES.md)
and [native projects](../../examples/emerge/gallery/README.md) cover retained
patch/radome radiation, complex E/H planes, the licensed ESP32 surrogate and
an original multilayer two-port setup. Historical result bindings remain
unchanged; setup-only cases have no invented numerical result. Opening a
project does not run the extension.

## GUI model, script and results

In the EMI or HF/SI EMerge panel, choose nets and pad pairs, then expand the
advanced controls. Set reference impedance, optional imported dielectric loss,
air margin, sparse solver (runtime auto or SciPy SuperLU), optional parallel
sweep workers, angular-grid spacing and cut azimuth. Select the field-excited
port and optionally request an XY E/H plane with explicit height and grid size.
The mesh, frequency, port, material and surroundings controls remain the
authoritative inputs; you do not need to write Python.

**Preview generated Python** prepares the chosen SI or radiation study without
running a solve. Copy or download its readable source. On **Run**, SPIKE prepares
the exact current study, checks the displayed source digest, and passes that
digest to the contained runner. A changed source or setup cannot silently use
an obsolete preview. The saved result records the actually executed source's
SHA-256. The script includes only SPIKE-owned adapter code and admitted model
data; EMerge and optional EMCAD remain separately installed dependencies.
Run an exported script with `python simulation.py --result result.json`.
This standalone command returns engine data; normal SPIKE execution also
validates and admits the result against its imported board binding.

Use the result view to select solved frequencies, inspect the 3D pattern and
cuts, probe an explicit complex S-parameter, and export CSV or RI Touchstone.
The optional near-field panel plots returned E/H vector magnitudes on the
explicit XY sample grid and probes the three complex vector components at a
selected coordinate. Invalid samples remain blank; no spatial interpolation
is added by SPIKE. Export all complex field planes as CSV. E/H values use the
recorded EMerge port coefficient convention; unit coefficient is not asserted
to be one volt or one watt. Input-power calibration is needed for absolute
field interpretation. Relative far-field amplitude is distinct from this
near-field data.

The engineering report includes sampled network analytics, advanced settings,
stackup, ports, field sample counts, excitation, model status, warnings, case
digest, executed-source digest and raw evidence. Failed or malformed samples
cannot supply analytics. Saved near-field grids must preserve frequency order,
constant height and rectangular y-major/x-minor topology before display.

The reproducible [fresh board examples](../../examples/emerge/gui_workflow/README.md)
include patch, dielectric-cover, licensed ESP32 RF-surrogate and lossy-patch
E/H runs, with their exact scripts, admitted results, probes, plots and an
[offline report](../../examples/emerge/gui_workflow/report.html).

## Full upstream feature inventory

The GUI lists EMerge's [published feature scope](https://www.emerge-software.com/features)
and distinguishes integrated board controls from pending adapters. This
integration does **not** yet expose every EMerge feature. General CAD solids,
PML, waveguide/modal/Floquet/periodic ports, PMC/symmetry, impedance boundaries,
lumped elements, adaptive refinement, geometry optimization, tensor/dispersive
materials, library material selection, vector fitting, eigenmodes, RCS, thermal
coupling and explicit optional GPU solvers need additional setup and result
contracts. They remain marked `adapter_pending`; a native engine API or a
catalog row does not establish a runnable SPIKE GUI workflow. Existing GUI
results remain unvalidated.

## Use in SPIKE

1. Import a board with a physical 2-16 copper-layer alternating stackup and
   verified filled copper geometry.
2. Open **Settings -> Extension manager -> EMerge Suite**.
3. Use **Check EMerge runtime** to see whether the selected Python environment
   exposes the SI and radiation adapters. Select a signal and return net. Choose a signal pad and an aligned
   return pad on the adjacent copper layer below it for the first vertical lumped port. A second pad pair is
   optional; add it for two-port S21/S12 data.
4. Enter start and stop frequency, sweep points, and mesh resolution. Select
   **EMerge SI port sweep** or **EMerge radiation pattern**, then **Run**.
5. Inspect the returned plots, model information, and warnings in SPIKE. Radiation
   results have S-parameters, a phi=0, theta=0..180 degree cut, and a sampled
   full-sphere pattern at each solved frequency. Rotate and zoom the 3D plot.

Install EMerge 3 or newer in a Python environment supported by that distribution.
The Extension Manager's optional **EMerge Python executable** selects that
environment's interpreter. If blank, SPIKE checks a project-local
`.venv-emerge3`, its worker interpreter, then `.venv-emerge`. This
extension does not download or bundle EMerge. The runtime probe requires the
EMerge 3+ PCB, microwave, and mesh APIs used by this adapter. It reports the
exact version and whether the version has executed fixture evidence or only
API detection. Results remain unvalidated physical models regardless of the
runtime version. A separate `.venv-emerge3` environment can be selected
explicitly in the setup form.
Packaging, interpreter discovery, API-evidence, and sandbox constraints are
recorded in [EMerge runtime compatibility](../../docs/EMERGE_VERSION_SUPPORT.md).

## Supported geometry and limits

The API also admits coupled-conductor studies with `additional_signal_nets`
(up to three beyond the primary) and `port_pairs` (2–8 explicitly ordered
signal/return terminal pairs). All selected signal nets must have terminals;
signal endpoints cannot be reused. Ports still require aligned adjacent-layer
pads and a common selected return net. The existing GUI first/second-pair form
remains the basic setup; advanced coupled examples supply the explicit mapping.
See the [Marble/White Rabbit SI experiment](../../examples/emerge/board_si/README.md)
for source-derived four-port sections, mixed-mode plots and explicitly DC-assumed
eyes. These are local route scenarios, not complete-board SI qualifications.

The adapter currently exports only selected signal and return nets on a rigid
2-16 copper-layer board, using straight tracks, undrilled supported pad contours, and
source-verified filled zones without holes. It uses the imported rectangular
board bounds, explicit thickness and relative permittivity for each dielectric,
and surface PEC copper. Copper thickness is omitted from the z spacing.
It requires vertically aligned single-layer pad pairs on adjacent copper layers
with signal above return; ports spanning intermediate conductors are rejected. Selected-net
vias are rejected by default. A bounded explicit `shorting_via_ids` list can
admit source-identified return-net through vias on two-layer boards as **solid PEC cylinders**;
barrels, drills and antipads remain unresolved. Attributed unnetted copper
graphics and idealized reference planes require documented source fields and
generate warnings. `fragment_copper: false` is an explicit diagnostic
fallback for overlapping polygons and requires mesh inspection. The
[ESP32 two-conductor example](../../examples/esp32/README.md) records these
assumptions and a limited mesh comparison. Non-rectangular outlines, copper
cutouts, unfilled zones, more than 16 copper layers, flex regions, and bends
are not represented. Cases containing
known unsupported selected-net geometry fail before launching EMerge. Other
board nets, components, copper thickness and solder mask are omitted.
Dielectric loss tangent is omitted by default and can now be enabled explicitly;
only the imported constant value is represented. Copper loss and material
dispersion remain omitted; the result records those model limits. The absorbing-air
region is bounded and needs a spacing/convergence study.

Choose **Geometry preparation -> emcad copper union** to use optional
[EMCAD 0.1.0](https://pypi.org/project/emcad/) to merge overlapping polygons
within each selected net and copper layer before EMerge meshing. Install it
separately in the selected EMerge interpreter. The runtime probe reports
`emcad_available`, `emcad_version`, `geometry_backends` and `max_copper_layers`.
Missing EMCAD is an explicit error when selected; native EMerge geometry
remains the default. Union-created holes are rejected because this surface
adapter cannot represent them yet. Polygon and vertex budgets apply before
and after union. SPIKE requests no simplification; EMCAD's own default boolean
tolerances apply to coordinates passed in millimetres.
No upstream implementation is bundled or adapted: SPIKE calls the public
`Polygon` and `add_polygons` API. This integration does not bypass DesignIR
using EMCAD's ODB++ parser. Existing importer quality gates remain authoritative.
The [original multilayer fixture](../../examples/emerge/multilayer/README.md)
records a completed four-layer EMerge 3.0.0a19 / EMCAD 0.1.0 SI sweep.
No throughput improvement or physical accuracy has been established.

Input admission limits: 4,096 polygons, 200,000 vertices, 40,000 mm2 board
bounds, a 200,000-cell layer-weighted planar preflight estimate (not a
tetrahedron count), two ports, 2-64 solved
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
`[frequency][receive_port][excited_port]` at an explicit configurable reference
impedance (50 ohms by default).
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

## How the adapter works

### Mesh workspace

`emerge-mesh-preview` prepares a readable, complete Python script; `emerge-mesh`
executes exactly those bytes after checking `expected_generated_script_sha256`.
Missing or stale previews and stale board bindings fail before execution. The
separately installed runtime must expose the public `Simulation.generate_mesh`
and `Simulation.mesh` APIs. The mesh branch stops immediately after meshing,
before explicit port/absorber boundary assignment or a frequency sweep.

The returned `spike/emerge-mesh/v1` contains complete millimetre `nodes_mm`,
zero-based `tetrahedra` and `triangles`, CAD volume/face index groups, bounds,
finite nondegenerate tetrahedron checks and board/case/script SHA-256 provenance.
Its `design_top_copper` frame preserves board XY and puts top copper at Z=0.
Triangles include internal volume faces. Entity tags do not establish net or
material attribution. Limits are 100,000 nodes, 200,000 tetrahedra and 200,000
triangles within an 8 MiB serialized exchange; oversized meshes fail completely.

The original KiCad antenna completed this mesh-only route with EMerge 3.0.0a19:
1,891 nodes, 10,683 tetrahedra and 21,582 triangles. Its 40×30×1.6 mm dielectric
group integrated to 1,920 mm³, and its finite air region bounds were
[79.9999, 79.9999, −21.6001, 160.0001, 150.0001, 20.0001] mm. Host admission
verified design binding and topology. These checks establish execution and
coordinate/connectivity consistency. This selected-net approximate PCB mesh is
unsolved and unvalidated; no convergence, antenna performance or arbitrary
cross-engine mesh reuse is established. Port plate geometry and the finite air
region are retained from the corresponding EMerge PCB case.

The real runtime regression is opt-in:
`SPIKE_EMERGE_MESH_INTEGRATION=1 python -m unittest tests.python.test_emerge_mesh_extension`.

`board_adapter.py` admits SpiDeR and constructs `spike/emerge-board-case/v1`.
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

An experimental internal [sampled circuit and resistor-thermal bridge](../../docs/EMERGE_COSIMULATION.md)
now preserves bound EMerge networks for owned AC/rational consumers. It requires
explicit RMS power-wave and terminal/reference-plane declarations. Only known
external series-resistor heat maps to retained thermal cells; radiation or
unclassified EM power is not heat. Fresh field calibration, EM-body heating,
live SPICE execution and general feedback remain pending. The current release
source adds explicit worker/CLI routes and a draft export plus guarded Python
Workspace runners; it does not advertise general qualified EM/thermal coupling.
