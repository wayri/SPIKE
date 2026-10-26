# IBIS and spatial SI source verification - 25 October 2026

## Scope and status

This record covers a separate experimental classic IBIS driver/Input receiver
workflow and sampled SI visualization in the main single-board 3D viewport.
It does not close arbitrary-board extraction, general assembly multiphysics,
USB/Ethernet compliance, measurement correlation or release qualification.
The independent [derivation and bounded review](IBIS_DRIVER_RECEIVER_DERIVATION_20261025.md)
preceded physics implementation. Review identified and corrected mandatory
runtime-hash admission and a direct capacitive derivative-defect screen.

## Executed source checks

| Check | Actual result |
| --- | --- |
| IBIS compiler, inventory and execution boundary | 24 tests passed |
| Public worker dispatch and native opt-in rejection | 3 tests passed |
| Current spatial context, actual phasor mapping, revision/geometry rejection | 5 tests passed |
| Existing loaded SI workflow | 23 tests passed |
| Existing coupled-pair physical/reference tests | 11 tests passed |
| Existing coupled-pair worker/CLI/schema contracts | 3 tests passed |
| Spatial frontend model, controls, stale/unmount and explicit-run interactions | Node test passed |
| TypeScript | `tsc --noEmit --incremental false` passed, 1536 MiB heap limit |
| Architecture guard | Passed |
| Shared control standard | Passed for desktop and 23 previews |
| README and changed public Markdown | 11 files passed documentation checker |
| Original spatial example reproduction | Generated canonical design, complete setup, three-field solver draft, actual sample data and full evidence |

The first combined Python run was interrupted when the restricted CLI subprocess
stopped producing output. A fresh 66-test in-process run passed in 1.060 s; the
same three CLI/schema tests passed separately with repository write access in
2.384 s. This is 69 focused tests, not a complete repository test-suite result.
No native application screenshots, installed lifecycle, Linux/macOS execution,
new installer build or full-suite run was performed in this increment.

## Actual supervised IBIS execution

Two tiny original synthetic fixture runs completed using the existing bundled
ngspice executable. Its SHA-256 is
`86c9ea5f645ca919e305639fa7bdb522355364c424d14e197f1ade617feb3453`.
Runtime version was not independently queried and is recorded as unknown.
Windows Job Object enforcement was established; each run retained the 30 s,
512 MiB and 4 MiB admission limits. The engine completed to 15 ns with return
code zero and accepted die-voltage domain checks.

| Maximum time step | Admitted accepted-time samples | Engine elapsed |
| --- | --- | --- |
| 20 ps | 1389 | 0.406 s |
| 10 ps | 2057 | 0.078 s |

Linear comparison of the refined trace onto coarse accepted times gave:

| Probe | Maximum absolute change | Predeclared 0.5 mV voltage criterion |
| --- | --- | --- |
| Driver pin voltage | 0.698400 mV | Not met |
| Receiver pin voltage | 0.686556 mV | Not met |
| Driver die voltage | 0.515209 mV | Not met |
| Receiver die voltage | 0.385620 mV | Met for this comparison |
| Driver package current | 14.6367 microampere | No current criterion claimed |

**Convergence qualification remains open.** Do not weaken the criterion to
promote a smoke run. This is not extraction-fixture replay, a withheld-load test,
manufacturer-model validation or measured correlation. The source fixture has
zero driver die capacitance and zero clamp curves; separate arithmetic tests
exercise nonzero capacitance, signed tables and rejection paths. Broader actual
engine behavior remains to be qualified.

The compact [execution receipt](../../examples/si/ibis_driver_receiver/execution_evidence.json)
retains model/request/deck/raw/log hashes, budgets, probe ranges and the explicit
open convergence decision. The [spatial example](../../examples/si/spatial_crosstalk/README.md)
retains its supplied-RLGC scope and actual sampled RMS victim voltages; it
contains no surrounding E-field or fabricated spatial halo.

## Remaining acceptance

Native wide/narrow visual interaction and save/reopen qualification remain open.
Drafts/samples are session-local and explicitly exportable. Multi-board
transformed spatial overlays are unsupported. Real-model applicability,
withheld-load/fixture replay, strict timestep convergence, runtime/version
qualification and knowledgeable human numerical approval remain required.
No release was published and no installed application was changed here.
