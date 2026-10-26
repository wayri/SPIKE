<!-- SPDX-License-Identifier: Apache-2.0 -->
# Explicit signed-diagonal policy: derivation and retained-state evidence

The first investigation below was output-only during the source freeze. After
explicit freeze release, the owned public helper gained a separate signed
policy. The default positive-only admission is preserved. This record concerns
linear directions and does not qualify a nonlinear flow stage or blade load.

## Relevant state and provenance

The v19 stage03 failed after a successful full Newton step from its iteration00.
Both retained iteration00 matrices have positive velocity diagonals. The
failed iteration01 matrix was not retained, so its original hash is unavailable.
The authorized output-only capture reconstructs its state from
`air_omega200_hubcleaned_v19_current_strong/partial-unqualified-fields.npz`,
SHA256 `b74513ad670cf1a34a12889e72612a234483b585c9a0a029208992e8def6cd47`.
This is the last accepted Newton iterate inside a failed density stage, not an
accepted density stage. Fraction is 0.005196152422706632, density is that fraction
times the supplied 1.225 kg/m3, viscosity 1.81e-5 Pa s, rotation 200 rad/s about
Y and origin [0,0.01,0] m. The expected original nonlinear relative residual is
0.015365719444555618, as confirmed by the flow owner and retained run output.

`capture_v19_failed_state_20261024.py` uses an isolated package whose search
path is the v19 source snapshot only. It verifies snapshot hashes against
request/failure start/end maps, exact mesh/field numbering, field density and
request geometry identities. The existing observer seam saves the assembled
matrix, rhs, gauge and velocity count, then raises a dedicated `CaptureComplete`
before any current factor, direction or new Newton trial. Input hashes are
checked again at exit. The existing zero-factor restart adapter prevents an
unnecessary initial Stokes factor. All work is contained in a 600 s / 2 GiB
child, with BLAS environment variables set before NumPy imports.

## Primary foundation and original derivation

