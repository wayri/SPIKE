# SPIKES Wave 1 owned-engine benchmarks

Wave 1 adds a versioned owned-kernel corpus without promoting a competitive
claim. Generate the report with:

```powershell
.venv\Scripts\python.exe scripts\run_spikes_wave1_benchmarks.py `
  --library build-spikes-hybrid\spikes_c_api.dll `
  --repetitions 2 `
  --timeout 120 `
  --output artifacts\spikes-wave1-benchmark-2026-08-30.json
```

The corpus includes 500- and 2,000-section SPD sparse ladders at requested
thread counts 1, 2, and 4; a nonsymmetric controlled-switch Newton/GMRES case;
a singular floating network whose bounded, explicit failure is the expected
result; and a synchronous buck with 80 ns break-before-make dead time, source
resistance, switch resistance, inductor DCR, and capacitor ESR.

Every thread configuration runs in an isolated worker. The report separates:

- cold process elapsed time, including interpreter launch and DLL loading;
- first execution time after the library is loaded;
- subsequent warm execution samples and their median;
- requested versus observed solver thread count and convergence diagnostics;
- current-process peak working set. On Windows this comes from
  `GetProcessMemoryInfo`; the worker launches no child process, so it is also
  the isolated benchmark process-tree peak.

Accuracy and expected-failure behavior gate every timing record. Missing,
timed-out, malformed, inaccurate, or incorrectly converged runs fail the case.
`performance_claim_eligible` remains `false` regardless of a clean run.

## Converter boundary

The converter is a circuit-level switching fixture, not a compact-device or
loss-model qualification. Its switches are smooth, bidirectional conductances
with fixed on/off resistance. The fixture excludes semiconductor charge,
reverse recovery, nonlinear capacitance, gate-driver impedance and mismatch,
electrothermal feedback, magnetic saturation and hysteresis. Its accuracy gate
checks convergence, steady conversion ratio, ripple and rail bounds only.

The `medium` and `large` labels are bounded tiers of this owned corpus. They do
not establish performance on public industry decks. Cross-engine performance,
whole-product parity, hard-real-time and HIL gates remain blocked.
