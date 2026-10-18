<!-- SPDX-License-Identifier: Apache-2.0 -->
# Sheet and flex folding preview

## Status and scope

`python/spike_core/sheet_folding.py` provides a bounded, deterministic geometry
preview for a rectangular sheet with parallel, finite-radius bends. It supports
ordinary sheet descriptions and flex/rigid-flex descriptions whose bends are
wholly contained in declared flex regions. This is prescribed geometry, not a
deformation solver. It does not calculate stress, strain, springback, forming
limits, fatigue, delamination, conductor reliability, or manufacturing
feasibility.

The v1 coordinate system has sheet length along +x, width along y, and the flat
mid-surface at z=0. Bends are processed in increasing x order. The negative-x
side remains fixed. Positive angles rotate the downstream sheet toward +z about
an axis parallel to y; negative angles rotate it toward -z.

## Contract and workflow

Open **Sheet and flex folding** from command search, **View > Board managers**,
or the Flex PCB manager. Import a neutral definition or supported DXF, enter
reviewed thickness, edit dimensions and bends, declare flex strips where needed,
then choose **Preview fold**. Changing inputs clears stale geometry. Export the
definition to retain setup and material data; import it to resume later.

The exact input contract is `spike/sheet-folding/v1`:

```json
{
  "contract": "spike/sheet-folding/v1",
  "id": "coupon",
  "kind": "sheet_metal",
  "sheet": {
    "length_mm": 100.0,
    "width_mm": 20.0,
    "thickness_mm": 2.0,
    "material": null
  },
  "bends": [{
    "id": "bend-1",
    "start_x_mm": 30.0,
    "angle_deg": 90.0,
    "inside_radius_mm": 4.0,
    "k_factor": 0.5,
    "fixed_side": "negative_x",
    "segments": 12
  }],
  "flex_regions": []
}
```

`validate_sheet(raw)` rejects missing and unknown fields, non-finite values,
out-of-order or overlapping developed bend spans, unsupported fixed sides, and
unsupported topology. Its normalized result contains only public v1 fields, is
idempotently valid, and can be JSON-exported and re-imported without derived
preview fields leaking into the definition. `fold_sheet(raw, fraction=1)` returns
`spike/sheet-folding-preview/v1` with closed flat and folded triangle meshes.
Vertex and triangle IDs derive only from the source ID, mesh role, and mesh
indices, so identical input produces identical IDs. Triangle winding is outward;
each directed boundary edge has exactly one reverse mate and closed previews have
positive signed volume in the declared right-handed coordinate system.

`kind` is `sheet` (general/nonmetal), `sheet_metal`, `flex_pcb`, or `rigid_flex_pcb`. The latter two require
one or more non-overlapping `flex_regions`; every bend's complete developed span
must fit in one region. Regions do not assert a stackup, material law, minimum
bend radius, or flex-cycle rating.

`material` is optional inert JSON. When it has the recognized shared material
snapshot envelope (`schema_version`, `material_id`, `revision`, `digest`, and
`record`), its identity and digest are validated by the shared material library.
Other JSON remains descriptive. The folding code does not select or infer
physical properties from either form.

Examples: [sheet-metal coupon](../examples/mcad/folded-sheet.spike-sheet.json)
and [rigid-flex strip](../examples/mcad/rigid-flex-strip.spike-sheet.json).
The latter retains a generic polyimide screening record; it is not a qualified
laminate, copper stackup or manufactured PCB. Properties do not predict
K-factor, forming feasibility or bend reliability in this geometric workflow.

The workspace does not yet map an existing PCB's copper/components to a fold,
attach its preview as a formed assembly part, import/unfold arbitrary STEP sheet
solids, generate exact folded BREP/STEP, or produce a solver-admitted folded mesh.
Those require additional source/assembly bindings and geometry validation.

## Independent formulation

Let `t` be thickness, `R` inside radius, `K` the supplied neutral-axis fraction
measured through thickness from the inner face, and `theta` the signed bend
angle in radians. The developed neutral-axis bend length is

```text
L = abs(theta) * (R + K*t).
```

