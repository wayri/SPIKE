<!-- SPDX-License-Identifier: Apache-2.0 -->
# Requested capability acceptance: 9 October 2026

This audit distinguishes implemented behavior from release qualification.
The complete coupled converter, airflow, SI and radiated-EMI workflow is not
qualified. A release must not describe these individual features as that
complete workflow.

| Capability | Current evidence and remaining limits |
| --- | --- |
| Exploded assemblies | Occurrence transforms apply to boards, their overlays and harness endpoints. Native two-board checks exercised exploded geometry. Simulation overlay alignment has focused regression checks; a native saved-result overlay check remains. |
| Multiple sections | Up to six arbitrary planes or an interior box clip board, component, harness and result geometry. Picking uses the same retained half-spaces. Native arbitrary-plane, two-plane and box views passed; clipped picking and narrow layout still require native checks. |
| Viewport performance | Cached conservative occurrence bounds cull offscreen geometry during rendering and restore it before picking. Shadow refresh bypasses culling. Batching/cache tests pass. No measured interactive speedup or hidden-face detail reduction is claimed. |
| Transient viewing/export | Saved timestamps drive playback; bounded GIF and capability-detected VP9/VP8 WebM exporters preserve returned samples. Export and cancellation tests pass. Stored playback pause is distinct from solver pause. Native encoded-video verification and correlated all-domain field histories remain. |
| Harness PI/SI | Selected-wire DC, uniform SI and bounded supplied-RLGC branched multiconductor kernels have independent checks. A narrow straight-round-wire/ideal-plane extractor is available. Full-wave harness radiation and arbitrary shields/twists are not qualified. |
| Closed-loop converter | Native finite-conductance PWM buck and cycle-sampled PI control now couple winding resistance to a lumped thermal state. Native/independent switched-ODE checks cover refinement, feedback and energy. This reference excludes vendor MOSFET switching loss, deadtime, spatial package/PCB cooling and EMI. |
| Multiboard electrothermal | Steady reduced-circuit DC and single-frequency AC resistor losses map into retained thermal volumes with temperature feedback. This does not establish arbitrary transient bidirectional E/H coupling. |
| Airflow and field coupling | The channel airflow screen and separate field adapters retain explicit validity limits. Arbitrary turbulent conjugate heat transfer plus switching-converter SI/radiated EMI remains open. |

## Reproducible demonstration artifacts

Local build artifacts are intentionally not source-controlled downloads.

- Arduino: `build/curated-multiboard-20261005/arduino/arduino-r4-relay-shield.spike`.
  Actual worker reruns reproduce saved PI, SI and thermal results and validate
  retained bindings.
- Raspberry Pi: `build/curated-release-20261009-v2/raspberry-pi/cm4io-sailor-hat.spike`.
  The rebuilt canonical active design record and retained source members fix
  the earlier reopening and missing scene-source errors. Actual worker reruns
  reproduce all three saved domains; the frozen worker reads both source
  artifacts byte for byte. Native scene acceptance remains pending. The CM4
  source has no explicit redistribution grant in its archive, so this package
  is local-use-only and is not a public release asset.
- Transient assembly thermal evidence:
  [CalculiX comparison](validation/ASSEMBLY_THERMAL_TRANSIENT_20261008.md).
- PWM derivation, reproducible commands and source-bound qualification:
  [sourced power checks](SOURCED_POWER_QUALIFICATION.md).
- Playback/export semantics and resource guards:
  [result playback](RESULT_PLAYBACK_EXPORT.md).

The new numerical changes require knowledgeable human review under
`CONTRIBUTING.md`. A new Windows candidate also requires clean packaging,
native smoke tests, offline startup and upgrade checks before publication.

## Windows candidate checks

The 0.3.9 unsigned preview EXE and MSI were built in
`artifacts/windows/installer`; their manifest records sizes and SHA-256 hashes.
Administrative MSI extraction returned zero and all 2,165 staged resource
files matched byte for byte, along with the desktop and frozen worker binaries.
The extracted CLI passed 73 help surfaces, version, inspection and structured
error checks. These are extraction/runtime checks; installation, upgrade,
uninstall and offline GUI acceptance remain unverified.

The full Python suite passed 2,969 tests with 23 skips using an external
disposable temporary directory (the earlier Git-worktree fixture error was
environmental). Rust release-profile checks passed 40 tests with one ignored
live OS-counter test; the complete release-profile Cargo command also passed
its binary and documentation targets. TypeScript and the production frontend build passed.
The restored source configuration passed architecture and documentation checks.

A fresh original two-board plus STEP thermal solve and actual CalculiX rerun
agreed within the declared tolerances across 288 nodes and five times; maximum
absolute difference was 0.011425845 K. Its new retained project reopened with a
current saved result. Exact-sample GIF and final PNG artifacts are in
`build/preview-0.3.9/demonstrations`; this scientific animation does not establish
the remaining native viewport codec/export acceptance.
