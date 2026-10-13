<!-- SPDX-License-Identifier: Apache-2.0 -->
# Engineering review, BoM and quick tools

Open **Tools → Engineering review · BoM, checks & quick tools**. Run review
against the currently loaded board or all available assembly board occurrences.
Repeated design references remain separate occurrences. Review is read-only.

## BoM and analytics

The workspace provides component search, paged rows, occurrence-scoped grouped
BoMs, DNP filtering of fitted totals, and staged component cost/currency,
mass (g), power (W) and population overrides. Run again after staging an edit.
Missing values remain unknown; a known subtotal is not a complete assembly total.
Currencies are kept separate. Costs and totals use bounded decimal arithmetic.
Declared component power is metadata, not an electrical or thermal solve.

Export BoM CSV for all components or **Export evidence** for the complete input
snapshot, overrides, groups, findings, coverage and result digest. CSV cells
that could be interpreted as spreadsheet formulas are neutralized. Staged fields and completed review evidence are saved inside `.spike` under
`analysis.engineering_review` with the `spike/engineering-review-workspace/v1`
contract. Overrides are bound to a SHA-256 fingerprint of the normalized board
occurrences. Reopening restores staging only for the same source snapshot.
Use **Run review** to refresh saved totals and checks through the managed worker;
archived totals are never displayed as current results. Changed sources leave
old evidence inactive. Saving a project copy without results retains staged fields
and removes the completed review result. There is no native board synchronization
or procurement lookup.

## Checks

Contextual diagnostics identify duplicate references within an occurrence,
missing references, footprints, manufacturer part numbers and absent physical
stackup metadata. These are not KiCad DRC/ERC, manufacturing tolerance checks,
exact solid collision tests or an engineering release pass. Those checks remain
explicitly unknown in this result; the absence of findings cannot qualify a board.
Review requests admit at most 30 boards, 20,000 components and 8 MiB of JSON.

## Quick tools

Explicit SI inputs drive three independently authored analytical calculators:

- Unloaded ideal resistor divider: output voltage, current and resistor powers.
- Ideal RC charging step from zero volts: time constant, voltage and current.
- Uniform rectangular DC trace resistance with supplied bulk resistivity.

Each result includes units, input digest and applicability. These calculators
exclude geometry-dependent field effects and cannot replace PI/SI/thermal studies.
They execute through the same managed worker boundary as the CLI.

Quick-tool requests put the named inputs directly beside `contract` and `tool`:

```json
{"contract":"spike/quick-engineering-tool-request/v1","tool":"resistor_divider","vin":"5","r_top_ohm":"10000","r_bottom_ohm":"10000"}
```

```powershell
.venv/Scripts/python.exe -m python.spike_core.cli engineering-review --request review.json
.venv/Scripts/python.exe -m python.spike_core.cli quick-tool --request calculator.json
```

Worker methods are `review_engineering` and `quick_engineering_tool`, both with
`params: {request: ...}`. Request contracts are
`spike/engineering-review-request/v1` and `spike/quick-engineering-tool-request/v1`.
Engineering review contains `boards: [{occurrence_id, design}]` and `overrides`.
Overrides target exact occurrence/component IDs. Null removes declared numeric
values; cost and currency must be supplied together or both cleared.

## Integration coverage and remaining work

The documentation-only capability inventory identified these useful workflows:

| Workflow | Current integration |
| --- | --- |
| BoM grouping, population and quantitative coverage | Implemented as described above |
| Manufacturing and native DRC/ERC evidence gates | Contextual checks only; native evidence ingestion pending |
| Mechanical collision/clearance and waivers | Pending; no pass implied by rendering |
| PI/SI/thermal, RLC and return-path tools | Existing SPIKE analysis workspaces; not transplanted engines |
| Pin tables, signal paths, controller maps and bring-up packages | Existing connectivity surfaces; richer exports pending |
| Copper-density diagnostics | Pending |
| Native field synchronization, variants, assembler templates and sourcing | Pending |
| Fanout, via stitching and bulk board label mutation | Pending reviewed mutation contracts |
| Ordered checks and analysis jobsets | CLI operations available individually; unified evidence pipeline pending |

This is partial integration, not feature parity with the source application.
Local source application documentation was inspected for behavior and licensing;
its implementation was not read or copied. Original SPIKE code remains Apache-2.0.
GPL components are not linked or transplanted. MIT component availability does
not override the repository clean-room implementation policy.

## Verification

Nine focused backend/service/CLI tests cover grouping, occurrence identity,
DNP and coverage, invalid and oversized inputs, clearing fields, exact decimal
subtotals and analytical calculators. An isolated browser fixture uses cached
actual backend outputs to check BoM presentation, filtering, calculator units,
stale-result invalidation and Escape dismissal. It does not execute a native
worker. Recreate it with `scripts/prepare_engineering_review_preview.py`, then
open `engineering-review-preview.html` through the Vite development server.
Native installed-window verification and release packaging remain pending.

Project persistence additionally has focused frontend checks for canonical scope
fingerprints, changed-source isolation, bounded admission and result-free exports,
and a native package save/open/save-as regression retaining scoped overrides and
complete decimal-valued review evidence. These are file/contract tests, not an
installed-window acceptance check.
