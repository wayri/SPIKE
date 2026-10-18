# ODB++ and harness extension validation

Date: 2026-09-05. Status: engineering preview; no vendor-corpus parity claim.

Subsequent [public-board corpus validation](../benchmarks/public-board-corpus/REPORT.md)
exercised 22 inputs, including published hardware exports and complex KiCad boards.
It found and regression-tested additional parser fixes, and records unresolved
geometry and project-size failures. The synthetic checks below do not supersede
those observed limitations.

## Compressed job-root regression, 2026-10-19

Local import-quality record: `IQ-ODB-COMPRESSED-ROOT`. Previously, a valid job
whose matrix was stored as `matrix/matrix.gz` failed root discovery before
inspection or normalization. The regression is repaired by the bounded logical
member lookup and the fixtures below; no external issue was filed by this task.

The independently authored minimal job in
`tests/python/test_odb_harness_extensions.py` now exercises gzip compression of
every text member, including the matrix root marker, as a folder, ZIP and TGZ.
Assertions compare exact layers, nets, tracks, pads, zones and components against
the plain job; separately check object counts, endpoints, width and board bounds
in millimetres; and verify original member names and the source digest. A
negative-copper fixture verifies that unsupported geometry remains diagnostic
and blocks readiness after compressed-root discovery.

`tests/python/test_odb_source_inspection.py` covers compressed multi-step
selection, ambiguous roots and plain/gzip members, disabled nested gzip,
decompression ratio limits and the explicit unsupported Unix compress error.
The ODB inspection/harness slice passed 42 tests; parity-candidate and
public-board import regressions passed 11 tests. Architecture checks passed.
Tests used the repository `.venv` with `TEMP` and `TMP` directed to
`build/odb-import-test-temp` because the execution sandbox denied its default
temporary directory. These are package compatibility checks; no new vendor
conformance, panel expansion or solver qualification is claimed.

## Executed checks

- Broad Python suite: 1,356 tests, no failures, one skip. Native ABI tests used
  `build-spikes-hybrid/spikes_c_api.dll` through `SPIKES_TEST_NATIVE_LIBRARY`.
  The default test path selects an older DLL without the session-voltage API.
- After the final import and numerical checks: 26 focused ODB++, harness, and
  packaged-worker tests passed. These cover quoted property separators,
  unresolved drills, inconsistent stackup order, and resistance overflow and
  underflow in addition to archive, geometry, schema, graph and persistence tests.
- TypeScript checking and the desktop production build passed. Vite reports
  its existing large-chunk advisory.
- Display projection, project-package round trip and PI series handoff tests
  passed. Exact imported geometry stays separate from display tessellation.
- Native desktop host: 29 tests passed with `cargo test --lib --offline -q`.
- Architecture checks passed.

## Frozen runtime

The final isolated worker is under
`build/odb-harness-qualification/resources/spike-worker/`.
Its adjacent `spike-worker.manifest.json` records file hashes and these gates:

- Source-versus-packaged runtime comparison: all eight checks passed.
- Numerical benchmark gate: all 15 benchmarks passed, none skipped.
- Canonical Arrow project persistence and native interactive engine probes passed.
- Both bundled extensions actually executed, including schema loading, harness
  circuit compilation, ODB++ geometry normalization, and importer-registry
  generation of the desktop design snapshot.

This build does not replace the archived Windows release or install anything.

## Qualification limits

The fixtures exercise documented syntax and deliberate failure cases, not a
representative Altium, OrCAD/Allegro, EAGLE, Zuken or Xpedition export corpus.
Negative artwork composition, custom-symbol expansion, panel repeats, complex
padstacks and automatic STEP display remain outside this preview. Unsupported
conductor data is retained and blocks solver use. Explicit model assignments,
transforms and bytes are preserved through the enrichment schema and project
save/reload; byte retention is not geometry conversion or placement validation.

Harness electrical output is a lumped circuit fragment. It requires explicit
or dimensionally complete electrical data and does not infer a ground return,
shield coupling or field-solver model from connection topology.

See [usage and contracts](ODB_AND_HARNESS_EXTENSIONS.md) for supported input,
desktop actions, schema locations and the qualification checklist.
