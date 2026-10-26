<!-- SPDX-License-Identifier: Apache-2.0 -->
# Multiport known-standard calibration and joint uncertainty

SI08-S07 extends the offline calibration foundation to 2--4 ports and 1--2
positive frequencies. The estimator combines three supplied reflection
standards per port with a supplied known multiport coupling standard. It
identifies relative transmission gains and corrects all receiver/source DUT
entries, retaining a full joint real covariance. This is a port-separable
error-box model, not arbitrary crosstalk calibration or an instrument driver.
No worker, GUI, installer or release qualification is added.

## Primary mathematics reviewed

- Jargon, Williams and Sanders, *Three-Port Vector-Network-Analyzer
  Calibrations using the NIST Microwave Uncertainty Framework*, 2019 92nd
  ARFTG conference, sections II--III, PDF pages 1--2, figures 1--2:
  [NIST author PDF](https://tsapps.nist.gov/publication/get_pdf.cfm?pub_id=927081).
  Reviewed diagonal error boxes, reflection-product ambiguity, relative
  transmission consistency and measured-wave input requirements. Their
  no-crosstalk model and wave convention motivate the boundary here; SPIKE's
  known-matrix reference-column estimator and derivatives are independently
  derived. This is not an implementation of unknown-thru SOLR or the MUF.
- NIST TN2079, December 2019, section 3.1, equations 3.1--3.3, printed page 9:
  [three-term reflection model](https://nvlpubs.nist.gov/nistpubs/TechnicalNotes/NIST.TN.2079.pdf).
- JCGM 102:2011, sections 6.1.3 and 6.2.1, formula 3, printed pages 14--15:
  [joint real sensitivity/covariance law](https://www.bipm.org/documents/20126/2071204/JCGM_102_2011_E.pdf).

The [independent preimplementation derivation and frozen oracles](validation/MULTIPORT_CALIBRATION_DERIVATION_20261024.md)
record units, gauge, identifiability, analytical sensitivities and acceptance.
The algorithm, fixtures, code, derivation and prose are SPIKE-owned original
work. No external implementation was inspected or adapted. Primary papers
were read for mathematical foundations; they do not qualify this implementation.
Knowledgeable human numerical review remains required before release.

## Governing model and estimator

All waves use a fixed common positive real impedance in ohms. Complex ratios,
error coefficients and sensitivities are dimensionless; covariance has squared
ratio units. Matrices are indexed `[receiver][source]` in explicit named port
order. `measurement_basis=coherent_wave_matrix_ratio` asserts that the supplied
M matrices are formed from consistent measured wave matrices as `B*A^-1`.
This API does not acquire waves or perform switch-term correction. Uncorrected
switched S-parameter tables must not be relabeled as these inputs. Reference
and frequency uncertainty are outside the selected model.

Let D,U,V,W be diagonal directivity, outward gain, source match and inward gain.
Wave elimination gives `M=D+U*S*(I-V*S)^-1*W`. This assumes independent port
error boxes and a common unchanged measurement state. DUT and coupling-standard
networks may themselves have dense reflection, coupling and nonreciprocity.
No passivity or reciprocity is imposed on those supplied networks.

The existing one-port owner solves each port's three known standards, yielding
`d_i`, `v_i`, and `t_i=U_i*W_i`. Reflection calibration alone cannot identify
individual directional gains. For supplied known coupling standard C, form
`K=(I-C*V)^-1*C` and `E=(Mc-D)*diag(1/t)`. Then `E=U*K*U^-1`.
The explicit `gain_reference_port` r fixes the arbitrary common complex gauge
`U_r=1`. Each other port needs a nonzero, well-resolved direct reference-column
path: `U_i=E_ir/K_ir`; set `W_i=t_i/U_i`. This is an explicit star estimator,
not inferred graph connectivity, unknown-thru phase selection or a least-squares
fit. All supplied coupling-standard entries are preserved. Only its reference
measurement column identifies gains; unused measured entries have zero
derivative and serve as redundant consistency diagnostics, not extra fitted
constraints or an inferred noise estimate. Their residual is reported without
assuming a statistical acceptance threshold.

For DUT measurement Md, form `X=U^-1*(Md-D)*W^-1` by diagonal scaling and solve
`(I+X*V)*S=X`. The common gain gauge cancels. A separately retained 2N-port
error-box network exposes the same named exterior/DUT partition for comparison
with supplied-fixture removal; these are representation-compatible values,
not automatic covariance composition with that separate workflow.

## Sensitivities and uncertainty

Differentiate the one-port calibration systems implicitly, including both
known-standard and measured-standard changes. For each complex input direction,
the coupling-standard derivative solves
`(I-C*V)*dK=dC*(I+V*K)+C*dV*K`. Then
`dE=(dMc-diag(dd))*diag(1/t)-E*diag(dt/t)` and
`dU_i=(dE_ir-U_i*dK_ir)/K_ir`, with `dU_r=0`.
Use `dW/W=dt/t-dU/U`. Differentiating the DUT scaling yields
`dX=U^-1*(dMd-diag(dd))*W^-1-diag(dU/U)*X-X*diag(dW/W)`;
the final derivative solves
`(I+X*V)*dS=dX*(I-V*S)-X*dV*S`.
No finite-difference derivative is used in the implementation; the independent
oracle uses finite differences to assess these expressions.

For complex derivative h, real quadrature sensitivity is
`[[Re(h),-Im(h)],[Im(h),Re(h)]]`. The full supplied real input covariance Cx
propagates as `J*Cx*J^T`, retaining cross-port, standard/model/measurement,
Re/Im and cross-frequency correlations. The output contains all complex DUT
entries, including both directions of each transmission. No block independence,
isotropic quadratures, noise floor or fit-residual uncertainty is invented.
`linearization_qualified=false` and `measurement_qualified=false` are retained;
local synthetic convergence does not certify adequacy for arbitrary input
distributions. Coverage probabilities and expanded uncertainty are unsupported.

## Contract, identity and resource limits

`spike/multiport-calibration-request/v1` contains `id`, `port_names`,
`reference_impedance_ohm`, `frequencies_hz`, `measurement_basis`,
`gain_reference_port`, `reflection_standards`, `coupling_standard`, `dut` and
`covariance`, plus `contract`. The three reflection-standard records contain
`id`, `provenance`, and frequency-by-port RI `reflection` and `measured` arrays.
Coupling-standard records contain `id`, `provenance`, known `s_parameters` and
`measured` square samples. DUT records contain `id`, `provenance`, `measured`.
Every complex entry is exactly `{real,imag}`; source IDs must be distinct.

`covariance` has explicit `basis`, real `matrix` and `provenance`. Frequency-major
complex input order is all three known reflection rows, their three measured
rows, then row-major known coupling S, measured coupling M, and measured DUT M.
Each complex input contributes real then imaginary coordinates. `input_basis`
returns exact labels, e.g. `f0.reflection_standards0.reflection.p0.real` and
`f0.dut.measured.p0.p1.imag`. Index labels avoid ambiguous punctuation in port
names; the retained `port_names` supplies their physical identity.
The dimension is `2*F*(6*N+3*N*N)`, at most 288. Output order is frequency-major
receiver/source then real/imag, with dimension `2*F*N*N`, at most 64.

`spike/multiport-calibration-result/v1` retains the independent source snapshot
and canonical compact sorted UTF-8 JSON SHA256, separate derived network,
coefficients and error-box networks, diagnostics, real sensitivity matrix,
output basis, full covariance and explicit experimental/qualification scope.
Source and derived arrays must be independent. Nonempty provenance strings
preserve the caller's assertions; they do not establish certificates or
traceability. No standard characterization or calibration certificate is
manufactured by the example.

Binary64 solves use condition ceiling 1e8 and backward/reconstruction residual
ceiling 1e-10. Reflection guards are inherited unchanged. Reference coupling
paths require `abs(K_ir)>=1e-10*max(1,norm(K))`; measured paths require
`abs(E_ir)>=1e-12*max(1,norm(E))`. Outward/inward gain magnitude ratios must not
exceed 1e8. Feedback/recovery minimum singular value divided by
`max(1,largest singular value)` must be at least 1e-10, also rejecting a
uniformly small operator whose condition number is innocuous. Singular cases fail with
no inverse, pseudoinverse or regularization. Covariance admission reuses the
existing correlation-scaled PSD screen without repair. Only multiplication
roundoff asymmetry is averaged. Requests are stream-budgeted to 8 MiB and
finite serialized results to 16 MiB. Cancellation and a failed later frequency
return no successful partial output.

## Execution and remaining gates

`examples/multiport_calibration/run_calibration.py --output NEW.json` executes
an explicitly synthetic three-port example; `--request REQUEST.json` accepts
an explicit supplied study. Existing output is preserved. Run the source-bound
stage gate `scripts/verify_multiport_calibration.py --output NEW.json --log NEW.log
--capture NEW_CAPTURE.json` with fresh paths. See the
[executed stage record](validation/SI08_MULTIPORT_CALIBRATION_20261024.md).

Remaining SI08 calibration work includes arbitrary crosstalk/error-box topology,
actual wave/switch-term acquisition, independent measured standards and DUT
comparison, repeatability/drift budgets, nonlinear adequacy, general calibration
connectivity and joint calibration/fixture covariance composition. Worker/UI
integration, human numerical review and installed-release qualification remain
separate. This source addition is excluded from the already-staged 0.4.1
installer and inherits none of that candidate's qualification. Full SI08 stays
open, including causality/DC, passive broadband fitting and transient acceptance.
