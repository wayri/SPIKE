# Stability, qualification, and release work plan — 2026-09-05

This is a reconciliation checkpoint for the current working tree, not a release
approval. Preserve concurrent changes and validate the integrated tree before
packaging. Desktop 0.2.5 and the independently versioned SPIKES engine are distinct
products. Existing licensing terms are unchanged.

## Completed stability repairs in this checkpoint

| Failure | Cause and implemented repair | Evidence |
|---|---|---|
| Arbitrary-board 3D scenes rejected as VRML | Verified GLB bundles use extensionless `blob:` URLs. Dispatch now defaults board scenes to GLTFLoader; explicitly named WRL/VRML uses the legacy loader. | Real Three.js GLB Blob parse in `app/scripts/test-model-scene-loader.mjs` |
| Imported board inherits another package on Save As | Successful import now clears prior package identity and board-bound assembly/model/results/thermal/SI state. Missing lossless base still fails closed. | Frontend package regression; worker missing-base test |
| Save rejects embedded source digest on Windows | Text-mode temporary writes changed newlines; importer now hashes the exact UTF-8 bytes embedded in the package. | LF, CRLF, Unicode worker tests; two public-board round trips |
| Two-layer nets report three copper layers | `*.Cu` was counted as a physical layer. Shared resolver expands it to the physical stack; `F&B.Cu` expands only to front/back. | 2/10/32-layer inventory tests |
| Diagnostic warnings wrap one character per line | Header flex selector overrode the warning-list grid. Cards now occupy full-width rows with a separate full-width message. | Diagnostic CSS regression; pixel acceptance pending |
| High-part-count model completion scales quadratically | Each component rescanned all picking objects. Component lookup and replacement now use indexed lookup and one partition pass. | 100,000 proxies / 10,000 components inspected once each |

Public corpus sources, fetched 2026-09-05 into a local `.tmp` cache:

