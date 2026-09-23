<!-- SPDX-License-Identifier: MIT -->

# Stage-one PI validation matrix

Stage-one examples use the original [SPIKE PI reference board](../examples/pi/reference_board/README.md),
copyright Yawar Badri and licensed MIT within its own directory. No
third-party board is redistributed as the release benchmark. The board is a
synthetic electrical fixture, not a manufactured product or measurement.

The reproducible [evidence](../examples/pi/reference_board/validation/pi-reference-evidence.json)
records the KiCad file SHA-256, native solver binary SHA-256, solver IDs,
assumptions, thresholds, statuses, and 17 executable checks. Its current
result is **17/17 passed** for the synthetic board and
`release_validated: false`. The board-derived DC and AC results remain
`approximate` even when a benchmark check passes.

| PI capability | Example / check | Present evidence | Release conclusion |
| --- | --- | --- | --- |
| KiCad import and board validation | Four-net reference board | Exact counts: 6 tracks, 2 vias, 12 pads, 2 filled zones, 8 components, 3 stackup rows | Fixture import passes; importer breadth needs a separate corpus. |
| Hybrid mesh and preflight | VLOAD rail | v3 mesh has cells and branches; solver admission passes | Structural handoff passes; this is not field-solution accuracy. |
| Routed DC on traces, pads, vias, and zone | VIN, VLOAD, VAUX | Three completed approximate results; VLOAD includes 3 tracks, 2 vias, 1 zone, 4 pads | Execution passes on fixture. |
| DC analytical resistance | VAUX straight trace | Closed-form `L/(sigma*w*t)` differs by 0.067%; allowed 2% for pad attachments | Bounded analytical comparison passes. |
| DC conservation | VAUX straight trace | Copper loss versus current times load drop agrees within 1.2e-11 relative; allowed 1% | Conservation check passes on fixture. |
| DC mesh convergence | VAUX and VLOAD | Three ordered refinement levels each; unchanged solver thresholds pass | Fixture convergence passes; real-board convergence remains unresolved. |
| Quasi-static AC PEEC | VIN, VLOAD, VAUX | Three completed approximate results with nonnegative sampled resistance; VLOAD includes trace, via, pad, and zone | Fixture execution and sampled passivity pass; real-board passivity remains unresolved. |
| Reviewed series component path | VIN to VLOAD through R1 | KiCad-imported R1 pads validate; native path circuit completes with explicit 0.1 ohm element and relative residual below 1e-9 | Explicit fixture path passes; general circuit behavior is not implied. |
| Multi-net batch and results | VIN DC, VAUX DC, VLOAD AC | Three independent requests and a versioned PI batch report; JSON and HTML examples retained | Portable result workflow passes on fixture. |
| PDN multiport and capacitor placement sensitivity | C2 placed versus C3 unpopulated | Both reviewed candidate ports appear in extracted multiport; finite one-part search compares equal 47 uF/8 mOhm/0.6 nH parts | C3 ranks lower worst-target ratio in this model (0.245 versus 0.266); **not** a hardware optimum. |
| Capacitor loading algebra | Separate passive two-node reference | 17-frequency independent nodal re-solve within 1e-10 relative | Circuit reduction passes; it does not validate board extraction or placement. |
| Reports and visualization | Checked JSON and HTML; full desktop result UI | Portable data/rendering example exists; UI checks are separate | Desktop visual comparison and packaged result parity are pending. |
| Extension PI execution | Extension boundary | Worker stage policy rejects excluded methods; no audited PI-only extension package has been run | Pending. |
| Real-board engineering correlation | Marble and other complex boards | Marble AC matrix fails the solver's non-passivity gate; a separate board has failed DC convergence | Blocked. No measured agreement or signoff claim. |
| Source/package parity and clean install | Desktop release artifacts | Local app starts, but the current copied worker is not a public PI-only bundle | Blocked. |

## Interpretation and promotion

The reference board is intentionally modest so each feature has a clear
location, controlled source/load, and reproducible model. The comparison of C2
and C3 uses equal nominal parts and an ideal common reference. It omits
regulator dynamics, fabrication and mounting tolerances, bias/temperature
derating, aging, measured return impedance, and hardware measurements.

The independent checks validate specific calculations and contracts; they do
not convert an approximate field model into a validated physical solver. The
real-board AC failure has a diagnosed self/mutual-inductance inconsistency.
Keep that failure gate intact until a consistent conductor model, convergence
cases, and knowledgeable numerical review support a correction. A public
release requires every retained PI workflow to have explicit pass/fail
evidence from source and packaged builds, safe redistributable example assets,
and truthful result-level model status.
