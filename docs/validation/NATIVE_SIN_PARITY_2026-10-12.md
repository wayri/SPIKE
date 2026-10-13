# Native SIN compatibility checkpoint (2026-10-12)

Status: bounded experimental increment; complete ngspice parity remains blocked.

## Implemented boundary

Owned C++ SIN voltage/current source evaluation now occurs at every internal
transient solve time. There is no Python sampled-waveform substitution. Exact
delay boundaries enter the existing breakpoint scheduler. Persistent sessions
carry the global-time offset into analytic evaluation and preserve checkpoint
replay. The additive C ABI uses symbol-based capability checks without changing
ABI version 1; loading an older library remains possible for other devices,
but using SIN requires rebuilding and fails explicitly if unavailable.

Phase-before-delay behavior now holds `VO + VA*sin(PHASE)` in the native and
Python reference routes. Earlier code held VO, creating a false step at TD for
nonzero phase. Parameters remain bounded to explicit positive FREQ, nonnegative
TD/THETA and finite values. Analysis-dependent frequency defaults are not added.

## Method, units, independent oracles and conditioning

Source semantics derive from the public
[ngspice 46 manual, sections 4.1.2 and 4.1.10](https://ngspice.sourceforge.io/docs/ngspice-46-manual.pdf).
Implementation, fixtures and prose were independently authored; no upstream
implementation source or examples were copied or adapted.

Set `u=max(0,t-TD)` in seconds. The source value is
`VO + VA*exp(-THETA*u)*sin(2*pi*FREQ*u + PHASE*pi/180)`; FREQ is Hz, THETA is
inverse seconds, PHASE is degrees and VO/VA are volts or amperes. Native phase
reduction avoids multiplying a large phase by pi. No matrix/Jacobian changes
are introduced: independent-source values modify only the existing MNA RHS.
The delay changes derivative, not value, and restarts integration through the
existing event mechanism. Extremely ill-scaled time/frequency products remain
subject to finite-result failure; no frequency-resolution qualification is implied.

The independent zero-state RC oracle is
`[sin(w*t)-w*tau*cos(w*t)+w*tau*exp(-t/tau)]/[1+(w*tau)^2]`, with
`tau=R*C=100 us` and `w=2*pi*1000 rad/s`. Existing fixed-step BE refinement and
new adaptive-BDF2 maximum-step/tolerance refinement test actual loaded-node errors. Direct
source values are checked at every irregular internal point, independently of
the implementation's sine evaluator. Native persistent tests verify exact replay.

## Runnable verification

Configure a separate regression build to avoid replacing another task's DLL:

```powershell
cmake -S tests/native_spikes -B build-spikes-sine-20261012 -G "Visual Studio 18 2026" -A x64 -DEigen3_DIR=C:/Users/yawar/Documents/agws/Autoplacer/vcpkg/packages/eigen3_x64-windows/share/eigen3
cmake --build build-spikes-sine-20261012 --config Release --parallel 2
ctest --test-dir build-spikes-sine-20261012 -C Release --output-on-failure
$env:SPIKES_TEST_NATIVE_LIBRARY = (Resolve-Path build-spikes-sine-20261012/Release/spikes_c_api.dll).Path
$env:SPIKES_TEST_NGSPICE = (Resolve-Path runtime/external/Spice64/bin/ngspice_con.exe).Path
python -m unittest tests.python.test_spikes_sine_source tests.python.test_spikes_exp_sffm_source -v
python -m unittest discover -s tests/python -p 'test_spikes*.py' -q
python scripts/check_architecture.py
```

Paths are this Windows development environment, not portable requirements.
No numerical release or performance claim is made from a local build.

Executed native DLL SHA-256:
`2CC08782E6A1503BD268288DC3488E2BC05841DC764DD321D5AD9E600A9A9682`.
Reference ngspice 46 executable SHA-256:
`86C9EA5F645CA919E305639FA7BDB522355364C424D14E197F1ADE617FEB3453`.

Executed evidence: all eight native regression executables pass with assertions
enabled, including adaptive SIN current/voltage and session replay checks.
The 18-test focused SIN/EXP/SFFM suite passes with actual native execution and three
same-deck ngspice 46 comparisons. The delayed phased voltage and current decks
use 100 ns requested/reference maximum step over 1 ms; the loaded RC deck uses
the same grid. Full in-domain traces must remain within 50 microvolts after
reference-to-native linear interpolation. UIC's missing reference time zero is
explicitly excluded, never extrapolated. The original 1 us grid straddled TD
in ngspice and produced approximately 407 microvolts interpolation error at
the derivative kink; refinement corrected that error without relaxing the gate.
Native and ngspice internal tolerance semantics are not asserted equivalent.

Architecture and changed-file whitespace checks pass; the shared Python native
MNA suite passes all 15 tests. Final SPIKES discovery
completes 445 tests successfully with 15 explicit skips. The first discovery
attempt lacked `jsonschema`; the repository-pinned `jsonschema==4.25.1` and its
dependencies were installed only into `.tmp/spikes-validation-deps`, then
selected through `PYTHONPATH` for the passing rerun. No global environment was
changed. Reproduce that setup with `python -m pip install --target
.tmp/spikes-validation-deps jsonschema==4.25.1` and set `PYTHONPATH` to the
resolved target folder if the development interpreter lacks the dependency.
The new startup refinement test was corrected as described below before this
final run. Skipped tests are not validation evidence; this circuit-subsystem
run is not the entire repository, frontend, packaging or platform release gate.

The startup/event BE step has no embedded defect estimate in the existing
integrator. Tightening only LTE tolerances cannot repair the first-step error
from an oversized maximum step. The RC test therefore refines the maximum
step from 20 us to 5 us along with the tolerance; this limitation is retained,
not hidden by dropping early samples or changing integrator behavior.

## Remaining compatibility work, in order

1. Extend direct native analytic evaluation and event handling to EXP/SFFM;
   remove their documented fixed-grid PWL approximation only after equivalent
   adaptive/refinement and cross-engine traces pass.
2. Add analysis-dependent source defaults and combined DC/AC/transient source
   cards with OP semantics, contract round trips and rejection fixtures.
3. Expose native AC/noise/pole-zero/sensitivity pathways only when executable
   native kernels and per-device linearization/noise models are qualified.
   Python-reference analysis and external ngspice remain distinct backends.
4. Complete model-card and device families (including opposite semiconductor
   polarities, distributed/coupled devices, and charge/temperature/noise
   coverage) against explicit equal-model corpora. Current compiled compact
   extensions do not imply general manufacturer-library compatibility.
5. Grow adversarial, scaling, platform and redistributable-model qualification;
   retain the ten blocked competitive-release gates until evidence closes each.

No full SPICE architecture completion, whole-product parity, speed superiority,
hard real-time or HIL qualification is established. Numerical changes require
knowledgeable human review before release. GUI acceptance and full-repository
gates are separate from these native/source tests.
