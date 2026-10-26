<!-- SPDX-License-Identifier: Apache-2.0 -->
# Independent calibrated-fixture joint uncertainty derivation

Date: 2026-10-25. The reviewer authored this derivation and fixed the acceptance
tolerances before inspecting the new composition implementation. Scope is a
finite, offline, supplied linear-network calculation, with N=2..4 ports and
one or two positive-frequency samples. Physical fixture characterization,
measurement validation, nonlinear adequacy for each study and knowledgeable
human numerical review before release remain open.

## Sources and assumptions

Primary sources reviewed directly: Marks and Williams, *A General Waveguide
Circuit Theory*, J. Res. NIST 97 (1992), section 3.4, equation (61), and the
real-reference specialization of equation (63),
[original article](https://nistdigitalarchives.contentdm.oclc.org/digital/api/collection/p16009coll6/id/74796/download);
JCGM 102:2011, sections 6.1.3 and 6.2.1, formula (3),
[official October 2011 edition](https://www.bipm.org/documents/20126/2071204/JCGM_102_2011_E.pdf);
Jargon, Williams and Sanders, *Three-Port Vector-Network-Analyzer Calibrations
Using the NIST Microwave Uncertainty Framework*, sections I and II,
[NIST article](https://tsapps.nist.gov/publication/get_pdf.cfm?pub_id=927081).
These establish linear scattering, real-coordinate propagation and correlated
calibration uncertainty respectively; they do not validate SPIKE's composition.
No external implementation or data was examined or incorporated.

Every port shares a supplied positive real reference resistance (ohms), the
frequency grid is exact (Hz), and S entries, their real coordinates, derivatives
and covariance are dimensionless. Wave amplitudes use square-root-watt units.
Port names identify reference planes. The instrument model is the existing
diagonal error-box coherent-wave calibration; the physical fixture is a
separate fully coupled supplied 2N-port network. It may be active or
nonreciprocal. No unknown fixture is estimated from standards.

## Independent simultaneous-wave construction

Write exterior incidence as U=I, exterior reflection as B, incidence at the DUT
as A and outgoing DUT waves as Z. The fixture equations are

```text
B = Fee U + Fei Z
A = Fie U + Fii Z
Z = D A.
```

Synthetic observations solve the complete 3N system for (B,A,Z), with block
rows `[I,0,-Fei]`, `[0,I,-Fii]`, `[0,-D,I]` and forcing `(Fee,Fie,0)`.
Instrument observations are then synthesized with the independent existing
SI08-S07 simultaneous-wave fixture. Calibration is recovered with its
three-point cross-ratio oracle and gain-ratio construction, not production
calibration calls. For known calibrated B, the independent recovery oracle
solves the complete two-equation system

```text
[ Fei    0 ] [ Z ] = [ B - Fee ]
[ -Fii   I ] [ A ]   [ Fie     ],
```

then determines D from `D A=Z` using a transposed solve. This never calls
production fixture removal or evaluates its reduced recovery expression.
Arbitrary storage permutations are resolved by names before assembly.

## Differential and full joint covariance

An independent differentiation of the constitutive equations gives
`dB=dFee+dFei Z+Fei dZ`,
`dA=dFie+dFii Z+Fii dZ` and `dZ=dD A+D dA`.
Thus `dD A=dZ-D dA`. This is a separate way to verify every tangent column
without assuming commuting matrices or conjugate right solves.

For comparison with a reduced implementation, define X by `Fei X Fie=B-Fee`.
Then `(I+X Fii)D=X`; product differentiation yields

```text
Fei dX Fie = dB-dFee-dFei X Fie-Fei X dFie
(I+X Fii)dD = dX(I-Fii D)-X dFii D.
```

Let c be all existing calibration real coordinates, f all fixture real
coordinates, and Jc the calibrated-B sensitivity. The full chain sensitivity is
`J=[J_B Jc, J_f]`. All complex entries expand to adjacent real and imaginary
coordinates; holomorphic multiplication becomes the real block `[Re,-Im;Im,Re]`.
There is no conjugation in the network equations. A supplied joint real
covariance C propagates exactly once as `J C J^T`. In particular its off-diagonal
calibration/fixture blocks contribute both cross terms. The nested calibration
covariance must equal the leading C block exactly; it is retained for the
intermediate result, not added again at the final stage. Cross-frequency and
cross-quadrature correlations are retained even though nominal solves are local.

## Conditioning and frozen acceptance

Inheritance of calibration and removal conditioning screens is necessary.
Additionally reject canonical feedback `I-Fii D` and recovery `I+X Fii` if
their smallest singular value is below 1e-10: a scaled identity may have
condition number one while approaching an absolute pole. This protects local
linearization from these exact all-direction cases; no bound on real-world
measurement accuracy follows from it. No regularization or clipping is allowed.

Frozen before new implementation inspection:

- Synthetic known truth and independent recovery: atol=rtol=2e-12.
- All joint real-coordinate central differences: step=2e-6, atol=3e-8,
  rtol=3e-6. Dense covariance against independent finite differences:
  atol=2e-14, rtol=5e-6.
- Port permutation: nominal tolerance above; Jacobian/covariance tolerances
  above. Zero covariance must remain zero.
- Symmetric finite perturbation covariance refinement: noise scales
  2e-4, 1e-4, 5e-5; relative error falls by at least 2.5 per halving and
  final relative error <2e-5. This is local algebraic Taylor evidence only.
- Correlated cancellation: a rank-one common measurement/fixture perturbation
  keeping the true DUT fixed yields covariance norm <1e-20, while deleting
  cross blocks leaves norm >1e-10.
- Invalid leading-block mismatch, poles, malformed maps and late sample
  failure reject atomically and preserve the caller's request.

The tests reuse SPIKE-owned encoding and calibration-oracle helpers after
reviewing their cross-ratio and simultaneous-wave equations. Fixture numbers,
recovery assembly, composition tests and this prose are independently authored.
Executed measurements and source hashes are appended after the checks run;
this initial record does not claim any executed verification.

## Executed independent verification

After freezing the preceding derivation and tolerances, the reviewer inspected
`calibrated_fixture_uq.py` and ran
`python -B -m unittest tests.python.test_calibrated_fixture_uq_oracles -v`.
Final run: nine tests passed, zero skips, 6.621 seconds. Cases include all
2/3/4-port and one/two-frequency nominal truths, full real Jacobians for
(N,F)=(2,1),(2,2),(3,2),(4,2), joint correlations, common-error cancellation,
external calibration-port permutation, fixture storage permutation, DUT-map
permutation, strict leading covariance agreement, late cancellation, late
sample failure, immutable source/digest and both absolute poles.

Measured maximum absolute errors and relative Frobenius covariance errors:

| Ports/samples | Truth error | Jacobian error | Covariance relative error |
| --- | --- | --- | --- |
| 2/1 | 4.85e-16 | 1.164e-9 | 1.666e-10 |
| 2/2 | 4.85e-16 | 1.164e-9 | 1.430e-10 |
| 3/2 | 4.58e-16 | 7.012e-10 | 9.662e-11 |
| 4/2 | 3.87e-16 | 4.397e-10 | 1.178e-10 |

The symmetric nonlinear covariance relative errors were
`[9.8317526190e-5, 2.4577004448e-5, 6.1441026375e-6]`, approximately fourfold
improvement per noise halving at the predeclared scales. These finite symmetric
points have exactly the supplied input covariance; they do not represent a
measured probability distribution or qualify arbitrary uncertainty magnitudes.

The largest full-precision dense covariance initially exceeded the inherited
8 MiB JSON cap. The independently generated positive-definite covariance was
rounded at 1e-15 absolute precision to make a bounded synthetic input; all
existing PSD and numerical tolerances remained unchanged. The final 544-column
test passes within the original cap. This is a fixture representation change,
not a relaxation of numerical or resource acceptance.

To isolate the absolute feedback gate from earlier reconstruction rejection,
the pole fixture uses exactly representable identity calibration (standards
1,-1,0; off-diagonal coupling 0.5), `epsilon=2^-40`, fixture transmission
`2^-20 I`, Fii=I and exterior measured response `(1-epsilon)I`. Recovery gives
D=(1-epsilon)I, hence feedback is epsilon I with condition number one. A
separate unit-transmission case with measured `(-1+epsilon)I` has recovery
epsilon I. Both reject with `CALIBRATED_FIXTURE_UQ_REPRESENTATION_LIMIT`.

Source SHA-256 reviewed and exercised:

- `python/spike_core/solvers/signal_integrity/networks/calibrated_fixture_uq.py`:
  `73515e68f68cb4ad60f584b088fe0240bc545bba6b74bc5d79998bcf909172ca`.
- `tests/python/test_calibrated_fixture_uq_oracles.py`:
  `9a76558176a7ec7d6515ef7e575ec3fa0650101fe9d114ebfb93fe795a17a59d`.

Review found no unresolved algebraic mismatch at these sources. An initial
resource-allocation concern was retracted after confirming that the delegated
calibration basis already bounds ports and sample count before label expansion;
the owner made those checks explicit at the composition boundary as well.
This is independent AI-authored synthetic evidence, not the required
knowledgeable human numerical release review. The parent integration owner
retains responsibility for adjacent regressions and project-wide checks.
