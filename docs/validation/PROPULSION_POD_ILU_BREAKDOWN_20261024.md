<!-- SPDX-License-Identifier: Apache-2.0 -->
# Hard retained-Jacobian ILU diagnosis and explicit stronger candidate

This record extends the independently reviewed block algebra in
`PROPULSION_POD_JACOBIAN_SCHUR_20261024.md`. It concerns one saved linear
system, not a converged nonlinear stage or qualified blade load. All experiments
read the exact v18 stage02 iteration00 matrix/rhs; none reconstructs or changes
the PDE, quadrature, forcing, residual norm or acceptance targets.

## Primary sources and independently authored diagnostics

- Y. Saad, *Iterative Methods for Sparse Linear Systems*, second edition,
  SIAM 2003, [author PDF](https://www-users.cse.umn.edu/~saad/IterMethBook_2ndEd.pdf),
  §6.3.1 proposition 6.6 and §6.3.2 algorithm 6.2 and following double
  orthogonalization discussion, printed pages 160–163. Reviewed for the
  Arnoldi relation, exact-arithmetic breakdown, cancellation and reorthogonalization.
- [SciPy 1.17.0 `gmres`](https://docs.scipy.org/doc/scipy-1.17.0/reference/generated/scipy.sparse.linalg.gmres.html),
  Parameters and Returns: left preconditioning, `pr_norm` inner-iteration
  callbacks, restart-cycle interpretation of `maxiter`, and independent full
  residual convergence. `info>0` is nonconvergence; it does not certify its cause.
- [SciPy 1.17.0 `spilu`](https://docs.scipy.org/doc/scipy-1.17.0/reference/generated/scipy.sparse.linalg.spilu.html),
  Parameters and Notes: drop tolerance/fill control an approximate inverse.
  Increasing retained fill and reducing dropping can improve the approximation;
  neither guarantees stable factors or convergence.
- [SciPy 1.17.0 `SuperLU`](https://docs.scipy.org/doc/scipy-1.17.0/reference/generated/scipy.sparse.linalg.SuperLU.html),
  factorization relation and permutation/factor attribute semantics, reviewed
  to establish `Pr Vhat Pc=L U`. No external implementation source was used.

Diagnostic equations, code and small matrices are original; no external code
or examples were copied. Required knowledgeable human release review remains.
The current reference runtime is NumPy 2.4.2 / SciPy 1.17.0.

## Which residual is being measured

Let `V` be the supplied current velocity matrix, `B` its ILU inverse action,
and `Vhat=Pr^T L U Pc^T` the matrix represented by its factors. On an input `r`
we measure:

```text
x = B r
inverse amplification = ||x||2 / ||r||2
original-matrix approximation defect = ||Vx-r||2 / ||r||2
```

The latter is **not the triangular factor solve backward error**. In particular,
a huge value can result from a poor inverse approximation even if solving the
factor equations is backward stable in a factor-scaled sense. Earlier informal
wording calling this original-V quantity a factor backward error is corrected
here explicitly; the initial JSON names retain the original-V denominator.

For the separate factor audit use `y=Pc^T x`, `s=Pr r`, and compute
`d=L(Uy)-s` without forming a sparse matrix product. Also compute
`b=|L|(|U||y|)+|s|`. We report `||d||2/||s||2`,
`max_i |d_i|/b_i`, and `||d||inf/||b||inf`. The latter two are product-scaled
roundoff indicators, not a condition estimate or exact componentwise backward
error against the original `V`. The larger denominator can mask cancellation
inside `LU`; all original-V and factor residuals must be retained together.
These algebraic quantities retain the supplied system's scaling; they introduce
no physical-unit conversion or new residual norm into the acceptance gate.

For the independent Arnoldi audit, set `T=M A`, `q0=M rhs/||M rhs||`. For each
column compute `w=T qj`, subtract its components along existing basis vectors
sequentially, and measure `||w_remaining||/||T qj||` and `||Q^T Q-I||`.
A second pass repeats the projections. Values near machine epsilon indicate
that normalization is dominated by cancellation. This audit does not duplicate
SciPy's implementation or assert its exact internal stopping branch. A small
preconditioned residual or exact-arithmetic happy-breakdown argument cannot
replace the actual full-system residual in finite precision.

## Decisive probes on the hard system

The original `drop_tol=1e-4, fill_factor=10` velocity ILU has actual-rhs inverse
amplification `5.844230243e8` and original-V relative defect `1.331028911e8`.
Two deterministic random/manufactured probes also have very large defects.
The complete current-Schur preconditioner amplifies the full rhs by `1.0143e20`.
The SciPy initial `pr_norm` trace ends at zero after 14 callbacks while the
true full relative residual remains 3.43045 and `info=40`.

The independent one-pass Arnoldi audit sees operator-vector norms around
`1e21–1e22`, basis orthogonality error 1.41, and a new-vector relative norm
below machine epsilon by the fourth column. Two passes preserve orthogonality
to `7.19e-15` but still reach a relative new-vector norm `1.58e-16`.
Thus severe amplification/cancellation is observed, rather than evidence that
simply increasing the iteration limit will solve this system. These are not
proofs that `V`, the full Jacobian, or its factors are exactly singular.

The separate factor audit distinguishes the approximation from its solve:

| Actual velocity rhs | Original ILU | Stronger ILU |
| --- | ---: | ---: |
| Drop tolerance / fill factor | 1e-4 / 10 | 1e-6 / 20 |
| Native velocity factor entries | 8,806,635 | 17,196,138 |
| Factor-equation relative residual | 9.21786e-8 | 1.42626e-14 |
| Maximum product-scaled component ratio | 2.49551e-16 | 3.02235e-16 |
| Original-V relative approximation defect | 1.33103e8 | 2.09650e-4 |
| Inverse amplification | 5.84423e8 | 0.945671 |
| Minimum absolute U diagonal | 0.00296033 | 0.0537333 |

Both factor solves have roundoff-sized product-scaled indicators; the original
approximate inverse is badly amplifying on the relevant directions. Stronger
ILU improves both the original-matrix approximation and inverse action. The
observed nonzero pivots alone are not stability evidence.

The diagnostic deliberately exported `.L/.U` **only inside its separate 2 GiB
child**, after the native entry check, to inspect these factor equations. This
is not a change to the production storage guard. The audit completed in
24.532 s with peak process commit 1,077,170,176 bytes. The Arnoldi/probe audit
completed in 11.953 s, peak 872,574,976 bytes. Both had 90 s external wall limits.

## Usable same-matrix direction and explicit API

The first stronger-factor experiment retained the same current `C,G,D`, Schur
formula, fixed-forcing owner, zero initial iterate, and full/physical target
0.1. It passed in 155 iterations: true full residual and actual physical defect
both `0.0003802394896`, physical norm-merit slope `-5.1650689052`. Setup was
9.844 s, solve 17.609 s, total 27.890 s; peak commit 1,113,124,864 bytes and
combined native factor entries 22,441,243, below the unchanged 30,000,000 cap.
The full-preconditioner rhs amplification fell from about `1e20` to 205.62.
This was one discriminating parameter change, not a blind parameter sweep.

The candidate helper now exposes explicit optional settings:

```python
owner = JacobianSimpleSchur(
    current_matrix, n_velocity, n_pressure, gauge,
    velocity_drop_tol=1e-6, velocity_fill_factor=20,
)
M = owner.preconditioner
```

Defaults remain `1e-4` and `10`. Accepted explicit ranges are drop tolerance
`[1e-12,1]` and fill factor `[1,20]`, finite real Python numbers excluding bools.
The conservative bounds do not certify every choice. There is no automatic
retry, fallback, cap increase or parameter selection from residual success.
`factor_options` is an immutable mapping of the normalized float values and
the integer factor cap; `factor_options_sha256` hashes canonical sorted compact
ASCII JSON. Result owners must bind this identity together with code and actual
matrix/rhs identities. A parameter hash alone is not a solve provenance hash.

Seven candidate tests plus eight adjacent tests pass (15 tests, 0.078 s), and
the repository architecture check passes. New option tests verify defaults,
explicit-equivalent identity, different-option identity, immutable metadata,
the dense bordered oracle, finite/bool/range rejection and unchanged cap.
Two additional output-only diagnostic tests pass (0.026 s): an independently
assembled permuted dense factor matrix versus `factor.solve`, and a distinct
general-C/G nonconstant-gauge full bordered inverse. Root independently checked
another dense oracle (error `1.25e-15`, full residual `1.26e-16`) as recorded in
`independent-explicit-ilu-options-20261024.json`.

An additional retained-system replay uses this exact public helper API rather
than the experimental factory, binding its source hash and option identity.
Its receipt is `hard-explicit-strong-helper-20261024.json`; the OS supervision
receipt and saved direction are adjacent with `-bounded-` and `-iterate-` names.
This final public-API replay **passed** with exactly the same 155 iterations,
full and physical defect `0.0003802394895987026`, and slope
`-5.1650689051823395`. Setup was 10.656 s, solve 19.500 s, total 30.422 s;
peak process commit was 1,128,996,864 bytes. OS 2 GiB containment was enforced.
Code SHA256 is `497c7721430aa27490b65f015aa65b68e67e4000ee91ac0abf3b6ca47feafaae`;
normalized option SHA256 is
`bea30eb570ca03a129da37d60b5f837b4409e7ac63f5a4b5c02d15126d9c3dd4`.
This accepts only a linear direction. The original physical forcing/descent,
nonlinear backtracking, final convergence, mass/work/traction, mesh, material
and load qualification gates remain necessary. No active PDE or route changed.

## Reproduction and preserved evidence

All following artifacts are under
`output/promo-propulsion-pod-20261023/inertial_cfd/`:

- `diagnose_hard_ilu_20261024.py` and `hard-ilu-diagnostic-20261024.json`:
  original approximation probes, full preconditioner and Arnoldi records.
- `audit_ilu_factor_solves_20261024.py` and
  `hard-ilu-factor-audit-20261024.json`: separate factor-equation evidence.
- `probe_stronger_ilu_20261024.py`, `hard-stronger-ilu-20261024.json`,
  and saved `hard-stronger-ilu-iterate-20261024.npz`: initial accepted direction.
- `test_hard_linear_diagnostics_20261024.py`: independently authored oracles.
- `replay_explicit_strong_helper_20261024.py`: final explicit helper replay.

Each numerical script has a corresponding `*-bounded-20261024.json` receipt
showing OS memory containment. The probes and factor audit use 90 s / 2 GiB;
the two stronger-direction runs use 180 s / 2 GiB. BLAS environment variables
are one before scientific imports, without independently observed backend
thread count. Old failed baseline/current-Schur receipts and iterates remain
unchanged. No performance/physical claim is promoted from an incomplete solve.

Exact retained inputs:

```text
matrix  29458593396a0dc63e6a13abfad6b344bd2363d2c500ce878ae2401733b86176
vectors f4acbb59d8facc30c65885cd8315cf712c68a56f51df8bc52d1a357591194c01
```
