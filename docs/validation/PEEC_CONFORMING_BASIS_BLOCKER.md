<!-- SPDX-License-Identifier: MIT -->
<!-- Copyright (c) 2026 SigHarmonic -->
# PEEC conforming basis and finite contact blocker

Date: 2026-09-24. Diagnostic evidence; no corrected AC extraction or release
qualification. The current branch geometry cannot express the conforming
boundary/contact correction. `hybrid_mesh.py` is deliberately unchanged.

## Isolated affine-prism verification kernel

`src/peec/affine_triangle_basis.hpp/.cpp` now implements exact local affine
current moments and same-prism resistance, plus a bounded mutual-inductance
integral for **strictly separated** triangular prisms. It is deliberately not
connected to the board extractor or Python binding. The manufactured shared-face
unit-flux pair gives `0.0001642036124794745 ohm`, matching its analytic
resistance. An independent six-dimensional reference also agrees with a
separated mutual result (`5.55826e-10 H` versus `5.55794e-10 H`, reported
estimate `1.61853e-11 H`). The estimate includes a floating-point roundoff
indicator; it is not a certified interval bound.

`test_affine_triangle_basis` is registered as an isolated CTest target. It
passes strict MSVC and GCC builds. Touching/self prism inductance, overlapping
supports, annular cross terms, composite basis assembly, terminal/via contact
stamping, and board convergence are still unsupported. The current public
Marble AC run remains ineligible under the copper-support gate; this kernel
does not change that status.

## Reproduced geometry and contact evidence

Run from the repository root with the qualification interpreter, NumPy and
Shapely. Shapely is used only for independent diagnostic polygon differences.

```powershell
build/qualification-py311/Scripts/python.exe scripts/audit_peec_conforming_basis.py --board build/marble-qualification/sources/Marble-v1.4.4/design/Marble.kicad_pcb --output build/marble-volume-20260924/conforming-basis-audit.json
```

The script verifies board SHA-256
`3304ba37c2bd891849fc36b500cd940934aaf1f2013a95639c03564fb925c512`.
It retains the C383-named net, original layer/stackup geometry and anchored
U37.18/R195.1 terminals. Its one-ampere resistive solve intentionally inspects
the unqualified mesh directly; it bypasses volume-adapter admission and is not
an admitted solver result. No C, L or skin-loss increment enters this solve.

| Quantity | 1 mm | 0.75 mm | 0.5 mm |
| --- | ---: | ---: | ---: |
| All physical bases | 45 | 64 | 120 |
| Physical bases in routed component | 36 | 51 | 103 |
| Zone bases outside source copper | 7 | 9 | 19 |
| Summed outside support area, mm^2 | 0.558522869 | 0.434589429 | 0.710276566 |
| Diagnostic port R, mOhm | 4.778865323 | 4.377684231 | 5.251177223 |
| Zone-attachment loss / I^2, mOhm | 0.279059401 | 0.149328697 | 0.220254340 |
| Pad-attachment loss / I^2, mOhm | 0.396052099 | 0.386790191 | 0.304072910 |
| Pad-zone-attachment loss / I^2, mOhm | 0.188818892 | 0.012398837 | 0.590558877 |
| Total attachment share of port loss | 18.078% | 12.530% | 21.231% |
| MNA relative residual | 2.10e-16 | 1.34e-16 | 1.37e-16 |

The maximum nodal current balance error is at most 1.12e-16 A for all three
levels. Boundary-support admission fails at every level at 1e-8 mm^2 per basis.
Summed basis-support areas count overlapping bases separately, not unique copper.

U37.18 resolves to (232.9726, 159.4734) mm and R195.1 to
(233.0832, 159.3850) mm at every level, exactly their imported pad centers.
The retained pad sizes are respectively (1.05, 0.35) and (0.62, 0.58) mm.
Thus the observed drift is not a shift in the selected terminal coordinate.
The code still injects a nodal current rather than defining a finite terminal
contact distribution. C383.1 remains disconnected at all levels.

No native L extraction was repeated after this failed geometry gate. The
existing passive but nonconverged L evidence is recorded in
[the volume correction record](../PEEC_VOLUME_CORRECTION_20260924.md).
Its passivity result remains evidence about those supplied bases, not proof of
correct support or a new conforming extraction.

## Why changing width or attachment resistance is insufficient

`_Builder.zones` clips control/display cells but assigns one full-cell width
to a branch between their interior points. A shared edge can be oblique to
this branch, and a clipped cell can have several independent boundary normals.
The current support therefore is not the union of the incident clipped cells
and the branch width is not a shared-face flux normalization.

The native `RectangularVolume` in `src/peec/volume_inductance.hpp` fixes the
basis to a constant vector `direction/(width*thickness)` over a rectangle.
`VolumeBasis` in `src/peec/volume_matrix.hpp` is only a variant of that rectangle
and a uniform axial annulus. The Python binding exposes only
`add_rectangular` and `add_coaxial_annulus`; it has neither polygon pieces nor
spatial current coefficients. `MeshBranch` likewise stores only two endpoint
nodes and scalar width/thickness. Supplying a clipped polygon to the preview
cannot change the native R/L support.

