# Text-deck and native-kernel evidence

The owned engine must pass both the text input path and the lower-level C ABI.
The new deck runner supplements, rather than replaces, the existing 14-case
native qualification suite.

From the repository root:

```powershell
python -m python.spikes.compatibility_qualification --library build-spikes-standalone-beta1-vs/spikes_c_api.dll --include-direct-abi --repetitions 2 -o artifacts/qualification/my-fresh-report.json
```

Output files are not overwritten. The report includes the exact decks, source
and library hashes, convergence diagnostics, absolute-error gates, first and
subsequent in-process timings, and explicit claim limitations.

## Executed evidence

`artifacts/qualification/two-stage-20260907-native.json` records 4/4 text-deck
checks and 14/14 existing native-ABI checks passing on the actual Windows DLL.
The date in the filename is a batch identifier; the authoritative timestamp and
host are embedded in the JSON.

| Text deck | Reference | Maximum absolute error |
|---|---|---|
| Parameterized, scoped resistor divider | 20/3 V | 8.89e-16 V |
| RC charging, all 5,000 returned samples | 1-exp(-t/RC) | 4.992e-7 V |
| RL charging, all 5,000 returned samples | (V/R)(1-exp(-tR/L)) | 4.992e-8 A |
| Current-biased static diode | n k T/q ln(1+I/Is) | 2.588e-11 V |

The existing ABI corpus covers resistor scaling, sparse and iterative methods,
an RLC transient, lumped RF resonator, fixed-speed motor armature, simplified
switching circuits, checkpoint/replay, continuous pacing and deadline trips.
Its precise fixture limitations remain in the report. These are not production
semiconductor, general motor, RF distributed-model or hardware-HIL qualification.

## What this does not establish

- The original Windows-only report did not find ngspice. The newer WSL run below
  records actual cross-engine results; it does not retroactively change that report.
- No MATLAB, PSIM, PLECS, LTspice or QSPICE performance comparison was made.
- Timings include Python parsing, library load, construction and extraction.
  The first call is not an OS-cache-cold benchmark; peak memory is not measured.
- Four text decks do not establish complete SPICE syntax or manufacturer-model
  compatibility. Unsupported families require their own executable cases.
- Real-time pacing on a desktop OS is not hard-real-time/HIL certification.

Tests: `test_compatibility_qualification.py` requires `SPIKES_TEST_LIBRARY` for
the native test, otherwise that test is explicitly skipped. No reference solver
is silently substituted when the native library is absent.

## Actual ngspice reference run

Ubuntu/WSL ngspice 42 was run against the current-source Linux C++ library.
`artifacts/ngspice-reference-20260906/scoped-traces-v2.json` retains both engines'
complete scalar/trace values, exact submitted decks, executable/library hashes,
version, tolerances and coverage. Its embedded timestamp is authoritative.

```bash
python3 -m python.spikes.compatibility_qualification \
  --library build-spikes-linux-reference-20260906/libspikes_c_api.so \
  --ngspice /usr/bin/ngspice --repetitions 1 \
  -o artifacts/qualification/new-ngspice-report.json
```

| Identical circuit/model fixture | Compared samples | Maximum SPIKES–ngspice difference |
|---|---:|---:|
| Scoped divider | 1 | 0 V |
| RC charge | 5,000 | 4.991258e-7 V |
| RL charge | 5,000 | 4.991258e-8 A |
| Scoped diode with IS/N instance overrides differing from defaults | 1 | 1.819072e-7 V |

All four passed their pre-existing absolute-error gates. Reference traces are
linearly interpolated onto native times, never extrapolated. The runner permits
only a reported omitted zero-time UIC sample; all other missing native-domain
coverage fails qualification. This run excluded no native samples. Numerical
settings are deliberately explicit: ngspice uses tighter reference tolerances
and a maximum step equal to native requested spacing. This is **not** a claim
that both engines have equivalent adaptive algorithms or identical tolerances.
The static diode test does not establish dynamic charge/noise model equivalence.

The existing nine-case competitive harness was also executed, recorded in
`artifacts/ngspice-reference-20260906/competitive.json`: SPIKES **9/9** and
ngspice **9/9** passed; the overall three-engine gate remains **blocked** because
LTspice was unavailable in WSL. These include ideal PWM-LC, passive RF RLC and
electrical motor-armature surrogates, not physical converter/motor qualification.
With one repetition, median case process-launch timings were approximately
330 ms for the Python-launched SPIKES workflow and 21.5 ms for ngspice. This
exposes startup overhead, not warm C++ solver throughput; no speed advantage is
claimed. Medium/large, memory and multicore qualification are still missing.

All five qualification tests pass with both `SPIKES_TEST_LIBRARY` and
`SPIKES_TEST_NGSPICE` set. Explicit ngspice failures fail the report; reference
execution never substitutes for owned native execution.
