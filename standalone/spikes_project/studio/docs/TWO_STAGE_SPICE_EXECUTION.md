# Two-stage SPICE completion plan and execution record

This plan covers the full intended product. Its initial execution is a bounded
increment, not completion of either entire stage or a release-parity claim.

## Stage 1 — compatibility and native implementation

Goal: representative manufacturer decks elaborate faithfully and execute through
the owned C/C++ solver, with every unsupported term diagnosed explicitly.

Work order:

1. Establish executable feature probes and preserve failing decks with diagnostics.
2. Complete scope/include/library/parameter semantics and source waveforms; enforce
   strict errors rather than ignored physical parameters.
3. Implement dynamic charge-conserving semiconductor models and coupled devices,
   including BJT/JFET/MOS/BSIM, WBG/IGBT/thyristor, transmission lines and magnetics.
4. Complete analysis modes and nonlinear small-signal/noise behavior; document
   dialect-specific features separately from SPICE3.
5. Close sparse transient, integration/error-control and convergence gaps. Keep
   Python orchestration distinct from C/C++ numerical execution in evidence.

Exit gate: required grammar/device/analysis corpus passes, including negative
tests and real manufacturer models. Parsing alone does not satisfy the gate.

Executed in this increment:

- Added `python -m python.spikes capabilities` with 41 positive grammar probes and
  3 strict-rejection sentinels; it reports acceptance separately from untested
  numerical and cross-engine status.
- Implemented scoped diode model declarations with local/enclosing/global lookup,
  instance-qualified model references and sibling isolation. Duplicate and
  unsupported model declarations still reject. Parameters remain numeric literals;
  this does not introduce dynamic charge or other semiconductor model families.

## Stage 2 — qualification and differentiated capabilities

Goal: establish accuracy, robustness and performance evidence, then extend the
qualified foundation without weakening it.

Work order:

1. Run textual netlists through the native path and compare to analytical results.
2. Run equal-model/tolerance decks across available reference engines; retain
   failures and unavailable-engine status. Qualify real model libraries per part.
3. Expand converter/RF/motor and pathological corpora; measure cold/warm runtime,
   memory and thread scaling across published circuit sizes.
4. Validate interactive command timing, rolling/event capture and replay. Extend
   electrothermal/magnetic and compiled-block workflows under the same gates.
5. Qualify physical SIL/PIL/HIL adapters on actual hardware; desktop timing tests
   must never be presented as hard-real-time certification.

Exit gate: required cross-engine, accuracy, scale, convergence and platform
evidence is complete. Competitor superiority requires matched benchmarks, not
small-circuit timings or a model-count comparison.

Executed in this increment:

- Added textual parser-to-native qualification for scoped parameterized divider,
  RC, RL and static diode cases, including full sampled-trace comparisons.
- Reused the existing direct-ABI qualification suite rather than duplicating it.
- Ran the suite against the existing C++ library. Missing reference engines are
  explicit; no cross-engine or hard-real-time qualification is inferred.

Commands from the source root:

```powershell
python -m python.spikes capabilities -o artifacts/capabilities.json
python -m python.spikes.compatibility_qualification --help
```

Further work remains in both stages. The capability report is representative,
not an exhaustive statement of every SPICE dialect feature.

## Measured result of this execution

- Stage 1: 22/41 positive grammar probes accepted; 19 rejected. All 3 negative
  sentinels rejected as intended. Evidence: `artifacts/two-stage-capabilities-20260906.json`.
- Stage 2: 4/4 text-deck cases and 14/14 existing direct-ABI cases passed against
  the hashed C++ library, including the newly scoped static diode path.
  Evidence: `artifacts/qualification/two-stage-20260906-final-native.json`.
- Regression: 130 standalone tests ran (1 skipped), plus 35 targeted parser/CLI
  tests passed. The skipped test requires Windows symbolic-link creation privilege.
- No ngspice executable was found on PATH or in the workspace tools directory;
  cross-engine qualification was not performed. These results do not close either
  stage's full exit gate. Dynamic devices, missing language/analysis features,
  manufacturer qualification and broader performance evidence remain required.

## Follow-on execution with ngspice

The previous unavailable-reference condition is now resolved for Linux/WSL:
Ubuntu's package-managed ngspice 42 (`42+ds-3build1`) is installed at
`/usr/bin/ngspice`. Official Windows ngspice 47 download attempts returned HTML,
not archives, and failed the upstream checksum check; none were executed.

- Added scoped static-diode model parameter expressions, per-instance binding and
  STEP-dependent values. Coverage audit now accepts 23/42 positive probes and
  still rejects 19; all strict rejection sentinels pass.
- Built current C++ source on both Windows and Linux. The development launcher
  now prefers `build-spikes-current-vs18-20260906/Release/spikes_c_api.dll`.
  Fixed explicit MSVC exception-unwinding and strict floating-point build flags.
  The earlier missing session-voltage API failure disappears with the current DLL.
- Windows: all 310 core tests pass; standalone tests: 131 pass, 2 skipped. The
  actual dashboard's 13 checks pass with the fresh DLL, including native control,
  pause/resume and clean worker stop.
- Linux: four analytical text-deck comparisons against ngspice pass, including
  5,000 compared samples each for RC and RL. Reference settings and interpolation
  are recorded; tighter reference tolerances are not described as equal tolerances.
- Shared nine-case corpus: SPIKES 9/9 and ngspice 9/9 pass. LTspice remains
  unavailable, so the complete competitive report stays blocked.
- One process-per-case timing observation was approximately 330 ms median for
  SPIKES versus 22 ms for ngspice. This includes startup/result handling, is not a
  kernel-throughput comparison, and is not a speed advantage.

Evidence: `artifacts/ngspice-reference-20260906/scoped-traces.json`,
`artifacts/ngspice-reference-20260906/competitive.json`,
`artifacts/two-stage-capabilities-model-params-20260906.json`, and
`artifacts/studio-dashboard-current-core-20260906/checks.json`.
Both full-stage exit gates remain open. The installed GUI release has not been
replaced; these changes and the current native builds are development artifacts.
