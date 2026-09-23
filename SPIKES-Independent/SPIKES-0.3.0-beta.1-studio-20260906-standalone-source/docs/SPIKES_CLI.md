# SPIKES experimental circuit CLI

The initial SPIKES CLI is a fail-closed adapter from a deliberately small
SPICE text subset to the existing SPIKE native linear MNA engine. It is an
experimental implementation slice, not a claim of feature or performance
parity with mature SPICE products.

Run it from the repository root on Windows:

```powershell
.\spikes.cmd check examples\spikes\voltage_divider.cir
.\spikes.cmd compile examples\spikes\voltage_divider.cir -o compiled.json
.\spikes.cmd run examples\spikes\voltage_divider.cir --probe "V(out)" --probe "I(R1)"
.\spikes.cmd run examples\spikes\dc_sweep.cir --probe "V(out)" --probe "P(R2)"
.\spikes.cmd run examples\spikes\rc_transient.cir --probe "V(out)" --probe "I(C1)"
.\spikes.cmd ac examples\spikes\rc_lowpass.cir --source V1 `
  --start-hz 10 --stop-hz 1e6 --points 201 --scale log --probe "V(out)"
.\spikes.cmd transfer examples\spikes\rc_lowpass.cir --source V1 `
  --start-hz 10 --stop-hz 1e6 --points 201 --output-probe "V(out)"
.\spikes.cmd fourier transient-result.json --probe "V(out)" `
  --fundamental-hz 100e3 --harmonics 20 -o harmonics.json
.\spikes.cmd temp-sweep examples\spikes\voltage_divider.cir `
  --start-c -40 --stop-c 125 --step-c 5 --reference-c 27 `
  --tempco R1=0.0039 --probe "V(out)"
.\spikes.cmd monte-carlo examples\spikes\voltage_divider.cir `
  --vary R1=0.01 --vary R2=0.01 --samples 100 --seed 2026 --probe "V(out)"
.\spikes.cmd corner-sweep examples\spikes\voltage_divider.cir `
  --vary R1=0.01 --vary R2=0.01 --probe "V(out)"
.\spikes.cmd native-run examples\spikes\native_pwm_switch.cir `
  --library build-peec-native\spikes_c_api.dll --method bdf2 `
  --probe "V(out)" --probe "I(Smain)"
.\spikes.cmd qualification --library build-peec-native\spikes_c_api.dll `
  --repetitions 3 --wall-steps 20 -o artifacts\spikes-qualification-report.json
```

The equivalent portable development invocation is
`python -m python.spikes`.

## Accepted netlist subset

- Two-terminal ideal linear resistors (`R`), capacitors (`C`), inductors (`L`),
  DC voltage sources (`V`), and DC current sources (`I`).
- Standard `Dname anode cathode model` elements with top-level
  `.model NAME D(IS=... N=... TNOM=...)` cards. This bounded Shockley model
  executes through `native-run`; unsupported diode parameters fail closed.
- Exactly one `.op`, single-source linear `.dc SOURCE START STOP STEP`, or
  strict fixed-output-step `.tran TSTEP TSTOP` directive. `.tran` start-time,
  maximum-step and `UIC` options are rejected in this bounded slice.
- Optional `.title`, `.end`, `*` line comments, and `$` or `;` inline
  comments.
- SPICE numeric scales including `K`, `MEG`, `M` (milli), `U`, `N`, `P`, and
  `F`; quantity suffixes such as `kOhm`, `mA`, and `V` are accepted.
- Probe arguments `V(node)`, `V(node,node)`, `I(element)`, and `P(element)`.
- Bounded `.subckt NAME pins...` / `.ends [NAME]` definitions and positional
  `X... nodes... NAME` instances, including forward references and nested
  hierarchy. Instance-local nodes are private and hierarchical element paths
  use `:` (for example `XTOP:XA:R1`) in current/power probes and DC sweeps.
- Bounded `.param NAME=EXPR` arithmetic using numbers, previously declared
  names, parentheses, and `+`, `-`, `*`, `/`, or bounded `**`. Element values,
  sweep limits, transient times, subcircuit defaults/local parameters, and
  instance overrides may use `{expression}`. Subcircuit instances receive
  isolated lexical scopes.
- Top-level `.global NODE...` declarations. Global names remain unscoped through
  nested instances and are retained in the project contract.
- UTF-8 `.include "file"` and `.lib "file" SECTION` expansion confined to the
  top-level netlist directory after path and symlink resolution. Expansion is
  limited to 16 levels, 64 files, 8 MiB, and 100,000 lines; cycles and missing
  sections fail closed. Library sections use `.lib SECTION` / `.endl [SECTION]`.

All unsupported elements, directives, continuations, non-constant source waveforms,
duplicate elements, missing node `0`, invalid units, and conflicting analyses
are rejected with a source-located JSON diagnostic. SPIKES does not silently
drop unsupported devices. Parameter functions, conditionals, strings, nested
expression braces, arbitrary filesystem includes, recursive definitions, and
scoped model cards are not accepted in this slice.

