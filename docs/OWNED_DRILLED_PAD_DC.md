# Conservative owned pad geometry for DC

PI01-S01 is an opt-in extension of `pad_zone_coupling: owned_shared_faces`.
It is not full-board SI/PI qualification. Its status and executable evidence
are recorded in the parity backlog; availability alone does not establish
convergence on an imported board.

The underlying model remains steady Ohmic conduction, `J = sigma E`,
`E = -grad(V)`, and `div(J) = 0` away from terminals. See Haus and Melcher,
[*Electromagnetic Fields and Energy*, section 7.2](https://web.mit.edu/6.013_book/www/chapter7/7.2.html).
The geometry constructions and analytic checks below are original derivations.
The 19 October 2026 source review covered the online section's steady-current,
continuity, insulating-boundary and conductance prose. Displayed equation GIFs
were not transcribed. This is physical foundation, not third-party algorithm
lineage; no source text, figures or implementation was copied. No independent
measurements or material calibration establish predictive validation here.
Lengths supplied to the mesh are millimetres; resistance evaluation converts
lengths and areas to SI units. A graph face uses
`R = centroid_distance / (sigma * thickness * shared_face_width)`.
This two-point approximation requires convergence evidence, particularly for
nonorthogonal cells. Exact area ownership alone does not prove field accuracy.

## Drilled rounded rectangles

Retain the imported dimensions and radius `r = min(w,h) * roundrect_rratio`.
Use 32 inscribed chords per quarter circle on the outer land and a
circumscribed polygon on the centered circular or oval drill. Merge both
polygons' vertex angles and intersect each ray with both boundaries. Radial
interpolation partitions the resulting polygon annulus without adding an
area approximation. Shared faces use actual lengths and cells use polygon
centroids. Pad and surrounding zone interiors must have disjoint ownership.

For 128 total curved chords the outer area deficit is
`r^2/2 * (2*pi - 128*sin(2*pi/128))`, relative to the continuum area
`w*h - (4-pi)*r^2`. A circular drill of radius `a`, circumscribed with `N`
sides, adds void area `a^2 * (N*tan(pi/N) - pi)`. These two deficits add;
the circular expression is not an oval-drill formula. The maximum outer
chord sagitta is `r*(1-cos(pi/128))`.

EBrake J11.1 retains 1.7 by 1.95 mm dimensions, 0.95 mm centered drill,
and imported ratio 0.147059. The resulting radius 0.2500003 mm differs
from KiCad's quantized 0.25 mm by 0.3 nm. The chord sagitta is about
75.2954 nm; the rounding difference is separate. Tests check the continuum
envelope, entire cell edges against the drill, area budget, rotations,
positive ligaments, invalid metadata and allocation limits.

Plating must be finite and physically supported; the new drilled-roundrect
envelope rejects plating below 0.005 mm instead of silently flooring it.
The electrical barrel remains one branch per layer span, with width
`pi*(drill_diameter + plating_thickness)`, thickness equal to plating, and
length equal to the actual layer separation. Its angular landing remains
an approximation. Visual barrel quads do not define parallel electrical
branches or change the barrel conductance.

## Resolved convex custom SMD pads

The EBrake 3Vin selection also includes U2.35 and U2.39. The extension is
restricted to resolved, finite, simple convex polygons in pad-local
millimetres, with no holes and no drill. Retain the source polygon; a convex
hull is an admission check, never replacement copper. Existing finite-cell
clipping, centroid placement and actual shared faces provide the owned mesh.
Unresolved, nonconvex, holed or drilled custom geometry remains unsupported.
This scope requires dedicated source-area, containment, contact, rotation and
failure-case checks before promotion.

## Numerical references and limits

For a sheet annulus with radii `a,b`, conductivity `sigma`, thickness `t`,
and complete radial-edge electrodes at angular separation `theta`, the two
angular paths are in parallel. Integration of `dG = sigma*t*dr/(theta*r)`
gives `R = theta*(2*pi-theta)/(2*pi*sigma*t*ln(b/a))`.
The angular convergence check uses at least three actual mesh levels and a
fixed finest relative resistance error limit of 2%. The separate radial
annulus oracle `R = ln(b/a)/(2*pi*sigma*t)` retains its 1% bound. Neither
test qualifies arbitrary finite contacts, local current-density percentiles,
nor nonorthogonal field reconstruction.

Use `scripts/check_ebrake_owned_dc.py` for the full imported 3Vin selection
and original assumed 24 V / 1 A diagnostic terminals. It retains public CLI
output and the unchanged mesh-convergence checks. A successful mesh build
does not override a failed density, power, resistance or voltage-drop gate.
Original default EBrake acceptance and Marble admission checks remain
separate evidence. AC guards, default dispatch, material requirements,
resource limits and unsupported states remain in force. Electrical loss may
feed a future thermal coupling only with its recorded model status and
validated support; this extension adds no thermal or other physics solver.

The stage gate `scripts/parity_owned_pad_gate.py` executes the numerical tests,
records before/after source hashes, and binds the full-board request, CLI
result/log, convergence result and source-stable audit. Its geometry-stage
receipt preserves the board's convergence outcome, including a failure; it
does not promote that outcome to board sign-off. Knowledgeable human numerical
review remains required before release.
