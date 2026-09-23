# SPIKE 0.2.10 — portable project state and local deployment

Date: 2026-09-06. Status: preparation and qualification in progress.
Channel: unsigned engineering preview; physics qualification is unchanged.

## Intended integrated checkpoint

- Portable native project state/results and imported visual artifacts, verified
  against the opened manifest identity; preserved canonical imported design data.
- Full saved result history and result-file load/export, with legacy compatibility.
- Current PI/SI tabular inputs, staged board import/recovery and MCAD export fixes.
- Refreshed contextual help and a uniform restored-SVG self-contained-content gate.
- Relative embedded frontend paths, a checkout-specific installer mutex, and a
  build-only native UI acceptance stage before expensive installer generation.

The prior 0.2.9 installer is rejected: an absolute Windows frontend snapshot path
became a URL and displayed a directory listing. This release requires actual
native UI observation in addition to source/worker tests. No test pass count by
itself constitutes frontend acceptance.

## Delivery record

Pre-build persistence evidence: six new Python artifact/workflow tests and 38
existing package-v3 tests passed. A real JTYU backend round trip preserved 28
layers, 41,762,958 visual bytes and 25 complete result records without source-CAD
access. UI rendering removes the exact standard KiCad SVG DTD after integrity
verification; a subsequent UI save preserves that normalized visual content,
not necessarily the original SVG declaration bytes.

Frontend qualification ran all 48 test scripts plus TypeScript. The initial
staged-import fixture used literal `layout` instead of SVG; it was updated to a
minimal SVG under the new universal validator, and that test then passed. No
validator was weakened. Updated help inventories 1,162 control sites (279
requiring runtime context). Full Python and native build qualification continue.

The first broad Python run executed 1,435 tests in 461.613 seconds, with one
skip and one infrastructure-overlap failure: the production-input negative
test encountered the active installer mutex instead of its expected missing
release-input rejection. That check must be rerun without an active build.
Native host tests passed 32/32. Frozen-worker source parity passed 183/183
modules; runtime parity passed 8/8 and packaged analytical benchmarks 15/15.

Build hashes, final regression results, installation and native UI observations
will be recorded here after completion. Project budgets, explicit unresolved
models and existing PI/SI/thermal engineering limitations remain applicable;
portable persistence does not imply unlimited result size or physics signoff.
