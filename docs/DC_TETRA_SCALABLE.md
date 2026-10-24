<!-- SPDX-License-Identifier: Apache-2.0 -->
# Explicit scalable DC development profile

24 October 2026: experimental development; not full PI01-S02 acceptance or
production qualification. Governing equations and tetrahedral field/heat
derivation remain [the RT0 reference](DC_TETRA_RT0.md). Geometry localization
has its own [partition derivation](DC_BOARD_PARTITION.md).

## Admission and numerical invariants

The separate `spike/tetra-dc-rt0-scalable-request/v1` has the same four fields
as the original request. Its initial ceilings are 50,000 retained cells,
50,000 vertices and 64 MiB serialized input. The original contract retains
5,000 cells / 10,000 vertices / 16 MiB. Shared solid-mesh topology, orientation,
overlap, hanging-node, geometric conditioning, physical-volume, workspace and
comparison audits remain mandatory. Limits are ceilings, not guaranteed problem
sizes. Unsupported geometry or exceeded resources fail explicitly.

`spike/dc-board-volume-scalable-model/v1` and
`spike/source-board-volume-scalable-study/v1` select this profile explicitly;
their original counterparts retain original admission. The experimental
compiler can consider up to 1,024 barrel gaps and 250,000 raw source-boundary
vertices, subject to its independent cell, node, geometry and process budgets.
No curve simplification, missing-volume deletion or relaxed physical tolerance
is implied by selecting a profile.

## Independent factor reuse derivation

On the gauge-fixed trace matrix K, diagonal scaling S gives A=S K S and
b=-S f. Solve A y=b, then lambda=S y, retaining the original unscaled physical
flux, field, terminal and Joule witnesses. The exact eliminated hybrid operator
and physical laws are unchanged. Gauges, prescribed
component balance and signed work retain their existing meanings.

In the scalable implementation the same source-free scalar tetrahedral
operator is evaluated as a Gram product rather than subtracting inverse-mass
rank-one terms. For outward face-area rows N_i and volume V, let c_i be the
face centroids. The affine potential with values lambda_i at c_i has
gradient N^T lambda/V by the divergence theorem; its volume mean is
sum(lambda_i)/4. Therefore J=-sigma N^T lambda/V,
q=N J and H=(sigma/V)N N^T. The independently audited barycentric gradients
give N_i=-3V grad(b_i). Subtracting a common trace before the gradient sum
reduces cancellation while preserving the exact gauge invariance. Heat is
V|J|^2/sigma and fields are constant within a source-free RT0 tetrahedron.
Independent retained cubature, weak laws and signed face integrals remain
mandatory. The original bounded profile keeps its inverse-mass implementation.

The inverse/projected implementation rejected an independently constructed
six-tetrahedron 1 by 0.73 by 0.001 m slab for lost symmetry; its scaled
asymmetry was 6.14e-14 against the unchanged 2.84e-14 screen. The Gram form
passes the known uniform field, face traces, signed currents and heat without
loosening that screen. See [the independent oracle record](DC_TETRA_SCALING_ORACLES.md).

For a positive eigenpair A v=mu v, A^-1 v=mu^-1 v. Thus the largest-magnitude
eigenpair of the inverse locates the eigenvalue nearest zero without thousands
of unshifted smallest-algebraic iterations. One sparse LU supplies inverse
actions and the final linear solve; A is never inverted explicitly. The largest
eigenvalue uses direct Lanczos matrix-vector products. The residuals
r=A v-mu v are recomputed. The existing 1e12 spectral condition screen uses
(mu_max+||r_max||)/(mu_min-||r_min||), requires a positive denominator and finite
values, and fails on eigen-iteration nonconvergence. This is a numerical
spectral estimate, not proof that every extremal eigenvalue was located or a
rigorous forward-error bound.

Nearest-zero eigenvalues alone can miss a negative mode. Symmetric minimum-degree
ordering and diagonal-only preferred pivots are therefore used, with independent
checks for equal row/column permutations, strictly positive finite U diagonals
and U approximately equal to D L^T. In exact arithmetic A=L D L^T has positive
quadratic form because L is nonsingular and D positive. The executed checks
are floating-point positivity/transpose screens; they do not claim exact
inertia certification. An indefinite matrix must not be accepted merely because
its nearest-zero and largest eigenvalues are positive.

Up to three residual corrections y <- y+LU^-1(b-Ay) reuse the factor. Final
per-component face/cell current and heat/work gates remain 1e-9. A linear residual
alone never qualifies a physical field. Component reductions gather each item
once and apply `math.fsum`, preserving weak independently driven islands while
avoiding repeated scans of every cell for every disconnected component.

Reviewed primary API documentation on 24 October 2026: SciPy 1.17.0
[`eigsh`](https://docs.scipy.org/doc/scipy-1.17.0/reference/generated/scipy.sparse.linalg.eigsh.html),
parameters `sigma`, `OPinv`, `which`, `tol`, `maxiter`, and normal-mode notes;
[`splu`](https://docs.scipy.org/doc/scipy-1.17.0/reference/generated/scipy.sparse.linalg.splu.html),
CSC input, ordering, pivot and solve API; and the official
[SuperLU FAQ](https://portal.nersc.gov/project/sparse/superlu/faq.html),
"Symmetric or diagonally dominant problems", including no off-diagonal pivoting,
approximate U=D L^T relation and symmetric-mode controls. No external source,
example or fixture was copied or translated. Algebra and tests are independently
authored. Executed dependency versions and numerical results belong in the dated
validation record, rather than inferred from documentation version alone.

## Resource enforcement and retained outcomes

Sparse input is capped at 200,000 rows / 800,000 entries and retained LU at
16 million entries. The fill check happens after factorization and cannot bound
its peak allocation. Actual board experiments therefore use the existing
`run_adapter_process` supervisor with 4,096 MiB process memory, at most 600 s,
512 MiB output files and 1 MiB streams. This is an isolated offline reference,
not a public worker route. Windows venv launchers spawn another interpreter;
the supervisor enters the base interpreter directly with the same venv package
path, preserving its one-process job ownership and memory limit.

`scripts/benchmark_board_volume_scaling.py` retains exact selected-model hashes,
per-target geometry/field reports, counts, timings and OS memory diagnostics.
Failed, timed-out or resource-terminated cases cannot be refinement successes.
At least three successfully solved levels with observable-specific unchanged
acceptance thresholds are needed for board convergence; a profile selection,
single solve or unexcited-volume result is not convergence evidence.

For the new explicit full-pad unit-current transfer ladder, the frozen
development stability test uses three solved levels with target size halved
at each step and increasing actual cell counts. Both successive changes must
be <=1% for transfer resistance and integrated heat and <=2% for physical-volume
p95/p99 current-density observables. This criterion was recorded before reading
the finer real-board results. `verify_board_volume_refinement.py` replays source
coverage and retained fields, verifies unchanged native/model/method identity,
and binds the supervised executions. Passing is numerical refinement stability
for that selected transfer under supplied assumptions; it is not an a posteriori
continuum error bound, hardware validation, original point-study acceptance or
full PI01-S02 completion. Original study identities and gates remain unchanged.
