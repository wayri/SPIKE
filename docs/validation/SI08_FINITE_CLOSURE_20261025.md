<!-- SPDX-License-Identifier: Apache-2.0 -->
# Finite SI08 closure and independent SI/PI execution

Date: 25 October 2026. This records a frozen execution plan and two verified
implementation advances, not completed SI08 parity or release qualification.

## Frozen plan

[Checklist v1](../si08-closure-checklist-v1.json) pins exactly I01--I08,
E01--E02 and R01--R02. Each point has a concrete deliverable, owner role,
prerequisites, implementation steps and acceptance/evidence. The
[readable plan](../SI08_FAMILY_CLOSURE.md) maps all original SI08 targets to
these points without substituting stage counts for full-family acceptance.
`scripts/check_si08_closure.py` checks the frozen scope SHA256, fixed point
inventory, statuses, dependencies and supported current evidence validators.
The main backlog guard invokes it and refuses a completed SI08 with open gates.
Tests reject deleted/redefined points, added external implementation blockers,
unverified promotions and incomplete execution evidence.

Implementation completion, full-family acceptance and release readiness are
computed separately. The user confirmed **no measured corpus yet**; E01 records
this external blocker and the exact needed data/metadata/certificate/budget
inputs. E02 requires the independently measured correlation. R01 requires
knowledgeable human review and R02 the exact new installed candidate. None
blocks an implementation with no actual dependency. The source-only additions
remain excluded from the earlier immutable 0.4.1 installed candidate.

The [execution queue](../SI_PI_EXECUTION_QUEUE_20261025.md) covers every SI/PI
family with its next deliverable, validation route and real dependencies. It
also records the directly reconciled current 63 family IDs versus stale
68-family narrative counts; no original family IDs were silently removed by
this task. The queue keeps implementation, measured evidence and release work
distinct. After I04 the remaining order is I01, I02, I03, I05, I06, I07, I08.

## Closed SI08-I04: joint calibration and fixture covariance

The [method](../CALIBRATED_FIXTURE_UQ.md) composes the unchanged known-standard
calibration and coupled-fixture owners. It retains the complete calibration/
fixture cross-covariance rather than summing independent error budgets. The
nested calibration covariance must equal the joint leading block exactly;
it is never counted twice. Explicit port/storage maps, source snapshots and
separate derived networks are retained, with original numerical/resource limits
and additional canonical near-pole rejection.

The [independent preimplementation derivation](CALIBRATED_FIXTURE_UQ_DERIVATION_20261025.md)
and nine independent oracles verify all 544 admitted real input coordinates,
truth, dense/cross-frequency covariance, cancellation, port/storage
behavior, nonlinear local refinement and atomic pole/late failure cases. Four
additional contract/cancellation/budget/actual CLI checks complete the 13-test
source-bound gate. The maximum observed truth/Jacobian/covariance errors were
`4.85e-16` absolute, `1.164e-9` absolute and `1.666e-10` relative respectively.
Frozen tolerances were not weakened. These remain local synthetic numerical
checks; physical measurement and per-input nonlinear adequacy are unqualified.

Current [I04 receipt](parity/SI08-I04-joint-uq-r2-20261025.json),
[log](parity/SI08-I04-joint-uq-r2-20261025.log) and
[source/result capture](parity/SI08-I04-joint-uq-r2-capture-20261025.json)
bind final sources, complete executed test names and runtime versions. The
initial wrapper run expected 12 tests before the independent suite added its
ninth test; its rejected receipt remains historical. The final frozen replay
requires and passes all 13. No first-run rejection is relabeled as success.

Three finite-checklist tests passed, including current evidence validation and
separation of external/release gates from ready implementation. Twenty-seven
unchanged calibration/fixture regressions passed. Numerical source paths follow
the current `solvers/signal_integrity/networks/` ownership after migration.

## Independent SI01 advance

[SI01-S02](../SI_CANDIDATE_CONSTRAINT_EXPORT.md) exports explicit reviewed
selections from existing SI01-S01 studies to neutral finite sampled constraint
manifests. It preserves original supplied limits and their witnesses instead
of manufacturing design limits from observed extrema. Exact source/result
digests and coverage/status are checked. Hold/reject and failed cases remain
non-applicable; native layout, continuous-band, physical and production flags
remain false. It does not depend on measured SI08 closure.

Six implementation tests, three adversarial verifier tests and 22 existing
SI01 study/contract tests passed in a coherent 31-test replay. Its
[source-bound receipt](parity/SI01-S02.json) is accepted by the backlog stage
dispatcher only after current source and execution validation. This stage is
done; the complete SI01 target remains open.

## Broader verification and preserved failures

Architecture and all changed-document checks passed after correcting the
readable checklist's initial heading order. Scoped whitespace and reference
inventory checks are recorded after the final pass. No full repository suite
or installed candidate qualification is claimed for these source additions.

The first broad backlog attempt in `.venv-emerge3` timed out in owned-pad
class setup with zero tests executed, reporting a large elapsed/negative
remaining-time gap. A `.venv` retry also ran zero backlog tests because its
owned-pad gate failed. Component isolation found 28/28 owned-pad tests pass in
`.venv-emerge3`, while the `.venv` sandbox interpreter produced temporary-file
access/cleanup PermissionErrors in the custom-pad cases. Neither failure was
waived. The final retry uses `.venv-emerge3` with TEMP/TMP inside the authorized
workspace and retains `build/si08-finite-backlog-20261025-r3.log`. Its terminal
result is appended below; the earlier failed attempts remain failed attempts.


## Terminal verification and current global blocker

The workspace-temp retry executed 16 backlog tests in 185.415 seconds and
failed with five errors. Unlike the setup failures, this discriminated the
actual broader blocker: historical receipts no longer match source coverage
following the solver-directory migration. A per-stage audit found 51 stale
receipts. The unchanged SI01-S01 gate was genuinely replayed after relocation:
22 tests passed, its current source-bound receipt is retained at
`parity/SI01-S01-finite-closure-replay-20261025.json`, and its backlog pointer
was updated with the earlier receipt preserved in history. Fifty historical
receipts still require genuine replay, including older WF01/PI/SI and native
SI08-S05 acceptance. The backlog retains this explicit audit and continues to
reject those stale proofs; hashes and requirements were not patched to make
the run green. Historical done labels are not current qualification.

Current I04 and SI01-S02 source-bound gates validate independently, with the
SI01-S01 dependency now current. Three finite-checklist adversarial tests pass.
Twenty-seven preceding calibration/fixture regressions and 31 SI01
new/existing tests pass; component diagnosis separately passed all 28 owned-pad
tests in `.venv-emerge3`. Architecture and ten changed-document checks pass.
The reference inventory was regenerated and checked; scoped whitespace checks
pass. Full repository and installed qualification remain unclaimed.

Coordination preserves the other chat's numerical exclusivity window and low-C
storage constraint. No mass replay or large new C output is launched here.
The other chat explicitly accepted ownership of all remaining 50 genuine
receipt replays after its exclusivity windows; this chat completed the
SI01-S01 prerequisite replay. Native acceptance is included where required,
and the replay owner is coordinating isolated qualification storage. Native captures cannot be promoted
by merely rebinding migrated source hashes. This blocker is covered by I08's
existing integrated-current-evidence gate; it does not create a ninth SI08
implementation point or invalidate the newly verified joint-UQ implementation.
