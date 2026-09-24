# SPIKE Solver Status

This file describes executable behavior. Catalog entries marked unavailable are
architecture contracts, not implemented physics.

## Loaded SI workflow (experimental)

The [source-to-receiver workflow](SI_WORKFLOW.md) connects RLGC/Touchstone or
bounded board extraction to configurable endpoints, deterministic aggressors,
graded passives, port edits, loaded transfer, waveform/eye/TDR and noise reports.
IBIS support is inventory plus explicit DC-slope/ramp reduction, not nonlinear
switching or AMI simulation. Results and exports retain these limitations.

## PI Deployable Release Gate

The machine-readable PI promotion gate is
`build/pi-release-qualification.json`. Regenerate it with
`python -m python.spike_core.cli --output build/pi-release-qualification-current.json pi-release-qualification --runtime-report build/release-runtime-qualification-current.json --benchmark-report build/native-benchmark-current.json`. The gate is fail-closed
and currently reports `blocked`: packaged/source runtime parity passes, but the
native benchmark has skipped cases and none of the six required native PI and
circuit workflows has reached a validated release state. See
`docs/PI_RELEASE_QUALIFICATION.md` for the exact contract. External solvers are
comparison evidence and cannot independently promote a native SPIKE workflow.

## Operational

### Copper Geometry DC (`spike.routed_dc`)

- State: available
- Geometry: tracks, through vias, pads, polygonal copper zones
- Excitation: multiple voltage sources and current sinks
- Models: explicit source/load contact and package resistance
- Results: voltage, voltage drop, branch current, current density, solved probes
- Numerics: sparse resistive network; finite-volume zone spreading; policy-
  controlled NumPy/Numba assembly and SuperLU/PETSc-MUMPS sparse solve
- Limit: zone sign-off requires a mesh-convergence comparison

### Native PEEC RLCG (`spike.peec_2_5d`)

- State: experimental when `spike_peec_native` is packaged
- Geometry: routed tracks, polygonal copper zones, SMD/THT pads, plated vias,
  and through-pad barrels in one connected hybrid mesh
- Results: port-referred frequency-dependent resistance, partial inductance,
  approximate single-reference capacitance/dielectric conductance, complex
  impedance sweeps, and branch-current magnitude
- Models: smooth isolated-slab skin effect, optional Hammerstad RMS roughness,
  imported stackup permittivity, and loss tangent where supplied
- Numerics: native C++/Eigen partial-element matrices plus branch-incidence
  modified nodal analysis; planar copper uses a finite-volume grid
- Resource admission: dense PEEC derives its branch capacity from the configured
  solver-memory allowance and detected physical RAM. The default allowance is
  2 GB; users may set a stricter explicit branch cap. Admission is recorded in
  result provenance and does not change the solver's experimental validity tier.
- Limits: proximity effect, arbitrary-geometry/multiconductor capacitance,
  via/antipad capacitance, Huray/gradient roughness, geometry-derived
  S-parameters, and full-wave radiation are not included
- Validity: quasi-static wavelength limit is checked and reported

### Geometry PEEC transient (`spike.peec_rl_transient`)

- State: experimental and executable when `spike_peec_native` is packaged
- Excitation: constant, step, pulse, and piecewise-linear voltage/current
  terminal profiles with explicit timing, timestep, frame, wall-time, and
  memory budgets
- Numerics: backward-Euler integration over conductor R, the mutual partial-L
  matrix, and optional single-reference stackup shunt capacitance
- Results: timestamped voltage, drop, current, density, loss, via stress,
  probes, and bounded 2D/3D visualization frames
- Limits: no nonlinear device equations, dielectric loss/dispersion, via
  capacitance, radiation, or transmission-line/full-wave propagation
- Validation: analytical waveform and topology regressions pass; measured
  time-domain and independent field-solver correlation remain required

### Native linear MNA (`spike/native-mna-request/v1`)

- State: implemented, experimental, and not eligible for PI release promotion
- Elements: linear resistor, capacitor, inductor, independent voltage/current
  sources, and VCCS, VCVS, CCCS, and CCVS dependent sources
- Analyses: DC operating point, linear AC sweep, and bounded fixed-step
  backward-Euler transient analysis
- Results: `spike/native-mna-result/v1` with node and element values plus
  structured diagnostics and explicit `experimental` model status
- Verification: focused analytical tests cover resistor dividers, current
  sources, all four dependent-source classes, RC AC response, RC transient
  response, source waveforms, nonlinear rejection, and singular diagnostics
- Integration boundary: the service and CLI expose direct request validation and
  execution plus reviewed SPICE-workspace compilation/execution. A reviewed
  field/circuit package can invoke the native PEEC reduction provider and this
  MNA core through a deterministic fixed-point loop.
- Limits: nonlinear semiconductor and behavioral devices, adaptive timesteps,
  sparse/iterative linear systems, general automatic PEEC-to-circuit
  compilation, and electrothermal feedback are unsupported and must fail
  closed. The fixed-point field/circuit route is experimental, requires an
  explicit reviewed package, and is not a general FEA or electrothermal path.
- Release status: the integrated core remains experimental and cannot satisfy
  the native SPICE-compatible workflow gate until independently validated under
  `docs/PI_RELEASE_QUALIFICATION.md`.

### SPIKES owned circuit kernel and CLI

- State: experimental circuit and integration foundation; not performance-qualified
- Native kernel: strict-floating-point C++ modified nodal analysis for linear
  R/C/L elements and independent DC current/voltage sources, plus DC
  Shockley-diode, three-terminal Ebers-Moll BJT, and four-terminal Level-1
  Shichman-Hodges MOSFET residual/Jacobian paths. The MOSFET includes body
  effect, channel-length modulation, reverse terminal operation, and finite
  off conductance. The nonlinear solve provides damped Newton, limiting where
  applicable, overflow-safe exponential continuation, and explicit
  nonconvergence