This follows directly from circular arc length `radius * angle` at neutral-axis
radius `R + K*t`. `start_x_mm` is the first tangent in the flat definition and
the second is `start_x_mm + L`. This convention makes overlap and flex-region
containment explicit.

For the final solid preview, its mid-surface radius is `Rm = R + t/2`. At local
angle `phi`, before applying the accumulated upstream rigid transform, the
mid-surface displacement is

```text
dx = Rm * sin(abs(phi))
dz = sign(theta) * Rm * (1 - cos(phi)).
```

The transported mid-surface normal is used to offset the two faces by `-t/2`
and `+t/2`. Consequently the final inside and outside cylindrical radii are
exactly `R` and `R+t`. Downstream stations receive the full rigid rotation and
translation. This separates the developed neutral-axis length from the rendered
mid-surface geometry; their arc lengths generally differ when `K != 0.5`, as
expected from through-thickness extension and compression.

At `fraction=0`, the output is exactly flat. For `0 < f <= 1`, the neutral-axis
radius is `(R+K*t)/f`, the applied angle is `f*theta`, and their product remains
the original developed allowance. The rendered mid-surface radius is therefore
`(R+K*t)/f + (0.5-K)*t`. Its limit as `f` approaches zero is the flat developed
span; at `f=1` its inside and outside offsets give exactly `R` and `R+t`. This is
a geometric kinematic convention, not a strain history or forming simulation.
The implementation evaluates the near-flat limit with sinc and half-angle
identities. It never forms the unbounded `(R+K*t)/f` value, so all admitted
fractions, including binary64 subnormal values, produce finite coordinates.

## Imports

`import_sheet_text(contents, source_format)` accepts:

- `json`: a complete v1 definition, validated immediately.
- `dxf`: dependency-free ASCII DXF containing exactly one closed, four-vertex,
  axis-aligned rectangular `LWPOLYLINE`. `$INSUNITS` must be 4 (millimetres) or
  absent/unitless. Unitless coordinates are explicitly marked as an assumption
  requiring review when interpreted as millimetres.

DXF has no sheet thickness. A successful DXF outline import therefore returns a
draft with `sheet.thickness_mm: null` and
`import_status: "requires_thickness"`. Set a reviewed positive thickness and
remove `import_status` before calling `validate_sheet` or `fold_sheet`. Lines,
arcs, circles, splines, bulges, multiple entities, arbitrary rotations, holes,
non-rectangular outlines, binary DXF, and non-mm declared units fail explicitly.
The four cyclic edges must each be nonzero and axis aligned, preventing a
self-crossing vertex order from being accepted as a rectangle. Mismatched x/y
coordinate counts, nonzero elevation or entity thickness, and non-default OCS
extrusion also fail rather than being silently projected into the XY plane.

## Evidence and verification

The governing bend-allowance relation was reviewed in Skyler Mondell,
*Understanding Mechanical Design With Respect to Manufacturability*, NASA NTRS
20110004137, 2010, section III.A.1, pp. 4-5, especially equation (3) and the
nomenclature defining K, thickness, radius, and angle:
https://ntrs.nasa.gov/citations/20110004137

That source also says material and grain influence neutral-axis location and
recommends a bent test piece for practical allowance. SPIKE therefore requires
the caller to supply K and makes no material prediction.

The implementation, derivation, data structures, examples, and test oracles are
independently authored. No third-party implementation was inspected or adapted.
Analytical tests cover the 90-degree arc endpoint, bend allowance, negative-angle
mirror symmetry, noncentral K-factor inside/outside radii and preserved neutral
arc length across fold fractions, exact flat fraction, sequential
parallel bends, stable IDs, flex confinement, overlap rejection, and importer
object, coordinate, unit, and unsupported-entity behavior.

Known numerical limits are ordinary binary64 trigonometric rounding and the
caller-selected angular segmentation. Segmentation refines the triangulated
appearance; station coordinates lie on the analytical cylinder. No convergence
claim is made for stresses because no stress solution exists. Knowledgeable
human numerical and manufacturing review remains required before release use.
Inside radius must be positive, flex regions are bounded to 256, and the preview
does not detect global self-intersection or collision between folded portions.
