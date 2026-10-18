<!-- SPDX-License-Identifier: Apache-2.0 -->
# Hybrid via barrel drill containment - 18 October 2026

## Scope and observed defect

`hybrid_mesh.py::_Builder.vias` provides circular via barrel faces and explicit
inner vertices to the existing `meshing.py` volume conversion. An inscribed
inner polygon put its chords inside the declared drill. For a 0.3 mm drill and
eight sides, the first chord midpoint was 0.13858192987669302 mm from the axis,
inside the 0.15 mm bore. This affects exported/displayed physical geometry.
This change does not establish accuracy of the DC or electromagnetic model.

## Reviewed foundation and independent derivation

Primary mathematical reference: Euclid, *Elements*, Book III, Proposition 18,
[Clark University edition by David Joyce](https://mathcs.clarku.edu/~djoyce/elements/bookIII/propIII18.html),
proposition and proof reviewed on 2026-10-18. The result establishes the normal
relationship between a circle's radius and its tangent. No external source
code, implementation, fixture, image or prose was copied. The following
formulation and regression were independently authored for SPIKE.

All dimensions use millimetres in the existing board frame. Assume a straight
circular cylindrical drill of radius r and constant plating thickness t > 0;
the outer radius is R = r+t. For N equally spaced unit normals n_i, tangent
lines satisfy n_i dot x = r. Their adjacent intersections define the existing
circumscribed-circle helper's inner polygon. Its edges stay outside the open
drill disk because their distance to the origin equals r. Its corner radius is
r/cos(pi/N). Outer vertices lie on radius R at the same
angles, so the two polygons are concentric and homothetic. Requiring
r/cos(pi/N) < R ensures positive wall thickness, and equivalently the outer
chords also clear the drill. Extrusion over the unchanged layer span therefore
cannot add conductor inside the bore. No material or field equation changes.

## Approximation, conditioning and limits

The outer polygon remains inscribed and the bore polygon circumscribed, so
polygonal barrel volume underestimates the analytic annulus. For fixed r,t the
radial deviations approach zero with order N^-2 as N grows. Existing initial
8--24 side sizing remains; sides double only when needed to preserve a positive
wall, with an explicit failure at 384 sides. Consequently this is a bounded
containment correction, not an arbitrary requested-accuracy guarantee.
The helper solves adjacent tangent intersections with determinant
sin(2*pi/N); N <= 384 bounds its reciprocal to approximately 61.12.

The equivalent electrical branch area remains pi*(drill+t)*t. It is analytically
the circular annular area, separate from the approximate exported mesh volume.
Blind/buried endpoint selection and existing default/clamped plating policies
remain limitations of the existing model. This record does not qualify general
drills, tapered microvias, machining tolerances, source provenance, native
viewport appearance or production physics. Human numerical review remains
required before release.

## Executed verification

`test_via_volume_faces_preserve_circular_drill_void_and_layer_span` uses an
independent closest-point-on-segment oracle, rather than reusing the tangent
helper, to check both inner and outer chords. It checks positive wall thickness,
explicit `hex8_barrel` geometry, and a front-to-inner-layer blind span for drill
and plating pairs (0.3, 0.025) mm and (3.0, 0.005) mm under coarse sizing.
The pre-change 0.3 mm example fails the chord-distance requirement above.

Executed with workspace-local TEMP/TMP after the sandbox default temporary
directory denied fixture writes:

```text
python -m unittest tests.python.test_hybrid_mesh_containment tests.python.test_kicad_via_types tests.python.test_pcb_volume_compiler tests.python.test_peec_conforming_mesh -q
Ran 42 tests: OK
python scripts/check_architecture.py
SPIKE architecture check passed
```

These are geometry and contract regressions, without physical measurement
validation. Existing numerical provenance gaps remain open.
