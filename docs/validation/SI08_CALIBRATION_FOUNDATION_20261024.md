<!-- SPDX-License-Identifier: Apache-2.0 -->
# SI08-S06 one-port calibration and uncertainty foundation

Date: 24 October 2026. Status: **done for the bounded offline numerical stage**.
Full SI08 and physical/measurement/linearization/production qualification remain
open. The already-staged 0.4.1 installer uses an earlier frozen source baseline:
this new calibration code is **not included in that installed candidate** and
inherits none of its qualification. No service, schema, catalogue, UI or version
files were edited for this stage.

## Method and independent evidence

The [method and contract](../ONE_PORT_CALIBRATION.md) records the reviewed
NIST TN2079 section 3.1 error model and JCGM 100/102 joint covariance law,
units, assumptions, explicit source identities, numerical guards and remaining
qualification boundaries. An independent reviewer authored the
[derivation and frozen acceptance](ONE_PORT_CALIBRATION_DERIVATION_20261024.md)
before reading the implementation, then supplied a separate cross-ratio oracle,
scalar SOL coefficient check, real-coordinate finite differences and nonlinear
deterministic covariance refinement. No external implementation was inspected.

`one_port_calibration.py` estimates three complex error terms from exactly
three supplied known-standard reflection measurements. Standards can be
nonideal, such as explicitly supplied open capacitance, short inductance and
resistive-load reflections. A separate one-port DUT network retains its named
reference, grid and immutable source snapshot/digest. Analytic implicit
sensitivities include uncertainty in both the calibration system matrix and
right-hand side. The full supplied joint real covariance retains Re/Im,
cross-standard, standard/measurement and cross-frequency correlations.
No residual-based noise estimate or distribution/coverage claim is made.

## Executed checks

- Nineteen numerical, contract and actual example-subprocess checks passed
  without skips after integration into the final owning packages.
- Three additional evidence-validator adversarial checks passed: altered
  sources, execution inventory, artifact identity, numerical capture and
  unsupported qualification cannot mark the stage done.
- Independent recovery of ideal/reactive standards and active DUTs passed
  at frozen 2e-12 absolute/relative tolerance; all six standard permutations
  retain the corresponding reordered covariance and sensitivities.
- Maximum absolute discrepancy in the independent 42-coordinate Jacobian
  check was `1.0698206209802663e-10`, within the predeclared tolerances.
- Deterministic covariance relative errors at perturbation scales
  0.004, 0.002 and 0.001 were `1.5726800519425674e-4`,
  `3.932392730800683e-5` and `9.83141560191564e-6`; error halving ratios
  `0.2500440395326061` and `0.25001103081364523` demonstrate local quadratic
  convergence for this synthetic family. Per-input linearization remains
  unqualified, including for distributions wider than the verified local case.
- Tests admit zero/rank-deficient covariance without inflation, reject tiny
  indefinite blocks alongside large variances, singular/near-pole calibration,
  invalid later samples, incorrect identity/basis/provenance, nonfinite values,
  cancellation/callback failure and streamed oversized requests. The maximum
  16-frequency/224-input-coordinate resource boundary is exercised.

Independent review found a frequency-list alias between the separate derived
network and retained source. A copied derived grid fixed it; the added mutation
regression and the full oracle suite passed. No numerical tolerance was relaxed.

The [source-bound receipt](parity/SI08-S06-calibration-20261024.json),
[execution log](parity/SI08-S06-calibration-20261024.log) and
[synthetic source/result capture](parity/SI08-S06-calibration-capture-20261024.json)
retain exact final source hashes, test names/count, runtime versions and actual
example output. Reproduce with `python -B scripts/verify_one_port_calibration.py
--output NEW.json --log NEW.log --capture NEW_CAPTURE.json`; paths must be fresh
and inside the repository. The backlog validates this receipt before accepting
the done status. Earlier ignored staging receipts remain historical.

## Coordination and remaining work

Implementation, independent derivation and initial tests stayed in ignored
staging during the other chat's installer freeze. The packaging owner opened a
short integration window before its final full-suite source snapshot. This
stage adds source-only offline capabilities and preserves the installed
candidate's frozen scope. Required architecture, documentation, backlog and
affected existing network checks are recorded below after execution.

Next SI08 requirements remain two-/multiport calibration and transmission error
terms, characterized standards and repeatability/drift/noise budgets, independent
measured-DUT comparisons, nonlinear propagation adequacy, calibration/fixture
covariance composition, qualified worker/UI workflows, causality/DC policy,
general passive causal fitting and integrated transient acceptance. Knowledgeable
human numerical review remains required before release. No full family closes
because this one-port numerical foundation passed.

## Final integration checks

The full backlog regression passed 15/15 tests with zero skips in 87.088
seconds, including current stage coverage, stale/false completion rejection
and owned-pad regeneration. Twenty-seven existing two-/multiport numerical,
worker/schema, workflow and native-evidence-validator regressions passed.
Architecture checking passed after the packaging owner restored its canonical
resource mappings. Documentation validation passed for all eight edited method/
status/contract records; reference inventory regeneration/check and scoped
new/existing-file whitespace checks passed. The final SI08-S06 receipt was
revalidated against current sources. The subsequent full source qualification
run belongs to the other chat; no unexecuted full-suite or installed-candidate
qualification is claimed here.
