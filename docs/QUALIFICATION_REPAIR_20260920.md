# Local qualification repair - 2026-09-20

This repairs the reported Python/native qualification environment and one
benchmark fixture. It does not qualify arbitrary PCB fields, SERDES compliance,
actuators, measured correlation or a distributable release.

## Root causes and changes

- Default `python` resolves to CPython 3.14 without all test dependencies.
  CPython 3.11.9 had jsonschema but lacked pyarrow and current native bindings.
- Created `build/qualification-py311` using the installed CPython 3.11.9 with
  system-site-packages. This is a local supplemental environment, NOT a fully
  hermetic release environment. System Python was not modified.
- Downloaded the already pinned pyarrow 25.0.1 and nanobind 3.0.0 wheels and
  verified SHA-256 before offline installation. The supplemental CPython 3.11
  hashes are in `requirements-qualification-py311-windows-x64.txt`. Nanobind's
  upstream yank concerns incorrectly declared Python 3.9 compatibility; the
  selected environment is 3.11. This does not grant new redistribution rights.
- Rebuilt the current native bindings with MSVC 19.51.36256.0, Eigen 3.4.0 and
  nanobind 3.0.0 in `build/qualification-native-py311`. Eigen headers came from
  the existing local SimCircuit `build_neo/_deps/eigen3-src` directory and were
  configured, not modified, using `build/qualification-eigen`.
- Replaced only `python/spike_peec_native.cp311-win_amd64.pyd`. The previous
  binary is preserved at
  `build/qualification-native-py311/spike_peec_native.pre-rebuild.cp311-win_amd64.pyd`.
  CPython 3.12/3.14 binaries were not rebuilt or promoted.
- The native hybrid benchmark had a trace running through an overlapping
  pad/plane, double-counting copper in the filament approximation. The fixture
  now terminates at the pad attachment and retains only small topology joins.
  The non-passive-matrix rejection and all tolerances remain unchanged.
  This is NOT a solver fix for arbitrary overlapping PCB copper; that remains
  a geometry normalization limitation requiring separate implementation.

Current CPython 3.11 native binary SHA-256:
`3b2a20bc5e48fb8452a6b6f5af27ebd22ace8341da87c11c7152b1abf7087a8d`.

## Reproduction

Use the interpreter explicitly; do not infer qualification from `python` on PATH:

```powershell
& ./build/qualification-py311/Scripts/python.exe scripts/check_solver_qualification_environment.py
& ./build/qualification-py311/Scripts/python.exe -W error -m unittest discover -s tests/python -v
python scripts/check_architecture.py
```

The initial repair log is `build/qualification-native-py311/python-suite.log`;
the final rerun is `build/qualification-native-py311/python-suite-final.log`.
Local focused checks cover topology APIs, Arrow data, benchmark execution and
generalized-reference-plane geometry/native admission. A passing geometry test
does not imply a field solve, arbitrary geometry support or measured accuracy.

The initial repair run eliminated the original 2 failures/39 errors and
uncovered a duplicate-ZIP fixture warning under `-W error`: 1,719 tests, one
error, two skips. The fixture now explicitly asserts the expected zipfile
warning while preserving the package reader's duplicate-member rejection.
Warnings-as-errors remains enabled globally. Its focused regression passes.

Additional local evidence: all 15 solver benchmarks passed with zero skips,
20 focused Python regressions passed, and all five native CTest PEEC/topology
targets passed with assertions enabled. The four preflight regressions pass.
Native builds emitted an NDEBUG override warning; no warning-free native
release qualification is claimed.

Final rerun: **1,724 tests, zero failures/errors, two skips**, 282.582 s,
with warnings treated as errors. The skips are the unavailable CUDA/CuPy
runtime and the optional external KiCad fixture (SPIKE_FIXTURE_BOARD unset).
Architecture guard also passes. This supersedes the failed software-suite
result for this CPython 3.11 environment only; it is not physical qualification.

## Remaining completion sequence

1. Pass this local suite with current native APIs; retain failures and skips.
2. Execute controlled nested cross-board refinement, then separate PML and
   duration sensitivity studies; retain the 0.02 full-complex-S criterion.
3. Implement union-normalized PCB copper and conforming materials/ports with
   ownership and source-identity checks before claiming general extraction.
4. Implement and validate physical receiver/CDR and BER workflows independently
   of the existing ideal-phase/Gaussian estimates; qualify explicit Ethernet
   variants and model coverage, not a generic "10GbE supported" flag.
5. Qualify nonlinear magnetic material, force/torque and actuator workflows
   against independent analytical/solver and measured references.

No unfinished item in this sequence is enabled merely by passing the software
suite. Private CI, platform/backend, clean-machine and measured qualification
remain separate release evidence.
