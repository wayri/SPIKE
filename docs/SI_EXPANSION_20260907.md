<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright (c) 2026 SigHarmonic -->
# SI expansion — 2026-09-07

Implemented in the public Python reference runtime and React result renderer.
This is an engineering-analysis increment, not a claim of HyperLynx parity,
native SPIKES feature parity, protocol compliance, or production qualification.
No third-party implementation or restricted book content was copied.

## Available now

- Explicit loaded NEXT/FEXT analysis for 4–16-port networks: physical port roles,
  one resistor per port, Thevenin source voltage, signed victim waveforms and
  full-record peak magnitudes. Geometry-channel requests accept `crosstalk_model`.
  Existing matched S-parameter NEXT/FEXT results retain their original meaning.
- Per-port matched driving-point R/X/|Z| in ordinary network reports;
  `analyze_impedance` additionally accepts explicit other-port resistive loads.
  Open/pole and ill-conditioned samples are masked, not replaced with arbitrary
  large values. Legacy `input_impedance_port1` is explicitly identified as
  open-circuit Z11, not matched input impedance.
- Sampled magnitude peaks/dips and reactance-crossing brackets. These are
  candidates for refined investigation, not fitted poles, Q factors or proven
  physical resonances. Narrow resonances may be missed by a coarse grid.
- Actual result-panel frequency/time plots, numerical ticks, zoom/cursors,
  separate matched-wave versus loaded-voltage units, impedance plots,
  masked gaps, candidate lists, CSV and offline SVG/HTML exports.
- Identity-bound two-port board → connector/cable → board chains through
  `run_si_workflow`, with `channel.kind = "multiboard"`. Segment model SHA-256,
  owner identities, port direction and adjoining reference-plane IDs are
  checked. Networks use identical grids and explicit common normalization.
- Batched loaded-network solves: 128-frequency working chunks, shared multiple
  RHS solves and vectorized noise propagation. The matched impedance path
  skips unnecessary matrix solves.

## Executable examples and evidence

From the repository root (choose fresh output paths when rerunning immutable
benchmark/export evidence):

```powershell
python scripts/run_si_crosstalk_example.py --output build/si-crosstalk-geometry-20260907
python scripts/benchmark_si_crosstalk.py --output build/si-crosstalk-analytical-20260907/report.json
python scripts/benchmark_si_multiboard.py --output build/si-multiboard-analytical-20260907
python scripts/benchmark_si_loaded_response.py --output build/si-loaded-batch-benchmark-20260907.json
node app/scripts/export-si-crosstalk-results.mjs --input build/si-crosstalk-geometry-20260907/result.json --output build/si-crosstalk-geometry-20260907/ui-export
```

The geometry example runs the actual service handler and writes design,
request, result and hashes. Its output includes the four-port impedance report
and a finite-edge aggressor pulse with unequal terminal resistances.
Waveform samples use the explicitly DC-inclusive uniform network grid:
`dt = 1 / ((2*N - 1)*df)`. No invented DC or automatic causality repair.
CSV preserves retained samples; a decimated export is not a full-resolution
history. Signed victim extrema are retained when reducing the time trace.

Analytical evidence produced this session:

- Even/odd scalar ABCD oracle versus coupled telegrapher solution: max error
  1.94e-14; direct Fourier sum/convolution versus loaded report: 6.56e-16.
- Board/connector/board total delay 0.4 ns: complex transmission error 1.08e-15.
- Local kernel benchmark, four ports/three RHS with identical complex loads:
  1,025 frequencies 35.44 ms scalar versus 1.78 ms batched; 4,097 frequencies
  252.87 ms versus 11.96 ms. Five measurements after warm-up. Observed outputs
  were identical. These are kernel measurements, not whole-solver speedups.

## Next capability requirements

Priority order for subsequent implementation and acceptance:

1. General coupled N-port multiboard graphs, explicit harness and connector
   models, reference/return mapping and joint aggressor studies. Current chains
   are serial two-port models only, not cross-board electromagnetic extraction.
2. Frequency-adaptive impedance/resonance refinement with fitted pole/Q
   uncertainty and analytical RLC/cavity checks. Do not treat sampled extrema
   as a resonance qualification result.
3. Full package/via/reference-plane discontinuity extraction, frequency-dependent
   conductor/dielectric losses and convergence against independent field solvers.
4. Executable nonlinear source/receiver coverage, AMI/CDR/equalization, jitter
   and noise correlations, power-aware SI, timing and authorized protocol limits.
5. Measured coupon/system correlations, uncertainty budgets, wider Linux/native
   packaging tests and deployment evidence. Local analytical tests are not
   measured qualification.

Requirements comparison source, not an implementation source:
[Siemens HyperLynx SI](https://www.siemens.com/en-us/products/pcb/hyperlynx/signal-integrity/)
and its [official multiboard training scope](https://training.plm.automation.siemens.com/ilt/iltdescription.cfm?pID=298990-US_____EDA__2510___1199).
The user's earlier books and repository links must be re-identified before
review; unavailable material has not been claimed as reviewed.

## Subsequent coupled-network increment

See [coupled graph and RLC fit implementation](SI_NETWORK_GRAPH_INCREMENT_20260907.md)
for the implemented N-port workflow, bounded resonance fitting and admitted
public measured-data processing. This supersedes the serial-two-port-only
network limitation above, not the cross-board field or physical-mode gates.

## Validation boundary

The final focused regression passed 99 Python tests with warnings treated as
errors, the channel/crosstalk/workflow UI assertions, and the architecture guard.
The final service example and renderer output are under
`build/si-crosstalk-geometry-final-20260907/`.

The generated export has numerical/CSV fidelity tests. Automated browser
visual inspection of the local-file report was blocked by browser URL policy;
that block was not bypassed. The full application TypeScript check and focused
SI renderer tests passed after a concurrent owner fixed an unrelated ES2020
compatibility issue. Native desktop packaging was not qualified by this check.
