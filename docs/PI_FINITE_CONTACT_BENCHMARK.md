<!-- SPDX-License-Identifier: Apache-2.0 -->
# PI01-S02A: finite-contact planar DC acceptance benchmark

This is a bounded prerequisite to PI01-S02, not its completion. It exercises
the existing experimental conforming RT0 solver and complete polygon compiler
without changing production dispatch or board acceptance thresholds. No new
solver engine or physical contact inference is introduced.

## Frozen acceptance, before execution

Three target edge lengths are 0.5, 0.25 and 0.125 mm. Every level must retain
all planar volume, finite contact areas, experimental status, and separate
resistance (ohm), dissipation (W at 1 A) and density (A/mm2) identities.
Cell and face KCL must be below 1e-8 A, relative linear residual and relative
terminal-work error below 1e-7. Finest relative resistance error must be below
0.002 and improve over the coarsest; no monotonic density claim is required.
Finest p95 and p99 enclosure endpoints must be within 2% of the analytical
values. These are discretization-error checks, not formal error enclosures.
Physical volume and inactive volume errors must be below 1e-10 mm3.

Execute a base sheet, its rigidly rotated counterpart, an explicitly doubled
conductivity sheet, and a sheet with a retained disconnected inactive island.
Each uses the same three physical contact/geometry levels. The rotated case
is compared to its analytical invariant. The original receipt used a rotated
conforming partition; the strengthened replay rotates source/contact polygons
before compilation and declares a 1e-12 mm geometry grid. The original physical
error tolerances remain fixed. Boundary, topology and contact uncertainty are
retained and verified with [explicit precision admission](DC_PRECISION_PARTITION.md).
Fail closed on missing/reordered levels, nonfinite fields, lost support,
changed contact/material identity, failed solver status, or altered tolerance.
An emitted report must be replayable through the validator; CLI exit status
must reflect failed acceptance. Report validation is not authentication of a
solver run: the stage gate additionally binds source hashes and actual tests.

## Governing physics and independent analytical reference

Reviewed on 2026-10-21: Haus and Melcher, MIT online *Electromagnetic Fields
and Energy*, [section 7.2](https://web.mit.edu/6.013_book/www/chapter7/7.2.html),
steady Ohmic conduction, conservation, insulating-boundary and conductance
discussions. The text supports steady conservation and Ohm's law; embedded
equation images were not separately transcribed. Also reviewed Vohralik,
*C. R. Math.* 339 (2004), pp.525–528,
[DOI 10.1016/j.crma.2004.08.004](https://comptes-rendus.academie-sciences.fr/mathematique/item/10.1016/j.crma.2004.08.004.pdf),
equations (1)–(3), p.526 compact oriented face basis. These establish the
mixed flux/potential foundation, not the particular benchmark solution.
No external implementation, mesh, test data or elimination algorithm was used.
All fixture geometry, derivation, code and adversarial controls are original.

A rectangular sheet has length L=2 mm, width w=1 mm, thickness t=0.035 mm,
conductivity sigma=5.8e7 S/m. Uniform through-thickness current +I enters the
left full-width strip 0<=x<=a and -I leaves L-a<=x<=L, with a=0.5 mm and I=1 A.
All exterior in-plane boundaries are insulating. These are distributed area
contacts, not equipotential electrodes. Sheet conductance is k=sigma*t*1e-3 S.
Integrating conservation across width gives Kx=I*x/(a*w) in the source,
I/w in the gap, and I*(L-x)/(a*w) in the sink, in A/mm; Ky=0.
Ohm's law gives dV/dx=-Kx/k. Terminal voltages are area-average potentials,
power conjugate to the prescribed area injection. Hence

`R = integral(Kx^2*w dx)/(k*I^2) = (L-4*a/3)/(k*w)`.

Each contact contributes I^2*a/(3*k*w) W and the gap contributes
I^2*(L-2*a)/(k*w) W; their sum equals I^2*R. The benchmark compares total
solved planar Joule loss and conjugate terminal work independently to this
integral, without substituting a branch histogram. Heat remains W, not J.
The source/sink density ramps cover half the active volume; the gap plateau
occupies the other half. Both physical-volume p95 and p99 are I/(w*t) A/mm2.
A separate 0.5 mm2 inactive island adds zero-current volume; this retains the
same p95/p99 plateau while checking volume inclusion. The doubled sigma case
halves resistance and heat, leaving current density and physical volume fixed.
Rigid rotation preserves these scalar observables. The area-distributed source
field is not exactly RT0 inside source triangles: its non-isotropic affine
gradient requires spatial refinement. It is therefore a genuine discretization
check, rather than only a reconstruction identity.

## Workflow and limits

Run `scripts/benchmark_pi_finite_contact.py --output <fresh repository JSON>`
with the documented NumPy/SciPy/Shapely environment. The output retains every
solver level, exact fixture identity, reference values, errors and acceptance
decisions. Sparse LU runtime/fill remain supervised offline risks. Polygonal
planar support only; no axial land/barrel ownership, source-file import, AC,
thermal-cell allocation, material law, measurement or release qualification.
Full physical-volume status remains false even for these planar fixtures.
EBrake's undefined finite electrode and original failing density/AC gates,
Marble AC/SI, and all remaining PI01-S02 conditions remain open.

The original trial independently rotated the copper/contact polygons before
partitioning. The rotated 0.5 mm level failed the existing triangle-shape guard
(`RT0 triangle is reversed, degenerate or ill-shaped`). No guard was weakened
and no sliver was removed. Arbitrarily rotated polygon-overlay compilation
still fails on the default g=0 path. The opt-in precision-grid path now fixes
this bounded example without removing triangles or weakening shape guards;
the legacy rejection remains a negative regression. Arbitrary unresolvable
features are rejected, and general board/contact qualification remains open.
