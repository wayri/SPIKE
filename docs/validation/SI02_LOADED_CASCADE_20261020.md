<!-- SPDX-License-Identifier: Apache-2.0 -->
# SI02-S11 physical RLC loaded coupled-cascade verification -20 October2026

> **Public evidence boundary:** Paths marked as unbundled local records identify generated developer-run evidence that is not shipped in the public source. The historical observation remains provisional and does not establish release qualification; reproduce and review it before relying on the claim. See the [release local-evidence boundary](RELEASE_040_LOCAL_EVIDENCE.md).

Status: **Done for the bounded experimental development stage**.
The implemented capability remains experimental with `production_qualified:false`
regardless of replay completion. SI02, full PI/SI parity, physical board
qualification and knowledgeable human numerical release review remain open.
See [independent method/source ledger](../RLGC_LOADED_CASCADE.md) and
[ADR0122](../adr/0122-physical-rlc-loaded-coupled-cascades.md).

## Executed evidence

- [Source-bound receipt](parity/SI02-S11-qualified-20261020.json) and
  raw test log (unbundled local record: `parity/SI02-S11-qualified-20261020.log`): **10 passed, zero
  failures/errors/skips**. All65 distinct bound source hashes match current
  bytes and before/after execution. The envelope includes both unchanged S09/S10
  constituent dependency envelopes, own kernel/tests/contracts/example/method/ADR,
  worker/CLI/catalog and the evidence validator. No numerical source hash was
  refreshed without executing its gate.
- An independently authored physical self/mutual four-state spatial chain solves
  the RLC exterior equations directly, without production modal transform or wave
  feedback. It reuses the preceding independent test oracle's physical coefficient
  assembly; the zero-drive wave boundary solution is discarded. The new physical
  RLC equations determine initial state and all section probe V/I and terminal
  line/source currents. Voltage/current tolerance:2e-11 absolute plus2e-9 relative.
- Independent32/64-node physical quadratic heat integration verifies every section
  conductor/dielectric split, not just total balance. Source/line complex powers
  and terminal heat use2e-12 absolute plus2e-9 relative. Mean L/C energy uses
  2e-20 J absolute plus2e-9 relative. Source current differs from line current by
  capacitor current. A large-storage case proves mean J/reactive var are separate
  from terminal/section heat W; absorbing-source work keeps its sign.
- One-section equality to the unchanged S09 result, physical resistive limit,
  homogeneous subdivision, zero/scaling, terminal record ordering, conductor
  permutation and chain reversal pass. Duplicate ports, wrong source grids,
  exact cross-section reference mismatch, malformed/nonfinite reactive values,
  resources, conditioning,1e308 unrepresentability, cancellation and callback
  failure all reject. Forged child digest/network/interior field, section order,
  heat split preserving total, aggregate heat and junction ledger all reject.
- Actual worker, CLI, saved example, strict nested schemas and request/digest
  no-mutation checks pass. Request/result contracts remain separate from the
  supplied child model and preserve complete loaded child provenance.
- **136 focused regressions passed, zero skips**, in28.889 seconds: SI workflow,
  network graph, schema catalog, scalar RLGC network/fields/cascades, coupled
  pairs, resistive/reactive boundaries and piecewise coupled-cascade numerical
  and contract modules. Raw log:
  `build/si02-s11-development-20261020/focused-regressions.log`.

- **24 prior numerical stages genuinely reexecuted**, totaling **286 test
  executions**, no failures/errors/skips:19 affected shared CLI/worker/catalog
  stages plus SI01-S01 and SI02-S07/S08/S09/S10. Fresh receipt/log names end
  `-loaded-cascade-20261020`; historical receipts remain unchanged. Replay
  summary:`build/si02-s11-development-20261020/prior-replays.json`.
- PI01-S01 separately binds the CLI. Its original owned-mode EBrake CLI and all
  four unchanged mesh levels were rerun in
  `build/si02-s11-development-20261020/ebrake-owned-replay`, with stable source
  hashes. Approximate CLI execution completed, but density remains
  **failed_to_converge, can_sign_off=false**. The audit's failure is preserved.
  **28 owned-pad checks passed**, with a
  [fresh bounded geometry receipt](parity/PI01-S01-loaded-cascade-20261020.json).
  This geometry result does not qualify the board.

Final backlog and candidate/pair/reactive/cascade/loaded evidence corruption
controls passed **20 tests, zero skips**, in19.267 seconds; raw log:
`build/si02-s11-development-20261020/tracking-regressions.log`. The68-capability
backlog/source-bound checker and architecture boundaries pass. Reference inventory
is regenerated and checked against the final shared-tree snapshot.

## Independent review and provenance

Independent read-only numerical review verified both conditioned direct solves,
physical boundary reconstruction, exact canonical child ledger binding, section
heat accounting, resource/cancellation bounds and oracle independence. Final
integration review independently ran all10 numerical/contract tests with zero
skips, checked the65-source/log-bound receipt and found no actionable issue.
Reviewed kernel SHA-256:
`077a3bdbf4b564d0b63f6776ead825f7d401778d9257cd8ccc6662bd1610f885`.
Frozen pre-implementation acceptance plan:
`build/si02-s11-development-20261020/acceptance-plan.json`, SHA-256
`83da52a88dd0ecf3550bc95c2af7495356ba691ab4f073dcdf97e31e132295eb`.
Agent review does not replace required knowledgeable human numerical review before
release. No independent measurement or performance-parity claim is made.

## Run and remaining applicability

```powershell
.venv-emerge3/Scripts/python.exe -m python.spike_core.cli --quiet --output build/loaded-cascade-result.json rlgc-loaded-cascade examples/rlgc_loaded_cascade/physical.request.json
```

The four exterior physical ports retain conductor0-left,conductor1-left,
conductor0-right,conductor1-right order. Each positive frequency is an independent
RMS steady scenario. Named terminals own lumped resistor heat; named sections own
pair-level distributed heat. No physical contact area, mutual-term conductor
share, thermal cell, temperature law or transient thermal history is inferred.
General terminal topology, ideal open/short, nonlinear/lossy/frequency-dependent
reactives, asymmetric/noncommuting models, branching, geometric discontinuity or
return parasitics, DC/transient/causal initialization, radiation, thermal feedback,
measurements and original-board qualification remain open. Original EBrake and
Marble limitations remain in the [PEEC follow-up](PEEC_REPAIR_FOLLOWUP_20261019.md).
Marble was not requalified by this integration; no full repository, installed
desktop or release qualification was executed by this stage.