- [OLIMEX MOD-OLED-128x64](https://github.com/OLIMEX/MOD-OLED-128x64):
  `olimex-oled.kicad_pcb`, 78,814 bytes, SHA-256
  `405a8ba55bafc8fe75c60eabb1fccf36e216080077f1e4d93f74799718eed703`.
- [Raspberry Pi RP2040 minimal design](https://www.raspberrypi.com/documentation/microcontrollers/microcontroller-chips.html):
  `RPI-RP2040-MINIMAL_R3-S1.kicad_pcb`, 1,435,209 bytes, SHA-256
  `f6c8e633a567ca884b269dc7ec934bebbce28534d0fdb84623a007840a01a471`.

Both pass canonical import/save/lossless-Save-As/reopen with identical DesignIR
and embedded source. Reproduce with `python scripts/check_board_corpus_roundtrip.py
<board1.kicad_pcb> <board2.kicad_pcb>`. Inputs remain third-party materials;
they are not copied into the product distribution or relicensed. These checks
do not execute physics or establish viewport/3D-model completeness.

The separate frontend parser corpus check (`app/scripts/check-board-corpus.mjs`)
passes both inputs: OLED 2 copper / 20 drawable layers, 16 components, 191 tracks,
65 pads; RP2040 2 copper / 20 drawable layers, 34 components, 313 tracks, 219 pads.
Observed parse times were approximately 9 ms and 70 ms on this runtime; these
are parser-only observations, not end-to-end load or frame-rate benchmarks.

## Historical intermediate verification snapshot

Superseded for the supported Windows runtime by the
[0.2.6 verification record](RELEASE_0_2_6_VERIFICATION.md): 1,349 Python tests
run with no failures/errors and one skip, 42 frontend suites and 29 host tests
pass. MSI/NSIS packages are built. Local upgrade waits for the user to save and
close the running 0.2.5 app; interactive and high-density qualification remain open.

- TypeScript and Vite production build pass; Vite still warns about large chunks.
- Focused model/layer/parser/project/diagnostic/viewport regressions pass.
- Worker protocol: 19 tests pass in the focused run; later added source-byte
  regression also passes and is included in broad discovery.
- Focused analytical/SI/thermal validation: 24 tests pass.
- CLI benchmark report `build/solver-benchmarks-stability-20260905.json`: 15/15 pass.
- Full Python discovery: **1,303 tests, 1 failure, 38 errors, 10 skips** (334 s).
  The observed blockers match the prior baseline: missing optional `pyarrow`,
  stale native PEEC module without `canonicalize_planar_region`, and native
  session ABI lacking `session_element_voltage_available`. This is not a green
  release baseline; rebuild/qualify the intended dependency/native runtime.
- Architecture guard fails on spread extrema in `EmiFieldPlots.tsx`,
  `schematicGeometry.ts`, `topologyGeneration.ts`, and the 830-line `powerTree.ts`.
  These are integration findings in separately edited files, not waived checks.
- Browser preview starts, but two file-chooser attempts did not load a design.
  Native dialogs, rendered-board pixels and layer-toggle acceptance remain open.

## Wave assessment and completion criteria

The original numbered wave plan remains the sequencing authority. The user's
split-gate decision allows Wave 1 functional sequencing to close separately from
release qualification. Regression fixes reopen affected acceptance checks.

| Wave | Evidence-backed status | Required closure |
|---|---|---|
| 0 stability/contracts | Core package/UI paths implemented; the defects above demonstrate incomplete acceptance | Public corpus, native dialog/restart, all layer toggles, large-scene frame/memory/cancellation tests, green or explicitly quarantined integrated baseline |
| 1 CAD/assembly/MCAD | Functional sequencing previously closed; DesignIR/AssemblyIR/package/MCAD paths exist | Revalidate arbitrary-board visuals and deterministic mixed-assembly reopen; retain separate legal/install/pixel acceptance |
| 2 geometry/mesh | Exact and conformal slices exist; arbitrary geometry coverage remains incomplete | Custom pads, thin conductors, ownership/connectivity, all required mesh families, adaptive/conservative transfer and resource evidence |
| 3 PI/circuit | Useful bounded DC/PEEC/circuit workflows; release gate remains unqualified | Six workflow-specific independent/measured validations plus native-path and packaging evidence; no automatic promotion from unit tests |
| 4 thermal | Real synthetic solid-vacuum and PCB/package/contact/air v2606 runs; candidate energy/convergence evidence | Representative enclosure/fan/potting/radiation/CHT/electrothermal; native path, independent/measured correlation and exact packages |
| 5 multiboard | Assembly structures/harness contracts exist; full coupling unqualified | Numerically executed port/launch/return/shield/mutual binding, 2/5/20-board coupled PI/thermal then SI fixtures |
| 6 SI | Bounded loaded/uniform/coupled channel paths and editors exist; arbitrary signoff unqualified | DDR/SerDes/LVDS end-to-end first; arbitrary discontinuities, driver models, correlated BER/jitter/equalization/protocol evidence |
| 7 pre-EMI release | Open | All prior numerical, scalability, security, licensing, Windows/Linux and clean-machine gates |

Do not advance production EMI physics while pre-EMI qualification remains open.
Shared dashboard/report infrastructure can be implemented without adding physics
claims. This checkpoint is not an exhaustive line-by-line audit of every solver.

## Ordered implementation backlog from the latest request

| ID / priority | Deliverable and acceptance |
|---|---|
| S1 / immediate | Complete arbitrary-board 2D/3D import/open/save/save-as/restart tests; board/material/models independent from layer toggles; 2/10/32 layers and high part count |
| S2 / immediate | Reproduce custom-pad/thin-net failures from exact requests; preserve geometry ownership, classify unsupported shapes, fix translator/mesher rather than bypass validation |
| S3 / immediate | Non-obscuring net preview; compact grouped source/load tables; batch cancellation/progress/result identity; useful selection context actions |
| S4 / immediate | Unified object/board/frame probe selection linking PI/SI/thermal/EMI viewport, tables, plots and offline interactive reports |
| E1 / next | Reconcile concurrently edited topology studio; editable sequence text, table editor, symbols and per-port help; one canonical topology underneath all views |
| E2 / next | SOURCE:U1.1 -> R1 -> SINK:J2.1 parser; infer passive terminals only when unambiguous, require directional device pin semantics; span diagnostics, undo/redo, autocomplete and incremental highlighting |
| E3 / next | Bus expressions such as DDR_ADD[1:3] -> U8[4:5,8]; deterministic expansion, explicit lane/pin cardinality and clock/timing columns; no implicit Cartesian wiring |
| E4 / next | Protocol-specific auto-generation from real connectivity with reviewable unresolved pins; DDR/SerDes/LVDS before additional named protocols |
| E5 / next | Touchstone import/export/generation with port/order/units/reference validation; BSIM/IBIS/SPICE and driver/sink files retained with provenance and capability-checked execution |
| R1 / next | Shared domain-aware live dashboards: plots/cursors, metric tables, bounded refresh, frame selection, saved report selections, exact units and coordinate provenance |
| R2 / next | Static and interactive offline reports; company logo/header/footer settings; image/file sanitization, print layout, cross-highlighting, package persistence/reopen |
| H1 / next | Optional guided tours and block/workflow help; all newly saved editor, model, report and tour settings round-trip through native packages |
| Q1 / release | Analytic/independent/measured benchmark ladder below; broad public corpus and packaged pixel checks |
| D1 / release | Curated repository map, API/architecture/math/user/extension docs, runnable examples and real screenshots; no destructive reorganization of historical/concurrent work |
| L1 / release | Owner selects distribution model after ownership/dependency review; exact licenses/notices/SBOM/signatures/Windows/Linux installer and rollback evidence |

For large scenes record hardware/runtime, source digest, part/net/layer counts,
cold/warm load, p50/p95 frame latency during interaction, idle work, peak memory,
draw calls, triangle/sample counts and cancellation latency. The 20-board,
1 m x 1 m, thousands-of-components target is a required fixture, not a tested
capacity claim. Million-point fields need chunked storage/transfer and bounded
display sampling that preserves complete solver/export data.

## Benchmark ladder and mathematical documentation

Run existing `python -m python.spike_core.cli --output <report.json> benchmark`
and focused SI/thermal tests as implementation verification. Preserve their
actual tolerances and limitations in the report. Expand with:

| Domain | Analytic fixture / observable | Further validation |
|---|---|---|
| PI DC | Uniform conductor R=L/(sigma*A), V=IR; via/contact chains; KCL/KVL residuals | Geometry/mesh refinement and independently solved/measured coupons |
| PI AC/transient | Passive RLC circuits, known poles/time constants, multiport impedance | Independent MNA/SPICE plus calibrated PDN measurement with de-embedding |
| SI | Uniform line Z0=sqrt((R+jwL)/(G+jwC)), gamma=sqrt((R+jwL)(G+jwC)); matched/open/short responses | Frequency/time-step convergence; passivity/causality/reciprocity; calibrated VNA/TDR and eye measurements |
| Thermal solid | Slab deltaT=Q*L/(k*A); lumped thermal RC where its assumptions apply; contact drop Q*Rcontact | Spatial/time refinement, energy balance, independent FEM and instrumented assemblies |
| Thermal radiation/CHT | Radiation balance epsilon*sigma*A*(T^4-Ta^4); bounded duct/plate cases with explicit regime | Coupled regional flux cancellation, mesh/time sensitivity, fan curves and measured enclosure correlation |

For each case record assumptions, units, boundary/initial conditions, dimensional
analysis, discretization, matrix assembly, conservation residual, convergence,
reference provenance/uncertainty and validity limits. Analytic agreement is not
measured correlation. Do not copy another program's implementation; use primary
published derivations/standards with attribution and independently written code.

Thermal evidence from the preceding checkpoint remains in
`validation/openfoam-v2606-board-package-contact-cht-synthetic-candidate.json`:
0.0566% synthetic energy residual, three mesh levels and three time steps. It
does not qualify arbitrary PCB CHT, active fans, or commercial signoff.

## Release and documentation organization

Retain [ARCHITECTURE.md](../ARCHITECTURE.md) as runtime authority,
[SUBSYSTEM_INDEX.md](SUBSYSTEM_INDEX.md) as ownership map,
[SOLVER_STATUS.md](SOLVER_STATUS.md) for executable scope, and
[VALIDATION_PROGRAM.md](VALIDATION_PROGRAM.md) for evidence tiers. The canonical
architecture diagram is maintained in ARCHITECTURE.md; use extension and solver
plugin documentation for process/contract detail rather than duplicating them.

Prepare two distribution plans without changing licenses yet: an explicitly
licensed open-source distribution with a support/services business, or a
commercial desktop/SDK distribution with reviewed third-party boundaries.
The current mixed-license policy and prior grants remain authoritative. Owner
and legal approval are required before choosing licenses, publishing, or making
redistribution claims. Preserve process isolation for external solver adapters;
it is not itself evidence of license compliance.

Before release: reconcile all source changes; freeze input/solver/build digests;
execute the full suite and standard benchmarks; publish failure/validity ranges;
complete exact package SBOM/notices/signing and clean Windows/Linux install,
upgrade, rollback and uninstall tests. Do not install this intermediate slice
over the user's current app merely because the web build passes.
