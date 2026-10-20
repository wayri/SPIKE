# Component maker verification

> **Public evidence boundary:** Paths marked as unbundled local records identify generated developer-run evidence that is not shipped in the public source. The historical observation remains provisional and does not establish release qualification; reproduce and review it before relying on the claim. See the [release local-evidence boundary](RELEASE_040_LOCAL_EVIDENCE.md).

## Scope

This increment adds inert `.spkcmp` user packages, a wx component editor,
source-preserving circuit capture and explicitly approved build adapters.
It changes no governing device equations or native numerical integrators.

## Executed checks

- Focused package/capture/compiler/symbol/context/native-wx run: 44 tests passed.
- Final layout/example/transistor-mapping checks: 13 tests passed.
- C++ and Icarus tests invoked installed compilers, verified artifact hashes,
  checked compile failure reporting and refused missing/mismatched consent.
  Component builds did not automatically execute generated artifacts.
- Capture compared native RC time samples and output samples exactly between
  the original circuit and its generated subcircuit. Scoped-parameter
  counterexamples reject unsafe capture instead of rebinding parameters.
- Real UI inspection at wide and compact sizes verified labeled terminal legs,
  a dragged pin snapping to another body edge, auto-fit and readable validation
  output. Duplicate geometry-library controls were removed from the embedded
  editor; compact pin properties scroll and reports have a separate tab.
- Architecture and shared desktop button/control checks passed.

The first full-suite invocation had a sibling-fixture import-path error, not a
behavioral failure; its rerun uses the existing test directory on `sys.path`.
The final complete standalone Studio plus component-build run executed 704
tests in 171.449 seconds: **683 passed, 21 skipped, no failures/errors**.
Skipped checks require separately configured ngspice/KiCad, opt-in firmware
environments or host symlink permissions; they are not claimed as passed.
The run enabled native wx tests and used
`build-spikes-io-pad-20261019/Release/spikes_c_api.dll` for configured native
checks. Detailed logs are in `.tmp/component-maker-full-suite-final.log`.

## Historical limits at initial verification

This evidence does not establish arbitrary-model compatibility, manufacturer
qualification, hostile-code isolation or a new installed release. C++ uses the
existing sampled controller ABI. Verilog is compile-only through Icarus, with
no analog pin co-simulation. Subcircuit insertion expands native parts; only
primitive MODEL placement retains the custom component glyph. Unsupported
source and unsafe capture contexts fail explicitly. See the
[workflow](../../standalone/spikes_project/studio/docs/COMPONENT_MAKER.md).

## Beta 7 installation update — 2026-10-21

The subsequent compact-subcircuit and toolchain increment is now installed
locally as `0.3.0-beta.7`, an unsigned engineering preview. The final source
suite ran 722 tests: 701 passed, 21 skipped. A later first-run toolchain-directory
fix passed focused tests; the complete suite was not repeated after that fix.

Both frozen and installed component self-tests passed all four workflows:
native SPICE RC execution, C++ sampled-controller compile/run, Verilog compile,
and VVP digital execution. Both normal-window GUI acceptance runs passed; the
installed run passed all 125 checks. All 1,706 installed payload files match,
with no forbidden Qt files. Installation completed with exit 0 and beta 6
rollback artifacts retained.

Earlier hidden-window GUI acceptance failures are preserved: pin targets require
canvas paint, so GUI checks must be launched visibly. No assertions or native
worker timeout were weakened. See
installation evidence (unbundled local record: `../../artifacts/component21/VERIFICATION.md`).

Compact reusable SPICE symbols now project source-authoritative primitives;
Verilog digital simulation is tested, but analog Verilog pin co-simulation is
still absent. C++ remains the sampled controller ABI. Manufacturer qualification,
arbitrary-model compatibility and production numerical-review gates remain open.
