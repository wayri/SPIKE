<!-- SPDX-License-Identifier: Apache-2.0 -->
# Native EMerge Gerber workflow

SPIKE can retain a small Gerber stackup and pass each copper file directly to
EMerge 3 `FileBasedPCB.layer_from_file`. This is a separate geometry source
from the KiCad/SpiDeR polygon adapter. SPIKE does not convert the artwork to
KiCad, reconstruct copper polygons, or infer Gerber nets and pads.

The application contribution `emerge-gerber-import` accepts
`parameters.source` using `spike/emerge-gerber-source/v1` and returns
`data.snapshot` using `spike/design-snapshot/v1`. The same package can be saved
as `*.spike-gerber.json` and opened through the registered
`emerge-gerber-design` importer. The snapshot retains every admitted source
string, its SHA-256 and its byte count under
`metadata.emerge_gerber_source`. Its canonical design contains stackup layers,
the declared board bounding box and display-only port markers. Empty canonical
track, zone and pad arrays are intentional; their absence prevents a native
Gerber import from becoming an inferred copper or connectivity claim.

In the EMerge setup, choose **Native Gerber study**. Choose original copper
files in top-to-bottom order, define each dielectric gap, enter board bounds
in millimetres, and place one or two manual vertical port planes. **Load Gerber
study** imports that setup. The initial viewport shows declared substrate
extent; copper appears after native mesh preparation. Use **Check EMerge runtime**
and **Prepare native Gerber mesh**, inspect conductor/port contact in the mesh,
then use the normal RF solve and result controls. Missing optional dependencies
and retained Excellon sources block execution with recovery instructions.

**Export source package** writes `*.spike-gerber.json`; **Open source package**
restores the original artwork and setup. Normal SPIKE project save/reopen also
retains artwork and current material assignments. In standalone SPIKE-Em,
the fixed built-in EMerge gateway and its read-only registered source importer
provide these routes without adding EMerge to the mutable extension catalog.

An example two-layer source package has this shape:

```json
{
  "contract": "spike/emerge-gerber-source/v1",
  "name": "RF artwork",
  "bounds_mm": [0, 0, 40, 30],
  "layers": [
    {"name": "F.Cu", "file_name": "top.gbr", "content": "..."},
    {"name": "B.Cu", "file_name": "bottom.gbr", "content": "..."}
  ],
  "dielectrics": [
    {"thickness_mm": 1.6, "epsilon_r": 4.2, "loss_tangent": 0.02}
  ],
  "ports": [
    {"id": "P1", "x_mm": 10, "y_mm": 15, "width_mm": 1,
     "signal_layer": "F.Cu", "return_layer": "B.Cu"}
  ],
  "resolution_mm": 0.01,
  "drills": []
}
```

Copper layers must be ordered `F.Cu`, sequential `In1.Cu` names, and `B.Cu`.
There is one dielectric record for each adjacent copper-layer gap. One or two
ports are allowed and must be named `P1` and optionally `P2`. A port connects a
signal layer to the adjacent copper layer below it. Its coordinate and width
are manual annotations. SPIKE verifies their numeric bounds and layer relation,
but it cannot verify that a Gerber flash or pad exists there.

After import, use the normal EMerge SI, radiation, script-preview or mesh
contribution with `geometry_source: "gerber"`. Frequency, mesh, air-domain,
loss, dielectric-box surroundings, sweep, field and sampling controls keep their existing meaning. The
compiled board case retains source content and assumptions, and its case and
generated-script digests change when artwork, material data, bounds, ports or
solver settings change. The contained runner writes the exact retained UTF-8
bytes to a private temporary directory and calls the public native loader for
each layer. It does not call the polygon compiler for this branch.

The retained package records the material values supplied at import. The
current SPIKE design stackup is authoritative at compile time so later edits in
the material manager affect the executed case. Its copper order must still
match the retained source layers exactly; each current dielectric gap supplies
the effective thickness, relative permittivity and loss tangent recorded in the
case. The original retained package remains unchanged as import evidence.

