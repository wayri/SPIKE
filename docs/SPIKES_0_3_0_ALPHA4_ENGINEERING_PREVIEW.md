# SPIKES 0.3.0-alpha.4 engineering preview

This release is an unsigned Windows x64 engine, console, C/C++ SDK, Python
bridge, compact-model, and evidence bundle. Its release manifest binds every
file and keeps all production claims fail-closed.

## Executable additions

- OSDI 0.4 DC, reactive-charge, fixed-step backward-Euler transient, and noise
  callback execution in the owned C++ path.
- Typed OSDI model and instance parameter assignment with aliases and required
  Verilog-A simulator callbacks.
- Official Berkeley BSIM-BULK 107.2.1 and BSIM-CMG 112.1.0 compiled modules.
- Arbitrary validated multi-tone, third-order bounded Volterra analysis and
  correlated noise-source decomposition.
- `.func`, `.ac`, `.temp`, C/L `IC=`, and `.tran ... UIC` parser/execution
  slices in addition to the previously released language and analysis waves.
- Nine-case converter/RF/motor/DC equal-model comparison across SPIKES,
  ngspice, and LTspice.
- A strict physical-HIL evidence evaluator that refuses simulation, loopback,
  self-authored status fields, missing calibration, missing raw traces, timing
  misses, incomplete physical fault injection, or unsigned attestation.

## Evidence boundaries

The BSIM report proves source/compiler/artifact provenance and native callback
execution. It is not a process-design-kit or fabricated-silicon correlation.
The converter/RF/motor report compares small idealized/electrical models with
process startup included. It is not a switching-loss, S-parameter, mechanical,
or thread-scaling superiority result. A physical HIL certification can pass
only for the exact named host, target, firmware, fixture, calibration, timing
trace, and signed evidence package.

## Release blockers retained

- Complete SPICE3 parser, control-language, device-card, and analysis parity.
- Foundry/process-card qualification and vendor GaN/SiC/IGBT/thyristor model
  licenses plus golden electrical, thermal, breakdown, and switching data.
- General OSDI multistep history and output-referred correlated AC noise.
- General dynamic-device multi-tone Volterra/HB/PSS analysis.
- Physical hard-real-time/HIL execution on identified, calibrated equipment and
  independent certification.
- Signed production packaging and any competitive-superiority claim.

These are evidence requirements, not documentation tasks; the release cannot
honestly mark them complete in the absence of the required external inputs.
