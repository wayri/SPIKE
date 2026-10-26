<!-- SPDX-License-Identifier: Apache-2.0 -->
# SI08-S07 multiport known-standard calibration and uncertainty

Date: 24 October 2026. Status: **done for the verified offline numerical stage**.
Full SI08, physical measurement accuracy, per-input nonlinear adequacy and
production/release qualification remain open. This new source addition is
excluded from the already-staged 0.4.1 installer and inherits none of that
candidate's qualification. No service, schema, catalogue, UI or version files
were edited for this stage. Packaging coordination confirmed no active freeze
or overlapping calibration ownership.

## Method and scope

The [method and contract](../MULTIPORT_CALIBRATION.md) record the reviewed NIST
three-port error-box and measured-wave boundary, NIST TN2079 reflection model
and JCGM 102 real covariance law. The
[independent derivation and frozen oracles](MULTIPORT_CALIBRATION_DERIVATION_20261024.md)
were authored before reading the implementation. Original scalar cross-ratio
and simultaneous internal-wave oracles verify the new estimator independently
of its matrix recovery formula. No external implementation was inspected.

The API supports 2--4 explicitly named ports and 1--2 positive frequencies.
Three known reflection standards per port determine directivity, source match
and transmission products. A supplied known multiport coupling standard and
explicit reference port identify relative directional transmission gains.
The resulting port-separable error boxes correct all receiver/source DUT
entries. Common complex gain gauge, port permutations, dense/nonreciprocal
standard/DUT coupling and active DUTs are covered within the selected model.
Arbitrary instrument crosstalk, raw wave acquisition and switch correction are
unsupported. Supplied coherent wave matrix-ratio semantics are a required
caller assertion, not something inferred from uncorrected S-parameter files.

Analytical implicit sensitivities propagate the entire supplied real input
covariance, including port, quadrature, standard/model/measurement and frequency
correlations. Source snapshots and separately derived networks, estimated
error-box networks, coefficients, basis and diagnostics are retained. The
error-box values interoperate with existing supplied-fixture removal, verified
by an executed comparison. Joint calibration/fixture uncertainty composition
is still unimplemented. Redundant measured coupling entries are diagnostic
only; no residual-based noise or statistical acceptance threshold is invented.

## Executed verification

Twenty numerical/contract/workflow tests passed without skips in the
[source-bound receipt](parity/SI08-S07-multiport-calibration-20261024.json).
Its [actual execution log](parity/SI08-S07-multiport-calibration-20261024.log)
and [explicitly synthetic capture](parity/SI08-S07-multiport-calibration-capture-20261024.json)
retain exact source hashes, Python/NumPy versions, complete test inventory,
original standards/measurements and all derived results. Three additional
adversarial evidence-validator tests passed, rejecting changed source,
incomplete execution, promoted qualification, and rebound captures with altered
gains, error boxes, DUT entries, Jacobian or covariance. These validator fixtures
are explicitly synthetic and are not independent physical measurements.

Independent results across two-, three- and four-port two-frequency studies:

| Observable | Worst observed error |
| --- | --- |
| Complex DUT entry versus original independent truth | `6.805e-16` absolute |
| Analytical Jacobian versus all-coordinate independent finite differences | `9.384e-10` absolute |
| Joint covariance versus independent Jacobian propagation | `1.564e-10` relative Frobenius |
| Original measured-wave reconstruction | `6.324e-16` relative |

At deterministic symmetric perturbation scales `2e-4`, `1e-4` and `5e-5`,
nonlinear covariance relative errors were `3.1826510361e-4`,
`7.9550443511e-5` and `1.9886622139e-5`. This fourfold error reduction per
halving passes the frozen local-refinement tolerance; it does not qualify
arbitrary input distributions or uncertainty coverage. Zero/rank-one/dense
covariance, gauge and permutation invariance and late failures are exercised.

Independent review found a consequential all-direction inverse pole: a nearly
zero scaled identity can have a benign condition number and a misleading
reconstruction residual. The implementation now screens absolute/relative
minimum singular values as well as condition. Exact and epsilon=1e-12 near-pole
tests pass without relaxed tolerances. Callback failure, cancellation, invalid
basis/provenance, indefinite covariance, missing reference paths and resource
rejection return no successful partial sweep. Actual example subprocess output
creation and overwrite preservation pass.

Reproduce with `python -B scripts/verify_multiport_calibration.py --output NEW.json
--log NEW.log --capture NEW_CAPTURE.json`. All paths must be fresh and inside
the repository. The backlog's SI08-S07 dispatcher validates current sources,
execution and capture before accepting a done stage.

## Remaining closure and release gates

Full SI08 remains in progress. Next calibration work requires independent
measured standards/DUTs and complete repeatability/drift/noise budgets,
calibration/fixture covariance composition, general connection graphs, actual
wave/switch-term workflows and broader crosstalk models. Qualified worker/UI
integration and per-study nonlinear adequacy remain separate. Causality/DC,
general passive broadband fitting and integrated transient acceptance also
remain open. Knowledgeable human numerical review is required before release;
independent agent review and synthetic tests do not fulfill that human gate.
The existing 0.4.1 installer remains immutable and excludes this module.

## Final integration checks

All 23 new tests passed at final paths: 20 independent numerical/contract/
workflow tests and three adversarial evidence-validator tests. Forty-two
existing one-port, supplied multiport fixture, worker/schema, capture and
native-evidence-validator tests passed in 9.252 seconds. Full backlog
regression passed 15/15 tests with zero skips in 83.990 seconds, including
the new done-stage receipt and existing stale/false-completion controls.
Architecture, all eight changed-document checks and scoped new/existing-file
whitespace checks passed. The reference inventory was regenerated and checked.
The current SI08-S07 source-bound receipt was revalidated after tracking edits.
No full repository suite or installed-release execution is claimed for this
source increment. The prior guarded qualification remains dated to its own
source snapshot and immutable installed candidate.
