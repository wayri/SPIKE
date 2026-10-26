<!-- SPDX-License-Identifier: Apache-2.0 -->
# Fixed-grid co-simulation orchestration overhead - 23 October 2026

This check covers Python orchestration only. It changes no participant equation,
communication point, coupling order, time step, output value, admission gate, or
model-status claim.

## Optimization

`run_cosimulation` normalizes every accepted participant output into a fresh
dictionary. Each tick replaces the complete output tree and later adapters only
receive newly constructed scalar input dictionaries. Retained frames can
therefore own those fresh trees directly; deep-copying them again was redundant.

The built-in replay and gain adapters are stateless and return the JSON value
`null` (`None`) at every call. Hashing and deep-copying that immutable value at
every communication point cannot add byte-bound validation or rollback
isolation. Non-null custom state still receives the existing bounded canonical
JSON traversal and commit copy, and its previous accepted state is copied before
the callback.

The focused regression mutates an adapter's returned output after completion,
checks that every retained frame owns distinct dictionaries, and runs a custom
mutable-state adapter across ticks. Existing failure-before-commit,
configuration-mutation, cancellation, byte-budget, schema, CLI and worker tests
remain unchanged.

## Reproduction and result

Interpreter: repository `build/qualification-py311/Scripts/python.exe`, Python
3.11 environment. Fixture: two gain participants in an explicit-lag feedback
loop, 10,000 steps, two scalar outputs per retained frame. One warm-up preceded
11 uninstrumented `perf_counter_ns` samples. Both measurements have request
SHA-256 `b981ffab46dbdb2c039e9627c7d4b4f24e3bfe0a18b0b4f56a8fcb5980eca1bb`.

| implementation | median | range |
| --- | ---: | ---: |
| immediately preceding implementation | 385.168 ms | 163.266-612.874 ms |
| optimized implementation | 35.563 ms | 25.897-54.987 ms |

The observed median decreased 90.8% (10.8x). Machine load caused broad baseline
spread, but the slowest optimized sample remained below the fastest baseline
sample. Raw samples are retained in
`output/performance-20261023/cosimulation-before-py311.json` and
`output/performance-20261023/cosimulation-after-py311.json`. The checked-in
`scripts/benchmark_cosimulation_overhead.py` reproduces the current measurement.

This benchmark does not measure participant solvers, process startup, service
imports, JSON worker transport, or the newer propulsion field/BEM solve. It
supports only reduced master-loop overhead for already in-process scalar
participants. It does not establish millisecond latency for arbitrary coupled
physics.

## Executed checks

With workspace `TEMP` and `TMP` redirected to the writable `output` directory:

```
build/qualification-py311/Scripts/python.exe -m unittest tests.python.test_cosimulation -v
```

All 11 tests passed. A first run under the sandbox default temporary directory
had 10 passing tests and one `PermissionError` while creating the test's
temporary malformed-input file; redirecting the temporary directory resolved
that environment-only failure.