## Bounded parameter steps and scalar measurements

Ordinary `run` executes top-level linear parameter steps of the exact form
`.step param NAME START STOP STEP`. `NAME` must have been declared by an
earlier top-level `.param`. Up to eight axes, 10,000 Cartesian variants, and
two million variant-by-analysis work points are accepted. Nesting is
deterministic: the leftmost `.step` is the outermost axis. Every variant is
fully executed and returned with its parameter values; `compile` reports the
variant count. `native-run` rejects these directives instead of ignoring them.

The same route accepts `.measure` (or `.meas`) for the selected `op`, `dc`, or
`tran` analysis. `MAX`, `MIN`, `AVG`, and `RMS` reduce a scalar V/I/P probe;
DC/transient reductions may use a paired inclusive `FROM=value TO=value`
sample window. `FIND probe AT=value` linearly interpolates DC/transient data;
OP `FIND` returns the scalar directly without `AT`. At most 1,024 measurements
are accepted. An empty window, an out-of-axis `AT`, or another reduction error
produces an explicit failed measurement record while preserving a successfully
completed simulation.

This is intentionally not complete SPICE stepping or measurement syntax.
List, decade, octave, temperature, and model stepping; parameter-dependent
analysis bounds; and `WHEN`, `TRIG`/`TARG`, derivatives, and integral
measurements are unavailable. `AVG` and `RMS` are unweighted reductions over
returned samples, not continuous-time integrals.

## Explicit frequency-domain commands

`ac` exposes the existing complex linear MNA implementation without pretending
that the text parser accepts a SPICE `.ac` card. The input circuit must use an
accepted `.op` netlist as its topology container. `--source` selects exactly one
independent V or I source and `--magnitude` / `--phase-deg` define its phasor;
all other independent sources have zero AC magnitude. The output contains the
frequency axis, complex node voltage/current/power series, requested complex
probe series, residual diagnostics, and `spikes/ac-analysis-result/v1`
provenance.

`transfer` executes the same sweep and divides the selected `--output-probe`
phasor by that known source phasor. It is a bounded reduction with contract
`spikes/transfer-function-result/v1`, not a `.tf` operating-point analysis. It
accepts voltage or current output probes; complex power is rejected because it
is not linear in excitation amplitude. It does not compute input/output
resistance or linearize a nonlinear biased device.

This AC path supports ideal linear R/L/C/V/I circuits only. It does not yet
provide nonlinear small-signal linearization, compact-model AC behavior,
noise, pole-zero analysis, or the owned C++ solver path. Results explicitly
report `owned_cpp_ac: false`; `.ac` and `.tf` directives remain fail-closed in
the netlist parser. A sweep is limited to 65,536 total points and one million
complex output-series values across the circuit and requested probes.

`fourier` is deterministic post-processing of a completed ordinary SPIKES
transient JSON result. The named probe must contain finite real samples on a
uniform time grid, the capture must cover a positive integral number of
fundamental cycles, and requested harmonics must stay below Nyquist. The direct
DFT is bounded to 128 harmonics and eight million sample-by-harmonic terms. It
reports DC, complex peak-amplitude harmonics, phase, and THD under
`spikes/fourier-reduction-result/v1`. It is not a `.four` parser directive and
does not window non-coherent captures; incoherent input is rejected rather
than returning leakage-dependent amplitudes. Input JSON is capped at 64 MiB
before parsing.

## Explicit temperature, Monte Carlo, and corner sweeps

`temp-sweep` applies explicit first- and optional second-order polynomial
coefficients to named ideal R/L/C values around `--reference-c`, then runs each
temperature as an independent ordinary analysis. `monte-carlo` varies named
nonzero element values by relative tolerances using a platform-independent
SHA-256 counter mapping; its uniform or clipped three-sigma-normal samples are
exactly replayable from the reported seed. `corner-sweep` executes every
low/high Cartesian combination in deterministic input-order bitmask order.

These commands consume an otherwise accepted `.op`, `.dc`, or `.tran` deck;
they do not parse or claim compatibility with `.temp`, `.mc`, process-corner,
or statistical model-card syntax. Parameter expressions already elaborated by
the supported parser can be varied by their flattened element IDs. The current
temperature calculation changes only explicitly selected ideal values. It has
no semiconductor junction-temperature physics, self-heating feedback,
temperature-dependent compact models, correlated process distributions, or
mismatch hierarchy.

Every result records the source digest, normalized orchestration inputs, every
case deviation/factor, nested executable result, and the fact that cases used
the Python reference runner. A request is limited to 256 cases, 16 varied
elements, and 250,000 aggregate underlying solve points. Relative tolerances
must lie strictly between zero and one; invalid or nonpositive derived passive
values fail before execution.

