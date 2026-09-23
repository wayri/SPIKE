# SPIKES competitive release gates

SPIKES must not claim whole-product parity or superiority over ngspice, QSPICE,
PSIM, SIMPLIS, PSpice, or QucsStudio from feature intent or isolated
microbenchmarks. A claim is eligible only when the matching machine-readable
gate in `docs/validation/spikes-ngspice-competitive-gate.json` is `passed` and
links reproducible evidence.

`python.spikes.competitive_gate.validate_competitive_gate` enforces the exact
gate set, derived totals/status, and SHA-256-addressed artifacts for passed
gates. A manually asserted claim or unevidenced pass fails closed.

The ngspice baseline is intentionally broad. Its official documentation lists
the KLU solver, XSPICE mixed-signal/code-model support, runtime Verilog-A models
through OSDI/OpenVAF, shared-library use, and a mature set of circuit analyses
and source forms. SPIKES therefore needs evidence in every category below, not
just a faster resistor network or one converter waveform.

Required whole-product gates are:

1. SPICE language, hierarchy, behavioral-source, and model-card compatibility.
2. Operating point, DC, AC, transient, noise, pole-zero, distortion,
   sensitivity, temperature, and statistical analyses.
3. Qualified compact-device breadth including established diode/BJT/JFET/MOS
   families, WBG models, transmission lines, magnetics, and mixed-signal parts.
4. A sandboxed compiled model interface with qualification comparable in scope
   to Verilog-A/OSDI and XSPICE code models.
5. Converter accuracy and convergence over CCM/DCM, hard/soft switching,
   synchronous/regenerative operation, saturation, thermal feedback, and
   protection events.
6. Cold/warm runtime and peak-memory wins on public small, medium, and large
   corpora, measured on pinned hardware with identical tolerances and outputs.
7. Robustness: zero silent corruptions, bounded failure behavior, restart and
   convergence evidence across adversarial and industry-derived cases.
8. Stable C and Python embedding, continuous sessions, deterministic lockstep,
   bounded event capture, and independently qualified real-time/HIL latency.
9. Redistributable model-library coverage with provenance, licensing, parameter
   evidence, and per-model numerical qualification.
10. Repeatable Windows/Linux/macOS builds and result agreement within declared
    numerical tolerances.

The present gate is `blocked`. This pass advances the switching and embedding
sub-gates with native PULSE/PWL sources, exact breakpoints, an event-aware
hybrid trapezoidal/BE method, bounded exact-matrix LU reuse, a differentiable
bidirectional controlled switch, C ABI access, and Python access. It does not
satisfy the whole-product gate.

## Executable checks

The current same-deck comparison can be reproduced locally with:

```powershell
.venv\Scripts\python.exe scripts\run_spikes_competitive_benchmarks.py `
  --library build-spikes-hybrid\spikes_c_api.dll `
  --repetitions 5 `
  --output artifacts\spikes-competitive-benchmark-2026-08-30.json

.venv\Scripts\python.exe scripts\run_spikes_parity_checks.py `
  --benchmark artifacts\spikes-competitive-benchmark-2026-08-30.json `
  --qualification artifacts\spikes-qualification-report-2026-08-30.json `
  --output artifacts\spikes-parity-check-report-2026-08-30.json
```

The current report executes nine bounded same-model decks through the owned
C++ kernel, ngspice, and LTspice: three DC operating points, RC and RL
unit-step values at one time constant, the average voltage of an ideal
PULSE-driven resistive load, an ideal PWM LC buck endpoint, passive RF RLC
ringing, and a motor-armature R-L electrical surrogate. SPIKES and ngspice
reduce their existing result vectors;
LTspice receives equivalent `FIND ... AT` or `AVG ... FROM/TO` measurements.
Every scalar is accuracy-gated before wall time is retained, and every engine
binary (plus the owned SPIKES DLL) is SHA-256 bound. All engines use an
isolated cold process and return the same scalar output, so that limited timing
scope is comparable.

The buck case qualifies source timing, LC energy storage, and scalar reduction,
not a semiconductor model: it contains no parasitic switching loss, reverse
recovery, dead time, or control loop. The RF case is time-domain passive
ringing, not an S-parameter/noise/nonlinear RF qualification. The motor case
has no mechanics, torque, magnetic saturation, or back-EMF coupling. The
corpus also lacks medium/large public cases, AC/noise, compact models,
robustness, peak-memory, warm-solve, and thread-scaling evidence. It is
therefore far too small for a performance or parity claim and the report keeps
`performance_claim_eligible` false.

The second command evaluates all ten mandatory gates from the benchmark and
native qualification artifacts. Every absent evidence class becomes a named
blocking check; a partial pass cannot silently promote the product claim.

The separate owned-engine Wave 1 scale, thread, memory, convergence, expected
failure, and parasitic/dead-time converter corpus is documented in
`SPIKES_WAVE1_BENCHMARKS.md`. It expands qualification evidence but does not
change the cross-engine competitive gate.

The recorded 2026-08-31 run is
`artifacts/spikes-competitive-converter-rf-motor-2026-08-31.json`. All 27
engine/case results passed (nine each for SPIKES, ngspice, and LTspice). Its
cold per-process scalar timings are evidence, not a superiority score: in this
run SPIKES was slower than ngspice and faster than LTspice on the three newly
added fixtures, with Python/CLI startup included.
