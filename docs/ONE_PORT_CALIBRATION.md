<!-- SPDX-License-Identifier: Apache-2.0 -->
# One-port calibration and uncertainty foundation

SI08-S06 is a bounded offline numerical foundation. It estimates the three
complex error coefficients from exactly three supplied known reflection
standards, corrects a separate DUT measurement, and propagates a supplied joint
real covariance. It does not establish measured accuracy, traceability, general
multiport calibration, fixture-removal covariance, or full SI08 completion.
The result is experimental, with measurement, linearization and production
qualification explicitly false. No worker, GUI or instrument driver is added.

## Reviewed mathematical foundations

- NIST Technical Note 2079, December 2019, section 3.1, equations 3.1--3.3,
  printed page 9: the three-term one-port error box. Reviewed primary PDF:
  <https://nvlpubs.nist.gov/nistpubs/TechnicalNotes/NIST.TN.2079.pdf>.
- JCGM 102:2011, sections 6.1.3 and 6.2.1, equation 3, printed pages 14--15:
  multivariate real sensitivity/covariance propagation, including a complex
  measurement represented by real components. Reviewed primary PDF:
  <https://www.bipm.org/documents/20126/2071204/JCGM_102_2011_E.pdf>.
- JCGM 100:2008, corrected 2010, sections 5.2.2 and 5.2.5, equation 13, printed
  pages 21--23: retain significant correlations and account for shared effects.
  Reviewed primary PDF:
  <https://www.bipm.org/documents/20126/2071204/JCGM_100_2008_E.pdf>.

These references establish the selected model and local propagation law.
SPIKE's elimination, derivative, implementation, examples, oracle and prose are
independently authored; no external implementation source, test corpus or
standard model was examined or adapted. No third-party document is redistributed.
The independently authored preimplementation derivation is
[retained separately](validation/ONE_PORT_CALIBRATION_DERIVATION_20261024.md).
Knowledgeable human numerical review remains required before release.

## Model, units and derivation

All complex reflection ratios and error coefficients are dimensionless at one
fixed common positive real impedance in ohms and a named reference plane.
Frequencies are known positive Hz values, strictly increasing and resolvable
in binary64. This foundation admits 1--16 frequencies and exactly three known
standards on the exact same grid; no interpolation, renormalization, DC model,
frequency/reference uncertainty or automatic standard characterization occurs.
Supplied standards may be nonideal; short/open/load are an example rather than
an assumption of ideal values. Active DUTs are not silently clipped to passivity.

For known standard reflection g and measured ratio m, write
`m = d + t*g/(1-s*g)`, where d is directivity, s is source match and t is
reflection tracking. Set `b=t-d*s`. Rearrangement yields
`d + b*g + s*m*g = m`. For the three standards, solve the complex system
with rows `[1,g_i,m_i*g_i]` for `q=[d,b,s]`; recover `t=b+d*s`.
The DUT correction is `gD=(mD-d)/(b+s*mD)`. These are algebraic corrections of
the supplied data, not a claim that the three-term model captures a real
instrument's drift, switching, compression, leakage or connector repeatability.

Differentiate the original system: `A*dq = dm - dA*q`. Row i has forcing
`(1-s*g_i)*dm_i - (b+s*m_i)*dg_i`. Differentiating the DUT equation gives
`dgD = ((1-s*gD)*dmD - dd - gD*db - mD*gD*ds)/(b+s*mD)`.
For a complex sensitivity h, multiplication in real coordinates has block
`[[Re(h),-Im(h)],[Im(h),Re(h)]]`. This retains noncircular real/imaginary
uncertainty instead of assuming independent equal quadratures.

## Explicit uncertainty contract

`spike/one-port-calibration-request/v1` contains `id`, `port_name`,
`reference_impedance_ohm`, `frequencies_hz`, three `standards`, a `dut`, and
`covariance`. Every standard has distinct `id`, nonempty `provenance`, and
per-frequency RI `reflection` and `measured` arrays. The DUT has distinct `id`,
`provenance` and RI `measured` samples. RI records have exactly `real` and `imag`.
The covariance record has exactly `basis`, `matrix` and `provenance`.