- Linear backend: pivoted dense LU remains the general MNA reference. The
  native DC path assembles a compressed sparse matrix directly and reserves
  the complete nonlinear Jacobian pattern before Newton iteration. It provides
  COLAMD-ordered sparse LU and rank-revealing sparse QR with symbolic-pattern
  reuse across Newton numeric factorizations, plus row-equilibrated
  ILUT-preconditioned sparse GMRES with an
  original-system residual gate. It additionally provides diagonally preconditioned conjugate
  gradient for symmetric positive-definite systems, strict symmetry/positive-
  definiteness failure gates, automatic LU fallback, configurable iteration
  tolerances, and opt-in OpenMP matrix-vector/dot execution. Row-equilibrated
  restarted GMRES adds a bounded general-MNA path with two-pass modified
  Gram-Schmidt, Givens updates, and final unscaled-residual verification. The
  legacy restarted-GMRES path remains available as a dense reference. Automatic
  dispatch uses dense LU for small systems, sparse LU for larger systems, and
  attempts ILU-GMRES before sparse LU at the largest current threshold. Sparse
  DC factorization is currently single-worker. Linear and nonlinear transient systems at the
  configured size threshold now assemble directly into sparse triplets, reuse
  COLAMD symbolic analysis for an unchanged pattern, and perform numeric-only
  SparseLU refactorization when companion or nonlinear Jacobian values change.
  Dense nonlinear assembly remains the small-system reference; stronger
  preconditioners and parallel sparse factorization remain required for
  production scale.
- Native transient: bounded dense backward Euler, event-aware hybrid
  trapezoidal, and variable-step BDF2 integration support ideal
  capacitors/inductors, explicit C/L initial conditions or DC initialization,
  nonlinear Newton/backtracking, shortened final steps, periodic PULSE and PWL
  current/voltage sources, and per-sample node/element voltage, current, and
  power. The requested timestep is a maximum: every PULSE phase boundary and
  PWL knot forces an exact solve point and remains subject to the hard step
  bound. Hybrid mode uses BE at startup/source events and trapezoidal companion
  models between events. BDF2 uses unequal-step coefficients, retains two-step
  C/L history across persistent calls and checkpoints, and restarts with BE at
  startup/source events. An opt-in embedded BDF2/BE or trapezoidal/BE defect
  controller rejects and retries candidate steps, enforces a minimum timestep
  and rejection budget, and reports accepted-step bounds. Diode,
  charge-storage dynamic-diode, and smooth controlled-switch systems now use
  a genuine second Newton solve for the BE
  companion at the same endpoint; failure of that companion is treated as an
  infinite defect and reduces the timestep. The startup/event BE step itself
  has no embedded estimate; nonlinear companion solves use the sparse path at
  the configured threshold.
  The bounded qualification is recorded in
  `docs/validation/NONLINEAR_EMBEDDED_LTE.md`.
  Exact-matrix dense LU caching reuses
  linear companion matrices and exact nonlinear Jacobians under bounded
  entry/memory limits. A native two-terminal dynamic diode adds one implicit
  diffusion-charge state, junction capacitance, reverse-recovery terminal
  current, BE/BDF2 residuals, and analytic Jacobians. Hybrid trapezoidal mode
  rejects this device until a charge-consistent companion is implemented. A
  coupled electrothermal resistor stamps temperature-dependent conductance,
  Joule heat, Rth, and Cth on an explicit temperature-rise node. A smooth
  saturating inductor stamps an energy-consistent flux-linkage law with
  positive differential inductance through the saturation knee. Both support
  BE/BDF2 and embedded LTE and currently reject hybrid trapezoidal mode.
  The bounded five-terminal GaN/SiC WBG model integrates conservative terminal
  charge and its electrothermal `Rth-Cth` state under BE/BDF2, including
  reverse conduction and avalanche. Level-1 MOSFET and Ebers-Moll BJT charge
  storage is deliberately rejected in transient analysis. The
  transient engine remains a correctness reference, not production SPICE.
- Native switching: a four-terminal voltage-controlled switch provides finite
  Ron/Roff, a smooth threshold transition, an analytic control Jacobian, and
  bidirectional terminal current. This enables initial PWM-driven converter
  circuits but is not a semiconductor compact model or converter validation.
- Diagnostics: singular/numerical/nonconverged status, residual, pivot,
  nonlinear-iteration, damping, junction-limit, breakpoint,
  BE/trapezoidal/BDF2, dense and sparse factorization/reuse/cache counters,
  symbolic analysis, numeric-only refactorization, embedded-LTE rejection/ratio
  and accepted-step bounds, node voltages, and per-element
  current/power
- Embedding: versioned opaque-handle C ABI (`SPIKES_ABI_VERSION == 1`) with
  exception containment and explicit ownership. Additive transient API v1
  exposes C/L construction, PULSE/PWL sources, the controlled switch, the
  charge-storage dynamic diode, electrothermal resistor, saturating inductor,
  DC Level-1 MOSFET and Ebers-Moll BJT construction, adaptive-controller
  options,
  versioned/size-guarded options, immutable sample results, and diagnostics. An
  explicit-path Python `ctypes` bridge verifies ABI compatibility and owns
  native circuit/result lifetimes.
- CLI: `spikes check|compile|run` accepts a fail-closed R/C/L/V/I/D/E/G/F/H
  subset plus affine single-control B sources with
  one `.op`, linear single-source `.dc`, or strict bounded `.tran TSTEP TSTOP`
  analysis and V/I/P probe descriptors. The ordinary CLI transient executes
  through the Python native-MNA reference engine and records that boundary.
  `spikes native-run --library PATH` is the explicit owned-kernel route for
  `.op`, independent-source `.dc`, and `.tran`, including PULSE/PWL sources, inline native controlled
  switches, hierarchy, V/I/P probes, selectable `trap|be|bdf2` integration,
  breakpoint/factorization diagnostics, and owned-engine provenance. It never
  searches for a library. Standard diode instances and top-level
  `.model NAME D(IS=... N=... TNOM=...)` cards execute through the owned diode
  ABI; unsupported diode options and standard switch `.model` cards remain
  blocked.
- Compiled console/dashboard: `spikes_console` loads a bounded native `.spkc`
  project or a built-in demo and runs directly on a persistent C++ transient
  session. It supports live and runtime-attached node/element V/I/P,
  electrothermal temperature, dissipation, and aggregate failure-margin
  probes; bounded rolling histories and CSV export; ASCII trends; source
  set/toggle controls; checkpoint/restore; scripted execution; and best-effort
  wall-clock pacing. The same implementation is reusable through the
  `spikes_dashboard` static library. This is not complete SPICE syntax, a
  deterministic hard-real-time scheduler, or physical-HIL qualification. See
  `docs/SPIKES_CONSOLE_DASHBOARD.md`.
- Linear analysis wave 3: versioned executable Python-reference contracts add
  uncorrelated resistor Johnson-Nyquist noise propagated through the exact AC
  MNA system, central-difference complex AC sensitivities for R/L/C values, and
  generalized-descriptor pole/SISO-zero extraction. Analytical resistor-noise
  and RC sensitivity/pole fixtures pass. This does not include semiconductor
  noise, nonlinear operating-point linearization, adjoint sensitivity,
  Volterra/distortion analysis, or pole-zero cancellation reduction; see
  `docs/SPIKES_LANGUAGE_ANALYSIS_WAVE3.md`.
