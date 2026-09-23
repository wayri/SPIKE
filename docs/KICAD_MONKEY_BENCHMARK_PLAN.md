# KiCad Monkey corpus benchmark plan

## Decision

Use selected, hash-verified **input data** from
[wavenumber-eng/kicad_monkey](https://github.com/wavenumber-eng/kicad_monkey)
to extend SPIKE's importer and geometry-readiness regression evidence.  Do not
vendor or execute its test runner, generators, parser, Rust benchmarks, or
oracle code.  This is a parser/import/geometry corpus only: it is explicitly
not an electrical PI, SI, PDN, thermal, EM, DRC, fabrication, or 3-D fidelity
oracle.

Research snapshot: upstream `main` resolved to
[`bc6796c1b8ce55bfbcb8b1771f3ecbc70658d34d`](https://github.com/wavenumber-eng/kicad_monkey/tree/bc6796c1b8ce55bfbcb8b1771f3ecbc70658d34d)
on 2026-09-20.  Every upstream link below is pinned to that revision.

## What is available upstream

The repository is MIT licensed ([LICENSE](https://github.com/wavenumber-eng/kicad_monkey/blob/bc6796c1b8ce55bfbcb8b1771f3ecbc70658d34d/LICENSE)).
That permits copying its authored test metadata and synthetic fixtures when
the copyright/permission notice is retained.  It does **not** establish a
license for every board embedded in the separate corpus archive.  Upstream
also calls the archive a test/review asset, excludes it from sdists, and
requires its hash before use ([corpus README](https://github.com/wavenumber-eng/kicad_monkey/blob/bc6796c1b8ce55bfbcb8b1771f3ecbc70658d34d/tests/corpus/README.md)).

The archive descriptor is concrete but deliberately large:

| asset | size | immutable identity | recommended SPIKE use |
| --- | ---: | --- | --- |
| `tests/corpus/kicad.zip` | 266,556,039 bytes | SHA-256 `12a23e9849579198395a2a0d58aa8d8c368f08d6fa9612fb9439d765255e8b71` ([manifest](https://github.com/wavenumber-eng/kicad_monkey/blob/bc6796c1b8ce55bfbcb8b1771f3ecbc70658d34d/tests/corpus/kicad.archive.toml)) | Optional, external developer/CI cache only; never commit, package, or silently fetch. |
| small footprint | 7,977 bytes | `common/complex_hierarchy/input/complex_hierarchy.pretty/CP_Axial_L11.0mm_D6.0mm_P18.00mm_Horizontal.kicad_mod`, SHA-256 `b515e3d5a18e3a67c6c01ac82a77ea1b6e1d77005270a6be9b451e4083ddcd90` | fast footprint/parser smoke test only. |
| medium schematic | 996,306 bytes | `board_svg/input/speedy/ZYNQ_CONFIG.kicad_sch`, SHA-256 `0a2015aad423ba54940b706dbaf3f7659131c2bc73b8131bfc47729e0b6e700e` | schematic importer/read-path benchmark. |
| large PCB | 71,556,836 bytes | `common/vme-wren/input/vme-wren.kicad_pcb`, SHA-256 `98bb12606c3798d10dc5c9713c8d4a2a3338768eacfe80a431397686efd2ee42` | opt-in large-board import, memory, and geometry-extraction benchmark. |

The three named files, their operation set (`parse`, `roundtrip`), and the
upstream cross-platform-pending status are defined in
[`sexpr_corpus_cases.toml`](https://github.com/wavenumber-eng/kicad_monkey/blob/bc6796c1b8ce55bfbcb8b1771f3ecbc70658d34d/tests/performance/sexpr_corpus_cases.toml).
Their status is measurement, not a published threshold.  Preserve that
distinction in SPIKE reports.

## Reusable test matrix

| lane | inputs | SPIKE operation and assertions | evidence |
| --- | --- | --- | --- |
| unit / always-on | SPIKE-owned tiny boards plus the upstream small footprint only if separately reviewed | bounded parse; deterministic normalization; no crash; object type/count invariants | input SHA-256, parser/importer version, elapsed time |
| importer compatibility | reviewed corpus PCB/schematic subset | CLI/worker import to `DesignIR`; diagnostics bounded; save/reopen count and identifier invariants | per-input provenance record and source/normalized counts |
| geometry readiness | PCB subset including large board only in opt-in lane | extract layers, nets, pads, tracks, arcs, vias, zones, board outline; validate finite coordinates and references; record unsupported features | extraction counts, warning/error taxonomy, peak RSS, timeout |
| round-trip preservation | selected text inputs | import/export/import structural comparison, with explicit tolerated normalization rules | source and output hashes, changed categories, not byte identity |
| performance / nightly | the named small/medium/large cases, plus SPIKE synthetic stress boards | cold/warm process-inclusive import and geometry timings, 3+ runs, median and peak RSS; advisory until multiple-host baselines exist | host/OS/CPU, dependency and executable hashes, raw samples |
| malformed/security | SPIKE-authored truncated, huge-count, nesting, and invalid-coordinate cases | reject safely under resource budgets; no network or code execution from fixture | exit status, diagnostic code, wall time and memory cap |

For semantic shape, the upstream corpus's parser-only flow is
`lex -> tree -> build -> reparse -> compare`
([L1_018](https://github.com/wavenumber-eng/kicad_monkey/blob/bc6796c1b8ce55bfbcb8b1771f3ecbc70658d34d/tests/L1_parsing/test_L1_018_corpus_sexpr_passthrough.py)).
SPIKE should report equivalent phases separately, so importer/geometry
failures cannot masquerade as syntax failures.  Its projection comparison
also supports useful non-physics invariants: compare collection counts, pad
and model-reference counts, and representative layer/net/coordinate fields
([L1_020](https://github.com/wavenumber-eng/kicad_monkey/blob/bc6796c1b8ce55bfbcb8b1771f3ecbc70658d34d/tests/L1_parsing/test_L1_020_pcb_projection_corpus.py)).

## Acquisition, license, and provenance rules

1. Keep upstream data outside Git and installers (for example,
   `build/external-corpora/kicad-monkey/<archive-sha256>/`).  Fetch only after
   an explicit developer/CI action; the default test suite must skip cleanly
   when it is absent.
2. Before extraction, check archive byte count and SHA-256.  Extract into a
   newly-created, content-addressed directory; reject absolute paths, `..`,
   symlinks escaping the root, and duplicate/colliding names.  Treat fixtures
   as data: do not run bundled scripts, macros, plug-ins, or external model
   files.
3. A SPIKE manifest must pin: upstream repository URL, commit above, archive
   URL, archive SHA-256, selected relative path, selected-file SHA-256 and
   bytes, retrieval time, license review status, and the copied license/notice
   location.  Hash the exact bytes actually passed to the importer.
4. Do not redistribute a corpus member until its own provenance/license is
   documented and approved.  The repository-level MIT license applies to
   Monkey software, not automatically to third-party hardware designs.  If
   that evidence is unavailable, allow local opt-in testing only and mark the
   result `redistribution_approved: false`.
5. SPIKE-authored synthetic inputs are preferable for committed regression
   fixtures.  Upstream synthetic generators are MIT-covered but should be
   copied as data only after attribution review, or independently reimplemented
   from the desired feature specification.  They use stable UUIDv5 fixture
   identities and a `input/reference_output/output` layout
   ([common helper](https://github.com/wavenumber-eng/kicad_monkey/blob/bc6796c1b8ce55bfbcb8b1771f3ecbc70658d34d/scripts/synthetic_corpus/common.py)).

## SPIKE integration point

SPIKE already has the appropriate bounded, data-only pattern in
[`scripts/benchmark_board_corpus.py`](../scripts/benchmark_board_corpus.py):
it validates relative `.kicad_pcb` paths, SHA-256, a 128 MiB input ceiling,
and executes the SPIKE importer in a timed subprocess.  Its existing public
board-corpus report correctly says the input corpus is not a complete CAD or
solver-parity qualification ([report](../benchmarks/public-board-corpus/REPORT.md)).

Extend that script or factor its validation into a shared helper; do not use
the upstream Rack runner.  Add a dedicated manifest such as
`benchmarks/kicad-monkey-corpus/manifest.json` with `enabled: false` by
default.  Make the existing 128 MiB ceiling an explicit per-lane policy:
retain it for standard import runs, and permit the 71.6 MB VME-WREN case only
with `--allow-large-corpus` plus a configurable timeout/RSS limit.  Preserve
fresh output directories and per-fixture JSON evidence.

Suggested result schema additions are `upstream_commit`, `archive_sha256`,
`fixture_sha256`, `fixture_bytes`, `license_review`, `phase`, `cold_samples_ns`,
`warm_samples_ns`, `median_ns`, `peak_rss_bytes`, `geometry_counts`, and
`unsupported_feature_codes`.  Capture SPIKE executable/package hashes and
host information as upstream does in its
[performance provenance helper](https://github.com/wavenumber-eng/kicad_monkey/blob/bc6796c1b8ce55bfbcb8b1771f3ecbc70658d34d/tests/support_scripts/performance_provenance.py).

## Boundaries and promotion

Passing this plan demonstrates only that SPIKE can ingest the exact bounded
file and produce internally consistent normalized geometry under the recorded
resource limits.  It does not prove net connectivity correctness, copper-area
or curve equivalence, clearance/DRC results, stackup material accuracy, field
solutions, impedance, PI/SI/crosstalk, thermal behavior, manufacturing
readiness, or viewport/3-D pixel equivalence.

Start with advisory measurements.  Promote an invariant to a blocking gate
only after (a) per-fixture license review, (b) stable expected behavior across
at least Windows and Linux, (c) recorded resource budgets with headroom, and
(d) an explicit review of tolerated-format normalizations.  The upstream
large-corpus performance test itself calls its measurements advisory and keeps
threshold ratification pending across platforms
([L1_023](https://github.com/wavenumber-eng/kicad_monkey/blob/bc6796c1b8ce55bfbcb8b1771f3ecbc70658d34d/tests/L1_parsing/test_L1_023_rust_corpus_performance_memory.py)).
