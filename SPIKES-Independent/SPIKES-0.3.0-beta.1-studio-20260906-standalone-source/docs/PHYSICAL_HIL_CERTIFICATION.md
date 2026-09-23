# Physical hard-real-time and HIL gate

`python/spikes/hil_certification.py` defines the fail-closed
`spikes/physical-hil-evidence/v1` gate. A passing package must bind the exact
host, solver binary, target serial, firmware hash, physical I/O fixture,
calibration certificate and raw cross-clock trace. It also requires a declared
period, minimum duration and cycle count, zero deadline misses, bounded
p99.999 response latency and jitter, hardware cross-timestamp error, physical
fault injection, observed safe states, and an independently verified signed
manifest.

Simulation, software loopback, self-authored summaries, or an unverified
`status: passed` field cannot satisfy the gate. Qualification applies only to
the named host/target/firmware/fixture combination.

This workstation exposes COM3, COM8 and COM9, but no target identity,
protocol, firmware, I/O fixture, calibration artifact or independent signer
was supplied. SPIKES therefore does not open or drive those ports and the
physical certification gate remains blocked. Doing otherwise could interfere
with unrelated connected equipment and would not produce defensible evidence.

Evaluate an evidence package with the shipped command:

```powershell
python bin/evaluate_spikes_hil_evidence.py evidence.json `
  --period-ns 100000 `
  --maximum-response-latency-ns 80000 `
  --maximum-absolute-jitter-ns 5000 `
  --output hil-gate.json
```

The process returns zero only when every gate passes and returns two for a
blocked package. The evaluator recomputes artifact digests and never trusts an
embedded `status` field.
