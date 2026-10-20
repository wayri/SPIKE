<!-- SPDX-License-Identifier: Apache-2.0 -->
# Native execution and acceleration boundaries

The owned SPIKES circuit kernels execute in C/C++ behind the C ABI. Python is
used for desktop UI, project ingestion, orchestration, reports and reference
checks. This is a direction and an ownership boundary, not a claim that every
analysis or coupled-physics feature has already been ported.

## Changes verified on 2026-10-13

- Ideal CCM buck, boost, buck-boost and flyback stability calculations now run
  in `src/spikes/smps_stability.cpp`: operating point, rational plant and loop
  response, poles, all crossings and stability classification. The additive C
  ABI transfers typed bulk arrays rather than per-point JSON. Studio and CLI
  select native execution by default; reference execution is explicit.
- Compiled C/C++ controllers offer opt-in `persistent_process` execution to
  avoid launching a process per tick. Default `fresh_process` behavior remains
  available. Static/global variables persist only in persistent mode; reset
  restarts the process. These are sampled controllers, not continuous device
  residuals or a hard-real-time runtime. See SPIKES_CONTROLLER_NATIVE_SPEED.md.

Differential tests cover all twelve topology/compensator combinations against
the independent Python analytical implementation, including complex curves,
poles and crossings. Native tests also cover invalid CCM points and numerical
conditioning. This is ideal averaged-model evidence, not switching-converter
or manufacturer qualification.

Measured warm end-to-end analysis (including Python validation and bulk-array
transport), thirty repetitions per size, gave median reference/native ratios
of 3.85 at 401 points and 5.15 at 10,000 points. Reproduce using
`scripts/benchmark_spikes_native_smps.py`; raw timings are in
`artifacts/spikes-native-smps-speed-20261013.json`. These measurements do not
establish ngspice parity, general transient acceleration, or cold-start speed.

## Remaining work and performance rules

The [behavioral DAG hot path](SPIKES_BEHAVIORAL_NATIVE_ACCELERATION.md) now
uses decoded opcodes and bounded thread-local scratch with no warm cache
allocations. Kernel benchmark evidence is separate from whole-circuit speed.
The [1D equilibrium device-field subsystem](SPIKES_TCAD_EQUILIBRIUM.md) is also
native C++, while PDK circuit workflows explicitly use the compiled ngspice
compatibility backend; neither establishes full TCAD or native PDK parity.

Python/SciPy analysis implementations, reference battery/digital models and
other service computations still exist. Each feature must be audited and
ported with a native contract and numerical regression evidence; exposing a
Python method through a native wrapper does not count as a port. Explicit
ngspice compatibility execution remains a separately selected external backend.

Numerical cores retain strict floating-point behavior; unsafe fast-math is not
an accepted shortcut. Sparse assembly, factorization reuse, event handling,
batched observables and bounded capture should be profiled on representative
switching decks. Parallel assembly and solving require thread-safe device
callbacks and accuracy/thread-scaling tests. CG is only appropriate for verified
SPD systems, not general nonsymmetric/indefinite MNA. GPU work is conditional
on demonstrated throughput benefit including transfers and latency.

Trusted compiled controllers can access host files and network. Process
separation contains some failures but is not a hostile-code sandbox. Native
implementation alone does not establish HIL deadlines or physical certification.
Knowledgeable human numerical review is required before release. The installed
application and installers have not been updated by this development pass.

## Native CLI JSON output

`native-run` emits compact JSON on stdout to reduce serialization, transport and
parse overhead while retaining every field, channel and sample. Use `--pretty`
for indented stdout. `-o result.json` remains indented by default. Help and error
usage retain terminal-width formatting; successful native runs defer that work.
Native transient channel extraction reuses its query handle/name/output buffer
within each channel and checks every scalar ABI return code. It does not expose
native storage, truncate outputs or alter the solver result.
