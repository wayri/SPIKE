<!-- SPDX-License-Identifier: Apache-2.0 -->
# UI and solver-boundary performance — 23 October 2026

This pass removes redundant presentation, initialization, orchestration, and
transport work. It does not change governing equations, mesh-density settings,
communication points, convergence tolerances, or solver admission gates. It does
not establish millisecond latency for every solver or arbitrary coupled model.

## Measured results

| Path and exact workload | Before | After | Interpretation |
| --- | ---: | ---: | --- |
| Scalar co-simulation master, two gain participants, 10,000 steps | 385.168 ms median | 35.563 ms median | Same request, retained frames, state isolation and communication points; participant field solvers and transport excluded |
| Results presentation, 100,000 samples / 75,000 selected | 45.73–93.10 ms baseline medians | 0.0009–0.0011 ms warm lookup medians | Immutable field/layer reuse; new fields/layer selections still pay the original cold cost |
| Import `python.spike_core`, five fresh interpreter processes | 2,139.94 ms median | 201.36 ms median | Contract-only package initialization; filesystem caches and concurrent host load uncontrolled; full service and numerical-engine import excluded |
| JSON encoding of 10,000 synthetic scalar sample rows | 954,128 bytes | 854,123 bytes | 10.5% fewer UTF-8 wire bytes; JSON-decoded values identical |
| Retained Arduino GND mesh preparation, fixed density and budgets | 4.095 s median | 1.408 s median | 2.91x; complete mesh SHA-256, ownership and counts unchanged |

The encoding microbenchmark measured 11.404 ms formatted versus 10.669 ms
compact median in this run. The byte reduction is deterministic for this input;
that small timing difference is not a portable speed guarantee.

Detailed evidence and scope:

- [Co-simulation measurements and state isolation](COSIMULATION_OVERHEAD_20261023.md).
- [Dense result presentation measurements](RESULT_SCALAR_PRESENTATION_PERFORMANCE_20261023.md).
- [Coverage of all solver families and remaining bottlenecks](SOLVER_PERFORMANCE_COVERAGE_20261023.md).
- [Exact PCB preparation optimization and retained-fixture evidence](PCB_PREPARATION_OPTIMIZATION_20261023.md).
- [Independent edge-index and slab-sweep equivalence review](PCB_PREPARATION_INDEX_REVIEW_20261023.md).
- Raw initialization, encoding and bounded solve measurements:
  [`output/performance-20261023`](../../output/performance-20261023).

The Results panel additionally memoizes the selected board geometry/layer
inventory, engineering analytics, DC review, and source/load review using their
complete inputs. Unrelated control changes no longer rescan and sort those
immutable inputs. Changing the result, scope, limits, or fusing settings
recomputes the corresponding review. No separate browser-frame latency claim
is made for this integration change.

## Initialization and bounded solve checks

The package previously loaded field/circuit iteration and PEEC providers even
for contract-only consumers, transitively initializing NumPy/SciPy. Those
public exports now resolve on demand. Function/class identity, aliases,
`import *`, discovery through `dir`, and unknown-attribute failures remain
covered. Explicit imports remain visible inside the lazy branches for frozen
dependency analysis. The frozen qualification candidate created before these
edits does not contain these changes; a new packaged build is still required.

`scripts/benchmark_solver_latency.py` separates numerical imports, first use,
and eleven repeated calls to the existing analytical/discrete MNA reference
fixtures. The final run records repeated medians of 0.109 ms for the DC divider,
0.169 ms for one AC RC frequency, and 7.525 ms for the 101-state RC transient.
Every call checks the existing reference and tolerance. These tiny cases were
already fast before this pass. Differences between runs are not evidence of a
numerical-kernel optimization. Numerical imports still took 2.878 s in the final
run; package initialization savings must not be represented as eliminating that
necessary first-use cost.

Reproduce from the repository root with the qualified Python 3.11 environment:

```text
build/qualification-py311/Scripts/python.exe scripts/benchmark_solver_latency.py --output output/performance-20261023/solver-latency-repeat.json
build/qualification-py311/Scripts/python.exe -m unittest tests.python.test_package_imports tests.python.test_cosimulation tests.python.test_service_simulation_handlers tests.python.test_worker_response_encoding
```

The host is an Intel Core Ultra 7 255H with 16 logical processors, Windows build
26300, Python 3.11.9, NumPy 2.4.6 and SciPy 1.17.1. Measurements are unpinned on
a concurrently used desktop. The source tree contains unrelated in-progress
changes; no clean-release or cross-machine performance claim follows.

## Integration checks executed

The integration owner ran 75 passing Python tests across package exports,
co-simulation, service simulation routing, solver reference benchmarks, native
contracts, CLI entry, worker protocol/encoding and the four affected boundary/
filled-path test modules. The worker protocol tests include project migration,
source-byte preservation, save/reopen, placement policy and structured failures.

The result-performance, impedance UI, PI review/admission, responsive-manager,
and panel-layout scripts passed. TypeScript checking, architecture checking,
documentation checking and diff whitespace checks passed. These checks do not
replace native window-size, dialog, rendering or end-to-end responsiveness
verification on an immutable current build.

## Remaining qualification

The native 10-/20-board load, process-tree/GPU memory and responsiveness runs
remain deferred: Windows CIM reported 2,846,232,576 free physical bytes at
13:23 UTC, below the owner's revised 6,000,000,000-byte start gate. That gate is
separate from the 10 GB available-memory product target and from hard memory
limit qualification. Native dialog/tab/export checks remain governed by the
existing native checkpoint; this source-level pass does not mark them complete.

Large retained geometry preparation, realistic field/thermal/circuit participant
coupling, dense viewport delivery, and cold/warm external-engine phase timings
remain substantive work. The coverage audit identifies the existing entry
points and distinguishes measured timings from correctness-only evidence.
