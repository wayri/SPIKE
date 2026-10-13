<!-- SPDX-License-Identifier: Apache-2.0 -->
# Equation devices and package composition: development evidence

Date: 2026-10-13. Windows host, Python 3.14, existing owned C++ DLL
`build-spikes-native-analysis-20261013/Release/spikes_c_api.dll`.

Executed 53 tests, all passed, no skips:

```powershell
$env:SPIKES_TEST_LIBRARY=(Resolve-Path build-spikes-native-analysis-20261013/Release/spikes_c_api.dll).Path
$env:SPIKES_TEST_NATIVE_LIBRARY=$env:SPIKES_TEST_LIBRARY
$env:SPIKES_TEST_SMPS_LIBRARY=$env:SPIKES_TEST_LIBRARY
python -m unittest tests.python.test_spikes_equation_device tests.python.test_spikes_device_parasitics tests.python.test_spikes_lumped_physics_parts tests.python.test_spikes_smps_cli tests.python.test_spikes_native_cli tests.python.test_spikes_transient_slice -v
```

New checks include:

- Input isolation, duplicate/invalid field rejection and inert CLI library export.
- Four-quadrant cubic current and negative differential resistance, with native
  terminal KCL and analytic DC current oracles.
- Nonlinear charge ramp matching exact discrete BE/BDF2 charge derivatives to
  1e-10 A absolute error.
- Four-pin illustrative HEMT-like equations, field-plate charge and nonlinear
  gate-drain charge, wrapped in package R/L; native transient convergence and
  terminal-current sum within 2e-9 A.
- Arbitrary five-pin HEMT package interface, private-node collision handling,
  exact zero-volt links, and full mutual-inductance matrix passivity rejection.
- Native series-R/L/shunt-C step response; existing semiconductor, CLI and
  transient regressions retained.

`scripts/check_architecture.py` passed. Both bundled JSON demonstrations were
exported by the real CLI to inert `.lib` and resolved-report artifacts under
`artifacts/spikes-user-hemt-20261013.*` and
`artifacts/spikes-user-material-20261013.*`.

No compiler/kernel modifications or installed-application changes were needed:
all generated numerical operations reuse native behavioral and R/L/C/V MNA
primitives. Model construction and contract validation are Python services.
No HEMT/diamond material validation, manufacturer qualification, arbitrary
internal-state dynamics, thermal/noise qualification, or owned K-element
execution is established. Human numerical review remains pending. This is not
a qualified release, full parasitic coverage or a speed benchmark.
