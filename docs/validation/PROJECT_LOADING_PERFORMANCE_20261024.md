<!-- SPDX-License-Identifier: Apache-2.0 -->
# Project loading projection performance — 24 October 2026

## Scope

This pass profiles and improves the actual `read_project_package` worker handler
after the 23 October validation/comparison caches. It uses the retained
`build/multiboard-acceptance-20261001/three-ebrake-assembly.spike` package and
the desktop's deferred-artifact, compact-normalized-source and
compact-canonical-design options. The package is fully read, hashed and admitted
on every invocation. No integrity check, manifest/signature behavior, source
identity, artifact admission, equation, numerical gate or capability changed.

The host had less than the 6 GB free-memory start gate. No 10/20-board, native
UI, large-mesh or stress workload was run.

## Finding and bounded change

The pre-change profile in
`output/performance-20261024/loading/current-profile.profile.txt` recorded
6,898,324 calls in 2.744 profiled seconds. The two dominant remaining phases
were project package read/admission and `frontend_project_payload`.

The v2-to-v1 frontend projection already allocates new legacy lists and maps.
Calling `SpiDeR.to_dict()` then invoked `dataclasses.asdict`, recursively
rebuilding that complete multi-megabyte tree a second time. This traversal was
not validation and did not add isolation beyond a normal deep copy.

`python/spike_core/service_project.py` now converts the projected `SpiDeR`
fields with one ordinary `deepcopy`, retaining explicit dictionary conversion
for the nested `ValidationIssue` dataclasses. This preserves:

- the exact public v1 mapping and JSON types;
- detached nested lists, mappings, metadata and future metadata values;
- issue dictionaries rather than Python dataclass instances;
- the authoritative canonical v2 design and all source identities;
- every existing package, artifact, signature and admission check.

The change deliberately does not cache an admitted project across opens or
share mutable response objects between requests.

## Paired evidence

`scripts/benchmark_project_open.py` can now load an optional retained
`service_project.py` from its reference directory in addition to the existing
validator/comparator references. For this comparison, the reference directory
contains the exact current custom-pad and assembly-design implementations and
only the pre-change project projection. Alternating order limits monotonic host
drift. Five pairs produced:

| Deferred in-process open | Samples (ms) | Median (ms) |
| --- | --- | ---: |
| Pre-change projection | 994.473, 895.503, 945.810, 1,075.981, 962.290 | 962.290 |
| Updated projection | 1,660.588, 791.844, 763.178, 749.270, 795.543 | 791.844 |

The observed median reduction is 17.7% (1.22x). The first updated sample is a
retained outlier; it was not removed from the evidence. All ten complete worker
responses have the identical canonical-JSON SHA-256
`75a44248fddfdb22445ba27757cfd234473009e321f353252aac261dd0d03c8c`
and identical encoded size 11,767,534 bytes. The input package SHA-256 is
`9bec19f71570fc41f418313b5af7a9e8817cc4a701889d5755ac2c963c955953`.
Machine/runtime, samples, parameters and production/reference source hashes are
retained in
`output/performance-20261024/loading/paired-current-baseline.json`.

Reproduce with the qualification Python 3.11 runtime:

```text
build/qualification-py311/Scripts/python.exe scripts/benchmark_project_open.py build/multiboard-acceptance-20261001/three-ebrake-assembly.spike --output output/performance-20261024/loading/repeat.json --repeats 5 --reference-dir output/performance-20261024/loading/reference
```

## Verification

With `TEMP` and `TMP` directed to a workspace-owned directory:

- 11 project loading, compact transport and persistence tests passed;
- 39 project-package v3 integrity, signature, limits, artifact and future-field
  tests passed;
- 15 assembly-design identity, duplicate, size-limit and lossless-reopen tests
  passed.

The new focused test compares the production projection against the established
`SpiDeR.to_dict()` result, checks issue JSON conversion, mutates nested projected
future metadata, and verifies the canonical input remains byte-value unchanged.

## Limits and next bottleneck

This measures in-process worker opening on one retained three-board package.
Cold worker startup, native IPC, deferred result/model artifact hydration,
frontend decoding/state admission, rendering and 10/20-board behavior remain
outside the result. Timings on a concurrently used host are local observations,
not a portable latency guarantee.

After this bounded projection fix, package read/admission remains the dominant
measured phase. Its work includes streaming member integrity verification, JSON
decode, canonical v2 admission, active-design equality, geometry/model/source
checks and parallel-state admission. Those checks have different security and
correctness ownership and should not be removed or persistently cached. A next
pass should add phase clocks and allocation/peak-memory evidence inside one
authenticated read before considering request-local reuse. Native end-to-end
measurement and the prepared 10/20-board workloads remain gated on at least
6 GB free physical memory.
