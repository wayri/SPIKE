<!-- SPDX-License-Identifier: Apache-2.0 -->
# SI02-S13 physically loaded coupled-star verification — 21 October 2026

> **Public evidence boundary:** Paths marked as unbundled local records identify generated developer-run evidence that is not shipped in the public source. The historical observation remains provisional and does not establish release qualification; reproduce and review it before relying on the claim. See the [release local-evidence boundary](RELEASE_040_LOCAL_EVIDENCE.md).

Status: **Done for the bounded experimental development stage**.
The capability remains experimental with `production_qualified:false` regardless
of replay completion. SI02, full PI/SI parity, physical board qualification and
knowledgeable human numerical release review remain open. See
[independent method and sources](../RLGC_LOADED_STAR.md) and
[ADR 0124](../adr/0124-physical-rlc-loaded-coupled-stars.md).

## Executed evidence

- [Source-bound receipt](parity/SI02-S13-qualified-20261021.json) and
  raw log (unbundled local record: `parity/SI02-S13-qualified-20261021.log`): **13 passed, zero
  failures/errors/skips**. All 87 distinct bound source hashes match current
  bytes and before/after execution, including the boundary-integrity repair,
  constituent methods, own numerical/contract tests, strict schemas, actual
  worker/CLI/example, references and ADR. No hash-only evidence refresh.
- An independent physical 4m spatial RLC endpoint/node-KCL system verifies
  terminal and internal fields, source current, signed source/line complex work,
  mean L/C energies and resistor heat. It uses only the earlier independent
  oracle's physical coefficient assembly and discards its zero-drive solution.
  Production wave/node/modal feedback is not the reference calculation.
  Tolerances: V/I 2e-11 absolute plus 2e-9 relative; power/heat 2e-12 absolute
  plus 2e-9 relative; mean energy 2e-20 J absolute plus 2e-9 relative.
- Independent physical 32/64-node quadratic integration verifies each branch's
  conductor/dielectric heat split and reference quadrature refinement. Terminal
  and branch heat are counted once; mean J and reactive var are not heat W.
- Two legs agree with S11 physical cascade endpoints. Matched resistive sources
  reproduce the prescribed-wave star. Zero/scaling, record/leg/conductor
  permutations, absorbing sources, large storage versus heat and actual eight-leg
  physical operation pass. Strict branch-dependent dimensions validate both
  two- and eight-leg requests/results and reject missing source/terminal data.
- Malformed identity/reference/grid/ports/reactives, resources, ill conditioning,
  1e308 representability, cancellation/callback failure, nested digest/network/
  interior-field/heat/node/order corruption all reject. Actual worker, CLI,
  saved example, schemas and request/digest no-mutation checks pass.
- **173 focused regressions passed, zero skips**, in 31.130 seconds: SI workflow,
  network graph, schema catalog, scalar RLGC network/fields/cascades/stars,
  coupled pairs and resistive/reactive/cascade/star workflows with their contract
  modules. Raw log:
  `build/si02-s13-development-20261020/focused-regressions.log`.

- **26 prior numerical stages genuinely reexecuted**, totaling **308 test
  executions**, zero failures/errors/skips: 19 affected shared CLI/worker/catalog
  stages plus SI01-S01 and SI02-S07 through SI02-S12. Fresh receipt/log names
  end `-loaded-star-20261021`; historical receipts remain unchanged. Summary:
  `build/si02-s13-development-20261020/prior-replays.json`.
- The original owned-mode EBrake CLI and all four unchanged mesh levels ran with
  stable source hashes in
  `build/si02-s13-development-20261020/ebrake-owned-replay`. Approximate CLI
  execution completed, but density remains **failed_to_converge,
  can_sign_off=false**. Its failure is preserved. **28 owned-pad checks passed**,
  with a [fresh bounded geometry receipt](parity/PI01-S01-loaded-star-20261021.json).
  Geometry verification does not qualify EBrake or repair its AC gates.

Final backlog and separate stage-evidence corruption controls passed **22 tests,
zero skips**, in 17.658 seconds. Raw log:
`build/si02-s13-development-20261020/tracking-regressions.log`. All 68 capability
coverage/source-bound checks and architecture boundaries pass. The reference
inventory is regenerated and checked for the final shared-tree snapshot.
[Progress and remaining goals](../PI_SI_PROGRESS_20261021.md) distinguishes
bounded stage completion from family and board qualification.

## Standing-wave integrity correction and independent review

A valid almost-zero branch current originally failed the relative-only S08
physical-boundary reconstruction check. Preserve its 1e-9 relative criterion and
add only 64*float64.eps times the local V/I wave-operand scale at physical
boundaries. Strict modal-network/interior checks, raw physical values, all heat,
power, KVL, conditioning and board gates remain unchanged. The physical oracle
verifies the retained counterexample; native-float false current at 1e-10 of its
local operand scale is rejected specifically by field-integrity validation.
Direct tests also distinguish permitted eps-scale error from rejected 1e-10-scale
error at three amplitudes. No fixture or convergence threshold was changed to
hide the case.

Independent Astra numerical review derived the variable-port feedback and checked
the allowance's units/limits. It independently ran all nine numerical tests,
checked additional seeded 2–8-leg cases and the physical counterexample, and
rejected targeted near-node/endpoint forgeries. Review found no blocker within
scope. The paper supports operand-scaled cancellation reasoning, not factor 64
for the full two-path reconstruction. Upstream remote operands can exceed the
local scale; conservative rejections can remain. This is an implementation
allowance, not a universal forward-error certificate or near-zero relative-
accuracy claim. Final independent integration review ran all 13 tests with zero
skips, verified the 87-source/log-bound receipt and found no actionable issue.

Kernel SHA-256: `b0442475a02d74443eea0132d9440be40f0c03e00dd4f9432d8b57a8566311d7`.
Repaired S08 helper SHA-256: `d272b08dc6a16669b5f155d76fe751cb7c3655be37e5977643dddeba65fb1155`.
Frozen plan: `build/si02-s13-development-20261020/acceptance-plan.json`, SHA-256
`6d0e56b5ce77fdc3207aa27ab27dc13f33797d39b457525da619b2cb339e02c8` (work began before local midnight; final qualification is dated 21 October).
Agent review does not replace required knowledgeable human numerical release
review. No independent measurements or performance-parity claim.

## Run and remaining applicability

```powershell
.venv-emerge3/Scripts/python.exe -m python.spike_core.cli --quiet --output build/loaded-star-result.json rlgc-loaded-star examples/rlgc_loaded_star/physical.request.json
```

Exterior ports follow leg then conductor order. Zero source voltage denotes an
inactive but explicitly RLC-loaded terminal. Positive frequency rows are separate
RMS steady scenarios, without automatic summation or transient heat histories.
Terminals/legs own their lumped/pair heat; no mutual-term conductor share, finite
contact, thermal cell or temperature law is inferred. General graphs/asymmetry,
piecewise legs, geometric junction/contact/return parasitics, ideal open/short,
nonlinear/lossy/frequency-dependent endpoints, DC/transient/causal behavior,
radiation, thermal mapping/feedback, measurements and original-board qualification
remain open. EBrake/Marble limitations remain in the
[PEEC follow-up](PEEC_REPAIR_FOLLOWUP_20261019.md). Marble was not requalified
by this workflow. Full repository, installed desktop and release qualification
were not executed by this stage.