- Nonlinear language/analysis waves 4-6: a safe differentiable AST supports
  bounded memoryless multi-control B voltage/current expressions with analytic
  gradients and hierarchical scoping. A dense reference Newton engine executes
  R/V/I/E/G/F/H/B/diode operating points, bias-linearized memoryless small
  signal, resistor-plus-diode biased noise, nonlinear adjoint sensitivities,
  and local third-order one-tone distortion. Wave 6 adds SPICE-style `TABLE`,
  `URAMP`, `U`, `SGN`, `FLOOR`, `CEIL`, `INT`, and modulo semantics with
  analytic gradients away from explicitly rejected discontinuities. Diode
  `.model` cards accept `KF`/`AF`, and biased noise reports the white
  shot/thermal plus frequency-dependent 1/f spectrum and integrated variance.
  These are analytical correctness fixtures, not native production
  implementations. Bounded complex source-correlation matrices and a
  frequency-dependent one-source/one-tone third-order Volterra reference are
  executable. Device-internal BSIM correlated noise, arbitrary multi-tone
  Volterra grids, harmonic balance, and complete SPICE3 expression/deck
  semantics remain absent. See `docs/SPIKES_LANGUAGE_ANALYSIS_WAVE6.md`.
- Hierarchy: bounded `.subckt`/`.ends` definitions and positional `X` instances
  support forward references, nested deterministic flattening, private local
  nodes, hierarchical probes, and hierarchical DC-source sweep paths. Recursive
  definitions and expansion overflow fail closed. Bounded arithmetic `.param`
  scopes, subcircuit defaults/overrides, top-level `.global`, and root-confined
  UTF-8 `.include` / selected `.lib` sections are implemented with explicit
  expression, path, cycle, depth, file-count, byte, and line limits. Parameter
  functions/conditionals and scoped model cards remain unsupported.
- Step/measure slice: ordinary `spikes run` executes bounded linear
  `.step param` Cartesian variants (eight axes, 10,000 variants, and two
  million variant-by-analysis work points) in deterministic leftmost-outermost
  order. Scalar OP/DC/transient `MAX`, `MIN`, `AVG`, `RMS`, and `FIND`
  measurements execute with explicit sample windows/interpolation and
  per-measure failure records. This is a bounded reference-runner feature;
  `native-run` rejects it, and full SPICE stepping/measurement syntax is not
  claimed.
- Archetypes: the versioned built-in registry remains a separate ideal-model
  catalog. The owned C++ ABI now exposes DC diode, Ebers-Moll BJT, and Level-1
  MOSFET construction, but these have not been promoted into a qualified
  redistributable part library because dynamic charge, electrothermal behavior,
  parameter-card compatibility, and vendor qualification remain absent.
- Persistent execution foundation: immutable content-addressed compiled-block
  metadata, stable numeric signal/control IDs, checkpoint/restore, bounded
  event history, deterministic lockstep, best-effort wall-clock pacing, safe
  trip/re-arm, and typed momentary/toggle/pulse/set/increment/ramp controls are
  implemented in Python. An additive native session now copies a circuit once,
  updates constant sources, advances stateful backward-Euler, hybrid-
  trapezoidal, or BDF2 steps, reports
  cumulative diagnostics, and supports owner-bound native checkpoint/restore
  through C and Python. Persistent global PULSE/PWL time, exact internal source
  breakpoints, PWL interpolation, and waveform-position checkpoint restore are
  implemented. A bounded full-matrix-keyed workspace reuses LU factors across
  session calls and exposes factorization/reuse/cache diagnostics. Persistent
  capacitor-current/inductor-voltage and two-step C/L history enables hybrid or
  BDF2 stepping and is rewound by checkpoints; actual source events restart
  with BE. Large nonlinear steps can use the sparse assembly path, but the
  session is not preallocated, deterministic WCET, or hard HIL.
- Digital foundation: an experimental bounded four-state event kernel provides
  `0/1/X/Z` resolution, deterministic integer ticks and delta cycles, primitive
  gates, tri-state drivers, and D flip-flops. It is not a Verilog/VHDL compiler,
  timing sign-off engine, MCU/FPGA emulator, or analog/digital bridge.
- Model-builder foundation: versioned content-addressed sources, parameters,
  datasets, validity envelopes, deterministic fits, black-box descriptors, and
  qualification records are implemented with a Shockley-diode reference fitter.
  LLM extraction is always unreviewed evidence; named review, independent data,
  metric gates, digest verification, and a rechecked export safety floor are
  required before a model can become runnable.
- Dynamic-diode path: an executable bounded Python constitutive model
  provides temperature-scaled Shockley conduction, analytic conductance,
  continuous depletion charge/capacitance, implicit-Euler transport charge,
  reverse recovery, and an analytic transient Jacobian. The native C++ MNA
  path now provides a smaller charge-control form with an implicit diffusion
  state, junction capacitance, BE/BDF2 stamping, reverse-recovery current, and
  additive C/Python ABI construction. Neither path is vendor-qualified; see
  `docs/DYNAMIC_DIODE_WAVE1.md` and
  `docs/validation/NATIVE_DYNAMIC_DIODE_DAE.md`.
- Complex-device extension foundation: immutable metadata declares electrical,
  thermal, rotational, translational, magnetic, and acoustic power ports;
  parameters/states/observables; residual/Jacobian/event capabilities; validity
  envelopes; runtime provenance; and explicit four-quadrant, NDR, passivity,
  and reciprocity behavior. Bounded registration validates exact host
  capabilities and rejects untrusted native runtimes. Registration is metadata
  only: arbitrary extension code is not loaded or executed.
- Reviewed compiled-control boundary: exact executable/manifest/evidence
  digests admit trusted local JSON-subprocess control blocks with fixed argv,
  strict finite port/state schemas, timeout and I/O limits, a fresh working
  directory, and stable failure codes. This is not hostile-code isolation, a
  solver callback ABI, or Verilog-A/OSDI/HDL compilation; see
  `docs/SPIKES_COMPILED_BLOCKS.md`.
- OSDI 0.3 DC boundary: trusted digest-reviewed modules can register directly
  as first-class C++ MNA elements. On Windows, hostile-marked OSDI DC requests
  instead use a digest-bound zero-capability AppContainer worker; real-model,
  forbidden-file, and denied-network probes pass. Transient/reactive, noise,
  limiting, OSDI 0.4, non-Windows hostile isolation, and general compiled-block
  sandboxing remain open; see `docs/SPIKES_HDL_FRONTEND.md`.
