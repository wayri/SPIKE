<!-- SPDX-License-Identifier: Apache-2.0 -->
# Independent tetrahedral DC derivation and oracles

Status: experimental mathematical reference. This document and its tests were
authored independently of the tetrahedral kernel by a separate review worker.
They do not establish board completeness, material characterization, physical
validation, production qualification, or the required knowledgeable human
review before numerical code release.

## Foundations actually reviewed

Reviewed 23 October 2026, online editions at the URLs below:

- Haus and Melcher, *Electromagnetic Fields and Energy*, MIT online Chapter
  7.2, "Steady Ohmic Conduction": steady conservation, potential formulation,
  continuity conditions, insulating boundary, and conductance discussion.
  <https://web.mit.edu/6.013_book/www/chapter7/7.2.html>
- Same work, Chapter 7.4, "Superposition and Uniqueness of Steady Conduction
  Solutions": mixed boundary data, linear superposition, conductance matrix,
  and uniqueness discussion.
  <https://web.mit.edu/6.013_book/www/chapter7/7.4.html>
- DefElement, "Raviart-Thomas", definition table: tetrahedral polynomial space,
  facet normal moments, four lowest-order tetrahedral degrees of freedom,
  contravariant Piola mapping, and normal-component continuity.
  <https://defelement.org/elements/raviart-thomas.html>

The DefElement definition table is an authoritative element-family reference,
not the original historical RT paper. The browser returned public API creation
snippets adjacent to the table; no external implementation source, basis
example, mesh, or test data was used. The derivation, fixtures, and quadrature
below are independently authored. These citations describe mathematical
foundations and do not import source code or redistribution rights.

## Physical problem and energy identity

Let a conductor have positive scalar conductivity sigma [S/m], electrical
potential phi [V], and current density J [A/m^2]. Assume steady Ohmic response,
no volumetric current source, and no displacement-current, temperature,
frequency, magnetic, anisotropic, or nonlinear dependence:

    J = -sigma grad(phi),       div(J) = 0.

A finite terminal patch p imposes a constant inward density I_p/A_p, where
I_p [A] is positive into the conductor. All other exterior faces are insulating.
This is a prescribed-flux patch, not an equipotential electrode. Each connected
component separately requires sum_p I_p = 0. Fixing one scalar potential gauge
per component removes the otherwise arbitrary additive constant. No gauge can
repair an unbalanced component.

Multiplying the constitutive law by J/sigma and integrating, then using
div(J)=0 and the divergence theorem, gives

    P = integral |J|^2/sigma dV
      = -integral_boundary phi J.n dA
      = sum_p I_p mean_patch(phi).

P is heat in watts. The patch mean must use area weights; a vertex mean or
unweighted triangle mean is generally incorrect. The expression is gauge
independent exactly because the component current balance is zero. At material
interfaces phi and J.n are continuous; E.n need not be continuous.

## Independent finite-element derivation

For a tetrahedron K with vertices v_0,...,v_3 and volume V, face i is opposite
v_i. Its altitude is 3V/A_i. The vector

    b_i(x) = (x-v_i)/(3V)

has integrated outward normal flux 1 on face i and 0 on every other face: on
the opposite face the numerator's normal component is the altitude, while
on a face containing v_i the numerator is tangent. Therefore

    J_K(x) = sum_i q_i b_i(x),  div(J_K) = sum_i q_i / V,

where q_i is outward face current [A]. With no volume source, sum_i q_i=0;
the resulting lowest-order field is constant within each tetrahedron. Keeping
the affine representation remains useful for checking trace/field consistency.
For a shared face, the two outward currents must sum to zero.

Test the constitutive relation with b_i and integrate grad(phi) by parts.
Because div(b_i)=1/V, with cell mean u and face mean trace lambda_i,

    M q - 1 u + lambda = 0,     1^T q = 0,
    M_ij = integral_K b_i.b_j / sigma dV.

M is symmetric positive definite for a nondegenerate tetrahedron and positive
sigma. Eliminating q and u produces a positive semidefinite trace operator
with one constant nullspace per connected component. Choosing a gauge must
not remove its conservation equation from post-solve checks.

This is a derivation from face moments and integration by parts, independent
of the kernel's matrix-construction implementation. It predicts conservation,
reciprocity, nonnegative energy, and exact constant-current fields.

## Independent volume quadrature

For uniform volume averaging over a tetrahedron, repeated integration over
the unit simplex gives E[lambda_i]=1/4, E[lambda_i^2]=1/10, and
E[lambda_i lambda_j]=1/20 for distinct barycentric coordinates. An equal-weight
four-point rule has one coordinate a and three coordinates b at each point.
Solving a+3b=1 and (a^2+3b^2)/4=1/10 gives

    a=(5+3 sqrt(5))/20,    b=(5-sqrt(5))/20.

