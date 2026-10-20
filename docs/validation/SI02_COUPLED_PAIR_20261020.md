<!-- SPDX-License-Identifier: Apache-2.0 -->
# SI02-S07 supplied symmetric coupled pair verification — 20October2026

> **Public evidence boundary:** Paths marked as unbundled local records identify generated developer-run evidence that is not shipped in the public source. The historical observation remains provisional and does not establish release qualification; reproduce and review it before relying on the claim. See the [release local-evidence boundary](RELEASE_040_LOCAL_EVIDENCE.md).

This bounded experimental stage composes supplied even/odd scalar models into
physical-conductor four-port scattering, coherent V/I and conservative pair
loss/storage. The full SI02 family remains in progress. See the
[method record](../RLGC_COUPLED_PAIR.md) and
[ADR0113](../adr/0113-symmetric-coupled-rlgc-pair.md) for exact assumptions,
primary-reference access, original derivation, units and validity limits.

Status: **Done for the supplied symmetric-pair stage**, recorded only after
current source-bound receipts and independent review passed.

## Executed evidence

- [Source-bound receipt](parity/SI02-S07-qualified-20261020.json) and
  raw test log (unbundled local record: `parity/SI02-S07-qualified-20261020.log`): **14 passed, 0 skipped**.
  All22 source hashes match before/after execution and current source bytes.
  Actual worker, CLI and standalone example agree and satisfy strict registered
  request/result schemas. Child requests, digests and full modal results remain.
- An independently authored physical4×4 spatial matrix-exponential boundary
  solve checks all complex S entries and conductor V/I; it uses neither production
  transforms nor scalar propagation helpers. Original self/mutual quadratic forms
  check J/m and W/m;32/64point Gauss quadrature checks integrated conductor and
  dielectric W. All frozen tolerances in the method record pass.
- Other checks cover lossless unitarity/reciprocity, actual near/far-end coupling,
  equal-mode zero coupling, pure modes/exact zero, coherent drive scaling,
  probe-independent integrals, conductor permutation, line reversal/current
  sign, malformed modal identity, nonfinite/bool inputs, preflight resource
  rejection, cancellation/callback failure and forged child results.
- **66 focused regressions passed**, 0 skipped: loaded SI workflow, network-graph
  workflow, schema catalog and scalar RLGC network/field tests. Log:
  `build/si02-s07-development-20261020/focused-regressions.log`.
- **20 prior stages were genuinely rerun**, totaling236 test executions, with
  zero failures/errors/skips. This covers19 shared network/CLI stages plus
  SI01-S01. Their fresh dated receipts/logs end `-coupled-pair-20261020`;
  raw replay summary `build/si02-s07-development-20261020/prior-replays.json`.
  Every replay was checked against the final catalog, including the other
  chat's coordinated CFD additions; historical receipts were preserved.
- PI01-S01 additionally binds the changed CLI: the actual unchanged EBrake
  owned-mode CLI and all four mesh levels were rerun with stable source hashes.
  Approximate execution completed but density convergence remains
  `failed_to_converge`, `can_sign_off=false`. Its separate28 owned-pad tests and
  [fresh bounded receipt](parity/PI01-S01-coupled-pair-20261020.json) verify only
  the already-established geometry stage. No physical contact was invented and
  no board gate or threshold changed.
- The separate stage-evidence adversarial test passes; it rejects source drift,
  missing source coverage, failed/qualified state, skips, count and log tampering.
- Final backlog and stage-evidence regressions pass all16 tests, zero skips;
  log `build/si02-s07-development-20261020/tracking-regressions.log`.
  Architecture and68-item backlog/evidence checks pass. The reference inventory
  was regenerated and checked after integration.

The pre-implementation acceptance record is retained in
`build/si02-s07-development-20261020/acceptance-plan.json`.
The earlier `SI02-S07-verified-20261020.json` receipt predates the final CFD
catalog append and is historical; the qualified dated receipt above is current.

## Independent review and qualification limits

Independent read-only review found no actionable numerical or integration defect.
It independently ran all14 numerical/contract tests and validated the final
receipt against all22 sources, exact test identities and bound log. Reviewed
kernel SHA-256:
`d50c53e95e5009e716abdca808d5a705ad34d1f855cca480b18d71a08ff9b6fc`.
This is agent review, with knowledgeable human numerical review still required
before release.

There are no admitted physical measurements or geometry-derived modal data.
Arbitrary asymmetric/noncommuting matrices, bends/vias/reference discontinuities,
DC/transient/causal material qualification, radiation, thermal deposition and
feedback remain open. Pair-level and modal heat represent the same loss;
consumers must not double count them or assign mutual terms to invented cells.
Original EBrake/Marble and broader release qualification are not promoted by
these synthetic checks; the existing
[PEEC follow-up](PEEC_REPAIR_FOLLOWUP_20261019.md) retains unresolved board failures.