A concrete obstruction: on the triangle with vertices (0,0), (a,0), (0,a),
require one ampere through the diagonal face and zero normal current through
the two coordinate-axis faces. For any constant planar vector, the two zero
normal conditions force both components to zero. It cannot carry the required
diagonal flux. Clipping a constant rectangle alone does not repair this local
continuity condition. A finite rectangular partition also cannot exactly tile
a general polygon with acute nonrectangular corners. A staircase approximation
would need quantified omitted support/contact error and extra refinement; none
has been qualified here.

The current nearest-node attachments span finite distances, using cell or pad
widths that change with refinement. Replacing all of them by ideal links would
remove physical spreading loss. Their measured 12.5%-21.2% share means a
distributed contact correction can materially affect R, but it does not predict
the sign or magnitude of the corrected R. Holding the existing currents fixed,
the nonattachment loss is 3.914935, 3.829167 and 4.136291 mOhm, still nonmonotone.
Those values are an energy decomposition, not a solve with corrected contacts.
Actual distributed coupling changes the whole current field; no valid contact
correction can be claimed before its support and normalization are specified.

## Smallest proposed conforming interface

This is a design proposal, not an implemented or validated capability. It
requires an ADR because the mesh-to-native numerical boundary changes.

1. Partition the union of same-net copper on each layer into nonoverlapping
   triangles, retaining source IDs, holes, finite pad terminal patches and
   via contact footprints. Tracks, pads and zones must share this partition
   where they overlap. Preserve retained source-filled connectivity evidence;
   touching a point does not establish finite shared-face area.
2. Introduce a native affine triangular-prism piece with three planar vertices
   in metres, lower/upper z in metres, and vector coefficients defining
   `b(r)=c+M*(r-r0)` in 1/m^2. Store a basis as an ordered list of such pieces,
   with stable basis ID, orientation and adjacent cell IDs. Common triangular
   face-flux bases have two pieces; exterior terminal faces may have one.
   This representation avoids assuming every current basis is a rectangle
   perpendicular to its endpoint connection.
3. Assemble both `R_ij=integral(b_i dot b_j / sigma)` and
   `L_ij=mu/(4*pi)*double_integral(b_i dot b_j / distance)` from those identical
   pieces. Native integration needs affine moment integrals, including singular
   self/touching cases and mixed annular pairs, with error/resource admission.
   Extending only the polygon domain while retaining a constant numerator is
   insufficient. Keep the existing rectangle/annulus path for admitted inputs.
4. Define the cell/face incidence using integrated oriented flux. Cell
   potentials replace arbitrary independently meshed pad/zone center nodes.
   A terminal must specify its retained finite patch and an explicit excitation
   model (equipotential electrode or prescribed distributed injection); integrate
   that patch against the partition. A thin-sheet via coupling likewise maps
   the annular footprint into cell source terms and remains a documented 2.5D
   approximation until its junction physics is qualified.

For a triangle of area A and opposite vertex r0, the independently derived
unit-current face basis is `b(r)=(r-r0)/(2*A*t)` for thickness t, with sign
chosen consistently across the common face. Its selected-face flux is one,
the other two edge fluxes vanish, and its volume-integrated divergence is one.
On the adjacent triangle, reversing the sign gives continuous normal flux
and integrated divergence minus one. For a square of side a split along its
diagonal, these two pieces have exact combined loss
`R=1/(3*sigma*t)`; this is a basis matrix entry, not a whole-square terminal
resistance. At sigma=5.8e7 S/m and t=35e-6 m it is
0.0001642036124794745 Ohm. The diagnostic script checks this with independent
degree-two triangle quadrature and samples continuity along the common face.
This derivation and oracle were authored from the stated flux/energy invariants;
no external implementation was read or adapted.

## Minimum acceptance checks before a corrected board run

- Exact selected-face unit flux, zero exterior side flux and opposing integrated
  divergence on the manufactured triangle pair; verify orientation reversal,
  translation/rotation, SI scaling and analytic R above. Test degenerate,
  inverted and inconsistent pieces and contact patches outside retained copper.
- Manufactured rectangle-to-triangle subdivision: fixed finite terminal patches,
  identical copper union and current conservation under refinement. Verify R/L
  with independent reference integrals; symmetry and PSD alone are insufficient.
- Clipped and concave boundaries, narrow necks, holes, track/pad/zone overlaps,
  pad-edge contacts and annular footprints: correct components, no copper added
  outside tolerance, no silent lost contact, and positive physical contact area.
- Pinned Marble U37.18/R195.1 at three actual refinements: keep the terminal
  model fixed, satisfy the <=2% consecutive R/L change gate in the audit,
  separate quadrature sensitivity from mesh sensitivity, retain residual/current
  balance checks and zero passivity repair. C383.1 must remain disconnected.
- Qualify time/memory bounds, package parity, trusted independent reference and
  knowledgeable human numerical review before release capability claims.

The 18 existing hybrid-containment and volume-resistance tests passed in the
qualification CPython 3.11 interpreter. They protect their existing invariants;
they do not cover the proposed native basis. The fresh diagnostic run passed
its manufactured polynomial oracle and reproduced the three failed support
gates above. No production numerical code, tolerances or terminal selections
were changed in this diagnostic increment.
