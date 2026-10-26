<!-- SPDX-License-Identifier: Apache-2.0 -->
# Independent SI08-S07 calibration derivation and oracle

Prepared 2026-10-24 before inspecting the new multiport implementation.
This independently authored derivation, synthetic data and test oracle use no
external implementation. It is a bounded mathematical verification plan, not
physical instrument qualification. Knowledgeable human review remains required
before release.

## Primary foundations actually reviewed

- Jargon, Williams and Sanders, *Three-Port Vector-Network-Analyzer Calibrations
  Using the NIST Microwave Uncertainty Framework*, NIST publication 927081,
  sections II-III, PDF pages 1-2:
  https://tsapps.nist.gov/publication/get_pdf.cfm?pub_id=927081 . The reviewed
  material motivates independent port error boxes, a no-crosstalk assumption,
  transmission-product ambiguity, relative transmission adjustment, and the use
  of coherent wave measurements. The present known arbitrary coupling-standard
  construction is independently derived below; it is not the paper's SOLR method.
- NIST TN2079, December 2019, section 3.1, equations (3.2)-(3.3), PDF page 16:
  https://doi.org/10.6028/NIST.TN.2079 . The scalar inverse is a bilinear map
  with directivity, source match and transmission-product terms.
- JCGM 102:2011, October 2011, sections 6.1.3 and 6.2.1, equation (3), PDF
  pages 22-23: https://www.bipm.org/documents/20126/2071204/JCGM_102_2011_E.pdf .
  A complex model can be expressed in real coordinates; the first-order output
  covariance is the real Jacobian sandwich of the full input covariance.

## Independent wave derivation

Let external incident/reflected waves be a0,b0 and internal DUT incident/reflected
waves be a,b. Every error box is independent of other ports:

    b0 = D a0 + U b; a = W a0 + V b; b = S a.

D,U,V,W are diagonal. Waves use one known positive real reference impedance;
S,D,U,V,W and all supplied ratios are dimensionless. Frequencies are positive
Hz, impedance is ohms. Measurements must already be coherent matrix ratios
B0 A0^-1, not a matrix of unrelated scalar receiver ratios. Eliminating a,b
gives M = D + U S (I-V S)^-1 W. Finite linear equations apply to active and
nonreciprocal networks as well; passivity is not assumed or inferred.

For a scalar standard g, m = d+t*g/(1-v*g), t=u*w. Three distinct known
standards determine the scalar Mobius transform. With q=(d,h,v), h=t-d*v,
the equations are [1,g,m*g]q=m; implicit differentiation gives
A*dq = dm-dA*q and dt=dh+v*dd+d*dv. Coalescent standards, negligible tracking,
and singular standard feedback are nonidentifiable or unusable.

For the known coupling standard C, define K by (I-C V)K=C. Then
(Mc-D)diag(1/t)=U K U^-1. Choosing u_r=1 yields u_i=E_ir/K_ir, w_i=t_i/u_i.
Every i != r requires a nonzero direct effective K_ir and nonzero measured gain.
No graph completion or unknown-thru reciprocity inference is made. Multiplying
all u by a nonzero complex scalar and dividing all w by it has no effect on M
or recovered S. Redundant Mc entries need not be consistent with the selected
calibration equations under noisy data; their residual is diagnostic, not a
noise estimator or an overdetermined fit.

For the DUT, X=U^-1(Md-D)W^-1 obeys (I+X V)S=X. Differentiation yields

    (I-C V)dK = dC(I+V K)+C dV K
    dE = (dMc-diag(dd))diag(1/t)-E diag(dt/t)
    du_i = (dE_ir-u_i*dK_ir)/K_ir; du_r=0
    dw/w = dt/t-du/u
    dX = U^-1(dMd-diag(dd))W^-1-diag(du/u)X-X diag(dw/w)
    (I+X V)dS = dX(I-V S)-X dV S.

These equations fix multiplication order; diagonal terms do not generally
commute with a coupled S. Real/imaginary coordinates are interleaved for every
complex entry. Frequency blocks are independent for the deterministic map,
but a supplied joint covariance can connect any inputs across frequencies.
Thus Sigma_out=J Sigma_in J^T retains cross-frequency and cross-port terms.
Reference impedance and grid values are treated as known, not uncertain inputs.

## Independent computational oracle

The test oracle does not call production coefficient or derivative helpers.
It obtains scalar coefficients by expanding cross-ratio preservation between
the three known and measured standards, without solving production's 3x3 fit.
The cross-ratio forward map is (n1*g+n0)/(h1*g+h0), giving d=n0/h0,
v=-h1/h0, and t=n1/h0+d*v.

