<!-- SPDX-License-Identifier: Apache-2.0 -->
# Second tetrahedral allocation optimization

Date: 2026-10-12. Scope: existing bounded convex point-cloud generation.

This pass removes the per-sphere nested function, intermediate coordinate lists,
norm generator and unconditional tie-ID tuple. A shared lift helper constructs
four rows directly; IDs are constructed only for an exact symbolic tie. The
immutable point magnitudes are accessed directly. No coordinates, arithmetic
association, Python `sum` semantics, floating filter, exact rational fallback,
tie ordering, work limit, certification or public result contract changed.

The first-pass baseline source is SHA-256
`773708649885455223e6543ad80fecddc274c9c7d1150515ba756c26926be1d5`;
the new source is
`47ba7c465816d38f622d98d0b9f39b09599706951a45b1041cf80d890f69d3a1`.
The baseline generator is an unbundled local record named `baseline-generation.py`.

## Exactness and timing

The new test compares floating hexadecimal determinant values and exact
Fraction values against the original lift construction over 200 seeded cases.
Full-candidate tests retain the cube, lattice, random cloud and finite-enclosure
rejection oracles. The focused tetrahedral and benchmark groups passed 66 tests.
Independent review matched 2,610 predicate decisions/exceptions and per-call
counters across 29 randomized and degenerate clouds, including both symbolic
modes. Seven complete candidates, four rejections, and predicate/exact-fallback
budget boundary errors matched the saved first-pass source.

`scripts/benchmark_tetra_allocation_pass2.py` alternates backend order in one
process, with one warmup and five timed samples per backend. Every invocation
requires equal complete candidates or equal rejection type/message, plus
unchanged input bytes. Generation timing includes mandatory certification;
result comparison is outside the timed interval. The artifact is
the unbundled local `allocation-benchmark.json` record.

| Fixture | First pass median (ms) | Second pass median (ms) | Speedup |
| --- | ---: | ---: | ---: |
| 8 points | 2.5935 | 2.3261 | 1.115x |
| 32 points | 39.0317 | 25.3965 | 1.537x |
| 64 points | 165.5008 | 99.9762 | 1.655x |
| 128 points | 691.3871 | 397.2180 | 1.741x |
| Cospherical cube | 6.6243 | 6.1789 | 1.072x |

The thin fixture was rejected identically and is excluded from success rankings.
These measurements establish additional speed on this corpus, not RAM savings.
Do not multiply speedups from separate runs to infer cumulative performance.

A separate serial subprocess comparison directly measured the original
pre-optimization source (`4906644b110a1e024d011836537ed5042f9518f46bd20b6df199906c6fd0adec`)
against the current source. Five samples and one warmup produced:

| Fixture | Original kernel (ms) | Current kernel (ms) | Current full API (ms) |
| --- | ---: | ---: | ---: |
| 8 points | 3.3887 | 1.8357 | 2.0054 |
| 32 points | 60.5615 | 23.6837 | 25.7490 |
| 64 points | 273.0357 | 94.4669 | 91.7787 |
| 128 points | 1280.4762 | 374.5010 | 378.3131 |
| Cospherical cube | 7.1724 | 5.3409 | 5.9658 |

The measured kernel gains at 32/64/128 points are 2.56/2.89/3.42x relative to
the original source. Accepted outputs retained identical geometry hashes and
passed the independent audits; all three backends rejected the thin fixture.
Small kernel/full-API ordering differences are sample variation, not evidence
that extra API validation is faster. The artifact is
the unbundled local `original-comparison/benchmark.json`, SHA-256
`77d4f0b5ae33d8e6181b100d9b5b8ef53d84e749bc235ba42cae9cb57e852db8`.
Worker process memory counters do not demonstrate mesh-only RAM savings.

## Real PCB scope

The separate [retained Marble diagnostic](LARGE_PCB_MESHER_PROFILE_20261012.md)
finished but omitted five of seven requested copper zones. Its measured hotspot
samples identify polygon validation and contact evidence as future optimization
targets. It is not accepted as a complete mesh or solver input. The hybrid
mesher source was not changed by this second pass. Neither this point-cloud
benchmark nor the partial Marble result establishes the 10-20-board, 10 GB
whole-program target or reduces its required capabilities.

The [first-pass comparison](INTERNAL_MESHER_OPTIMIZATION_20261012.md) retains
black-box Gmsh and SciPy evidence and its unequal validation timing boundaries.
External engines were not rebenchmarked or adopted in this allocation pass.

## Reproduction and integration

```powershell
.venv\Scripts\python.exe scripts\benchmark_tetra_allocation_pass2.py `
--output "$env:TEMP\spike-allocation-benchmark-fresh.json"
.venv\Scripts\python.exe -m unittest discover -s tests\python -v
.venv\Scripts\python.exe scripts\check_architecture.py
```

The benchmark refuses to overwrite evidence and requires the pinned baseline.
Architecture and Python compilation checks passed. Full integration results
are recorded in the unbundled local `mesher-pass2-python-final-tests-20261012.log`: 3,495 tests
in 912.026 seconds, one failure, nine errors and 51 skips. All 20 tests in the
predicate-allocation, mesher-benchmark and hybrid-equivalence modules passed.
The broad repository gate remains failing:

- One failure and one error concern the public-release schema surfaces,
  including the absent/duplicate assembly-EM schema identifier.
- Four SI analytical fixtures lack `signal_width_m`.
- Four native SIN-source tests lack analytic SIN exports in the loaded library.

These categories were independently observed before this allocation pass;
their source/fixture/native paths were not edited here. The prior broad
Python-debug timeout failure did not recur. No failing check was waived or
weakened. The full log SHA-256 is
`2ef3e58f8db98ae51f86dc3316c86dc7725320d6e6110e2e90102cf15e661cf7`.
Frontend architecture/button rules, TypeScript, high-layer parser checks, and
Rust host tests passed (54 passed, one live GPU smoke check ignored). Existing
dependencies were used without a package installation.

Implementation, test oracles, and benchmark driver are original SPIKE work. No
external implementation was inspected or adapted. This is an allocation-only
change, so the original numerical validity and convergence limits remain.
Knowledgeable human numerical review remains required before release.

The subsequent [retained Marble correction](MARBLE_FILLED_ZONE_FIX_20261013.md)
records complete cutout-preserving copper meshing, contact-query acceleration,
board-wide evidence accounting and the later full regression result. It does
not change this tetrahedral pass's measured scope or qualification.