It integrates every quadratic polynomial exactly. Tests obtain current at
these points by barycentric interpolation of the four returned vertex values,
then independently sum V/4 * |J|^2/sigma. The kernel's mass matrices and moment
helpers are never imported. Tests also recover each face current by dotting
the mean of its three current values with an independently oriented area
vector, and compute cell volume from a determinant.

## Analytical and refinement fixtures

`tests/python/test_dc_tetra_rt0.py` creates original Cartesian tetrahedral
meshes; no external geometry or solver output is imported.

| Fixture | Independent expected value | Acceptance |
| --- | --- | --- |
| 2 x 3 x 4 m slab, sigma=5 S/m, I=6 A | J=(0.5,0,0) A/m^2, drop=0.2 V, P=1.2 W | field 1e-9 absolute; voltage/heat nine decimal places |
| Same slab expressed in mm | Same physical solution | same limits and independent SI volume integration |
| Unit slab, rotation about (1,2,3), translation | J=R(3,0,0), P=4.5 W | field 2e-8 absolute; heat eight decimal places |
| Unit slab, two half-length layers sigma=2,8 S/m, I=2 A | J=(2,0,0), R=5/16 ohm, drop=5/8 V, P=5/4 W | field 2e-9; energy/voltage nine decimal places |
| Six terminals, sigma=4 S/m | J=(2,-3,5), P=38/4 W | field 2e-9; energy eight decimal places |
| Disconnected 1 m^3 driven and 8 m^3 undriven solids | retain all 9 m^3, exactly zero undriven field | volume ten decimal places; componentwise balance enforced |
| Zero excitation | zero field and heat, full volume retained | exact zeros |

The nonuniform continuum fixture uses phi=x*y on the unit cube, sigma=1,
J=(-y,-x,0), div(J)=0, and exact heat integral P=2/3 W. Each exterior triangle
receives the exact integral of the linear normal current, obtained from its
centroid. The terminal condition remains piecewise constant on each triangle;
it approaches the continuous normal condition on refinement. This exercises
both boundary-data approximation and field approximation. It is not an exact
RT0 representable patch test.

For n=1,2,4 subdivisions in each direction (6,48,384 tetrahedra), independent
quadrature measures the L2 current error over the full volume. Each refinement
must reduce this error by a factor below 0.65 and the heat error by a factor
below 0.4. The finest field error must be below 0.12 A/m^2 times sqrt(m^3)
and heat error below 0.02 W. These acceptance thresholds were written before
running the new solver. Passing this fixture establishes convergence for this
smooth polynomial and boundary approximation, not a universal rate for finite
contact edges, arbitrary meshes, or high-contrast conductors.

All executed fixtures additionally check cell conservation, shared-face
continuity, contact current recovery, field-integrated heat, and signed
terminal work. Scalar absolute tolerances are 1e-9 A for these ordinary-scale
fixtures; heat/work use relative tolerances 1e-9/1e-8 with explicit small floors.
These test tolerances are not admission rules for arbitrarily tiny excitation.

### Physical-volume current quantiles

For this harmonic solution, |J|=sqrt(x^2+y^2). Since it is independent of z,
its volume CDF is the area inside a radius-r disk in the unit first-quadrant
square. For r<=1 this is pi*r^2/4. For 1<=r<=sqrt(2), split the x integral
at a=sqrt(r^2-1): area=a+integral_a^1 sqrt(r^2-x^2) dx. Evaluating this
antiderivative and using asin(a/r)=pi/2-asin(1/r) gives

    F(r) = sqrt(r^2-1) + r^2 * (asin(1/r)-pi/4).

Sixty bounded bisections give continuum p95=1.1981088515846348 A/m^2 and
p99=1.3155155640525038 A/m^2. The pre-execution acceptance rule is less than
10% relative error for both endpoints of each reconstructed quantile interval
on n=4. This rule checks continuum approximation at this declared resolution;
the much narrower returned intervals enclose the discrete field's quantiles
only, and must never be interpreted as continuum uncertainty intervals.

## Adversarial scope and execution

Tests reject missing/extra/nonpositive/boolean conductivity, nonfinite or
boolean currents, repeated/missing face nodes, duplicate contacts or reused
faces, internal contact faces, intersecting solids, exceeded cell/contact
budgets, cross-net shared faces, cells with mixed source nets, and
componentwise imbalance. Finite-patch reciprocity and current reversal exercise
three contacts with nonuniform spreading. A second disconnected fixture drives
both components independently and checks two gauges and summed heat. Retained
witness tests reject forged vectors, cell potentials, heat, face currents,
terminal currents, quantiles, board completeness, and production status.

Review found and repaired two issues in the candidate: admission errors escaped
the advertised exception type, and I=1e-160 A could produce matching rounded
subnormal heat/work that passed a relative check despite insufficient precision.
The kernel now rejects nonzero subnormal cell heat, and retained admission
independently enforces that guard. Regressions include 1e-160, 1e-200 and the
smallest positive representable current, plus a resolvable 1e-100 A solution.

