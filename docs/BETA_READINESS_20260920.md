# Beta readiness checkpoint — 2026-09-20

This checkpoint is not a release or installation approval.

## Implemented and checked

- SI plots expand into resizable in-app dialogs with shared cursors, Escape,
  keyboard focus containment/restoration, and nonuniform-X/letterboxing-aware
  cursor positioning. Native detached windows are not implemented by this change.
- AC retains circuit incidence and finite graph-link resistance. Unsupported
  topology-link inductance/capacitance terms are excluded explicitly. Physical
  negative inductance modes fail closed instead of being silently projected.
  The MODULAR case no longer needs the previous 50.4% matrix correction; this
  is not independent high-frequency accuracy qualification.
- Transient admission reports both configured branch and RAM-derived limits.
  Invalid native filament construction returns a structured extraction failure.
- CLI version follows the application package version.
- A hash-pinned, bounded local board-corpus import runner records import evidence.
  Two bundled boards passed import smoke tests; no third-party corpus was executed.

## Evidence

Artifacts: `artifacts/beta-validation-20260920/`.

- Full Python run during integration: 1707 tests, 9 skipped, successful.
- Final changed-path Python rerun: 51 tests passed.
- Final analytical benchmark run: 15/15 passed.
- Rust: 35 passed, 1 ignored. TypeScript and 32-copper-layer parser checks passed.
- SI plot helper/structural assertions and architecture checks passed after final edits.

The full Python run preceded the final bounded edits; focused checks cover those
edits. CLI/helper tests do not establish visual or interactive acceptance.

## Remaining blockers

- The 3314-branch MODULAR transient request passes admission at 4 GB/4000
  branches but still fails native filament geometry validation. It is not solved.
- AC topology-field exclusion needs numerical/model review and independent
  correlation; zero matrix correction alone is insufficient evidence.
- Real-board Quick SI endpoint-to-result workflow, save/reopen, and interactive
  chart verification remain pending. See `QUICK_SI_USABILITY_TARGET.md`.
- OpenFOAM execution and full thermal field qualification remain unverified here.
- KiCad Monkey corpus acquisition/licensing review and golden benchmark execution
  remain pending; see `KICAD_MONKEY_BENCHMARK_PLAN.md`.
- Required knowledgeable human numerical review remains a release prerequisite.

No installer was generated or installed in this checkpoint.