- Signed I/V references: bounded tabulated and analytic polynomial evaluators
  preserve negative voltage/current, generated versus absorbed power, exact
  small-signal slope, and explicitly authorized negative differential
  resistance. No positive-slope clamp or passive-only assumption is applied.
- Virtual instruments: bounded, calibrated waveform/response contracts feed an
  edge-triggered scope, DMM mean/RMS/frequency, windowed radix-2 spectrum
  analysis, one-port S11/Z conversion, and Smith coordinates. Active and
  negative-resistance responses with reflection magnitude greater than one are
  preserved. Native transient and persistent-session waveform bridges enforce
  explicit uniform timebases before scope/FFT use.
- Streaming results: fixed-capacity multi-channel rings overwrite and count old
  samples; trigger engines retain only bounded pre/post windows with hysteresis,
  holdoff, queue limits, and drop accounting. The experimental `.spkw` writer
  uses independently decodable CRC-protected chunks, a hard file-size limit,
  recoverable torn tails, and lossless raw/zlib/XOR-zlib/LZMA codecs. Compression
  and disk I/O are not permitted to imply hard-real-time qualification; see
  `docs/SPIKES_STREAMING_RESULTS.md`.
- Qualified local model-index foundation: exact-digest model records and KiCad
  `Library:Symbol` mappings require explicit redistribution approval,
  license-evidence digests, reviewed qualification, complete one-to-one pin
  binding, and immutable parameter overrides. This is a fail-closed format,
  not a populated vendor library; see `docs/SPIKES_MODEL_LIBRARY.md`.
- Limits: no production compact semiconductor library,
  complete deck-syntax AC/noise/pole-zero/sensitivity coverage, complete SPICE
  behavioral semantics, production arbitrary-multitone frequency-dependent
  distortion analysis,
  event-state hysteresis, qualified switching-specialized solver, multiport
  VNA/de-embedding, rendered instrument UI, adaptive native event queues, KiCad
  schematic adapter, executable extension loader, HDL/C/C++ block compiler,
  native lock-free capture ring, asynchronous disk writer, rotating archives,
  virtual MCU/FPGA, mixed-signal bridge, multimodal LLM runtime, or HIL
  qualification yet
- Competitive claim gate: whole-product ngspice parity/superiority is blocked.
  The ten fail-closed gates and current machine-readable status are documented
  in `docs/SPIKES_COMPETITIVE_GATES.md` and
  `docs/validation/spikes-ngspice-competitive-gate.json`.
- Benchmarks: a bounded accuracy-first harness supplies analytical cases,
  warmups/repeats, hashes, explicit timing scope, and a no-shell external JSON
  adapter; speed is withheld whenever any measured repeat fails accuracy.
- Qualification corpus: fourteen native/interactive scenarios exercise a balanced
  bridge, direct and two-worker CG 200-section ladders, sparse-LU/ILU-GMRES on
  a 1000-section general-MNA ladder, a GMRES/LU controlled-
  switch cross-check, Shockley diode,
  analytical underdamped RLC, a 50 MHz-class resonator, a fixed-back-EMF
  motor-armature electrical model,
  breakpoint PWM, synchronous buck, native stepwise user controls,
  checkpoint/replay, continuous pacing, and deadline-safe trip behavior. The
  report includes cold/warm timings, native-library digest, and host binding;
  hard-real-time, HIL, and competitive claims remain false. See
  `docs/SPIKES_QUALIFICATION.md` and
  `artifacts/spikes-qualification-report-0.3.0-alpha.3-2026-08-31.json`.
- Performance claims: none. Comparisons with QucsStudio, ngspice, PSIM,
  SIMPLIS, PSpice, and other engines require equal-model/equal-tolerance
  accuracy gates before timing results can be published.

### Parallel-diode electrothermal sharing reference

- State: implemented as `reference_qualification_only`; it is not general MNA
  integration or a production device model
- Behavior: common-voltage parallel Shockley-plus-series-resistance diodes,
  individual temperature-dependent parameters, backward-Euler compact thermal
  RCs, symmetric mutual thermal coupling, exact matching, explicit mismatch,
  and reproducible seeded log-normal sampling
- Results: per-device current share, loss, junction temperature, local runaway
  margin, and source-localized warning/trip events
- Purpose: permanent qualification fixtures for current hogging, matched
  sharing, thermal divergence, and later production DAE electrothermal models

### Native fixed-point field/circuit co-simulation

- State: implemented as an experimental reviewed-package workflow through the
  service and `field-circuit-validate` / `field-circuit-run` CLI commands
- Coupling: deterministic fixed-point updates between a native PEEC reduction
  provider and either the compiled linear-reference MNA workspace or the
  release-owned C++ SPIKES circuit kernel. The selected circuit engine is
  explicit in the request and result provenance.
- Owned-kernel boundary: `spike/owned-spice-workspace-request/v1` accepts only a
  reviewed structured workspace and bounded probes, composes the netlist
  internally, binds the engine result to its SHA-256, hashes the adjacent owned
  DLL, and strips host paths. Raw netlist text and caller-selected libraries are
  rejected.
- Dedicated process: `python -m python.spike_core.owned_spice_process` exposes
  only capabilities and the fixed `--request <job>/request.json --result
  <job>/result.json` interface. Controls are strict UTF-8 JSON capped at 8 MiB;
  request/result paths share one non-reparse job directory and publication is
  atomic. The hash-locked Windows x64 circuit-only recipe now produces and
  smoke-tests `spike-circuit-worker.exe` without importing the unrelated
  PyArrow/scientific desktop runtime. The trusted host supervisor admits the
  exact worker and owned-DLL SHA-256 identities before launch, creates the
  process suspended, assigns a memory-bounded kill-on-close Windows Job Object,
  then resumes it. Timeout, cancellation, memory denial, tamper rejection, and
  a packaged structured solve pass locally. The POSIX implementation uses a
  new process group plus address-space/core limits and complete-group
  termination, but still requires Linux execution evidence. Both routes remain
  `experimental`; clean-machine installation and private-CI evidence remain
  release gates.
- Validation: focused resistive fixed-point and provider-mapping fixtures pass
  in the current qualification evidence; the workflow is still blocked from
  release promotion because its validation state is `experimental`
- Limits: no automatic arbitrary-geometry PEEC network compiler, iterative
  electrothermal feedback, production-scale circuit qualification, or
  independent/measured-board correlation. The owned kernel has bounded
  nonlinear devices, but not every parser vocabulary element has a typed native
  runner binding and its C++ kernel has no native AC/phasor solve. Those gaps
  must fail closed rather
  than be represented as a validated PI/FEA co-simulation.

