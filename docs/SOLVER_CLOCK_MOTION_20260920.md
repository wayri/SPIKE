<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright (c) 2026 SigHarmonic -->
# Executable clock and actuator-motion increment

This follows the earlier [verification feedback](SERDES_ACTUATOR_VERIFICATION_20260920.md).
It fixes implemented numerical behavior and adds bounded mechanics; it does not
declare completion of all Ethernet PHYs or actuator field extraction.

## Changes driven by failing checks

1. Reproduced NRZ rate drift and rejected nonintegral samples/UI. Added a shared
   continuous-time symbol clock to loaded and normalized NRZ paths. Ramps and
   fractional source delays use physical event times; receiver interpolation
   never extends beyond the record. Nominal display samples and actual fractional
   samples/UI are reported separately. See [SI workflow](SI_WORKFLOW.md).
2. Reproduced dense Touchstone export/reimport rejection: 12-digit rounding
   destroyed uniform frequency spacing. Changed export to binary64-roundtrip
   17-digit precision, without loosening the uniform-grid admission tolerance.
3. Added [1DOF actuator motion](ACTUATOR_MOTION.md) from admitted force maps,
   with mass, spring, damping, work/energy accounting and finite stroke.
4. Independent review exposed final-step roundoff causing a velocity jump, and
   missed leave-and-return stroke crossings. Added regressions, indexed the time
   grid with an ulp-aware step count, and solved both stroke event quadratics for
   the earliest positive midpoint-family crossing. Review reran both examples
   successfully after correction.
5. Split exact piecewise-linear map work from midpoint quadrature work, so a
   small discrete energy residual cannot hide force-work integration error.

## Executed evidence

- Full Python discovery: **1,771 tests, zero failures/errors, two skips**,
  291.027 seconds. Log: `build/solver-clock-motion-20260920/python-suite.log`.
  This is the full-run snapshot; subsequent shared normalized-clock/schema
  additions were covered by the latest targeted run recorded in the manifest.
- All six SERDES refinement grids preserve exactly **10.3125 GBd**. Additional
  4,097/8,193-point runs reduce the final eye change to about **7.14 microvolts**,
  below the unchanged 0.2mV engineering gate. All earlier levels are retained;
  this delta is not an absolute solution-error bound.
- Independent continuous-time RC ODE comparison: eye errors at 16/32/64/128
  samples/UI are approximately **18.54/12.17/4.73/2.44 mV**. The last passes
  the 5mV target; coarse levels do not. No production threshold was relaxed.
- Three actuator-class examples compare against the independently derived
  forced damped oscillator. Maximum displacement error is about **2.43e-9 m**;
  each also satisfies a relative displacement check. Normalized energy balance
  is checked as well as the absolute residual, including the tiny electrostatic
  example. Results are in `actuator-motion-reference.json` in the evidence folder.
- Motion tests check oscillator timestep convergence, malformed/extreme input,
  nonunique steps, stroke events, force-knot quadrature and public schema/example.

Reproduce from the repository root with the documented CPython 3.11 environment:

```powershell
build/qualification-py311/Scripts/python.exe scripts/qualify_serdes_reference.py
build/qualification-py311/Scripts/python.exe scripts/qualify_actuator_motion.py
build/qualification-py311/Scripts/python.exe -m unittest tests.python.test_si_exact_clock tests.python.test_actuator_motion -v
```

The evidence folder's manifest binds current numerical sources, tests, reports
and the full-run log by SHA-256. No source commit or remote was created.

Remaining implementation: BASE-T PHY/DSP/coding, interface-specific receivers,
dynamic CDR/training and normative qualification, actuator geometry-to-field
generation and coupled electrical drive/back-EMF, plus matched independent and
measured system validation. These are not features that a passing unit suite
can create or certify; see [delivery plan](SERDES_ACTUATOR_DELIVERY.md).
