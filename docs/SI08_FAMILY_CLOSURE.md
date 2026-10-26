<!-- SPDX-License-Identifier: Apache-2.0 -->

# SI08 full-family closure campaign


## Frozen closure v1: 25 October 2026

The authoritative [machine-checked checklist](si08-closure-checklist-v1.json)
contains exactly eight implementation points, two external validation gates
and two release gates. Each has an owner role, prerequisites, concrete closure
steps and acceptance/evidence. `scripts/check_si08_closure.py` pins the scope
hash and rejects unsupported verified claims; the main backlog invokes it.
The [execution target map](SI08_IMPLEMENTATION_EXECUTION_TARGETS_20261025.md)
specifies each remaining deliverable, its integration boundary and closure evidence.
A stage count cannot close a point or the family. Changed scope requires an
explicit versioned change and reopened acceptance, rather than an endless
sequence of replacement milestones.

| Point | Finite implementation deliverable | Current status |
| --- | --- | --- |
| I01 | Integrated named interoperability, pairing, polarity and source/export cases | **Verified** offline, [current receipt](validation/parity/SI08-I01-interoperability-r3-20261025.json); worker/native completion remains I07 |
| I02 | Causality/DC/resampling policy with independent causal/noncausal and refinement witnesses | **Verified** bounded policy, [current receipt](validation/parity/SI08-I02-policy-20261025.json); original source causality remains unknown |
| I03 | Public known-standard calibration, explicit connected paths and captured setup/replay | Planned; S06/S07 offline foundations are partial evidence |
| I04 | Joint calibration/fixture sensitivity and full covariance, including their correlations | **Verified**, [current receipt](validation/parity/SI08-I04-joint-uq-r2-20261025.json) |
| I05 | Automatic stable conjugate-pole fitting and broadband passivity assessment/enforcement | Planned; supplied real poles do not fulfill this point |
| I06 | Loaded transient use, analytical/circuit references, refinement and energy/stability | Planned; depends on I05 |
| I07 | Complete worker/schema/native desktop/save/run/recovery/export workflows | Planned; depends on I01-I06 |
| I08 | One integrated manifest covering every target and all current implementation receipts | Planned; depends on I01-I07 |

Implementation order is I04, I01, I02, I03, I05, I06, I07, I08. I01/I02/I03/I05
can proceed independently when their own references and tests are frozen.
I04 uses the existing bounded calibration domain and rejects unsupported cases;
its completion does not qualify measurement accuracy or arbitrary model scope.

E01 obtains approved measured standards/fixture/DUT data, metadata and complete
uncertainty budgets. E02 freezes budget-derived comparison criteria and executes
independent measured correlation/applicability checks. These gates are
**pending external evidence**, not implementation dependencies. R01 is
knowledgeable human numerical review; R02 is exact new installed-candidate
qualification. Both are **pending release**. Implementation, full-family and
release readiness are computed separately; current full SI08 remains open.

The [all-family SI/PI queue](SI_PI_EXECUTION_QUEUE_20261025.md) covers all 14
SI/PI families. Work without an actual SI08 dependency proceeds concurrently;
SI01-S02 reviewed constraint export is now verified independently. There is no
blanket instruction to finish SI08 measurement/release gates before other
SI/PI implementation. The unchanged broader expansion policy still applies.

The sections below preserve the original campaign and historical bounded
foundation evidence; they do not add checklist points.

### Current qualification and integration boundary

On 25 October the qualification owner released its source freeze for bounded
disjoint implementation. SI08-S05 remains the one stale historical stage:
53 of 54 labelled-complete stages passed the current source audit. Its new
13-test headless integration passed, but fresh correctly targeted candidate
native evidence is still missing. The previous launcher selected installed
alpha.1, and execution review stopped native automation. Old observations may
not be rebound or captured through an alternate automation path.

The finite native target is wide (at least 1200 by 600) and narrow (900–1100
by at least 600) views, long names, retained result, edit invalidation with
export disabled, singular-second-sample failure with export disabled, and
recovery; retain fresh screenshots/UIA and unchanged before/after sources for
the existing validator. This is qualification work, not a new checklist point.

Full-suite qualification also remains incomplete. The previous complete run
had 5,647 tests with one failure, 45 errors and 79 skips. Forty-eight focused
receipt/adversarial checks passed after genuine adoption; the corrected full
run was interrupted by a disk-capacity incident and is not passing evidence.
The remaining targets are capacity recovery, a complete stable-source rerun,
the native target above, installed lifecycle/Linux desktop qualification and
knowledgeable human review. See the
[qualification record](validation/MOVING_LID_RELEASE_QUALIFICATION_20261025.md)
and [incident record](validation/QUALIFICATION_DISK_INCIDENT_20261025.md).
This campaign performs no WSL relocation or large rerun.

