# Explicit axisymmetric annular land reference

Status: experimental bounded numerical reference, October 21, 2026. This is a
standalone mixed finite-element land model with full azimuth symmetry. It does not
establish a general board/contact compiler or complete PI01 qualification.
`production_qualified` and `complete_board_physical_volume` remain false.

## Input and physical support

`spike_core.dc_annular_land.solve_annular_land(request)` accepts the exact
`spike/dc-annular-land-request/v1` object with `radial_planes_mm`,
`axial_planes_mm`, `conductivity_s_m`, and `contacts`. Every contact supplies
`id`, `attachment_id`, `face`, `interval_mm`, and signed `current_a`.
Positive current enters the domain. Faces are `r_min`, `r_max`, `z_min`,
`z_max`; an interval runs in z on a radial face or in radius on an axial face.
Every patch covers the entire azimuth and its endpoints must exactly match
supplied mesh planes. Unassigned boundary faces are insulating.

Attachment identities are provenance labels. Repeating one does not collapse
patches or make their potentials equal. Face IDs follow geometric support;
overlap is rejected, including overlapping zero-current patches. Uniform
normal injection uses each face's physical area divided by total patch area.
The area ratio is evaluated before multiplying the current to avoid premature
underflow. A nonzero current that stamps a zero face current is rejected.

The kernel admits positive homogeneous scalar conductivity from 1e-6 through
1e12 S/m, 2..8 patches, at most 512 cells, at most 65 planes on either axis,
coordinate magnitude at most 1e6 mm, minimum spacing 1e-9 mm and cell aspect
budget 1e4. Radius is strictly positive (at least 1e-9 mm); each radial cell
has outer/inner radius at most two. The r=0 axis is unsupported. Inputs are
strict finite real numbers, excluding booleans. Input current imbalance is
limited to 64 binary64 epsilons times the sum of current magnitudes.

## Governing equations and independently derived basis

The assumptions are stationary Ohmic conduction, constant positive sigma,
axisymmetry and no volumetric sources. In SI units,

```
J = -sigma grad(phi),  (1/r) d(r Jr)/dr + dJz/dz = 0,
P = integral (Jr^2 + Jz^2)/sigma * 2 pi r dr dz.
```

For one cell, let `a <= r <= b`, `c <= z <= d`, `h=d-c`,
`D=b^2-a^2`, `A=pi D`, `V=A h`, `s=(r^2-a^2)/D`, `t=(z-c)/h`.
Local degrees of freedom `q=[qr-,qr+,qz-,qz+]` are outward integrated face
currents in amperes. Define

```
Jr = [-qr- (1-s) + qr+ s] / (2 pi r h),
Jz = [-qz- (1-t) + qz+ t] / A.
```

Each basis has one unit outward integrated face flux, zero on the other
faces and divergence `1/V`. Thus local divergence vanishes exactly when
`sum(q)=0`. This is the contravariant RT0 construction under the change of
radial coordinate to r squared; no constant-Cartesian radial-density
approximation is made. Components have units A/m2, volume has m3, and
`q.T M q` has watts. The mass matrix is block diagonal:

```
Mr = 1/(2 pi sigma h) integral_a^b
     [[(1-s)^2, -(1-s)s], [-(1-s)s, s^2]] dr/r,
Mz = h/(sigma A) [[1/3, -1/6], [-1/6, 1/3]].
```

The axial block is analytic. The radial integral uses 16-point Gauss-Legendre
quadrature in the local radial coordinate; every cell is also evaluated at
32 points and rejected if the relative maximum-entry difference exceeds
1e-12. This comparison is a diagnostic, not a rigorous quadrature error
certificate. The bounded radial ratio avoids approaching the integrand's
axis singularity within a cell. Stable local differences avoid subtracting
large squared radii. The tests independently use adaptive scalar QUADPACK
integration, including a thin ring and the maximum admitted radial ratio.

Integrating Ohm's law against a basis gives
`M q + lambda - p 1 = 0`, with `p` the cell mean potential and `lambda`
the face mean potential. Eliminating `p` using local conservation gives

```
v = inv(M) 1, d = 1.T v,
H = inv(M) - v v.T / d,
q = -H lambda, p = v.T lambda/d.
```

Assemble H on shared face IDs. An interior face has zero sum of outward
currents from neighboring cells. A boundary face has prescribed outward
current `-Ipatch Aface/Apatch`, so the global equation is
`S lambda = -q_prescribed`. Fix face 0 to zero potential. Check all recovered
face equations, including the removed gauge equation, and all cell sums
against `1e-9 sum(abs(Ipatch))`. The diagonally scaled trace condition
estimate uses the existing rectangular reference's bounded estimator and
rejects estimates above 1e12 or failed estimation/factorization.

