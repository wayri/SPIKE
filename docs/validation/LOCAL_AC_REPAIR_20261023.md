<!-- SPDX-License-Identifier: Apache-2.0 -->
# Local dielectric AC weak-terminal checks - 23 October 2026

## Bounded claim and cause

`pdn_dielectric_ac.py` retains its experimental finite-domain P1
electroquasistatic model. This repair strengthens result admission, not solver
capacity or physical qualification. No geometry, material, boundary, frequency,
regularization or external field is inferred. Governing equations and solved
fields are unchanged. See [the existing model](../PDN_DIELECTRIC_AC.md) and
[method evidence policy](../NUMERICAL_METHOD_EVIDENCE.md).

The previous residual, field-power and reciprocity checks pooled all unit-drive
columns into a Frobenius norm. Current conservation divided the largest current
imbalance by the largest column's total current. Therefore a strong terminal
could conceal a bad independent weak-terminal experiment. A connected unit cube
with a grounded internal sheet at x=0.5, signal sheets at x=0 and x=1, and a
1e12 coefficient ratio provides an exact two-gap witness. The old code accepted
both an injected 10% error in the weak basis free solution and an injected 10%
error in its electrode currents. Two rejection tests failed before the repair
because no exception was raised; the unmodified analytical solution passed.
These injections test admission failure, not an observed LU factorization bug.

## Source ledger and independent derivation

Reviewed on 23 October 2026: David H. Staelin, *Electromagnetics and
Applications*, MIT course notes, copyright 2011,
[official PDF](https://ocw.mit.edu/courses/6-013-electromagnetics-and-applications-spring-2009/d3be4ea78b036a6362230fb41780cf54_MIT6_013S09_notes.pdf).
Reviewed portions: section 2.1, equation 2.1.21, printed page 25 (integral charge
continuity); section 2.7.2, equations 2.7.13-2.7.27, printed pages 58-60
(harmonic products, complex Maxwell equations and power). This is a limited
equation/method review, not a full-book review or retrospective provenance claim.
The peak-amplitude average product converts to RMS by removing the one-half
factor. No external implementation, mesh, example, prose or dataset was copied.

Independently in SPIKE notation, total RMS current density is
`Jt = gamma E`, where `gamma = sigma I + omega tan(delta) epsilon + j omega epsilon`
has units S/m. With `E = -grad(phi)`, continuity gives
`div(gamma grad(phi)) = 0`. The supplied fixed sheets remove the constant-potential
nullspace. The unchanged affine tetrahedral Galerkin operator is
`K_e = volume B gamma B^T`, in S. Each basis column solves `Kff p_j = b_j`.
For a converged basis matrix P, electrode reactions Y and independently
integrated field form W obey `Y = P^H K P = W`. Current conservation holds for
each basis experiment separately, not just for a pooled numerical scale.

Let `r_j = Kff p_j - b_j`. The added checks are
`max_j norm(r_j)/max(norm(b_j), tiny)`,
`max_j norm((Y-W)[:,j])/max(norm(Y[:,j]), tiny)` and the same column ratio for
`Y-Y^T`. Current imbalance is
`max_j abs(sum_e I[e,j])/max(sum_e abs(I[e,j]), tiny)`.
`tiny` remains the existing positive IEEE float64 normal minimum, not a
physical error allowance. Aggregate Frobenius checks remain included as well.
All four tolerances remain 1e-9; overflow/nonfinite checks, the 1e12 equilibrated
condition gate, passivity gate, cancellation, 128-free-node and all other
resource limits remain unchanged. No eigenvalue clipping or damping is added.
The existing scalar residual/power/reciprocity diagnostics now report the maximum
of aggregate and per-basis relative errors; balance reports the worst basis.
The network solver's separately named normwise backward-error diagnostic is
unchanged. Existing result schemas remain valid.

For the two grounded gaps, each thickness is 0.5 m and area is 1 m2.
Thus `Y = diag(2 gamma_left, 2 gamma_right)` S, with zero transfer terms.
The exact potentials are `max(1-2x,0)` and `max(2x-1,0)` V. These are affine
within each gap, so aligned P1 meshes should reproduce them to roundoff.
Scaling both epsilon and sigma on the right by 1e-12 while retaining loss
tangent preserves the exact voltage solutions and scales only its response.
The 10% defective weak current has pooled relative error approximately 1e-13,
but its own relative error is approximately 0.1 and must fail.

## Executed checks and binding

Windows repository `.venv/Scripts/python.exe`, with `OPENBLAS_NUM_THREADS`,
`OMP_NUM_THREADS` and `MKL_NUM_THREADS` all set to 1:

```
python -m unittest tests.python.test_pdn_dielectric_ac tests.python.test_pdn_dielectric_ac_contract tests.python.test_pdn_dielectric_thermal tests.python.test_pdn_dielectric_thermal_contract tests.python.test_pdn_dielectric_feedback tests.python.test_pdn_dielectric_feedback_contract tests.python.test_pdn_dielectric_thermomechanical -v
python scripts/check_architecture.py
```

45 tests passed, zero skips, unittest time 5.910 s. Architecture check passed.
This includes actual worker/schema tests and unchanged AC/heat/feedback/elastic
coupling checks, plus four new tests: independent two-refinement gap solutions,
weak free-solution rejection, weak field-power rejection and isolated weak
reference-current KCL rejection. No mock response establishes the analytical
acceptance result. Existing malformed-input, cancellation, ill-conditioning,
norm-overflow and work-bound refusals continue to pass.

At refinements n=2 and n=4 the largest relative diagonal-admittance errors were
6.676e-16 and 1.555e-15 respectively, against a preset 2e-12 test tolerance.
The n=4 equilibrated condition was 5.2842, maximum relative free residual
4.305e-16 and maximum power-identity error 1.950e-15. This is an exact affine
refinement witness, not an arbitrary-geometry convergence-rate claim.

SHA-256 of the executed files (raw current bytes):

| File | SHA-256 |
| --- | --- |
| `python/spike_core/pdn_dielectric_ac.py` | `4d7791b945938fb748c65528c6fb7c36823f9a14f9f49e8323958fe4a7ea09bd` |
| `tests/python/test_pdn_dielectric_ac.py` | `d4347f4c7cb1f7b76085f119ad208e8c07ccb655fcf4b080ea9fdb5b8edf76eb` |

The integration owner then genuinely re-executed PI02-S01 through PI02-S04:
16, 9, 10 and 9 tests respectively, zero skips. New source-bound receipts
`docs/validation/parity/PI02-S01-20261023.json` through
`PI02-S04-20261023.json` and their exact execution logs are retained; the
backlog points to these fresh receipts, while old receipts remain historical.
No hash was relabeled without execution. Architecture and backlog checks passed.
The combined AC/EMerge/network/thermal/feedback/elastic regression passed
86 tests, zero skips, in 6.864 s. Full repository/release checks were not run
by this bounded repair. Physical measurement, material dispersion, board-scale
geometry/refinement, full-wave/conductor coupling and knowledgeable human
numerical release review remain open. Per-column tests are not elementwise
relative-error guarantees for arbitrarily small cross-couplings; passivity and
conditioning retain their existing normwise scope. No speedup is claimed.
