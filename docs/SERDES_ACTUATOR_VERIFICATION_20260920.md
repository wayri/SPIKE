<!-- SPDX-License-Identifier: MIT -->
<!-- Copyright (c) 2026 SigHarmonic -->
# Executed SERDES / actuator verification feedback

Follow-up: [clock correction and executable actuator mechanics](SOLVER_CLOCK_MOTION_20260920.md)
implements the physical-rate fix and records the next verification/correction cycle.

## Runs

- Full public Python discovery: **1,747 tests, zero failures/errors, two skips**,
  326.981 seconds, CPython 3.11 supplemental qualification environment.
  Command: `build/qualification-py311/Scripts/python.exe -W error -m unittest discover -s tests/python -q`.
  Log: `build/actuator-review-20260920/python-suite.log`.
- Latest targeted modules: **16 tests pass** (actuator map, actuator reference,
  SERDES reference), after the added schema/example and refinement checks.
- Architecture guard passes. All new documentation's local links resolve.
- Three actuator example CLI invocations exit successfully and return
  `consistent`. Their output is in `build/actuator-review-20260920/`.
- Actuator verification report: **11 runs, nine passing criteria**, including
  the three deliberately reversed-force rejection checks. Refinement error
  ratios are approximately `3.88, 3.94, 3.97` for both gap models, consistent
  with second-order stroke differentiation.
- SERDES reference runs check the loaded complex gain, RC transfer, matched
  eye amplitude, representable rate and rejection of insufficient bandwidth.
  Matched eye absolute error is approximately `5.45e-13 V` against `0.4 V`.

Generated artifacts are local evidence, not guaranteed to exist after cloning.
Regenerate with `scripts/qualify_actuator_reference.py` and
`scripts/qualify_serdes_reference.py`; both emit machine-readable criteria and
return nonzero on failed checks. Artifact manifests and source identities are
recorded in `build/actuator-review-20260920/evidence-manifest.json`.

## Feedback applied, not waived

1. Independent review reproduced a nonfinite force/mass result from finite
   extreme inputs. All derived summaries now undergo numerical-range checks;
   a regression verifies clean rejection instead of a later JSON failure.
2. Huge integer excitation and unhashable actuator kind leaked unintended
   exceptions. Explicit type/conversion admission now rejects them with
   `ValueError`; regression cases pass.
3. Comparing two eye outputs alone could accept a shared error. Added an
   independent absolute `0.4 V` matched-load/attenuation oracle.
4. Changing 8/16 samples/UI also changes bandwidth and period. The report now
   calls this sensitivity, not convergence.
5. Fixed-bandwidth frequency refinement still changes the represented symbol
   rate because the existing waveform generator rounds samples/UI. The drift
   must be reported; contracting eye deltas are not a controlled physical-rate
   convergence proof or an error bound. A rate-preserving waveform resampler
   and separate fixed-band/fixed-rate verification remain implementation work.

## What these tests establish

These are executed software and bounded analytical checks, not verification of
every advertised or planned physics mode. No inference is made from skipped
tests. Hardware limits require the applicable specification and experimental
uncertainties, not a tolerance selected to fit a run. Private force kernels
were inspected for interface availability but were not built or tested here.
The public review consumes maps; it does not replace the missing field adapter.

The [delivery plan](SERDES_ACTUATOR_DELIVERY.md) identifies the distinct missing
KR, SFI/XFI, BASE-T and three actuator workflows. In particular, BASE-T PHY
algorithms and arbitrary-geometry actuator field/motion workflows cannot be
verified by rerunning these different, already implemented models. They need
implementation, matched oracles and a new execute/compare/correct cycle.
