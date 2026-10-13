# Internal SPICE and schematic development

The development target is ngspice compatibility and a substantially more usable
KiCad-inspired schematic editor. Whole-product parity remains blocked. This
document orders the remaining work; it does not promote planned capabilities.

## Ownership and acceptance

`python/spikes/` owns deck contracts, parsing and reference orchestration;
`src/spikes/` owns the internal numerical kernel. The separate SPIKES Studio
editor lives in `standalone/spikes_project/studio/python/spikes_studio/`.
The SPIKE desktop SPICE workbench is a separate integration surface.

Every compatibility increment must exercise the submitted text deck, serialized
contract and execution route. Parser acceptance, reference execution, owned
kernel execution and ngspice comparison are separate evidence. Preserve explicit
unsupported states and compare equivalent circuit/model values with stated
tolerances before making numerical or performance claims.

`capability_audit.run_capability_audit()` is a bounded grammar inventory, not a
qualification suite. Its include/library probes now create an actual top-level
deck so filesystem admission does not masquerade as missing grammar support.
`compatibility_qualification.py` and `parity_report.py` retain the stronger
execution and release gates. Do not weaken those gates to improve counts.

## Next engineering milestones

The 2026-10-12 [native SIN increment](validation/NATIVE_SIN_PARITY_2026-10-12.md)
replaces SIN's sampled-PWL native path with analytic internal-step evaluation,
delay breakpoints and persistent global time. EXP/SFFM still use PWL lowering.
This is one tested source-family increment, not full SPICE compatibility.

