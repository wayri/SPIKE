# SPIKES 0.2.0 engineering preview

The Windows x64 portable artifact is locally built and integrity-verified. It
ships the owned C++ SPIKES engine inside the frozen worker and exposes bounded
JSON-line operations for one-shot netlist runs and persistent interactive
transient sessions.

Interactive sessions support source updates, lockstep stepping, selected probe
samples, native diagnostics, checkpoints, bit-exact restore, and explicit
close through one resident desktop worker. The resident-process integration
test verifies a single worker PID from create through close.

The owned CLI now executes `.op`, independent-source `.dc`, and bounded
`.tran`. The first standard nonlinear syntax slice supports diode instances and
top-level `.model NAME D(IS=... N=... TNOM=...)` cards, including forward model
references and flattened subcircuits. Unsupported diode options fail closed.

The same-model competitive check now runs three DC cases, passive RC and RL
transients, and an ideal PULSE-driven load through SPIKES, ngspice, and LTspice.
All 18 engine/case outcomes pass their analytical accuracy gates. The small
corpus is not eligible for a general performance claim.

This is an engineering preview, not a parity or superiority release. The
competitive gate remains blocked at 0/10 because complete SPICE3 language,
analysis and device coverage; public equal-model benchmarks; hard-real-time and
physical HIL qualification; production model-library licensing; and
cross-platform release evidence remain incomplete.

Artifact: `artifacts/windows/SPIKE-0.2.0-windows-x64-portable.zip`

SHA-256: `4d700dea0ab4231cb02ec124575f6260de9d13be2f5c23aa74574860786003e5`

The machine-readable release decision is
`artifacts/windows/SPIKE-0.2.0-release-readiness.json`.

The independently generated tree/archive integrity decision is
`artifacts/windows/SPIKE-0.2.0-first-release-readiness.json` and passes 8/8
checks.