The explicit 14F basis is frequency-major. At each frequency it lists real then
imaginary components for standard0/1/2 reflection, standard0/1/2 measured, then
DUT measured. Exact labels are returned by `input_basis(F)`, e.g.
`f0.standard0.reflection.real` and `f0.dut.measured.imag`. The supplied full
matrix retains cross-standard, measurement/standard, Re/Im and cross-frequency
covariances; entries have units of dimensionless-ratio squared. Zero covariance
is an explicit input assertion, not evidence of exact physical knowledge.
Provenance strings preserve the caller's description; they do not certify it.

`spike/one-port-calibration-result/v1` retains immutable `source_request` and its sorted compact UTF-8 JSON
SHA256 `input_digest`. `derived_network` is a separate single-port sampled
network, with retained names, exact reference and grid. `coefficients` retains
per-frequency d,t,s. `sensitivity` is the real 2F by 14F J, `covariance` is
`J*C*J^T`, and `output_basis` identifies interleaved corrected DUT quadratures.
No standards/measurement correlations are dropped. No noise is estimated from
the exactly determined three-standard fit; a zero residual provides no such
estimate. The full joint covariance is reusable at subsequent explicit domain
boundaries, but no automatic connection to fixture or multiphysics uncertainty
is implemented or implied here.

The propagated covariance is a first-order local approximation. The code does
not infer a distribution, effective degrees of freedom, expanded uncertainty,
coverage probability or confidence ellipse, or certify linearization adequacy
for arbitrary input uncertainties. Unmodeled quantities and nonlinear bias may
dominate real measurements. A small returned covariance does not close these
gaps. The independent deterministic small-perturbation checks verify the local
law on declared synthetic cases only; per-study adequacy remains unqualified.

## Numerical guards and frozen acceptance

Use binary64 complex solves, with no inverse, least-squares fallback,
pseudoinverse, pole clipping or regularization. Reject standard matrix condition
above 1e8; tracking magnitude below 1e-12; scaled inverse or forward denominator
margin below 1e-10; or solve/reconstruction residual above 1e-10. These are
representation/admission screens, not bounds on physical measurement error.
Diagnostics retain condition, backward errors and pole margins for every sample.
Reject an invalid later sample atomically with no successful partial sweep.
Cancellation and callback failures also return no successful capture.

Covariance must be explicitly real, finite, exactly symmetric, nonnegative on
the diagonal, and zero across each zero-variance row. Its positive-variance
submatrix is normalized to correlation coordinates before a PSD eigentest;
this detects tiny invalid blocks alongside large unrelated variances. The
roundoff admission tolerance is `64*eps*n*max(1,max(abs(eigenvalues)))` in those
coordinates. It does not authorize repair: supplied values are unchanged.
Result multiplication is averaged with its transpose only to remove arithmetic
asymmetry; no eigenvalue clipping, diagonalization or inflation is performed.
An unrepresentable covariance or negative output variance fails closed.
Input JSON is stream-budgeted to 8 MiB; F<=16 bounds a 224-square covariance;
result serialization is finite and limited to 16 MiB. No accelerator is needed
for this bounded reference; native/HPC work requires separate profiling.

Independent numerical acceptance is frozen in the preimplementation derivation:
cross-ratio correction, analytic error terms, both real/imaginary derivative
columns, full correlated covariance, small-noise refinement and failure cases.
The executable physical lumped-standard example must recover independent DUT
values within 2e-12 absolute and relative error. No measurement tolerance is
derived from these synthetic numerical tolerances.

## Use and remaining closure

`examples/one_port_calibration/run_calibration.py --output NEW.json` executes
the clearly labeled synthetic example. `--request FILE.json` uses an explicit
request instead. Exclusive output creation preserves previous captures. The
example's open capacitance, short inductance, resistive load, instrument terms
and covariance are illustrative synthetic inputs, not vendor specifications or
calibration certificates. Reopen the capture to inspect source and separate
derived results. The Python API is `calibrate_one_port(request, cancel_check=...)`.

The source-bound stage gate is `scripts/verify_one_port_calibration.py`; stage
status and executed results are in
[the validation record](validation/SI08_CALIBRATION_FOUNDATION_20261024.md).
Next closure requirements include independently characterized standards and
repeatability/drift budgets, measured DUT comparison, nonlinear propagation
adequacy, two-/multiport error models and transmission terms, calibration-to-
fixture covariance composition, and qualified worker/UI workflows. None is
closed by this one-port numerical foundation.
