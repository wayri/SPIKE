<!-- SPDX-License-Identifier: Apache-2.0 -->
# Independent one-port calibration derivation and acceptance record

Date: 24 October 2026. Scope: bounded offline SI08-S06 foundation.
This derivation and the tolerances below were authored by an independent
review agent before reading the implementation. Test execution and subsequent
implementation review are recorded separately below. Experimental only;
knowledgeable human numerical review is required before release.

## Reviewed primary foundations

- Jargon et al., NIST Technical Note 2079, December 2019,
  [DOI 10.6028/NIST.TN.2079](https://nvlpubs.nist.gov/nistpubs/TechnicalNotes/NIST.TN.2079.pdf),
  section 3.1, printed pages 8-9, equations 3.1-3.3, reviewed in full text.
  Equation 3.1 defines the measured ratio; the actual inverse is equation 3.2
  and its determinant convention is equation 3.3. These establish the linear
  three-term one-port error-box model, not calibration of a particular VNA.
- JCGM 102:2011, October 2011,
  [Supplement 2 to the GUM](https://www.bipm.org/documents/20126/2071204/JCGM_102_2011_E.pdf),
  sections 6.1.3 and 6.2.1, printed pages 14-15, formula 3, reviewed in full
  text. Complex quantities may be represented by paired real quantities;
  output covariance follows the real sensitivity matrix and joint input
  covariance. This is a local propagation law, not an exact nonlinear PDF.
- JCGM 100:2008, corrected version 2010,
  [GUM](https://www.bipm.org/documents/20126/2071204/JCGM_100_2008_E.pdf),
  sections 5.2.2 and 5.2.5, printed pages 21-23, reviewed in full text.
  Correlated inputs require covariance terms. An instrument/standard shared
  between observations can induce correlation; zero fit residual is not
  evidence of zero measurement uncertainty.

Only mathematical publications were consulted. The derivation, fixtures,
cross-ratio oracle, perturbation construction and code are original SPIKE
work; no external implementation or example data was inspected or copied.

## Observable, units and assumptions

At each supplied frequency in Hz, recover the dimensionless complex DUT
reflection coefficient at one named port and one common positive real reference
impedance in ohms. Three supplied known-standard reflection coefficients and
their three measured ratios characterize an unchanged linear instrument error
box. The DUT measured ratio uses that same box. No frequency interpolation,
drift correction, renormalization, standards synthesis, noise-floor inference,
multiport correction, causal inference or physical validation is implied.
Frequency and reference impedance are treated as exact metadata; derivatives
with respect to those quantities are outside this declared model. Any upstream
mapping of additional physical uncertainties into the seven complex inputs
needs separate justification; this implementation performs no such mapping.
All complex variables and coefficients below are dimensionless.

The seven complex input quantities per frequency are ordered
`g0,g1,g2,m0,m1,m2,mD`, each real before imaginary. Joint real covariance has
shape `(14F,14F)`; it can encode unequal real/imaginary variances and arbitrary
cross-standard, standard/measurement, and cross-frequency correlations. Output
ordering is `Re(gD0),Im(gD0),Re(gD1),Im(gD1),...` with shape `(2F,2F)`.

## Independent derivation

Let outgoing error-box waves satisfy `b0=d*a0+u*a1` and
`b1=v*a0+s*a1`; a load has `a1=g*b1`. Eliminating the internal waves gives
`m=b0/a0=d+u*v*g/(1-s*g)`. Set `t=u*v`, the reflection tracking product.
Only that product is identifiable, not the individual transmission factors.

For `b=t-d*s`, multiplication by `1-s*g` gives
`m=d+b*g+s*m*g`. Therefore each calibration pair contributes the row
`[1,g_i,m_i*g_i]` to `A`, with unknown `q=(d,b,s)` and right side `m_i`.
Recover `t=b+d*s`. With an admitted invertible calibration map,
`gD=(mD-d)/(b+s*mD)`. No least-squares noise estimate is available from three
complex equations exactly determining three complex coefficients.

For real perturbations of input quantities, differentiate the entire implicit
system: `A*dq=dm-dA*q`. For one standard this row forcing is
`(1-s*g_i)*dm_i-(b+s*m_i)*dg_i`. Let `D=b+s*mD` and `g=gD`. Then

```text
dg = ((1-s*g)*dmD - dd - g*db - g*mD*ds) / D.
```

This accounts for uncertainty in the standards themselves as well as measured
ratios. A complex derivative `h` with respect to a complex input contributes
the real block `[[Re(h),-Im(h)],[Im(h),Re(h)]]`. Stack frequency-local blocks
into `J`. Taking second moments of `dy=J*dx` gives `Cy=J*Cx*J^T`; its
off-diagonal frequency blocks generally remain nonzero even though `J` is
frequency-block diagonal. Circular complex covariance alone would discard
information admitted by this real representation.

## Independent scalar oracle

For any fractional linear map `M(x)=(d+b*x)/(1-s*x)`, direct subtraction gives
`M(x)-M(y)=t*(x-y)/((1-s*x)*(1-s*y))`. In a ratio of four differences,
all error-box factors cancel. Thus

```text
((mD-m0)*(m1-m2))/((mD-m2)*(m1-m0))
  = ((gD-g0)*(g1-g2))/((gD-g2)*(g1-g0)).
N = (mD-m0)*(m1-m2)*(g1-g0)
H = (mD-m2)*(m1-m0)*(g1-g2)
gD = (N*g2-H*g0)/(N-H).
```

This homogeneous expression avoids unnecessary intermediate ratio poles and
uses neither the production linear solve nor its correction coefficients.
Finite differences of this oracle in all `14F` real coordinates supply a
separate sensitivity reference. Three ideal standard values `+1,-1,0` also
admit a scalar check: with `a=mOpen-mLoad`, `c=mShort-mLoad`,
`d=mLoad`, `s=(a+c)/(a-c)`, `t=-2*a*c/(a-c)`.

Synthetic reactive standards use elementary circuit definitions: for the
`exp(+j*omega*time)` phasor convention, a capacitor has admittance `j*omega*C`
and an inductor impedance `j*omega*L`. Defining reflection by
`(Z-Z0)/(Z+Z0)` gives open-capacitance reflection
`(1-j*omega*C*Z0)/(1+j*omega*C*Z0)` and short-inductance reflection
`(j*omega*L-Z0)/(j*omega*L+Z0)`. These identities define supplied synthetic
fixtures, not a manufacturer standard model or validation of a real kit.

## Conditioning, resources and failure meaning

Coincident standards or constant instrument response make calibration
unidentifiable. Small tracking `t`, ill-conditioned `A`, forward poles
`1-s*g_i`, and inverse poles `b+s*mD` require rejection. Small algebraic
residual alone does not ensure a stable inverse. Numerical admission screens
must not regularize, clip or fabricate a result. All sweep frequencies must
succeed atomically, including a failure at the final frequency.

Only 1-16 positive strictly increasing frequencies are admitted, limiting the
largest joint real covariance to 224 by 224. The covariance must be finite,
real, symmetric and positive semidefinite within a documented floating-point
screen. Zero and rank-deficient covariance are meaningful inputs; an
indefinite covariance, even if its negative entries are absolutely small,
is not meaningful. Relative assessment should use covariance scale.

The linear uncertainty result requires local differentiability and perturbations
small compared with distance to singular calibration and correction poles.
Passing a numerical point screen does not prove this assumption for an input
distribution. No coverage factor/probability, traceability certification,
passivity or production qualification follows from covariance propagation.

## Predeclared acceptance tolerances and fixtures

Before implementation inspection or test execution:

- Well-conditioned synthetic recovery, scalar SOL coefficients and standard
  permutations: absolute/relative tolerance `2e-12` on complex values.
- All-coordinate central differences of the independent cross-ratio oracle:
  step `2e-6`, Jacobian absolute tolerance `2e-9`, relative `2e-7`.
- Dense covariance against that independent Jacobian: absolute `2e-16`,
  relative `5e-7`; correlation deletion must measurably change the answer.
- Deterministic nonlinear convergence: choose a dense real factor `L`,
  `Cx=epsilon^2*L*L^T`. The `2n` points `x +/- sqrt(n)*epsilon*L[:,k]`,
  weight `1/(2n)`, reproduce exactly the supplied mean and covariance.
  Compute nonlinear cross-ratio outputs, subtract their empirical mean,
  and compare their covariance with the linear prediction. Symmetry cancels
  odd-order errors; normalized covariance error is `O(epsilon^2)`.
  For epsilon `0.004,0.002,0.001`, each halving must reduce normalized error
  below `0.35` of its previous value and final normalized error below `2e-4`.
  This is local deterministic convergence, not full distribution validation.
- Cases cover zero/rank-one/dense covariance, noncircular real/imaginary
  uncertainty, cross-frequency correlation, ideal and reactive standards,
  permutation invariance, active DUT reflection, singular/near-pole and
  malformed covariance rejection, late-sweep atomic failure, provenance
  retention and absence of input mutation.

## Executed verification and implementation review

No implementation was inspected before completing the derivation and freezing
the acceptance tolerances above. The subsequent review checked the implemented
implicit derivative signs, complex-to-real blocks, frequency-major ordering,
full covariance contraction, conditioning/pole screens and rejection semantics.
The covariance screen scales active variances to a correlation matrix, preserving
small invalid sub-block detection without covariance clipping. The current
point-admission limits are condition number `1e8`, tracking magnitude `1e-12`,
pole margin `1e-10` and solve/reconstruction backward residual `1e-10`.

One source-provenance defect was identified by inspection: the derived network
frequency list originally aliased the retained source frequency list. The
implementation owner copied the derived list, and an independent mutation
regression now verifies separation. No remaining consequential mathematical
defect was found within this bounded review; this is not a human qualification.

Executed on Windows, Python 3.14.2, NumPy 2.4.2:

```text
python -m unittest discover -s build/si08-calibration-staging \
  -p test_one_port_calibration_oracles.py -v
11 tests passed (0.262 seconds reported by unittest).
```

The reviewed source and independently authored test file were staged outside
tracked source during a concurrent packaging freeze. Final-path integration
and required project checks belong to the integrating owner; this command
records the checks actually executed by the independent reviewer.

| Observable | Executed evidence |
| --- | --- |
| Maximum absolute Jacobian discrepancy, all 42 real coordinates | `1.0698206209802663e-10` |
| Nonlinear covariance relative error, epsilon 0.004 | `1.5726800519425674e-4` |
| Nonlinear covariance relative error, epsilon 0.002 | `3.932392730800683e-5` |
| Nonlinear covariance relative error, epsilon 0.001 | `9.83141560191564e-6` |
| Error halving ratios | `0.2500440395326061`, `0.25001103081364523` |

All predeclared tolerances passed unchanged. The convergence shows the expected
quadratic local correction to first-order covariance for this synthetic joint
input family; it does not establish adequate linearization for arbitrary users'
uncertainties. The implementation keeps `measurement_qualified=false`,
`linearization_qualified=false`, and `production_qualified=false`.

Source hashes for the final independent run:

```text
one_port_calibration.py
b3175c244e1fcb4d0b9c9e669d5aba116cf0ba5ecb6e8a05dee332aee0c0977d
test_one_port_calibration_oracles.py (staging import)
34721ad912ac55b07f502ff382d2e86dbd42c68c40714d383cda2bc7a6c0b05b
```

The numerical metrics were measured before the frequency-list-only correction
(module SHA-256 `274ca3ee96f4e7e0c6be1a0a93c9e7fec6f77cbd364a84032a50e475b619e9b7`);
the full oracle suite, including numerical tolerances and the added provenance
test, passed against the final module hash above. Required knowledgeable human
review, physical standards/instrument validation, complete uncertainty budgets,
measurement traceability, distribution/coverage analysis, worker integration
and broader SI08 closure remain open.