On 23 October 2026, all 14 tests passed (1.483 s test-runner duration) using
`.venv-emerge3/Scripts/python.exe -B` and explicit import aliases for the four
candidate modules under `build/pi01-board-volume-20261023/pending/`. This
permitted verification during the separate qualification freeze without writes
to implementation roots or bytecode caches. An earlier 12-test run additionally
wrapped every successful result in `validate_tetra_dc`; all passed (1.187 s).
After publication, the original 14 oracles passed through ordinary imports
(1.020 s), then the final 22-test run below exercised the integrated changes.

Candidate SHA-256 identities for that execution:

```text
dc_tetra_rt0.py           4eaee79bf37fd3ff3de7a521dca1a027be4a6ede76b46ad337e057b5aa31bddd
dc_tetra_rt0_input.py     cb211b0057b1bcfea6cc84bbbdae17d870f4ba2544616662897f5f35014db249
dc_tetra_density.py       ce73194f9f2b8878ed8d94ab12f9a6975a7f59b305f6f40f67278323d84fbb70
dc_tetra_rt0_evidence.py  3a7a2c772e05c97a03e8540926f03978aa766320750f14e20c2725fb67bccbd3
```

| n | Tetrahedra | Current L2 error | Heat W | Absolute heat error W | Discrete p95 A/m^2 | Discrete p99 A/m^2 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 6 | 0.3333333333333335 | 0.5555555555555556 | 0.11111111111111105 | 0.942809041582064 | 0.942809041582064 |
| 2 | 48 | 0.1666666666666667 | 0.6388888888888884 | 0.027777777777778234 | 1.178511301977578 | 1.178511301977580 |
| 4 | 384 | 0.08333333333333304 | 0.6597222222222426 | 0.006944444444423992 | 1.178511301977587 | 1.296362432175340 |

The discrete p95 is unchanged between n=2 and n=4 to rounding, so quantile
convergence is not claimed monotonic. Finest p95 and p99 errors are about 1.64%
and 1.46%, below the frozen 10% rule. Finite-contact singularity convergence,
arbitrary mesh quality, high-contrast materials and real-board correlation
remain outside these fixtures; no such qualification is inferred.

## Independent composition review after integration

Review of `dc_board_source.py`, `dc_board_study.py`, and the retained tetrahedral
witness validator produced two additional failing counterexamples, preserved
in `tests/python/test_dc_board_review.py`:

1. Two disconnected unit cubes carry independently balanced currents of
   +/-1 A and +/-1e-12 A. Before repair, the retained validator accepted a
   forged record that erased every current, potential, field, and watt in the
   weak component, with its total and quantile summaries recomputed. Boundary
   residuals had been scaled by the strongest drive across all components.
   Kernel and validator now use each connected component's own drive magnitude
   for cell, face, and gauge conservation checks. Each driven component also
   requires positive heat/work and its own energy identity. Component terminal
   work is computed from prescribed face currents and traces, so a patch
   spanning multiple components is apportioned by physical face support.
2. Source-run replay accepted a changed `source_request.contract` and unknown
   extra request fields, although fresh execution rejected both. The same
   strict request contract/key-set admission now runs before execution and
   before retained source replay. Both mutations now fail closed.

The independent reviewer reproduced each acceptance before repair, inspected
the changes, and reran these tests with ordinary module imports:

```text
.venv-emerge3/Scripts/python.exe -B -m unittest
  tests.python.test_dc_tetra_rt0 tests.python.test_dc_board_review
  tests.python.test_dc_board_source tests.python.test_dc_board_study -v
```

All 22 tests passed on 23 October 2026 (3.486 s test-runner duration): 14
independent numerical oracles, two review regressions, four source-adapter
tests, and two retained-study tests. This supersedes the pending-publication
qualification of the earlier scratch run. Integrated reviewed SHA-256:

```text
dc_tetra_rt0.py           2f02bed7c227288a0510108ec03f57366d8aa8acfd7dfb7d9ec6b170c5fd12bd
dc_tetra_rt0_evidence.py  f06b01d237f4dfa2c808480e63b4069b43bda71ad3caa9542453396e0ea1f967
dc_board_source.py        bb370793c6be8050ba19254e4f14bdd626265b6e1bdd6dda0ac658afcf43827b
dc_board_study.py         3a8821a0eab780381a3dfbec93251c708c48e345ce3c39a23962df727c04d13f
```

No further consequential flaw was identified within these reviewed boundaries.
This is bounded experimental review, not knowledgeable human release approval.
Native pad positions and custom copper polygons still depend on the existing
importer; the auxiliary inventory specifically authenticates pad metadata and
direct via geometry, rather than independently reimplementing footprint
transforms or custom polygons. The source model explicitly declares supplied
plating/conductivity, layer-profile provenance, polygonal curve approximation,
and full-pad prescribed-flux electrodes. It does not recover an original point
terminal study, certify finite-contact singularities, or establish full-board
PI/SI readiness. Small patches within one strongly driven component retain
`patch_relative_accuracy_certified=false`; component-level conservation is not
a relative-accuracy certificate for every individual patch.