Reviewed H. Elman et al., *A taxonomy and comparison of parallel block
multi-level preconditioners for the incompressible Navier–Stokes equations*,
JCP 227 (2008), 1790–1808,
[DOI 10.1016/j.jcp.2007.09.026](https://doi.org/10.1016/j.jcp.2007.09.026),
[author PDF](https://www.cs.umd.edu/~elman/papers/tax.pdf), equations (2)–(12),
§3.1.1 and §3.1.2, printed pages 1791–1795. The block-factor framework permits
different inverse approximations in the Schur and velocity corrections.
The pressure-correction discussion compares diagonal and row-derived choices
and warns of poor convection approximation. This record does not identify its
ILU velocity correction with textbook SIMPLE/SIMPLEC or infer their guarantees.

For the original supplied matrix `A=[V,G,0;C,0,g;0,gT,0]`, exact elimination
gives `[-C V^-1 G,g;gT,0]`. Replacing only that pressure approximation by
`H=[-C D^-1 G,g;gT,0]`, and using a fixed ILU inverse `B` for velocity, defines
the original independently authored block action

```text
y = B ru
[p,lambda] = H^-1 [rp-Cy,rg]
u = y-BGp.
```

Its represented approximate matrix has blocks `B^-1,G,C,g,gT` and pressure
block `CBG-CD^-1G`. This multiplication remains valid for a finite invertible
diagonal D of either sign, provided H itself is invertible. For diagonal V and
exact B, choosing the signed D=V makes the action the exact full inverse even
when V is indefinite. Positive entries are therefore not required for the
block-algebra identity; they are an existing explicit applicability restriction.
This distinction does not authorize weakening the default route.

The first candidate, only if the measured failed-state diagonal is finite and
nonzero, is **signed_current_nonzero_v1**. It preserves the actual signs without
clamping or changing A. Signed diagonal cancellation may still make H singular
or ineffective; no symmetry/SPD claim follows. Absolute diagonal, row magnitude
or frozen viscous values are different approximations and are not silently
substituted. A row magnitude must specify whether it means absolute signed row
sum or sum of absolute entries; the two differ strongly under cancellation.
No experiment may select between these by relabeling the same formula.

`probe_signed_diagonal_20261024.py` is a separate output-only candidate using
the previous explicitly verified ILU settings 1e-6 / 20, unchanged current C/G,
full gauge border, unchanged 30M combined native factor cap, finite inverse
checks and the existing full/physical 0.1 forcing/descent owner. It reports
negative-entry counts, diagonal/row scales, deterministic velocity approximation
probes and full inverse amplification before Krylov. A probe refusal remains
a failure; passing that screen is not a stability certificate. No nonlinearity,
geometry, numerical quadrature, physical unit or residual scaling changes.

## Independent small oracle before large comparison

`test_signed_diagonal_20261024.py` passes its independently assembled dense
oracle (one test, 0.430 s). It uses V=diag(-2,3,-4), G different from C transpose,
g=[2,5] and an arbitrary rhs with nonzero gauge component. The full inverse
and full residual agree within 4e-14; zero/nonfinite/overflowing-reciprocal
diagonals reject. Crucially, the original public candidate's default rejects
this same indefinite fixture. No external source implementation was inspected,
copied or translated. The independent integration-owner algebra/scope review is
`docs/validation/PROPULSION_POD_SCHUR_DIAGONAL_REVIEW_20261024.md`.

Actual reassembly, diagonal measurements and bounded candidate results must
be appended before claiming usefulness. Reconstructed matrix identity cannot
be retroactively equated to unretained original bytes. A passing linear
direction still requires the unchanged nonlinear Armijo and final physical
qualification gates in its owning solver.

## Executed reconstructed-state evidence

The source-bound capture completed in 228.360 s, peak process commit
1,206,853,632 bytes, with 600 s / 2 GiB OS containment enforced. It reproduced
the original failed-state relative residual **exactly**:
`0.015365719444555618`. Absolute scaled residual norm is 0.03144198744134962.
Every recorded input/source hash was unchanged before and after the capture;
the dedicated observer stopped before factorization/direction. The loaded
CFD modules all resolved to the frozen snapshot. The numerical pressure-kernel
preflight is bound separately to the same mesh/surface/distance evidence in
`v19-failed-state-reassembly-20261024/correspondence-verification.json`; no
uniform inf-sup or physical-load qualification is inferred from that preflight.

Exactly one of 23,799 velocity diagonal entries is negative: local index11501,
value `-0.24073468701525627`. None is zero. Minimum absolute diagonal is
0.2407346870, maximum diagonal 476.0578388 and minimum ratio of absolute
diagonal to row L1 norm 0.0198605533. This is a sign restriction at a finite,
non-tiny entry, not an observed reciprocal-overflow or zero-pivot case.
Minimum row L1 norm is 1.1838076893, whereas minimum absolute signed row sum
is `3.381744493e-6`; this distinguishes the row alternatives without running
a speculative variant sweep.

These observations support the explicit signed-current experiment first. It
preserves the actual signed diagonal-elimination approximation and the
successful stronger velocity ILU from the preceding state. The existing
positive-only public helper was independently called on this reassembled
matrix and still rejected it before factors with its original guard message.

The signed experiment passed unchanged full/physical/descent gates:

| Quantity | Measured value |
| --- | ---: |
| GMRES iterations (info=0, no refinement) | 165 |
| Original full relative residual | 0.0009922057836077769 |
| Actual applied physical defect | 0.0009922057836077769 |
| Required full/physical target | 0.1 |
| Raw physical merit slope | -0.03141417951170726 |
| Setup / solve / total seconds | 4.687 / 7.219 / 12.156 |
| Combined native factor entries | 22,401,810 |
| Schur matrix stored entries | 551,495 |
| Peak process commit, bytes | 1,116,893,184 |

Actual velocity-rhs inverse amplification is 3.76978, original-V approximation
defect 0.000482377; deterministic random/manufactured probes give defects
0.000188446 and 0.00000354288. Full preconditioner amplification is 610.274.
These are useful observed inverse actions, not condition-number certificates.
The 180 s / 2 GiB containment and unchanged 30M native cap passed. There is no
claim that signed diagonals work for all later states, and no nonlinear trial
or Armijo evaluation has been run in this output-only experiment.

Identity and receipt locations under the inertial CFD output directory:

```text
v19-failed-state-reassembly-20261024/matrix.npz
  ed53d6dc112ddf9600c95f76a91aa07e77de80bc1c945409448bcaf5ad5d4d19
v19-failed-state-reassembly-20261024/vectors.npz
  e5ba78a9970c32a37ce4160913a62cf427676cae7eb1a6879ceaf481a605e753
v19-failed-state-reassembly-20261024/evidence.json
  027a72b798f4ce0a22cf29529bfc45e955d602e0dc79aea2ca261dba0b0b52a3
probe_signed_diagonal_20261024.py
  5e393f9949e851544d1aee09465cce33cdda8c0d2d2e62bae599ebbfa2f7487f
```

The saved linear direction is `v19-signed-diagonal-iterate-20261024.npz`;
`v19-signed-diagonal-20261024.json` and
`v19-signed-diagonal-bounded-20261024.json` retain the algorithm/parameter,
input/source identities, full histories and OS supervision. All live source
and defaults remained untouched during this experiment. Proposed future
integration requires explicit policy binding and another public-helper replay
after the source freeze is released; this output-only factory is not a route.

## Public helper after source-freeze release

The integration owner authorized this narrow extension after reviewing the
independent block derivation and the reconstructed-state experiment:

```python
JacobianSimpleSchur(
    matrix, n_velocity, n_pressure, gauge,
    velocity_drop_tol=1e-6, velocity_fill_factor=20,
    diagonal_policy='signed_current_nonzero_v1',
)
```

`diagonal_policy` accepts only two exact strings:

- `positive_current_v1` is the default. It retains the original positive
  diagonal guard, inverse arithmetic, factors and numerical behavior.
- `signed_current_nonzero_v1` preserves the signed current entries, admits
  negatives explicitly and rejects zeros. Nonfinite matrix entries and
  nonfinite reciprocals (including overflowing subnormal reciprocals) reject
  under either policy. There is no absolute-value conversion, clipping,
  fallback, automatic retry or relaxation of the 30M combined factor cap.

The policy is included in the immutable `factor_options` mapping and canonical
`factor_options_sha256`. Therefore **even the new default policy hash differs
from the earlier three-key descriptor**, despite unchanged numerical behavior.
Old receipts and source hashes remain valid records of their older descriptor;
callers must not attach their old option hash to the new four-key mapping.
The versioned policy names bind the choice; source and matrix/rhs identities
must also accompany any reported solve.

Seventeen focused/adjacent tests passed in 0.098 s, including the new
indefinite-diagonal full inverse with general C/G, nonconstant gauge and
arbitrary gauge rhs, default rejection of that same matrix, zero/nonfinite/
subnormal reciprocal failures, unknown/nonstring policies, unchanged budget
failure and bitwise positive action parity for default/explicit-positive/
explicit-signed policies. Policy identities differ as required. Repository
architecture check passed. No flow engine/adapter/default route, stage state,
build artifact, version resource or packaged source was edited by this change.

The source SHA256 for this policy extension is
`e078516b7c886dd32f6146cdf1baf82ba1be69408e6a8f9ef210316190de1f63`;
tests SHA256 is
`b2b4f41fbf2ab5aed13d28de28376ceecc182166cffc69e3a064347c46218d79`.
`replay_public_diagonal_policy_20261024.py` performs two fresh bounded
public-helper runs: positive v18 using the default and reconstructed-negative
v19 using explicit signed policy. It checks both original residual gates and
compares returned vectors to preserved previous accepted linear directions.
Each child has 85 s / 2 GiB, a total nominal wall allowance of 170 s, with
source/input hashes checked before and after. Results are retained in the
`public-diagonal-policy-{positive,signed,bounded}-20261024.json` receipts.

Both public-helper replays passed, with all source/input hashes unchanged:

| Public policy / system | Default positive / retained v18 | Explicit signed / reassembled v19 |
| --- | ---: | ---: |
| Iterations | 155 | 165 |
| Full relative residual | 0.0003802394895987026 | 0.0009922057836077769 |
| Actual physical defect | 0.0003802394895987026 | 0.0009922057836077769 |
| Raw physical merit slope | -5.1650689051823395 | -0.03141417951170726 |
| Setup / solve seconds | 4.718 / 7.313 | 5.250 / 8.171 |
| Combined native factor entries | 22,441,243 | 22,401,810 |
| Peak process commit, bytes | 1,128,751,104 | 1,128,554,496 |
| Bitwise equal to previous accepted linear direction | true | true |

Both satisfy the unchanged 0.1 full and physical target. The positive result
is bitwise identical to the earlier three-key-options helper direction, so
the descriptor change did not change its numerical result on this measured
system. The signed result is bitwise identical to the output-only factory
direction. The public default was also called on the negative-diagonal system
and still rejected it before factors. Total two-child elapsed time was
29.890 s; OS containment was enforced for both.

For the explicit 1e-6 / 20 / 30M settings, current four-key option identities:

```text
positive_current_v1      0bfe96c094fa253e28be401096c75955df447585f56a56d013585ecad8b024c7
signed_current_nonzero_v1 c417a55e412b3518613a9008ef1af5306c70996839ca0c8302a6007f0adaf00f
```

The integration owner independently reviewed the final policy implementation
and ran a distinct 6x6 full bordered oracle with general C/G, nonconstant gauge
and nonzero gauge rhs. Positive and signed-indefinite full relative residuals
were 1.26e-16 and 1.01e-16; default rejection of the negative case also passed.
Its receipt is `independent-signed-current-e078516b7c88-f1aeec94d114.json`.
That review and these linear replays do not replace the owning nonlinear
solver's unchanged Armijo or final physical qualification checks.
