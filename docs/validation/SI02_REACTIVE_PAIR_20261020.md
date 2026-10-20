<!-- SPDX-License-Identifier: Apache-2.0 -->
# SI02-S09 reactive physical coupled-line endpoints - 20 October 2026

> **Public evidence boundary:** Paths marked as unbundled local records identify generated developer-run evidence that is not shipped in the public source. The historical observation remains provisional and does not establish release qualification; reproduce and review it before relying on the claim. See the [release local-evidence boundary](RELEASE_040_LOCAL_EVIDENCE.md).

Status: **Done for the bounded experimental development stage**. SI02, full
PI/SI parity, physical board qualification and human numerical release review
remain open. See [method and primary-reference derivation](../RLGC_REACTIVE_PAIR.md)
and [ADR 0118](../adr/0118-reactive-coupled-line-boundaries.md).

## Executed evidence

- [Source-bound receipt](parity/SI02-S09-qualified-20261020.json) and
  raw execution log (unbundled local record: `parity/SI02-S09-qualified-20261020.log`): **12 passed,
  zero failures/errors/skips**. All 43 distinct source paths match current
  bytes and their before/after execution hashes. The receipt binds the numerical
  kernel, tests, worker/CLI, example, strict schemas, method/ADR and underlying
  resistive/coupled/scalar producer dependencies.
- Independent physical four-state matrix-exponential endpoint equations verify
  conductor V/I and source current, with no production modal/wave/feedback helper.
  A separate lossless scalar ABCD loaded-transfer oracle verifies endpoint signs.
  Pure zero-L/C reproduces the resistive producer. Frozen V/I tolerance is
  2e-11 absolute plus 2e-9 relative; complex power/heat is 2e-12 plus 2e-9
  relative; mean stored energy is 2e-20 J plus 2e-9 relative.
- A large-storage fixture distinguishes source/line/capacitor currents and keeps
  mean J and reactive var separate from heat W. Complex source work, KVL/KCL,
  absorbing-source signs, zero/scaling/order/permutation/reversal, malformed or
  unrepresentable inputs, conditioning, resources, cancellation/callback failure
  and split-preserving child-field/heat corruption are covered.
- Actual worker, command-line, saved example and strict nested schema workflows
  pass. Source request and digest retain the original physical terminal/model
  identity. Example execution:

  ```powershell
  .venv-emerge3/Scripts/python.exe -m python.spike_core.cli --quiet --output build/reactive-pair-result.json rlgc-reactive-pair examples/rlgc_reactive_pair/rlc.request.json
  ```

- **99 focused regressions passed**, no failures/errors/skips, in 9.690 seconds:
  `test_si_workflow`, `test_si_network_graph_workflow`, `test_schema_catalog`,
  scalar RLGC network/fields, coupled-pair and resistively terminated-pair
  numerical/contract modules. This is focused integration verification, not
  a full repository, installer, release or original-board qualification run.
- **22 prior numerical stages genuinely reexecuted**, totaling **263 test
  executions** with no failures/errors/skips. They cover 19 affected shared
  CLI/worker/catalog stages, SI01-S01, SI02-S07 and SI02-S08. Fresh receipt/log
  names end `-reactive-pair-20261020`; historical receipts remain unchanged.
  Replay summary: `build/si02-s09-development-20261020/prior-replays.json`.
- PI01-S01 additionally binds the CLI. Its original owned-mode EBrake command
  and all four unchanged mesh levels were rerun with stable source hashes in
  `build/si02-s09-development-20261020/ebrake-owned-replay`. Approximate CLI
  execution completed; density remains **failed_to_converge, can_sign_off=false**.
  This expected failing board audit was retained, not converted into a pass.
  The separate **28 owned-pad checks passed** with a
  [fresh bounded geometry receipt](parity/PI01-S01-reactive-pair-20261020.json).

Final backlog and separate candidate/coupled/resistive/reactive stage-evidence
checks passed **18 tests, zero skips**, in 18.038 seconds; raw log:
`build/si02-s09-development-20261020/tracking-regressions.log`. Architecture
checks and all 68 capability backlog/source-bound evidence checks passed.

Pre-implementation bounds/tolerances remain in
`build/si02-s09-development-20261020/acceptance-plan.json`, SHA-256
`ea410b22bf32e29cdf0077a25e341fdc6298a8ddb7d5071a0fd919ea0d467f6`.
Independent read-only numerical and integration review found no actionable gap,
independently ran all 12 tests with zero skips, checked receipt validity and ran
the stage-evidence corruption controls. Kernel SHA-256:
`e10c6ac00135362e317d3f88598432d7061ce7fb8f79725441a3408dc82c2577`.
Agent review does not replace required knowledgeable human review before release.

## Scope and unresolved work

Each positive frequency is an independent RMS steady scenario. No automatic
sample summation, transient thermal history, heat deposition or contact ownership
is inferred. Explicit terminal IDs preserve future coupling identity. General
reactive topology, ideal open/short, nonlinear or lossy/frequency-dependent
reactives, causal/transient initialization, asymmetric geometry extraction,
measurement correlation and physical thermal feedback remain open. Original
EBrake and Marble qualification limits remain in the
[PEEC follow-up](PEEC_REPAIR_FOLLOWUP_20261019.md); Marble was not requalified
by this bounded endpoint change. No full SI/PI or multiphysics parity claim.
