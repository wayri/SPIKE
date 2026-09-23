# SPIKES solver and interactive qualification

`spikes qualification` runs a bounded, versioned corpus against an explicitly
selected owned C++ library. It combines correctness gates with cold/warm timing
observations; timing is reported only for the selected host and is never turned
into an automatic competitive claim.

```powershell
.\spikes.cmd qualification `
  --library build-peec-native\spikes_c_api.dll `
  --repetitions 3 --wall-steps 20 `
  -o artifacts\spikes-qualification-report.json
```

The corpus covers:

- a balanced loaded Wheatstone bridge with a zero differential solution;
- a 200-section resistor ladder with a closed-form interior voltage;
- a two-worker preconditioned-CG SPD ladder with a closed-form endpoint;
- a 1000-section general-MNA ladder cross-checking sparse LU and ILU-GMRES,
  with a structural-nonzero storage gate;
- a restarted-GMRES controlled-switch Newton system cross-checked against LU;
- a Shockley diode operating point checked against the analytic diode law;
- an underdamped series-RLC step checked against its second-order solution;
- a 50 MHz-class lumped RF resonator checked against the damped closed form;
- a fixed-speed motor R-L armature/current/torque fixture checked against its
  fixed-back-EMF closed form;
- breakpoint-aligned PWM on/off levels and factorization reuse;
- a synchronous smooth-switch buck checked over a settled ten-period window;
- user control applied to an RC plant through one native C-ABI solve per step;
- momentary-key release and exact checkpoint/restore replay;
- bounded continuous wall-clock pacing with native compute-latency statistics;
- deterministic consecutive-deadline-overrun trip to safe inputs.

Every case records a cold execution, configured warm repetitions, median and
p95 elapsed time, behavior-specific observations, and solver diagnostics. The
report binds measurements to the native-library SHA-256 and host runtime.

## Real-time boundary

The interactive fixture proves functional closed-loop semantics: a control
changes the next simulation step, all requested steps execute, checkpoints
replay exactly, and deadline failures force declared safe inputs. The current
plant holds one persistent native circuit/session handle, updates a constant
independent source, advances one native step, and reads the accepted
state without reconstructing the circuit through Python.

The report always keeps `hard_realtime_qualified`, `hil_qualified`, and
`competitive_speed_claim_eligible` false. Session v1 can use the native sparse
assembly path for large systems and retains bounded factorization state plus
checkpointable hybrid companion history across calls. It preserves global
PULSE/PWL time and exact internal breakpoints. Promotion still requires
adaptive error control, preallocated/lock-free
data paths, deterministic-WCET analysis, latency/jitter testing under load,
physical I/O timestamping, watchdog/fault injection, and target-specific HIL
correlation.

The committed latest run is
`artifacts/spikes-qualification-report-0.3.0-alpha.3-2026-08-31.json`. The associated whole-repository
test execution is recorded in `artifacts/spikes-regression-report.json`.

The first-party, redistributable equal-model application decks are in
`benchmarks/public_application` with CC0 licensing and explicit provenance.
They are correctness fixtures, not vendor-model or hardware correlation data.
