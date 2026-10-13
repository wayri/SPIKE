# Internal SPICE fault and timing-control increment, 2026-10-10

This is development evidence for an owned bounded fixture, not a release,
whole-engine parity, real-time guarantee or hardware reliability qualification.

## Implemented boundaries

- Native persistent-session ordinary resistor and Level-1 NMOS VTO edits.
- Generated RLC/constant-source/static-diode/static-NMOS board objects with
  declared finite-shunt/VTO fault descriptors, isolated instances and replay.
- Explicit fault schedules, conditional supplied FIT/Weibull hazards and
  bounded temperature/dose/humidity/vibration parameter mappings.
- `.tran` TSTART/TMAX integration/output controls with rolling-capture and
  recorded-sample measurement compatibility preserved.

See [electrical and reliability limits](../SPICE_FAULT_RELIABILITY.md),
[compiled package contract](../COMPILED_BOARD_LIBRARY.md) and
[transient controls](../INTERNAL_SPICE_TRANSIENT_CONTROLS.md).

## Actual checks

| Check | Result |
| --- | --- |
| Five static fault configurations: direct native, generated board DLL, ngspice 46 | Pass, 1 microvolt absolute tolerance; [exact decks and hashes](spikes-fault-ngspice46-2026-10-10.json) |
| Existing four-deck compatibility qualification with direct ABI evidence | Pass; `build/spice-fault-checks/deck-ngspice46.json` |
| C++ fault/state regression executable | Pass |
| Actual compiled-board/C++ firmware regressions | 20 pass |
| Reliability/environment unit and arithmetic checks | 12 pass |
| Campaign contract and actual native RC/dose/VTO checks | 8 pass |
| Final timing-control/source/measurement/Studio regressions | 45 pass in the focused follow-up |
| Complete fresh SPICE subsystem suite against the rebuilt current native engine | 394 tests: 379 pass, 15 skipped; `build/spice-fault-checks/spikes-integrated.log` |
| Complete Studio suite with the fresh owned DLL and ngspice executable | 236 pass, 2 skipped (host symlink and opt-in cursor widget); 238 total |
| Actual compiled environment mapping and campaign replay after final unit/baseline validation | Pass |
| Rust `cargo test -j 1` | 44 pass, 1 ignored |
| Architecture, button standard, TypeScript no-emit and frontend parser | Pass |

Full root Python discovery began before the final timing-control follow-up:
3170 tests, 3 failures and 41 skips. Its log is
`build/spice-fault-checks/root-full.log`. It is not a passing gate:
Python debugger session-startup checks failed, and the earlier native grid
regression appeared before the final fix. The final focused timing/control and
Studio suites above exercise the corrected code. A focused debugger rerun
also timed out in a different session-startup case; this remains unresolved
outside the changed SPICE subsystem. No checks were weakened.

A subsequent 394-test SPICE sweep initially found three unsupported behavioral
opcodes in the earlier DLL. The shared behavioral source had been extended after
that DLL's build. A separate build from current source resolves those three
cases, including their ngspice comparisons, without replacing the earlier DLL
or invalidating the verified compiled fault-board manifest.
The integrated engine is
`build-spikes-integrated-20261010/Release/spikes_c_api.dll`, SHA-256
`92aba9e4a561f329494cc185f5517e5ca6662b6902f9cc76d61ce411b0629761`.

The compiled fault-fixture's owned native engine SHA-256 is
`3da429f5b5a0d415f26b58a44ed47a7aeb37f08139979182c79f7ef441144b89`.
The retained board package is
`build/compiled-board-fault-demo/fault_board/manifest.json`.
Generated artifacts require their exact recorded engine and a trusted native
package. Numerical human review before release remains required.