### PEEC plus ngspice staged hybrid

- State: operational for explicitly reviewed PEEC-network-to-circuit-node
  mappings and explicit component/subcircuit models
- Execution: deterministic R/L/C/G netlist composition followed by the
  process-isolated ngspice 46 adapter
- Security: unsafe include, library, control, shell, and source directives are
  rejected; runtime and raw-result size are bounded
- Coupling: one-way staged extraction/circuit execution; it is not iterative
  field/circuit feedback and does not silently fit PEEC Z(f)
- Validity: the combined result inherits the weakest PEEC/device-model status
  and remains approximate when the source RLCG network is approximate
- Detail: see `docs/PEEC_NGSPICE_HYBRID.md`

### PWM converter staged study (`spike/converter-study/v1`)

- State: operational orchestration for reviewed explicit device models and
  waveform bindings; physical validity remains solver/model dependent
- Inputs: structured PWM source timing and levels, a transient SPICE workspace,
  explicit input/output vectors, a measurement window, optional reviewed PEEC
  mappings, explicit device-loss bindings, and an optional compact thermal case
- Results: input/output power, efficiency, loss, ripple, inrush, component loss
  and stress records, waveforms, and optional compact thermal temperatures
- Execution: structured controls are compiled into SPICE `PULSE` sources before
  process-isolated ngspice execution; missing vectors fail instead of being
  inferred
- Coupling: one-way PEEC to ngspice to compact thermal. No iterative
  electrothermal feedback, CFD, controller-code co-simulation, or validated
  Bode extraction is claimed
- Detail: see `docs/CONVERTER_STUDY.md`

### AC PDN multiport candidate review (`spike/pdn-multiport/v1`)

- State: operational interface and placement-review workflow; numerical status
  remains approximate
- Inputs: explicitly placed user probes on the analysed net. SPIKE forwards
  their reviewed coordinates, layers, and anchor identity as candidate ports;
  it does not infer physical capacitor locations from nearby geometry.
- Results: candidate-port local, transfer, and reverse-transfer impedance data
  when returned by the selected solver, plus a placement review in the desktop
  UI.
- Physics limit: the current PEEC path retains a shared-reference capacitance
  approximation. It does not yet provide a validated arbitrary-geometry,
  multiconductor return-path extraction or signoff-qualified physical capacitor
  placement recommendation.
- Validity: `spike/pdn-multiport/v1` is a stable result contract, not evidence
  that the underlying PEEC result is validated. Reports and UI must preserve
  the solver's approximate status.

### PDN target and candidate review (`spike/pdn-review/v1`)

- State: operational screening contract
- Inputs: a solver-produced driving-point impedance sweep, target impedance,
  and explicit capacitor-bank candidates
- Placement models: direct-port shunt, supplied lumped mounting/spreading
  path, or reviewed two-port local/transfer-impedance loading
- Numerics: deterministic complex impedance reduction on the source frequency
  grid; no hidden spatial inference or interpolation
- Validity: direct-port and series-path screens remain approximate. A two-port
  candidate can only inherit validation already present in its source network.
- Remaining gate: independently correlated multiport extraction and measured
  board confirmation are required before claiming optimal physical placement.

### Reviewed multi-net PI path composition (`spike/pi-path-circuit-compile/v1`)

- State: operational experimental composition for ordered, reviewed linear
  paths; not release-qualified
- Geometry stage: each conductor segment is preflighted and extracted
  independently at its exact reviewed input/output pad anchors. One matching
  `spike/rlgc-network/v1` network is required for every segment.
- Component stage: intervening reviewed linear resistor, inductor, and capacitor
  models are stamped between their explicit component pads. Missing, duplicate,
  mismatched, unreviewed, ideal-zero, and nonlinear transitions fail closed.
- Solve stage: the combined network executes in native MNA for AC or fixed-step
  transient analysis. Constant, step, pulse, and PWL source/load profiles use
  the same bounded native source contracts.
- Result truth: all extracted segment networks and endpoint bindings remain in
  provenance. SPIKE does not fabricate a circuit-wide spatial field from the
  lumped solve; spatial fields remain the responsibility of the segment
  extraction results.
- Remaining gate: package/contact-volume geometry, nonlinear semiconductor and
  behavioral model composition through reviewed ngspice, whole-path convergence,
  independent cross-solver agreement, and measured-board correlation.

## Optional Acceleration

Acceleration changes execution only. It does not add geometry, physics,
accuracy, or validation status.

| Backend | State | Implemented scope | Important limit |
|---|---|---|---|
| NumPy assembly | Available | Hybrid DC graph-Laplacian triplets | Baseline path |
| Numba assembly | Optional | JIT acceleration of the same assembly kernel | Does not mesh or solve matrices |
| SciPy SuperLU | Available | Tested real/complex hybrid DC reduced sparse system | Single-process baseline |
| PETSc/MUMPS | Optional, Linux-first | Hybrid DC reduced sparse direct solve through `COMM_SELF` | No distributed or out-of-core orchestration |

Automatic policy selects Numba at 50,000 branches and PETSc/MUMPS at 100,000
unknowns when those backends are available. The thresholds are configurable and
the actual requested/selected backend, fallback, matrix size, residual, and
timings are recorded in result provenance. Explicitly requested unavailable
backends fail rather than silently changing policy.

Numba accelerates assembly kernels only. PETSc/MUMPS is optional and
Linux-first. Neither backend accelerates dense PEEC partial-inductance or
transient factorizations. See `docs/ACCELERATION_ARCHITECTURE.md`.

The SuperLU regression path includes a complex matrix with a real right-hand
side and verifies that the complex solution is preserved. PETSc/MUMPS catalog
capabilities are limited to the implemented single-process `COMM_SELF` adapter
and the scalar type of the local PETSc build. Use `spike accelerators` to inspect
the effective backend catalog and policy.

## Pre-Solve Workflow

The desktop worker and CLI expose:

- `preflight_analysis`: validates nets, solver capabilities, frequency setup,
  dielectric availability, source/load presence, and mesh generation.
- `preview_mesh`: creates a bounded renderer-neutral mesh before matrix assembly.
- `run_analysis`: selects a compatible solver only after the request is valid.

Mesh previews use the same hybrid topology as the PEEC adapter and include
selected-net track surfaces, zone cells, pad cells, and layer-by-layer
via barrel surfaces. A preview is not a solved field and never contains
inferred voltage, electric-field, or magnetic-field data.

