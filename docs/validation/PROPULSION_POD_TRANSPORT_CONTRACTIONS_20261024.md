<!-- SPDX-License-Identifier: Apache-2.0 -->
# Bounded volume transport contraction reassociation, 24 October 2026

`python/spike_core/propulsion_pod_transport_contractions.py` is an optional
algebra-only helper for `RotatingNavierStokes.operators`. It is not integrated
into the active solver source. The PDE, quadrature, boundary flux, Coriolis
operator, sparse assembly and solver tolerances are unchanged. The owner of
the active CFD snapshot decides whether and when to integrate it.

This record follows [the numerical evidence policy](../NUMERICAL_METHOD_EVIDENCE.md).
The existing volume weak form and its physical assumptions are owned by the
[full-loop independent review](PROPULSION_POD_FULL_LOOP_REVIEW_20261023.md),
including the inertial-flow review and section 30. The change only associates
finite sums differently. No external implementation, quadrature, dataset or
new physical model is imported. Equations and validation below were authored
independently from the existing SPIKE tensor contracts.

## Exact algebra and tensor layout

Input arrays are the existing float64 arrays: N[q,i], G[c,q,i,b],
weight[c,q], U[c,q,a], DU[c,q,a,b], W[c,q,b], with ten P2 nodes and three
velocity components. Here W=U-Omega cross (x-origin). N is dimensionless,
G is 1/m, U and W are m/s, DU is 1/s, weight is m^3, rho is kg/m^3.
The returned transport/Jacobian entries are kg/s and mass entries are m^3.

The original finite sums are retained exactly in real arithmetic:

```
adv_cqj = sum_b W_cqb G_cqjb
T_cij = sum_q N_qi adv_cqj weight_cq
skew_cij = .5*rho*(T_cij-T_cji)
mass_cij = sum_q N_qi N_qj weight_cq
extra_ciajb = .5*rho*sum_q weight_cq *
              [N_qi N_qj DU_cqab - G_cqib N_qj U_cqa].
```

The first two contractions use N.T times weighted batched matrices. For the
first extra term, form only the small quadrature/basis-pair matrix
P[(i,j),q]=N[q,i]N[q,j], multiply it by
D[c,q,(a,b)]=weight[c,q]DU[c,q,a,b], reshape c,i,j,a,b and transpose to
c,i,a,j,b. For the second term, multiply
G[c,(i,b),q] by L[c,q,(j,a)]=weight[c,q]N[q,j]U[c,q,a], reshape c,i,b,j,a
and exchange the component axes to c,i,a,j,b. No component is dropped and
the factor .5*rho is applied exactly once. Floating summation order changes,
so bitwise equality is not asserted.

The helper returns `(skew, mass, extra)`; `extra=None` for jacobian=False.
It does not form or change the Coriolis block. Existing code continues to use
`skew*identity + rho*mass*cross(Omega)` in c,i,a,j,b ordering, adds existing
boundary terms, reshapes to c,30,30 and assembles the same global CSR matrix.

## Budgets and admission

Only existing NumPy float64 arrays are accepted, avoiding hidden full-input
conversion copies. Inputs must have the declared shape, finite values and
positive weights. Density must be a positive finite real scalar. Input arrays
are read without mutation, including noncontiguous/read-only views.

Default cell chunks are 128; callers may select 1..256. Quadrature count is
bounded by 216 and cell count by 40,000, independently of an explicit output
allocation budget at most 224 MiB. The exact output allocation is
`8*cells*(200+900*jacobian)` bytes. Exceeding a budget rejects the call before
output allocation. A full c,q,i,j tensor is never allocated. Finite-value
checks also use cell chunks; there is no global temporary mask for G.
Native BLAS working memory is not a hard allocator guarantee; measured memory
below belongs only to the stated bounded benchmark.

## Executed parity and derivative evidence

Five tests passed in 0.116 seconds using the project virtual environment:

```
.venv/Scripts/python.exe -B -m unittest tests.python.test_propulsion_pod_transport_contractions -v
```

`scripts/check_architecture.py` also passed after source, tests and this
record were added. Whole-solver validation remains the integration owner's
check on the future snapshot that actually invokes the helper.