Started 24 October 2026 at the owner's request to close complete families.
SI08 is the first campaign because its network-data boundary is self-contained;
PI03 physical placement and PI04 switching qualification depend on larger open
geometry, package and device-model work. None of these families is complete.
PI01-S02 board acceptance remains active and its frozen tolerances remain in force.

The original SI08 target is retained: reviewed causality/resampling/DC policy,
calibrated fixture removal, general port pairing and passive causal broadband
model fitting. The table is a family-level acceptance checklist, not a
percentage based on completed implementation milestones.

| Requirement | Current evidence | Remaining closure evidence |
| --- | --- | --- |
| General named pairing and interoperability | SI08-S01 explicit general mixed-mode pairing | End-to-end source/export identity, polarity, permutation, unpaired ports and independent reference checks in the family campaign |
| Source causality and resampling/DC policy | SI08-S03 explicit interpolation/DC and SI08-S04 causal constructed realization | Independent causal delayed/resonant and noncausal references, finite-band ambiguity, missing DC, grid refinement and reviewed applicability policy |
| Coupled multiport fixture algebra | Verified supplied 2N-port numerical reference, worker/schema execution and native desktop import/run/export, invalidation/recovery and wide/narrow inspection | Calibrated fixtures, uncertainty and physical qualification remain distinct gates |
| Calibration and uncertainty | SI08-S06 one-port foundation and SI08-S07 port-separable 2--4-port calibration with relative transmission gains and supplied joint covariance; independent wave/derivative/local-refinement oracles | Versioned calibration standards/method, calibrated multiport data, covariance/noise propagation and independently measured DUT comparison with predeclared uncertainty/tolerances |
| Passive causal broadband fitting | SI08-S04 supplied stable real-pole fit | Automatic stable complex-conjugate pole selection, independently assessed/enforced broadband passivity, retained pre/post models, DC/high-frequency behavior, held-out frequencies and intersample violation witnesses |
| Transient circuit use | Existing bounded rational/transient references | Automatic fitted models in loaded circuits, analytical/circuit references, refinement, long-horizon stability and energy/passivity checks |
| Full-family acceptance | No qualified family benchmark | Frozen versioned manifest mapping every original target/open gap to executed source-bound evidence; physical/measurement validity and independent numerical review; no open target gaps |

Work order is multiport fixture algebra, calibration/uncertainty foundations,
causality/DC policy qualification, general passive fitting, then integrated
transient and measured acceptance. Existing mathematical kernels may be reused
only inside their verified scope. Do not relabel supplied two-port algebra as
calibration, sampled passivity as broadband passivity, or a causal fitted model
as evidence that the source data are causal.

Before each remaining numerical implementation, freeze an observable-specific
reference, units, validity domain and tolerances. Measurement tolerances depend
on reviewed fixture/standard uncertainty and cannot be invented from synthetic
test errors. No fabricated or downloaded unlicensed measurement corpus is used.
The full-family benchmark remains definition-pending until these choices and
data are actually pinned. Release qualification and required human numerical
review remain separate from development milestones.

The authoritative status remains in
[the capability backlog](parity-capability-backlog-v1.json). SI08 remains
`in_progress`; no family is closed merely because its listed stages passed.

The original [offline multiport receipt](validation/parity/SI08-multiport-20261024.json)
remains historical evidence of that source snapshot. The later
[integration record](validation/SI08_MULTIPORT_INTEGRATION_20261024.md) covers
13 numerical/worker/workflow checks and actual headless panel handlers, with
native interactive acceptance completed and source-bound. Replay current bounded
integration evidence with `python -B scripts/verify_multiport_integration.py
--output FRESH.json --log FRESH.log`. Numerical recovery tolerances remain
fixture-specific 2e-12 absolute and relative. SI08-S05 is done; full SI08 remains in progress.
The native software-stage receipt is
[SI08-S05 native evidence](validation/parity/SI08-S05-native-20261024.json);
its validator is `scripts/parity_multiport_native_gate.py`.

[SI08-S06](validation/SI08_CALIBRATION_FOUNDATION_20261024.md) is done within
its offline one-port scope. General multiport calibration, measured standards
and nonlinear uncertainty adequacy remain open. The already-staged 0.4.1
installer does not contain this new module and gains no qualification from it.

[SI08-S07](validation/SI08_MULTIPORT_CALIBRATION_20261024.md) is done for
its offline known-standard, port-separable multiport scope. General crosstalk,
measured standards/DUT qualification and joint calibration/fixture covariance
remain open. No installed or release qualification is inferred.
