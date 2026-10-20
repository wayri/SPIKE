<!-- SPDX-License-Identifier: Apache-2.0 -->
# Experimental same-slab affine magnetic integral, 19 October 2026

This bounded kernel increment addresses the unusably broad self/touching
integration envelopes of the existing isolated affine-prism candidate. It is
not registered, bound to Python, or selected by an extractor. It neither fixes
nor qualifies the original EBrake `/AOUT1` AC request. Its original completed,
positive-R/L, copper-support and energy gates remain unchanged.

## Reviewed sources and clean-room scope

Reviewed 2026-10-19:

- M. T. Homer Reid, *Taylor-Duffy Method for Singular Tetrahedron-Product
  Integrals: Efficient Evaluation of Galerkin Integrals for VIE Solvers*,
  arXiv:1708.04666v1, 7 August 2017. The [primary full text](https://arxiv.org/html/1708.04666)
  section I equation (1), section II-A equation (4), section II-B equation (5),
  and section II-C equations (6)-(10) establish the polynomial-times-radial
  kernel, relative-coordinate reduction and singularity-transform strategy.
  This is a preprint reference, not certification of this candidate. Its
  tetrahedron tables, source implementation and code generator were not used.
- Haus and Melcher, *Electromagnetic Fields and Energy*, MIT online edition,
  [section 8.1](https://web.mit.edu/6.013_book/www/chapter8/8.1.html), text discussion
  of the vector Poisson equation, vector-potential superposition and conserved
  assembled currents around equations (5)-(9). The equation-image request was
  unavailable; this records the reviewed prose, not a claim to have inspected
  every displayed equation. Individual partial-current bases need not be
  solenoidal; their assembled physical-current continuity remains a separate
  circuit/field requirement.

The equal-slab thickness reduction, overlap-domain decomposition, data
structures, C++ implementation and tests below were independently authored
from these mathematical foundations. No external implementation, test fixture,
symbolic output or tables were copied, translated or adapted. Existing SPIKE
rectangle integration is an independent internal oracle, not a source for the
new integration algorithm. Knowledgeable human numerical review before release
remains mandatory under `CONTRIBUTING.md` and `NUMERICAL_METHOD_EVIDENCE.md`.

## Independent derivation and units

For planar CCW triangles T and U extruded over the identical interval [z0,z0+h],
let b(x), c(y) be arbitrary affine vector current densities per ampere, constant
in z. Coordinates are metres; these fields have units 1/m^2. The existing PEEC
bilinear form is

`L = mu/(4*pi) integral_T integral_U b(x).c(y) K_h(|x-y|) dy dx`.

Integrating the finite Coulomb kernel through both thickness variables gives

`K_h(rho) = 2 integral_0^h (h-s)/sqrt(rho^2+s^2) ds`

`= 2 [h asinh(h/rho) - sqrt(rho^2+h^2) + rho]`.

The code evaluates the subtraction in rationalized form
`sqrt(rho^2+h^2)-rho = h^2/(hypot(rho,h)+rho)`.
There is no softening radius, skipped singular sample or thin-sheet replacement.
K has units m and behaves logarithmically at rho=0. The final quantity has
units H: `(H/m)*(m^4)*(1/m^4)*(m)`.

Change variables to d=x-y (unit Jacobian), giving

`L = mu/(4*pi) integral_(T-U) K_h(|d|) M(d) dd`,

`M(d) = integral_(T intersect (U+d)) b(x).c(x-d) dx`.

The overlap polygon is the exact integration-domain intersection, not a
modification of either physical basis. For fixed d its integrand is degree two.
Fan triangulation and three symmetric degree-two triangle samples therefore
evaluate M exactly in exact arithmetic. In particular overlapping currents
retain their full cross energy; no branch or physical copper is removed.

T-U is the convex hull of nine vertex differences. Overlap-vertex formulas
change when a vertex of either triangle lies on a translated edge of the
other. Splitting this convex domain on those 18 supporting lines keeps these
piecewise-polynomial changes out of cubature-cell interiors. A partition area
check at relative 1e-11 fails closed on a material geometry discrepancy; it is
an integration-domain arithmetic check, not a relaxed copper-support tolerance.

Each convex region is triangulated about the origin if it contains the origin,
otherwise about its vertex mean. On a resulting sector (o,a,b), use

`d = o + u^2 [(1-v)(a-o) + v(b-o)], 0<u,v<1`,

with Jacobian `2*u^3*cross(a-o,b-o)`. For o=0 the singular factor becomes
`O(u^3 log(u))`; Gauss nodes are interior and never evaluate rho=0. Otherwise
the sector has no interior singularity. Topological break lines, not numerical
quadrature, determine the retained displacement partition.

## Numerical contract and limits

`src/peec/affine_slab_inductance.hpp/.cpp` adds `same_slab_mutual` without changing
the original conservative-envelope `mutual` or separated-only APIs. Equal z
intervals are required exactly. The established triangle geometry/conditioning
checks are reused; malformed or unequal-slab inputs throw. Annular/mixed
barrel terms, different copper layers and thickness-varying current are not
implemented. Same-slab overlap, touch and separation are admitted geometrically.

Nested-work 4-by-4 and 8-by-8 tensor Gauss rules estimate local error as eight
times their difference plus a magnitude-scaled floating-point indicator.
These rules are not nested-node rules. Adaptive bisection alternates parameter
directions and refines the cell with the largest estimated error. Stopping is
`sum(error) <= absolute_tolerance_h + relative_tolerance*abs(sum(value))`.
`estimated_error_h` is explicitly an a posteriori estimate, NOT an analytic
or interval bound. Two agreeing quadratures alone cannot certify an error,
especially on ill-conditioned inputs or cancellation-dominated entries.
The old conservative result's `error_bound_estimate_h` is not repurposed.

Defaults are absolute 1e-17 H, relative 1e-6, 500,000 integrand evaluations and
4,096 active cells. Hard limits are 10 million evaluations, 65,536 active cells
and 512 displacement regions. Each cell costs exactly 80 samples; a split costs
160. Insufficient initial or refinement budget returns `converged=false`; an
initial-budget failure returns no partial integral and a maximal finite error
sentinel. The bounded local geometry partition precedes the quadrature budget.
There is no in-kernel cancellation callback; execution remains suitable only
behind process-level cancellation. This is not a scalable board matrix engine.

There is no eigenvalue projection, diagonal shift, basis-width repair or energy
clamp. Canonical pair ordering preserves reciprocity of the adaptive traversal.
Roundoff floors, matrix conditioning, full support/contact assembly and original
passivity gates remain independent admission authorities.

## Verification scope

`tests/test_affine_triangle_basis.cpp` retains all pre-existing failed-tight-
envelope checks and adds:

- A 1 mm square split into two triangular prisms, with every self and touching
  cross term retained, versus the separate native rectangular volume kernel at
  thicknesses 1 mm, 35 um and 1 um. The new path uses absolute 1e-20 H and
  relative 1e-7; the rectangle oracle uses 1e-20 H / 1e-9 and explicit larger
  reference-only budgets. Accuracy gate: 2e-7 relative, and agreement within
  the sum of independently reported estimates.
- An independently derived affine cube difference-coordinate oracle (retained
  from the prior primitive test), now with a 2e-7 relative accuracy gate rather
  than merely containment in the old broad analytic envelope.
- Thin RT0 self integration, tighter fixed-support integration sensitivity,
  rotation/translation, orientation reversal, SI scaling, reciprocity, overlap,
  exact zero and a six-dimensional separated-pair oracle.
- All six independent local three-face magnetic-matrix entries and all 125
  integer-current combinations in [-2,2]^3, requiring nonnegative unprojected
  quadratic energy, plus positive scaled Cholesky pivots for the complete
  unmodified local 3-by-3 matrix. Neither check proves general board passivity.
- Invalid tolerance, nonfinite fields, inverted supports, unequal slabs and
  exhausted evaluation/memory admission.

This is synthetic numerical verification, not measured physical validation.
The tested aspect ratios, oracle tolerances and resource limits do not establish
accuracy for arbitrary sliver triangles, large coordinate offsets, cancellation,
field frequencies or imported boards.

### Executed Windows evidence

MSVC 19.51.36256.0, C++20, `/W4 /WX /fp:strict`, Release: the final complete
`test_affine_triangle_basis` CTest passes in 17.82 seconds (17.86 seconds total).
This includes all old primitive checks and the new independent rectangle oracle
work; it is not the runtime of one magnetic pair. Architecture and scoped
`git diff --check` pass. Reproduce from an already configured test build:

```powershell
cmake --build build/affine-verify-elevated-20260924 --target test_affine_triangle_basis --config Release
ctest --test-dir build/affine-verify-elevated-20260924 -C Release -R '^test_affine_triangle_basis$' --output-on-failure
.venv/Scripts/python.exe scripts/check_architecture.py
```

The native log is
`build/affine-verify-elevated-20260924/Testing/Temporary/LastTest.log`.
The executable is
`build/affine-verify-elevated-20260924/Release/test_affine_triangle_basis.exe`.
These build artifacts are local evidence, not redistributed solver payloads.

| Thickness | Two-triangle square L (H), rounded | Summed estimated error (H) | Weighted pair evaluations |
| --- | ---: | ---: | ---: |
| 1 mm | 1.88231e-10 | 1.80681e-17 | 72,000 |
| 35 um | 2.90372e-10 | 2.86975e-17 | 154,560 |
| 1 um | 2.97112e-10 | 2.97076e-17 | 363,840 |

Weighted evaluations count `N_aa + 2*N_ab + N_bb`, corresponding to all four
terms, though the reciprocal cross term is computed only once. The independent
rectangle oracle converged for all three at its tighter declared tolerance;
its evaluations were 6,087,270, 5,359,438 and 2,953,230. Those are different
algorithms, tolerances and work units, not a general performance comparison.

The 1 mm by 35 um unit-face RT0 triangle self result is 2.53546e-11 H with
estimated error 2.53386e-18 H after 64,960 evaluations. Its 1e-8-relative tighter
run also passes the declared fixed-support integration-sensitivity check.
The old conservative cube self test still correctly returns resource-limit at
200,001 evaluations with estimate 5.46505e-8 H and envelope 1.97691e-8 H.
These are different fields/geometries, so no equal-error speedup is inferred.

GCC 16.2.0 (MSYS2 UCRT64, Windows), C++20 with `-O2 -Wall -Wextra -Werror
-fno-fast-math -ffp-contract=off`, also compiled the final sources successfully.
The final static-runtime GCC executable completed all checks with exit code zero
and the same rounded values/evaluation counts above. Its buffered output was
returned after completion; no reliable separate elapsed runtime was retained.
This is a second compiler on Windows, not Linux or general platform qualification.
The exact standalone build is:

```powershell
$env:PATH='C:/msys64/ucrt64/bin;'+$env:PATH
& 'C:/msys64/ucrt64/bin/g++.exe' -std=c++20 -O2 -Wall -Wextra -Werror -fno-fast-math -ffp-contract=off -static-libgcc -static-libstdc++ -I src src/peec/affine_triangle_basis.cpp src/peec/affine_slab_inductance.cpp src/peec/volume_inductance.cpp tests/test_affine_triangle_basis.cpp -o build/affine-verify-elevated-20260924/test_affine_triangle_gcc.exe
& build/affine-verify-elevated-20260924/test_affine_triangle_gcc.exe
```

Final source SHA-256 bindings for this execution:

| File | SHA-256 |
| --- | --- |
| `src/peec/affine_slab_inductance.cpp` | `0c41db17e6a58014552240698d28c924f268ef899c64502a5224010e6ad6bbc2` |
| `src/peec/affine_slab_inductance.hpp` | `c911acfd1cfec0ee3b67ca0a4139e57fffd17ef92a9b75531a530763768c6e8f` |
| `tests/test_affine_triangle_basis.cpp` | `315ba8cb16093e72ff189e723c2663fe053d706ff931a6724e19a8dad875597b` |

## Remaining original EBrake blockers

The retained clipped zone support still needs an owned conforming copper
partition and shared-face/contact compiler. `MeshBranch` still holds scalar
rectangle dimensions, and the production native binding still only accepts
rectangles/axial annuli. Drilled pads, finite pad/via contacts, affine/annulus and
inter-layer mixed magnetic terms, consistent frequency-dependent R, dense
resource policy and complete board refinement are unresolved. Nothing here
wires RT0 DC current into rectangular legacy L, omits rejected copper, or changes
the original fixture's terminals, geometry counts, positive R/L assertions or
support/energy tolerances. Only an actual unchanged original AC run can close
that acceptance gate.