They compare every skew, mass and c,i,a,j,b extra coefficient against the
original einsum formulas at existing quadrature orders 4, 5 and 6, with
different chunk boundaries. Relative Frobenius-error acceptance is 2e-15,
with per-entry rtol 5e-13 and atol 2e-16 on the synthetic SI fixture. They
also check the existing flattened 30-by-30 Coriolis/Jacobian layout, positive
mass spectrum, skew work, jacobian=False, noncontiguous/read-only inputs and
shape/nonfinite/density/allocation-budget rejection.

The derivative test independently evaluates the weak volume residual

```
R_cia=.5*rho*sum_q weight_cq *
      [N_qi (W dot grad(U_a))_cq - (W dot grad(N_i))_cq U_cqa].
```

Centered nodal-velocity perturbations must match `(skew*I+extra)*delta_u`
with relative norm error below 2e-9. Deliberately omitting extra must cause
more than 10 percent discrepancy for that fixture, preventing a frozen
advecting-velocity implementation from passing. No solver residual tolerance,
physical acceptance gate or test assertion was weakened.

## Measured subset benchmark

The first microprofile was executed before implementing the helper. It used
128, 256 and 512 cells and showed a measurable benefit, supporting the bounded
implementation. Both receipts and the repeatable benchmark script are in
`output/promo-propulsion-pod-20261023/inertial_cfd/`:

- `transport-contractions-microprofile-20261024.json`
- `benchmark_transport_contractions_20261024.py`
- `transport-contractions-benchmark-20261024.json`

Input is the saved v12 stage-02 field file
`air_omega200_hubcleaned_v12_relative/stage-02-actual-fields.npz`, SHA-256
`cf7b9298e0465e85f1fb659169810efa7ddc927a9a0c3b91a5ad963c0c72e0cb`.
The fixture reuses its P1 tetrahedra, P2 connectivity and actual saved velocity,
computing the same basis gradients, physical volume weights and rotating
velocity at order-four quadrature. rho=.001225 kg/m^3,
Omega=(0,200,0) rad/s and origin=(0,.01,0) m are retained. No solver,
factorization, full case, active v17 snapshot or source modification was run.

OPENBLAS_NUM_THREADS, OMP_NUM_THREADS and MKL_NUM_THREADS were set to 1 before
NumPy import. NumPy was 2.4.2. Runtime threadpool introspection was unavailable
because threadpoolctl was not installed; the receipt records the environment
request rather than asserting a measured backend thread count. Three timed
calls per method followed an initial parity/warmup call.

| Cells | Original median, s | Guarded helper median, s | Contraction-only ratio |
| --- | ---: | ---: | ---: |
| 128 | 0.1413713 | 0.0051735 | 27.33 |
| 256 | 0.3042794 | 0.0115447 | 26.36 |
| 512 | 0.6004187 | 0.0191354 | 31.38 |

Maximum relative coefficient error across these samples is 1.280e-16 and
maximum absolute error is 2.033e-20 in the respective coefficient units.
The 512-cell helper's traced peak allocation, including returned outputs,
was 8,270,696 bytes (7.89 MiB). Process peak private commit increased by
38,993,920 bytes (37.19 MiB) over its pre-input baseline, including input
preparation, original reference calls and helper calls. The benchmark body
took 4.478 seconds; it asserted a 60-second wall budget and a 300-MiB extra
peak-commit budget. No end-to-end CFD speedup or full-scale memory result is
inferred from these local contraction measurements.

Measured source SHA-256:
`c5d835d0f3b01bcc9afd33100bd58e0fac2a1ea030a267b38e4908fdb38a461b`.
Test SHA-256:
`b9b79fba9e32c378499269a262525d457eef2a2330d7a36247403687543901c5`.
The receipt also hashes the benchmark script itself.

## Narrow integration seam

On a future owner-approved snapshot, import `volume_transport_contractions`
and replace only the existing adv/skew/mass/extra volume construction with:

```
skew, mass, extra = volume_transport_contractions(
    self.N, self.grad, self.weights, uq, gu, w, rho, jacobian=jacobian)
```

Keep uq/gu/frame construction, block/Coriolis expression, every boundary-flux
term, tensor reshape and sparse assembly exactly as owned by the solver. Run
the existing full Newton derivative and manufactured-solution checks on that
snapshot before a bounded source replay. The supplied helper has not been
installed into the active owner files. Actual convergence, traction recovery,
quadrature/mesh refinement and physical load qualification remain open under
their existing requirements.
