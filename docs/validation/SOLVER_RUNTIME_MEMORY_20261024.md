<!-- SPDX-License-Identifier: Apache-2.0 -->
# Solver Runtime and Process Memory Observation - 24 October 2026

## Scope

This source-development observation compares fresh Python processes using the
backend-default numerical thread environment and an explicit one-thread CPU/BLAS
environment. Each child runs a 64-sample independently analytical matched AC
one-port fixture followed by `benchmark_em_network_cht.run_level(2,
flowing=True)`. It does not change or qualify either solver.

Git HEAD was `537023f84e70ed0d45915c7ef2b5cdb858d18228` with an uncommitted
worktree; the recorded source hashes, not that commit alone, bind this run. Python
3.12.9, NumPy 2.4.2 and SciPy 1.17.0 on 64-bit Windows. One fresh-process warmup
per configuration was discarded, followed by five alternating fresh-process
measurements per configuration. The exact reproducer is:

```powershell
.venv\Scripts\python.exe scripts\benchmark_solver_runtime_memory.py `
  --output <new-report.json> --samples 5 --timeout-seconds 120
```

The JSON report records the machine identity, runtime versions, complete thread
environment, input digests, source hashes before and after execution, every
sample, medians, and acceptance results. Output creation is exclusive so an old
report cannot be silently overwritten.

## Observations

| Configuration | Median solve time (s) | Import private commit (bytes) | Lifetime peak private commit (bytes) | Lifetime peak resident (bytes) |
| --- | ---: | ---: | ---: | ---: |
| Backend default | 0.2303359000 | 1,098,358,784 | 1,135,136,768 | 79,319,040 |
| Explicit one thread | 0.2272350000 | 86,994,944 | 123,920,384 | 77,070,336 |

These are observations for this machine and synthetic fixture, not portable
resource thresholds. Windows values come from
`GetProcessMemoryInfo/PROCESS_MEMORY_COUNTERS_EX`: working-set fields are
resident memory and private/pagefile fields are private commit. Unsupported
metrics are serialized as `null`, never zero. Snapshots were taken before
numerical imports, after imports, and after both solves; peak fields cover the
whole child lifetime.

Child stdout and stderr are redirected to temporary files. The parent rejects
either stream above 1 MiB before a bounded read; this bounds parent memory but
does not impose a temporary-disk growth limit during child execution.

## Acceptance evidence

All measured samples passed:

- the independent matched-load AC oracle at maximum absolute error `0.0` with
  the predeclared `1e-12` limit;
- CHT cell/global energy defects at or below `1e-9`, mixed residual at or below
  `1e-10`, and nonzero solved mass flow;
- backend-default versus explicit-one-thread AC phasors, CHT temperatures and
  face mass flows at `rtol=1e-10`, `atol=1e-10`;
- unchanged source hashes from pre-run to post-run.

The profiled level-2 CHT relative temperature-rise L2 error was approximately
`0.13374411495`. It is recorded as an observation only. It is not substituted
for or used to weaken the existing three-level refinement gate, whose `0.05`
limit applies to the level-4 result.

The focused observer and benchmark-harness unit tests pass. The repository
architecture check passes.

The final post-review report is `build/solver-runtime-memory-policy-r2-20261024.json`,
SHA-256 `fed1afe663a1551164eae96c44c82c4fe3314783a7b1c55418b525b254074f71`.
It contains the complete source/input identities and all measured samples.
The small timing difference does not establish a repeatable speedup; the
demonstrated benefit is approximately 89% less private commit, not that much
less resident RAM. The earlier retained report
`build/solver-runtime-memory-final-20261024.json` (SHA-256
`7078189e08192bb6bd419b04d8a2359f4b3bf324b2c00f8dfd13b1b2435c86f3`)
had nearly equal 0.198 s medians. Other development work was active, so timing
observations are not exclusive-machine release-performance qualification.

Independent review found and corrected two resource-policy defects before R2:
desktop overrides now pass canonical/bounded CPU-budget validation **before**
process creation, and inherited `MKL_DOMAIN_NUM_THREADS` is removed in desktop,
Python child-environment and executable-bootstrap paths. A fresh 5+5 R2 run
passed all seven recorded checks after those corrections. Thirteen policy/
observer/harness tests and the final 28-test runtime/entry/parallel-pool run
passed; the broader 89-test solver regression run passed. The Rust boundary
test `numerical_thread_override_is_bounded_before_child_creation` passed
(76 unrelated tests filtered), and the desktop library passed offline Cargo
checking. These do not constitute full-suite or installer qualification.

The unchanged full three-level benchmark was also rerun and passed at
`build/em-network-cht-runtime-20261024/report.json`: finest relative rise errors
0.03183281 (conduction limit) and 0.03170820 (tangential solved shear), with
observed orders above 2.07. This manufactured tangent-flow case has zero
continuum advection of temperature; it does not qualify active enclosure cooling.
The refinement report SHA-256 is
`908e1b20a31aeb5d1e671276dea738304fc390882a820710040466efdc9d5acd`.
No turbulence, transient feedback, general PCB extraction or release capability
is promoted. See [runtime usage and boundaries](../WORKER_NUMERICAL_RUNTIME.md).
