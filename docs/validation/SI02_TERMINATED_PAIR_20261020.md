<!-- SPDX-License-Identifier: Apache-2.0 -->
# SI02-S08 physical resistive source/load verification — 20 October 2026

> **Public evidence boundary:** Paths marked as unbundled local records identify generated developer-run evidence that is not shipped in the public source. The historical observation remains provisional and does not establish release qualification; reproduce and review it before relying on the claim. See the [release local-evidence boundary](RELEASE_040_LOCAL_EVIDENCE.md).

Status: **Done for the bounded experimental stage**. The complete SI02 family,
physical board qualification and release remain open. See the
[method and primary-reference record](../RLGC_TERMINATED_PAIR.md) and
[ADR 0116](../adr/0116-physical-resistive-coupled-line-terminations.md).

## Executed evidence

- [Current source-bound receipt](parity/SI02-S08-qualified-20261020.json) and
  raw log (unbundled local record: `parity/SI02-S08-qualified-20261020.log`): **13 passed, 0 skipped**.
  All 32 bound sources match before/after execution and current bytes. The
  receipt includes actual worker/CLI, saved example, strict registered schemas,
  complete producer dependencies, test identities and method documentation.
- An independently authored physical four-state spatial matrix-exponential
  boundary solve verifies loaded conductor V/I. It solves left `V+R I=Vs` and
  right `V-R I=Vs`, using neither production feedback nor power-wave conversion.
  Frozen tolerances are 2e−11 absolute plus 2e−9 relative for V/A.
- Independent physical quadratic heat and 64-point length quadrature verify
  separate conductor/dielectric heat to 2e−12 absolute plus 2e−9 relative in W.
  Matched-line divider/phase and an absorbing-source case verify the physical
  signs and signed source work. Source work equals terminal resistor heat plus
  distributed line heat without adding nested modal loss a second time.
- Other controls cover source/termination record ordering, zero/scaling,
  probe independence, conductor permutation and line reversal, malformed and
  nonfinite/bool data, ill-conditioned feedback, resource admission, cancellation
  and callback failures, forged child provenance, boundary/interior fields and
  heat splits that preserve the total.
- **80 focused regressions passed**, zero skips: loaded SI workflow, network
  graph workflow, schema catalog, scalar RLGC network/fields and coupled-pair
  numerical/contract cases. Log:
  `build/si02-s08-development-20261020/focused-regressions.log`.
- **21 prior numerical stages were genuinely rerun**, totaling 250 test
  executions with no failures/errors/skips: 19 affected shared network/CLI
  stages, SI01-S01 and SI02-S07. Current hashes were validated before backlog
  pointer updates. Fresh receipts/logs end `-terminated-pair-20261020`; historical
  receipts remain. Raw summary:
  `build/si02-s08-development-20261020/prior-replays.json`.
- PI01-S01 additionally binds the CLI. Its unchanged EBrake owned-mode CLI and
  all four mesh levels were rerun with stable source hashes. Approximate execution
  completed, but density remains `failed_to_converge`, `can_sign_off=false`.
  The separate **28 owned-pad tests passed**, with a
  [fresh bounded receipt](parity/PI01-S01-terminated-pair-20261020.json).
  This refresh verifies the existing geometry stage and does not qualify EBrake.
- The new stage-evidence adversarial test rejects source drift, missing producer
  coverage, failed/qualified state, skips, count and log tampering.
- Final backlog and stage-evidence regressions pass **17 tests**, zero skips;
  log `build/si02-s08-development-20261020/tracking-regressions.log`.
  Architecture and all 68 capability backlog/evidence checks pass. The recorded
  reference inventory was regenerated and checked after integration.

The pre-implementation acceptance plan is retained at
`build/si02-s08-development-20261020/acceptance-plan.json`. Independent review
found a real integrity gap: total-power checks alone admitted a false
conductor/dielectric split and unchecked interior fields. The repair reconstructs
those observables from canonically bound modal constituents and checks each
channel separately. The corresponding corruption tests now reject them.

## Independent review and limits

Independent read-only re-review found no remaining actionable numerical or
integration issue and independently ran all 13 numerical/contract tests.
Reviewed kernel SHA-256:
`ea1112a14446775ea689f0415ac40e88c5a08eab469e342799f3a24acd084e76`.
This is agent review; knowledgeable human numerical review remains required
before release.

Every frequency row is a separate steady RMS operating case. No automatic
frequency summation, transient thermal input or physical heat mapping is inferred.
Terminal IDs label lumped heat, not finite contacts or mesh cells. Reactive,
ideal/zero/infinite resistances, general asymmetric geometry, causal/transient
material models, measured accuracy and thermal feedback remain open. Existing
EBrake/Marble and broad qualification limits remain in the
[separate PEEC follow-up](PEEC_REPAIR_FOLLOWUP_20261019.md).
