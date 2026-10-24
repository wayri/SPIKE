<!-- SPDX-License-Identifier: Apache-2.0 -->
# Analysis preparation and project loading — 23 October 2026

This pass extends the earlier UI/co-simulation work to multiboard dispatch,
retained tetrahedral CFD/CHT and project opening. It removes repeated work while
preserving geometry, identities, numerical settings and admission gates. It does
not establish millisecond latency for every solver or arbitrary large model.

## Project opening

The actual `read_project_package` handler was exercised on the retained
`build/multiboard-acceptance-20261001/three-ebrake-assembly.spike`, SHA-256
`9bec19f71570fc41f418313b5af7a9e8817cc4a701889d5755ac2c963c955953`,
using the desktop's deferred-artifact/compact-transport options. The package is
completely read and verified on every call; imports are outside the timer.

Profiling found 104 polygon-simplicity validations for six distinct custom-pad
shapes. Validation now reuses only that pure predicate, keyed by complete
normalized coordinate tuples within one call. Every pad's shape, metadata,
drill/approximation evidence, coordinate structure, finite values and range
are still checked. Retention is bounded to 128 polygons and 32,768 vertices;
there is no persistent acceptance cache or rounded geometry key.

Exact primitive/dictionary fast paths also reduce mapping-protocol overhead
in recursive active-design comparison. Generic mappings, tuple/list hydration,
ordinary scalar equality and NaN behavior retain their previous semantics.

Five alternating predecessor-reference/current pairs measured:

| Deferred in-process project opening | Median | Range |
| --- | ---: | ---: |
| Predecessor validation/comparison | 2,441.218 ms | 1,865.822–3,035.867 ms |
| Optimized | 1,162.625 ms | 702.343–1,413.645 ms |

This is a 52.4% reduction (2.10x) on a concurrently used host. All ten complete
responses have identical canonical-JSON SHA-256
`75a44248fddfdb22445ba27757cfd234473009e321f353252aac261dd0d03c8c`
and 11,767,534 encoded bytes. The fingerprint covers canonical designs,
occurrences, explicit links, source bytes and manifest data.

Separate instrumented profiles decreased from 24.8 million calls / 11.67 s
to 6.9 million calls / 1.87 s. These are profiling costs, not uninstrumented wall
times. Calls to the unchanged simplicity predicate fell from 104 to 12.

Reproduce with qualification Python 3.11:

```text
build/qualification-py311/Scripts/python.exe scripts/benchmark_project_open.py build/multiboard-acceptance-20261001/three-ebrake-assembly.spike --output output/performance-20261023/project-open/repeat.json --repeats 5 --reference-dir output/performance-20261023/project-open/reference
```

The retained reference modules were reconstructed by removing only this pass's
fast paths. The script patches their runtime bindings for reference calls,
alternates order and rejects response-fingerprint differences. Samples,
runtime, source/reference hashes and earlier separate profiles are retained in
`output/performance-20261023/project-open/alternating.json` and adjacent files.

This measures worker-side opening. Cold service startup, native IPC,
result/model artifact hydration, frontend parsing and rendering remain outside
the timing. Canonical admission during imports/analyses also benefits, but
direct KiCad parser speed was not measured here.

An older internal Arduino package was rejected before timing because its
inline `analyses/index.json` exceeds the current 64 MiB control-plane limit.
That pre-existing compatibility gap requires result-artifact migration. No
limit was raised and the rejected file was not modified or used for speed claims.

## Multiboard and coupled analysis

[Multiboard evidence](MULTIBOARD_PREPARATION_PERFORMANCE_20261023.md) records
**340.986 → 24.654 ms** (13.83x) for the bounded 30-occurrence, 4,000-track
plain-JSON preparation fixture. It uses request-local summary/parsing reuse;
callback and Python-only container paths retain ordinary parser admission.
Per-occurrence IDs,
namespaces, explicit links, result rows, cancellation and aggregate resource
limits remain independent. Content and container-type changes must revalidate
instead of receiving stale parsed data. Refer to its final reviewed timings;
preparation time is distinct from physical solve time.

[CFD/CHT evidence](CFD_PERFORMANCE_20261023.md) covers the complete small retained
tetrahedral creeping-flow/conjugate-energy composition. Two distinct meshes
still receive full admission. Private snapshots and content binding allow
downstream reuse while protecting callbacks and mutable input containers.
Standalone calls retain full admission. The final paired 96-tetrahedron case
measured **106.840 → 62.241 ms** (1.72x), with identical fields and stable
diagnostics fingerprints. Turbulence, SU2, large CAD models and
distributed CFD remain outside this qualification.

[Independent review](ANALYSIS_PERFORMANCE_REVIEW_20261023.md) records invariants,
mutation regressions and limits. Integrity checks were retained even where
they reduced early speedup estimates.

## Verification and remaining work

The integration owner ran 18 custom-pad reuse/drill/composite/stroke tests and
70 assembly design/package/persistence/state-artifact/encapsulation tests:
all passed. These cover real eBrake imports, metadata/coordinate mutation,
invalid polygons, tuple/mapping equality, tampered archives and project identity.
The integration owner additionally ran 61 multiboard/circuit/link/scope tests
and 34 CFD/CHT/service/Stokes/energy tests successfully: 183 passing tests across
these four nonoverlapping groups. Review evidence is recorded in the linked files.

These are source changes requiring a fresh packaged build. Experimental and
unqualified capability labels remain explicit. End-to-end native opening and
the 10-/20-Marble-board and large-mesh memory/interaction checks remain pending.
Windows CIM reported 2,610,647,040 free physical bytes at this pass's start,
below the owner's 6,000,000,000-byte stress-start gate.

The [solver-family audit](SOLVER_PERFORMANCE_COVERAGE_20261023.md) and
[native/HPC roadmap](../NATIVE_HPC_MIGRATION.md) retain broader work: large-mesh
preparation/sparse-solve scaling, external-engine startup, realistic
co-simulation participants, native result delivery, and a common latency/memory
matrix. Small reference improvements do not qualify those larger workloads.