## Owned native execution route

`native-run` is the explicit CLI route to the owned C++ kernel. It requires an
exact local DLL/SO/dylib path; the CLI never searches for or silently selects a
native binary. In addition to ordinary R/C/L/V/I and bounded hierarchy, this
route accepts:

- `PULSE(V1 V2 TD TR TF PW PER)` voltage or current sources;
- `PWL(T0 V0 T1 V1 ...)` voltage or current sources;
- the SPIKES-native inline switch form
  `Sname N+ N- CTRL+ CTRL- RON ROFF VT VSLOPE`.

The inline switch is deliberately not presented as generic SPICE syntax.
Standard `.model ... SW(...)` parsing and hysteresis semantics are not yet
implemented. Native extensions remain rejected by ordinary `check`, `compile`,
and `run`, preserving their existing reference-engine contract. `native-run`
supports `.op`, independently orchestrated single-source `.dc`, and `.tran`.

Native transient JSON reports a nonuniform breakpoint-aligned `time_s` vector,
`source_breakpoint_steps`, integration/factorization work counters, and
`owned_cpp_transient: true` provenance. `--method trap` is the default: it uses
backward Euler at startup and source edges and trapezoidal integration between
events. `--method be` selects backward Euler throughout. `--method bdf2`
selects unequal-step BDF2 after a backward-Euler startup/event restart and
preserves its two-step state in persistent sessions. It is not LTE-adaptive.
Consumers must not
assume the `.tran` maximum step is every returned sample interval.

## Result status and limitations

The project, compiled request, probes, result, and CLI-error envelopes are
JSON-compatible and versioned. Results are currently marked `experimental`
because they inherit the qualification status of `spike.native.linear_mna`.
A `.dc` sweep is implemented as deterministic independent operating points;
`.tran` currently delegates to the existing Python `spike_core.native_mna`
reference adapter and uses fixed-step backward Euler. It is not the owned C++
SPIKES transient kernel. Initial-condition cards and source waveform syntax are
not yet accepted. Nonlinear devices, temperature effects, adaptive integration,
and convergence continuation remain outside this slice.

That limitation applies to ordinary `run`. The explicit `native-run` route now
executes owned PULSE/PWL sources and the native controlled switch described
above.

## Archetype library and benchmarks

`spikes library search|inspect|validate|elaborate` exposes the versioned native
archetype registry. Eight ideal linear archetypes elaborate to current native
MNA elements with deterministic defaults, presets, overrides, limitations, and
provenance. Diode, op-amp, BJT, MOSFET, GaN, and SiC descriptors are explicitly
`unavailable`; they never elaborate into misleading substitutes.

`spikes benchmark` delegates to the accuracy-gated analytical DC harness.
Timing is scored only after every repeat passes its independent error gate, and
the report makes no competitive claim.

`spikes qualification` extends the evidence surface to complex DC, nonlinear,
RLC transient, PWM, synchronous-buck, native interactive-control, continuous
pacing, checkpoint/replay, and deadline-safety cases. It records cold/warm
timings and binds the report to the selected library digest. See
`docs/SPIKES_QUALIFICATION.md` for gates and real-time limitations.

## Python integration foundations

The `python.spikes` package also exposes experimental contracts for persistent
compiled-block sessions, typed dashboard/console controls, deterministic
lockstep and best-effort continuous pacing, checkpoint/restore, and safe trip.
These APIs host pluggable Python plants, and the qualification path now binds
one to an owned persistent native backward-Euler circuit session with source
updates and native checkpoint/restore. It remains explicitly not hard-real-time
or HIL qualified. `load_native_library(path)` provides the explicit,
ABI-checked, ownership-safe bridge for native DC, bounded transient, and
persistent-step solves; `native_transient_waveform` converts uniformly spaced
native samples to the instrument contract.

The same package contains an experimental four-state digital event kernel and
a fail-closed model-builder and complex-device extension workflow. The digital
kernel has no HDL frontend or analog bridge yet, and extension manifests do not
load code. Datasheet/LLM-derived model evidence remains untrusted until human
review and numerical qualification succeed.

Virtual-instrument reference engines currently provide a triggered scope, DMM,
spectrum analyzer, one-port network analyzer, and Smith-chart data. They use
bounded calibrated waveform/frequency-response contracts and intentionally
preserve active or negative-resistance responses. Rendering, live multi-channel
transport, multiport calibration, and de-embedding are future layers.

Continuous Python sessions can use `SessionCaptureMonitor` to keep a fixed-size
rolling plot window and emit bounded pre/post-trigger events rather than storing
the entire run. Selected records can be written with
`ChunkedWaveformWriter`; `.spkw` chunks are lossless, independently decodable,
CRC protected, recoverable after an interrupted tail, and subject to a hard
file-size limit. See `docs/SPIKES_STREAMING_RESULTS.md`.
