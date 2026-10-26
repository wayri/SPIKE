<!-- SPDX-License-Identifier: Apache-2.0 -->
# Independent scope review for a nonpositive Newton velocity diagonal

Written by the integration owner before inspecting any proposed variant
implementation. This is a block-algebra argument, not approval of a variant,
an actual-fluid solve or load convergence. Exact retained/reassembled-system
evidence and implementation review must be added separately.

## What positivity does and does not establish

For the existing nonsymmetric bordered Newton system

```
A = [ V  G  0 ]
    [ C  0  g ]
    [ 0 gT  0 ],
```

elimination using invertible V gives the bordered pressure block
`[-C V^-1 G, g; gT, 0]`. Here the actual stabilized upper and lower couplings
need not be transposes. No general SPD conclusion follows from a positive
velocity diagonal; a negative diagonal entry alone also does not prove that V
or A is singular. The current candidate's positive-diagonal check is an
explicit applicability restriction of that approximation. It must not be
reported as a physical residual or load failure, nor silently removed.

Replacing V^-1 inside the pressure approximation by any chosen finite
invertible diagonal inverse D^-1 defines `Q=-C D^-1 G`. If the bordered
approximation H is invertible, and B is the fixed velocity ILU inverse action,
the same application remains well-defined:

```
yu = B ru
[p,lambda] = H^-1 [rp-C yu, rg]
u = yu-B Gp.
```

The factorization proof in the independently reviewed current-Jacobian method
record holds for this general D. It does not require positive entries or
assert symmetry. Conversely, finite nonzero diagonal entries do not prove H
invertible, well conditioned or effective. A different D changes the
preconditioner only; the original A, RHS, physical direction check, actual
pressure-mean residual and nonlinear Armijo test must remain unchanged.

Using a signed current diagonal, absolute values, a row magnitude, or a frozen
viscous diagonal are distinct approximation choices. Algebra alone does not
select one or justify a performance/convergence claim. Any new choice must be
explicit, source/parameter bound and separately tested on the relevant state.
The existing positive-only/default behavior must remain reproducible. An
absolute or row-magnitude choice is not the exact diagonal-elimination inverse
for a negative diagonal V; tests must not demand or claim that false identity.

## Evidence required before integration

The v19 failure matrix was not exported: its observer retained iteration zero,
while the nonpositive diagonal arose after a successfully accepted Newton
step. A subsequent source-bound reassembly from the retained partial iterate
can provide relevant evidence, but must be labeled reassembled, with exact
saved velocity/pressure/density/geometry/scaling and residual correspondence.
It cannot acquire a nonexistent original-matrix hash retroactively. The
partial iterate is not an accepted density stage or load result.

Require independently recomputed true full and applied physical residuals,
negative raw merit slope, gauge consistency, fixed matrix/ILU action, bounded
factor storage, explicit resource containment and source hashes. Approximate
inverse amplification and defect against V differ from factor-equation
product-scaled residuals. A passing linear direction does not imply that its
nonlinear trial, density stage, geometry refinement or propeller load passes.

The primary mathematical foundation is the block-elimination reference
actually reviewed in
[the current-Jacobian method record](PROPULSION_POD_JACOBIAN_SCHUR_20261024.md):
Elman et al., JCP 227 (2008), equations (2)-(12),
DOI [10.1016/j.jcp.2007.09.026](https://doi.org/10.1016/j.jcp.2007.09.026).
The reasoning here follows directly by multiplying the displayed blocks;
no external implementation was copied. This review makes no additional
reference-reading or numerical-execution claim.

## Subsequent implementation review and executed independent oracle

The integration owner inspected helper source SHA256
`e078516b7c886dd32f6146cdf1baf82ba1be69408e6a8f9ef210316190de1f63`.
Its default `positive_current_v1` still rejects nonpositive current diagonal
entries; only explicit `signed_current_nonzero_v1` admits negative entries.
Zero entries, nonfinite data, overflowing reciprocals, unsupported policies,
factor failure and the existing combined storage cap still reject. No absolute
value, clamp or automatic alternative is applied. Current C/G and gauge borders
and the fixed ILU/block application remain unchanged. The full four-key factor
descriptor includes policy; both option hashes therefore differ from the prior
three-key format, deliberately preserving semantic identity rather than
claiming old hash compatibility. Numerical default behavior remains separate.

A separately authored integration-owner 6-by-6 dense oracle, with different
non-transpose C/G, nonconstant gauge and nonzero gauge RHS, passed both positive
and indefinite diagonal cases. Signed-case solution norm error was 5.55e-17
and relative full residual 1.015e-16; the default still rejected that case.
Positive-case relative residual was 1.26e-16. Reproducible script:
`output/promo-propulsion-pod-20261023/inertial_cfd/independent_signed_current_oracle_20261024.py`.
Its source-bound receipt ends `e078516b7c88-f1aeec94d114.json` in that directory
and retains both complete matrices and RHS. This is small block verification,
not field convergence or an inf-sup proof.

The author's separately bounded public-API replays retained unchanged inputs:
the signed reconstructed failed state passed 165 iterations with full/physical
defect 0.0009922057836077769 and negative merit slope; the positive retained
system passed 155 iterations with defect 0.0003802394895987026. Both returned
directions were bitwise equal to their earlier accepted diagnostic directions.
Receipts `public-diagonal-policy-{positive,signed,bounded}-20261024.json` under
the same output tree bind sources, options, input hashes and OS containment.
These checks clear this explicit preconditioner option for a new experimental
continuation only. They do not admit a nonlinear Armijo trial or density stage.
