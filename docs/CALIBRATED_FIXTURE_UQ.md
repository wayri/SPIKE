<!-- SPDX-License-Identifier: Apache-2.0 -->
# Joint calibration and coupled-fixture uncertainty

This closes implementation point SI08-I04 within the admitted calibration and
fixture contracts, independently of SI08's measurement and release gates.
The original derivation and frozen acceptance are in
[the independent record](validation/CALIBRATED_FIXTURE_UQ_DERIVATION_20261025.md).
Reviewed primary foundations are Marks/Williams, *A General Waveguide Circuit
Theory*, JResNIST 97, 533 (1992), sections 3.4 and 5
([original paper](https://nistdigitalarchives.contentdm.oclc.org/digital/api/collection/p16009coll6/id/74796/download)),
and JCGM 102:2011 sections 6.1.3/6.2.1 formula 3
([primary guide](https://www.bipm.org/documents/20126/2071204/JCGM_102_2011_E.pdf)).
They define the selected wave and local covariance conventions. Derivation,
implementation and synthetic fixtures are independently authored; no external
implementation or measured data was copied. Human numerical release review
remains separate.

## Composition and governing derivative

`compose_calibrated_fixture` first runs the unchanged known-standard calibration
owner, then the unchanged coupled-fixture removal owner. The calibrated network
is the exterior physical fixture measurement, not the final board/DUT. The
fixture can have dense reflection and coupling, arbitrary named storage order,
and explicit complete exterior/interior maps. The existing calibration domain
is 2--4 ports and 1--2 positive frequencies, with common known real impedance.
All S parameters and sensitivities are dimensionless; covariance is in squared
dimensionless quadratures. Frequency and impedance uncertainty remain outside
the selected model. Existing coherence, calibration topology and numerical
admission limitations are retained.

For fixture blocks Fee,Fei,Fie,Fii and calibrated exterior M, solve
`Fei*X*Fie=M-Fee`, then `(I+X*Fii)*D=X`. Differentiate without inverses:

```text
Fei*dX*Fie = dM-dFee-dFei*X*Fie-Fei*X*dFie
(I+X*Fii)*dD = dX*(I-Fii*D)-X*dFii*D
```

Realification retains both quadratures of each complex sensitivity. Let Jc be
the existing calibration Jacobian, Jm the fixture-removal derivative with
respect to calibrated M, and Jf its derivative with respect to the physical
fixture. The complete chain Jacobian is `[Jm*Jc, Jf]`. Use **one** supplied joint
covariance C and return `J*C*J^T`, including its calibration/fixture cross-blocks.
Summing two independent covariance estimates is not equivalent. The nested
calibration covariance must equal C's leading block exactly; otherwise reject.
Its separately reported propagated covariance is retained for inspection and
is not added again. Zero and correlated cancellation cases remain meaningful.

## Contract and resources

`spike/calibrated-fixture-uq-request/v1` has exactly `contract`, `calibration`,
`fixture`, `external_ports`, `dut_ports` and `covariance`. `calibration` is the
existing full multiport calibration request; `fixture` is the existing sampled
2N-port network record. Exterior order must match calibrated port order and
both partitions must cover the fixture exactly once. `covariance` contains
`basis`, `matrix` and a nonempty caller provenance description.

`input_basis(calibration,fixture)` concatenates the calibration coordinate list
with row-major fixture quadratures, frequency-major in the fixture's stored
order: `fixture.f0.p0.p1.real`, etc. The total is
`2*F*(6*N+7*N*N)`, at most 544 coordinates. The output has `2*F*N*N` coordinates
in final DUT order. Joint covariance is finite, exactly symmetric and PSD under
the unchanged correlation-scaled numerical screen; no independence, clipping,
inflation or traceability is inferred. The 8 MiB serialized request and 16 MiB
result budgets remain hard limits: a maximal full-precision dense covariance
may exceed admission even when its dimensions fit. Use an explicitly supported
compact numeric representation, not silent matrix truncation or changed limits.

`spike/calibrated-fixture-uq-result/v1` retains canonical source digest/snapshot,
calibration and fixture results, independently owned final `derived_network`,
complete `sensitivity`, output basis and final covariance. Qualification flags
remain false. Existing transmission/condition/backward-residual guards are
retained. Additional canonical recovery/feedback minimum-singular-value screens
reject scaled-identity poles; no inverse, regularization or partial successful
sweep is returned. Cancellation is correlated through the existing owners.

## Verification and use

The independent oracle solves internal waves simultaneously and recovers
`D*A=Z`, rather than using the production reduced expression. It checks all
joint coordinates through the 544-coordinate boundary, dense/cross-frequency
covariance, correlation cancellation, storage/DUT permutations, nonlinear local
refinement, late failures and pole cases at frozen tolerances. These are
synthetic numerical checks, not measured adequacy or uncertainty coverage.

Run `examples/calibrated_fixture_uq/run_study.py --output NEW.json` for the
explicitly synthetic example, or supply `--request FILE.json`. The existing
output is preserved. `scripts/verify_calibrated_fixture_uq.py --output NEW.json
--log NEW.log --capture NEW_CAPTURE.json` retains source-bound execution and a
capture. The authoritative finite checklist is
[SI08 closure v1](si08-closure-checklist-v1.json); external E01/E02 and release
R01/R02 remain distinct. No current installer, worker or native UI is promoted.
