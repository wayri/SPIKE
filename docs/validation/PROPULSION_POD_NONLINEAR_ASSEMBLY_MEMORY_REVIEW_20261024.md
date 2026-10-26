<!-- SPDX-License-Identifier: Apache-2.0 -->
# Independent review: bounded element tangent assembly

Authored by the integration owner before implementation. The actual-domain
linear-limit probe reached the hard 2 GiB process bound while NumPy's optimized
tangent contraction attempted a 65.3 MiB intermediate. This is an allocation
failure, not a constitutive mismatch. Exact evidence remains in
`output/promo-propulsion-pod-20261023/real_motor/actual-domain-linear-limit-v2-20261024/`.
No nonlinear actual-domain case completed. Increasing the memory cap or
discarding the reference preconditioner is not proposed here.

The governing energy, residual and tangent are unchanged from the independently
derived [nonlinear P2 method](PROPULSION_POD_NONLINEAR_P2_20261023.md), including
its reviewed magnetic-energy foundations. For element e and local indices i,j,

```
Ke[i,j] = sum_q sum_ab w[e,q] C[e,q,i,a] D[e,q,a,b] C[e,q,j,b].
```

The index e is not summed by this contraction. Partitioning its range into
disjoint contiguous batches and writing each corresponding output slice
therefore computes precisely the same real-arithmetic local matrices.
Scatter the complete output into the existing COO rows/columns and convert
to CSR in the same order. Retain binary64, quadrature points/weights, all
material evaluations/range guards, boundary treatment, residual, energy,
source hashes and solver tolerances. Ke units remain A m²/Wb. Batching is a
storage strategy, not a new constitutive or integration approximation.

In finite precision an optimizer can choose another contraction order for a
different batch size. Do not promise bitwise identity. Verify local entries
against an independently authored scalar sum on nonconstant SPD tensor data,
including PM/replaced regions, and compare full residual/tangent/energy and
solved reference behavior using unchanged predeclared tolerances. Include a
partial last batch and batches of one/all elements. Test absence of any
full-element intermediate on a synthetic allocation/shape fixture, separately
from any true OS peak-memory experiment. Explicit scratch accounting must
include output, sparse conversion and still-live fields; an einsum path alone
does not establish whole-process resource admission.

Primary API reference independently read 2026-10-24: [NumPy einsum manual](https://numpy.org/doc/stable/reference/generated/numpy.einsum.html),
served v2.5, parameters `out` and `optimize` and explicit-output index semantics.
The installed runtime version must be recorded in executed evidence; the
served documentation version is not asserted to be the installed version.
[DefElement degree-two triangle](https://defelement.org/elements/examples/triangle-lagrange-equispaced-2.html)
was independently read for the six-node scalar polynomial basis. No external
implementation, code, example or test data was copied or translated.

The implementation owner must first identify persistent versus scratch
allocations and provide a bounded proposal. Only after review, focused checks
and source freezing may one new actual-domain attempt run at the same 180 s /
2 GiB / BLAS1 containment and unchanged physics/acceptance. A memory improvement
does not imply real-material torque, temporal accuracy, full-air loads or GUI
qualification. Human numerical review remains required before release.

## Implementation review and focused evidence

The owner reviewed the private batch-size rule and local-tangent helper, the
single replaced assembly call and all three new fixtures. The rule caps batches
at 1024 elements and a modeled 8 MiB scratch allowance, accounting for four
curl-shaped intermediates and one local matrix. At Q=4,16,36,256 it selects
1024,1024,594,85 elements. The full output and native workspace are explicitly
excluded from that scratch claim. Each optimized contraction writes a contiguous
slice of the original element ordering; the existing COO/CSR construction and
all returned field arrays remain unchanged.

The independent scalar-index SPD tensor oracle uses compensated sums, and the
batch1/all/partial tests compare local and full mixed anisotropic-PM/supplied-BH
assemblies. Instrumented high/low quadrature cases check actual operand/output
element extents. Thirty-eight nonlinear P2/motor/modal/direct-port checks and
twelve adjacent geometry/energy/table checks pass; architecture passes. The
runtime is NumPy 2.4.2 / SciPy 1.17. Exact source and test identities and installed
contraction paths are in
`output/promo-propulsion-pod-20261023/real_motor/nonlinear-p2-tangent-batching-checks-20261024.json`.
Reviewed P2 source SHA256 is
`6a6b97d4f9b4e6a9cb063d31044f71ad8091918e6aab103163c6c52fb0d305e1`.

This evidence admits the bounded storage change, not a whole-process memory
claim. One fresh source-bound actual-domain linear-limit probe is authorized
with the unchanged 180 s / 2 GiB / BLAS1, 120 s prepare and 45 s evaluation
bounds and original two cases/tolerances, conditional on at least 4 GiB physical
and 8 GiB commit headroom. Any failure is retained and stops that experiment;
there is no silent increase of a resource or numerical tolerance.

## Actual-domain linear-limit probe: completed

The single versioned batched attempt passed both original current cases at the
same angle, with all input/source identities unchanged and no late unbound
modules. Cold preparation took 24.931 s, the two evaluations 2.124 and 2.094 s,
and the full child 29.991 s wall / 29.109 s CPU. Peak commit was 2,078,949,376
bytes under the unchanged 2,147,483,648-byte cap. The remaining 68,534,272 bytes
are a narrow margin, not admission for multi-iteration nonlinear laws or direct
controller-loop caches.

Each linear-limit case used one CG/Newton correction and passed the original
field residual, flux, torque and energy comparisons. Maximum differences from
the fresh linear reference were 1.18482e-15 Wb-turn flux, 2.37366e-13 Nm torque
and 1.36957e-12 J coenergy. Exact per-case gates, input hashes, independent
saved-value recomputation and OS evidence are in
`output/promo-propulsion-pod-20261023/real_motor/actual-domain-linear-limit-v3-batched-20261024/`.
The preceding unbatched resource failure remains preserved. This is actual
geometry under the unchanged illustrative linear law (`bh_curves={}`), not
H070 qualification, actual nonlinear torque, load convergence or a real pod
coupled run.
