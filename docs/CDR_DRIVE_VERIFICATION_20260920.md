<!-- SPDX-License-Identifier: MIT -->
<!-- Copyright (c) 2026 SigHarmonic -->
# Loaded NRZ recovery and reciprocal voice-coil verification

This increment adds optional transition-PI timing recovery to the full-resolution
loaded SI waveform and a standalone linear electrical/mechanical voice-coil
drive. They are executable bounded models, not complete Ethernet or arbitrary
actuator qualification. See [CDR](SI_CLOCK_RECOVERY.md) and
[drive equations](VOICE_COIL_DRIVE.md) for derivations, units and limitations.

## Verification feedback and results

- Full Python discovery with warnings treated as errors: **1,808 tests,
  zero failures/errors, two skips**, 362.290 seconds. This is a shared-workspace
  snapshot, not exclusively tests authored in this increment. The subsequently
  added example/schema regressions are also covered by the 24-test focused run.
  Final architecture and recorded-reference inventory checks passed.

- Integration exposed NumPy histories that were not JSON serializable; the SI
  adapter now converts histories to lists. A strict serialization regression
  exercises the actual loaded workflow.
- Extreme integer and time-range tests exposed uncaught conversion/overflow
  behavior; these now fail with explicit validation errors under warnings-as-errors.
- The drive CLI now bounds its input read before parsing. Convergence comparison
  scales current, position and velocity independently rather than mixing units.
- The constant midpoint propagator is reused. Independent review checked the
  reciprocal signs and energy identity; a separate negative-coupling closed-form
  check showed convergence ratios 3.99907 and 3.99977.
- The checked 10.3125 GBd matched-line PRBS7 example recovered **894 checked
  symbols with zero observed errors**, with no frequency-bound hits. This finite,
  deterministic observation is not a statistical BER bound or compliance claim.
- The 500-step voice-coil example's energy-balance residual was
  **1.8865e-17 J**. Analytical RL response, lossless energy and timestep
  convergence are separately tested; energy balance alone cannot prove accuracy.
- Focused core, integration and schema run: **24 tests passed**, warnings treated
  as errors. The architecture guard passed once, then a later snapshot flagged
  an unrelated concurrent `app/src/contourField.ts` spread-extrema change.
  A subsequent rerun passed again. No architecture gate was relaxed here;
  shared-workspace checks must be rerun on the final release snapshot.

## Reproduction

From the repository root, use the documented qualification Python environment:

```powershell
build/qualification-py311/Scripts/python.exe scripts/qualify_cdr_workflow.py
build/qualification-py311/Scripts/python.exe -m python.spike_core.voice_coil_drive --request examples/actuator/voice-coil-drive.json --result build/voice-coil-drive-result.json
build/qualification-py311/Scripts/python.exe -W error -m unittest tests.python.test_si_cdr_workflow tests.python.test_si_clock_recovery tests.python.test_voice_coil_drive tests.python.test_voice_coil_drive_schema -q
```

Local reports and the broader regression log are retained under
`build/cdr-drive-20260920/`. The environment uses CPython 3.11 with supplemental
system packages; it is not a hermetic clean-machine release qualification.
The local manifest binds the numerical sources, tests, schemas, examples and
focused result artifacts by SHA-256; it is integrity evidence, not a signature.

## Remaining scope

This is not a full BASE-T PHY, KR/SFI electrical receiver compliance model,
adaptive equalizer/training system, geometry-derived nonlinear actuator or
measured device correlation. The CDR is offline threshold-transition feedback,
not Gardner or a transistor-level receiver. Voice-coil parameters and terminal
voltage are constant. Human numerical review remains required before release.
No unsupported capability was enabled merely because its unit tests passed.
