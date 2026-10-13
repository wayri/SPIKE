<!-- SPDX-License-Identifier: Apache-2.0 -->
# Initial solver accuracy baseline, 2026-10-12

See [the accuracy program](../SOLVER_ACCURACY_PROGRAM.md) for all-family coverage,
published reference candidates, comparison rules and improvement priorities.
The [machine-readable evidence](SOLVER_ACCURACY_BASELINE_20261012.json) preserves
the executed reports, tolerances, case hashes and runtime identities.
This baseline does not qualify all SPIKE solvers or establish overall superiority.

## Executed results

- Permanent corpus: **15 passed, 0 failed, 0 skipped**. This supersedes the
  older 10-case count only for this run; the historical report is preserved.
- Shared circuit corpus: **9/9 passed separately in owned C++, ngspice and
  LTspice**, one repetition per case/engine, using the existing harness gates.
- New finite-ramp RC/RL convergence experiment: both passed over 1, 0.5 and
  0.25 microsecond requested steps. Raw diagnostics confirm the effective
  integration steps. Endpoint errors decrease approximately fourfold per
  halving; observed orders are approximately 1.9996 and 1.9998.
- 71 focused thermal, channel CHT, planar magnetic FEM, machine and SI
  regression tests passed in `build/qualification-py311/Scripts/python.exe`.
  These are software/analytical checks, not new external comparisons.
- 16 benchmark/oracle regression tests passed; architecture check passed.
  Frontend/Rust checks were not run: no frontend/host or numerical kernel was changed.

Of the permanent corpus's 15 passes, 12 have numeric reference errors; three
are connectivity/execution/AC-monotonicity checks without reference errors.
For numeric cases, the largest relative errors are sheet resistance **2.5%**
and the wide-microstrip capacitance asymptote **2.2452%**. The remaining numeric
cases are at or below approximately 1.6e-13 relative error. Some oracles test
the same mathematical approximation or discrete method; near-zero error does
not establish physical accuracy of general geometry.

## Shared scalar circuit errors

Numbers are absolute voltage errors at the prescribed sample or averaging
window, versus the harness's analytical oracle. They are not waveform-wide
maximum errors. All cases passed their pre-existing individual gates.

| Case | SPIKES error (V) | ngspice error (V) | LTspice error (V) | Gate (V) |
| --- | ---: | ---: | ---: | ---: |
| Equal divider | 0 | 0 | 0 | 1e-10 |
| Unequal divider | 0 | 0 | 0 | 1e-10 |
| Current load | 0 | 0 | 0 | 1e-10 |
| RC ramp/step | 3.64039e-5 | 5.44979e-9 | 2.93349e-8 | 5e-5 |
| RL ramp/step, sense voltage | 3.64039e-5 | 5.44984e-9 | 2.65986e-4 | 3e-4 |
| Pulse duty average | 0 | 0 | 1.4e-10 | 2e-3 |
| Ideal LC buck PWM | 3.83976e-3 | 3.88906e-3 | 1.62677e-3 | 0.06 |
| Passive series RLC | 6.73703e-5 | 2.99350e-5 | 1.40125e-5 | 0.015 |
| Motor armature RL surrogate | 1.45533e-3 | 2.20710e-4 | 6.12864e-5 | 2e-3 |

The buck oracle idealizes source edges; the motor oracle treats a short finite
rise approximately. Those documented model differences remain in the harness
tolerances and prevent interpreting every difference as pure solver error.
The motor is an electrical surrogate, not a torque/magnetic/mechanical test.
The RF label is an RLC transient, not full-wave/S-parameter qualification.

## Verified improvement and interpretation

For the original passive fixtures, the oracle independently solves
`tau*y' + y = min(t/rise, 1)` with zero initial state. The RC output and RL
sense voltage share this normalized equation. For `tau=1 ms`, `rise=10 us`
and `t=1.01 ms`, the exact observable is `0.6339538400080997 V`.

| Requested step | RC absolute error (V) | RL absolute error (V) |
| --- | ---: | ---: |
| 1 us | 3.64038726e-5 | 3.64038726e-5 |
| 0.5 us | 9.10323821e-6 | 9.10323828e-6 |
| 0.25 us | 2.27609395e-6 | 2.27609373e-6 |

Quartering the step improves this endpoint error approximately sixteenfold.
The native diagnostics show two backward-Euler startup/recovery steps and
trapezoidal stepping for the remainder of the coarse run. The near-second-order
trend supports a temporal-discretization explanation for these cases. It does
not exclude errors in other models, transitions, or long histories.

**Action:** use 0.25 us for these fixtures when a roughly 2.3 uV endpoint budget
is required, and extend comparisons to waveform errors and accuracy versus cost.
No solver production defaults or numerical kernels were changed on this evidence.
Speed rankings are not supported by a one-repetition scalar corpus.

## Identity, reproducibility and limitations

Owned C++ binary:
`build-spikes-sine-20261012/Release/spikes_c_api.dll`, SHA-256
`2cc08782e6a1503bd268288dc3488e2bc05841dc764dd321d5ad9e600a9a9682`.
The same hash appears in the competitive and final timestep reports; the
timestep harness verifies that the library stays unchanged during its execution.
The default PEEC/MNA module used for the permanent corpus is separately identified
in the JSON. These are different native execution routes.

ngspice and LTspice executable paths and byte hashes are retained in the JSON;
the competitive harness did not record their semantic version strings. That is
a reproducibility gap to close before a version-labelled publication.
Relevant Python hashes were captured after the runs. The heavily modified
workspace was not reset, and the compiled native artifact has not been proven
equivalent to all current C++ sources. Claims bind to the recorded binary.

Reproduce from the repository root with the matching runtimes available:

```powershell
python -c "import json; from python.spike_core.benchmarks import run_solver_benchmarks; print(json.dumps(run_solver_benchmarks(), indent=2, allow_nan=False))"
python scripts/run_spikes_competitive_benchmarks.py --library build-spikes-sine-20261012/Release/spikes_c_api.dll --repetitions 1 --output output/new-circuit-comparison.json
python scripts/benchmark_circuit_timestep_accuracy.py --library build-spikes-sine-20261012/Release/spikes_c_api.dll --output output/new-timestep-run
build/qualification-py311/Scripts/python.exe -m unittest tests.python.test_assembly_tetra_thermal tests.python.test_structured_solid_thermal tests.python.test_laminar_channel_cht tests.python.test_magnetic_fem tests.python.test_em_machines tests.python.test_si_channel -q
build/qualification-py311/Scripts/python.exe -m unittest tests.python.test_benchmarks tests.python.test_spikes_competitive_benchmark tests.python.test_spikes_public_benchmark tests.python.test_circuit_timestep_accuracy -q
python scripts/check_architecture.py
```

The timestep output must be new. Failed attempts are retained locally:
the first fixture title needed an explicit comment marker; sandbox restrictions
blocked native-library access and temporary-file operations; the default Python
lacked jsonschema for broader regressions. Corrected runs used the qualification
environment and authorized native execution, without changing solver code or gates.
Local raw evidence and logs remain under `output/solver-accuracy-20261012/`.

Historical SU2, CalculiX and openEMS comparisons are audited in the program
register but were not rerun here. No new hardware correlation, magnetic external
comparison, commercial multiphysics run, general structural solve or optical
accuracy qualification was performed. Those are explicit remaining workstreams.