It solves simultaneous internal wave equations [I,-V;-C,I][a;b]=[diag(t);0]
for a provisional unit-outward-gain instrument. The observed-to-provisional
response ratio in column r determines relative u. For the DUT it reconstructs
the wave matrices b=diag(1/u)(Md-D) and a=diag(w)+V*b, and solves S*a=b
as a right solve. Forward synthetic measurements independently solve the same
2N simultaneous wave equations with prescribed true error boxes and DUTs.
This differs from production's left-inverse DUT recovery and similarity solve.

## Acceptance tolerances frozen before implementation inspection

- 2, 3 and 4 ports, one and two frequencies; dense complex reflected,
  nonreciprocal and active DUTs: recovered S and identified coefficients agree
  with synthetic truth and independent oracle at rtol=atol=2e-11.
- All real input coordinates: central finite differences of the independent
  oracle, step 2e-6, agree with analytic sensitivity at rtol=3e-6, atol=3e-8.
- Dense positive definite covariance: independent finite-difference sandwich
  agrees at rtol=5e-6, atol=2e-14, including nonzero off-frequency terms.
- Gauge and consistent named-port permutation preserve recovered S at 2e-11;
  covariance under consistent reindexing agrees at rtol=5e-6, atol=2e-14.
- Deterministic symmetric perturbation sets at scales 2e-4, 1e-4, 5e-5:
  centered nonlinear covariance error relative to J Sigma J^T must decrease
  by at least a factor 2.5 per halving and end below 2e-5. This checks local
  first-order refinement for these synthetic samples only, not probability
  coverage or every supplied covariance.
- Missing effective reference-column paths, collapsed scalar standards,
  zero tracking, singular standard feedback, singular DUT recovery, and
  later-frequency failures must raise a structured error without input mutation
  or a partial successful result. Singular cases do not have accuracy tolerances.

Conditioning must be screened at each fit, feedback and inverse solve, including
scale loss not revealed by a condition number alone. Residuals measure algebraic
backward error, not physical validity. No extrapolation, crosstalk calibration,
raw-wave inversion, unknown-thru method, standard-material characterization,
distribution inference, confidence region or release qualification is claimed.

## Executed verification

Executed `python -m unittest tests.python.test_multiport_calibration_oracles -v`:
12 tests passed on 2026-10-24 in 2.805 seconds. Tolerances above were unchanged.
The first nine-test run identified an exact all-direction DUT inverse pole
that the original condition-only screen accepted. With Md=diag(d-t/v), the
recovery operator is roundoff times identity: its condition number can be small
while the recovered DUT is meaningless. Production was repaired to require
the smallest singular value divided by max(1,largest singular value) to be
at least 1e-10, in addition to condition <=1e8. The unchanged exact-pole test
and added epsilon=1e-12 scaled-identity/condition-1.5 near-pole tests now pass.
This screen is appropriate to the canonical I +/- P operators: ||P|| is at
most 1+||I +/- P||, so scaling by max(1,||I +/- P||) bounds operand scale
within a factor two. It is a declared numerical gate, not a noise threshold.

For the two-frequency fixtures the measured errors were:

| Ports | Max absolute S error | Max absolute Jacobian difference | Relative covariance Frobenius difference | Max reconstruction residual |
| --- | --- | --- | --- | --- |
| 2 | 6.805e-16 | 9.384e-10 | 1.564e-10 | 6.324e-16 |
| 3 | 2.559e-16 | 6.139e-10 | 9.760e-11 | 5.709e-16 |
| 4 | 2.831e-16 | 3.561e-10 | 8.166e-11 | 5.266e-16 |

The deterministic symmetric perturbation covariance relative errors at scales
2e-4, 1e-4 and 5e-5 were respectively 3.1826510361e-4, 7.9550443511e-5,
and 1.9886622139e-5. The approximately fourfold refinement supports the local
first-order expansion on this fixture. These are 2*180 symmetric synthetic
points, not an inferred experimental probability distribution or measured
coverage validation.

Other executed checks retain exact zero and rank-one covariance, reorder dense
covariance under a three-port permutation, change the gain-reference choice,
rescale the unobservable common complex gain, reject collapsed scalar fits,
reject missing coupling paths and zero measured gains, preserve source ownership,
and keep redundant coupling measurements as a nonzero diagnostic with zero
calibration sensitivity. No partial result is returned on last-frequency poles.

Reviewed local source snapshots (SHA-256):

- `python/spike_core/multiport_calibration.py`:
  `3ecc00321c4151950d96f6fdfd8bd94390afafd4f3b85beded75c14d310c98e1`
- `python/spike_core/one_port_calibration.py`:
  `e9f2ec28eebe53e61a77c2945248837a5808374ef83a57f8bb5ab183978b2e74`
- `tests/python/test_multiport_calibration_oracles.py`:
  `34a5f3a89284e9c3361228daa448664c6ac8998f3b8f91b5d4fedfeb10fc19ed`

These hashes identify the executed review snapshot, not future revisions.
Only the independent oracle suite was run by this reviewer; full repository,
integration, packaging and human release review belong to their separate gates.