Multiplication of the local weak law by q gives `q.T M q = -q.T lambda`.
Interior terms cancel on assembly. Uniform patch flux therefore yields
`P = sum(Ipatch * mean_patch_phi)`, with area-weighted mean potential.
The kernel checks finite nonnegative cell powers and relative total heat/work
agreement at 1e-9; a nonzero-current solve with underflowed total heat rejects.
These residual/condition limits are operational acceptance screens, not
forward-error bounds for every field or tiny patch current. Each patch
retains absolute recovered-current error and the global absolute tolerance,
with `patch_relative_accuracy_certified=false`.

## Coupling and retained evidence

The result retains its source request/digest, raw face potentials, contact
face IDs/areas/mean potentials/recovered currents, and each cell's four
outward currents, physical bounds, volume, mean potential and Joule heat.
The exported radial endpoint numerators and axial endpoint component
densities reconstruct the complete two-component field using the formulas
above. Center samples are not a substitute for volume integration.

An external coupling layer may obtain linear responses from this API, solve
for actual interface currents and call this API again with those currents.
That must be a fresh physical solve: imposed-current heat from an unrelated
unit response is not a final coupled result. A patch couples uniform normal
current and area-mean voltage, not pointwise equipotential metal or a general
nonuniform interface distribution. Contact/barrel ownership, source-backed
geometry and circuit closure remain responsibilities of that external layer.

## Executed independent checks

Command: `.venv-emerge3/Scripts/python.exe -m unittest tests.python.test_dc_annular_land -v`.
Seven tests passed on October 21, 2026:

- Pure radial resistance `ln(b/a)/(2 pi sigma h)` and pure axial resistance
  `h/[sigma pi (b^2-a^2)]`, nonuniform meshes, current reversal and scaling.
  For a=0.1 mm, b=0.4 mm, h=0.1 mm and sigma=5.8e7 S/m, the resistances are
  3.80406207159744e-5 and 3.65873432395162e-6 ohm.
- Radial mass against independently evaluated adaptive scalar integrals.
- Harmonic `phi=C(r^2-2z^2)` with nonzero Jr and Jz: exact density, cell mean
  potential up to gauge and independent analytic total heat.
- Independent 32-by-3 Gauss integration of returned component fields with
  cylindrical volume measure, matching cell Joule heat and total work.
- Same-face spreading with opposite uniform currents on inner/outer bands:
  a=0.2 mm, b=0.6 mm, h=0.2 mm, interface radius 0.4 mm, sigma=5.8e7 S/m.
  Independent cell-centered finite-volume reference uses analytic radial
  edge resistance, axial conductance and Neumann boundary half cells.
  Its 64-by-32 and 128-by-64 grids give 8.141684484957875e-6 and
  8.131586982855074e-6 ohm (0.1242% relative difference). This is empirical
  refinement evidence, not a rigorous continuum tail/error bound.
- Strict invalid-input/overlap/balance checks, retained tiny-current stamps,
  and rejected nonzero-current heat underflow.
- Patch order and axial translation invariance, resource-limit admission and
  detached retained input evidence.

| Annular grid | Cells | Spreading resistance, ohm | Error vs finer FV |
| --- | ---: | ---: | ---: |
| 4 by 2 | 8 | 8.573142617527159e-6 | 5.4301% |
| 8 by 4 | 32 | 8.275036563177182e-6 | 1.7641% |
| 16 by 8 | 128 | 8.173479519602760e-6 | 0.5152% |

The retained spreading test requires reference-grid agreement below 0.2%,
monotonically improving three-level errors and finest error below 2%.
This one problem does not establish convergence rates for arbitrary patches
or singular edges, and no local maximum density convergence claim is made.

## Primary-law review and remaining limits

Reviewed on October 21, 2026: Haus and Melcher, *Electromagnetic Fields and
Energy*, MIT online edition,
[section 7.5, Example 7.5.2](https://web.mit.edu/6.013_book/www/chapter7/7.5.html)
(stationary Ohmic conductors, insulating boundary conditions, axial cylinder
and radial washer), and
[section 5.7](https://web.mit.edu/6.013_book/www/chapter5/5.7.html)
(polar-coordinate separation, radial logarithmic solutions and axis
regularity). The rendered surrounding derivations were reviewed; embedded
equation-image numbering was not treated as transcribed machine-readable
mathematics. The RT0 mass/hybrid algebra and finite-volume verification above
were independently derived for this implementation; those sources establish
the physical laws and analytic reference cases, not certification of this code.
Clean-room provenance: no external source implementation, mesh, fixture or
example code was used or translated. The source, documentation and tests are
original SPIKE material under the repository's Apache-2.0 boundary.

There is no azimuthal current/crowding, offset via, arbitrary polygon,
nonuniform material, inferred electrode, arbitrary interface load profile,
AC/skin effect, transient, thermal mapping or manufactured-board validation.
General contact/land transition and complete board coverage require separate
evidence. Knowledgeable human numerical review before release remains open.
