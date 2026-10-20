<!-- SPDX-License-Identifier: Apache-2.0 -->
# SI02-S12 ideal coupled-star verification — 20 October 2026

> **Public evidence boundary:** Paths marked as unbundled local records identify generated developer-run evidence that is not shipped in the public source. The historical observation remains provisional and does not establish release qualification; reproduce and review it before relying on the claim. See the [release local-evidence boundary](RELEASE_040_LOCAL_EVIDENCE.md).

Status: **Done for the bounded experimental development stage**.
The capability remains experimental with `production_qualified:false` regardless
of development replay completion. SI02, full PI/SI parity, physical board
qualification and knowledgeable human numerical release review remain open.
See [independent method/source ledger](../RLGC_COUPLED_STAR.md) and
[ADR 0123](../adr/0123-ideal-supplied-coupled-line-stars.md).

## Executed evidence

- [Source-bound receipt](parity/SI02-S12-qualified-20261020.json) and
  raw execution log (unbundled local record: `parity/SI02-S12-qualified-20261020.log`): **12 passed,
  zero failures/errors/skips**. All 54 distinct bound source paths match current
  bytes and before/after execution hashes. The envelope includes own numerical
  kernel/tests/contracts/example/method/ADR, worker/CLI/catalog and unchanged
  constituent pair/field/connection/provenance dependencies.
- An independent physical self/mutual telegrapher operator for every leg feeds
  a 4m-state boundary system: exterior V+Z0 I conditions, common right-conductor
  voltage and node KCL. Direct spatial matrix exponentials verify every S column
  and coherent internal probe field without production modal/wave helpers.
  V/I/S tolerance: 2e-11 absolute plus 2e-9 relative.
- Independent 32/64-node physical quadratic integration verifies each leg's
  conductor/dielectric heat separately to 2e-12 W absolute plus 2e-9 relative,
  including quadrature refinement. Global input equals leg heat counted once;
  the two distinct ideal nodes conserve voltage, current and signed power.
- Identical uncoupled matched branches agree with the closed-form phased
  unitary star matrix. Two legs agree with the unchanged coupled cascade.
  Zero/scaling, leg/conductor permutations, collision-free JSON pair identities
  and the actual eight-leg/sixteen-port upper boundary pass; nine legs reject.
- Malformed identity/reference/grid/excitation, empty probes, resources, trapped
  singular connections, 1e308 representability, cancellation/callback failures,
  forged child identity/interior fields and false heat splits preserving total
  all reject. Raw node voltage/current/power and connection residuals remain
  explicit; none are relabeled as junction heat or redistributed.
- Actual worker/CLI/example/schema/provenance checks pass. Initial contract
  tests exposed a schema dimension gap: the runtime rejected malformed wave
  lengths while the schema admitted them. Explicit 2–8-leg request/result
  conditionals now enforce wave, matrix, boundary and node-residual dimensions.
  Two- and eight-leg outputs validate; dimension-tampering cases reject.
- **161 focused regressions passed, zero skips**, in 36.118 seconds: SI workflow,
  network graph, schema catalog, scalar RLGC network/fields/cascades/stars,
  coupled pairs, resistive/reactive endpoints, coupled cascades and physically
  loaded cascades with their contract modules. Raw log:
  `build/si02-s12-development-20261020/focused-regressions.log`.

- **25 prior numerical stages genuinely reexecuted**, totaling **296 test
  executions**, zero failures/errors/skips: 19 affected shared CLI/worker/catalog
  stages plus SI01-S01 and SI02-S07 through SI02-S11. Fresh receipt/log names
  end `-coupled-star-20261020`; historical evidence remains unchanged. Summary:
  `build/si02-s12-development-20261020/prior-replays.json`.
- PI01-S01 separately binds the CLI. Its original owned-mode EBrake CLI and all
  four unchanged mesh levels were actually rerun with stable source hashes in
  `build/si02-s12-development-20261020/ebrake-owned-replay`. Approximate execution
  completed, but density remains **failed_to_converge, can_sign_off=false**.
  The board audit failure is preserved. **28 owned-pad checks passed** with a
  [fresh bounded geometry receipt](parity/PI01-S01-coupled-star-20261020.json);
  the geometry pass does not qualify EBrake.

Final backlog and separate stage-evidence corruption controls passed **21 tests,
zero skips**, in 15.308 seconds. Raw log:
`build/si02-s12-development-20261020/tracking-regressions.log`. The 68-capability
backlog/source-bound checker, architecture boundaries and scoped whitespace check
pass. Reference inventory is regenerated and checked against the final shared-tree
snapshot; that inventory records links, not proof of source adoption or validation.

## Independent review and provenance

Independent read-only numerical review verified the two-conductor node map,
its projector/unitarity proof, physical ordering/KCL/power signs, strong child
field/loss binding, resource/cancellation bounds and oracle independence.
Final integration review independently ran all 12 numerical/contract tests with
zero skips, validated the 54-source/log-bound receipt and found no actionable
issue. Reviewed kernel SHA-256:
`cd3b1652a348db5264ff8c21d7c347444b972af3bb69bce701a96ba652f13f00`.
Frozen pre-implementation plan:
`build/si02-s12-development-20261020/acceptance-plan.json`, SHA-256
`5f4bc181671bba34ae1ecac02d21a6d4c65c6c52527de3498c89eb35a2e219ba`.
Agent review does not replace knowledgeable human numerical review before release.
No independent measurement or performance-parity claim is made.

## Run and remaining applicability

```powershell
.venv-emerge3/Scripts/python.exe -m python.spike_core.cli --quiet --output build/coupled-star-result.json rlgc-coupled-star examples/rlgc_coupled_star/three-leg.request.json
```

Exterior ports follow leg then conductor order; network labels are canonical
JSON [leg_id, conductor_id] strings. Right ends with matching conductor identity
meet at their own ideal node, without shorting the two conductors together.
Each positive frequency is an independent RMS steady scenario. Leg IDs retain
pair-level heat ownership, without inferring mutual-term conductor shares,
contact areas, thermal cells, temperature laws or transient heat histories.
General graphs, asymmetric or piecewise legs, physical RLC star endpoints,
geometric junction/contact/return parasitics, DC/transient/causal behavior,
radiation, thermal allocation/feedback, measurement and original-board
qualification remain open. EBrake and Marble limits remain in the
[PEEC follow-up](PEEC_REPAIR_FOLLOWUP_20261019.md). Marble was not requalified
by this branch composition. Full repository, installed desktop and release
qualification were not executed by this stage.
