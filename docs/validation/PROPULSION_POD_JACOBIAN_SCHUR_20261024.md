<!-- SPDX-License-Identifier: Apache-2.0 -->
# Current-Jacobian diagonal-Schur candidate, 24 October 2026

Status: explicit experimental algebraic preconditioner, with no default route,
PDE, quadrature, forcing, tolerance, active-run or material admission changes.
The existing frozen `SimpleSchurStokes` remains unchanged. Implementation:
`python/spike_core/propulsion_pod_jacobian_schur.py`; independent fixtures:
`tests/python/test_propulsion_pod_jacobian_schur.py`.

## Scope and primary foundations actually reviewed

This record follows `CONTRIBUTING.md`, `docs/NUMERICAL_METHOD_EVIDENCE.md` and
the numerical qualification/human review requirements. This Python module is a
bounded sparse-algebra orchestration/reference candidate, not a native kernel
migration or a new production solver route.

1. H. Elman, V. E. Howle, J. Shadid, R. Shuttleworth, R. Tuminaro,
   *A taxonomy and comparison of parallel block multi-level preconditioners
   for the incompressible Navier–Stokes equations*, JCP 227 (2008) 1790–1808,
   [DOI 10.1016/j.jcp.2007.09.026](https://doi.org/10.1016/j.jcp.2007.09.026),
   [author PDF](https://www.cs.umd.edu/~elman/papers/tax.pdf).
   Reviewed equations (2)–(4), §2 equations (5)–(7), §3 equations (9)–(12),
   and §3.1.1, printed pages 1791–1794. These supply the block factorization,
   inexact-Newton full-residual condition, and diagonal pressure-Schur idea.
   The reference's SIMPLE velocity correction uses the diagonal inverse;
   this candidate deliberately uses the velocity ILU solve instead, so it is
   called SIMPLE-type rather than an implementation of that exact algorithm.
   No mass-preserving or convergence guarantee is imported. The reference
   warns that the diagonal approximation can be poor for convection.
2. [SciPy 1.17.0 `spilu` documentation](https://docs.scipy.org/doc/scipy-1.17.0/reference/generated/scipy.sparse.linalg.spilu.html),
   Parameters, Returns and Notes reviewed: real CSC factorization, explicit
   `drop_tol=1e-4`, `fill_factor=10`, approximate solve semantics. The installed
   reference runtime is SciPy 1.17.0 / NumPy 2.4.2.
3. Existing project independent review,
   `PROPULSION_POD_FULL_LOOP_REVIEW_20261023.md` §35, supplies the pinned
   SciPy 1.17.0 native `SuperLU.nnz` storage-counter audit. Its recorded native
   counter bounds exported L/U entries without materializing those copies.
   This work did not inspect or adapt third-party implementation source.

All derivation, code, fixture matrices and oracles below are independently
authored. References establish mathematical provenance; no external code,
examples, meshes or tests were copied. Numerical qualification and required
knowledgeable human review remain separate gates.

## Independent block derivation

The already assembled current system has ordered unknowns velocity `u`,
pressure `p`, and one gauge multiplier `lambda`:

```text
A = [ V  G  0 ]       A [u,p,lambda]^T = [ru,rp,rg]^T.
    [ C  0  g ]
    [ 0 g^T 0 ]
```

`C` is the current lower pressure/velocity coupling and `G` the current upper
velocity/pressure coupling, including any existing stabilized contribution.
They are read separately; `G=C^T` is not assumed. `g` is the actual gauge
functional in both borders and need not be a pressure null vector. The supplied
gauge must exactly match both matrix borders. Other nonzero blocks are rejected
rather than silently discarded.

Exact elimination gives `u=V^-1 ru-V^-1 Gp`, followed by

```text
[ -C V^-1 G  g ] [p     ] = [rp-C V^-1 ru].
[    g^T     0 ] [lambda]   [     rg     ]
```

Let `B` denote the fixed ILU inverse action for this current `V` and
`D=diag(V)>0`. The candidate uses `Q=-C D^-1 G` in the full bordered matrix
`H=[Q,g;g^T,0]`, and applies

```text
yu = B ru
[p,lambda] = H^-1 [rp-C yu, rg]
u = yu-B Gp.
```

This is the inverse action of the approximate block factorization

```text
P = [I  0 0] [B^-1 0 0] [I BG 0]
    [CB I 0] [ 0   Q g] [0  I 0]
    [0  0 1] [ 0  gT 0] [0  0 1].
```

Multiplication gives its velocity block `B^-1`, exact off-diagonal blocks
`G,C`, pressure block `CBG-CD^-1G`, and the original gauge borders. Thus the
pressure equation is generally altered *inside the preconditioner*. The
operator `A` used by Krylov and the accepted original-system residual are
unchanged. For diagonal `V`, exact diagonal ILU has `B=D^-1`; the pressure
perturbation vanishes and the full bordered action is the exact inverse.

Even with positive `D`, `Q` is generally nonsymmetric and not asserted SPD.
Both bordered Schur and velocity factors may fail; no pressure-null-vector
projection, sign change, zero-gauge-rhs assumption or automatic fallback is
permitted. A nonzero `g` alone does not prove invertibility. Convection and
non-normality may make the diagonal approximation ineffective; GMRES must
check the unchanged full system, including its gauge equation.

## Units, conditioning, contracts and resource limits

All entries retain the units and row/unknown scaling of the supplied Jacobian.
`D^-1 G` maps pressure increments into velocity increments; `C D^-1 G` has
the same pressure-to-continuity scaling as the eliminated exact block.
No nondimensionalization or physical parameter adjustment occurs here.

Construction requires real finite sparse data, matching dimension and gauge,
and positive finite current velocity diagonal with finite reciprocal. The
resulting Schur entries and every applied result must be finite. The matrix,
couplings and gauge are copied before constructing fixed factors; later caller
mutations cannot mix a new coupling with old factors. A new Jacobian requires
a new candidate. The API does not claim to solve the PDE or certify a linear
iterate by itself.

The bounded reference admits at most 200,000 velocity unknowns, 5,000 pressure
unknowns and 30,000,000 input stored entries. The pressure dimension limits
the unbordered sparse product to at most 25,000,000 possible entries. Native
factor stored-entry counts are checked after each factor and after combining
them, at a caller-selectable cap no greater than 30,000,000. This is a
conservative post-factor storage gate under the pinned counter audit, **not**
a peak allocation or workspace bound. `.L` and `.U` are not materialized.
Large construction must run inside external wall-time and memory containment;
LU setup itself cannot be interrupted by this helper. Factor failure is an
explicit rejected candidate. No nonlinear/CFD convergence follows from setup.

## Executed verification

Six new tests plus the two adjacent frozen-Schur tests pass (0.034 s on the
initial focused run). New tests cover:

- Independent dense full bordered solve with diagonal velocity, nonsymmetric
  `G != C^T`, nonconstant/non-null-mode gauge and arbitrary nonzero gauge rhs:
  inverse action and full residual agree within `3e-14` relative/absolute.
- Nondiagonal nonsymmetric velocity: the preconditioner alone demonstrably
  fails to solve the full system, while full GMRES reaches independently
  recomputed relative residual below `1e-12`, agreeing with the dense oracle.
- Rebuilding from a changed diagonal changes the action; later caller matrix
  and gauge mutations leave existing snapshots unchanged.
- Nonpositive/subnormal-overflow diagonal, nonfinite/complex/malformed data,
  unsupported pressure/gauge blocks, mismatched/zero gauge, invalid dimensions,
  singular Schur factor, injected backend failure, stored-factor budget and
  malformed applied rhs are rejected.

## Retained-system replay and integration boundary

`output/promo-propulsion-pod-20261023/inertial_cfd/benchmark_jacobian_schur_20261024.py`
replays the saved v10 failed Newton matrix and rhs without reconstructing the
PDE. Each method runs in a fresh bounded child (85 s and 2 GiB, two sequential
children; total nominal wall budget 170 s). The baseline uses the unchanged
frozen Stokes Schur with current velocity ILU, omitting the unused reference
velocity factor. Both use the same existing `refined_gmres`, zero start,
original target and half-target initial forcing. All source/input SHA256
identities, setup/solve times, full residuals and failures are retained.
BLAS thread environment variables are set to one before importing NumPy;
backend thread count is not independently observed.

The first launch attempt failed because the Windows venv redirector tried to
create another process inside a one-process Job. That receipt is preserved as
`jacobian-schur-launch-failure-20261024.json`. The corrected launcher directly
uses the same base interpreter with the venv package directory, retaining
the one-process OS containment; no solver execution occurred on the failed
attempt. Controlled numerical results are recorded in the adjacent baseline,
candidate and bounded-comparison JSON receipts.

The controlled comparison completed in 22.406 s overall, with both OS memory
limits enforced and assignment performed while the child was suspended:

| Same retained v10 system | Frozen baseline | Current-Jacobian candidate |
| --- | ---: | ---: |
| Setup seconds | 2.141 | 2.359 |
| Linear solve seconds | 9.531 | 5.563 |
| GMRES iterations | 386 | 201 |
| Independently recomputed full relative residual | 1.4487292492e-9 | 3.8240420863e-10 |
| Required full relative target | 2.9289380027e-9 | 2.9289380027e-9 |
| Peak process commit, bytes | 843,984,896 | 876,670,976 |

Both used initial forcing `1.4644690013433187e-9`; neither needed a residual
refinement correction. Candidate native factor count is 13,189,978 and bordered
Schur matrix stored count 551,495. The 27,339-square current matrix has
1,510,961 stored entries, `n_velocity=23799`, `n_pressure=3539`; the norm of
`G-C^T` is 8.0767915703, so retaining current `G` is material on this replay.
This single controlled observation supports fewer iterations and less solve
time **on this retained system only**, not a general performance guarantee.

Input SHA256 identities, independently computed in both children:

```text
current matrix  2b88137985bd58583d552533bd8f8836923b4386d79d6a0877c2d98905b7f91e
rhs/iterate NPZ 2602911b95d51cef3c64f3a1ed6b127112654c6c467b7dc6bb7db73475f83c4f
frozen Stokes   3a44544e891e5557a5d08fe6fe8f8e3da40ba7f5bb021e54f1a070922c247ee7
candidate code  8cb32b94d9af70c18ce94d85b2600f7e770d8b4b55629bde2629979d35b758d5
```

The repository architecture check passed. The candidate is not imported by
the active solver; no new framework/dependency or UI route was introduced.

Future integration is an explicit owner choice:
`JacobianSimpleSchur(current_matrix,n_velocity,n_pressure,current_gauge).preconditioner`.
The existing full residual/forcing/physical-direction gates remain mandatory.
The retained v10 matrix is an auxiliary-density stage, not the current v17
air stage. Its timing cannot predict later high-Reynolds-number behavior or
establish physical CFD load qualification. No active run or default was changed.

## Hard retained v18 replay: both candidates rejected

The subsequently retained `air_omega200_hubcleaned_v18_transport/`
`current-linear-systems/stage-02-iteration-00` system is density fraction
0.009, with the same 27,339 unknowns. A second independent-process harness,
`benchmark_hard_jacobian_schur_20261024.py`, reads this saved matrix/rhs and
verifies their identities against the saved evidence. It also verifies that
the live frozen-Schur, residual-refinement and fixed-forcing module hashes
match the saved owner evidence. No PDE reconstruction occurred.

Both methods used the original `solve_fixed_step` (initial forcing 0.05,
full relative target 0.1). The harness additionally called the unchanged
`applied_direction` and independently computed `F=-rhs`,
`Jd=A*delta-[0,g*delta_lambda,0]`, `norm(F+Jd)/norm(F)` and
`F dot Jd / norm(F)`. Thus the auxiliary multiplier was not treated as an
applied physical state increment. Each child again had 85 s / 2 GiB OS
containment, and BLAS environment variables were set before NumPy imports.
The two-child comparison finished in 16.297 s.

| Hard v18 stage02 iteration00 | Frozen baseline | Current-Jacobian candidate |
| --- | ---: | ---: |
| Setup seconds | 4.765 | 4.656 |
| Linear solve seconds | 1.297 | 2.032 |
| Iterations by initial solve / two refinements | 7 / 9 / 4 | 14 / 9 / 7 |
| Full residual by solve / refinements | 1.72898 / 2.47252 / 3.60448 | 3.43045 / 3.49042 / 3.48754 |
| Final actual physical direction defect | 3.6044815548 | 3.4875364289 |
| Physical norm-merit slope | -0.1571378827 | -0.1497389311 |
| Required residual and physical defect | <=0.1 | <=0.1 |
| Both gates accepted | **false** | **false** |
| Peak process commit, bytes | 844,328,960 | 876,044,288 |

Every inner GMRES returned `info=40`; the small iteration counts do not mean
convergence. The negative slopes do not compensate for the failed forcing
defects. Candidate setup admitted positive diagonal minimum 0.5761396371,
14,051,740 native factor entries and 551,495 Schur matrix entries, but those
checks do not establish a useful preconditioner. These results reject the
candidate as a demonstrated remedy for this hard stage. They do not diagnose
the cause of Krylov failure or justify changing tolerances, the PDE, the
factor settings or the candidate's default admission.

Both failures and rejected iterates are retained under
`hard-jacobian-schur-{baseline,candidate}-20261024.json`,
`hard-jacobian-schur-{baseline,candidate}-iterate-20261024.npz`, and
`hard-jacobian-schur-bounded-comparison-20261024.json` in the inertial CFD
output directory. Source identities include:

```text
hard matrix    29458593396a0dc63e6a13abfad6b344bd2363d2c500ce878ae2401733b86176
hard vectors   f4acbb59d8facc30c65885cd8315cf712c68a56f51df8bc52d1a357591194c01
saved evidence 92377c3a45d1fb111ff98e0bab452b587040bab14d20d444545897c4a1ad188f
hard harness   20556af2dbe51ce55972d391ba14d88302c5bd1adddd6d4b96321b7bc27c12ea
forcing owner  7ba3cedaa17b92acea0da5b4da515ec96c3c9c9aac8686c2a3261d96b5f1751e
```

The candidate source remains the same hash as the earlier v10 replay.
Independent algebra review in the full-loop review §37 found no consequential
mathematical defect; that result and the small dense oracles establish the
implemented block algebra, not hard-stage convergence or physical loads.

Subsequent bounded diagnosis and explicit optional factor parameters are
recorded in [the ILU breakdown and stronger-candidate record](PROPULSION_POD_ILU_BREAKDOWN_20261024.md).
The defaults and cap remain unchanged. The stronger explicit choice passes
both gates on this exact hard linear system; nonlinear/physical admission is
still separate. Earlier source hashes and failed results above remain records
of the original-default experiments, not identities for the later extension.

The [explicit signed-diagonal policy](PROPULSION_POD_SIGNED_DIAGONAL_20261024.md)
preserves positive-only default admission and separately admits finite nonzero
signed current entries. It records a source-bound reconstruction of the
unretained v19 failure-state matrix, exact residual correspondence, independent
indefinite/gauge oracles and bounded original-system/physical direction checks.
The new policy is included in option identity, so legacy option hashes must
not be reused for the extended descriptor. Nonlinear trial and load gates
remain separate.