The selected solver interpreter needs EMerge 3 and its optional Gerber
dependencies. Install the distribution's Gerber extra in that interpreter,
for example `python -m pip install "emerge[gerber]"`. **Check EMerge runtime**
reports `gerber_available`, `gerber_reason`, the `gerber_loader` API check, and
`native_gerber_geometry` only when the dependency and required public API are
present. Missing Gerber support does not disable the existing KiCad/polygon
EMerge path. Native Gerber is fail-closed on a future EMerge major version
until its loader contract is qualified.

The case compiler supports 2-16 copper layers, but the current package budget
limits admission to eight total layer and drill files, 512 KiB per file and 2 MiB of retained source content. Bounds are finite,
increasing and at most 40,000 mm2. Dielectric gaps are 0.01-10 mm, relative
permittivity is 1.01-30, loss tangent is 0-1, and the native outline sampling
resolution is 0.001-1 mm. File names must be portable plain names without directories, reserved device
names, controls or platform-invalid characters. Safe interior spaces and
Unicode names are preserved.
Malformed JSON, duplicate file names, mismatched retained hashes, non-finite
numbers and stale source digests fail before launching EMerge.
The optional `*.spike-gerber.json` file importer also applies a 16 MiB outer
JSON parser limit before decoding escaped source strings.

Excellon text can be retained in `drills`, but a case containing it currently
fails before meshing. The public native via loader has not yet been integrated
and verified against SPIKE's layer-span, plating and antipad contracts, so
ignoring drills or inventing solid vias would make the model misleading.

This workflow is an unvalidated geometry integration. Gerber carries no source
net connectivity, material stackup, reference-return choice or reliable pad
identity. `GerberRF` and `GerberReturn` are setup labels only. Copper is modeled
as zero-thickness PEC surfaces, dielectric extents use the declared rectangle,
manual ports are not verified pads, and native outline simplification and
tolerances belong to the selected EMerge/Gerber runtime. Mesh geometry is
available for viewport review; it does not establish physical solver accuracy.
Release use still requires mesh convergence, port review and independent
correlation by a knowledgeable engineer.

The clean-room fixtures in `tests/fixtures/emerge_gerber` are original SPIKE
test data. The millimetre fixture has a dark rectangular region and clear
circular hole; the inch fixture has a flash and trace. The optional installed
runtime test loads both through `FileBasedPCB`, checks metre-scale bounds and
the clear-hole boundary, without reading or copying upstream implementation
source.

## Source and fabrication coordinates

The Source step separates portable package actions from numeric setup. **Open
source package** restores a retained source draft; **Export source package**
validates and downloads its original files and setup. Neither runs a solver.
Study name is a project label. Contour resolution (0.001–1 mm) controls native
Gerber sampling and is separate from tetrahedral mesh size.

Minimum/maximum X and Y are assembly/source millimetres. Keep the original
Gerber origin and enter increasing bounds. This rectangle declares the substrate;
it does not extract the board edge from artwork. Review these values against the
fabrication source before importing.

## Copper and dielectric stack

Order copper from F.Cu through inner layers to B.Cu. Choose one original Gerber
file for each copper layer. Each gap below a copper layer has explicit thickness
(mm), relative permittivity and loss tangent. These are user-supplied material
values, not values inferred from the Gerber file. Adding or removing inner copper
requires reviewing all adjacent dielectric gaps and port layer references.

## Drill sources

The Stack step can retain optional Excellon files for source provenance.
They currently block native drill/via execution before meshing or solving;
retention is not a claim that drill holes or plated vias have been reconstructed.
Remove unsupported drill sources only when that omission is appropriate for the
intended study, and record the resulting geometry limitation.

## Explicit port planes

Ports are manual X/Z planes at an entered Y. Set centre X, Y and plane width in
millimetres, and select the signal layer and adjacent lower return layer. One or
two ports are supported. Coordinates and layer bounds can be checked, but Gerber
artwork supplies no verified terminal, pad or net identity. Inspect actual
conductor/port contact in the prepared native mesh before solving.

## Review and load

Review summarises source files, copper count, drills and ports while keeping the
draft mounted. **Load Gerber study** is the explicit import action; switching
steps, opening Help or exporting a package does not import it. Import failure
keeps the draft for correction. Saving the project after import retains the
source definitions. Native mesh preparation and solving are subsequent actions.

The setup uses bounded form columns, compact action buttons and section headers.
The **Help** button beside each header opens this matching offline help section. Closing
Help and returning through panel navigation preserves the setup draft.
