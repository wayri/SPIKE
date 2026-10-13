<!-- SPDX-License-Identifier: Apache-2.0 -->
# PDK/TCAD foundation and native acceleration checkpoint

Host: Windows, MSVC 19.51 C++20 Release, Python 3.14; date 2026-10-13.
This is development evidence, not foundry qualification or a released installer.

Built `spikes_tcad.lib`, `spikes_tcad_console.exe`, the accelerated
`spikes_c_api.dll`, and relevant native test executables with strict FP for
the new kernels/tests. CTest passed all six selected executables:
behavioral evaluator, TCAD equilibrium, SMPS analytical model, circuit DC,
transient and transient session.

Combined Python suite: 67 tests passed, no skips. Modules exercised local PDK
inventory/workflow, actual ngspice execution of an original synthetic NMOS
fixture, equation devices, package parasitics, SMPS CLI, TCAD console, existing
multi-terminal models, native CLI and transient contracts/results. Additional
PDK output protection regression verified model/config preservation. No real
SKY130/GF180/IHP model was installed or qualified.

The native TCAD 401-node PN regression met contact-potential and convergence
oracles. The actual default 501-node JSON artifact
`artifacts/spikes-tcad-pn-20261013.json` reports six accepted steps and normalized
residual 3.39e-13 against requested 1e-10. Manufactured-solution tests establish
second-order potential/face-field refinement and finite-volume Gauss balance.
See SPIKES_TCAD_EQUILIBRIUM.md for limits and a retained stagnation example.

The native behavioral benchmark preserves exact legacy values/gradients and
lazy branches, passes four-thread checks and reports zero warm cache allocations
versus 200 per 100 legacy calls. Worker repeated paired runs measured mean
1.43x evaluator speedup (range 1.356..1.533). A parent execution measured legacy
167.724 ms +/-35.202 versus optimized 104.857 ms +/-3.943, ratio 1.600; host
noise prevents treating that single ratio as a guaranteed speedup. The benchmark
is five trials x 10,000 evaluations of a 217-node DAG, not circuit performance.

Verified binary SHA-256 at this checkpoint:

- TCAD console: `FA4D2BCD4CF84530381B6E2554A3B243E4B9DCD4E379F02973F9384BA8B5FA08`.
- Native C ABI: `6B9014073366D7F43B003AA93A6EE740C3F750FBC978074B83C784320122CA5D`.

Architecture and focused whitespace checks passed. Full Studio regression:
455 tests, 454 passed, no failures, one host-restricted symlink test skipped.
Results are recorded in
`artifacts/studio-native-pdk-tcad-acceleration-tests-20261013.json`.
Full TCAD/PDK coverage, transport, extraction, compact-model qualification,
native PDK parity, mixed-mode field/circuit coupling and hardware evidence remain
pending. Human numerical review and Linux/package validation are still required;
the installed application and installers were not changed.
