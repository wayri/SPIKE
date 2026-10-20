<!-- SPDX-License-Identifier: Apache-2.0 -->
# SI02-S10 supplied coupled-line cascade verification - 20 October 2026

> **Public evidence boundary:** Paths marked as unbundled local records identify generated developer-run evidence that is not shipped in the public source. The historical observation remains provisional and does not establish release qualification; reproduce and review it before relying on the claim. See the [release local-evidence boundary](RELEASE_040_LOCAL_EVIDENCE.md).

Status: **Done for the bounded experimental development stage**. SI02, full
PI/SI parity, physical board qualification and knowledgeable human numerical
release review remain open. The method retains `production_qualified:false`
regardless of development replay completion. See
[independent derivation, primary sources and limits](../RLGC_COUPLED_CASCADE.md)
and [ADR0120](../adr/0120-supplied-coupled-line-cascades.md).

## Executed evidence

- [Final current source-bound receipt](parity/SI02-S10-final-20261020.json) and
  raw test log (unbundled local record: `parity/SI02-S10-final-20261020.log`): **11 passed, zero
  failures/errors/skips**. All43 distinct bound source hashes agree before/after
  execution and current bytes. Kernel, numerical/contract tests, nested strict
  schemas, actual worker/CLI, example, underlying producers, method and ADR are
  covered. An earlier receipt was superseded by actual execution after resolving
  a concurrent ADR number collision; historical evidence was preserved.
- The independent oracle builds physical self/mutual R/L/G/C matrices and a
  four-state spatial chain using SciPy matrix exponentials. Exterior physical
  V +/- Z0 I equations produce every S column and coherent internal probe V/I
  independently of production modal transforms, scattering connection and scalar
  propagation. V/I and S tolerance:2e-11 absolute plus2e-9 relative.
- Independent physical quadratic integration at32 and64 Gauss points verifies
  each section conductor/dielectric heat separately to2e-12 W absolute plus2e-9
  relative, and confirms quadrature refinement. Ideal interface inward powers
  cancel; heat is counted once without counting nested modal heat again.
- One-section equivalence to the unchanged coupled producer, homogeneous
  subdivision, uncoupled scalar-cascade reduction, zero/scaling, conductor
  permutation and chain reversal pass. Malformed request/identity/reference/grid,
  empty probes, resources, singular/nonfinite connections, cancellation/callback
  errors, forged child identity/interior fields and a false heat split preserving
  total heat all reject. Worker/CLI/example/schema and original digest/no-mutation
  checks execute the public boundary.
- **125 focused regressions passed, zero skips**, in20.299 seconds: loaded SI
  workflow, SI network graph, schema catalog, scalar RLGC network/fields/cascades,
  coupled pair, resistive and reactive physical pair endpoints and their contract
  modules. Raw log:`build/si02-s10-development-20261020/focused-regressions.log`.
- **23 prior numerical stages were genuinely rerun**, totaling**275 test
  executions** with no failures/errors/skips:19 affected shared CLI/worker/catalog
  stages plus SI01-S01 and SI02-S07/S08/S09. New receipt/log names end
  `-coupled-cascade-20261020`; previous evidence is retained. Replay summary:
  `build/si02-s10-development-20261020/prior-replays.json`.
- The separate PI01-S01 geometry envelope also binds the CLI. The original
  owned-mode EBrake CLI and four unchanged mesh levels were actually rerun in
  `build/si02-s10-development-20261020/ebrake-owned-replay`, with stable source
  hashes. Approximate CLI execution completed; the board density gate remains
  **failed_to_converge, can_sign_off=false**. The audit's expected failure is
  preserved. **28 owned-pad tests passed**, with a
  [fresh bounded geometry receipt](parity/PI01-S01-coupled-cascade-20261020.json).
  That geometry pass does not qualify the original board.

Final backlog and candidate/coupled/resistive/reactive/cascade evidence controls
passed **19 tests, zero skips**, in15.625 seconds. Raw log:
`build/si02-s10-development-20261020/tracking-regressions.log`. The68-capability
backlog/evidence checker and architecture boundaries passed.

## Independent review and source lineage

Independent read-only numerical review verified the physical connection,
conditioned solve, energy conservation, section provenance and independent
physical-chain/quadrature oracle. It found one scope-text mismatch: the initial
plan said zero probes could be admitted, while the unchanged child requires1..32.
The implementation's limitations/method now state1..32 and explicitly test empty
probe rejection. The original frozen plan remains preserved; its separate
clarification records this inherited constraint without relaxing numerical gates.

A second independent integration review ran all11 numerical/contract tests
with zero skips, validated the current receipt/source/log bindings and found
no actionable issue. Reviewed kernel SHA-256:
`533c2efa781bfe291f37bf2efd666e6ae47e60074db96afc99d504f5c91fd50a`.
Original pre-implementation acceptance plan:
`build/si02-s10-development-20261020/acceptance-plan.json`, SHA-256
`56b914d2ca414dcf84e3f6c7be558805a3d4c7d336ca7d20b0e05594c736e447`.
Clarification:`build/si02-s10-development-20261020/acceptance-clarification.json`.
Agent review does not replace required knowledgeable human review before release.

## Run and remaining applicability

```powershell
.venv-emerge3/Scripts/python.exe -m python.spike_core.cli --quiet --output build/coupled-cascade-result.json rlgc-coupled-cascade examples/rlgc_coupled_cascade/piecewise.request.json
```

Ports are ordered conductor0-left,conductor1-left,conductor0-right,conductor1-right.
Each frequency is an independent RMS steady scenario. Named sections retain pair
heat ownership for later explicit coupling; no conductor share of mutual heat,
thermal mesh mapping, finite contact area, temperature law or transient heat
history is inferred. Ideal interfaces do not extract bend/via/launch/return-path
parasitics. General asymmetric/noncommuting matrix models, branching, physical
endpoint feedback around a whole cascade, DC/transient/causal behavior, radiation,
measurements and general-board qualification remain open. Original EBrake and
Marble limitations remain in the [PEEC follow-up](PEEC_REPAIR_FOLLOWUP_20261019.md);
Marble was not requalified by this piecewise line composition. Full repository,
installed desktop and release qualification were not executed by this stage.