The current increments add [bounded SIN/EXP/SFFM sources](INTERNAL_SPICE_SOURCE_WAVEFORMS.md)
and continuous orthogonal wiring with Move/Drag and explicit branch junctions in
[Studio's workbench](../standalone/spikes_project/studio/docs/WORKBENCH_GUIDE.md).
EXP/SFFM native source execution still lowers to PWL on the requested grid;
direct native SIN evaluation does not establish full source-language parity.

The [compiled internal-engine board preview](COMPILED_BOARD_LIBRARY.md) adds an
instantiable C/C++ electrical object and Python client for bounded RLC/constant
sources, static Shockley diodes and Level-1 NMOS. Explicit finite-shunt and VTO
faults work in native sessions and compiled objects, with event/checkpoint
orchestration and supplied reliability/environment scenarios; see
[fault scope and evidence](SPICE_FAULT_RELIABILITY.md).
[Research and extension order](BOARD_LIBRARY_RESEARCH.md)
separate that implemented boundary from future FMI, emulator, protocol and
external-engine adapters. A faithful populated board requires the actual
device models, circuit and firmware target; compilation cannot supply missing
physics.

| Workstream | Next complete increment | Acceptance evidence |
| --- | --- | --- |
| Source language | Extend bounded SIN/EXP/SFFM to omitted analysis-dependent defaults, remaining sources and adaptive breakpoints | Independent waveform equations, parser rejection cases, loaded-circuit convergence and ngspice traces |
| Transient controls | Extend implemented TSTART/TMAX grids to adaptive smooth-source integration | Preserve start-window retention, maximum-step enforcement, event alignment, convergence and contract round trips; see [implemented controls](INTERNAL_SPICE_TRANSIENT_CONTROLS.md) |
| Analysis language | Expose existing bounded analysis kernels through supported deck syntax, one mode at a time | End-to-end AC/noise/transfer/pole-zero/sensitivity decks; unsupported device and excitation cases fail explicitly |
| Device compatibility | Bind supported charge models and broaden controlled compact-device cards | Charge conservation, Jacobians, bias/transient/noise coverage and equal-model reference comparison |
| Coupled and distributed devices | Implement coupled inductors and transmission-line families as separate numerical milestones | Passivity/energy, reciprocal coupling, delay and termination oracles, conditioning and ngspice comparisons |
| Schematic connectivity | Extend explicit terminal-to-wire branches to richer wire-to-wire/junction workflows | Crossings remain distinct unless joined; stable node identity; undo/redo and save/reopen preserve netlists |
| Compiled board objects | Extend the bounded RLC/static-semiconductor fault package with qualified charge models and a supplied board/firmware target | Actual compiled consumers, independent physics/time refinement, instance isolation, restart, pin failures and exact engine binding |
| Schematic interaction | Extend Move/Drag and continuous orthogonal wiring to richer selection and placement | Cancellation leaves document unchanged; preview matches commit; shortcuts share availability rules |
| Symbol and hierarchy workflows | Improve searchable symbol placement, pins, hierarchy and model mapping | Ordered pin identity, transformed hit testing, deterministic netlist generation and unresolved-model recovery |
| Product qualification | Grow representative compatibility, robustness and scaling corpora | Reproducible engine/version hashes, complete output coverage, accuracy before timing, platform evidence |

These are ordered development slices, not a declaration that all ngspice
models, dialects or analyses are implemented. Numerical changes require
knowledgeable human review before release under `CONTRIBUTING.md`.

## Verification workflow

The 2026-10-10 fault/control increment adds actual native parameter edits,
compiled fault objects and an ngspice 46 reference comparison. Five owned static
fault configurations pass a 1 microvolt cross-engine tolerance in the
[retained report](validation/spikes-fault-ngspice46-2026-10-10.json).
The C++ fault regression executable, 20 compiled-board regressions, 12
reliability/environment checks and 8 campaign checks pass. Final Studio checks
pass 236/238, with the symlink and opt-in cursor widget checks skipped; this is
not native visual acceptance or release qualification. The transient-control
follow-up restores rolling capture and preserves Studio sample-weighted
reductions while the core runner explicitly uses time-weighted reductions.
Rust checks pass 44 tests with 1 ignored; architecture, TypeScript and parser
checks pass. A separate current native rebuild passes all 394 SPICE subsystem
tests (15 skipped), including updated behavioral-source/ngspice comparisons;
the verified compiled fixture retains its original engine hash. Broader Python
gate status is recorded in the
[fault-increment validation note](validation/SPICE_FAULT_INCREMENT_2026-10-10.md);
whole-product parity remains blocked.

Run focused engine/editor regressions while iterating, followed by architecture,
root Python and Studio suites. The repository's contribution gates also include
TypeScript, frontend parser and Rust host checks. Configure actual native-library
and reference-executable paths when testing those routes; skipped tests are not
native or cross-engine evidence.

Native Studio visual acceptance remains necessary: exercise wide and narrow
windows, long names, visible inspectors, wire previews, shortcut placement,
cancellation and saved-project reopening. Model tests and screenshots from a
different interface cannot establish those interactions.

## Current increment evidence (2026-10-10)

- Focused engine suites: 68 tests passed, including SIN execution against
  `build-spikes-current-vs18-20260906/Release/spikes_c_api.dll`, reactive RC
  step refinement, contract/parser tests, capability-audit regressions and
  affected MNA/transient/native-CLI regressions.
- Studio suite: 233 tests completed successfully, with 33 explicit skips for
  optional/native prerequisites. This is model/workflow evidence; native visual
  acceptance was unavailable in this session.
- Architecture, TypeScript, frontend parser and button-standard checks passed.
- Root Python suite: 3,067 tests completed with 24 errors, one failure and
  26 skips. Many errors were memory/disk exhaustion; the run is not a passing
  project gate. The worktree failure came from putting a non-repository fixture
  inside this checkout; all five worktree tests passed when rerun with scratch
  files outside Git. Full-suite resource/runtime errors still require resolution.
- Rust host tests could not build: the parallel attempt exhausted paging
  capacity; a single-job retry failed for insufficient disk space. No Rust
  implementation was changed by this increment.
- No new ngspice cross-engine SIN comparison is established by these checks.

The native library above is an existing local build, not a rebuilt or packaged
release. These checks do not waive the remaining compatibility, visual,
packaging or knowledgeable numerical-review gates.

## Compiled-board, additional sources and junction increment (2026-10-10)

- The integrated `test_spikes*.py` suite completed 337 tests successfully, with
  eight compiled-board native tests skipped in that general environment. The
  final compiler-enabled board suite passed all 12 tests, including the linked
  C++ consumer, continuous RC refinement and failed-solve rollback. The raw log
  is `build/compiled-board-demo/native-verification.log`; see the
  [compiled-board evidence](COMPILED_BOARD_LIBRARY.md).
- The shared native-MNA suite completed all 15 tests successfully. Source checks
  include actual owned-DLL execution and EXP-driven RC timestep refinement;
  ngspice trace comparison remains unestablished.
- Studio completed 237 tests successfully, including branch/source identity,
  crossings, undo, transformations and save/load; 33 optional/native tests were
  skipped. Native visual acceptance remains unavailable.
- TypeScript and frontend parser checks passed. The latest architecture check
  failed because the separately changed `python/spike_core/service.py` has 803
  lines, above the 800-line guard. No changes to that file were made by this
  increment.
- Earlier whole-repository Python and Rust failures above remain unresolved.
  Focused passing suites are not a passing release gate.

The compiled wrapper is built and tested against the existing local owned
engine. Cross-platform packaging, a supplied complete board/firmware target,
broader device admission and numerical human release review remain pending.