Preview size is admitted against a memory budget, not a fixed global cell cap.
The desktop derives the budget from detected RAM and the user's solver-memory
policy; the worker independently reports the requested cells, admitted cells,
estimated resident bytes per cell, and effective budget. This only scales mesh
inspection. Dense PEEC, full-wave, CFD, and other engines retain their own
solver-specific limits and must not infer readiness from preview admission.

## Network Data Workbench

Touchstone network ingestion and post-processing are operational and independent
of the field-solver catalog. Available functions include S/Z/Y ingestion,
S/Z/Y conversion, real-reference renormalization, adjacent-pair mixed-mode
conversion, passivity and reciprocity checks, group delay, matched-port input
impedance, trace plotting, and Touchstone export.

This does not mean SPIKE can generate validated S-parameters from general PCB
geometry. The PEEC adapter emits an RLCG driving-point model. R and partial L
come from the hybrid conductor PEEC mesh. C and dielectric G remain explicitly
`approximate`: they use a single-reference Hammerstad/Jensen stackup estimate
for supported planar branches.

A separate bounded `geometry_uniform_channel` analysis accepts either one
straight constant-width DesignIR v2 path, two straight parallel coextensive
paths, or the explicit `piecewise_planar` connected same-layer constant-width
approximation over one simple fully covering reference zone and homogeneous
dielectric. The single path produces experimental scalar RLGC and reciprocal
two-port S. The pair uses a sparse finite-difference cross-section Maxwell
capacitance matrix, its vacuum-matrix-derived quasi-TEM L, and multiconductor
propagation to produce matrix RLGC, four-port S, and bounded geometry-derived
NEXT/FEXT. The piecewise pair requires matched parallel segments and explicit
skew/separation tolerances and uses the minimum separation conservatively. P/N
selection adds an orthonormal mixed-mode transform, differential two-port,
TDR/TDT, and normalized deterministic NRZ eye. Bends are recorded but their
discontinuity physics is omitted. Their shared request/result contracts are
`spike/si-uniform-channel-request/v1` and `spike/si-channel-result/v1`.
Field-sensitive return-path proof, accepted cross-section/frequency convergence,
frequency-dependent conductor physics, general coplanar/multiconductor
electrostatics, vias/antipads, bends, launches, connectors, arbitrary coupled
lines, IBIS/source/receiver models, statistical eyes, rare-event BER, isolated
packaged-SPIKES parity, independent correlation, and measured two/four-port
VNA/TDR evidence remain required. See `GEOMETRY_DERIVED_SI_CHANNEL.md`.

Causality checking for arbitrary imported networks remains unavailable until
DC extrapolation, resampling, window, and delay-removal policies are explicit.
The bounded channel's required DC-starting uniform grid and recorded no-window,
no-padding policy make its transform reproducible but do not establish general
causality or production validity.

## Executable Benchmarks

Run `spike benchmark` to execute the permanent analytical corpus. It currently
checks straight-trace resistance, annular via-barrel resistance, square-sheet
mesh convergence, hybrid trace/zone/pad/via connectivity, native rectangular
conductor self-inductance, the hybrid PEEC MNA path, AC-loss monotonicity, and
the wide-microstrip parallel-plate capacitance limit. It also verifies a
closed-form shared-reference two-port resistor matrix and the PDN two-port
capacitor-loading identity against an independent nodal re-solve.

The latest machine-readable run is committed at
`docs/validation/solver-benchmarks.json`.

These fixtures validate bounded units, extraction, topology, matrix assembly,
network reduction, and numerical convergence properties. The matrix/network
cases do not validate PCB multiport field extraction. None of the fixtures
replace correlation against measured boards or a trusted commercial/full-wave
solver.

## Packaged Windows Worker

The Windows desktop package is built offline-first with PyInstaller 6.21.0.
The worker bundle includes the native PEEC extension for the packaged Python
ABI and is accompanied by a SHA-256 manifest covering every bundled file.
Tauri tries this packaged worker before the repository Python development
fallback.

The worker build is rejected unless all three smoke gates pass:

1. worker health response;
2. capability-catalog response confirming the required native PEEC extension;
3. the permanent 15-case analytical benchmark corpus with zero failures and
   zero skipped cases.

These are packaging-integrity and bounded-regression gates. They do not make
the PEEC solver signoff validated, change the approximate multiport physics
boundary, or replace independent measured-board correlation.

## External Engine Adapters

The solver manager exposes workload-based recommendations, local registrations,
and allowlisted tuning through `spike solver-manager`, `solver-recommend`,
`solver-register`, `solver-unregister`, and `solver-tune`. Registration never
installs or executes software; unregistering never deletes third-party files.
Managed downloads remain disabled. See `docs/SOLVER_MANAGER.md`.

| Integration | Current executable state | Validation boundary |
|---|---|---|
| openEMS | Runnable through the isolated desktop adapter when discovery and preflight pass | Simple-patch reference fixture only; arbitrary PCB and compliance remain unvalidated |
| OpenFOAM | v2606 is installed in Ubuntu 24.04 WSL; deterministic steady open-air natural/forced convection cases run through bounded fixed-argv processes and import aligned T/U/p cell fields | Experimental air-domain surrogate only; no PCB solids, conjugate heat transfer, advanced environments, mesh/energy validation, or measured correlation |
| Siemens FloTHERM | No entitlement or adapter is present | Future licensed connector only; SPIKE cannot bundle or activate it without customer entitlement |
| FreeCAD | ECAD/MCAD workbench and inert exchange contracts are implemented; local FreeCAD kernel smoke passes | Geometry exchange is not solver or product validation |
| sparseLizard | Native Windows self-test runtime compiled without WSL; DesignIR translation for DC, AC/RLCG, thermal, and field case contracts, process isolation/cancellation, strict result conversion, and qualification reporting are implemented | The installed executable is not the production PCB adapter. Its legacy manifest is unsigned, PETSc does not expose MUMPS, and no PCB fixture evidence is installed, so arbitrary PCB execution remains disabled |
| PETSc/MUMPS | Native Windows PETSc/SLEPc and standalone MUMPS libraries are packaged for the sparseLizard development runtime, but that PETSc build does not register MUMPS as a factorization backend | PETSc LU runs the bounded DC fixture; a PETSc build configured with MUMPS plus equivalence/performance qualification is still required |

### openEMS (`external.openems`)

- State: `reference_validated` only when the isolated native-object probe passes
  and the openEMS/adapter versions match the packaged three-level patch-antenna
  convergence record; otherwise experimental, unavailable, or interface-missing
