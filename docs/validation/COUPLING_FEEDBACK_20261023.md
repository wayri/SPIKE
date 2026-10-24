<!-- SPDX-License-Identifier: Apache-2.0 -->
# Coupling feedback and implementation checkpoint

Independent numerical review was requested before release integration.

| Finding | Action and acceptance evidence |
| --- | --- |
| P1: 300 MHz fields could be reused at 3 GHz after changing only the AC request digest | Captured frequency/material/network/port/mesh/run context and a separate field-packet digest are now mandatory. Stale-state regression passes. |
| Packet hashing alone could hide whether the physical rejection test executed | Corrupted volume E is rehashed in the regression; admission must still fail specifically at raw Poynting closure. |
| Sampling mesh is not proof of the interpolator's FE mesh or source authenticity | Results explicitly retain both verification flags false; no attestation or arbitrary EMerge calibration claim. |
| Live circuit path was export-only; owned engine lacks native AC | Typed passive sampled EM plus linear RLC is lowered to an exact real block and executed by the owned C++ operating-point engine. The method is named explicitly, not represented as native AC. |
| CHT must not accept caller-invented mass transport | Executed fluid-submesh velocity is mapped to shared oriented face mass flux; solid flux is exactly zero and both local mass and heat conservation are checked. |
| Frequency acceptance is not GHz PCB accuracy | New eight-frequency 1 MHz–3 GHz loaded-line test compares actual native execution to an independent spatial exponential. Geometry extraction, material/skin/proximity validity and measurement remain separate. |
| Sandbox sockets and DLL startup caused false full-suite failures/hangs | The unchanged local HTTP/TLS fixtures pass 28 tests outside the sandbox. The full suite is rerun with the same normal permissions; no test was skipped or weakened. |
| Candidate staging verified only before copying | Staged member sizes/hashes are now checked again before emitting a build config; injected copy corruption must fail. Safe nested qualification-report paths are retained. Six focused staging tests pass. |

## Executed checks and artifacts

- Combined source worker/CLI, heating, native SPICE, broadband line and CFD-route
  checks: 32 passed, zero skips in
  `build/review-feedback-focused-unrestricted-20261023.log`.
- Strict new schemas and existing schema catalog: 21 passed, zero skips.
- Nine schema-bound SI stages were genuinely replayed: 122 tests passed,
  zero skips; prior receipts were retained. Both loaded-cascade/star receipt
  corruption tests pass and the full parity ledger validates all 50 done stages.
- Fresh frozen candidate build passed its complete configured runtime probes,
  including actual owned SPICE and a nonzero-flow two-tetrahedron CHT case:
  `build/reviewed-coupling-candidate-r2-20261023/resources/`.
- Frozen/source comparison: 482 modules matched; no changed, missing or required
  missing modules in `build/reviewed-coupling-source-match-20261023.json`.
- Frozen CLI executed analytical body heating at 300 MHz:
  `build/reviewed-coupling-body-result-20261023.json`; accepted power 0.02 W,
  deposited 0.003433668723032475 W, escaping 0.016566331276965968 W,
  raw relative closure error 7.793042251596983e-14.

These generated build paths are local evidence, not redistributed qualified
fixtures. The full-suite log is `build/release-full-unsandboxed-20261023.log`;
its final status must be checked, not inferred from this checkpoint. Schema
registration also required genuine receipt replays; old source hashes were not
silently rebound. Full source-freeze, supported-platform clean-machine installer
qualification, physical correlation and knowledgeable human numerical review
remain distinct release gates. No release publication is authorized by a
successful source test or packaging probe alone.

## Full-run result and remaining qualification

The diagnostic full run completed: **4,901 tests, 3 failures, 2 errors,
83 skips** (2,383.578 s). It is not green. The two errors are the stale
loaded-cascade/star receipts subsequently replayed and passed. Two debugger
tests expired their unchanged four-second waits; both targeted tests and the
complete 16-test debugger module passed in isolation, but this is not proof
of full-suite reliability. The remaining production-build assertion observed
the active installer mutex instead of the missing-production-input message;
the installer and that assertion must be rerun sequentially. No deadline,
assertion, mutex, physical tolerance or signing check was weakened.

An additional 33-test native CHT/PWM run passed without skips, including
actual CalculiX histories. Its log is
`build/reviewed-native-cht-pwm-20261023.log`. The CHT source hashes still match
the recorded binary. The selected PWM DLL matches a historical passing record,
but current native source has changed; this is not a current-source rebuild
qualification. Optional/native/hardware skip coverage and an uncontended,
consistent-source full pass remain required. Previously approved CUDA and Xyce
deferrals are not numerical passes.

With installer compilation idle, all four implicated modules passed unchanged:
25 tests in 27.647 s, zero failures/errors/skips, recorded in
`build/reviewed-uncontended-failures-20261023.log`. This is focused recovery
evidence, not a replacement for a complete uncontended full-suite pass.

## Preview installer outcome

Both unsigned engineering-preview installers built with tests enabled. The
frontend production build passed; Rust tests reported 75 passed and one ignored.
The existing installed application was not replaced and nothing was published.

| Artifact | SHA-256 |
| --- | --- |
| artifacts/windows/installer/SPIKE_0.4.0-alpha.1_x64-setup.exe | 55ac81d35548f163e2fba7baedec60dc9b498a83443bbdff51ff016629d9bb05 |
| artifacts/windows/installer/SPIKE_0.4.0-alpha.1_x64_en-US.msi | 848f7151f239ef61bc7c8c2435e062d51d0559aa67cf5387580b3326aac56d2d |

Build log: `build/reviewed-coupling-installer-r2-20261023.log`. Administrative
MSI extraction into a fresh build directory returned zero. The actual extracted
worker passed the EM/network/resistor-thermal/owned-SPICE probe and nonzero-flow
tetra CHT probe, retaining experimental/nonproduction status. Reports:
`build/reviewed-msi-em-spice-probe-20261023.json` and
`build/reviewed-msi-cht-probe-20261023.json`.

Administrative extraction and payload execution do not establish normal install,
upgrade/rollback/uninstall, native graphical acceptance, clean-machine/offline
coverage, Linux qualification, measured correlation or production readiness.
