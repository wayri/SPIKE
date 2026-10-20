<!-- SPDX-License-Identifier: Apache-2.0 -->
# Tetra Stokes gauge and preconditioner independent review

Date: 21 October 2026. Scope: read-only consequential numerical implementation
review of `cfd_tetra_stokes.py` pressure multipliers, scaling, block
preconditioning and inverse stopping rules. No production source or owner tests
were edited. **No consequential defect found in the reviewed changes.** This is
supporting mathematical verification, not physical validation, a rigorous
condition-number certificate or knowledgeable human release review.

## Source-bound reproducible evidence

Original review script: `build/cfd-stokes-independent-review-20261021/probe.py`.
Executed JSON: `build/cfd-stokes-independent-review-20261021/result.json`.

```text
.venv-emerge3/Scripts/python.exe build/cfd-stokes-independent-review-20261021/probe.py
```

- Reviewed solver SHA-256:
  `fa6762881b27ae37037d61fa71bc9db74863b3381cbb4610e5a1e03ccea08bcf`.
- Probe SHA-256:
  `4a746be2449ebfc8abb307fc8aa64bf4aa071d36614f04d51d19108e3dd0e655`.
- Executed runtime: Python 3.11.9, NumPy 2.2.6, SciPy 1.17.1.

The governing method and primary-source provenance remain in
[the Stokes method record](CFD_TETRA_STOKES_20261021.md), especially its
boundary elimination, scaling and primary-method sections. This review used
project implementation/fixtures and independently assembled comparison algebra;
it did not inspect, copy or adapt external solver implementation code.

## Gauge and continuity analysis

The physical closed-component system augments the usual saddle equations by
`V*lambda` in the mass rows and `V.T*p=0`. Summing the original mass equations
over a component leaves only its prescribed boundary flux. Compatible flux
therefore forces `lambda=0`; no pressure penalty or local mass row deletion is
introduced by this formulation.

Under `u=Su*x` and `p=Sp*y`, the correct normalized gauge column is
`Sp*V/||Sp*V||`, with its transpose as the last row. The implementation matches
that congruence. The returned componentwise reference-pressure shift changes
only the constant pressure gauge. Independent original momentum and cell-mass
checks remain after the shift; the multiplier is not used as a substitute for
conservation.

The test constructs two disconnected 48-tetra boxes, with second box shifted
2 m in x. It perturbs interior vertex 13 by `(0.08,-0.03,0.06)` m in the first
and `(-0.05,0.07,-0.04)` m in the second. Cell-volume ratio is
1.6315789473684204. Boundary velocity is zero and body load is independent
NumPy RNG seed 481 normal samples times `1e-4 N/m^3`; viscosity is `1 Pa s`.
The comparison independently deletes one pressure/mass row per component,
fixes that pressure to zero and solves the resulting saddle system directly.
It does not reuse the new multiplier construction.

| Check | Executed value |
| --- | ---: |
| Relative velocity difference from independent gauge | 3.194e-15 |
| Relative pressure difference | 1.134e-14 |
| Maximum absolute raw volume-mean pressure (Pa) | 2.118e-22 |
| Maximum absolute scaled gauge multiplier | 1.470e-22 |
| Maximum original cell flux imbalance (m^3/s) | 2.126e-22 |
| Scaled saddle relative residual | 7.789e-16 |

The probe asserts relative field differences below `1e-12` and absolute flux
below `1e-18 m^3/s` for this fixed SI fixture. These are review checks, not new
production residual thresholds.

## SPD block and inverse checks

The preconditioner approximates the inverse of the block diagonal operator
`diag(Su*Kff*Su, Sp^2*V/mu, I_gauge)`. All vector components share the same
scalar broken-Laplacian operator and full-face Dirichlet mask, so the interleaved
scalar factor can be applied independently to all three columns. Positive
pressure masses and unit gauge entries make the other blocks SPD. This block
acts only inside MINRES; it adds nothing to the saddle matrix or physical PDE.
The scalar sparse LU application approximates an SPD inverse; it is not claimed
to be a Cholesky factorization or exactly symmetric in floating-point arithmetic.

For the fixture, the scalar velocity minimum eigenvalue is 0.1308543434 and
the smallest pressure diagonal is 0.4624781303. Explicitly constructing the
preconditioner action gives inverse-block infinity-norm defect `2.647e-15`
and relative symmetry defect `2.588e-16` (both asserted below `1e-12`).
The scalar factors store 1860 nonzeros.

The probe forces the iterative branch by reducing only its private direct-size
selector in test scope. With an independent seed-947 RHS, and amplitudes
`1`, `1e-100`, `1e100`, independently recomputed RHS-relative residuals are
at most `2.978e-16`; relative differences from a direct saddle solve are at
most `5.785e-16`. The probe requires the unchanged `1e-13` actual-inverse
residual and comparison error below `1e-10`.

Negative controls also execute:

- Forged MINRES `info=0` with a zero correction rejects with actual residual 1,
  rather than trusting the library success flag.
- A reduced test-only iteration budget rejects instead of accepting a partial
  inverse.
- A reduced test-only sparse-factor budget rejects.
- Cancellation raised from the iteration callback propagates.

## Limits and integration responsibility

This probe is a small, deliberately nonuniform disconnected algebraic check.
It does not replace the owner's larger-grid continuum convergence, runtime,
physical energy or Reynolds checks, nor the root integration suite. LU factor
storage is checked after factorization, not a hard peak-memory guarantee.
Cancellation is cooperative. `onenormest` remains a lower-bound estimate, not
a rigorous upper bound on conditioning; no stronger claim is made. Sampled SPD
and symmetry checks do not establish bounds for every admitted mesh. Extreme
physical-unit arithmetic can still reject conservatively on representability.
No accuracy, Reynolds, runtime, factor, residual or mesh-resource production
gate was altered by the review.