- Preparation: operational for selected rigid-board nets after preflight checks
  finite increasing frequencies, bounded frequency points, selected conductor
  geometry, copper/layer mapping, physical stackup, dielectric permittivity, and
  bounded mesh/runtime/thread options
- Execution: requires explicit 3D lumped ports and exactly one excited port;
  coordinates and impedance must be finite, and ports are never inferred from
  pads, probes, or source/load terminals; both endpoints must intersect distinct
  exported selected-net conductors
- Desktop workflow: the EMI workbench has an explicit port editor, preflight,
  case preparation, run controls, and structured result import. A full run is
  enabled only when the runtime is runnable and geometry, stackup, NF2FF request,
  resource limits, and ports pass preflight
- Geometry: tracks, zones, approximated pads, plated-via shells, conducting
  sheets, and dielectric boxes
- Results: setup XML, normalized S-parameter columns, shape-checked NF2FF
  electric-field components, directivity, radiated power, and raw artifacts.
  The desktop far-field view shows frequency-selectable polar cuts, metrics,
  angular sampling, observation radius, and the result validity boundary; the
  engineering report can retain the same structured NF2FF evidence
- Model status: the installed engine/adapter pair is reference-validated only
  for the official simple-patch fixture; arbitrary-board results keep their own
  unvalidated status and never imply regulatory compliance
- Limits: no rigid-flex translation, production multiport calibration,
  measured-board/chamber correlation, immunity workflow, or compliance signoff
- Installation: optional local/signed-offline engine only; no implicit downloads
- Process boundary: authenticated job and geometry snapshots plus trusted
  adapter source are sent to `python -I -` over stdin; the child never reopens
  mutable case inputs and the exported driver is never executed
- Result binding: imported data must match the exact random run ID, job/input
  digest, frequency grid, and mesh declaration; contained artifacts must exist
- Integrity storage: case signing keys live only in SPIKE's private application
  state, while bounded reads reject oversized job, geometry, and result JSON
- Resource bounds: 8 MiB log cap, 16 GiB engine-output quota, bounded timeout,
  and process-tree termination on timeout/quota; explicit user cancellation and
  Windows Job Object hard memory controls remain pending
- CLI: `spike external-engines`, `spike openems-prepare`, and
  `spike openems-run` expose the implemented catalog/prepare/run workflow

The validation record and numerical results are documented in
`docs/validation/OPENEMS_REFERENCE_VALIDATION.md`. This is not product-class or
compliance validation for arbitrary boards.

The implemented NF2FF path is: define selected/return nets and explicit ports in
the EMI workbench; request bounded frequencies, theta/phi sampling, radius, and
phase center; preflight and prepare the authenticated case; create the openEMS
NF2FF box after final mesh construction; execute FDTD and `CalcNF2FF`; then
validate result shape, finite values, run binding, frequency grid, mesh
declaration, and contained artifacts before display. Successful execution is a
computed solver result, not automatic validation of that PCB.

External-engine catalog capabilities are adapter-level claims and list only the
surface SPIKE implements, not every feature present in the external engine.
Contract tests cover catalog gating, preflight, private UUID jobs, path
containment, isolated trusted-source execution, and unavailable-engine recovery;
this description intentionally does not depend on an exact test count.

FastHenry and FastCap are catalog/discovery entries with exporters and result
importers still pending. OpenFOAM discovery exists, but the validated
multi-region case generator remains gated. ngspice retains its separate
explicit-netlist circuit adapter.

### Elmer FEM (`external.elmer`)

- State: discovery and explicit local registration only; no runnable SPIKE
  adapter exists
- Discovery: registered `external.elmer` path, `SPIKE_ELMER_HOME`, `PATH`, or
  SPIKE's optional local runtime directory may provide `ElmerSolver`; discovery
  never installs, probes, or executes it
- Implemented capabilities: none
- Candidate upstream scope: DC conduction, electrostatic capacitance,
  magnetostatic and harmonic electromagnetic fields, solid thermal,
  electrothermal, and lumped-circuit coupling
- Required gate: a bounded case translator, fixed process adapter, normalized
  result contract, resource limits, validation fixtures, and independent
  correlation before any PI, SI, thermal, or EMI workload can become runnable
- Overclaim guard: a detected `ElmerSolver` remains
  `installed_adapter_pending`, `model_status=unsupported`, and exposes no
  `run` action or validated claim

### sparseLizard (`external.sparselizard`)

- State: deterministic DesignIR translation, bounded exact-name process launch,
  cancellation, Windows Job Object memory enforcement, strict result import,
  and a five-class qualification report are implemented; no production
  `spike-sparselizard-adapter` executable is installed on the current machine
- Interface: process-isolated `spike-sparselizard-adapter`, never a
  project-supplied executable or in-process linked library
- Implemented adapter surface: `spike/sparselizard-case/v1` exports hybrid PCB
  mesh cells, copper/dielectric materials, selected conductors, explicit
  terminals, resource limits, and workload-specific DC, AC/RLCG, thermal, or
  field requests. `spike/sparselizard-result/v1` imports digest-bound mesh,
  scalar, vector, matrix, and convergence data only after strict validation
- CLI: `spike sparselizard-prepare REQUEST --case-dir DIR` is operational;
  `spike sparselizard-run CASE_DIR` remains unavailable until an exact adapter
  executable is installed or explicitly registered
- Downstream use: accepted results normalize to `AnalysisResult`, including
  scalar and vector field samples, mesh metadata, impedance matrices, RLCG,
  warnings, and provenance without promoting the source model status
- Candidate upstream scope: DC conduction, solid electrothermal coupling,
  electrostatic capacitance, harmonic magnetodynamics/Maxwell fields, and
  lumped-circuit coupling
- Current trust: exact executable name, fixed invocation, case/result digest
  binding, bounded streams/files/time, POSIX quotas, Windows Job Object process
  and memory limits, cancellation, and strict result validation. Production
  activation additionally requires a CMS-signed manifest, pinned artifacts,
  signed PETSc/MUMPS readiness, staging, self-test, and rollback
- License: sparseLizard is GPL-2.0-or-later; any linked adapter must use
  GPL-compatible terms and satisfy redistribution obligations
- Validation: the permanent plan contains analytical PCB DC, AC/RLCG, thermal,
  electrostatic, and harmonic-field fixtures with explicit tolerances. The
  current report is `blocked`: zero fixture evidence files are installed, the
  runtime manifest is unsigned, and PETSc has not registered MUMPS. The catalog
  therefore advertises no executable PCB physics capability and no validated
  sparseLizard result
