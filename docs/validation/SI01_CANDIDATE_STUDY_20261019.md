<!-- SPDX-License-Identifier: Apache-2.0 -->
# SI01-S01 finite supplied-line candidate/corner verification — 2026-10-19

> **Public evidence boundary:** Paths marked as unbundled local records identify generated developer-run evidence that is not shipped in the public source. The historical observation remains provisional and does not establish release qualification; reproduce and review it before relying on the claim. See the [release local-evidence boundary](RELEASE_040_LOCAL_EVIDENCE.md).

Status: **Done for the bounded experimental stage**. SI01 remains in progress;
whole PI/SI parity and physical-board qualification are not established.

The [method record](../SI_CANDIDATE_STUDY.md) defines V/V observables, explicit
models, primary-reference access, independent derivations, units, frozen
tolerances and omitted physics. [ADR 0112](../adr/0112-finite-si-candidate-corner-studies.md)
records the unchanged-solver orchestration boundary.

## Executed evidence

- [Source-bound stage receipt](parity/SI01-S01-verified-20261019.json) and
  raw test log (unbundled local record: `parity/SI01-S01-verified-20261019.log`): **22 passed, 0 skipped**.
  Sources were hashed before execution and checked unchanged afterward.
  The receipt binds production bytes, reused solver dependencies, public routing,
  request/result schemas, example, method documentation and exact test identities.
- Real worker, CLI and standalone example agree. Registered schemas validate the
  request/result and canonical digests. Complete Cartesian coverage, exact
  frequency retention, failure/partial exclusion, cancellation, forged provenance,
  nonfinite output and streaming resource exhaustion have rejection controls.
- Independent lossless ABCD and matched-line complex transfer checks meet the
  predeclared 2e−11 absolute / 2e−9 relative tolerances. Distributed-resistance DC
  and supplied 25/85°C resistor TCR corners meet the DC reference tolerances;
  temperature metadata is retained without inventing a thermal field.
- All **19 affected prior numerical stages** were actually rerun, totaling
  **214 test executions**, with 0 failures/errors/skips. Fresh dated receipts/logs
  ending `-si01-integration-20261019` replace only backlog evidence pointers;
  historical receipts remain. Replay summary:
  `build/si01-s01-development-20261019/prior-stage-replays.json`.
- PI01-S01 also binds the CLI: its **28 owned-pad tests passed** in a
  [fresh source-bound receipt](parity/PI01-S01-si01-integration-20261019.json).
  The actual unchanged EBrake owned-mode CLI and all four mesh levels were
  reexecuted with stable source hashes. Execution completed approximately;
  density convergence remained `failed_to_converge`, with `can_sign_off=false`.
  No physical-board acceptance is inferred from this stage receipt.
- **39 focused workflow, network-graph workflow and schema catalog regressions
  passed**, no skips. Log:
  `build/si01-s01-development-20261019/focused-regressions.log`.
- The stage evidence adversarial test passes and rejects source/hash/log/count,
  skip, failed-status and qualification tampering. Architecture checks pass.
- Final backlog coverage/evidence validation passes for all 68 capability items.
  The combined backlog and stage-evidence regression run passes **15 tests**,
  0 skips; log `build/si01-s01-development-20261019/tracking-regressions-verified.log`.
  The recorded-reference inventory was regenerated and checked after integration.

An initial regression command named a nonexistent network-workflow test module;
that command failed collection. The corrected command used the actual
`test_si_network_graph_workflow` module and produced the passing 39-test log.
The earlier provisional `SI01-S01.json` receipt predates the final evidence-source
list and is historical; the verified dated receipt above is authoritative.

## Independent review and limits

Independent read-only review identified missing child provenance binding and
late aggregate-size admission in the scratch version. Both were fixed, then
reviewed again. Final production integration review independently ran all 22
tests, with no actionable issue remaining. Production kernel byte SHA-256:
`b0af582abce930f86c39dc65ded52b73a41c0abdbab2cb33dd90e1b374060cca`.
Scratch and production text were equal after CRLF normalization; raw hashes
differ because line endings differ. No byte-identity claim is made.

This is deterministic supplied scalar-line sampled comparison. It establishes
neither continuous-band compliance nor measured accuracy, statistical yield,
general topology editing, native layout-rule export, nonlinear IBIS/eye/BER
qualification, field maps or physical heat/material feedback. Human numerical
release review remains pending. The broader qualification run and original
EBrake failures remain recorded in the
[separate repair follow-up](PEEC_REPAIR_FOLLOWUP_20261019.md); no original contact,
geometry or acceptance gate was changed by this stage.