- Overclaim guard: source/library detection and case preparation do not enable
  S-parameters, closed-loop SPICE, PCB far field, airflow, or EMI compliance

### Parallel SPIKES generic FEM runtime handoff

`D:\PROJECTS-DEV\SPIKES` is the separately developed native generic solver
suite. Its current Milestone 0 process boundary now declares deterministic 1D
diffusion and 2D triangular stationary/transient FEM verification workloads in
addition to capability probing and self-tests. It also declares two explicitly
prepared verification routes: compact frequency-domain Maxwell solves with
reused immutable system storage, and bounded rational-network conditioning.
Neither prepared route accepts general PCB geometry or advertises product
physics. The 2D core includes mixed
Dirichlet/Neumann/Robin boundaries, pure-Neumann gauge handling, adaptive
red-green refinement, backward Euler and BDF2 reference paths, and bounded
process/C-ABI execution. These are manufactured-solution verification
capabilities, not executable PCB PI, AC/RLCG, thermal, or coupled-field
backends. SPIKE therefore keeps `spike.spikes-native-process/v0.1` fail-closed
for product physics.

SPIKE can discover an installed runtime from an explicit path, the
`SPIKES_NATIVE_SOLVER` environment variable, or `PATH`, then invoke only
`--capabilities` through a bounded no-shell probe. A source checkout path is
never embedded. The probe accepts ABI v1 and records the runtime as
`discovery_only`; even a successful `verification_only` handshake cannot make
PCB product physics eligible.

The 2026-08-31 local integration audit built and probed
`spike-native-solver.exe` with MSVC. The private runtime capability document
validated against `spike/native-capability/v1`, the runtime DLL retained its
four-function C ABI, and the refreshed private Release corpus passed 308/308
tests. Seven focused AddressSanitizer tests passed for the rectangular-TE modal
scattering path, strict prepared modal-DtN process route, and conforming via
volume lineage compiler. The earlier affine-P2 H(curl), de-embedding, and
conditioned-network verification slices remain part of the passing corpus.
The prepared modal route accepts only canonical, hash-bound complex-symmetric
CSR operators and modal traces; it does not reconstruct or prove a PML model.
This is local verification evidence only: PETSc, hypre and MPI remain false in
the probed manifest, all prepared routes remain `verification_only`, and no
portable package or private CI evidence exists. The public adapter continues
to advertise only probe and self-test as runnable capabilities while listing
the prepared routes as verification capabilities.

The audit also detected an external change to the protected private artifact
`quasi_result.egres`: it is now 11,878 bytes with SHA-256
`D5734DD5BFDB12FD50F425CF4C257B5A33AAB97DE6EF906DC19613078DDAE155`, rather
than the recorded 11,877-byte `34A1F67D...` baseline. The solver tranches did
not modify or rebaseline it. Artifact-integrity acceptance therefore remains
failed until the owner confirms the new file or restores an authoritative
copy.

The next PCB-capable handoff must add a versioned model/mesh contract that
preserves canonical source object IDs, net IDs, copper layer IDs and spans,
materials, boundary classes, terminal selections, and result provenance. The
SPIKE-side reference contract now supplies exact capsule pad/slot boundaries,
explicit routed-via and plated through-pad barrel conductor volumes, and annular
ownership checks. The native suite must consume those shapes without converting
them back to ellipses or collapsing barrel spans. It must also represent zone
holes and antipads, castellations, blind/buried/microvias, and conformal
stitched-layer interfaces. Scalar/vector results must retain source ownership and layer
identity so an invalid or out-of-owner field cannot be rendered as a valid PCB
result.

The current geometry-handoff evidence is 593 passing canonical backend tests
with one opt-in external KiCad fixture skipped, plus 32 passing root integration
contract tests. Those tests establish deterministic transport and rejection
behavior only; they are not measured validation of current density, via stress,
impedance, or thermal fields.

SPIKES must remain unavailable for arbitrary PCB execution until its
capability manifest names the supported formulation and geometry, process
cancellation/resource bounds pass, result conversion is qualified, and the
relevant analytical, independent, and measured validation evidence passes.
This requirement is feedback to the parallel solver program; it does not
promote the current adapter or replace SPIKE's existing PI solvers.

## Unavailable

### Surface MoM (`spike.mom_surface`)

No executable or validated MoM implementation is packaged.

### Full-Wave 3D (`spike.fullwave_3d`)

No executable or validated native FEM/FDTD solver is packaged, so this solver
ID remains unavailable. The optional openEMS process adapter is a separate,
executable path and does not enable `spike.fullwave_3d`. A matching openEMS
runtime may be `reference_validated` and runnable for the simple-patch fixture,
while an arbitrary-PCB NF2FF result remains `not_validated`. Gmsh, Elmer,
openEMS, and GetDP are not downloaded implicitly. Native full-wave status and
product-class PCB validation cannot advance until deterministic bundles,
additional fixtures, explicit applicability limits, material and boundary
validation, and external/measurement correlation are complete.

## Environment Profiles

`spike/environment-profile/v1` profiles cover standard lab air, sealed/potted,
automotive, marine, aerospace altitude, vacuum/space, and user-defined inputs.
Domain readiness checks only whether required PI, SI, thermal, or EMI metadata
is present and internally consistent. A ready profile does not validate a
solver, represent a complete enclosure or flow domain, qualify hardware for an
environment, or assess compliance. Certification remains explicitly
`not_assessed`.

## Required Next Gates

1. Add a convergent panel/BEM capacitance matrix with via/antipad geometry and
   independent FastCap/FEM/measurement correlation.
2. Add proximity-effect current redistribution and validated Huray/gradient
   roughness models.
3. Add automatic production-run mesh-convergence execution and error thresholds.
4. Validate PDN impedance against RLC/SPICE fixtures and measured boards.
5. Correlate the implemented target/candidate review against measured PDN
   fixtures, add bias/temperature/tolerance-aware component models, and feed it
   validated location-specific multiport extraction before calling it physical
   capacitor optimization.
6. Replace dense partial-inductance assembly for motherboard-scale execution;
   current Numba and PETSc/MUMPS support does not address this matrix.
7. Qualify Numba and Linux PETSc/MUMPS bundles against baseline numerical and
   memory/performance fixtures.
8. Extend the existing simple-patch openEMS reference gate with representative
   PCB, enclosure, cable/connector, and measured chamber fixtures; require board-
   specific mesh convergence and correlation before promoting a PCB result.
9. Promote SI beyond the bounded experimental single/pair extractors only after
   analytical modal, four-port S/NEXT/FEXT, independent-field, and measured
   coupled-line fixtures pass with accepted convergence and uncertainty.
